from __future__ import annotations

from pathlib import Path

import pytest

from src.data.manifests import read_rows_csv, write_rows_csv
from src.pipeline.config import PipelineConfig
from src.pipeline.runner import PipelineRunner, _stable_iv
from tests.helpers import write_cover_manifest


def test_standardize_covers_from_index_writes_outputs(project_root: Path, runner: PipelineRunner) -> None:
    raw_root = project_root / "raw"
    index_csv = project_root / "raw_index.csv"

    rows: list[dict[str, str]] = []
    for group_id in [1, 2]:
        for source in ["real", "ml_a", "ml_b"]:
            raw_path = raw_root / f"{group_id}_{source}.jpg"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            from PIL import Image

            Image.new("RGB", (23, 17), color=(50, 100, 150)).save(raw_path)
            rows.append(
                {
                    "group_id": str(group_id),
                    "source": source,
                    "dataset": "fixture",
                    "orig_id": f"orig-{group_id}",
                    "caption_id": f"cap-{group_id}",
                    "caption_text": f"caption {group_id}",
                    "raw_image_path": str(raw_path),
                    "qc_pass": "true",
                    "qc_score": "0.9",
                    "seed": "123",
                }
            )

    write_rows_csv(
        index_csv,
        rows,
        fieldnames=[
            "group_id",
            "source",
            "dataset",
            "orig_id",
            "caption_id",
            "caption_text",
            "raw_image_path",
            "qc_pass",
            "qc_score",
            "seed",
        ],
    )

    out = runner.standardize_covers_from_index(index_csv)
    covers = read_rows_csv(out)

    assert len(covers) == 6
    first_spatial = project_root / covers[0]["spatial_path"]
    first_frequency = project_root / covers[0]["frequency_path"]
    assert first_spatial.exists()
    assert first_frequency.exists()

    from src.data.images import load_image

    standardized = load_image(first_spatial)
    assert standardized.size == (512, 512)
    assert standardized.mode == "L"
    assert not Path(covers[0]["spatial_path"]).is_absolute()
    assert not Path(covers[0]["frequency_path"]).is_absolute()


def test_build_payload_manifest_validates_group_count(project_root: Path, runner: PipelineRunner) -> None:
    covers_manifest = write_cover_manifest(
        project_root / "data" / "manifests" / "covers_master.csv",
        group_ids=[1, 2, 3],
    )

    with pytest.raises(ValueError, match="Expected 500 groups"):
        runner.build_payload_manifest(covers_manifest_path=covers_manifest)


def test_stable_iv_is_deterministic_and_16_bytes() -> None:
    iv_a = _stable_iv(10, "medium")
    iv_b = _stable_iv(10, "medium")
    iv_c = _stable_iv(10, "low")

    assert iv_a == iv_b
    assert iv_a != iv_c
    assert isinstance(iv_a, bytes)
    assert len(iv_a) == 16


def test_embed_params_json_contract(project_root: Path) -> None:
    runner = PipelineRunner(PipelineConfig(project_root=project_root, n_groups=4))

    lsb_low = __import__("json").loads(runner._embed_params_json("lsb", "low"))
    assert lsb_low["method"] == "lsb"
    assert lsb_low["bit_depth"] == 1
    assert lsb_low["fill_rate"] == 0.25
    assert lsb_low["scan_order"] == "row_major"

    dct_high = __import__("json").loads(runner._embed_params_json("dct", "high"))
    assert dct_high["method"] == "dct_lsb_jpeg"
    assert dct_high["fill_rate"] == 0.75
    assert dct_high["jpeg_quality"] == 95

    with pytest.raises(ValueError, match="Unknown method"):
        runner._embed_params_json("foo", "low")
