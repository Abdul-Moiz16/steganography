"""Smoke tests for the per-run statistical analysis modules.

Builds a tiny synthetic predictions.csv with the columns the runner emits,
then invokes the three analysis entry points and checks the resulting CSV
headers and row counts. The tests stay deliberately small: the goal is to
guarantee the modules wire up correctly against the schema, not to validate
the statistical content (which is exercised by the upstream scipy tests).
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from src.analysis.encryption_invariance import run_encryption_invariance
from src.analysis.t_tests import run_t_tests
from src.analysis.wilcoxon_tests import run_wilcoxon_tests


_DETECTORS = ("chi_square_spatial", "rs")
_SOURCES = ("real", "ml_a")
_METHOD = "lsb"
_PAYLOAD = "low"
_ENCRYPTIONS = ("plain", "encrypted")


def _write_synthetic_predictions(run_dir: Path, *, n_groups: int = 20) -> None:
    """Emit predictions.csv with two detectors, two sources, two encryption arms."""
    (run_dir / "predictions").mkdir(parents=True)
    (run_dir / "metrics").mkdir(parents=True)

    rng = np.random.default_rng(20260511)
    rows: list[dict[str, object]] = []
    for group_id in range(1, n_groups + 1):
        for detector in _DETECTORS:
            for source in _SOURCES:
                for encryption in _ENCRYPTIONS:
                    cover_score = float(rng.normal(0.2, 0.05))
                    stego_score = float(rng.normal(0.6, 0.08))
                    rows.append(
                        {
                            "detector": detector,
                            "group_id": group_id,
                            "source": source,
                            "method": _METHOD,
                            "payload_level": _PAYLOAD,
                            "encryption": encryption,
                            "label": 0,
                            "score": cover_score,
                        }
                    )
                    rows.append(
                        {
                            "detector": detector,
                            "group_id": group_id,
                            "source": source,
                            "method": _METHOD,
                            "payload_level": _PAYLOAD,
                            "encryption": encryption,
                            "label": 1,
                            "score": stego_score,
                        }
                    )

    fieldnames = list(rows[0].keys())
    with (run_dir / "predictions" / "predictions.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture()
def run_dir(tmp_path: Path) -> Path:
    _write_synthetic_predictions(tmp_path)
    return tmp_path


def test_wilcoxon_writes_expected_schema(run_dir: Path) -> None:
    out = run_wilcoxon_tests(run_dir)
    rows = _read_csv(out)

    assert out == run_dir / "metrics" / "wilcoxon_tests.csv"
    assert {
        "comparison", "detector", "n_pairs", "W_stat",
        "p_value", "p_corrected", "effect_size_r", "significant",
    } == set(rows[0].keys())

    comparisons = {r["comparison"] for r in rows}
    assert {"plain_vs_aes", "real_vs_sdxl"} <= comparisons


def test_t_test_writes_expected_schema(run_dir: Path) -> None:
    out = run_t_tests(run_dir)
    rows = _read_csv(out)

    assert out == run_dir / "metrics" / "t_tests.csv"
    assert {
        "comparison", "detector", "n_pairs", "t_stat",
        "p_value", "p_corrected", "cohens_d", "significant",
    } == set(rows[0].keys())


def test_encryption_invariance_writes_expected_schema(run_dir: Path) -> None:
    out = run_encryption_invariance(run_dir)
    rows = _read_csv(out)

    assert out == run_dir / "metrics" / "encryption_invariance.csv"
    expected_columns = {
        "detector", "source", "method", "payload_level",
        "n_pos_plain", "n_neg_plain", "n_pos_enc", "n_neg_enc",
        "auc_plain", "auc_encrypted", "auc_diff",
        "ci_lo", "ci_hi", "p_value", "invariant_within_margin",
    }
    assert expected_columns == set(rows[0].keys())

    # Both detectors x both sources should produce one stratum each.
    keys = {(r["detector"], r["source"]) for r in rows}
    assert keys == {
        (d, s) for d in _DETECTORS for s in _SOURCES
    }


def test_missing_predictions_csv_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run_wilcoxon_tests(tmp_path)
    with pytest.raises(FileNotFoundError):
        run_t_tests(tmp_path)
    with pytest.raises(FileNotFoundError):
        run_encryption_invariance(tmp_path)
