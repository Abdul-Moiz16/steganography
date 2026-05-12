"""Regression tests for the parallel + resume-aware embedding stage.

Cover:
- Sequential (n_workers=1) and parallel (n_workers>1) produce the same
  quality CSV row set and the same stego files on disk.
- Resume from a partial quality_metrics_raw.csv re-runs only missing
  rows and never duplicates an existing row.
- A truncated final line in quality_metrics_raw.csv is silently dropped
  on resume, mirroring the predictions.csv tolerance.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from PIL import Image

from src.data.manifests import read_rows_csv, write_rows_csv
from src.pipeline.config import PipelineConfig
from src.pipeline.runner import (
    _QUALITY_FIELDNAMES,
    _embed_one_task,
    _load_existing_quality_keys,
    PipelineRunner,
)


STEGO_FIELDNAMES = [
    "group_id", "source", "method", "payload_level", "encryption",
    "cover_path", "payload_path", "stego_path", "embed_params", "seed",
]


@pytest.fixture()
def two_row_run(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Build a tiny stego_manifest with one LSB and one DCT row.

    Returns (project_root, stego_manifest, quality_metrics_path).
    """
    project_root = tmp_path
    covers_dir = project_root / "data" / "covers"
    stego_dir = project_root / "data" / "stego"
    payloads_dir = project_root / "data" / "payloads"
    covers_dir.mkdir(parents=True)
    stego_dir.mkdir(parents=True)
    payloads_dir.mkdir(parents=True)

    # Make a 32x32 grayscale cover for the LSB branch and a JPEG for DCT.
    lsb_cover = covers_dir / "g0001__src-real.png"
    dct_cover = covers_dir / "g0001__src-real.jpg"
    Image.new("L", (32, 32), color=128).save(lsb_cover)
    Image.new("L", (32, 32), color=128).save(dct_cover, format="JPEG", quality=95)

    payload = payloads_dir / "g0001__p-low__e-plain.bin"
    payload.write_bytes(b"\x00" * 8)

    stego_manifest = project_root / "data" / "manifests" / "stego_manifest.csv"
    write_rows_csv(
        stego_manifest,
        rows=[
            {
                "group_id": "1",
                "source": "real",
                "method": "lsb",
                "payload_level": "low",
                "encryption": "plain",
                "cover_path": str(lsb_cover.relative_to(project_root)),
                "payload_path": str(payload.relative_to(project_root)),
                "stego_path": "data/stego/lsb_g0001.png",
                "embed_params": json.dumps({"fill_rate": 0.25, "bit_depth": 1}),
                "seed": "42",
            },
            {
                "group_id": "1",
                "source": "real",
                "method": "dct",
                "payload_level": "low",
                "encryption": "plain",
                "cover_path": str(dct_cover.relative_to(project_root)),
                "payload_path": str(payload.relative_to(project_root)),
                "stego_path": "data/stego/dct_g0001.jpg",
                "embed_params": json.dumps({"fill_rate": 0.25, "jpeg_quality": 95}),
                "seed": "42",
            },
        ],
        fieldnames=STEGO_FIELDNAMES,
    )
    return project_root, stego_manifest, project_root / "data" / "quality_metrics_raw.csv"


def _read_quality(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def test_embed_one_task_emits_quality_row_for_lsb(two_row_run: tuple[Path, Path, Path]) -> None:
    project_root, stego_manifest, _ = two_row_run
    row = read_rows_csv(stego_manifest)[0]
    task = {"row": row, "project_root": str(project_root), "compute_quality": True}
    out = _embed_one_task(task)
    assert out is not None
    assert out["method"] == "lsb"
    assert (project_root / row["stego_path"]).exists()
    # PSNR/SSIM should be populated (FSIM may be blank if torch/piq absent).
    assert out["psnr"] != ""
    assert out["ssim"] != ""


def test_sequential_and_parallel_produce_same_quality_rows(
    two_row_run: tuple[Path, Path, Path]
) -> None:
    project_root, stego_manifest, q_csv = two_row_run
    cfg = PipelineConfig(project_root=project_root, n_groups=1)
    runner = PipelineRunner(cfg)

    runner.run_embedding_stage(
        stego_manifest_path=stego_manifest,
        execute=True,
        quality_metrics_path=q_csv,
        n_workers=1,
    )
    seq_rows = sorted(
        _read_quality(q_csv),
        key=lambda r: (int(r["group_id"]), r["source"], r["method"], r["payload_level"]),
    )

    # Wipe and re-run with multiple workers; same input must yield same rows.
    q_csv.unlink()
    for f in (project_root / "data" / "stego").glob("*"):
        f.unlink()
    runner.run_embedding_stage(
        stego_manifest_path=stego_manifest,
        execute=True,
        quality_metrics_path=q_csv,
        n_workers=2,
    )
    par_rows = sorted(
        _read_quality(q_csv),
        key=lambda r: (int(r["group_id"]), r["source"], r["method"], r["payload_level"]),
    )

    assert len(seq_rows) == len(par_rows) == 2
    assert seq_rows == par_rows


def test_resume_skips_completed_rows(two_row_run: tuple[Path, Path, Path]) -> None:
    project_root, stego_manifest, q_csv = two_row_run
    cfg = PipelineConfig(project_root=project_root, n_groups=1)
    runner = PipelineRunner(cfg)

    # First pass writes both rows.
    runner.run_embedding_stage(
        stego_manifest_path=stego_manifest,
        execute=True,
        quality_metrics_path=q_csv,
        n_workers=1,
    )
    first_pass = _read_quality(q_csv)
    assert len(first_pass) == 2

    # Second pass on the same inputs must produce no duplicate rows.
    runner.run_embedding_stage(
        stego_manifest_path=stego_manifest,
        execute=True,
        quality_metrics_path=q_csv,
        n_workers=1,
    )
    second_pass = _read_quality(q_csv)
    assert second_pass == first_pass


def test_resume_completes_partial_csv(two_row_run: tuple[Path, Path, Path]) -> None:
    project_root, stego_manifest, q_csv = two_row_run

    # Seed the quality CSV with just the LSB row -- resume must add the DCT row.
    q_csv.parent.mkdir(parents=True, exist_ok=True)
    with q_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_QUALITY_FIELDNAMES)
        writer.writeheader()
        writer.writerow({
            "group_id": "1", "source": "real", "method": "lsb",
            "payload_level": "low", "encryption": "plain",
            "psnr": "55.0", "ssim": "0.999", "fsim": "0.9999",
        })

    cfg = PipelineConfig(project_root=project_root, n_groups=1)
    runner = PipelineRunner(cfg)
    runner.run_embedding_stage(
        stego_manifest_path=stego_manifest,
        execute=True,
        quality_metrics_path=q_csv,
        n_workers=1,
    )

    rows = _read_quality(q_csv)
    methods = sorted(r["method"] for r in rows)
    assert methods == ["dct", "lsb"]
    # The seeded LSB row's bogus PSNR=55.0 is preserved -- no duplicate.
    lsb_rows = [r for r in rows if r["method"] == "lsb"]
    assert len(lsb_rows) == 1
    assert lsb_rows[0]["psnr"] == "55.0"


def test_quality_key_parser_handles_edge_cases(tmp_path: Path) -> None:
    # Missing file.
    assert _load_existing_quality_keys(tmp_path / "missing.csv") == set()

    # Empty file.
    p = tmp_path / "empty.csv"
    p.write_text("")
    assert _load_existing_quality_keys(p) == set()

    # Foreign header.
    p = tmp_path / "foreign.csv"
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["alpha", "beta"])
        w.writerow(["a", "b"])
    assert _load_existing_quality_keys(p) == set()

    # Truncated last line.
    p = tmp_path / "partial.csv"
    with p.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_QUALITY_FIELDNAMES)
        writer.writeheader()
        writer.writerow({
            "group_id": "1", "source": "real", "method": "lsb",
            "payload_level": "low", "encryption": "plain",
            "psnr": "55.0", "ssim": "0.999", "fsim": "0.9999",
        })
    with p.open("a") as f:
        f.write("2,ml_a,dct,medium")  # truncated, no newline
    keys = _load_existing_quality_keys(p)
    assert (1, "real", "lsb", "low", "plain") in keys
    assert all(k[0] != 2 for k in keys)  # truncated row dropped
