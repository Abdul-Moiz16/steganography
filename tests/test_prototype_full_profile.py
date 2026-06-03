"""Tests for the prototype_full profile and the full-pipeline integration.

The prototype_full profile is meant to give every report figure (Exp 1-5,
ROC panels, quality summary) real data at 1/5 the cost of full_design. The
checks in this file pin down three things:

1. Profile metadata - groups, methods, payload levels, condition count.
2. Cardinality contracts - 100 groups produces the right number of cover,
   payload, and stego rows once both methods + all payloads + both encryption
   states are active.
3. Detector applicability - all 5 statistical detectors are reachable from
   the runner once both branches are active (LSB -> 3 spatial detectors,
   DCT -> 2 frequency detectors).

A separate small test confirms the runner now records an "fsim" value (or a
graceful blank when piq is not installed) instead of always emitting "" for
the column.
"""

from __future__ import annotations

import csv
from pathlib import Path

from src.data.manifests import read_rows_csv, write_rows_csv
from src.pipeline.config import PipelineConfig
from src.pipeline.profile import PROFILES
from src.pipeline.runner import PipelineRunner
from tests.helpers import write_cover_manifest


def test_prototype_full_profile_metadata() -> None:
    profile = PROFILES["prototype_full"]
    assert profile.n_groups == 100
    assert profile.pool_groups == 100
    assert profile.active_methods == ("lsb", "dct")
    assert profile.active_payload_levels == ("low", "medium", "high")
    # 3 sources x 2 methods x 3 payloads x 2 encryptions = 36 conditions
    assert profile.n_conditions == 36


def test_prototype_full_config_factory_uses_profile_constants(tmp_path: Path) -> None:
    cfg = PipelineConfig.from_profile(tmp_path, "prototype_full")
    assert cfg.n_groups == 100
    assert cfg.active_methods == ("lsb", "dct")
    assert cfg.active_payload_levels == ("low", "medium", "high")
    assert cfg.image_size == (512, 512)
    assert cfg.jpeg_quality == 95


def test_prototype_full_cardinality_and_detector_coverage(tmp_path: Path) -> None:
    """100 groups -> 300 covers, 600 payloads, 3600 stego rows; both branches active."""
    cfg = PipelineConfig.from_profile(tmp_path, "prototype_full")
    runner = PipelineRunner(cfg)

    covers_manifest = write_cover_manifest(
        tmp_path / "data" / "manifests" / "covers_master.csv",
        group_ids=range(1, 101),
    )
    covers_rows = read_rows_csv(covers_manifest)
    assert len(covers_rows) == 300  # 100 groups x 3 sources

    payload_manifest = runner.build_payload_manifest(covers_manifest_path=covers_manifest)
    payload_rows = read_rows_csv(payload_manifest)
    # 100 groups x 3 payload levels x 2 encryption states
    assert len(payload_rows) == 100 * 3 * 2

    stego_manifest = runner.build_stego_manifest(
        covers_manifest_path=covers_manifest,
        payload_manifest_path=payload_manifest,
    )
    stego_rows = read_rows_csv(stego_manifest)
    # 300 covers x 2 methods x 3 payload levels x 2 encryptions
    assert len(stego_rows) == 300 * 2 * 3 * 2 == 3600

    lsb_rows = [r for r in stego_rows if r["method"] == "lsb"]
    dct_rows = [r for r in stego_rows if r["method"] == "dct"]
    assert len(lsb_rows) == 1800
    assert len(dct_rows) == 1800

    # All 6 detectors must be reachable (3 spatial + 3 frequency).
    assert runner._detectors_for_method("lsb") == [
        "rs",
        "chi_square_spatial",
        "sample_pairs",
    ]
    assert runner._detectors_for_method("dct") == [
        "chi_square_dct",
        "calibration_chi_square",
        "chi_square_dct_tiled",
    ]


def test_prototype_full_includes_all_encryption_states(tmp_path: Path) -> None:
    """Both 'plain' and 'encrypted' rows must exist on every (method, payload) cell."""
    cfg = PipelineConfig.from_profile(tmp_path, "prototype_full")
    runner = PipelineRunner(cfg)

    covers_manifest = write_cover_manifest(
        tmp_path / "data" / "manifests" / "covers_master.csv",
        group_ids=range(1, 101),
    )
    payload_manifest = runner.build_payload_manifest(covers_manifest_path=covers_manifest)
    stego_manifest = runner.build_stego_manifest(covers_manifest, payload_manifest)

    cells = {
        (r["method"], r["payload_level"], r["encryption"])
        for r in read_rows_csv(stego_manifest)
    }
    expected = {
        (m, p, e)
        for m in ("lsb", "dct")
        for p in ("low", "medium", "high")
        for e in ("plain", "encrypted")
    }
    assert cells == expected


# ---------------------------------------------------------------------------
# FSIM integration in the runner's quality metrics output.
# ---------------------------------------------------------------------------


def _fields(path: Path) -> list[str]:
    with path.open(newline="") as f:
        return next(csv.reader(f))


def test_compute_quality_pair_returns_three_metrics(tmp_path: Path) -> None:
    """The runner helper must now return (psnr, ssim, fsim) - never just two."""
    from PIL import Image

    runner = PipelineRunner(PipelineConfig(project_root=tmp_path, n_groups=4))
    cover = Image.new("L", (32, 32), color=120)
    stego = Image.new("L", (32, 32), color=121)

    result = runner._compute_quality_pair(cover, stego)
    assert isinstance(result, tuple)
    assert len(result) == 3
    psnr_val, ssim_val, fsim_val = result
    # PSNR and SSIM always present (skimage is required); FSIM is optional and
    # may be None when piq is not installed.
    assert psnr_val is not None
    assert ssim_val is not None
    assert fsim_val is None or isinstance(fsim_val, float)


def test_runner_quality_metrics_csv_includes_fsim_column(tmp_path: Path) -> None:
    """Even when piq is missing the schema must still emit the fsim column."""
    from PIL import Image

    runner = PipelineRunner(PipelineConfig(project_root=tmp_path, n_groups=1))

    cover = tmp_path / "covers" / "g0001__src-real.png"
    stego_dest = tmp_path / "stego" / "g0001__src-real.png"
    cover.parent.mkdir(parents=True, exist_ok=True)
    Image.new("L", (32, 32), color=120).save(cover)

    payload_path = tmp_path / "payloads" / "g0001__p-low__e-plain.bin"
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_bytes(b"\x00" * 8)

    stego_manifest = tmp_path / "manifests" / "stego_manifest.csv"
    write_rows_csv(
        stego_manifest,
        rows=[
            {
                "group_id": "1",
                "source": "real",
                "method": "lsb",
                "payload_level": "low",
                "encryption": "plain",
                "cover_path": str(cover.relative_to(tmp_path)),
                "payload_path": str(payload_path.relative_to(tmp_path)),
                "stego_path": str(stego_dest.relative_to(tmp_path)),
                "embed_params": '{"fill_rate": 0.25, "bit_depth": 1}',
                "seed": "42",
            }
        ],
        fieldnames=[
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
        ],
    )

    quality_path = tmp_path / "manifests" / "quality_metrics_raw.csv"
    runner.run_embedding_stage(
        stego_manifest_path=stego_manifest,
        execute=True,
        quality_metrics_path=quality_path,
    )

    assert quality_path.exists()
    assert "fsim" in _fields(quality_path)
    rows = read_rows_csv(quality_path)
    assert len(rows) == 1
    # PSNR + SSIM always present; FSIM may be blank when piq is absent.
    assert rows[0]["psnr"] != ""
    assert rows[0]["ssim"] != ""
