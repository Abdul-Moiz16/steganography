from __future__ import annotations

"""Figure generation from computed metrics tables."""

import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        return [dict(r) for r in csv.DictReader(f)]


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _maybe_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _write_placeholder_plot(path: Path, title: str, reason: str) -> None:
    fig = plt.figure(figsize=(10, 4))
    ax = fig.add_subplot(111)
    ax.axis("off")
    ax.text(0.5, 0.62, title, ha="center", va="center", fontsize=14,
            fontweight="bold", transform=ax.transAxes)
    ax.text(0.5, 0.38, reason, ha="center", va="center", fontsize=10,
            style="italic", transform=ax.transAxes, wrap=True,
            color="#555555")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _delong_components(
    scores_pos: list[float],
    scores_neg: list[float],
) -> tuple[float | None, np.ndarray | None, np.ndarray | None]:
    """Compute AUC and DeLong structural components V10 and V01.

    V10[i] = fraction of negatives beaten by positive i.
    V01[j] = fraction of positives that beat negative j.
    """
    X = np.array(scores_pos, dtype=float)
    Y = np.array(scores_neg, dtype=float)
    m, n = len(X), len(Y)
    if m < 2 or n < 2:
        return None, None, None
    V10 = np.array([np.mean(xi > Y) + 0.5 * np.mean(xi == Y) for xi in X])
    V01 = np.array([np.mean(X > yj) + 0.5 * np.mean(X == yj) for yj in Y])
    return float(np.mean(V10)), V10, V01


def _delong_var(V10: np.ndarray, V01: np.ndarray) -> float:
    """Variance of the AUC estimator (DeLong 1988)."""
    m, n = len(V10), len(V01)
    s10 = float(np.var(V10, ddof=1)) / m if m > 1 else 0.0
    s01 = float(np.var(V01, ddof=1)) / n if n > 1 else 0.0
    return s10 + s01


def _delong_compare(
    pos_a: list[float],
    neg_a: list[float],
    pos_b: list[float],
    neg_b: list[float],
    *,
    paired: bool = False,
    z_crit: float = 1.96,
) -> dict:
    """DeLong test: AUC_A - AUC_B with 95% CI.

    paired=True  : shared negative cases (same covers); covariance is used.
    paired=False : independent samples (different source groups).

    Returns keys: auc_a, auc_b, diff, se, ci_lo, ci_hi, z, p.
    """
    auc_a, V10_a, V01_a = _delong_components(pos_a, neg_a)
    auc_b, V10_b, V01_b = _delong_components(pos_b, neg_b)
    _nan = dict(auc_a=auc_a, auc_b=auc_b, diff=None, se=None,
                ci_lo=None, ci_hi=None, z=None, p=None)
    if auc_a is None or auc_b is None:
        return _nan

    var_a = _delong_var(V10_a, V01_a)
    var_b = _delong_var(V10_b, V01_b)
    cov = 0.0

    if paired:
        # Covariance contribution from shared structural components.
        # V10: stego scores differ between conditions → compute sample cov if lengths match.
        # V01: cover scores are identical (same physical images) → cov = var.
        if len(V10_a) == len(V10_b):
            m = len(V10_a)
            cov_10 = float(np.cov(V10_a, V10_b)[0, 1]) / m if m > 1 else 0.0
        else:
            cov_10 = 0.0
        if len(V01_a) == len(V01_b):
            n = len(V01_a)
            cov_01 = float(np.cov(V01_a, V01_b)[0, 1]) / n if n > 1 else 0.0
        else:
            cov_01 = 0.0
        cov = cov_10 +cov_01

    var_diff = max(var_a + var_b - 2.0 * cov, 0.0)
    se = float(np.sqrt(var_diff))
    diff = auc_a - auc_b
    ci_lo = diff - z_crit * se
    ci_hi = diff + z_crit * se

    if se > 1e-12:
        z_val = diff / se
        p_val = float(2.0 * (1.0 - stats.norm.cdf(abs(z_val))))
    else:
        z_val = 0.0
        p_val = 1.0  # no difference is detected

    return dict(auc_a=auc_a, auc_b=auc_b, diff=diff, se=se, ci_lo=ci_lo, ci_hi=ci_hi, z=z_val, p=p_val)


def _load_predictions(predictions_path: Path) -> list[dict]:
    """Load predictions.csv and return typed rows sorted by group_id."""
    rows = _read_csv_rows(predictions_path)
    result = []
    for r in rows:
        score = _maybe_float(r.get("score"))
        label_raw = _maybe_float(r.get("label"))
        if score is None or label_raw is None:
            continue
        result.append({
            "detector": r.get("detector", ""),
            "group_id": int(r.get("group_id", 0)),
            "source": r.get("source", ""),
            "method": r.get("method", ""),
            "payload_level": r.get("payload_level", ""),
            "encryption": r.get("encryption", ""),
            "label": int(label_raw),
            "score": score,
        })
    result.sort(key=lambda r: (r["group_id"], r["detector"], r["source"],
                                r["method"], r["payload_level"], r["encryption"],
                                r["label"]))
    return result


def _filter_preds(rows: list[dict], **kwargs) -> list[dict]:
    """Return rows matching all supplied key=value pairs."""
    result = rows
    for key, val in kwargs.items():
        if val is not None:
            result = [r for r in result if r.get(key) == val]
    return result


def _pos_neg(rows: list[dict]) -> tuple[list[float], list[float]]:
    pos = [r["score"] for r in rows if r["label"] == 1]
    neg = [r["score"] for r in rows if r["label"] == 0]
    return pos, neg


def _ensure_source_condition_metrics(metrics_dir: Path, predictions: list[dict]) -> Path:
    """Write source_condition_metrics.csv (per detector x source x method x payload x encryption)."""
    out_path = metrics_dir / "source_condition_metrics.csv"

    strata = sorted({
        (r["detector"], r["source"], r["method"], r["payload_level"], r["encryption"])
        for r in predictions
    })

    rows: list[dict] = []
    for detector, source, method, payload_level, encryption in strata:
        subset = _filter_preds(
            predictions,
            detector=detector, source=source,
            method=method, payload_level=payload_level,
            encryption=encryption,
        )
        pos, neg = _pos_neg(subset)
        auc, V10, V01 = _delong_components(pos, neg)
        if auc is None:
            continue
        var_auc = _delong_var(V10, V01)
        se = float(np.sqrt(max(var_auc, 0.0)))
        rows.append({
            "detector": detector,
            "source": source,
            "method": method,
            "payload_level": payload_level,
            "encryption": encryption,
            "n_samples": len(pos) + len(neg),
            "n_pos": len(pos),
            "n_neg": len(neg),
            "roc_auc": round(auc, 6),
            "auc_se": round(se, 6),
            "ci_lower": round(auc - 1.96 * se, 6),
            "ci_upper": round(auc + 1.96 * se, 6),
        })

    _write_csv(out_path, rows)
    return out_path


def _forest_plot(
    ax,
    results: list[dict],
    xlabel: str,
    *,
    color: str = "steelblue",
    sig_color: str = "firebrick",
) -> None:
    """Draw a horizontal forest plot on *ax* from a list of DeLong result dicts.
    Each dict must have keys: label, diff, ci_lo, ci_hi, auc_a, auc_b, p.
    """
    x_values: list[float] = []

    for i, r in enumerate(results):
        if r.get("diff") is None:
            ax.text(0.0, i, "N/A  (< 2 samples)", ha="center", va="center",
                    fontsize=8, color="gray")
            continue

        c = sig_color if (r.get("p") is not None and r["p"] < 0.05) else color
        ci_lo, ci_hi, diff = r["ci_lo"], r["ci_hi"], r["diff"]

        ax.plot([ci_lo, ci_hi], [i, i], color=c, linewidth=2.5, solid_capstyle="butt")
        ax.plot(diff, i, "s", color=c, markersize=7, zorder=5)

        x_values.extend([ci_lo, ci_hi])

        p_str = f"p={r['p']:.3f}" if r.get("p") is not None else ""
        a_str = (f"AUC_A={r['auc_a']:.3f}  AUC_B={r['auc_b']:.3f}"
                 if r.get("auc_a") is not None else "")
        annot = f"Δ={diff:+.3f}  [{ci_lo:+.3f}, {ci_hi:+.3f}]  {p_str}"
        ax.annotate(
            annot,
            xy=(ci_hi, i), xytext=(7, 0), textcoords="offset points",
            va="center", fontsize=7.5, clip_on=False,
        )

    ax.axvline(0, color="gray", linestyle="--", linewidth=1, alpha=0.7, zorder=1)
    ax.set_yticks(list(range(len(results))))
    ax.set_yticklabels([r.get("label", str(i)) for i, r in enumerate(results)], fontsize=9)
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylim(-0.7, len(results) - 0.3)
    ax.grid(axis="x", alpha=0.25)

    if x_values:
        span = max(x_values) - min(x_values)
        pad = max(span * 0.15, 0.05)
        ax.set_xlim(min(x_values) - pad, max(x_values) + pad + span * 0.45)


# Actual plot design

def _plot_exp1(predictions: list[dict], figures_dir: Path) -> Path:
    """Exp 1: Real vs. pooled ML AUC per (detector, method, payload_level).
    DeLong test (independent), 95% CI. Pooled across encryption conditions.
    """
    out_path = figures_dir / "exp1_real_vs_pooled_ml.png"

    detectors = sorted({r["detector"] for r in predictions})
    strata = sorted({(r["method"], r["payload_level"]) for r in predictions})

    results = []
    for detector in detectors:
        for method, payload_level in strata:
            real_rows = _filter_preds(predictions, detector=detector, source="real",
                                      method=method, payload_level=payload_level)
            ml_rows = (
                _filter_preds(predictions, detector=detector, source="ml_a",
                              method=method, payload_level=payload_level)
                + _filter_preds(predictions, detector=detector, source="ml_b",
                                method=method, payload_level=payload_level)
            )
            if not real_rows or not ml_rows:
                continue

            stat = _delong_compare(*_pos_neg(real_rows), *_pos_neg(ml_rows), paired=False)
            results.append({
                "label": f"{detector}  ({method}, {payload_level})",
                **stat,
            })

    if not results:
        _write_placeholder_plot(out_path, "Exp 1: Real vs. Pooled ML",
                                "No prediction data available.")
        return out_path

    fig, ax = plt.subplots(figsize=(11, max(3.5, len(results) * 1.15 + 1.5)))
    _forest_plot(ax, results, "AUC Difference  (Real − Pooled ML)", color="steelblue")
    ax.set_title(
        "Exp 1 — Real vs. Pooled ML AUC  (DeLong test, 95% CI)\n"
        "Red = significant p < 0.05 · pooled across encryption conditions",
        fontsize=11, fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path




def _plot_exp2(predictions: list[dict], figures_dir: Path) -> Path:
    """Exp 2: Caption-matched ML-A vs. ML-B AUC per (detector, method, payload_level).
    DeLong test (independent), 95% CI. Pooled across encryption conditions.
    """
    out_path = figures_dir / "exp2_mla_vs_mlb.png"

    detectors = sorted({r["detector"] for r in predictions})
    strata = sorted({(r["method"], r["payload_level"]) for r in predictions})

    results = []
    for detector in detectors:
        for method, payload_level in strata:
            ml_a_rows = _filter_preds(predictions, detector=detector, source="ml_a",
                                      method=method, payload_level=payload_level)
            ml_b_rows = _filter_preds(predictions, detector=detector, source="ml_b",
                                      method=method, payload_level=payload_level)
            if not ml_a_rows or not ml_b_rows:
                continue

            stat = _delong_compare(*_pos_neg(ml_a_rows), *_pos_neg(ml_b_rows), paired=False)
            results.append({
                "label": f"{detector}  ({method}, {payload_level})",
                **stat,
            })

    if not results:
        _write_placeholder_plot(out_path, "Exp 2: ML-A vs. ML-B",
                                "No prediction data available.")
        return out_path

    fig, ax = plt.subplots(figsize=(11, max(3.5, len(results) * 1.15 + 1.5)))
    _forest_plot(ax, results, "AUC Difference  (ML-A − ML-B)", color="darkorange")
    ax.set_title(
        "Exp 2 — Caption-Matched ML-A vs. ML-B AUC  (DeLong test, 95% CI)\n"
        "Red = significant p < 0.05 · pooled across encryption conditions",
        fontsize=11, fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path




def _plot_exp3a(predictions: list[dict], figures_dir: Path) -> Path:
    """Exp 3a: AUC and source-contrast gaps across Low/Medium/High payload levels.
    Top row: AUC per source per detector (±95% CI).
    Bottom row: source-contrast gap = AUC_real − mean(AUC_ml_a, AUC_ml_b).
    """
    out_path = figures_dir / "exp3a_payload_level_auc.png"

    PAYLOAD_ORDER = ["low", "medium", "high"]
    available = sorted(
        {r["payload_level"] for r in predictions},
        key=lambda x: PAYLOAD_ORDER.index(x) if x in PAYLOAD_ORDER else 99,
    )
    detectors = sorted({r["detector"] for r in predictions})
    sources = sorted({r["source"] for r in predictions})

    if not available:
        _write_placeholder_plot(out_path, "Exp 3a: Payload Level AUC", "No data.")
        return out_path

    auc_data: dict[tuple, float] = {}
    se_data: dict[tuple, float] = {}
    for detector in detectors:
        for source in sources:
            for pl in available:
                rows = _filter_preds(predictions, detector=detector,
                                     source=source, payload_level=pl)
                pos, neg = _pos_neg(rows)
                auc, V10, V01 = _delong_components(pos, neg)
                if auc is not None:
                    auc_data[(detector, source, pl)] = auc
                    se_data[(detector, source, pl)] = float(
                        np.sqrt(max(_delong_var(V10, V01), 0.0))
                    )

    if not auc_data:
        _write_placeholder_plot(out_path, "Exp 3a: Payload Level AUC", "Insufficient data.")
        return out_path

    SOURCE_COLORS = {"real": "#1f77b4", "ml_a": "#ff7f0e", "ml_b": "#2ca02c"}
    SOURCE_MARKERS = {"real": "o", "ml_a": "s", "ml_b": "^"}
    n_det = len(detectors)
    x_ticks = list(range(len(available)))

    fig, axes = plt.subplots(
        2, n_det,
        figsize=(5 * n_det + 1, 9),
        sharex="col",
        gridspec_kw={"height_ratios": [2, 1]},
    )
    #ensure 2D indexing even with a single detector.
    if n_det == 1:
        axes = axes.reshape(2, 1)

    # top row: AUC per source 
    for col, detector in enumerate(detectors):
        ax = axes[0, col]
        for source in sources:
            aucs = [auc_data.get((detector, source, pl)) for pl in available]
            ses = [se_data.get((detector, source, pl), 0.0) for pl in available]
            valid = [(xi, a, s) for xi, a, s in zip(x_ticks, aucs, ses) if a is not None]
            if valid:
                xv, av, sv = zip(*valid)
                ax.errorbar(
                    xv, av,
                    yerr=[1.96 * s for s in sv],
                    marker=SOURCE_MARKERS.get(source, "o"),
                    color=SOURCE_COLORS.get(source, "gray"),
                    label=source, linewidth=2, markersize=8, capsize=4,
                )
        ax.set_ylim(0, 1.08)
        ax.set_title(detector, fontsize=10, fontweight="bold")
        ax.grid(alpha=0.3)
        if col == 0:
            ax.set_ylabel("ROC-AUC  (±95% CI)", fontsize=9)
        ax.legend(title="Source", fontsize=7, title_fontsize=8)

    # bottom row: source-contrast gap 
    for col, detector in enumerate(detectors):
        ax = axes[1, col]
        gaps, gap_labels = [], []
        for pl in available:
            real_auc = auc_data.get((detector, "real", pl))
            ml_aucs = [
                auc_data.get((detector, src, pl))
                for src in ("ml_a", "ml_b")
                if auc_data.get((detector, src, pl)) is not None
            ]
            if real_auc is None or not ml_aucs:
                gaps.append(None)
            else:
                gaps.append(real_auc - mean(ml_aucs))
            gap_labels.append(pl)

        valid = [(xi, g) for xi, g in zip(x_ticks, gaps) if g is not None]
        if valid:
            xv, gv = zip(*valid)
            ax.bar(xv, gv, color="slategray", alpha=0.75, width=0.4)
            ax.axhline(0, color="black", linewidth=0.8)
        ax.set_xticks(x_ticks)
        ax.set_xticklabels(available)
        ax.set_xlabel("Payload Level", fontsize=9)
        ax.grid(axis="y", alpha=0.3)
        if col == 0:
            ax.set_ylabel("Gap  (AUC_real − AUC_ml)", fontsize=9)

    note = ""
    if set(available) == {"low"}:
        note = ("\n[Prototype data: only 'low' payload level present. "
                "Full design adds medium & high.]")

    fig.suptitle(
        f"Exp 3a — AUC and Source-Contrast Gaps Across Payload Levels{note}",
        fontsize=11, fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path



def _plot_exp3b(predictions: list[dict], figures_dir: Path) -> Path:
    """Exp 3b: BD-Sens (k=2, 1.50 bpp) carrier-source amplification analysis."""

    out_path = figures_dir / "exp3b_bd_sens.png"

    bd_rows = [r for r in predictions if r.get("payload_level") == "bd_sens"]
    if not bd_rows:
        _write_placeholder_plot(
            out_path,
            "Exp 3b — BD-Sens Analysis  (k=2, 1.50 bpp)",
            "No BD-Sens data in prototype run.\n"
            "Requires full design with k=2 bit-plane embedding (primary_lsb_bit_depth=2).",
        )
    return out_path




def _plot_exp4(predictions: list[dict], figures_dir: Path) -> Path:
    """Exp 4: Spatial (LSB+PNG) vs. frequency (DCT-LSB+JPEG) carrier-source AUC gaps."""
    out_path = figures_dir / "exp4_spatial_vs_frequency.png"

    methods = {r["method"] for r in predictions}
    spatial = {m for m in methods if "lsb" in m.lower() and "dct" not in m.lower()}
    frequency = {m for m in methods if "dct" in m.lower()}

    if not spatial or not frequency:
        missing = []
        if not spatial:
            missing.append("spatial  (LSB+PNG)")
        if not frequency:
            missing.append("frequency  (DCT-LSB+JPEG)")
        _write_placeholder_plot(
            out_path,
            "Exp 4 — Spatial vs. Frequency Branch AUC",
            f"Missing branch data: {', '.join(missing)}.\n"
            "Prototype run includes only the LSB+PNG spatial branch.\n"
            "Full design required for DCT-LSB+JPEG frequency branch.",
        )
        return out_path

    # Full-design execution path (active once DCT data is available).
    detectors = sorted({r["detector"] for r in predictions})
    sources = sorted({r["source"] for r in predictions})
    sp_method = next(iter(sorted(spatial)))
    fr_method = next(iter(sorted(frequency)))

    results = []
    for detector in detectors:
        for source in sources:
            sp_rows = _filter_preds(predictions, detector=detector,
                                    source=source, method=sp_method)
            fr_rows = _filter_preds(predictions, detector=detector,
                                    source=source, method=fr_method)
            if not sp_rows or not fr_rows:
                continue
            stat = _delong_compare(*_pos_neg(sp_rows), *_pos_neg(fr_rows), paired=False)
            results.append({"label": f"{detector}  /  {source}", **stat})

    if not results:
        _write_placeholder_plot(out_path, "Exp 4: Spatial vs. Frequency", "No data.")
        return out_path

    fig, ax = plt.subplots(figsize=(11, max(3.5, len(results) * 1.1 + 1.5)))
    _forest_plot(ax, results, "AUC Difference  (Spatial - Frequency)", color="mediumpurple")
    ax.set_title(
        "Exp 4 — Spatial (LSB+PNG) vs. Frequency (DCT-LSB+JPEG) Branch AUC  (DeLong, 95% CI)",
        fontsize=11, fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path



def _plot_exp5(predictions: list[dict], figures_dir: Path) -> Path:
    """Exp 5: Plain vs. AES-256-CBC — detectability sanity check (expect Δ ≈ 0).
    Left panel : forest plot of AUC differences (paired DeLong, 95% CI).
    Right panel: grouped bar of mean AUC (plain vs. encrypted) per detector.
    """
    out_path = figures_dir / "exp5_encryption_effect.png"

    encryptions = {r["encryption"] for r in predictions}
    if "plain" not in encryptions or "encrypted" not in encryptions:
        _write_placeholder_plot(
            out_path, "Exp 5 — Encryption Effect",
            "Both 'plain' and 'encrypted' conditions are required.",
        )
        return out_path

    detectors = sorted({r["detector"] for r in predictions})
    sources = sorted({r["source"] for r in predictions})

    results = []
    for detector in detectors:
        for source in sources:
            plain_rows = _filter_preds(predictions, detector=detector,
                                       source=source, encryption="plain")
            enc_rows = _filter_preds(predictions, detector=detector,
                                     source=source, encryption="encrypted")
            if not plain_rows or not enc_rows:
                continue
            # Paired: both conditions share the same cover images (same negatives).
            stat = _delong_compare(
                *_pos_neg(plain_rows), *_pos_neg(enc_rows), paired=True
            )
            results.append({
                "label": f"{detector}  /  {source}",
                "detector": detector,
                "source": source,
                **stat,
            })

    if not results:
        _write_placeholder_plot(out_path, "Exp 5 — Encryption Effect", "No data.")
        return out_path

    fig, (ax_forest, ax_bar) = plt.subplots(
        1, 2,
        figsize=(15, max(4.5, len(results) * 0.75 + 2.5)),
        gridspec_kw={"width_ratios": [1.7, 1]},
    )

    _forest_plot(ax_forest, results, "AUC Difference  (Plain − Encrypted)",
                 color="steelblue", sig_color="firebrick")
    ax_forest.set_title(
        "Paired DeLong test (95% CI)\n"
        "Red = p < 0.05 — unexpected for sanity check",
        fontsize=10,
    )

    det_list = sorted({r["detector"] for r in results})
    x = np.arange(len(det_list))
    width = 0.35

    plain_means, enc_means = [], []
    for det in det_list:
        sub = [r for r in results if r["detector"] == det]
        plain_vals = [r["auc_a"] for r in sub if r.get("auc_a") is not None]
        enc_vals = [r["auc_b"] for r in sub if r.get("auc_b") is not None]
        plain_means.append(mean(plain_vals) if plain_vals else 0.0)
        enc_means.append(mean(enc_vals) if enc_vals else 0.0)

    ax_bar.bar(x - width / 2, plain_means, width,
               label="plain", color="#2196F3", alpha=0.85)
    ax_bar.bar(x + width / 2, enc_means, width,
               label="encrypted", color="#FF9800", alpha=0.85)
    ax_bar.set_xticks(x)
    ax_bar.set_xticklabels(det_list, rotation=20, ha="right", fontsize=9)
    ax_bar.set_ylabel("Mean ROC-AUC  (across sources)")
    ax_bar.set_ylim(0, 1.1)
    ax_bar.set_title("Mean AUC: Plain vs. Encrypted", fontsize=10)
    ax_bar.legend(fontsize=9)
    ax_bar.grid(axis="y", alpha=0.3)

    fig.suptitle(
        "Exp 5 — Encryption Effect on Detectability  (Sanity Check)\n"
        "Expectation: Δ ≈ 0  (AES-256-CBC payloads ≈ uniform random bits)",
        fontsize=12, fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path



def _plot_auc_by_source_detector(source_rows: list[dict], fig_path: Path) -> Path:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    detectors: set[str] = set()
    sources: set[str] = set()

    for row in source_rows:
        auc = _maybe_float(row.get("roc_auc"))
        det = row.get("detector", "")
        src = row.get("source", "")
        if auc is None or not det or not src:
            continue
        detectors.add(det)
        sources.add(src)
        grouped[(det, src)].append(auc)

    if not grouped:
        _write_placeholder_plot(fig_path, "AUC by Source and Detector",
                                "No source_metrics data available.")
        return fig_path

    det_sorted = sorted(detectors)
    src_sorted = sorted(sources)
    x = list(range(len(det_sorted)))
    width = 0.8 / max(len(src_sorted), 1)

    fig, ax = plt.subplots(figsize=(11, 5))
    for i, source in enumerate(src_sorted):
        values = [
            mean(grouped[(det, source)]) if (det, source) in grouped else 0.0
            for det in det_sorted
        ]
        shift = (i - (len(src_sorted) - 1) / 2.0) * width
        ax.bar([v + shift for v in x], values, width=width, label=source)

    ax.set_xticks(x)
    ax.set_xticklabels(det_sorted)
    ax.set_ylim(0.0, 1.0)
    ax.set_ylabel("ROC-AUC")
    ax.set_title("ROC-AUC by Detector and Source")
    ax.legend(title="Source")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(fig_path, dpi=150)
    plt.close(fig)
    return fig_path


def _plot_auc_by_method_detector(condition_rows: list[dict], fig_path: Path) -> Path:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    detectors: set[str] = set()
    methods: set[str] = set()

    for row in condition_rows:
        auc = _maybe_float(row.get("roc_auc"))
        det = row.get("detector", "")
        method = row.get("method", "")
        if auc is None or not det or not method:
            continue
        detectors.add(det)
        methods.add(method)
        grouped[(det, method)].append(auc)

    if not grouped:
        _write_placeholder_plot(fig_path, "AUC by Method and Detector",
                                "No condition_metrics data available.")
        return fig_path

    det_sorted = sorted(detectors)
    method_sorted = sorted(methods)
    x = list(range(len(det_sorted)))
    width = 0.8 / max(len(method_sorted), 1)

    fig, ax = plt.subplots(figsize=(11, 5))
    for i, method in enumerate(method_sorted):
        values = [
            mean(grouped[(det, method)]) if (det, method) in grouped else 0.0
            for det in det_sorted
        ]
        shift = (i - (len(method_sorted) - 1) / 2.0) * width
        ax.bar([v + shift for v in x], values, width=width, label=method)

    ax.set_xticks(x)
    ax.set_xticklabels(det_sorted)
    ax.set_ylim(0.0, 1.0)
    ax.set_ylabel("ROC-AUC")
    ax.set_title("ROC-AUC by Detector and Embedding Method")
    ax.legend(title="Method")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(fig_path, dpi=150)
    plt.close(fig)
    return fig_path


def generate_metrics_figures(metrics_dir: Path, figures_dir: Path) -> dict[str, Path]:
    """Generate all AUC figures for Experiments 1–5 plus overview bar charts.

    Parameters
    ----------
    metrics_dir:
        Path to the run's ``metrics/`` directory (contains *_metrics.csv files).
    figures_dir:
        Directory where PNG figures will be written (created if absent).

    Returns
    -------
    dict mapping figure keys to resolved ``Path`` objects.
    """
    metrics_dir = metrics_dir.resolve()
    figures_dir = figures_dir.resolve()
    figures_dir.mkdir(parents=True, exist_ok=True)

    pred_path = metrics_dir.parent / "predictions" / "predictions.csv"
    if not pred_path.exists():
        pred_path = metrics_dir / "predictions.csv"  # fallback
    predictions = _load_predictions(pred_path) if pred_path.exists() else []

    # Ensure source_condition_metrics.csv is generated / up-to-date.
    if predictions:
        _ensure_source_condition_metrics(metrics_dir, predictions)

    source_rows = _read_csv_rows(metrics_dir / "source_metrics.csv")
    condition_rows = _read_csv_rows(metrics_dir / "condition_metrics.csv")

    figures: dict[str, Path] = {}

    # Overview bar charts.
    figures["auc_by_source_detector"] = _plot_auc_by_source_detector(
        source_rows, figures_dir / "auc_by_source_detector.png"
    )
    figures["auc_by_method_detector"] = _plot_auc_by_method_detector(
        condition_rows, figures_dir / "auc_by_method_detector.png"
    )

    figures["exp1_real_vs_pooled_ml"] = _plot_exp1(predictions, figures_dir)
    figures["exp2_mla_vs_mlb"] = _plot_exp2(predictions, figures_dir)
    figures["exp3a_payload_level"] = _plot_exp3a(predictions, figures_dir)
    figures["exp3b_bd_sens"] = _plot_exp3b(predictions, figures_dir)
    figures["exp4_branch_comparison"] = _plot_exp4(predictions, figures_dir)
    figures["exp5_encryption"] = _plot_exp5(predictions, figures_dir)

    return figures
