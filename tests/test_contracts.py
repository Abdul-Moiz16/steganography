from __future__ import annotations

from pathlib import Path

from src.common.contracts import (
    SOURCES,
    PipelinePaths,
    cover_branch_for_method,
    cover_filename,
    payload_filename,
    stego_filename,
)


def test_filename_contracts() -> None:
    assert cover_filename(7, "real", "spatial") == "g0007__src-real.png"
    assert cover_filename(7, "real", "frequency") == "g0007__src-real.jpg"
    assert payload_filename(7, "medium", "encrypted") == "g0007__p-medium__e-encrypted.bin"
    assert (
        stego_filename(7, "ml_b", "dct", "high", "plain")
        == "g0007__src-ml_b__m-dct__p-high__e-plain.jpg"
    )


def test_cover_branch_mapping() -> None:
    assert cover_branch_for_method("lsb") == "spatial"
    assert cover_branch_for_method("dct") == "frequency"


def test_pipeline_paths_builders(project_root: Path) -> None:
    paths = PipelinePaths.from_project_root(project_root)
    assert paths.data_root == project_root / "data"
    assert paths.results_root == project_root / "results"

    # Cover path: data/covers/{source}/{filename}  (no spatial/frequency sub-dir)
    assert (
        paths.cover_path(1, "real", "spatial")
        == project_root / "data" / "covers" / "real" / "g0001__src-real.png"
    )
    assert (
        paths.cover_path(1, "real", "frequency")
        == project_root / "data" / "covers" / "real" / "g0001__src-real.jpg"
    )
    assert (
        paths.payload_path(1, "low", "plain")
        == project_root / "data" / "payloads" / "plain" / "low" / "g0001__p-low__e-plain.bin"
    )
    assert (
        paths.stego_path(1, "ml_a", "lsb", "medium", "encrypted")
        == project_root
        / "data"
        / "stego"
        / "lsb"
        / "medium"
        / "encrypted"
        / "ml_a"
        / "g0001__src-ml_a__m-lsb__p-medium__e-encrypted.png"
    )


def test_ensure_layout_creates_expected_directories(project_root: Path) -> None:
    paths = PipelinePaths.from_project_root(project_root)
    paths.ensure_layout()

    # Only manifests and per-source cover dirs are pre-created; stego/payload dirs
    # are created on-demand per run.
    assert paths.manifests_dir.is_dir()
    for source in SOURCES:
        assert paths.covers_dir(source).is_dir()
