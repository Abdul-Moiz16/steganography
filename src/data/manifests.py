from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class CoverRecord:
    group_id: int
    source: str
    dataset: str
    orig_id: str
    caption_id: str
    caption_text: str
    spatial_path: str
    frequency_path: str
    qc_pass: bool
    qc_score: float
    seed: int


@dataclass(frozen=True)
class PayloadRecord:
    group_id: int
    payload_level: str
    encryption: str
    payload_path: str
    payload_stream_bits: int
    fill_rate: float
    bit_depth: int
    aes_iv: str
    aes_key_id: str
    seed: int


@dataclass(frozen=True)
class StegoRecord:
    group_id: int
    source: str
    method: str
    payload_level: str
    encryption: str
    cover_path: str
    payload_path: str
    stego_path: str
    embed_params: str
    seed: int

def write_dataclass_csv(path: Path, records: Iterable[Any]) -> None:
    rows = [asdict(r) for r in records]
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_rows_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_rows_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def unique_group_ids(covers: Iterable[dict[str, str]]) -> list[int]:
    return sorted({int(row["group_id"]) for row in covers})
