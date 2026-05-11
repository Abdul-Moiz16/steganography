from __future__ import annotations

"""Generate ML cover sets from generation prompts.

This module builds canonical `ml_a` and `ml_b` cover images from
`data/manifests/generation_prompts.csv` and writes per-source + combined
manifest files under `data/manifests/`.

Default backends:
- ml_a: SDXL (`stabilityai/stable-diffusion-xl-base-1.0`) — UNet-based latent diffusion
- ml_b: FLUX.1-schnell (`black-forest-labs/FLUX.1-schnell`) — DiT-based diffusion transformer

For lightweight local testing, `engine="stub"` generates deterministic
synthetic images without model dependencies.
"""

import argparse
import gc
import hashlib
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# Force UTF-8 console output on Windows (avoids UnicodeEncodeError on
# restrictive codepages such as cp1253).
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from PIL import Image

from src.common.contracts import PipelinePaths, cover_filename
from src.data.images import save_jpeg, save_png, standardize_image
from src.data.manifests import read_rows_csv, write_json, write_rows_csv


SDXL_DEFAULT_MODEL_ID = "stabilityai/stable-diffusion-xl-base-1.0"
FLUX_DEFAULT_MODEL_ID = "black-forest-labs/FLUX.1-schnell"



FIELDNAMES = [
    "group_id",
    "source",
    "dataset",
    "orig_id",
    "caption_id",
    "caption_text",
    "spatial_path",
    "frequency_path",
    "qc_pass",
    "qc_score",
    "seed",
]


@dataclass(frozen=True)
class GeneratorSpec:
    source: str
    dataset_name: str
    model_id: str


class TextToImageGenerator(Protocol):
    def generate(
        self,
        *,
        prompt: str,
        seed: int,
        width: int,
        height: int,
        num_inference_steps: int,
        guidance_scale: float,
        negative_prompt: str,
    ) -> Image.Image: ...


class StubTextToImageGenerator:
    """Deterministic synthetic image generator used for tests/dry development."""

    def __init__(self, tag: str) -> None:
        self.tag = tag

    def generate(
        self,
        *,
        prompt: str,
        seed: int,
        width: int,
        height: int,
        num_inference_steps: int,
        guidance_scale: float,
        negative_prompt: str,
    ) -> Image.Image:
        _ = (num_inference_steps, guidance_scale, negative_prompt)
        base = hashlib.sha256(f"{self.tag}:{prompt}:{seed}".encode("utf-8")).digest()
        rng = random.Random(int.from_bytes(base[:8], byteorder="big", signed=False))

        image = Image.new("RGB", (width, height))
        pixels = image.load()
        for y in range(height):
            for x in range(width):
                # Structured but non-trivial deterministic pattern.
                noise = rng.getrandbits(8)
                r = (x * 3 + y * 5 + noise) % 256
                g = (x * 7 + y * 11 + noise // 2) % 256
                b = (x * 13 + y * 17 + noise // 3) % 256
                pixels[x, y] = (r, g, b)
        return image


class InferenceAPITextToImageGenerator:
    """HuggingFace Inference API backend — no local model download needed."""

    def __init__(self, model_id: str) -> None:
        try:
            from huggingface_hub import InferenceClient
        except ImportError as exc:
            raise RuntimeError(
                "Inference API backend requires `huggingface_hub` to be installed."
            ) from exc
        self.model_id = model_id
        self.client = InferenceClient(model=model_id)

    def generate(
        self,
        *,
        prompt: str,
        seed: int,
        width: int,
        height: int,
        num_inference_steps: int,
        guidance_scale: float,
        negative_prompt: str,
    ) -> Image.Image:
        """Generate one image via the HF Inference API, retrying on transient failures.

        Retries on any 5xx, connection error, timeout, or explicit rate-limit
        signal. Backoff is exponential (5, 10, 20, 40 s, capped at 60 s) with
        a small random jitter to avoid thundering-herd retries when the
        backend recovers. Non-retryable auth/permission errors (4xx, except
        429) fail fast.
        """
        import random
        import time

        max_retries = 8  # gives ~3-4 min of survivable transient outage
        # Substrings indicating a retryable transient condition.
        retryable = ("500", "502", "503", "504", "429", "rate", "timeout",
                     "timed out", "connection", "reset by peer", "temporarily")
        # Substrings indicating a permanent error — don't waste retries on these.
        non_retryable = ("401", "403", "404", "unauthor", "forbidden",
                         "not found", "invalid api key")

        for attempt in range(max_retries):
            try:
                image = self.client.text_to_image(
                    prompt,
                    negative_prompt=negative_prompt or None,
                    width=width,
                    height=height,
                    num_inference_steps=num_inference_steps,
                    guidance_scale=guidance_scale,
                    seed=seed,
                )
                if not isinstance(image, Image.Image):
                    raise TypeError("Inference API did not return a PIL image.")
                return image
            except Exception as exc:
                msg = str(exc).lower()
                is_permanent = any(s in msg for s in non_retryable)
                is_transient = any(s in msg for s in retryable)
                if is_permanent or not is_transient or attempt >= max_retries - 1:
                    raise
                wait = min(60, 5 * (2 ** attempt)) + random.uniform(0, 2)
                print(
                    f"  [inference_api] transient error (attempt {attempt + 1}/{max_retries}): "
                    f"{type(exc).__name__}: {str(exc)[:140]} "
                    f"— sleeping {wait:.1f}s"
                )
                time.sleep(wait)
        # Should never reach here — the loop either returns or re-raises.
        raise RuntimeError("Unreachable: exhausted retries without raising")


class DiffusersTextToImageGenerator:
    """Diffusers-backed text-to-image generator with lazy imports."""

    def __init__(self, model_id: str, flavor: str) -> None:
        try:
            import torch
            from diffusers import FluxPipeline, StableDiffusionXLPipeline
        except Exception as exc:  # pragma: no cover - depends on local env
            raise RuntimeError(
                "Diffusers backend requires `torch` and `diffusers` to be installed."
            ) from exc

        self._torch = torch
        if torch.cuda.is_available():
            self.device = "cuda"
        elif torch.backends.mps.is_available():
            self.device = "mps"
        else:
            self.device = "cpu"
        dtype = torch.float32 if self.device == "cpu" else torch.float16

        if flavor == "sdxl":
            kwargs: dict[str, object] = {"torch_dtype": dtype}
            if self.device == "cuda":
                kwargs["variant"] = "fp16"
            self.pipe = StableDiffusionXLPipeline.from_pretrained(model_id, **kwargs)
        elif flavor == "flux":
            self.pipe = FluxPipeline.from_pretrained(model_id, torch_dtype=dtype)
        else:
            raise ValueError(f"Unknown diffusers flavor: {flavor}")

        self.pipe = self.pipe.to(self.device)
        if hasattr(self.pipe, "set_progress_bar_config"):
            self.pipe.set_progress_bar_config(disable=True)

    def generate(
        self,
        *,
        prompt: str,
        seed: int,
        width: int,
        height: int,
        num_inference_steps: int,
        guidance_scale: float,
        negative_prompt: str,
    ) -> Image.Image:
        # MPS does not support torch.Generator(device="mps"); use CPU generator.
        gen_device = "cpu" if self.device == "mps" else self.device
        generator = self._torch.Generator(device=gen_device).manual_seed(seed)
        output = self.pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            width=width,
            height=height,
            generator=generator,
        )
        image = output.images[0]
        if not isinstance(image, Image.Image):
            raise TypeError("Diffusers pipeline did not return a PIL image.")
        return image


def _resolve_path(project_root: Path, path: Path | str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else (project_root / p)


def _to_project_relative(project_root: Path, path: Path | str) -> str:
    p = _resolve_path(project_root, path)
    try:
        return str(p.relative_to(project_root))
    except ValueError:
        return str(p)


def _seed_for(group_id: int, source: str, seed_base: int) -> int:
    source_offset = {"ml_a": 100_000, "ml_b": 200_000}[source]
    return seed_base + source_offset + group_id


def _validate_prompt_schema(rows: list[dict[str, str]]) -> None:
    required = {
        "group_id",
        "dataset",
        "orig_id",
        "caption_id",
        "caption_text",
        "real_spatial_path",
        "real_frequency_path",
    }
    if not rows:
        raise ValueError("generation_prompts.csv has no rows.")

    missing = required - set(rows[0].keys())
    if missing:
        raise ValueError(f"generation_prompts.csv missing columns: {sorted(missing)}")


def _build_cover_row(
    *,
    group_id: int,
    source: str,
    dataset_name: str,
    orig_id: str,
    caption_id: str,
    caption_text: str,
    spatial_path_rel: str,
    frequency_path_rel: str,
    seed: int,
) -> dict[str, object]:
    return {
        "group_id": group_id,
        "source": source,
        "dataset": dataset_name,
        "orig_id": orig_id,
        "caption_id": caption_id,
        "caption_text": caption_text,
        "spatial_path": spatial_path_rel,
        "frequency_path": frequency_path_rel,
        "qc_pass": "true",
        "qc_score": 1.0,
        "seed": seed,
    }


def _init_generator(
    *,
    engine: str,
    source: str,
    ml_a_model_id: str,
    ml_b_model_id: str,
) -> TextToImageGenerator:
    if engine == "stub":
        return StubTextToImageGenerator(source)
    if engine == "diffusers":
        if source == "ml_a":
            return DiffusersTextToImageGenerator(ml_a_model_id, flavor="sdxl")
        if source == "ml_b":
            return DiffusersTextToImageGenerator(ml_b_model_id, flavor="flux")
        raise ValueError(f"Unsupported source: {source}")
    if engine == "inference_api":
        model_id = ml_a_model_id if source == "ml_a" else ml_b_model_id
        return InferenceAPITextToImageGenerator(model_id)
    raise ValueError(f"Unsupported engine: {engine}")


def _release_generator(generator: TextToImageGenerator) -> None:
    """Best-effort cleanup to reduce peak memory between model families."""
    pipe = getattr(generator, "pipe", None)
    if pipe is not None:
        del pipe
    del generator
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def generate_ml_covers_from_prompts(
    *,
    project_root: Path,
    prompts_csv: Path,
    engine: str = "diffusers",
    ml_a_model_id: str = SDXL_DEFAULT_MODEL_ID,
    ml_b_model_id: str = FLUX_DEFAULT_MODEL_ID,
    negative_prompt: str = "",
    num_inference_steps: int = 30,
    guidance_scale: float = 7.0,
    width: int = 1024,
    height: int = 1024,
    image_size: tuple[int, int] = (512, 512),
    seed_base: int = 42,
    max_groups: int | None = None,
    run_dir: Path | None = None,
) -> dict[str, Path]:
    """Generate `ml_a` and `ml_b` cover sets from a prompt manifest."""
    project_root = project_root.resolve()
    paths = PipelinePaths.from_project_root(project_root)
    paths.ensure_layout()

    if run_dir is not None:
        for src in ("ml_a", "ml_b"):
            (run_dir / "covers" / src).mkdir(parents=True, exist_ok=True)
        (run_dir / "manifests").mkdir(parents=True, exist_ok=True)

    prompts_path = _resolve_path(project_root, prompts_csv)
    prompt_rows = read_rows_csv(prompts_path)
    _validate_prompt_schema(prompt_rows)

    # Deterministic ordering by group id for stable run outputs.
    prompt_rows.sort(key=lambda r: int(r["group_id"]))
    if max_groups is not None:
        prompt_rows = prompt_rows[:max_groups]

    specs = {
        "ml_a": GeneratorSpec("ml_a", "SDXL", ml_a_model_id),
        "ml_b": GeneratorSpec("ml_b", "FLUX.1-schnell", ml_b_model_id),
    }
    rows_ml_a: list[dict[str, object]] = []
    rows_ml_b: list[dict[str, object]] = []
    rows_ml_all: list[dict[str, object]] = []

    from tqdm import tqdm

    import time as _time

    def _resolved_paths(group_id: int, source: str) -> tuple[Path, Path]:
        if run_dir is not None:
            return (
                run_dir / "covers" / source / cover_filename(group_id, source, "spatial"),
                run_dir / "covers" / source / cover_filename(group_id, source, "frequency"),
            )
        return (
            paths.cover_path(group_id, source, "spatial"),  # type: ignore[arg-type]
            paths.cover_path(group_id, source, "frequency"),  # type: ignore[arg-type]
        )

    def _row_for(group_id: int, source: str, prompt_row: dict, seed: int) -> dict:
        spatial_path, frequency_path = _resolved_paths(group_id, source)
        return _build_cover_row(
            group_id=group_id,
            source=source,
            dataset_name=specs[source].dataset_name,
            orig_id=prompt_row["orig_id"],
            caption_id=prompt_row["caption_id"],
            caption_text=prompt_row["caption_text"],
            spatial_path_rel=_to_project_relative(project_root, spatial_path),
            frequency_path_rel=_to_project_relative(project_root, frequency_path),
            seed=seed,
        )

    def _attempt_one(prompt_row: dict, source: str, generator) -> tuple[dict | None, str | None]:
        """Return (manifest_row, error_message). Skip-if-exists supports resume."""
        group_id = int(prompt_row["group_id"])
        seed = _seed_for(group_id, source, seed_base)
        spatial_path, frequency_path = _resolved_paths(group_id, source)
        if spatial_path.exists() and frequency_path.exists():
            return _row_for(group_id, source, prompt_row, seed), None
        try:
            generated = generator.generate(
                prompt=prompt_row["caption_text"],
                seed=seed,
                width=width,
                height=height,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
                negative_prompt=negative_prompt,
            )
            standardized = standardize_image(generated, size=image_size)
            save_png(standardized, spatial_path)
            save_jpeg(standardized, frequency_path)
            return _row_for(group_id, source, prompt_row, seed), None
        except Exception as exc:  # noqa: BLE001 — we record and continue
            return None, f"{type(exc).__name__}: {str(exc)[:200]}"

    all_failures: list[dict[str, object]] = []

    for source in ("ml_a", "ml_b"):
        generator = _init_generator(
            engine=engine,
            source=source,
            ml_a_model_id=ml_a_model_id,
            ml_b_model_id=ml_b_model_id,
        )
        produced_rows: list[dict] = []
        failed_rows: list[dict] = []

        # Pass 1: every prompt.
        for row in tqdm(prompt_rows, desc=f"Generating {source}", unit="img"):
            manifest_row, err = _attempt_one(row, source, generator)
            if manifest_row is not None:
                produced_rows.append(manifest_row)
            else:
                failed_rows.append({"prompt_row": row, "error": err})
                print(f"  [warn] {source} group {row['group_id']} failed after retries: {err}")

        # Pass 2: re-attempt anything that failed (transient backend recovery).
        if failed_rows:
            print(
                f"  [retry] re-attempting {len(failed_rows)} failed {source} generations "
                f"after a 30s breather ..."
            )
            _time.sleep(30)
            still_failed: list[dict] = []
            for entry in failed_rows:
                manifest_row, err = _attempt_one(entry["prompt_row"], source, generator)
                if manifest_row is not None:
                    produced_rows.append(manifest_row)
                else:
                    still_failed.append({"prompt_row": entry["prompt_row"], "error": err})
            failed_rows = still_failed

        # Record any permanent failures so the user can target a follow-up rescue.
        for entry in failed_rows:
            all_failures.append({
                "source": source,
                "group_id": int(entry["prompt_row"]["group_id"]),
                "caption_id": entry["prompt_row"].get("caption_id", ""),
                "error": entry["error"],
            })

        # Sort by group_id for stable manifest ordering.
        produced_rows.sort(key=lambda r: int(r["group_id"]))
        rows_ml_all.extend(produced_rows)
        (rows_ml_a if source == "ml_a" else rows_ml_b).extend(produced_rows)

        _release_generator(generator)

    rows_ml_all.sort(key=lambda r: (int(r["group_id"]), r["source"]))
    rows_ml_a.sort(key=lambda r: int(r["group_id"]))
    rows_ml_b.sort(key=lambda r: int(r["group_id"]))

    if run_dir is not None:
        ml_a_manifest = run_dir / "manifests" / "covers_ml_a.csv"
        ml_b_manifest = run_dir / "manifests" / "covers_ml_b.csv"
        ml_manifest = run_dir / "manifests" / "covers_ml.csv"
        summary_path = run_dir / "manifests" / "ml_generation_summary.json"
    else:
        ml_a_manifest = paths.manifests_dir / "covers_master_ml_a.csv"
        ml_b_manifest = paths.manifests_dir / "covers_master_ml_b.csv"
        ml_manifest = paths.manifests_dir / "covers_master_ml.csv"
        summary_path = paths.manifests_dir / "ml_generation_summary.json"

    write_rows_csv(ml_a_manifest, rows_ml_a, fieldnames=FIELDNAMES)
    write_rows_csv(ml_b_manifest, rows_ml_b, fieldnames=FIELDNAMES)
    write_rows_csv(ml_manifest, rows_ml_all, fieldnames=FIELDNAMES)

    # Persist any permanent failures so the user can target a re-run.
    if all_failures:
        if run_dir is not None:
            failures_path = run_dir / "manifests" / "ml_generation_failures.csv"
        else:
            failures_path = paths.manifests_dir / "ml_generation_failures.csv"
        write_rows_csv(
            failures_path,
            all_failures,
            fieldnames=["source", "group_id", "caption_id", "error"],
        )
        print(
            f"\n  [warn] {len(all_failures)} permanent ML-cover failures recorded at "
            f"{failures_path}. Re-run the same command to retry only the missing "
            f"groups (already-generated files are skipped)."
        )

    summary = {
        "engine": engine,
        "seed_base": seed_base,
        "ml_a_model_id": ml_a_model_id,
        "ml_b_model_id": ml_b_model_id,
        "total_prompts_used": len(prompt_rows),
        "rows_ml_a": len(rows_ml_a),
        "rows_ml_b": len(rows_ml_b),
        "rows_ml_total": len(rows_ml_all),
        "permanent_failures": len(all_failures),
        "covers_master_ml_a_path": _to_project_relative(project_root, ml_a_manifest),
        "covers_master_ml_b_path": _to_project_relative(project_root, ml_b_manifest),
        "covers_master_ml_path": _to_project_relative(project_root, ml_manifest),
    }
    write_json(summary_path, summary)

    return {
        "covers_master_ml_a": ml_a_manifest,
        "covers_master_ml_b": ml_b_manifest,
        "covers_master_ml": ml_manifest,
        "summary": summary_path,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate ml_a (SDXL) and ml_b (FLUX.1-schnell) covers from generation prompts."
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--prompts-csv",
        type=Path,
        default=Path("data/manifests/generation_prompts.csv"),
    )
    parser.add_argument("--engine", choices=["diffusers", "inference_api", "stub"], default="diffusers")
    parser.add_argument("--ml-a-model-id", type=str, default=SDXL_DEFAULT_MODEL_ID)
    parser.add_argument("--ml-b-model-id", type=str, default=FLUX_DEFAULT_MODEL_ID)
    parser.add_argument("--negative-prompt", type=str, default="")
    parser.add_argument("--num-inference-steps", type=int, default=30)
    parser.add_argument("--guidance-scale", type=float, default=7.0)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--seed-base", type=int, default=42)
    parser.add_argument("--max-groups", type=int, default=None)
    return parser


def main() -> None:
    args = _parser().parse_args()
    outputs = generate_ml_covers_from_prompts(
        project_root=args.project_root,
        prompts_csv=args.prompts_csv,
        engine=args.engine,
        ml_a_model_id=args.ml_a_model_id,
        ml_b_model_id=args.ml_b_model_id,
        negative_prompt=args.negative_prompt,
        num_inference_steps=args.num_inference_steps,
        guidance_scale=args.guidance_scale,
        width=args.width,
        height=args.height,
        seed_base=args.seed_base,
        max_groups=args.max_groups,
    )
    print(f"ML-A manifest: {outputs['covers_master_ml_a']}")
    print(f"ML-B manifest: {outputs['covers_master_ml_b']}")
    print(f"Combined ML manifest: {outputs['covers_master_ml']}")
    print(f"Summary: {outputs['summary']}")


if __name__ == "__main__":
    main()
