"""Tests for src/analysis/rq_verdicts.py.

Constructs minimal contrast CSVs by hand and exercises each verdict
classifier path: confirmatory (Holm), exploratory (CI), RQ3 monotone
trend, and RQ5 equivalence margin.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from src.analysis.rq_verdicts import (
    compute_rq_verdicts,
    render_markdown,
    run_rq_verdicts,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _empty_metrics(tmp_path: Path) -> Path:
    metrics_dir = tmp_path / "metrics"
    metrics_dir.mkdir(parents=True)
    return metrics_dir


def test_verdicts_no_data_when_metrics_empty(tmp_path: Path) -> None:
    metrics_dir = _empty_metrics(tmp_path)
    data = compute_rq_verdicts(metrics_dir)
    for rq in ("RQ1", "RQ2", "RQ3", "RQ4", "RQ5"):
        assert data["verdicts"][rq]["verdict"] == "no_data"


def test_rq1_supported_when_holm_significant(tmp_path: Path) -> None:
    metrics_dir = _empty_metrics(tmp_path)
    _write_csv(metrics_dir / "exp1_rq1_real_vs_pooled_ml_contrasts.csv", [
        {"detector": "rs", "method": "lsb", "payload_level": "low",
         "diff": 0.10, "se": 0.02, "p": 0.001, "p_holm": 0.001,
         "n_pos_a": 50, "n_neg_a": 50, "n_pos_b": 100, "n_neg_b": 100},
        {"detector": "rs", "method": "lsb", "payload_level": "medium",
         "diff": 0.08, "se": 0.02, "p": 0.001, "p_holm": 0.003,
         "n_pos_a": 50, "n_neg_a": 50, "n_pos_b": 100, "n_neg_b": 100},
    ])
    data = compute_rq_verdicts(metrics_dir)
    rq1 = data["verdicts"]["RQ1"]
    assert rq1["verdict"] == "supported"
    assert rq1["n_significant_holm_0_05"] == 2
    assert rq1["pooled_diff"] > 0


def test_rq1_mixed_when_signs_disagree(tmp_path: Path) -> None:
    metrics_dir = _empty_metrics(tmp_path)
    _write_csv(metrics_dir / "exp1_rq1_real_vs_pooled_ml_contrasts.csv", [
        {"detector": "rs", "method": "lsb", "payload_level": "low",
         "diff": 0.10, "se": 0.02, "p": 0.001, "p_holm": 0.001,
         "n_pos_a": 50, "n_neg_a": 50, "n_pos_b": 100, "n_neg_b": 100},
        {"detector": "rs", "method": "lsb", "payload_level": "medium",
         "diff": -0.08, "se": 0.02, "p": 0.001, "p_holm": 0.003,
         "n_pos_a": 50, "n_neg_a": 50, "n_pos_b": 100, "n_neg_b": 100},
    ])
    rq1 = compute_rq_verdicts(metrics_dir)["verdicts"]["RQ1"]
    assert rq1["verdict"] == "mixed"


def test_rq1_underpowered_when_all_strata_below_threshold(tmp_path: Path) -> None:
    metrics_dir = _empty_metrics(tmp_path)
    _write_csv(metrics_dir / "exp1_rq1_real_vs_pooled_ml_contrasts.csv", [
        {"detector": "rs", "method": "lsb", "payload_level": "low",
         "diff": 0.10, "se": 0.20, "p": 0.6, "p_holm": 0.6,
         "n_pos_a": 5, "n_neg_a": 5, "n_pos_b": 10, "n_neg_b": 10},
    ])
    rq1 = compute_rq_verdicts(metrics_dir)["verdicts"]["RQ1"]
    assert rq1["verdict"] == "inconclusive_underpowered"


def test_rq4_supported_when_ci_excludes_zero(tmp_path: Path) -> None:
    metrics_dir = _empty_metrics(tmp_path)
    _write_csv(metrics_dir / "exp4_rq4_spatial_vs_frequency_contrasts.csv", [
        {"detector": "rs", "payload_level": "low",
         "diff": 0.05, "se": 0.01, "ci_lo": 0.03, "ci_hi": 0.07,
         "z": 5.0, "p": 0.0001},
    ])
    rq4 = compute_rq_verdicts(metrics_dir)["verdicts"]["RQ4"]
    assert rq4["verdict"] == "supported"
    assert rq4["n_significant_ci_excludes_0"] == 1


def test_rq3_monotone_trend_supported(tmp_path: Path) -> None:
    metrics_dir = _empty_metrics(tmp_path)
    rows = []
    for pl, gap in [("low", 0.02), ("medium", 0.05), ("high", 0.08)]:
        rows.append({
            "detector": "rs", "method": "lsb", "source": "real", "payload_level": pl,
            "auc": 0.85, "se": 0.02, "ci_lo": 0.80, "ci_hi": 0.90,
            "n_pos": 50, "n_neg": 50, "real_minus_ml_gap": gap,
        })
    _write_csv(metrics_dir / "exp3_rq3_payload_interaction_contrasts.csv", rows)
    rq3 = compute_rq_verdicts(metrics_dir)["verdicts"]["RQ3"]
    assert rq3["monotone_trend"] == "increasing"
    assert rq3["verdict"] == "supported"


def test_rq5_invariant_when_all_within_margin(tmp_path: Path) -> None:
    metrics_dir = _empty_metrics(tmp_path)
    _write_csv(metrics_dir / "exp5_rq5_encryption_contrasts.csv", [
        {"detector": "rs", "source": "real", "method": "lsb", "payload_level": "low",
         "diff": 0.005, "se": 0.005, "ci_lo": -0.005, "ci_hi": 0.015,
         "z": 1.0, "p": 0.32},
        {"detector": "rs", "source": "ml_a", "method": "lsb", "payload_level": "low",
         "diff": -0.002, "se": 0.005, "ci_lo": -0.012, "ci_hi": 0.008,
         "z": -0.4, "p": 0.69},
    ])
    rq5 = compute_rq_verdicts(metrics_dir)["verdicts"]["RQ5"]
    assert rq5["verdict"] == "supported"
    assert rq5["n_outside_margin"] == 0


def test_rq5_violated_when_ci_outside_margin(tmp_path: Path) -> None:
    metrics_dir = _empty_metrics(tmp_path)
    _write_csv(metrics_dir / "exp5_rq5_encryption_contrasts.csv", [
        {"detector": "rs", "source": "real", "method": "lsb", "payload_level": "low",
         "diff": 0.10, "se": 0.02, "ci_lo": 0.06, "ci_hi": 0.14,
         "z": 5.0, "p": 0.0001},
    ])
    rq5 = compute_rq_verdicts(metrics_dir)["verdicts"]["RQ5"]
    assert rq5["verdict"] == "not_supported"


def test_run_rq_verdicts_writes_json_and_md(tmp_path: Path) -> None:
    _empty_metrics(tmp_path)
    json_path, md_path = run_rq_verdicts(tmp_path)
    assert json_path.exists() and md_path.exists()
    data = json.loads(json_path.read_text())
    assert "verdicts" in data
    md = md_path.read_text()
    assert "Research Question Verdicts" in md
    assert "RQ1" in md and "RQ5" in md


def test_markdown_includes_all_rqs(tmp_path: Path) -> None:
    metrics_dir = _empty_metrics(tmp_path)
    data = compute_rq_verdicts(metrics_dir)
    md = render_markdown(data)
    for rq in ("RQ1", "RQ2", "RQ3", "RQ4", "RQ5"):
        assert f"## {rq}" in md
