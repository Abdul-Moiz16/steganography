from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.evaluation.plots import generate_metrics_figures


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _seed_plot_inputs(root: Path) -> tuple[Path, Path]:
    metrics_dir = root / "metrics"
    predictions_dir = root / "predictions"
    figures_dir = root / "figures"
    metrics_dir.mkdir(parents=True)
    predictions_dir.mkdir(parents=True)

    _write_csv(
        metrics_dir / "source_metrics.csv",
        [
            {"detector": detector, "source": source, "roc_auc": auc}
            for detector in ("chi", "rs")
            for source, auc in (("real", 0.92), ("ml_a", 0.82), ("ml_b", 0.78))
        ],
        ["detector", "source", "roc_auc"],
    )
    _write_csv(
        metrics_dir / "condition_metrics.csv",
        [
            {
                "detector": detector,
                "method": method,
                "payload_level": payload,
                "encryption": "plain",
                "roc_auc": auc,
            }
            for detector in ("chi", "rs")
            for method, auc in (("lsb", 0.86), ("dct", 0.81))
            for payload in ("low", "medium")
        ],
        ["detector", "method", "payload_level", "encryption", "roc_auc"],
    )
    _write_csv(
        metrics_dir / "quality_metrics.csv",
        [
            {
                "group_id": group_id,
                "source": "real",
                "method": method,
                "payload_level": payload,
                "encryption": "plain",
                "psnr": 42.0 - group_id,
                "ssim": 0.99,
                "fsim": "",
            }
            for group_id in range(1, 4)
            for method in ("lsb", "dct")
            for payload in ("low", "medium")
        ],
        ["group_id", "source", "method", "payload_level", "encryption", "psnr", "ssim", "fsim"],
    )

    prediction_rows: list[dict] = []
    for detector in ("chi", "rs"):
        for method in ("lsb", "dct"):
            for payload in ("low", "medium"):
                for group_id in range(1, 9):
                    for source, base in (("real", 0.44), ("ml_a", 0.36), ("ml_b", 0.32)):
                        for encryption, enc_delta in (("plain", 0.0), ("encrypted", 0.005)):
                            for label, offset in ((0, 0.0), (1, 0.34)):
                                prediction_rows.append(
                                    {
                                        "detector": detector,
                                        "group_id": group_id,
                                        "source": source,
                                        "method": method,
                                        "payload_level": payload,
                                        "encryption": encryption,
                                        "label": label,
                                        "score": base + enc_delta + offset + group_id * 0.01,
                                    }
                                )
    _write_csv(
        predictions_dir / "predictions.csv",
        prediction_rows,
        ["detector", "group_id", "source", "method", "payload_level", "encryption", "label", "score"],
    )
    return metrics_dir, figures_dir


def test_generate_metrics_figures_writes_report_and_support_outputs(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    metrics_dir, figures_dir = _seed_plot_inputs(tmp_path)

    outputs = generate_metrics_figures(metrics_dir, figures_dir)

    expected_figures = {
        "auc_by_source_detector.png",
        "auc_by_method_detector.png",
        "exp1_real_vs_pooled_ml.png",
        "exp2_mla_vs_mlb.png",
        "exp3a_payload_level_auc.png",
        "exp3b_bd_sens.png",
        "exp4_spatial_vs_frequency.png",
        "exp5_encryption_effect.png",
        "roc_condition_panels.png",
        "quality_summary.png",
    }
    assert expected_figures <= {path.name for path in figures_dir.iterdir()}
    assert {"exp1_contrasts", "exp2_contrasts", "exp5_contrasts"} <= set(outputs)
    assert (metrics_dir / "source_condition_metrics.csv").exists()


def test_confirmatory_contrast_tables_include_holm_adjustment(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    metrics_dir, figures_dir = _seed_plot_inputs(tmp_path)

    generate_metrics_figures(metrics_dir, figures_dir)

    exp1_rows = list(csv.DictReader((metrics_dir / "exp1_rq1_real_vs_pooled_ml_contrasts.csv").open()))
    exp2_rows = list(csv.DictReader((metrics_dir / "exp2_rq2_mla_vs_mlb_contrasts.csv").open()))

    assert exp1_rows
    assert exp2_rows
    assert {"p_holm", "significant_holm_0_05"} <= set(exp1_rows[0])
    assert {"p_holm", "significant_holm_0_05"} <= set(exp2_rows[0])
