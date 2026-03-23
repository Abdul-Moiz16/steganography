from __future__ import annotations

"""Stage orchestrator for the final proposal-aligned experiment pipeline.

`PipelineRunner` is the only layer that should handle file I/O for deferred
algorithm components. Deferred embedding, encryption, and detector functions
stay closed-loop (in-memory in/out), while this module:
- reads and writes manifests,
- resolves relative paths,
- materializes artifacts in the canonical layout,
- keeps the operational pipeline aligned with `proposal_updated_3.tex`.
"""

import hashlib
import random
import secrets
from pathlib import Path
import json

from src.common.contracts import ENCRYPTION_STATES, METHODS, PAYLOAD_LEVELS
from src.data.images import (
    load_bytes,
    load_image,
    save_bytes,
    save_png,
    standardize_and_save_variants,
)
from src.data.manifests import (
    CoverRecord,
    PayloadRecord,
    StegoRecord,
    read_rows_csv,
    unique_group_ids,
    write_dataclass_csv,
    write_json,
    write_rows_csv,
)
from src.detection.statistical import (
    calibration_chi_square_score,
    chi_square_dct_score,
    chi_square_spatial_score,
    rs_analysis_score,
    sample_pairs_score,
)
from src.embedding.dct import embed_dct_lsb_jpeg
from src.embedding.encryption import encrypt_payload_aes_256_cbc
from src.embedding.lsb import embed_lsb
from src.evaluation.metrics import (
    aggregate_by_groups,
    try_parse_score,
)
from src.evaluation.plots import generate_metrics_figures
from src.pipeline.config import PipelineConfig


def _stable_iv(group_id: int, payload_level: str) -> bytes:
    """Create a deterministic 16-byte IV from group and payload level."""
    digest = hashlib.sha256(f"{group_id}:{payload_level}".encode("utf-8")).digest()
    return digest[:16]


class PipelineRunner:
    """Execute pipeline stages for the final, proposal-locked experiment design."""

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.paths = config.paths

    def init_layout(self) -> None:
        """Create the full expected directory hierarchy for data/results artifacts."""
        self.paths.ensure_layout()

    def _resolve_manifest_path(self, value: str | Path) -> Path:
        """Resolve relative manifest paths against project root for local access."""
        path = Path(value)
        return path if path.is_absolute() else (self.config.project_root / path)

    def _to_project_relative(self, value: Path | str) -> str:
        """Store manifest paths relative to project root when possible."""
        path = self._resolve_manifest_path(value)
        try:
            return str(path.relative_to(self.config.project_root))
        except ValueError:
            return str(path)

    def _detectors_for_method(self, method: str) -> list[str]:
        if method == "lsb":
            return ["rs", "chi_square_spatial", "sample_pairs"]
        if method == "dct":
            return ["chi_square_dct", "calibration_chi_square"]
        raise ValueError(f"Unknown method: {method}")

    def standardize_covers_from_index(
        self,
        input_index_csv: Path,
        output_manifest_path: Path | None = None,
    ) -> Path:
        """Standardize raw cover images into branch-specific grayscale storage.

        Required input columns:
        group_id, source, dataset, orig_id, caption_id, caption_text,
        raw_image_path, qc_pass, qc_score, seed
        """
        rows = read_rows_csv(input_index_csv)
        records: list[CoverRecord] = []
        for row in rows:
            group_id = int(row["group_id"])
            source = row["source"]
            spatial_path = self.paths.cover_path(group_id, source, "spatial")  # type: ignore[arg-type]
            frequency_path = self.paths.cover_path(group_id, source, "frequency")  # type: ignore[arg-type]
            standardize_and_save_variants(
                input_path=self._resolve_manifest_path(row["raw_image_path"]),
                spatial_output_path=spatial_path,
                frequency_output_path=frequency_path,
                size=self.config.image_size,
                jpeg_quality=self.config.jpeg_quality,
            )
            records.append(
                CoverRecord(
                    group_id=group_id,
                    source=source,
                    dataset=row["dataset"],
                    orig_id=row["orig_id"],
                    caption_id=row["caption_id"],
                    caption_text=row["caption_text"],
                    spatial_path=self._to_project_relative(spatial_path),
                    frequency_path=self._to_project_relative(frequency_path),
                    qc_pass=row["qc_pass"].lower() == "true",
                    qc_score=float(row["qc_score"]),
                    seed=int(row["seed"]),
                )
            )

        output_path = output_manifest_path or (self.paths.manifests_dir / "covers_master.csv")
        write_dataclass_csv(output_path, records)
        return output_path

    def build_payload_manifest(
        self,
        covers_manifest_path: Path,
        output_manifest_path: Path | None = None,
        write_payload_files: bool = False,
    ) -> Path:
        """Generate payload rows for all groups, payload levels, and encryption states.

        Payload artifacts store deterministic pseudo-random streams sized for the
        proposal's nominal spatial capacity. DCT-LSB rows consume prefixes of
        those streams according to their own eligible-coefficient capacity.
        """
        cover_rows = read_rows_csv(covers_manifest_path)
        groups = unique_group_ids(cover_rows)
        if len(groups) != self.config.n_groups:
            raise ValueError(
                f"Expected {self.config.n_groups} groups in covers manifest, got {len(groups)}."
            )

        rng = random.Random(self.config.payload_seed)
        records: list[PayloadRecord] = []
        for group_id in groups:
            for payload_level in PAYLOAD_LEVELS:
                payload_stream_bits = self.config.spatial_payload_bits(payload_level)
                payload_bytes = self._generate_payload_bytes(payload_stream_bits, rng)
                fill_rate = self.config.payload_fill_rates[payload_level]
                for encryption in ENCRYPTION_STATES:
                    payload_path = self.paths.payload_path(group_id, payload_level, encryption)
                    iv = _stable_iv(group_id, payload_level)

                    if write_payload_files:
                        payload_path.parent.mkdir(parents=True, exist_ok=True)
                        if encryption == "plain":
                            payload_path.write_bytes(payload_bytes)
                        else:
                            key = secrets.token_bytes(32)
                            ciphertext = encrypt_payload_aes_256_cbc(payload_bytes, key=key, iv=iv)
                            payload_path.write_bytes(ciphertext)

                    records.append(
                        PayloadRecord(
                            group_id=group_id,
                            payload_level=payload_level,
                            encryption=encryption,
                            payload_path=self._to_project_relative(payload_path),
                            payload_stream_bits=payload_stream_bits,
                            fill_rate=fill_rate,
                            bit_depth=self.config.primary_lsb_bit_depth,
                            aes_iv=iv.hex(),
                            aes_key_id=self.config.aes_key_id,
                            seed=self.config.payload_seed,
                        )
                    )

        output_path = output_manifest_path or (self.paths.manifests_dir / "payload_manifest.csv")
        write_dataclass_csv(output_path, records)
        return output_path

    def build_stego_manifest(
        self,
        covers_manifest_path: Path,
        payload_manifest_path: Path,
        output_manifest_path: Path | None = None,
    ) -> Path:
        """Enumerate all main stego jobs from covers x methods x payloads x encryption."""
        cover_rows = read_rows_csv(covers_manifest_path)
        payload_rows = read_rows_csv(payload_manifest_path)

        payload_index = {
            (int(row["group_id"]), row["payload_level"], row["encryption"]): row
            for row in payload_rows
        }

        records: list[StegoRecord] = []
        for cover in cover_rows:
            group_id = int(cover["group_id"])
            source = cover["source"]
            for method in METHODS:
                cover_path = (
                    cover["spatial_path"] if method == "lsb" else cover["frequency_path"]
                )
                for payload_level in PAYLOAD_LEVELS:
                    for encryption in ENCRYPTION_STATES:
                        payload_row = payload_index[(group_id, payload_level, encryption)]
                        payload_path = self._to_project_relative(payload_row["payload_path"])
                        stego_path = self.paths.stego_path(
                            group_id=group_id,
                            source=source,  # type: ignore[arg-type]
                            method=method,  # type: ignore[arg-type]
                            payload=payload_level,  # type: ignore[arg-type]
                            encryption=encryption,  # type: ignore[arg-type]
                        )
                        embed_params = self._embed_params_json(method, payload_level)
                        records.append(
                            StegoRecord(
                                group_id=group_id,
                                source=source,
                                method=method,
                                payload_level=payload_level,
                                encryption=encryption,
                                cover_path=self._to_project_relative(cover_path),
                                payload_path=payload_path,
                                stego_path=self._to_project_relative(stego_path),
                                embed_params=embed_params,
                                seed=self.config.embed_seed,
                            )
                        )

        output_path = output_manifest_path or (self.paths.manifests_dir / "stego_manifest.csv")
        write_dataclass_csv(output_path, records)
        return output_path

    def run_embedding_stage(
        self,
        stego_manifest_path: Path,
        execute: bool = False,
    ) -> int:
        """Create stego artifacts from manifest rows.

        With ``execute=False`` this is a dry-run counter only.
        """
        rows = read_rows_csv(stego_manifest_path)
        if not execute:
            return len(rows)

        for row in rows:
            payload_bytes = self._resolve_manifest_path(row["payload_path"]).read_bytes()
            params = json.loads(row["embed_params"])
            method = row["method"]
            if method == "lsb":
                cover_image = load_image(self._resolve_manifest_path(row["cover_path"]))
                stego = embed_lsb(
                    cover_image=cover_image,
                    payload_bytes=payload_bytes,
                    fill_rate=float(params["fill_rate"]),
                    bit_depth=int(params["bit_depth"]),
                )
                save_png(stego, self._resolve_manifest_path(row["stego_path"]))
            elif method == "dct":
                cover_jpeg_bytes = load_bytes(self._resolve_manifest_path(row["cover_path"]))
                stego_bytes = embed_dct_lsb_jpeg(
                    cover_jpeg_bytes=cover_jpeg_bytes,
                    payload_bytes=payload_bytes,
                    fill_rate=float(params["fill_rate"]),
                    jpeg_quality=int(params["jpeg_quality"]),
                )
                save_bytes(stego_bytes, self._resolve_manifest_path(row["stego_path"]))
            else:
                raise ValueError(f"Unknown method: {method}")
        return len(rows)

    def run_detector_stage(
        self,
        stego_manifest_path: Path,
        output_path: Path | None = None,
        *,
        execute: bool = False,
        skip_unimplemented: bool = False,
    ) -> Path:
        """Run detector scoring over the full proposal-aligned evaluation table.

        Output schema:
        detector, group_id, source, method, payload_level, encryption, label, score
        """
        stego_rows = read_rows_csv(stego_manifest_path)

        pred_rows: list[dict[str, object]] = []
        for row in stego_rows:
            group_id = int(row["group_id"])
            for detector in self._detectors_for_method(row["method"]):
                pos_score = ""
                if execute:
                    try:
                        pos_score = self._score_detector_row(
                            detector=detector,
                            label=1,
                            row=row,
                        )
                    except NotImplementedError:
                        if skip_unimplemented:
                            continue
                        raise

                pred_rows.append(
                    {
                        "detector": detector,
                        "group_id": group_id,
                        "source": row["source"],
                        "method": row["method"],
                        "payload_level": row["payload_level"],
                        "encryption": row["encryption"],
                        "label": 1,
                        "score": pos_score,
                    }
                )

                neg_score = ""
                if execute:
                    try:
                        neg_score = self._score_detector_row(
                            detector=detector,
                            label=0,
                            row=row,
                        )
                    except NotImplementedError:
                        if skip_unimplemented:
                            pred_rows.pop()
                            continue
                        raise

                pred_rows.append(
                    {
                        "detector": detector,
                        "group_id": group_id,
                        "source": row["source"],
                        "method": row["method"],
                        "payload_level": row["payload_level"],
                        "encryption": row["encryption"],
                        "label": 0,
                        "score": neg_score,
                    }
                )

        out = output_path or (self.paths.predictions_dir / "predictions.csv")
        write_rows_csv(
            out,
            pred_rows,
            fieldnames=[
                "detector",
                "group_id",
                "source",
                "method",
                "payload_level",
                "encryption",
                "label",
                "score",
            ],
        )
        return out

    def compute_metrics_from_predictions(
        self,
        predictions_path: Path,
        metrics_dir: Path | None = None,
        quality_metrics_input: Path | None = None,
    ) -> dict[str, Path]:
        """Compute detector/condition/source metrics from prediction rows."""
        rows = read_rows_csv(predictions_path)
        scored_rows = [r for r in rows if try_parse_score(r.get("score", "")) is not None]

        out_dir = metrics_dir or self.paths.metrics_dir
        out_dir = self._resolve_manifest_path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        detector_metrics = aggregate_by_groups(scored_rows, ["detector"])
        condition_metrics = aggregate_by_groups(
            scored_rows, ["detector", "method", "payload_level", "encryption"]
        )
        source_metrics = aggregate_by_groups(scored_rows, ["detector", "source"])

        detector_path = out_dir / "detector_metrics.csv"
        condition_path = out_dir / "condition_metrics.csv"
        source_path = out_dir / "source_metrics.csv"
        quality_path = out_dir / "quality_metrics.csv"

        write_rows_csv(
            detector_path,
            detector_metrics,
            fieldnames=[
                "detector",
                "n_samples",
                "n_pos",
                "n_neg",
                "roc_auc",
                "eer",
                "accuracy_at_youden_j",
                "fpr_at_fixed_fnr",
            ],
        )
        write_rows_csv(
            condition_path,
            condition_metrics,
            fieldnames=[
                "detector",
                "method",
                "payload_level",
                "encryption",
                "n_samples",
                "n_pos",
                "n_neg",
                "roc_auc",
                "eer",
                "accuracy_at_youden_j",
                "fpr_at_fixed_fnr",
            ],
        )
        write_rows_csv(
            source_path,
            source_metrics,
            fieldnames=[
                "detector",
                "source",
                "n_samples",
                "n_pos",
                "n_neg",
                "roc_auc",
                "eer",
                "accuracy_at_youden_j",
                "fpr_at_fixed_fnr",
            ],
        )
        quality_fieldnames = [
            "group_id",
            "source",
            "method",
            "payload_level",
            "encryption",
            "psnr",
            "ssim",
            "fsim",
        ]
        if quality_metrics_input is not None:
            in_path = self._resolve_manifest_path(quality_metrics_input)
            write_rows_csv(quality_path, read_rows_csv(in_path), fieldnames=quality_fieldnames)
        else:
            write_rows_csv(quality_path, [], fieldnames=quality_fieldnames)

        return {
            "detector_metrics": detector_path,
            "condition_metrics": condition_path,
            "source_metrics": source_path,
            "quality_metrics": quality_path,
        }

    def generate_metrics_figures(
        self,
        metrics_dir: Path | None = None,
        figures_dir: Path | None = None,
    ) -> dict[str, Path]:
        """Generate core metric figures from metrics CSV outputs."""
        resolved_metrics_dir = self._resolve_manifest_path(metrics_dir or self.paths.metrics_dir)
        resolved_figures_dir = self._resolve_manifest_path(
            figures_dir or self.paths.figures_dir
        )
        return generate_metrics_figures(
            metrics_dir=resolved_metrics_dir,
            figures_dir=resolved_figures_dir,
        )

    def run_full_pipeline(
        self,
        *,
        covers_manifest_path: Path,
        execute_embeddings: bool = False,
        execute_detectors: bool = False,
        skip_unimplemented: bool = False,
        quality_metrics_input: Path | None = None,
        generate_figures: bool = False,
    ) -> dict[str, Path | int]:
        """Run all non-deferred mainline pipeline stages in sequence."""
        self.init_layout()

        resolved_covers = self._resolve_manifest_path(covers_manifest_path)
        payload_manifest = self.build_payload_manifest(
            covers_manifest_path=resolved_covers,
            write_payload_files=execute_embeddings,
        )
        stego_manifest = self.build_stego_manifest(
            covers_manifest_path=resolved_covers,
            payload_manifest_path=payload_manifest,
        )
        embedding_rows = self.run_embedding_stage(
            stego_manifest_path=stego_manifest,
            execute=execute_embeddings,
        )
        predictions = self.run_detector_stage(
            stego_manifest_path=stego_manifest,
            execute=execute_detectors,
            skip_unimplemented=skip_unimplemented,
        )
        metrics_outputs = self.compute_metrics_from_predictions(
            predictions_path=predictions,
            quality_metrics_input=quality_metrics_input,
        )

        out: dict[str, Path | int] = {
            "payload_manifest": payload_manifest,
            "stego_manifest": stego_manifest,
            "predictions": predictions,
            "embedding_rows_processed": embedding_rows,
        }
        out.update(metrics_outputs)

        if generate_figures:
            out.update(self.generate_metrics_figures())

        return out

    def _generate_payload_bytes(self, payload_bits: int, rng: random.Random) -> bytes:
        """Generate deterministic pseudo-random payload bytes for one condition row."""
        n_bytes = payload_bits // 8
        return bytes(rng.getrandbits(8) for _ in range(n_bytes))

    def _embed_params_json(self, method: str, payload_level: str) -> str:
        """Return serialized embedding parameters stored in the stego manifest."""
        fill_rate = self.config.payload_fill_rates[payload_level]
        if method == "lsb":
            params = {
                "method": "lsb",
                "fill_rate": fill_rate,
                "bit_depth": self.config.primary_lsb_bit_depth,
                "spatial_bpp": fill_rate * self.config.primary_lsb_bit_depth,
                "scan_order": "row_major",
                "reference": "fridrich2001lsb",
            }
        elif method == "dct":
            params = {
                "method": "dct_lsb_jpeg",
                "fill_rate": fill_rate,
                "jpeg_quality": self.config.jpeg_quality,
                "coefficient_rule": "nonzero_ac_only",
                "skip_dc": True,
                "scan_order": "row_major_blocks",
                "reference": "westfeld1999chi;fridrich2003calib",
            }
        else:
            raise ValueError(f"Unknown method: {method}")
        return json.dumps(params, sort_keys=True)

    def _score_detector_row(
        self,
        *,
        detector: str,
        label: int,
        row: dict[str, str],
    ) -> float:
        """Score one detector on either stego (label=1) or cover (label=0)."""
        image_path_key = "stego_path" if label == 1 else "cover_path"
        path = self._resolve_manifest_path(row[image_path_key])

        if detector == "rs":
            return rs_analysis_score(load_image(path))
        if detector == "chi_square_spatial":
            return chi_square_spatial_score(load_image(path))
        if detector == "sample_pairs":
            return sample_pairs_score(load_image(path))
        if detector == "chi_square_dct":
            return chi_square_dct_score(load_bytes(path))
        if detector == "calibration_chi_square":
            return calibration_chi_square_score(
                load_bytes(path),
                jpeg_quality=self.config.jpeg_quality,
            )
        raise ValueError(f"Unknown detector: {detector}")
