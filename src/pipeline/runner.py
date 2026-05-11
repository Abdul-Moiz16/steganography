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
import json
import random
import secrets
from datetime import datetime
from pathlib import Path

from src.common.contracts import ENCRYPTION_STATES, payload_filename, stego_filename
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
from src.embedding.dct import dct_payload_capacity_bytes, embed_dct_lsb_jpeg
from src.embedding.encryption import encrypt_payload_aes_256_cbc
from src.embedding.lsb import embed_lsb
from src.evaluation.metrics import (
    aggregate_by_groups,
    try_parse_score,
)
from src.evaluation.plots import generate_metrics_figures
from src.metrics.psnr import psnr as _compute_psnr
from src.metrics.ssim import ssim as _compute_ssim


def _compute_fsim_safe(cover: "Image.Image", stego: "Image.Image") -> "float | None":
    """Compute FSIM only if optional deps (piq, torch) are present.

    FSIM is part of the proposal quality-control trio (PSNR/SSIM/FSIM). The
    runtime cost and the torch+piq dependency are heavier than PSNR/SSIM, so
    we import lazily and return ``None`` whenever the deps or computation
    fail. The quality_metrics column is still emitted, just left blank for
    that row, which the report figures handle gracefully.
    """
    try:
        from src.metrics.fsim import fsim as _fsim_impl
    except Exception:
        return None
    try:
        return float(_fsim_impl(cover, stego))
    except Exception:
        return None
from src.pipeline.config import AES_CBC_BLOCK_BYTES, PAYLOAD_MODE_HARDCODED, PipelineConfig


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
            branch_detectors = ("rs", "chi_square_spatial", "sample_pairs")
        elif method == "dct":
            branch_detectors = ("chi_square_dct", "calibration_chi_square")
        else:
            raise ValueError(f"Unknown method: {method}")
        active = set(self.config.active_detectors)
        return [d for d in branch_detectors if d in active]

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
        payload_root: Path | None = None,
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

        # AES-CBC (PKCS7) adds up to one full 16-byte padding block to the
        # ciphertext.  To keep the encrypted payload exactly at capacity we
        # generate 16 bytes less plaintext; PKCS7 then pads back to the
        # original size so the ciphertext == capacity bytes exactly.
        rng = random.Random(self.config.payload_seed)
        records: list[PayloadRecord] = []
        for group_id in groups:
            for payload_level in self.config.active_payload_levels:
                payload_stream_bits = self.config.spatial_payload_bits(payload_level)
                fill_rate = self.config.payload_fill_rates[payload_level]
                for encryption in self.config.active_encryption:
                    # Plain payload fills capacity exactly; encrypted payload
                    # is generated 16 bytes shorter so its ciphertext (after
                    # PKCS7 padding) matches capacity.
                    plaintext_bits = (
                        payload_stream_bits - AES_CBC_BLOCK_BYTES * 8
                        if encryption == "encrypted"
                        else payload_stream_bits
                    )
                    payload_bytes = self._generate_payload_bytes(plaintext_bits, rng)

                    payload_path = self.paths.payload_path(group_id, payload_level, encryption)
                    iv = _stable_iv(group_id, payload_level)

                    if payload_root is not None:
                        payload_path = (
                            payload_root / encryption / payload_level
                            / payload_filename(group_id, payload_level, encryption)
                        )

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
        stego_root: Path | None = None,
    ) -> Path:
        """Enumerate all main stego jobs from covers x methods x payloads x encryption.

        When *stego_root* is supplied stego image paths are placed under that
        directory (e.g. ``runs/prototype_001/stego/``) rather than the shared
        ``data/stego/`` tree.  This keeps every run fully self-contained.
        """
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
            for method in self.config.active_methods:
                cover_path = (
                    cover["spatial_path"] if method == "lsb" else cover["frequency_path"]
                )
                for payload_level in self.config.active_payload_levels:
                    for encryption in self.config.active_encryption:
                        payload_row = payload_index[(group_id, payload_level, encryption)]
                        payload_path = self._to_project_relative(payload_row["payload_path"])

                        if stego_root is not None:
                            # Per-run isolated stego storage
                            stego_path: Path = (
                                stego_root
                                / method
                                / payload_level
                                / encryption
                                / source
                                / stego_filename(
                                    group_id=group_id,
                                    source=source,  # type: ignore[arg-type]
                                    method=method,  # type: ignore[arg-type]
                                    payload=payload_level,  # type: ignore[arg-type]
                                    encryption=encryption,  # type: ignore[arg-type]
                                )
                            )
                        else:
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
        quality_metrics_path: Path | None = None,
    ) -> int:
        """Create stego artifacts from manifest rows.

        With ``execute=False`` this is a dry-run counter only.
        When *quality_metrics_path* is provided and *execute* is True, PSNR and
        SSIM are computed for each LSB pair and written to that path.
        """
        from tqdm import tqdm

        rows = read_rows_csv(stego_manifest_path)
        if not execute:
            return len(rows)

        quality_rows: list[dict] = []
        _QUALITY_FIELDS = ["group_id", "source", "method", "payload_level", "encryption", "psnr", "ssim", "fsim"]

        for row in tqdm(rows, desc="Embedding", unit="img"):
            payload_bytes = self._resolve_manifest_path(row["payload_path"]).read_bytes()
            params = json.loads(row["embed_params"])
            method = row["method"]
            stego_path = self._resolve_manifest_path(row["stego_path"])
            stego_path.parent.mkdir(parents=True, exist_ok=True)
            if method == "lsb":
                cover_image = load_image(self._resolve_manifest_path(row["cover_path"]))
                stego = embed_lsb(
                    cover_image=cover_image,
                    payload_bytes=payload_bytes,
                    fill_rate=float(params["fill_rate"]),
                    bit_depth=int(params["bit_depth"]),
                )
                save_png(stego, stego_path)
                if quality_metrics_path is not None:
                    psnr_val, ssim_val, fsim_val = self._compute_quality_pair(
                        cover_image, stego
                    )
                    quality_rows.append({
                        "group_id": row["group_id"],
                        "source": row["source"],
                        "method": method,
                        "payload_level": row["payload_level"],
                        "encryption": row["encryption"],
                        "psnr": "" if psnr_val is None else psnr_val,
                        "ssim": "" if ssim_val is None else ssim_val,
                        "fsim": "" if fsim_val is None else fsim_val,
                    })
            elif method == "dct":
                cover_jpeg_bytes = load_bytes(self._resolve_manifest_path(row["cover_path"]))
                payload_bytes = self._payload_bytes_for_dct_row(
                    cover_jpeg_bytes,
                    payload_bytes,
                    fill_rate=float(params["fill_rate"]),
                )
                stego_bytes = embed_dct_lsb_jpeg(
                    cover_jpeg_bytes=cover_jpeg_bytes,
                    payload_bytes=payload_bytes,
                    fill_rate=float(params["fill_rate"]),
                    jpeg_quality=int(params["jpeg_quality"]),
                )
                save_bytes(stego_bytes, stego_path)
                if quality_metrics_path is not None:
                    # Decode both JPEG byte streams to grayscale images for the
                    # standard PSNR / SSIM / FSIM trio. The proposal asks for
                    # the same quality trio across both branches so Exp 4 can
                    # compare embedding fidelity, not just AUC.
                    try:
                        from io import BytesIO
                        from PIL import Image as _PIL_Image
                        cover_img = _PIL_Image.open(BytesIO(cover_jpeg_bytes)).convert("L")
                        stego_img = _PIL_Image.open(BytesIO(stego_bytes)).convert("L")
                        psnr_val, ssim_val, fsim_val = self._compute_quality_pair(
                            cover_img, stego_img
                        )
                    except Exception:
                        psnr_val = ssim_val = fsim_val = None
                    quality_rows.append({
                        "group_id": row["group_id"],
                        "source": row["source"],
                        "method": method,
                        "payload_level": row["payload_level"],
                        "encryption": row["encryption"],
                        "psnr": "" if psnr_val is None else psnr_val,
                        "ssim": "" if ssim_val is None else ssim_val,
                        "fsim": "" if fsim_val is None else fsim_val,
                    })
            else:
                raise ValueError(f"Unknown method: {method}")

        if quality_metrics_path is not None and quality_rows:
            quality_metrics_path.parent.mkdir(parents=True, exist_ok=True)
            write_rows_csv(quality_metrics_path, quality_rows, fieldnames=_QUALITY_FIELDS)

        return len(rows)

    def _compute_quality_pair(
        self, cover: "Image.Image", stego: "Image.Image"
    ) -> "tuple[float | None, float | None, float | None]":
        """Return (psnr, ssim, fsim) for a cover/stego pair; None per metric on error.

        FSIM uses optional deps (piq + torch) and is skipped silently when
        unavailable so a missing piq install does not break the run.
        """
        try:
            p = _compute_psnr(cover, stego)
        except Exception:
            p = None
        try:
            s = _compute_ssim(cover, stego)
        except Exception:
            s = None
        f = _compute_fsim_safe(cover, stego)
        return p, s, f

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
        from tqdm import tqdm

        stego_rows = read_rows_csv(stego_manifest_path)

        pred_rows: list[dict[str, object]] = []
        for row in tqdm(stego_rows, desc="Detecting", unit="img"):
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
        run_dir: Path | None = None,
        profile_name: str | None = None,
        cover_seed: int | None = None,
    ) -> dict[str, Path | int]:
        """Run all non-deferred mainline pipeline stages in sequence.

        When *run_dir* is supplied every output (manifests, predictions,
        metrics, figures, config snapshot) is written inside that directory
        so multiple runs never overwrite each other.  When omitted the
        legacy ``data/manifests`` + ``results/`` layout is used unchanged.
        """
        # ── Determine output roots ────────────────────────────────────────
        if run_dir is not None:
            run_dir.mkdir(parents=True, exist_ok=True)
            manifests_out   = run_dir / "manifests"
            predictions_out = run_dir / "predictions"
            metrics_out     = run_dir / "metrics"
            figures_out     = run_dir / "figures"
            stego_root      = run_dir / "stego"
            payload_root    = run_dir / "payloads"
            for d in (manifests_out, predictions_out, metrics_out, figures_out):
                d.mkdir(parents=True, exist_ok=True)
            if cover_seed is None:
                import random as _r
                cover_seed = _r.randrange(2**31)
            self._save_run_config(run_dir, profile_name, cover_seed=cover_seed)
        else:
            self.init_layout()
            manifests_out   = self.paths.manifests_dir
            predictions_out = self.paths.predictions_dir
            metrics_out     = self.paths.metrics_dir
            figures_out     = self.paths.figures_dir
            stego_root      = None
            payload_root    = None

        resolved_covers = self._resolve_manifest_path(covers_manifest_path)

        # Covers are already placed in run_dir by run.py before pipeline starts
        active_covers = resolved_covers
        self._validate_hardcoded_payload_against_dct_covers(active_covers)

        payload_manifest = self.build_payload_manifest(
            covers_manifest_path=active_covers,
            output_manifest_path=manifests_out / "payload_manifest.csv",
            write_payload_files=execute_embeddings,
            payload_root=payload_root,
        )
        stego_manifest = self.build_stego_manifest(
            covers_manifest_path=active_covers,
            payload_manifest_path=payload_manifest,
            output_manifest_path=manifests_out / "stego_manifest.csv",
            stego_root=stego_root,
        )
        raw_quality_path = manifests_out / "quality_metrics_raw.csv"
        embedding_rows = self.run_embedding_stage(
            stego_manifest_path=stego_manifest,
            execute=execute_embeddings,
            quality_metrics_path=raw_quality_path if execute_embeddings else None,
        )
        predictions = self.run_detector_stage(
            stego_manifest_path=stego_manifest,
            output_path=predictions_out / "predictions.csv",
            execute=execute_detectors,
            skip_unimplemented=skip_unimplemented,
        )
        effective_quality_input = (
            raw_quality_path
            if execute_embeddings and raw_quality_path.exists()
            else quality_metrics_input
        )
        metrics_outputs = self.compute_metrics_from_predictions(
            predictions_path=predictions,
            metrics_dir=metrics_out,
            quality_metrics_input=effective_quality_input,
        )

        out: dict[str, Path | int] = {
            "run_dir": run_dir or self.config.project_root,
            "payload_manifest": payload_manifest,
            "stego_manifest": stego_manifest,
            "predictions": predictions,
            "embedding_rows_processed": embedding_rows,
        }
        out.update(metrics_outputs)

        if generate_figures:
            out.update(self.generate_metrics_figures(
                metrics_dir=metrics_out,
                figures_dir=figures_out,
            ))

        # ── Per-run statistical analyses ──────────────────────────────────
        # These modules read predictions.csv and write supplementary tables
        # under metrics/. They are best-effort: a failure logs the error and
        # leaves the rest of the run intact.
        analysis_dir = metrics_out.parent
        for label, runner_fn in self._analysis_jobs():
            try:
                out_path = runner_fn(analysis_dir)
                out[f"analysis_{label}"] = out_path
            except Exception as exc:  # noqa: BLE001 — analysis must not break the run
                print(f"  [warn] analysis '{label}' failed: {exc}")

        # ── Refresh RQ verdict cards now that verdicts.json is on disk ─────
        # The figure was rendered earlier as a placeholder because verdicts
        # are produced after the contrast tables.  Re-render so the writer
        # sees the populated cards in figures/.
        if generate_figures:
            try:
                import json as _json
                from src.evaluation.plots import render_rq_summary_cards
                verdicts_path = metrics_out / "rq_verdicts.json"
                payload = _json.loads(verdicts_path.read_text()) if verdicts_path.exists() else None
                if payload is not None:
                    out["rq_summary_cards"] = render_rq_summary_cards(figures_out, payload)
            except Exception as exc:  # noqa: BLE001
                print(f"  [warn] rq summary card refresh failed: {exc}")

        return out

    def _analysis_jobs(self) -> list[tuple[str, "callable[[Path], Path]"]]:
        """Return (label, callable) pairs to run after metrics + figures.

        Each callable accepts a run directory and returns the path of the CSV
        (or first-of-many path) it wrote. Encryption-invariance is skipped
        when only one encryption arm is active because the paired comparison
        would be empty. The RQ verdict + power-analysis modules read the
        contrast CSVs written by generate_metrics_figures and are scheduled
        last so they always see the latest tables.
        """
        from src.analysis.t_tests import run_t_tests
        from src.analysis.wilcoxon_tests import run_wilcoxon_tests
        from src.analysis.rq_verdicts import run_rq_verdicts as _run_rq_verdicts
        from src.analysis.power_analysis import run_power_analysis as _run_power

        def _run_verdicts_first_path(run_dir: Path) -> Path:
            json_path, _ = _run_rq_verdicts(run_dir)
            return json_path

        def _run_power_first_path(run_dir: Path) -> Path:
            detail_path, _ = _run_power(run_dir)
            return detail_path

        jobs: list[tuple[str, "callable[[Path], Path]"]] = [
            ("wilcoxon", run_wilcoxon_tests),
            ("t_tests", run_t_tests),
        ]
        if {"plain", "encrypted"}.issubset(self.config.active_encryption):
            from src.analysis.encryption_invariance import run_encryption_invariance
            jobs.append(("encryption_invariance", run_encryption_invariance))
        jobs.append(("rq_verdicts", _run_verdicts_first_path))
        jobs.append(("power_analysis", _run_power_first_path))
        return jobs

    # ── Run-directory helpers ────────────────────────────────────────────────

    def _next_run_dir(self, profile_name: str) -> Path:
        """Return a timestamp-based run directory for *profile_name*.

        Directories are named ``runs/{profile}_{YYYYMMDD}_{HHMMSS}`` so every
        run is unique and lexicographically sortable by date.
        """
        runs_root = self.config.project_root / "runs"
        runs_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return runs_root / f"{profile_name}_{stamp}"

    def _save_run_config(self, run_dir: Path, profile_name: str | None, cover_seed: int | None = None) -> None:
        """Snapshot config + timestamp into *run_dir*/config.json."""
        run_dir.mkdir(parents=True, exist_ok=True)
        snapshot = {
            "profile": profile_name,
            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "n_groups": self.config.n_groups,
            "active_methods": list(self.config.active_methods),
            "active_payload_levels": list(self.config.active_payload_levels),
            "image_size": list(self.config.image_size),
            "split_seed": self.config.split_seed,
            "payload_seed": self.config.payload_seed,
            "payload_mode": self.config.payload_mode,
            "hardcoded_payload_bytes": (
                len(self.config.validate_hardcoded_payload_text(self.config.hardcoded_payload_text))
                if self.config.payload_mode == PAYLOAD_MODE_HARDCODED
                else None
            ),
            "hardcoded_payload_sha256": (
                hashlib.sha256(
                    self.config.validate_hardcoded_payload_text(self.config.hardcoded_payload_text)
                ).hexdigest()
                if self.config.payload_mode == PAYLOAD_MODE_HARDCODED
                else None
            ),
            "embed_seed": self.config.embed_seed,
            "jpeg_quality": self.config.jpeg_quality,
            "primary_lsb_bit_depth": self.config.primary_lsb_bit_depth,
            "payload_fill_rates": self.config.payload_fill_rates,
            "aes_key_id": self.config.aes_key_id,
            "cover_seed": cover_seed,
        }
        write_json(run_dir / "config.json", snapshot)

    def _generate_payload_bytes(self, payload_bits: int, rng: random.Random) -> bytes:
        """Generate deterministic payload bytes for one condition row."""
        n_bytes = payload_bits // 8
        if self.config.payload_mode == PAYLOAD_MODE_HARDCODED:
            return self._generate_hardcoded_payload_bytes(n_bytes)
        return bytes(rng.getrandbits(8) for _ in range(n_bytes))

    def _generate_hardcoded_payload_bytes(self, n_bytes: int) -> bytes:
        payload = self.config.validate_hardcoded_payload_text(
            self.config.hardcoded_payload_text
        )
        if len(payload) > n_bytes:
            raise ValueError(
                f"Hardcoded payload is too large for this condition: {len(payload)} bytes > {n_bytes} bytes."
            )
        repeats = (n_bytes + len(payload) - 1) // len(payload)
        return (payload * repeats)[:n_bytes]

    def _payload_bytes_for_dct_row(
        self,
        cover_jpeg_bytes: bytes,
        payload_bytes: bytes,
        *,
        fill_rate: float,
    ) -> bytes:
        capacity_bytes = dct_payload_capacity_bytes(cover_jpeg_bytes, fill_rate)
        if self.config.payload_mode == PAYLOAD_MODE_HARDCODED:
            return self._generate_hardcoded_payload_bytes(capacity_bytes)
        return payload_bytes[:capacity_bytes]

    def _validate_hardcoded_payload_against_dct_covers(self, covers_manifest_path: Path) -> None:
        if self.config.payload_mode != PAYLOAD_MODE_HARDCODED or "dct" not in self.config.active_methods:
            return
        payload = self.config.validate_hardcoded_payload_text(self.config.hardcoded_payload_text)
        if not self.config.active_payload_levels:
            return
        min_fill_rate = min(
            self.config.payload_fill_rates[level] for level in self.config.active_payload_levels
        )
        min_capacity: int | None = None
        min_path = ""
        for row in read_rows_csv(covers_manifest_path):
            cover_path = self._resolve_manifest_path(row["frequency_path"])
            capacity = dct_payload_capacity_bytes(load_bytes(cover_path), min_fill_rate)
            if min_capacity is None or capacity < min_capacity:
                min_capacity = capacity
                min_path = row["frequency_path"]
        if min_capacity is not None and len(payload) > min_capacity:
            raise ValueError(
                "Hardcoded payload is too large for the DCT covers in this run: "
                f"{len(payload)} bytes > {min_capacity} bytes on {min_path}."
            )

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
        """Score one detector on either stego (label=1) or cover (label=0).

        All detector functions follow the convention: higher score = stronger
        evidence of steganographic embedding.  Scores are returned as-is;
        AUC is rank-based and does not require a [0, 1] range.
        """
        image_path_key = "stego_path" if label == 1 else "cover_path"
        path = self._resolve_manifest_path(row[image_path_key])

        if detector == "rs":
            return float(rs_analysis_score(load_image(path)))
        if detector == "chi_square_spatial":
            return float(chi_square_spatial_score(load_image(path)))
        if detector == "sample_pairs":
            return float(sample_pairs_score(load_image(path)))
        if detector == "chi_square_dct":
            return float(chi_square_dct_score(load_bytes(path)))
        if detector == "calibration_chi_square":
            return float(calibration_chi_square_score(
                load_bytes(path),
                jpeg_quality=self.config.jpeg_quality,
            ))
        raise ValueError(f"Unknown detector: {detector}")
