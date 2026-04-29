from __future__ import annotations

import csv
import random
from pathlib import Path

import pytest

from src.evaluation.plots import generate_metrics_figures


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# Per-stratum AUC targets used to generate noisy, separable test scores.
# Values are calibrated so plots show real spread (not all 1.0 / not all 0.5).
_DETECTOR_BIAS = {"chi": 0.05, "rs": -0.02, "sample_pairs": -0.05}
_SOURCE_BIAS = {"real": 0.10, "ml_a": -0.04, "ml_b": -0.07}
_METHOD_BIAS = {"lsb": 0.04, "dct": -0.03}
_PAYLOAD_BIAS = {"low": -0.06, "medium": 0.0, "high": 0.05, "bd_sens": 0.08}
_ENC_PENALTY = {"plain": 0.0, "encrypted": 0.025}


def _seed_plot_inputs(root: Path) -> tuple[Path, Path]:
    metrics_dir = root / "metrics"
    predictions_dir = root / "predictions"
    figures_dir = root / "figures"
    metrics_dir.mkdir(parents=True)
    predictions_dir.mkdir(parents=True)

    detectors = ("chi", "rs", "sample_pairs")
    sources = ("real", "ml_a", "ml_b")
    methods = ("lsb", "dct")
    payloads = ("low", "medium", "high")
    encryptions = ("plain", "encrypted")

    rng = random.Random(20260429)

    def stratum_auc(detector: str, source: str, method: str,
                    payload: str, encryption: str) -> float:
        base = (
            0.78
            + _DETECTOR_BIAS.get(detector, 0.0)
            + _SOURCE_BIAS.get(source, 0.0)
            + _METHOD_BIAS.get(method, 0.0)
            + _PAYLOAD_BIAS.get(payload, 0.0)
            - _ENC_PENALTY.get(encryption, 0.0)
        )
        return max(0.55, min(0.97, base))

    _write_csv(
        metrics_dir / "source_metrics.csv",
        [
            {
                "detector": detector,
                "source": source,
                "roc_auc": round(
                    sum(
                        stratum_auc(detector, source, m, p, "plain")
                        for m in methods for p in payloads
                    ) / (len(methods) * len(payloads)),
                    3,
                ),
            }
            for detector in detectors
            for source in sources
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
                "roc_auc": round(
                    sum(
                        stratum_auc(detector, s, method, payload, "plain")
                        for s in sources
                    ) / len(sources),
                    3,
                ),
            }
            for detector in detectors
            for method in methods
            for payload in payloads
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
                "psnr": round(
                    44.0 - (1.5 if method == "dct" else 0.0)
                    - {"low": 0, "medium": 1.2, "high": 2.4}[payload]
                    + rng.uniform(-0.3, 0.3),
                    3,
                ),
                "ssim": round(
                    0.985 - (0.004 if method == "dct" else 0.0)
                    - {"low": 0.001, "medium": 0.004, "high": 0.008}[payload]
                    - rng.uniform(0.0, 0.003),
                    4,
                ),
                "fsim": round(
                    0.992 - (0.005 if method == "dct" else 0.0)
                    - {"low": 0.001, "medium": 0.003, "high": 0.006}[payload]
                    - rng.uniform(0.0, 0.0025),
                    4,
                ),
            }
            for group_id in range(1, 6)
            for method in methods
            for payload in payloads
        ],
        ["group_id", "source", "method", "payload_level", "encryption", "psnr", "ssim", "fsim"],
    )

    prediction_rows: list[dict] = []

    # Strata that vary across all five experimental factors. Scores are
    # generated as Gaussian draws around stratum-specific means so AUCs land
    # close to ``stratum_auc`` rather than collapsing to 1.0.
    n_per_label = 16
    sigma = 0.18

    def _emit(group_id: int, detector: str, source: str, method: str,
              payload: str, encryption: str) -> None:
        target_auc = stratum_auc(detector, source, method, payload, encryption)
        # mu_pos − mu_neg chosen so that AUC ≈ Φ((mu_pos − mu_neg) / (σ√2))
        # which gives a closed-form separation; we approximate with target.
        sep = max(0.0, (target_auc - 0.5) * 2.0)
        mu_pos = 0.55 + sep * 0.55
        mu_neg = 0.55 - sep * 0.05
        for _ in range(n_per_label):
            score_pos = rng.gauss(mu_pos, sigma)
            score_neg = rng.gauss(mu_neg, sigma)
            prediction_rows.append({
                "detector": detector, "group_id": group_id,
                "source": source, "method": method,
                "payload_level": payload, "encryption": encryption,
                "label": 1, "score": round(score_pos, 5),
            })
            prediction_rows.append({
                "detector": detector, "group_id": group_id,
                "source": source, "method": method,
                "payload_level": payload, "encryption": encryption,
                "label": 0, "score": round(score_neg, 5),
            })

    for detector in detectors:
        for method in methods:
            for payload in payloads:
                for source in sources:
                    for encryption in encryptions:
                        _emit(1, detector, source, method, payload, encryption)

    # Dedicated BD-Sens block (k=2, high bit-depth) on the LSB branch only.
    for detector in detectors:
        for source in sources:
            for encryption in encryptions:
                _emit(2, detector, source, "lsb", "bd_sens", encryption)

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
        "exp5_source_x_encryption.png",
        "quality_summary.png",
    }
    file_names = {path.name for path in figures_dir.iterdir() if path.is_file()}
    assert expected_figures <= file_names
    assert {"exp1_contrasts", "exp2_contrasts", "exp5_contrasts"} <= set(outputs)
    assert (metrics_dir / "source_condition_metrics.csv").exists()

    # Per-condition ROC curves are split into individual files now.
    panels_dir = figures_dir / "roc_panels"
    assert panels_dir.is_dir()
    panel_pngs = list(panels_dir.glob("*.png"))
    assert len(panel_pngs) >= 4, panel_pngs
    assert outputs.get("roc_panels_dir") == panels_dir

    # Exp 1 / Exp 2 each emit one overview + one PNG per detector.
    for exp in ("exp1_panels", "exp2_panels"):
        exp_dir = figures_dir / exp
        assert exp_dir.is_dir(), exp_dir
        per_det = list(exp_dir.glob("*.png"))
        assert len(per_det) >= 2, (exp, per_det)
    assert outputs.get("exp1_panels_dir") == figures_dir / "exp1_panels"
    assert outputs.get("exp2_panels_dir") == figures_dir / "exp2_panels"


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
