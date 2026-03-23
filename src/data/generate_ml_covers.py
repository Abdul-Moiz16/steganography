from __future__ import annotations

"""Generate ML cover sets from generation prompts.

This module builds canonical `ml_a` and `ml_b` cover images from
`data/manifests/generation_prompts.csv` and writes per-source + combined
manifest files under `data/manifests/`.

Default backends:
- ml_a: SDXL (`stabilityai/stable-diffusion-xl-base-1.0`)
- ml_b: PixArt-alpha (`PixArt-alpha/PixArt-XL-2-1024-MS`)

For lightweight local testing, `engine="stub"` generates deterministic
synthetic images without model dependencies.
"""

import argparse
import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PIL import Image

from src.common.contracts import PipelinePaths
from src.data.images import save_jpeg, save_png, standardize_image
from src.data.manifests import read_rows_csv, write_json, write_rows_csv


SDXL_DEFAULT_MODEL_ID = "stabilityai/stable-diffusion-xl-base-1.0"
PIXART_DEFAULT_MODEL_ID = "PixArt-alpha/PixArt-XL-2-1024-MS"


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


class DiffusersTextToImageGenerator:
    """Diffusers-backed text-to-image generator with lazy imports."""

    def __init__(self, model_id: str, flavor: str) -> None:
        try:
            import torch
            from diffusers import PixArtAlphaPipeline, StableDiffusionXLPipeline
        except Exception as exc:  # pragma: no cover - depends on local env
            raise RuntimeError(
                "Diffusers backend requires `torch` and `diffusers` to be installed."
            ) from exc

        self._torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if self.device == "cuda" else torch.float32

        if flavor == "sdxl":
            kwargs: dict[str, object] = {"torch_dtype": dtype}
            if self.device == "cuda":
                kwargs["variant"] = "fp16"
            self.pipe = StableDiffusionXLPipeline.from_pretrained(model_id, **kwargs)
        elif flavor == "pixart":
            self.pipe = PixArtAlphaPipeline.from_pretrained(model_id, torch_dtype=dtype)
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
        generator = self._torch.Generator(device=self.device).manual_seed(seed)
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


def _init_generators(
    *,
    engine: str,
    ml_a_model_id: str,
    ml_b_model_id: str,
) -> dict[str, TextToImageGenerator]:
    if engine == "stub":
        return {
            "ml_a": StubTextToImageGenerator("ml_a"),
            "ml_b": StubTextToImageGenerator("ml_b"),
        }
    if engine == "diffusers":
        return {
            "ml_a": DiffusersTextToImageGenerator(ml_a_model_id, flavor="sdxl"),
            "ml_b": DiffusersTextToImageGenerator(ml_b_model_id, flavor="pixart"),
        }
    raise ValueError(f"Unsupported engine: {engine}")


def generate_ml_covers_from_prompts(
    *,
    project_root: Path,
    prompts_csv: Path,
    engine: str = "diffusers",
    ml_a_model_id: str = SDXL_DEFAULT_MODEL_ID,
    ml_b_model_id: str = PIXART_DEFAULT_MODEL_ID,
    negative_prompt: str = "",
    num_inference_steps: int = 30,
    guidance_scale: float = 7.0,
    width: int = 1024,
    height: int = 1024,
    image_size: tuple[int, int] = (512, 512),
    seed_base: int = 42,
    max_groups: int | None = None,
) -> dict[str, Path]:
    """Generate `ml_a` and `ml_b` cover sets from a prompt manifest."""
    project_root = project_root.resolve()
    paths = PipelinePaths.from_project_root(project_root)
    paths.ensure_layout()

    prompts_path = _resolve_path(project_root, prompts_csv)
    prompt_rows = read_rows_csv(prompts_path)
    _validate_prompt_schema(prompt_rows)

    # Deterministic ordering by group id for stable run outputs.
    prompt_rows.sort(key=lambda r: int(r["group_id"]))
    if max_groups is not None:
        prompt_rows = prompt_rows[:max_groups]

    specs = {
        "ml_a": GeneratorSpec("ml_a", "SDXL", ml_a_model_id),
        "ml_b": GeneratorSpec("ml_b", "PixArt-alpha", ml_b_model_id),
    }
    generators = _init_generators(
        engine=engine,
        ml_a_model_id=ml_a_model_id,
        ml_b_model_id=ml_b_model_id,
    )

    rows_ml_a: list[dict[str, object]] = []
    rows_ml_b: list[dict[str, object]] = []
    rows_ml_all: list[dict[str, object]] = []

    for row in prompt_rows:
        group_id = int(row["group_id"])
        prompt = row["caption_text"]

        for source in ("ml_a", "ml_b"):
            spec = specs[source]
            seed = _seed_for(group_id, source, seed_base)
            generated = generators[source].generate(
                prompt=prompt,
                seed=seed,
                width=width,
                height=height,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
                negative_prompt=negative_prompt,
            )

            standardized = standardize_image(generated, size=image_size)
            spatial_path = paths.cover_path(group_id, source, "spatial")  # type: ignore[arg-type]
            frequency_path = paths.cover_path(group_id, source, "frequency")  # type: ignore[arg-type]
            save_png(standardized, spatial_path)
            save_jpeg(standardized, frequency_path)

            manifest_row = _build_cover_row(
                group_id=group_id,
                source=source,
                dataset_name=spec.dataset_name,
                orig_id=row["orig_id"],
                caption_id=row["caption_id"],
                caption_text=row["caption_text"],
                spatial_path_rel=_to_project_relative(project_root, spatial_path),
                frequency_path_rel=_to_project_relative(project_root, frequency_path),
                seed=seed,
            )
            rows_ml_all.append(manifest_row)
            if source == "ml_a":
                rows_ml_a.append(manifest_row)
            else:
                rows_ml_b.append(manifest_row)

    rows_ml_all.sort(key=lambda r: (int(r["group_id"]), r["source"]))
    rows_ml_a.sort(key=lambda r: int(r["group_id"]))
    rows_ml_b.sort(key=lambda r: int(r["group_id"]))

    ml_a_manifest = paths.manifests_dir / "covers_master_ml_a.csv"
    ml_b_manifest = paths.manifests_dir / "covers_master_ml_b.csv"
    ml_manifest = paths.manifests_dir / "covers_master_ml.csv"
    summary_path = paths.manifests_dir / "ml_generation_summary.json"

    write_rows_csv(ml_a_manifest, rows_ml_a, fieldnames=FIELDNAMES)
    write_rows_csv(ml_b_manifest, rows_ml_b, fieldnames=FIELDNAMES)
    write_rows_csv(ml_manifest, rows_ml_all, fieldnames=FIELDNAMES)

    summary = {
        "engine": engine,
        "seed_base": seed_base,
        "ml_a_model_id": ml_a_model_id,
        "ml_b_model_id": ml_b_model_id,
        "total_prompts_used": len(prompt_rows),
        "rows_ml_a": len(rows_ml_a),
        "rows_ml_b": len(rows_ml_b),
        "rows_ml_total": len(rows_ml_all),
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
        description="Generate ml_a (SDXL) and ml_b (PixArt-alpha) covers from generation prompts."
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--prompts-csv",
        type=Path,
        default=Path("data/manifests/generation_prompts.csv"),
    )
    parser.add_argument("--engine", choices=["diffusers", "stub"], default="diffusers")
    parser.add_argument("--ml-a-model-id", type=str, default=SDXL_DEFAULT_MODEL_ID)
    parser.add_argument("--ml-b-model-id", type=str, default=PIXART_DEFAULT_MODEL_ID)
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
