"""Tests for the new experiment tabular exports written by plots.py.

Builds a small synthetic predictions.csv that has both LSB and DCT methods,
multiple payload levels, and both encryption arms — then asserts each of
the new CSV exports is written with the expected columns.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from src.evaluation.plots import _write_experiment_contrast_tables, _load_predictions


SOURCES = ("real", "ml_a", "ml_b")
METHODS = ("lsb", "dct")
PAYLOADS = ("low", "medium", "high")
DETECTORS = ("rs", "chi_square_spatial", "chi_square_dct")


def _write_synthetic_predictions(run_dir: Path, *, n_groups: int = 30) -> Path:
    (run_dir / "predictions").mkdir(parents=True)
    (run_dir / "metrics").mkdir(parents=True)

    rng = np.random.default_rng(20260511)
    rows: list[dict[str, object]] = []
    for group_id in range(1, n_groups + 1):
        for detector in DETECTORS:
            for source in SOURCES:
                for method in METHODS:
                    for payload_level in PAYLOADS:
                        for encryption in ("plain", "encrypted"):
                            cover_score = float(rng.normal(0.2, 0.05))
                            stego_score = float(rng.normal(0.6, 0.08))
                            rows.append({
                                "detector": detector,
                                "group_id": group_id,
                                "source": source,
                                "method": method,
                                "payload_level": payload_level,
                                "encryption": encryption,
                                "label": 0, "score": cover_score,
                            })
                            rows.append({
                                "detector": detector,
                                "group_id": group_id,
                                "source": source,
                                "method": method,
                                "payload_level": payload_level,
                                "encryption": encryption,
                                "label": 1, "score": stego_score,
                            })

    path = run_dir / "predictions" / "predictions.csv"
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture()
def run_dir(tmp_path: Path) -> Path:
    _write_synthetic_predictions(tmp_path)
    return tmp_path


def test_exports_emit_all_five_experiment_tables(run_dir: Path) -> None:
    predictions = _load_predictions(run_dir / "predictions" / "predictions.csv")
    outputs = _write_experiment_contrast_tables(run_dir / "metrics", predictions)

    expected_keys = {
        "exp1_contrasts",
        "exp2_contrasts",
        "exp3_contrasts",
        "exp4_contrasts",
        "exp5_contrasts",
        "exp5_interaction_contrasts",
        "experiments_summary",
    }
    assert expected_keys <= set(outputs.keys())
    for key in expected_keys:
        assert outputs[key].exists(), f"{key} CSV was not written"


def test_exp3_csv_has_per_source_rows(run_dir: Path) -> None:
    predictions = _load_predictions(run_dir / "predictions" / "predictions.csv")
    outputs = _write_experiment_contrast_tables(run_dir / "metrics", predictions)
    rows = _read_csv(outputs["exp3_contrasts"])
    assert {r["source"] for r in rows} == set(SOURCES)
    expected_columns = {
        "experiment", "detector", "method", "source", "payload_level",
        "auc", "se", "ci_lo", "ci_hi", "n_pos", "n_neg", "real_minus_ml_gap",
    }
    assert expected_columns == set(rows[0].keys())


def test_exp4_csv_records_branch_interaction(run_dir: Path) -> None:
    predictions = _load_predictions(run_dir / "predictions" / "predictions.csv")
    outputs = _write_experiment_contrast_tables(run_dir / "metrics", predictions)
    rows = _read_csv(outputs["exp4_contrasts"])
    expected_columns = {
        "experiment", "payload_level",
        "spatial_method", "frequency_method",
        "n_spatial_detectors", "n_frequency_detectors",
        "gap_spatial", "gap_frequency", "diff", "se",
        "ci_lo", "ci_hi", "z", "p",
    }
    assert expected_columns == set(rows[0].keys())
    # One pooled row per payload level present.
    assert {r["payload_level"] for r in rows} == set(PAYLOADS)
    # Each row pools across multiple detectors.
    assert all(int(r["n_spatial_detectors"]) >= 1 for r in rows)
    assert all(int(r["n_frequency_detectors"]) >= 1 for r in rows)


def test_exp5_interaction_csv_has_dd_columns(run_dir: Path) -> None:
    predictions = _load_predictions(run_dir / "predictions" / "predictions.csv")
    outputs = _write_experiment_contrast_tables(run_dir / "metrics", predictions)
    rows = _read_csv(outputs["exp5_interaction_contrasts"])
    expected_columns = {
        "experiment", "detector", "method", "payload_level",
        "delta_real", "delta_ml_mean", "diff", "se",
        "ci_lo", "ci_hi", "z", "p",
    }
    assert expected_columns == set(rows[0].keys())


def test_experiments_summary_aggregates_all_experiments(run_dir: Path) -> None:
    predictions = _load_predictions(run_dir / "predictions" / "predictions.csv")
    outputs = _write_experiment_contrast_tables(run_dir / "metrics", predictions)
    rows = _read_csv(outputs["experiments_summary"])
    experiments = {r["experiment"] for r in rows}
    assert {
        "exp1_rq1_real_vs_pooled_ml",
        "exp2_rq2_mla_vs_mlb",
        "exp3_rq3_payload_interaction",
        "exp4_rq4_spatial_vs_frequency",
        "exp5_rq5_plain_vs_encrypted",
        "exp5_rq5_source_x_encryption",
    } <= experiments


def test_export_tolerates_empty_predictions(tmp_path: Path) -> None:
    (tmp_path / "metrics").mkdir()
    outputs = _write_experiment_contrast_tables(tmp_path / "metrics", [])
    assert outputs == {}


def test_generate_metrics_figures_registers_new_rq_figures(run_dir: Path) -> None:
    """The orchestrator must expose the RQ-specific plot output keys."""
    from src.evaluation.plots import generate_metrics_figures

    figures = generate_metrics_figures(run_dir / "metrics", run_dir / "figures")
    for key in (
        "rq3_source_payload_heatmap",
        "rq4_branch_auc_bars",
        "rq_summary_cards",
    ):
        assert key in figures, f"missing figure key: {key}"
        assert figures[key].exists()


def test_export_skips_exp4_when_only_one_method(tmp_path: Path) -> None:
    """Exp 4 needs both spatial and frequency branches; LSB-only data → no exp4."""
    (tmp_path / "predictions").mkdir(parents=True)
    (tmp_path / "metrics").mkdir(parents=True)
    with (tmp_path / "predictions" / "predictions.csv").open("w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["detector", "group_id", "source", "method",
                           "payload_level", "encryption", "label", "score"],
        )
        writer.writeheader()
        rng = np.random.default_rng(42)
        for group_id in range(1, 11):
            for source in SOURCES:
                for encryption in ("plain", "encrypted"):
                    for label in (0, 1):
                        writer.writerow({
                            "detector": "rs", "group_id": group_id, "source": source,
                            "method": "lsb", "payload_level": "low",
                            "encryption": encryption, "label": label,
                            "score": float(rng.normal(0.3 + 0.2 * label, 0.05)),
                        })

    predictions = _load_predictions(tmp_path / "predictions" / "predictions.csv")
    outputs = _write_experiment_contrast_tables(tmp_path / "metrics", predictions)
    assert "exp4_contrasts" not in outputs
    assert "exp5_interaction_contrasts" in outputs
