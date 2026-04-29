from __future__ import annotations

"""Figure generation from computed metrics tables."""

import csv
from collections import defaultdict
import math
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
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
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


def _holm_adjust(results: list[dict]) -> list[dict]:
    """Add Bonferroni-Holm adjusted p-values to confirmatory result rows."""
    indexed = [
        (idx, r["p"])
        for idx, r in enumerate(results)
        if r.get("p") is not None and not math.isnan(float(r["p"]))
    ]
    indexed.sort(key=lambda item: item[1])
    m = len(indexed)
    adjusted_by_idx: dict[int, float] = {}
    running = 0.0
    for rank, (idx, p_value) in enumerate(indexed, start=1):
        adjusted = min(1.0, (m - rank + 1) * float(p_value))
        running = max(running, adjusted)
        adjusted_by_idx[idx] = running
    for idx, row in enumerate(results):
        p_adj = adjusted_by_idx.get(idx)
        row["p_holm"] = p_adj
        row["significant_holm_0_05"] = bool(p_adj is not None and p_adj <= 0.05)
    return results


def _auc_var_for_rows(rows: list[dict]) -> tuple[float | None, float | None]:
    auc, V10, V01 = _delong_components(*_pos_neg(rows))
    if auc is None:
        return None, None
    return auc, _delong_var(V10, V01)


def _source_gap_stats(
    predictions: list[dict],
    *,
    detector: str,
    method: str,
    payload_level: str,
    encryption: str | None = None,
) -> dict:
    real_rows = _filter_preds(
        predictions,
        detector=detector,
        source="real",
        method=method,
        payload_level=payload_level,
        encryption=encryption,
    )
    ml_rows = (
        _filter_preds(
            predictions,
            detector=detector,
            source="ml_a",
            method=method,
            payload_level=payload_level,
            encryption=encryption,
        )
        + _filter_preds(
            predictions,
            detector=detector,
            source="ml_b",
            method=method,
            payload_level=payload_level,
            encryption=encryption,
        )
    )
    auc_real, var_real = _auc_var_for_rows(real_rows)
    auc_ml, var_ml = _auc_var_for_rows(ml_rows)
    if auc_real is None or auc_ml is None:
        return dict(auc_a=auc_real, auc_b=auc_ml, diff=None, se=None, ci_lo=None, ci_hi=None, z=None, p=None)
    diff = auc_real - auc_ml
    se = math.sqrt(max((var_real or 0.0) + (var_ml or 0.0), 0.0))
    ci_lo = diff - 1.96 * se
    ci_hi = diff + 1.96 * se
    z_val = diff / se if se > 1e-12 else 0.0
    p_value = 2.0 * (1.0 - stats.norm.cdf(abs(z_val))) if se > 1e-12 else 1.0
    return dict(auc_a=auc_real, auc_b=auc_ml, diff=diff, se=se, ci_lo=ci_lo, ci_hi=ci_hi, z=z_val, p=p_value)


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
    _holm_adjust(results)

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
    _holm_adjust(results)

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
    panels = sorted({(r["detector"], r["method"]) for r in predictions})
    sources = sorted({r["source"] for r in predictions})

    if not available:
        _write_placeholder_plot(out_path, "Exp 3a: Payload Level AUC", "No data.")
        return out_path

    auc_data: dict[tuple, float] = {}
    se_data: dict[tuple, float] = {}
    for detector, method in panels:
        for source in sources:
            for pl in available:
                rows = _filter_preds(predictions, detector=detector,
                                     source=source, method=method, payload_level=pl)
                pos, neg = _pos_neg(rows)
                auc, V10, V01 = _delong_components(pos, neg)
                if auc is not None:
                    auc_data[(detector, method, source, pl)] = auc
                    se_data[(detector, method, source, pl)] = float(
                        np.sqrt(max(_delong_var(V10, V01), 0.0))
                    )

    if not auc_data:
        _write_placeholder_plot(out_path, "Exp 3a: Payload Level AUC", "Insufficient data.")
        return out_path

    SOURCE_COLORS = {"real": "#1f77b4", "ml_a": "#ff7f0e", "ml_b": "#2ca02c"}
    SOURCE_MARKERS = {"real": "o", "ml_a": "s", "ml_b": "^"}
    n_det = len(panels)
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
    for col, (detector, method) in enumerate(panels):
        ax = axes[0, col]
        for source in sources:
            aucs = [auc_data.get((detector, method, source, pl)) for pl in available]
            ses = [se_data.get((detector, method, source, pl), 0.0) for pl in available]
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
        ax.set_title(f"{detector} / {method}", fontsize=10, fontweight="bold")
        ax.grid(alpha=0.3)
        if col == 0:
            ax.set_ylabel("ROC-AUC  (±95% CI)", fontsize=9)
        ax.legend(title="Source", fontsize=7, title_fontsize=8)

    # bottom row: source-contrast gap 
    for col, (detector, method) in enumerate(panels):
        ax = axes[1, col]
        gaps, gap_labels = [], []
        for pl in available:
            real_auc = auc_data.get((detector, method, "real", pl))
            ml_aucs = [
                auc_data.get((detector, method, src, pl))
                for src in ("ml_a", "ml_b")
                if auc_data.get((detector, method, src, pl)) is not None
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

    detectors = sorted({r["detector"] for r in bd_rows})
    results = []
    for detector in detectors:
        stat = _source_gap_stats(
            bd_rows,
            detector=detector,
            method="lsb",
            payload_level="bd_sens",
        )
        results.append({"label": detector, **stat})

    if not results or all(r.get("diff") is None for r in results):
        _write_placeholder_plot(out_path, "Exp 3b — BD-Sens Analysis", "Insufficient BD-Sens data.")
        return out_path

    fig, ax = plt.subplots(figsize=(11, max(3.5, len(results) * 0.9 + 1.5)))
    _forest_plot(ax, results, "AUC Gap  (Real − Pooled ML)", color="teal")
    ax.set_title(
        "Exp 3b — Bit-Depth Sensitivity Source Gap  (k=2, 1.50 bpp)",
        fontsize=11,
        fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
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

    # Full-design execution path: compare branch-level source gaps. Spatial and
    # DCT branches use different detector families, so this aggregates the
    # available detector-specific carrier-source gaps within each branch.
    payload_levels = sorted({r["payload_level"] for r in predictions})
    sp_method = next(iter(sorted(spatial)))
    fr_method = next(iter(sorted(frequency)))

    results = []
    for payload_level in payload_levels:
        branch_gaps: dict[str, list[float]] = {sp_method: [], fr_method: []}
        for method in (sp_method, fr_method):
            for detector in sorted({r["detector"] for r in predictions if r["method"] == method}):
                gap = _source_gap_stats(
                    predictions,
                    detector=detector,
                    method=method,
                    payload_level=payload_level,
                )
                if gap.get("diff") is not None:
                    branch_gaps[method].append(gap["diff"])
        if not branch_gaps[sp_method] or not branch_gaps[fr_method]:
            continue

        spatial_mean = mean(branch_gaps[sp_method])
        frequency_mean = mean(branch_gaps[fr_method])
        diff = spatial_mean - frequency_mean
        se_parts = []
        for vals in branch_gaps.values():
            if len(vals) > 1:
                se_parts.append(float(np.std(vals, ddof=1) / math.sqrt(len(vals))))
            else:
                se_parts.append(0.0)
        se = math.sqrt(sum(part * part for part in se_parts))
        ci_lo = diff - 1.96 * se
        ci_hi = diff + 1.96 * se
        z_val = diff / se if se > 1e-12 else 0.0
        p_value = 2.0 * (1.0 - stats.norm.cdf(abs(z_val))) if se > 1e-12 else 1.0
        results.append({
            "label": payload_level,
            "auc_a": spatial_mean,
            "auc_b": frequency_mean,
            "diff": diff,
            "se": se,
            "ci_lo": ci_lo,
            "ci_hi": ci_hi,
            "z": z_val,
            "p": p_value,
        })

    if not results:
        for detector in sorted({r["detector"] for r in predictions}):
            for payload_level in payload_levels:
                # Fallback for future configurations that reuse detector names
                # across branches.
                sp_gap = _source_gap_stats(
                    predictions,
                    detector=detector,
                    method=sp_method,
                    payload_level=payload_level,
                )
                fr_gap = _source_gap_stats(
                    predictions,
                    detector=detector,
                    method=fr_method,
                    payload_level=payload_level,
                )
                if sp_gap.get("diff") is None or fr_gap.get("diff") is None:
                    continue
                diff = sp_gap["diff"] - fr_gap["diff"]
                se = math.sqrt(max((sp_gap.get("se") or 0.0) ** 2 + (fr_gap.get("se") or 0.0) ** 2, 0.0))
                ci_lo = diff - 1.96 * se
                ci_hi = diff + 1.96 * se
                z_val = diff / se if se > 1e-12 else 0.0
                p_value = 2.0 * (1.0 - stats.norm.cdf(abs(z_val))) if se > 1e-12 else 1.0
                results.append({
                    "label": f"{detector}  /  {payload_level}",
                    "auc_a": sp_gap["diff"],
                    "auc_b": fr_gap["diff"],
                    "diff": diff,
                    "se": se,
                    "ci_lo": ci_lo,
                    "ci_hi": ci_hi,
                    "z": z_val,
                    "p": p_value,
                })

    if not results:
        _write_placeholder_plot(out_path, "Exp 4: Spatial vs. Frequency", "No data.")
        return out_path

    fig, ax = plt.subplots(figsize=(11, max(3.5, len(results) * 1.1 + 1.5)))
    _forest_plot(ax, results, "Difference in Source Gap  (Spatial − Frequency)", color="mediumpurple")
    ax.set_title(
        "Exp 4 — Carrier-Source Gap by Embedding Branch  (Exploratory, 95% CI)",
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
            for method in sorted({r["method"] for r in predictions}):
                for payload_level in sorted({r["payload_level"] for r in predictions}):
                    plain_rows = _filter_preds(
                        predictions,
                        detector=detector,
                        source=source,
                        method=method,
                        payload_level=payload_level,
                        encryption="plain",
                    )
                    enc_rows = _filter_preds(
                        predictions,
                        detector=detector,
                        source=source,
                        method=method,
                        payload_level=payload_level,
                        encryption="encrypted",
                    )
                    if not plain_rows or not enc_rows:
                        continue
                    stat = _delong_compare(
                        *_pos_neg(plain_rows), *_pos_neg(enc_rows), paired=True
                    )
                    results.append({
                        "label": f"{detector} / {source} / {method} / {payload_level}",
                        "detector": detector,
                        "source": source,
                        "method": method,
                        "payload_level": payload_level,
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


def _roc_curve_points(rows: list[dict]) -> tuple[list[float], list[float]]:
    labels = [r["label"] for r in rows]
    scores = [r["score"] for r in rows]
    if len(set(labels)) < 2:
        return [], []
    thresholds = sorted(set(scores), reverse=True)
    thresholds = [thresholds[0] + 1.0] + thresholds + [thresholds[-1] - 1.0]
    n_pos = sum(1 for y in labels if y == 1)
    n_neg = sum(1 for y in labels if y == 0)
    fprs: list[float] = []
    tprs: list[float] = []
    for threshold in thresholds:
        tp = fp = 0
        for label, score in zip(labels, scores):
            pred_pos = score >= threshold
            tp += int(label == 1 and pred_pos)
            fp += int(label == 0 and pred_pos)
        tprs.append(tp / n_pos if n_pos else 0.0)
        fprs.append(fp / n_neg if n_neg else 0.0)
    return fprs, tprs


def _plot_roc_condition_panels(predictions: list[dict], figures_dir: Path) -> Path:
    out_path = figures_dir / "roc_condition_panels.png"
    strata = sorted({
        (r["detector"], r["method"], r["payload_level"], r["encryption"])
        for r in predictions
    })
    if not strata:
        _write_placeholder_plot(out_path, "Condition ROC Panels", "No prediction data available.")
        return out_path

    n_cols = min(3, max(1, len(strata)))
    n_rows = math.ceil(len(strata) / n_cols)
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(5.2 * n_cols, 4.2 * n_rows), squeeze=False)
    source_colors = {"real": "#1f77b4", "ml_a": "#ff7f0e", "ml_b": "#2ca02c"}

    for ax, (detector, method, payload_level, encryption) in zip(axes.ravel(), strata):
        for source in ("real", "ml_a", "ml_b"):
            rows = _filter_preds(
                predictions,
                detector=detector,
                method=method,
                payload_level=payload_level,
                encryption=encryption,
                source=source,
            )
            fprs, tprs = _roc_curve_points(rows)
            if fprs:
                auc, _var = _auc_var_for_rows(rows)
                label = f"{source} (AUC={auc:.3f})" if auc is not None else source
                ax.plot(fprs, tprs, label=label, color=source_colors.get(source))
        ax.plot([0, 1], [0, 1], color="gray", linestyle="--", linewidth=0.8)
        ax.set_title(f"{detector}\n{method} / {payload_level} / {encryption}", fontsize=9)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.grid(alpha=0.25)
        ax.set_xlabel("FPR")
        ax.set_ylabel("TPR")
        ax.legend(fontsize=7)

    for ax in axes.ravel()[len(strata):]:
        ax.axis("off")

    fig.suptitle("Per-Condition ROC Curves by Carrier Source", fontsize=12, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def _plot_quality_summary(metrics_dir: Path, figures_dir: Path) -> Path:
    out_path = figures_dir / "quality_summary.png"
    rows = _read_csv_rows(metrics_dir / "quality_metrics.csv")
    values: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        method = row.get("method", "")
        payload_level = row.get("payload_level", "")
        psnr = _maybe_float(row.get("psnr"))
        if method and payload_level and psnr is not None:
            values[(method, payload_level)].append(psnr)

    if not values:
        _write_placeholder_plot(out_path, "Quality Summary", "No quality_metrics.csv PSNR data available.")
        return out_path

    keys = sorted(values)
    labels = [f"{method}\n{payload}" for method, payload in keys]
    means = [mean(values[key]) for key in keys]

    fig, ax = plt.subplots(figsize=(max(7, len(keys) * 1.1), 4.5))
    ax.bar(range(len(keys)), means, color="#607d8b", alpha=0.85)
    ax.set_xticks(range(len(keys)))
    ax.set_xticklabels(labels)
    ax.set_ylabel("Mean PSNR (dB)")
    ax.set_title("Embedding Quality Summary by Method and Payload")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def _write_experiment_contrast_tables(metrics_dir: Path, predictions: list[dict]) -> dict[str, Path]:
    outputs: dict[str, Path] = {}
    if not predictions:
        return outputs

    strata = sorted({(r["detector"], r["method"], r["payload_level"]) for r in predictions})

    exp1_rows: list[dict] = []
    for detector, method, payload_level in strata:
        real_rows = _filter_preds(predictions, detector=detector, source="real", method=method, payload_level=payload_level)
        ml_rows = _filter_preds(predictions, detector=detector, source="ml_a", method=method, payload_level=payload_level) + _filter_preds(predictions, detector=detector, source="ml_b", method=method, payload_level=payload_level)
        stat = _delong_compare(*_pos_neg(real_rows), *_pos_neg(ml_rows), paired=False)
        exp1_rows.append({"experiment": "exp1_rq1_real_vs_pooled_ml", "detector": detector, "method": method, "payload_level": payload_level, **stat})
    _holm_adjust(exp1_rows)
    outputs["exp1_contrasts"] = metrics_dir / "exp1_rq1_real_vs_pooled_ml_contrasts.csv"
    _write_csv(outputs["exp1_contrasts"], exp1_rows)

    exp2_rows: list[dict] = []
    for detector, method, payload_level in strata:
        ml_a_rows = _filter_preds(predictions, detector=detector, source="ml_a", method=method, payload_level=payload_level)
        ml_b_rows = _filter_preds(predictions, detector=detector, source="ml_b", method=method, payload_level=payload_level)
        stat = _delong_compare(*_pos_neg(ml_a_rows), *_pos_neg(ml_b_rows), paired=False)
        exp2_rows.append({"experiment": "exp2_rq2_mla_vs_mlb", "detector": detector, "method": method, "payload_level": payload_level, **stat})
    _holm_adjust(exp2_rows)
    outputs["exp2_contrasts"] = metrics_dir / "exp2_rq2_mla_vs_mlb_contrasts.csv"
    _write_csv(outputs["exp2_contrasts"], exp2_rows)

    exp5_rows: list[dict] = []
    for detector, method, payload_level in strata:
        for source in sorted({r["source"] for r in predictions}):
            plain_rows = _filter_preds(predictions, detector=detector, source=source, method=method, payload_level=payload_level, encryption="plain")
            enc_rows = _filter_preds(predictions, detector=detector, source=source, method=method, payload_level=payload_level, encryption="encrypted")
            stat = _delong_compare(*_pos_neg(plain_rows), *_pos_neg(enc_rows), paired=True)
            exp5_rows.append({"experiment": "exp5_rq5_plain_vs_encrypted", "detector": detector, "source": source, "method": method, "payload_level": payload_level, **stat})
    outputs["exp5_contrasts"] = metrics_dir / "exp5_rq5_encryption_contrasts.csv"
    _write_csv(outputs["exp5_contrasts"], exp5_rows)

    return outputs


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
    figures["roc_condition_panels"] = _plot_roc_condition_panels(predictions, figures_dir)
    figures["quality_summary"] = _plot_quality_summary(metrics_dir, figures_dir)

    for key, path in _write_experiment_contrast_tables(metrics_dir, predictions).items():
        figures[key] = path

    return figures
