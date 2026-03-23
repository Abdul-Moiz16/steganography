from __future__ import annotations

"""Merge real and ML cover manifests into the final covers_master.csv."""

import argparse
from pathlib import Path

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

SOURCE_ORDER = {"real": 0, "ml_a": 1, "ml_b": 2}


def _resolve_path(project_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else (project_root / path)


def _validate_source(rows: list[dict[str, str]], expected_source: str, manifest_name: str) -> None:
    bad = [r for r in rows if r.get("source") != expected_source]
    if bad:
        raise ValueError(
            f"{manifest_name} has invalid source column values; expected only '{expected_source}'."
        )


def _group_ids(rows: list[dict[str, str]]) -> set[int]:
    return {int(r["group_id"]) for r in rows}


def _validate_required_columns(rows: list[dict[str, str]], manifest_name: str) -> None:
    if not rows:
        raise ValueError(f"{manifest_name} has no rows.")
    missing = set(FIELDNAMES) - set(rows[0].keys())
    if missing:
        raise ValueError(f"{manifest_name} missing columns: {sorted(missing)}")


def _assert_unique_pairs(rows: list[dict[str, str]], manifest_name: str) -> None:
    seen: set[tuple[int, str]] = set()
    for row in rows:
        pair = (int(row["group_id"]), row["source"])
        if pair in seen:
            raise ValueError(f"Duplicate (group_id, source) pair found in {manifest_name}: {pair}")
        seen.add(pair)


def merge_covers_master(
    *,
    project_root: Path,
    real_manifest: Path,
    ml_a_manifest: Path,
    ml_b_manifest: Path,
    output_manifest: Path | None = None,
    expected_groups: int = 500,
) -> Path:
    """Merge three source-specific manifests into final covers_master.csv.

    Validations:
    - each source manifest has expected source values
    - group-id sets are identical across sources
    - row count per source equals expected_groups
    - final merged rows equal expected_groups * 3
    """
    project_root = project_root.resolve()
    real_path = _resolve_path(project_root, real_manifest)
    ml_a_path = _resolve_path(project_root, ml_a_manifest)
    ml_b_path = _resolve_path(project_root, ml_b_manifest)

    rows_real = read_rows_csv(real_path)
    rows_ml_a = read_rows_csv(ml_a_path)
    rows_ml_b = read_rows_csv(ml_b_path)

    _validate_required_columns(rows_real, "real manifest")
    _validate_required_columns(rows_ml_a, "ml_a manifest")
    _validate_required_columns(rows_ml_b, "ml_b manifest")

    _validate_source(rows_real, "real", "real manifest")
    _validate_source(rows_ml_a, "ml_a", "ml_a manifest")
    _validate_source(rows_ml_b, "ml_b", "ml_b manifest")

    _assert_unique_pairs(rows_real, "real manifest")
    _assert_unique_pairs(rows_ml_a, "ml_a manifest")
    _assert_unique_pairs(rows_ml_b, "ml_b manifest")

    ids_real = _group_ids(rows_real)
    ids_ml_a = _group_ids(rows_ml_a)
    ids_ml_b = _group_ids(rows_ml_b)

    if ids_real != ids_ml_a or ids_real != ids_ml_b:
        raise ValueError("Input manifests do not share identical group IDs.")

    if len(ids_real) != expected_groups:
        raise ValueError(
            f"Expected {expected_groups} unique groups, got {len(ids_real)}."
        )

    combined = rows_real + rows_ml_a + rows_ml_b
    combined.sort(key=lambda r: (int(r["group_id"]), SOURCE_ORDER[r["source"]]))

    if len(combined) != expected_groups * 3:
        raise ValueError(
            f"Expected {expected_groups * 3} rows in final manifest, got {len(combined)}."
        )

    # Re-check uniqueness after merge.
    _assert_unique_pairs(combined, "combined manifest")

    out_path = output_manifest or (project_root / "data" / "manifests" / "covers_master.csv")
    out_path = _resolve_path(project_root, out_path)
    write_rows_csv(out_path, combined, fieldnames=FIELDNAMES)
    return out_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Merge real + ml_a + ml_b cover manifests into final covers_master.csv"
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--real-manifest",
        type=Path,
        default=Path("data/manifests/covers_master_real.csv"),
    )
    parser.add_argument(
        "--ml-a-manifest",
        type=Path,
        default=Path("data/manifests/covers_master_ml_a.csv"),
    )
    parser.add_argument(
        "--ml-b-manifest",
        type=Path,
        default=Path("data/manifests/covers_master_ml_b.csv"),
    )
    parser.add_argument(
        "--output-manifest",
        type=Path,
        default=Path("data/manifests/covers_master.csv"),
    )
    parser.add_argument("--expected-groups", type=int, default=500)
    return parser


def main() -> None:
    args = _parser().parse_args()
    out = merge_covers_master(
        project_root=args.project_root,
        real_manifest=args.real_manifest,
        ml_a_manifest=args.ml_a_manifest,
        ml_b_manifest=args.ml_b_manifest,
        output_manifest=args.output_manifest,
        expected_groups=args.expected_groups,
    )
    print(f"Merged covers manifest: {out}")


if __name__ == "__main__":
    main()
