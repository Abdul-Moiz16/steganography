from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image

from src.common.contracts import SOURCES
from src.data.manifests import write_rows_csv


COVER_FIELDNAMES = [
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


STEGO_FIELDNAMES = [
    "group_id",
    "source",
    "method",
    "payload_level",
    "encryption",
    "cover_path",
    "payload_path",
    "stego_path",
    "embed_params",
    "seed",
]


def write_cover_manifest(path: Path, group_ids: Iterable[int]) -> Path:
    rows: list[dict[str, str]] = []
    for group_id in group_ids:
        for source in SOURCES:
            rows.append(
                {
                    "group_id": str(group_id),
                    "source": source,
                    "dataset": "fixture",
                    "orig_id": f"orig-{group_id}-{source}",
                    "caption_id": f"cap-{group_id}",
                    "caption_text": f"caption {group_id}",
                    "spatial_path": (
                        f"data/covers/spatial/{source}/g{group_id:04d}__src-{source}.png"
                    ),
                    "frequency_path": (
                        f"data/covers/frequency/{source}/g{group_id:04d}__src-{source}.jpg"
                    ),
                    "qc_pass": "true",
                    "qc_score": "0.99",
                    "seed": "42",
                }
            )
    write_rows_csv(path, rows, fieldnames=COVER_FIELDNAMES)
    return path


def create_image(
    path: Path,
    size: tuple[int, int] = (24, 16),
    color: tuple[int, int, int] = (120, 40, 200),
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color=color).save(path)
    return path
