"""
Worker : Nikolas Zouros

Paired t-tests for steganalysis comparisons.

Parametric counterpart to ``src.analysis.wilcoxon_tests``. Reads
predictions.csv from a finished run and writes a per-comparison t-test
CSV with raw + Bonferroni-corrected p-values and Cohen's d effect sizes.

Usage
-----
    python -m src.analysis.t_tests runs/<run-id>

Comparisons (paired by group_id with all other factors held fixed):
    - plain_vs_aes          : same image, plain vs encrypted payload
    - real_vs_sdxl          : same caption group, real vs ml_a
    - real_vs_flux          : same caption group, real vs ml_b
    - sdxl_vs_flux          : same caption group, ml_a vs ml_b

Output CSV: metrics/t_tests.csv (one row per comparison x detector)
    n_pairs        : how many paired observations went into the test
    t_stat         : Student's t statistic
    p_value        : raw two-sided p-value
    p_corrected    : Bonferroni-adjusted p-value (this is the one to trust)
    cohens_d       : standardised mean of the paired differences
                     (|d| ~ 0.2 small, 0.5 medium, 0.8 large)
    significant    : True only if p_corrected < 0.05

The Wilcoxon signed-rank companion is recommended when score distributions
are heavy-tailed; report both side-by-side as a robustness check.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import ttest_rel


def _load_predictions(predictions_csv: Path) -> list[dict[str, str]]:
    """Read predictions.csv into a list of row dicts (one per detection event)."""
    with predictions_csv.open(newline="") as f:
        return list(csv.DictReader(f))


def _stego_only(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep only rows where label=1 (stego images); drop clean-image rows."""
    return [r for r in rows if r["label"] == "1"]


def _key(row: dict[str, str], holding: tuple[str, ...]) -> tuple:
    """Build a tuple of values from the columns we hold fixed when pairing rows."""
    return tuple(row[k] for k in holding)


def _paired_scores(
    rows: list[dict[str, str]],
    factor: str,
    val_a: str,
    val_b: str,
    holding: tuple[str, ...],
) -> tuple[list[float], list[float]]:
    """Find rows that match on `holding` and differ on `factor`; return aligned score lists.

    The two returned lists are aligned: index i of both comes from the same
    image-condition pair. Rows without a matching partner are silently dropped.
    """
    a_index: dict[tuple, float] = {}
    b_index: dict[tuple, float] = {}
    for r in rows:
        if r[factor] == val_a:
            a_index[_key(r, holding)] = float(r["score"])
        elif r[factor] == val_b:
            b_index[_key(r, holding)] = float(r["score"])

    common = sorted(set(a_index) & set(b_index))
    a_scores = [a_index[k] for k in common]
    b_scores = [b_index[k] for k in common]
    return a_scores, b_scores


def _cohens_d_paired(a: list[float], b: list[float]) -> float:
    """Cohen's d for paired samples: mean(a-b) / std(a-b, ddof=1).

    The p-value tells you IF a difference exists; this tells you HOW BIG it is
    in standard-deviation units. |d| ~ 0.2 small, 0.5 medium, 0.8 large.
    Returns 0.0 if the within-pair differences are constant.
    """
    diffs = np.array(a, dtype=float) - np.array(b, dtype=float)
    if diffs.size < 2:
        return 0.0
    sd = float(np.std(diffs, ddof=1))
    if sd == 0.0:
        return 0.0
    return float(np.mean(diffs) / sd)


def _run_comparison(
    rows: list[dict[str, str]],
    name: str,
    factor: str,
    val_a: str,
    val_b: str,
    holding: tuple[str, ...],
    group_by: tuple[str, ...] = ("detector",),
) -> list[dict[str, object]]:
    """Run one paired t-test, separately for each detector.

    Splits rows into buckets by `group_by` (default: per detector), pairs each
    bucket on `holding` columns, and runs scipy.stats.ttest_rel on the scores
    where `factor` differs between val_a and val_b. Returns one result row per
    bucket containing the t statistic, raw p-value, Cohen's d, and pair count.
    Buckets with fewer than 3 pairs or all-tied differences are marked n/a.
    """
    buckets: dict[tuple, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        buckets[tuple(r[k] for k in group_by)].append(r)

    results: list[dict[str, object]] = []
    for bucket_key, bucket_rows in sorted(buckets.items()):
        a, b = _paired_scores(bucket_rows, factor, val_a, val_b, holding)
        n = len(a)
        row: dict[str, object] = {
            "comparison": name,
            **dict(zip(group_by, bucket_key)),
            "n_pairs": n,
            "t_stat": "",
            "p_value": "",
            "p_corrected": "",
            "cohens_d": "",
            "significant": "",
        }
        if n < 3:
            row["t_stat"] = "n/a"
            row["p_value"] = "n/a"
            results.append(row)
            continue

        diffs = np.array(a, dtype=float) - np.array(b, dtype=float)
        if np.allclose(diffs, 0.0):
            row["t_stat"] = "n/a"
            row["p_value"] = "n/a"
            results.append(row)
            continue

        stat, p = ttest_rel(a, b, alternative="two-sided")
        if not np.isfinite(stat) or not np.isfinite(p):
            row["t_stat"] = "n/a"
            row["p_value"] = "n/a"
            results.append(row)
            continue

        row["t_stat"] = round(float(stat), 3)
        row["p_value"] = float(p)
        row["cohens_d"] = round(_cohens_d_paired(a, b), 3)
        results.append(row)
    return results


def _bonferroni(results: list[dict[str, object]], alpha: float = 0.05) -> None:
    """Bonferroni-correct the raw p-values in place across the family of tests."""
    valid = [r for r in results if isinstance(r["p_value"], float)]
    m = len(valid)
    if m == 0:
        return
    for r in valid:
        p_corr = min(1.0, float(r["p_value"]) * m)
        r["p_corrected"] = round(p_corr, 6)
        r["significant"] = p_corr < alpha
        r["p_value"] = round(float(r["p_value"]), 6)


def run_t_tests(run_dir: Path) -> Path:
    """Run all paired t-tests on a finished run and save the result CSV.

    Loads predictions.csv from the run dir, filters to stego-only rows, runs
    4 paired comparisons (encryption + 3 source pairs) per detector, applies
    Bonferroni correction across the family of tests, and writes
    ``metrics/t_tests.csv``. Returns the output path.
    """
    predictions_csv = run_dir / "predictions" / "predictions.csv"
    if not predictions_csv.exists():
        raise FileNotFoundError(f"predictions.csv not found at {predictions_csv}")

    rows = _stego_only(_load_predictions(predictions_csv))

    results: list[dict[str, object]] = []

    # 1. Encryption effect (RQ5): plain vs aes
    results += _run_comparison(
        rows,
        name="plain_vs_aes",
        factor="encryption",
        val_a="plain",
        val_b="encrypted",
        holding=("group_id", "source", "method", "payload_level"),
    )

    # 2. Source effects (RQ1)
    for name, val_a, val_b in [
        ("real_vs_sdxl", "real", "ml_a"),
        ("real_vs_flux", "real", "ml_b"),
        ("sdxl_vs_flux", "ml_a", "ml_b"),
    ]:
        results += _run_comparison(
            rows,
            name=name,
            factor="source",
            val_a=val_a,
            val_b=val_b,
            holding=("group_id", "method", "payload_level", "encryption"),
        )

    _bonferroni(results)

    out_path = run_dir / "metrics" / "t_tests.csv"
    fieldnames = [
        "comparison", "detector", "n_pairs",
        "t_stat", "p_value", "p_corrected",
        "cohens_d", "significant",
    ]
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"Wrote {len(results)} test rows to {out_path}")
    return out_path


def main() -> None:
    """CLI entry: take a run-dir path from argv and call run_t_tests."""
    if len(sys.argv) != 2:
        print("Usage: python -m src.analysis.t_tests <run_dir>")
        sys.exit(1)
    run_t_tests(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
