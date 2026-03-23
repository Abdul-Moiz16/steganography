from __future__ import annotations

from pathlib import Path

from src.data.manifests import (
    CoverRecord,
    read_json,
    read_rows_csv,
    unique_group_ids,
    write_dataclass_csv,
    write_json,
    write_rows_csv,
)


def test_write_and_read_dataclass_csv(tmp_path: Path) -> None:
    path = tmp_path / "covers.csv"
    records = [
        CoverRecord(
            group_id=1,
            source="real",
            dataset="coco",
            orig_id="abc",
            caption_id="cap1",
            caption_text="a caption",
            spatial_path="/tmp/g0001.png",
            frequency_path="/tmp/g0001.jpg",
            qc_pass=True,
            qc_score=0.95,
            seed=42,
        ),
        CoverRecord(
            group_id=2,
            source="ml_a",
            dataset="sdxl",
            orig_id="def",
            caption_id="cap2",
            caption_text="another caption",
            spatial_path="/tmp/g0002.png",
            frequency_path="/tmp/g0002.jpg",
            qc_pass=False,
            qc_score=0.10,
            seed=100,
        ),
    ]

    write_dataclass_csv(path, records)
    rows = read_rows_csv(path)

    assert len(rows) == 2
    assert rows[0]["group_id"] == "1"
    assert rows[0]["source"] == "real"
    assert rows[1]["dataset"] == "sdxl"
    assert rows[0]["spatial_path"] == "/tmp/g0001.png"
    assert rows[1]["frequency_path"] == "/tmp/g0002.jpg"


def test_write_dataclass_csv_empty_writes_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    write_dataclass_csv(path, [])
    assert path.read_text(encoding="utf-8") == ""


def test_write_rows_read_rows_and_unique_group_ids(tmp_path: Path) -> None:
    path = tmp_path / "rows.csv"
    fieldnames = ["group_id", "source"]
    rows = [
        {"group_id": "2", "source": "real"},
        {"group_id": "1", "source": "ml_a"},
        {"group_id": "2", "source": "ml_b"},
    ]

    write_rows_csv(path, rows, fieldnames=fieldnames)
    read_back = read_rows_csv(path)

    assert read_back == rows
    assert unique_group_ids(read_back) == [1, 2]


def test_write_and_read_json(tmp_path: Path) -> None:
    path = tmp_path / "obj.json"
    obj = {"b": 2, "a": [1, 2, 3]}

    write_json(path, obj)
    loaded = read_json(path)

    assert loaded == obj
