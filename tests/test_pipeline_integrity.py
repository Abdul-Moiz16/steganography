from __future__ import annotations

from collections import Counter
from pathlib import Path

from src.data.manifests import read_rows_csv
from src.pipeline.config import PipelineConfig
from src.pipeline.runner import PipelineRunner
from tests.helpers import write_cover_manifest


def test_blueprint_cardinality_and_pairing_contract(project_root: Path) -> None:
    cfg = PipelineConfig(project_root=project_root, n_groups=500)
    runner = PipelineRunner(cfg)

    covers_manifest = write_cover_manifest(
        project_root / "data" / "manifests" / "covers_master.csv",
        group_ids=range(1, 501),
    )
    covers_rows = read_rows_csv(covers_manifest)
    assert len(covers_rows) == 1500

    payload_manifest = runner.build_payload_manifest(covers_manifest_path=covers_manifest)
    payload_rows = read_rows_csv(payload_manifest)
    assert len(payload_rows) == 500 * 3 * 2

    stego_manifest = runner.build_stego_manifest(
        covers_manifest_path=covers_manifest,
        payload_manifest_path=payload_manifest,
    )
    stego_rows = read_rows_csv(stego_manifest)
    assert len(stego_rows) == 18000

    covers_lookup = {(r["group_id"], r["source"]) for r in covers_rows}
    stego_cover_keys = {(r["group_id"], r["source"]) for r in stego_rows}
    assert stego_cover_keys == covers_lookup

    per_cover = Counter((r["group_id"], r["source"]) for r in stego_rows)
    assert set(per_cover.values()) == {12}


def test_detector_applicability_contract(project_root: Path) -> None:
    cfg = PipelineConfig(project_root=project_root, n_groups=500)
    runner = PipelineRunner(cfg)

    covers_manifest = write_cover_manifest(
        project_root / "data" / "manifests" / "covers_master.csv",
        group_ids=range(1, 501),
    )
    payload_manifest = runner.build_payload_manifest(covers_manifest_path=covers_manifest)
    stego_manifest = runner.build_stego_manifest(covers_manifest, payload_manifest)

    stego_rows = read_rows_csv(stego_manifest)
    lsb_rows = [r for r in stego_rows if r["method"] == "lsb"]
    dct_rows = [r for r in stego_rows if r["method"] == "dct"]

    assert len(lsb_rows) == len(dct_rows) == 9000
    assert runner._detectors_for_method("lsb") == ["rs", "chi_square_spatial", "sample_pairs"]
    assert runner._detectors_for_method("dct") == ["chi_square_dct", "calibration_chi_square"]
