"""Tests for src/analysis/power_analysis.py.

Exercises the closed-form Hanley-McNeil variance, the a priori required-n
calculator (with and without Holm correction), and the pilot-based
extrapolation. Smoke tests the run-level orchestrator against synthetic
contrast tables.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import pytest

from src.analysis.power_analysis import (
    hanley_mcneil_var,
    hanley_mcneil_se,
    required_n_a_priori,
    required_n_from_pilot,
    run_power_analysis,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_hanley_mcneil_se_shrinks_with_sample_size() -> None:
    se_small = hanley_mcneil_se(0.85, 50, 50)
    se_big = hanley_mcneil_se(0.85, 500, 500)
    assert se_small > se_big > 0
    # 10x more data should roughly cut SE by sqrt(10).
    assert se_small / se_big == pytest.approx(math.sqrt(10), rel=0.15)


def test_hanley_mcneil_returns_nan_for_degenerate_inputs() -> None:
    assert math.isnan(hanley_mcneil_var(0.0, 100, 100))
    assert math.isnan(hanley_mcneil_var(1.0, 100, 100))
    assert math.isnan(hanley_mcneil_var(0.85, 0, 100))


def test_required_n_a_priori_monotone_in_alpha() -> None:
    """Tighter alpha (Holm with more tests) should never reduce the n required."""
    n_baseline = required_n_a_priori(
        target_diff=0.05, target_auc=0.85, alpha=0.05, power=0.80, n_tests=1,
    )
    n_holm = required_n_a_priori(
        target_diff=0.05, target_auc=0.85, alpha=0.05, power=0.80, n_tests=15,
    )
    assert n_holm >= n_baseline


def test_required_n_a_priori_monotone_in_power() -> None:
    n_80 = required_n_a_priori(target_diff=0.05, target_auc=0.85, power=0.80)
    n_90 = required_n_a_priori(target_diff=0.05, target_auc=0.85, power=0.90)
    assert n_90 > n_80


def test_required_n_a_priori_paired_smaller_than_unpaired() -> None:
    n_paired = required_n_a_priori(
        target_diff=0.05, target_auc=0.85, paired=True,
    )
    n_unpaired = required_n_a_priori(
        target_diff=0.05, target_auc=0.85, paired=False,
    )
    assert n_paired < n_unpaired


def test_required_n_a_priori_smaller_diff_needs_more_n() -> None:
    n_big = required_n_a_priori(target_diff=0.10, target_auc=0.85)
    n_small = required_n_a_priori(target_diff=0.02, target_auc=0.85)
    assert n_small > n_big


def test_required_n_from_pilot_returns_none_for_zero_diff() -> None:
    assert required_n_from_pilot(
        observed_diff=0.0, observed_se=0.02, pilot_n_per_group=40,
    ) is None


def test_required_n_from_pilot_grows_with_smaller_diff() -> None:
    pilot_n = 40
    n_obs_big = required_n_from_pilot(
        observed_diff=0.10, observed_se=0.02, pilot_n_per_group=pilot_n,
    )
    n_obs_small = required_n_from_pilot(
        observed_diff=0.01, observed_se=0.02, pilot_n_per_group=pilot_n,
    )
    assert n_obs_small > n_obs_big


def test_run_power_analysis_produces_summary_and_detail(tmp_path: Path) -> None:
    metrics_dir = tmp_path / "metrics"
    metrics_dir.mkdir()
    _write_csv(metrics_dir / "exp1_rq1_real_vs_pooled_ml_contrasts.csv", [
        {"detector": "rs", "method": "lsb", "payload_level": "low",
         "diff": 0.04, "se": 0.025, "p": 0.10, "p_holm": 0.10,
         "n_pos_a": 40, "n_neg_a": 40, "n_pos_b": 80, "n_neg_b": 80},
    ])
    _write_csv(metrics_dir / "exp5_rq5_encryption_contrasts.csv", [
        {"detector": "rs", "source": "real", "method": "lsb", "payload_level": "low",
         "diff": 0.005, "se": 0.01, "ci_lo": -0.015, "ci_hi": 0.025,
         "z": 0.5, "p": 0.62,
         "n_pos_a": 40, "n_neg_a": 40, "n_pos_b": 40, "n_neg_b": 40},
    ])

    detail_path, summary_path = run_power_analysis(tmp_path)
    assert detail_path.exists() and summary_path.exists()

    with summary_path.open(newline="") as f:
        summary = list(csv.DictReader(f))
    assert {r["rq"] for r in summary} >= {"RQ1", "RQ2", "RQ4", "RQ5"}
    rq1 = next(r for r in summary if r["rq"] == "RQ1")
    # A priori 80% power for RQ1 should be a sensible integer.
    assert int(rq1["n_a_priori_80pct_power"]) > 0


def test_run_power_analysis_handles_missing_csvs(tmp_path: Path) -> None:
    metrics_dir = tmp_path / "metrics"
    metrics_dir.mkdir()
    detail_path, summary_path = run_power_analysis(tmp_path)
    # summary still produced (a priori envelope works without pilot data).
    assert summary_path.exists()
    # detail file is only produced if at least one row was harvested.
    if detail_path.exists():
        with detail_path.open(newline="") as f:
            assert sum(1 for _ in f) <= 1  # header only
