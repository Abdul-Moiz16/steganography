from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from src.data.manifests import read_rows_csv, write_rows_csv
from tests.helpers import STEGO_FIELDNAMES, create_image, write_cover_manifest


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
    assert {r["fill_rate"] for r in rows} == {"0.25", "0.5", "0.75"}
    assert {r["bit_depth"] for r in rows} == {"1"}

    sample = rows[0]
    assert sample["payload_path"].endswith(".bin")
    assert not Path(sample["payload_path"]).is_absolute()


def test_build_payload_manifest_with_file_writes_hits_encryption_placeholder(
    project_root: Path,
    small_runner,
) -> None:
    covers_manifest = write_cover_manifest(
        project_root / "data" / "manifests" / "covers_master.csv", group_ids=[1, 2, 3, 4]
    )

    with pytest.raises(NotImplementedError, match="AES-256-CBC encryption"):
        small_runner.build_payload_manifest(
            covers_manifest_path=covers_manifest,
            write_payload_files=True,
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


def test_run_embedding_stage_execute_raises_on_placeholder(project_root: Path, small_runner) -> None:
    cover = project_root / "tmp_cover.png"
    payload = project_root / "tmp_payload.bin"

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
                "stego_path": str(project_root / "out.png"),
                "embed_params": "{\"bit_depth\": 1, \"fill_rate\": 0.25}",
                "seed": "42",
            }
        ],
        fieldnames=STEGO_FIELDNAMES,
    )

    with pytest.raises(NotImplementedError, match="Sequential grayscale LSB embedding"):
        small_runner.run_embedding_stage(stego_manifest_path=stego_manifest, execute=True)


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
