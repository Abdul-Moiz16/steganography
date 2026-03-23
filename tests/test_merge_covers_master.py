from __future__ import annotations

from pathlib import Path

import pytest

from src.data.manifests import read_rows_csv, write_rows_csv


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


def _rows_for_source(source: str, dataset: str, groups: list[int]) -> list[dict[str, str]]:
    return [
        {
            "group_id": str(g),
            "source": source,
            "dataset": dataset,
            "orig_id": f"orig-{g}",
            "caption_id": f"cap-{g}",
            "caption_text": f"caption {g}",
            "spatial_path": f"data/covers/spatial/{source}/g{g:04d}__src-{source}.png",
            "frequency_path": f"data/covers/frequency/{source}/g{g:04d}__src-{source}.jpg",
            "qc_pass": "true",
            "qc_score": "1.0",
            "seed": "42",
        }
        for g in groups
    ]


def test_merge_covers_master_success(tmp_path: Path) -> None:
    from src.data.merge_covers_master import merge_covers_master

    real = tmp_path / "data/manifests/covers_master_real.csv"
    ml_a = tmp_path / "data/manifests/covers_master_ml_a.csv"
    ml_b = tmp_path / "data/manifests/covers_master_ml_b.csv"

    write_rows_csv(real, _rows_for_source("real", "COCO", [1, 2, 3]), FIELDNAMES)
    write_rows_csv(ml_a, _rows_for_source("ml_a", "SDXL", [1, 2, 3]), FIELDNAMES)
    write_rows_csv(ml_b, _rows_for_source("ml_b", "PixArt-alpha", [1, 2, 3]), FIELDNAMES)

    out = merge_covers_master(
        project_root=tmp_path,
        real_manifest=real,
        ml_a_manifest=ml_a,
        ml_b_manifest=ml_b,
        expected_groups=3,
    )

    rows = read_rows_csv(out)
    assert len(rows) == 9

    ordered = [(int(r["group_id"]), r["source"]) for r in rows]
    assert ordered == [
        (1, "real"),
        (1, "ml_a"),
        (1, "ml_b"),
        (2, "real"),
        (2, "ml_a"),
        (2, "ml_b"),
        (3, "real"),
        (3, "ml_a"),
        (3, "ml_b"),
    ]


def test_merge_covers_master_raises_on_group_mismatch(tmp_path: Path) -> None:
    from src.data.merge_covers_master import merge_covers_master

    real = tmp_path / "data/manifests/covers_master_real.csv"
    ml_a = tmp_path / "data/manifests/covers_master_ml_a.csv"
    ml_b = tmp_path / "data/manifests/covers_master_ml_b.csv"

    write_rows_csv(real, _rows_for_source("real", "COCO", [1, 2, 3]), FIELDNAMES)
    write_rows_csv(ml_a, _rows_for_source("ml_a", "SDXL", [1, 2, 3]), FIELDNAMES)
    write_rows_csv(ml_b, _rows_for_source("ml_b", "PixArt-alpha", [1, 2]), FIELDNAMES)

    with pytest.raises(ValueError, match="group IDs"):
        merge_covers_master(
            project_root=tmp_path,
            real_manifest=real,
            ml_a_manifest=ml_a,
            ml_b_manifest=ml_b,
            expected_groups=3,
        )


def test_merge_covers_master_raises_on_source_mismatch(tmp_path: Path) -> None:
    from src.data.merge_covers_master import merge_covers_master

    real = tmp_path / "data/manifests/covers_master_real.csv"
    ml_a = tmp_path / "data/manifests/covers_master_ml_a.csv"
    ml_b = tmp_path / "data/manifests/covers_master_ml_b.csv"

    bad_ml_a = _rows_for_source("ml_a", "SDXL", [1, 2, 3])
    bad_ml_a[0]["source"] = "real"

    write_rows_csv(real, _rows_for_source("real", "COCO", [1, 2, 3]), FIELDNAMES)
    write_rows_csv(ml_a, bad_ml_a, FIELDNAMES)
    write_rows_csv(ml_b, _rows_for_source("ml_b", "PixArt-alpha", [1, 2, 3]), FIELDNAMES)

    with pytest.raises(ValueError, match="source column"):
        merge_covers_master(
            project_root=tmp_path,
            real_manifest=real,
            ml_a_manifest=ml_a,
            ml_b_manifest=ml_b,
            expected_groups=3,
        )
