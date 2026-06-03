from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from src.data.manifests import read_rows_csv, write_rows_csv
from src.pipeline.config import PAYLOAD_MODE_HARDCODED, PipelineConfig
from src.pipeline.runner import PipelineRunner
from tests.helpers import COVER_FIELDNAMES, STEGO_FIELDNAMES, create_image, write_cover_manifest


DCT_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "dct" / "cover_q95.jpg"


def test_build_payload_manifest_cardinality_and_fields(
    project_root: Path,
    small_runner,
) -> None:
    covers_manifest = project_root / "data" / "manifests" / "covers_master.csv"

    write_cover_manifest(covers_manifest, group_ids=[1, 2, 3, 4])

    out = small_runner.build_payload_manifest(covers_manifest_path=covers_manifest)
    rows = read_rows_csv(out)

    assert len(rows) == 4 * 3 * 2

    by_group = Counter(int(r["group_id"]) for r in rows)
    assert set(by_group.values()) == {6}

    encrypted_rows = [r for r in rows if r["encryption"] == "encrypted"]
    assert all(r["aes_key_id"] == "aes256cbc-v1" for r in encrypted_rows)
    assert all(len(r["aes_iv"]) == 32 for r in rows)
    assert {r["fill_rate"] for r in rows} == {"0.05", "0.15", "0.3"}
    assert {r["bit_depth"] for r in rows} == {"1"}

    sample = rows[0]
    assert sample["payload_path"].endswith(".bin")
    assert not Path(sample["payload_path"]).is_absolute()


def test_build_payload_manifest_with_file_writes_creates_payloads(
    project_root: Path,
    small_runner,
) -> None:
    covers_manifest = write_cover_manifest(
        project_root / "data" / "manifests" / "covers_master.csv", group_ids=[1, 2, 3, 4]
    )

    out = small_runner.build_payload_manifest(
        covers_manifest_path=covers_manifest,
        write_payload_files=True,
    )
    rows = read_rows_csv(out)
    # Verify payload files were actually written
    for r in rows:
        payload_path = project_root / r["payload_path"]
        assert payload_path.exists(), f"Payload file not created: {payload_path}"
        assert payload_path.stat().st_size > 0


def test_build_payload_manifest_hardcoded_payload_repeats_text(project_root: Path) -> None:
    cfg = PipelineConfig(
        project_root=project_root,
        n_groups=1,
        image_size=(32, 32),
        # Override the lower default fill rates so the 32x32 fixture still
        # offers a non-trivial plaintext capacity (otherwise low=0.05 leaves
        # < 16 bytes of stream room after AES overhead).
        payload_fill_rates={"low": 0.25, "medium": 0.5, "high": 0.75},
        active_payload_levels=("low",),
        payload_mode=PAYLOAD_MODE_HARDCODED,
        hardcoded_payload_text="AB",
    )
    runner = PipelineRunner(cfg)
    covers_manifest = write_cover_manifest(
        project_root / "data" / "manifests" / "covers_master.csv", group_ids=[1]
    )

    out = runner.build_payload_manifest(
        covers_manifest_path=covers_manifest,
        write_payload_files=True,
    )
    rows = read_rows_csv(out)
    plain_row = next(r for r in rows if r["encryption"] == "plain")
    payload = (project_root / plain_row["payload_path"]).read_bytes()

    assert payload == (b"AB" * 16)


def test_hardcoded_payload_validation_rejects_oversized_text(project_root: Path) -> None:
    with pytest.raises(ValueError, match="too large"):
        PipelineConfig(
            project_root=project_root,
            image_size=(32, 32),
            active_payload_levels=("low",),
            payload_mode=PAYLOAD_MODE_HARDCODED,
            hardcoded_payload_text="x" * 17,
        )


def test_hardcoded_payload_validation_rejects_control_characters(project_root: Path) -> None:
    with pytest.raises(ValueError, match="control characters"):
        PipelineConfig(
            project_root=project_root,
            payload_mode=PAYLOAD_MODE_HARDCODED,
            hardcoded_payload_text="bad\x00payload",
        )


def test_build_stego_manifest_cardinality_and_condition_completeness(
    project_root: Path,
    small_runner,
) -> None:
    covers_manifest = write_cover_manifest(
        project_root / "data" / "manifests" / "covers_master.csv", group_ids=[1, 2, 3, 4]
    )
    payload_manifest = small_runner.build_payload_manifest(covers_manifest_path=covers_manifest)

    out = small_runner.build_stego_manifest(
        covers_manifest_path=covers_manifest,
        payload_manifest_path=payload_manifest,
    )
    rows = read_rows_csv(out)

    assert len(rows) == 4 * 3 * 12

    per_cover = Counter((r["group_id"], r["source"]) for r in rows)
    assert set(per_cover.values()) == {12}

    assert {r["method"] for r in rows} == {"lsb", "dct"}
    assert {r["payload_level"] for r in rows} == {"low", "medium", "high"}
    assert {r["encryption"] for r in rows} == {"plain", "encrypted"}
    assert any(r["cover_path"].endswith(".png") for r in rows if r["method"] == "lsb")
    assert any(r["cover_path"].endswith(".jpg") for r in rows if r["method"] == "dct")
    assert all(not Path(r["cover_path"]).is_absolute() for r in rows)
    assert all(not Path(r["payload_path"]).is_absolute() for r in rows)
    assert all(not Path(r["stego_path"]).is_absolute() for r in rows)


def test_run_embedding_stage_dry_run_counts_rows(project_root: Path, small_runner) -> None:
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
                "cover_path": "/tmp/cover.png",
                "payload_path": "/tmp/payload.bin",
                "stego_path": "/tmp/stego.png",
                "embed_params": "{\"bit_depth\": 1, \"fill_rate\": 0.25}",
                "seed": "42",
            },
            {
                "group_id": "1",
                "source": "real",
                "method": "dct",
                "payload_level": "high",
                "encryption": "encrypted",
                "cover_path": "/tmp/cover2.jpg",
                "payload_path": "/tmp/payload2.bin",
                "stego_path": "/tmp/stego2.jpg",
                "embed_params": "{\"fill_rate\": 0.75, \"jpeg_quality\": 95}",
                "seed": "42",
            },
        ],
        fieldnames=STEGO_FIELDNAMES,
    )

    assert small_runner.run_embedding_stage(stego_manifest_path=stego_manifest, execute=False) == 2


def test_run_embedding_stage_execute_produces_stego(project_root: Path, small_runner) -> None:
    cover = project_root / "tmp_cover.png"
    payload = project_root / "tmp_payload.bin"
    stego_out = project_root / "out.png"

    create_image(cover)
    payload.write_bytes(b"\x01\x02\x03")

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
                "cover_path": str(cover),
                "payload_path": str(payload),
                "stego_path": str(stego_out),
                "embed_params": "{\"bit_depth\": 1, \"fill_rate\": 0.25}",
                "seed": "42",
            }
        ],
        fieldnames=STEGO_FIELDNAMES,
    )

    n = small_runner.run_embedding_stage(stego_manifest_path=stego_manifest, execute=True)
    assert n == 1
    assert stego_out.exists()


def test_run_embedding_stage_truncates_payload_to_dct_capacity(
    project_root: Path,
    small_runner,
) -> None:
    payload = project_root / "oversized_payload.bin"
    stego_out = project_root / "out.jpg"
    payload.write_bytes(b"\xAA" * 100)

    stego_manifest = project_root / "data" / "manifests" / "stego_manifest.csv"
    write_rows_csv(
        stego_manifest,
        rows=[
            {
                "group_id": "1",
                "source": "real",
                "method": "dct",
                "payload_level": "low",
                "encryption": "plain",
                "cover_path": str(DCT_FIXTURE),
                "payload_path": str(payload),
                "stego_path": str(stego_out),
                "embed_params": "{\"fill_rate\": 0.25, \"jpeg_quality\": 95}",
                "seed": "42",
            }
        ],
        fieldnames=STEGO_FIELDNAMES,
    )

    n = small_runner.run_embedding_stage(stego_manifest_path=stego_manifest, execute=True)

    assert n == 1
    assert stego_out.exists()


def test_hardcoded_payload_preflight_rejects_text_larger_than_dct_capacity(
    project_root: Path,
) -> None:
    cfg = PipelineConfig(
        project_root=project_root,
        n_groups=1,
        active_methods=("dct",),
        active_payload_levels=("low",),
        payload_mode=PAYLOAD_MODE_HARDCODED,
        hardcoded_payload_text="abcdefg",
    )
    runner = PipelineRunner(cfg)
    covers_manifest = project_root / "data" / "manifests" / "covers_master.csv"
    write_rows_csv(
        covers_manifest,
        rows=[
            {
                "group_id": "1",
                "source": "real",
                "dataset": "fixture",
                "orig_id": "orig-1-real",
                "caption_id": "cap-1",
                "caption_text": "caption",
                "spatial_path": str(DCT_FIXTURE),
                "frequency_path": str(DCT_FIXTURE),
                "qc_pass": "true",
                "qc_score": "0.99",
                "seed": "42",
            }
        ],
        fieldnames=COVER_FIELDNAMES,
    )

    with pytest.raises(ValueError, match="too large for the DCT covers"):
        runner._validate_hardcoded_payload_against_dct_covers(covers_manifest)


def test_run_embedding_stage_execute_raises_on_unknown_method(project_root: Path, small_runner) -> None:
    cover = project_root / "tmp_cover.png"
    payload = project_root / "tmp_payload.bin"

    create_image(cover)
    payload.write_bytes(b"\x00")

    stego_manifest = project_root / "data" / "manifests" / "stego_manifest.csv"
    write_rows_csv(
        stego_manifest,
        rows=[
            {
                "group_id": "1",
                "source": "real",
                "method": "unknown",
                "payload_level": "low",
                "encryption": "plain",
                "cover_path": str(cover),
                "payload_path": str(payload),
                "stego_path": str(project_root / "out.png"),
                "embed_params": "{}",
                "seed": "42",
            }
        ],
        fieldnames=STEGO_FIELDNAMES,
    )

    with pytest.raises(ValueError, match="Unknown method"):
        small_runner.run_embedding_stage(stego_manifest_path=stego_manifest, execute=True)


def test_run_embedding_stage_writes_quality_metrics(project_root: Path, small_runner) -> None:
    """Quality metrics CSV is written when quality_metrics_path is provided."""
    cover = project_root / "tmp_cover.png"
    payload = project_root / "tmp_payload.bin"
    stego_out = project_root / "out.png"

    create_image(cover)
    payload.write_bytes(b"\x01" * 10)  # 80 bits < 96-bit capacity of 24×16 @ 25% fill

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
                "cover_path": str(cover),
                "payload_path": str(payload),
                "stego_path": str(stego_out),
                "embed_params": '{"bit_depth": 1, "fill_rate": 0.25}',
                "seed": "42",
            }
        ],
        fieldnames=STEGO_FIELDNAMES,
    )

    quality_path = project_root / "quality_metrics_raw.csv"
    small_runner.run_embedding_stage(
        stego_manifest_path=stego_manifest,
        execute=True,
        quality_metrics_path=quality_path,
    )

    assert quality_path.exists()
    rows = read_rows_csv(quality_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["group_id"] == "1"
    assert row["method"] == "lsb"
    assert row["psnr"] != "" and float(row["psnr"]) > 0
    assert row["ssim"] != "" and 0.0 <= float(row["ssim"]) <= 1.0


def test_run_embedding_stage_no_quality_path_no_file(project_root: Path, small_runner) -> None:
    """Without quality_metrics_path no quality file is written."""
    cover = project_root / "tmp_cover2.png"
    payload = project_root / "tmp_payload2.bin"
    stego_out = project_root / "out2.png"

    create_image(cover)
    payload.write_bytes(b"\x02" * 10)  # 80 bits < 96-bit capacity of 24×16 @ 25% fill

    stego_manifest = project_root / "data" / "manifests" / "stego_manifest2.csv"
    write_rows_csv(
        stego_manifest,
        rows=[
            {
                "group_id": "2",
                "source": "ml_a",
                "method": "lsb",
                "payload_level": "low",
                "encryption": "plain",
                "cover_path": str(cover),
                "payload_path": str(payload),
                "stego_path": str(stego_out),
                "embed_params": '{"bit_depth": 1, "fill_rate": 0.25}',
                "seed": "42",
            }
        ],
        fieldnames=STEGO_FIELDNAMES,
    )

    quality_path = project_root / "should_not_exist.csv"
    small_runner.run_embedding_stage(stego_manifest_path=stego_manifest, execute=True)
    assert not quality_path.exists()
