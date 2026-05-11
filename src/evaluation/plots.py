from __future__ import annotations

"""Figure generation from computed metrics tables."""

import csv
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from scipy import stats

# Centralised palette and rcParams so every figure shares the same look, for future report
THEME = {
    "real": "#5B8FB9",  # soft denim
    "ml_a": "#E2A85F",  # soft amber
    "ml_b": "#7FB29C",  # soft sage
    "plain": "#7FB3D5",  # pastel sky
    "encrypted": "#D88E8E",  # pastel rose
    "lsb": "#A89CD3",  # pastel violet
    "dct": "#E5B25D",  # pastel saffron
    "neutral": "#8A8C91",  # slate
    "accent": "#6B7FA0",  # academic muted blue
    "sig": "#B5524F",  # crimson (sig. < 0.05)
    "ns": "#6B7FA0",  # muted blue (n.s.)
    "grid": "#D9D9D9",
    "spine": "#4A4A4A",
    "text": "#2B2B2B",
    "muted": "#9A9A9A",
}

SOURCE_COLORS = {"real": THEME["real"], "ml_a": THEME["ml_a"], "ml_b": THEME["ml_b"]}
SOURCE_MARKERS = {"real": "o", "ml_a": "s", "ml_b": "^"}
METHOD_COLORS = {"lsb": THEME["lsb"], "dct": THEME["dct"]}
ENCRYPTION_COLORS = {"plain": THEME["plain"], "encrypted": THEME["encrypted"]}

# Diverging colormap centred on 0 for Δ-AUC heatmaps.
DIVERGING_CMAP = LinearSegmentedColormap.from_list(
    "academic_diverging",
    [THEME["plain"], "#F4F4F4", THEME["encrypted"]],
    N=256,
)


def _apply_academic_style() -> None:
    """Apply consistent academic styling to every figure in the module."""
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["DejaVu Serif", "Times New Roman", "Times", "serif"],
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
            "axes.labelsize": 9.5,
            "axes.labelcolor": THEME["text"],
            "axes.edgecolor": THEME["spine"],
            "axes.linewidth": 0.8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": THEME["grid"],
            "grid.linestyle": "-",
            "grid.linewidth": 0.6,
            "grid.alpha": 0.7,
            "xtick.color": THEME["text"],
            "ytick.color": THEME["text"],
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "xtick.direction": "out",
            "ytick.direction": "out",
            "legend.fontsize": 8.5,
            "legend.title_fontsize": 9,
            "legend.frameon": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "savefig.dpi": 200,
            "savefig.bbox": "tight",
            "figure.dpi": 120,
            "text.color": THEME["text"],
        }
    )


_apply_academic_style()


def _save_fig(fig, path: Path) -> None:
    """Persist a figure with consistent settings and close it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


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
    ax.text(
        0.5,
        0.62,
        title,
        ha="center",
        va="center",
        fontsize=13,
        fontweight="bold",
        transform=ax.transAxes,
        color=THEME["text"],
    )
    ax.text(
        0.5,
        0.38,
        reason,
        ha="center",
        va="center",
        fontsize=10,
        style="italic",
        transform=ax.transAxes,
        wrap=True,
        color=THEME["muted"],
    )
    _save_fig(fig, path)


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
    n_a = len(pos_a) + len(neg_a)
    n_b = len(pos_b) + len(neg_b)
    _nan = dict(
        auc_a=auc_a,
        auc_b=auc_b,
        diff=None,
        se=None,
        ci_lo=None,
        ci_hi=None,
        z=None,
        p=None,
        n_a=n_a,
        n_b=n_b,
        n_pos_a=len(pos_a),
        n_neg_a=len(neg_a),
        n_pos_b=len(pos_b),
        n_neg_b=len(neg_b),
    )
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
        cov = cov_10 + cov_01

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

    return dict(
        auc_a=auc_a,
        auc_b=auc_b,
        diff=diff,
        se=se,
        ci_lo=ci_lo,
        ci_hi=ci_hi,
        z=z_val,
        p=p_val,
        n_a=n_a,
        n_b=n_b,
        n_pos_a=len(pos_a),
        n_neg_a=len(neg_a),
        n_pos_b=len(pos_b),
        n_neg_b=len(neg_b),
    )


def _format_p(p_value: float | None) -> str:
    """Render a p-value following common academic conventions."""
    if p_value is None:
        return ""
    if p_value < 0.001:
        return "p<0.001"
    return f"p={p_value:.3f}"


def _meta_diamond(rows: list[dict]) -> dict | None:
    """Inverse-variance fixed-effect summary across rows with diff/se.

    Used to draw a meta-analytic diamond underneath a per-stratum forest. The
    summary is the variance-weighted mean of the per-stratum Δ-AUC, with a
    Wald 95 % CI under a fixed-effect assumption. We also report Cochran's
    heterogeneity Q and I² so the diamond can be flagged when between-stratum
    heterogeneity is large.
    """
    weights: list[float] = []
    diffs: list[float] = []
    for r in rows:
        if r.get("diff") is None or r.get("se") in (None, 0.0):
            continue
        se = float(r["se"])
        if se <= 0:
            continue
        weights.append(1.0 / (se * se))
        diffs.append(float(r["diff"]))
    if not weights:
        return None
    w_arr = np.array(weights)
    d_arr = np.array(diffs)
    w_sum = float(w_arr.sum())
    pooled = float((w_arr * d_arr).sum() / w_sum)
    se_pooled = float(np.sqrt(1.0 / w_sum))
    ci_lo = pooled - 1.96 * se_pooled
    ci_hi = pooled + 1.96 * se_pooled
    z_val = pooled / se_pooled if se_pooled > 0 else 0.0
    p_val = float(2.0 * (1.0 - stats.norm.cdf(abs(z_val)))) if se_pooled > 0 else 1.0
    # Cochran's Q
    q_stat = float((w_arr * (d_arr - pooled) ** 2).sum())
    df = max(len(weights) - 1, 0)
    i_sq = max(0.0, (q_stat - df) / q_stat) if q_stat > 0 else 0.0
    return dict(
        diff=pooled,
        se=se_pooled,
        ci_lo=ci_lo,
        ci_hi=ci_hi,
        z=z_val,
        p=p_val,
        q=q_stat,
        df=df,
        i_squared=i_sq,
        n_studies=len(weights),
        is_diamond=True,
    )


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
    ml_rows = _filter_preds(
        predictions,
        detector=detector,
        source="ml_a",
        method=method,
        payload_level=payload_level,
        encryption=encryption,
    ) + _filter_preds(
        predictions,
        detector=detector,
        source="ml_b",
        method=method,
        payload_level=payload_level,
        encryption=encryption,
    )
    auc_real, var_real = _auc_var_for_rows(real_rows)
    auc_ml, var_ml = _auc_var_for_rows(ml_rows)
    if auc_real is None or auc_ml is None:
        return dict(
            auc_a=auc_real,
            auc_b=auc_ml,
            diff=None,
            se=None,
            ci_lo=None,
            ci_hi=None,
            z=None,
            p=None,
        )
    diff = auc_real - auc_ml
    se = math.sqrt(max((var_real or 0.0) + (var_ml or 0.0), 0.0))
    ci_lo = diff - 1.96 * se
    ci_hi = diff + 1.96 * se
    z_val = diff / se if se > 1e-12 else 0.0
    p_value = 2.0 * (1.0 - stats.norm.cdf(abs(z_val))) if se > 1e-12 else 1.0
    return dict(
        auc_a=auc_real,
        auc_b=auc_ml,
        diff=diff,
        se=se,
        ci_lo=ci_lo,
        ci_hi=ci_hi,
        z=z_val,
        p=p_value,
    )


def _load_predictions(predictions_path: Path) -> list[dict]:
    """Load predictions.csv and return typed rows sorted by group_id."""
    rows = _read_csv_rows(predictions_path)
    result = []
    for r in rows:
        score = _maybe_float(r.get("score"))
        label_raw = _maybe_float(r.get("label"))
        if score is None or label_raw is None:
            continue
        result.append(
            {
                "detector": r.get("detector", ""),
                "group_id": int(r.get("group_id", 0)),
                "source": r.get("source", ""),
                "method": r.get("method", ""),
                "payload_level": r.get("payload_level", ""),
                "encryption": r.get("encryption", ""),
                "label": int(label_raw),
                "score": score,
            }
        )
    result.sort(
        key=lambda r: (
            r["group_id"],
            r["detector"],
            r["source"],
            r["method"],
            r["payload_level"],
            r["encryption"],
            r["label"],
        )
    )
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


def _ensure_source_condition_metrics(
    metrics_dir: Path, predictions: list[dict]
) -> Path:
    """Write source_condition_metrics.csv (per detector x source x method x payload x encryption)."""
    out_path = metrics_dir / "source_condition_metrics.csv"

    strata = sorted(
        {
            (
                r["detector"],
                r["source"],
                r["method"],
                r["payload_level"],
                r["encryption"],
            )
            for r in predictions
        }
    )

    rows: list[dict] = []
    for detector, source, method, payload_level, encryption in strata:
        subset = _filter_preds(
            predictions,
            detector=detector,
            source=source,
            method=method,
            payload_level=payload_level,
            encryption=encryption,
        )
        pos, neg = _pos_neg(subset)
        auc, V10, V01 = _delong_components(pos, neg)
        if auc is None:
            continue
        var_auc = _delong_var(V10, V01)
        se = float(np.sqrt(max(var_auc, 0.0)))
        rows.append(
            {
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
            }
        )

    _write_csv(out_path, rows)
    return out_path


def _forest_plot(
    ax,
    results: list[dict],
    xlabel: str,
    *,
    color: str | None = None,
    sig_color: str | None = None,
    annotate: bool = True,
    p_field: str = "p",
    show_n: bool = False,
) -> None:
    """Draw a horizontal forest plot on *ax* from a list of DeLong result dicts.

    Expected per-row keys: ``label``, ``diff``, ``ci_lo``, ``ci_hi``,
    ``auc_a``, ``auc_b`` and a p-value column (default ``p``; pass
    ``p_field='p_holm'`` for confirmatory experiments).

    Rows whose dict carries ``is_diamond=True`` are drawn as a meta-analytic
    diamond instead of a square marker. They are also separated from the rest
    of the rows by a thin rule for visual clarity.
    """
    color = color or THEME["ns"]
    sig_color = sig_color or THEME["sig"]
    x_values: list[float] = []

    for i, r in enumerate(results):
        if r.get("diff") is None:
            ax.text(
                0.0,
                i,
                "n/a",
                ha="center",
                va="center",
                fontsize=8,
                color=THEME["muted"],
                style="italic",
            )
            continue

        p_for_color = r.get(p_field)
        c = sig_color if (p_for_color is not None and p_for_color < 0.05) else color
        ci_lo, ci_hi, diff = r["ci_lo"], r["ci_hi"], r["diff"]
        is_diamond = bool(r.get("is_diamond"))

        if is_diamond:
            half = (ci_hi - ci_lo) / 2.0
            xs = [ci_lo, diff, ci_hi, diff, ci_lo]
            ys = [i, i - 0.32, i, i + 0.32, i]
            ax.fill(xs, ys, color=c, alpha=0.85, edgecolor="white", linewidth=0.8,
                    zorder=5)
        else:
            ax.plot(
                [ci_lo, ci_hi],
                [i, i],
                color=c,
                linewidth=2.2,
                solid_capstyle="round",
                alpha=0.85,
            )
            ax.plot(
                diff,
                i,
                marker="s",
                color=c,
                markersize=6.5,
                markeredgecolor="white",
                markeredgewidth=0.8,
                zorder=5,
            )

        x_values.extend([ci_lo, ci_hi])

        if annotate:
            p_str = _format_p(p_for_color)
            n_str = ""
            if show_n:
                n_a = r.get("n_a")
                n_b = r.get("n_b")
                if n_a is not None and n_b is not None:
                    n_str = f"  n={n_a}/{n_b}"
            extra = ""
            if is_diamond:
                k = r.get("n_studies")
                i_sq = r.get("i_squared")
                if k is not None and i_sq is not None:
                    extra = f"  (k={k}, I²={i_sq*100:.0f}%)"
            annot = (
                f"Δ={diff:+.3f}  [{ci_lo:+.3f}, {ci_hi:+.3f}]"
                f"  {p_str}{n_str}{extra}"
            )
            ax.annotate(
                annot,
                xy=(ci_hi, i),
                xytext=(6, 0),
                textcoords="offset points",
                va="center",
                fontsize=7.5,
                clip_on=False,
                color=THEME["text"],
                fontweight="bold" if is_diamond else "normal",
            )

    ax.axvline(
        0, color=THEME["spine"], linestyle="--", linewidth=0.8, alpha=0.55, zorder=1
    )
    ax.set_yticks(list(range(len(results))))
    ax.set_yticklabels([r.get("label", str(i)) for i, r in enumerate(results)])
    ax.set_xlabel(xlabel)
    ax.set_ylim(-0.7, len(results) - 0.3)
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.4)
    ax.grid(axis="y", visible=False)

    if x_values:
        span = max(x_values) - min(x_values)
        pad = max(span * 0.15, 0.05)
        right_pad = pad + span * 0.45 if annotate else pad
        ax.set_xlim(min(x_values) - pad, max(x_values) + right_pad)


# Actual plot design


def _make_pair_compare(
    predictions: list[dict],
    *,
    pos_source: str | tuple[str, ...],
    neg_source: str | tuple[str, ...],
) -> callable:
    """Return a function that runs DeLong on two source groups under a filter."""
    pos_sources = (pos_source,) if isinstance(pos_source, str) else tuple(pos_source)
    neg_sources = (neg_source,) if isinstance(neg_source, str) else tuple(neg_source)

    def _compare(**filters) -> dict | None:
        pos_rows: list[dict] = []
        for src in pos_sources:
            pos_rows.extend(_filter_preds(predictions, source=src, **filters))
        neg_rows: list[dict] = []
        for src in neg_sources:
            neg_rows.extend(_filter_preds(predictions, source=src, **filters))
        if not pos_rows or not neg_rows:
            return None
        return _delong_compare(*_pos_neg(pos_rows), *_pos_neg(neg_rows), paired=False)

    return _compare


def _render_pair_overview(
    *,
    out_path: Path,
    detectors: list[str],
    strata: list[tuple[str, str]],
    compare_fn,
    title_main: str,
    xlabel: str,
) -> Path:
    """Overview forest plot.

    Layout (top → bottom):
        ◆ Fixed-effect meta-analytic summary across **all strata**.
        ◆ One meta-analytic diamond per detector (over its own strata).
        ▣ One row per detector showing its pooled-scores DeLong (kept for
          comparison; readers can sanity-check that the diamond agrees).

    Holm correction is applied to the per-detector pooled-score test family.
    """
    # Per-stratum results — needed both for diamonds and for the family-wide
    # Holm correction on confirmatory experiments.
    per_stratum: list[dict] = []
    for detector in detectors:
        for method, payload_level in strata:
            stat = compare_fn(
                detector=detector, method=method, payload_level=payload_level
            )
            if stat is None:
                continue
            per_stratum.append(
                {
                    "label": f"{detector} · {method} / {payload_level}",
                    "_detector": detector,
                    **stat,
                }
            )
    _holm_adjust(per_stratum)

    results: list[dict] = []
    overall = _meta_diamond(per_stratum)
    if overall is not None:
        results.append({"label": "All strata  (meta-analytic)", **overall})

    for detector in detectors:
        det_rows = [r for r in per_stratum if r.get("_detector") == detector]
        diamond = _meta_diamond(det_rows)
        if diamond is not None:
            # Use the smallest Holm-adjusted p across strata as the diamond's
            # significance flag; this is conservative and matches the family.
            holm_min = min(
                (r["p_holm"] for r in det_rows if r.get("p_holm") is not None),
                default=None,
            )
            results.append(
                {"label": f"{detector}  ⟨meta⟩",
                 **diamond,
                 "p_holm": holm_min}
            )

    if not results:
        _write_placeholder_plot(out_path, title_main, "No prediction data available.")
        return out_path

    fig, ax = plt.subplots(figsize=(11, max(2.6, len(results) * 0.7 + 1.6)))
    _forest_plot(
        ax, results, xlabel,
        color=THEME["ns"], sig_color=THEME["sig"],
        p_field="p_holm" if any(r.get("p_holm") is not None for r in results) else "p",
    )
    ax.axhline(0.5, color=THEME["grid"], linewidth=0.6, zorder=0)
    family_n = sum(1 for r in per_stratum if r.get("p") is not None)
    ax.set_title(
        f"{title_main} — Overview  (Inverse-variance meta-analysis, 95% CI)\n"
        f"Diamonds = fixed-effect Δ-AUC pooled across strata · Holm correction "
        f"applied within Exp family (N = {family_n} tests)"
    )
    _save_fig(fig, out_path)
    return out_path


def _render_pair_detector_panels(
    *,
    panels_dir: Path,
    detectors: list[str],
    strata: list[tuple[str, str]],
    compare_fn,
    title_prefix: str,
    xlabel: str,
) -> dict[str, Path]:
    """One detail forest plot per detector covering every (method × payload) stratum.

    Holm correction is applied **within** each detector panel; the figure
    annotates how many tests the family contains so readers can verify scope.
    """
    panels_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {"_panels_dir": panels_dir}
    for detector in detectors:
        results: list[dict] = []
        for method, payload_level in strata:
            stat = compare_fn(
                detector=detector, method=method, payload_level=payload_level
            )
            if stat is None:
                continue
            results.append(
                {
                    "label": f"{method}  /  {payload_level}",
                    **stat,
                }
            )
        _holm_adjust(results)
        # Append a meta-analytic diamond for the detector at the top.
        diamond = _meta_diamond(results)
        rows_for_plot: list[dict] = []
        if diamond is not None:
            rows_for_plot.append({
                "label": f"{detector}  ⟨meta⟩",
                **diamond,
                "p_holm": min(
                    (r["p_holm"] for r in results if r.get("p_holm") is not None),
                    default=None,
                ),
            })
        rows_for_plot.extend(results)

        fig_path = panels_dir / f"{detector}.png"
        if not results:
            _write_placeholder_plot(
                fig_path,
                f"{title_prefix} · {detector}",
                "No prediction data available for this detector.",
            )
            out[f"detector_{detector}"] = fig_path
            continue

        fig, ax = plt.subplots(figsize=(11, max(3.0, len(rows_for_plot) * 0.6 + 1.6)))
        _forest_plot(
            ax, rows_for_plot, xlabel,
            color=THEME["ns"], sig_color=THEME["sig"],
            p_field="p_holm",
            show_n=True,
        )
        family_n = sum(1 for r in results if r.get("p") is not None)
        ax.set_title(
            f"{title_prefix} · detector = {detector}\n"
            f"Crimson = Holm-adjusted $p_{{Holm}} < 0.05$  ·  "
            f"Holm correction within detector (N = {family_n} tests) · "
            f"pooled across encryption"
        )
        _save_fig(fig, fig_path)
        out[f"detector_{detector}"] = fig_path
    return out


def _plot_exp1(predictions: list[dict], figures_dir: Path) -> dict[str, Path]:
    """Exp 1: Real vs. pooled ML AUC.

    Emits an overview (per-detector pooled) + per-detector detail panels.
    """
    detectors = sorted({r["detector"] for r in predictions})
    strata = sorted({(r["method"], r["payload_level"]) for r in predictions})
    compare_fn = _make_pair_compare(
        predictions,
        pos_source="real",
        neg_source=("ml_a", "ml_b"),
    )

    overview_path = figures_dir / "exp1_real_vs_pooled_ml.png"
    out: dict[str, Path] = {
        "exp1_real_vs_pooled_ml": _render_pair_overview(
            out_path=overview_path,
            detectors=detectors,
            strata=strata,
            compare_fn=compare_fn,
            title_main="Exp 1 — Real vs. Pooled ML AUC",
            xlabel="AUC Difference  (Real − Pooled ML)",
        ),
    }
    panels = _render_pair_detector_panels(
        panels_dir=figures_dir / "exp1_panels",
        detectors=detectors,
        strata=strata,
        compare_fn=compare_fn,
        title_prefix="Exp 1 — Real vs. Pooled ML",
        xlabel="AUC Difference  (Real − Pooled ML)",
    )
    out["exp1_panels_dir"] = panels.pop("_panels_dir")
    for key, path in panels.items():
        out[f"exp1_panel_{key.split('_', 1)[1]}"] = path
    return out


def _plot_exp2(predictions: list[dict], figures_dir: Path) -> dict[str, Path]:
    """Exp 2: Caption-matched ML-A vs. ML-B AUC.

    Emits an overview (per-detector pooled) + per-detector detail panels.
    """
    detectors = sorted({r["detector"] for r in predictions})
    strata = sorted({(r["method"], r["payload_level"]) for r in predictions})
    compare_fn = _make_pair_compare(
        predictions,
        pos_source="ml_a",
        neg_source="ml_b",
    )

    overview_path = figures_dir / "exp2_mla_vs_mlb.png"
    out: dict[str, Path] = {
        "exp2_mla_vs_mlb": _render_pair_overview(
            out_path=overview_path,
            detectors=detectors,
            strata=strata,
            compare_fn=compare_fn,
            title_main="Exp 2 — Caption-Matched ML-A vs. ML-B AUC",
            xlabel="AUC Difference  (ML-A − ML-B)",
        ),
    }
    panels = _render_pair_detector_panels(
        panels_dir=figures_dir / "exp2_panels",
        detectors=detectors,
        strata=strata,
        compare_fn=compare_fn,
        title_prefix="Exp 2 — ML-A vs. ML-B",
        xlabel="AUC Difference  (ML-A − ML-B)",
    )
    out["exp2_panels_dir"] = panels.pop("_panels_dir")
    for key, path in panels.items():
        out[f"exp2_panel_{key.split('_', 1)[1]}"] = path
    return out


def _plot_exp3a(predictions: list[dict], figures_dir: Path) -> Path:
    """Exp 3a: AUC and source-contrast gaps across Low/Medium/High payload levels.

    The proposal restricts RQ3 to the three k=1 payload levels (Low, Medium,
    High); BD-Sens is reported separately in Exp 3b. So we fix the analysis
    here to ``{low, medium, high}`` and let each (detector, method) panel
    show only the payload levels actually populated for that combination.

    Top row: AUC per source per detector (±95% CI).
    Bottom row: source-contrast gap = AUC_real − mean(AUC_ml_a, AUC_ml_b).
    """
    out_path = figures_dir / "exp3a_payload_level_auc.png"

    PAYLOAD_ORDER = ["low", "medium", "high"]
    panels = sorted({(r["detector"], r["method"]) for r in predictions})
    sources = sorted({r["source"] for r in predictions})

    # Per-panel availability: a payload only appears on the x-axis if there
    # is at least one row for that (detector, method, payload). BD-Sens is
    # excluded from RQ3 by design.
    panel_payloads: dict[tuple[str, str], list[str]] = {}
    for detector, method in panels:
        present = {
            r["payload_level"]
            for r in predictions
            if r["detector"] == detector
            and r["method"] == method
            and r["payload_level"] in PAYLOAD_ORDER
        }
        panel_payloads[(detector, method)] = [p for p in PAYLOAD_ORDER if p in present]

    panels = [pm for pm in panels if panel_payloads[pm]]
    if not panels:
        _write_placeholder_plot(
            out_path, "Exp 3a: Payload Level AUC",
            "No k=1 payload levels (low/medium/high) present.",
        )
        return out_path

    auc_data: dict[tuple, float] = {}
    se_data: dict[tuple, float] = {}
    for detector, method in panels:
        for source in sources:
            for pl in panel_payloads[(detector, method)]:
                rows = _filter_preds(
                    predictions,
                    detector=detector,
                    source=source,
                    method=method,
                    payload_level=pl,
                )
                pos, neg = _pos_neg(rows)
                auc, V10, V01 = _delong_components(pos, neg)
                if auc is not None:
                    auc_data[(detector, method, source, pl)] = auc
                    se_data[(detector, method, source, pl)] = float(
                        np.sqrt(max(_delong_var(V10, V01), 0.0))
                    )

    if not auc_data:
        _write_placeholder_plot(
            out_path, "Exp 3a: Payload Level AUC", "Insufficient data."
        )
        return out_path

    n_det = len(panels)

    fig, axes = plt.subplots(
        2,
        n_det,
        figsize=(4.6 * n_det + 1, 8),
        gridspec_kw={"height_ratios": [2, 1], "hspace": 0.22, "wspace": 0.22},
    )
    if n_det == 1:
        axes = axes.reshape(2, 1)

    # top row: AUC per source
    for col, (detector, method) in enumerate(panels):
        ax = axes[0, col]
        local_payloads = panel_payloads[(detector, method)]
        x_ticks = list(range(len(local_payloads)))
        for source in sources:
            aucs = [auc_data.get((detector, method, source, pl)) for pl in local_payloads]
            ses = [se_data.get((detector, method, source, pl), 0.0) for pl in local_payloads]
            valid = [
                (xi, a, s) for xi, a, s in zip(x_ticks, aucs, ses) if a is not None
            ]
            if valid:
                xv, av, sv = zip(*valid)
                ax.errorbar(
                    xv,
                    av,
                    yerr=[1.96 * s for s in sv],
                    marker=SOURCE_MARKERS.get(source, "o"),
                    color=SOURCE_COLORS.get(source, THEME["neutral"]),
                    label=source,
                    linewidth=1.8,
                    markersize=7,
                    capsize=3.5,
                    markeredgecolor="white",
                    markeredgewidth=0.7,
                    elinewidth=1.2,
                    alpha=0.95,
                )
        ax.set_xticks(x_ticks)
        ax.set_xticklabels(local_payloads)
        ax.set_xlim(-0.4, len(local_payloads) - 0.6)
        ax.set_ylim(0.4, 1.02)
        ax.set_title(f"{detector} / {method}")
        if col == 0:
            ax.set_ylabel("ROC-AUC  (±95% CI)")
        ax.legend(title="Source", loc="lower right")

    # bottom row: source-contrast gap
    for col, (detector, method) in enumerate(panels):
        ax = axes[1, col]
        local_payloads = panel_payloads[(detector, method)]
        x_ticks = list(range(len(local_payloads)))
        gaps: list[float | None] = []
        for pl in local_payloads:
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

        valid = [(xi, g) for xi, g in zip(x_ticks, gaps) if g is not None]
        if valid:
            xv, gv = zip(*valid)
            ax.bar(
                xv,
                gv,
                color=THEME["accent"],
                alpha=0.78,
                width=0.55,
                edgecolor="white",
                linewidth=0.8,
            )
            ax.axhline(0, color=THEME["spine"], linewidth=0.7)
        ax.set_xticks(x_ticks)
        ax.set_xticklabels(local_payloads)
        ax.set_xlim(-0.4, len(local_payloads) - 0.6)
        ax.set_xlabel("Payload Level")
        if col == 0:
            ax.set_ylabel(r"Gap  (AUC$_{real}$ − AUC$_{ml}$)")

    note = ""
    union = sorted(
        {pl for pls in panel_payloads.values() for pl in pls},
        key=lambda x: PAYLOAD_ORDER.index(x) if x in PAYLOAD_ORDER else 99,
    )
    if set(union) == {"low"}:
        note = (
            "\n[Prototype data: only 'low' payload level present. "
            "Full design adds medium & high.]"
        )

    fig.suptitle(
        f"Exp 3a — AUC and Source-Contrast Gaps Across Payload Levels"
        f"  (k=1; BD-Sens is in Exp 3b){note}",
        fontsize=12,
        fontweight="bold",
    )
    _save_fig(fig, out_path)
    return out_path


def _plot_exp3b(predictions: list[dict], figures_dir: Path) -> Path:
    """Exp 3b: BD-Sens (k=2) amplification analysis.

    Two side-by-side panels:
        Left  — per-detector source gap at BD-Sens (Real − Pooled ML).
        Right — amplification: ΔΔ = (gap@BD-Sens) − (gap@k=1 High).
                Tests whether a second bit-plane *increases* the source gap.

    When BD-Sens data is unavailable we fall back to the densest LSB payload
    as a surrogate so the figure is still rendered for prototype runs; the
    title is updated to flag the surrogate.
    """

    out_path = figures_dir / "exp3b_bd_sens.png"

    bd_rows = [r for r in predictions if r.get("payload_level") == "bd_sens"]
    bd_label = "k=2, 1.50 bpp"
    surrogate = False

    if not bd_rows:
        PAYLOAD_RANK = {"low": 0, "medium": 1, "high": 2, "bd_sens": 3}
        lsb_rows = [r for r in predictions if r.get("method") == "lsb"]
        if not lsb_rows:
            _write_placeholder_plot(
                out_path, "Exp 3b — BD-Sens Analysis",
                "No LSB prediction data available.",
            )
            return out_path
        densest = max(
            {r["payload_level"] for r in lsb_rows},
            key=lambda pl: PAYLOAD_RANK.get(pl, -1),
        )
        bd_rows = [r for r in lsb_rows if r["payload_level"] == densest]
        bd_label = f"surrogate · payload={densest}"
        surrogate = True

    detectors = sorted({r["detector"] for r in bd_rows})
    bd_payload = sorted({r["payload_level"] for r in bd_rows})[0]

    # Left panel: source gap at BD-Sens.
    gap_bd: list[dict] = []
    for detector in detectors:
        stat = _source_gap_stats(
            bd_rows, detector=detector, method="lsb", payload_level=bd_payload,
        )
        gap_bd.append({"label": detector, **stat})

    if not gap_bd or all(r.get("diff") is None for r in gap_bd):
        _write_placeholder_plot(
            out_path, "Exp 3b — BD-Sens Analysis",
            "Insufficient data for source-gap estimation.",
        )
        return out_path

    # Right panel: amplification ΔΔ = gap(BD-Sens) − gap(k=1 High).
    high_rows = [
        r for r in predictions
        if r.get("method") == "lsb" and r.get("payload_level") == "high"
    ]
    amp_results: list[dict] = []
    if high_rows:
        for detector in detectors:
            gap_high = _source_gap_stats(
                high_rows, detector=detector, method="lsb", payload_level="high",
            )
            gap_bd_det = next(
                (r for r in gap_bd if r["label"] == detector and r.get("diff") is not None),
                None,
            )
            if gap_bd_det is None or gap_high.get("diff") is None:
                continue
            diff_amp = gap_bd_det["diff"] - gap_high["diff"]
            se_amp = math.sqrt(
                (gap_bd_det.get("se") or 0.0) ** 2
                + (gap_high.get("se") or 0.0) ** 2
            )
            ci_lo = diff_amp - 1.96 * se_amp
            ci_hi = diff_amp + 1.96 * se_amp
            z_val = diff_amp / se_amp if se_amp > 1e-12 else 0.0
            p_val = (
                float(2.0 * (1.0 - stats.norm.cdf(abs(z_val))))
                if se_amp > 1e-12 else 1.0
            )
            amp_results.append({
                "label": detector,
                "diff": diff_amp,
                "se": se_amp,
                "ci_lo": ci_lo,
                "ci_hi": ci_hi,
                "z": z_val,
                "p": p_val,
                "auc_a": gap_bd_det["diff"],
                "auc_b": gap_high["diff"],
            })

    n_panels = 2 if amp_results else 1
    fig_width = 13 if n_panels == 2 else 11
    fig, axes = plt.subplots(
        1, n_panels,
        figsize=(fig_width, max(3.0, len(gap_bd) * 0.85 + 1.6)),
        gridspec_kw={"wspace": 0.55},
    )
    if n_panels == 1:
        axes = [axes]

    _forest_plot(
        axes[0], gap_bd, "AUC Gap  (Real − Pooled ML)",
        color=THEME["ns"], sig_color=THEME["sig"], show_n=True,
    )
    axes[0].set_title(f"Source gap at BD-Sens  ({bd_label})")

    if amp_results:
        _forest_plot(
            axes[1], amp_results,
            "Amplification  ΔΔ = gap@BD-Sens − gap@k=1 High",
            color=THEME["ns"], sig_color=THEME["sig"],
        )
        axes[1].set_title("Bit-plane amplification of the source gap")

    suptitle = "Exp 3b — Bit-Depth Sensitivity (k=2)"
    if surrogate:
        suptitle += "  ·  surrogate data (no true k=2 rows)"
    fig.suptitle(suptitle, fontsize=12, fontweight="bold")
    _save_fig(fig, out_path)
    return out_path


def _plot_exp4(predictions: list[dict], figures_dir: Path) -> Path:
    """Exp 4: Source × Branch interaction.

    For every (detector, payload) where both a spatial method (lsb) and a
    frequency method (dct) are populated, we compute the source-gap on each
    branch and form the interaction term

        ΔΔ = gap_spatial − gap_frequency

    with a Wald CI from the propagated DeLong SEs. Output:
        Left   — per-(detector × payload) interaction forest.
        Right  — meta-analytic diamond per detector + overall.
    """
    out_path = figures_dir / "exp4_spatial_vs_frequency.png"

    methods = {r["method"] for r in predictions}
    spatial = sorted(m for m in methods if "lsb" in m.lower() and "dct" not in m.lower())
    frequency = sorted(m for m in methods if "dct" in m.lower())

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

    sp_method = spatial[0]
    fr_method = frequency[0]

    PAYLOAD_ORDER = ["low", "medium", "high"]
    payload_levels = [
        pl for pl in PAYLOAD_ORDER
        if any(r["payload_level"] == pl for r in predictions)
    ]
    detectors = sorted({r["detector"] for r in predictions})

    # Per-(detector, payload) interaction results.
    per_cell: list[dict] = []
    for detector in detectors:
        for payload_level in payload_levels:
            sp_gap = _source_gap_stats(
                predictions, detector=detector,
                method=sp_method, payload_level=payload_level,
            )
            fr_gap = _source_gap_stats(
                predictions, detector=detector,
                method=fr_method, payload_level=payload_level,
            )
            if sp_gap.get("diff") is None or fr_gap.get("diff") is None:
                continue
            diff = sp_gap["diff"] - fr_gap["diff"]
            se = math.sqrt(
                max(
                    (sp_gap.get("se") or 0.0) ** 2
                    + (fr_gap.get("se") or 0.0) ** 2,
                    0.0,
                )
            )
            ci_lo = diff - 1.96 * se
            ci_hi = diff + 1.96 * se
            z_val = diff / se if se > 1e-12 else 0.0
            p_value = (
                2.0 * (1.0 - stats.norm.cdf(abs(z_val))) if se > 1e-12 else 1.0
            )
            per_cell.append({
                "label": f"{detector}  /  {payload_level}",
                "_detector": detector,
                "auc_a": sp_gap["diff"],
                "auc_b": fr_gap["diff"],
                "diff": diff,
                "se": se,
                "ci_lo": ci_lo,
                "ci_hi": ci_hi,
                "z": z_val,
                "p": p_value,
            })

    if not per_cell:
        _write_placeholder_plot(out_path, "Exp 4: Spatial vs. Frequency", "No data.")
        return out_path

    # Right panel: per-detector meta-analytic diamond + overall.
    summary: list[dict] = []
    for detector in detectors:
        det_rows = [r for r in per_cell if r["_detector"] == detector]
        diamond = _meta_diamond(det_rows)
        if diamond is not None:
            summary.append({"label": f"{detector}  ⟨meta⟩", **diamond})
    overall = _meta_diamond(per_cell)
    if overall is not None:
        summary.insert(0, {"label": "All detectors  (meta-analytic)", **overall})

    n_left_rows = len(per_cell)
    n_right_rows = len(summary)
    fig_height = max(3.5, max(n_left_rows, n_right_rows) * 0.5 + 1.8)
    fig, axes = plt.subplots(
        1, 2, figsize=(14, fig_height),
        gridspec_kw={"width_ratios": [1.4, 1.0], "wspace": 0.55},
    )

    _forest_plot(
        axes[0], per_cell,
        "Interaction  ΔΔ = gap$_{spatial}$ − gap$_{frequency}$",
        color=THEME["ns"], sig_color=THEME["sig"],
    )
    axes[0].set_title("Per-stratum source × branch interaction")

    if summary:
        _forest_plot(
            axes[1], summary,
            "Pooled  ΔΔ-AUC",
            color=THEME["ns"], sig_color=THEME["sig"],
        )
        axes[1].set_title("Meta-analytic summary")
    else:
        axes[1].axis("off")

    fig.suptitle(
        "Exp 4 — Source × Branch Interaction  (Exploratory, 95% CI)",
        fontsize=12, fontweight="bold",
    )
    _save_fig(fig, out_path)
    return out_path


def _plot_exp5(predictions: list[dict], figures_dir: Path) -> Path:
    """Exp 5: Plain vs. AES-256-CBC — detectability sanity check (expect Δ ≈ 0).

    Landscape layout (no more tall stacked forest):
        Top    : Δ-AUC heatmap (detector × source) per (method, payload_level).
        Bottom : grouped bar of mean ROC-AUC plain vs. encrypted per detector.
    """
    out_path = figures_dir / "exp5_encryption_effect.png"

    encryptions = {r["encryption"] for r in predictions}
    if "plain" not in encryptions or "encrypted" not in encryptions:
        _write_placeholder_plot(
            out_path,
            "Exp 5 — Encryption Effect",
            "Both 'plain' and 'encrypted' conditions are required.",
        )
        return out_path

    detectors = sorted({r["detector"] for r in predictions})
    sources = sorted({r["source"] for r in predictions})
    methods = sorted({r["method"] for r in predictions})
    payloads = sorted({r["payload_level"] for r in predictions})

    results = []
    for detector in detectors:
        for source in sources:
            for method in methods:
                for payload_level in payloads:
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
                        *_pos_neg(plain_rows),
                        *_pos_neg(enc_rows),
                        paired=True,
                    )
                    results.append(
                        {
                            "label": f"{detector} / {source} / {method} / {payload_level}",
                            "detector": detector,
                            "source": source,
                            "method": method,
                            "payload_level": payload_level,
                            **stat,
                        }
                    )

    if not results:
        _write_placeholder_plot(out_path, "Exp 5 — Encryption Effect", "No data.")
        return out_path

    # Active condition columns (only those with data).
    conditions = sorted({(r["method"], r["payload_level"]) for r in results})
    n_cond = len(conditions)
    n_det = len(detectors)
    n_src = len(sources)

    fig = plt.figure(figsize=(max(11.5, 2.6 * n_cond + 4), 8.5))
    gs = fig.add_gridspec(
        2,
        n_cond + 1,
        height_ratios=[1.3, 1],
        width_ratios=[1.0] * n_cond + [0.07],
        hspace=0.55,
        wspace=0.18,
        left=0.06,
        right=0.97,
        top=0.88,
        bottom=0.10,
    )

    # Top row: per-condition Δ-AUC heatmaps (detector × source).
    diff_max = max(
        (abs(r["diff"]) for r in results if r.get("diff") is not None),
        default=0.05,
    )
    vmax = max(diff_max * 1.05, 0.05)
    heat_axes = []
    last_im = None

    for col, (method, payload_level) in enumerate(conditions):
        ax = fig.add_subplot(gs[0, col])
        heat_axes.append(ax)
        matrix = np.full((n_det, n_src), np.nan)
        sig_mask = np.zeros((n_det, n_src), dtype=bool)
        for i, det in enumerate(detectors):
            for j, src in enumerate(sources):
                cell = next(
                    (
                        r
                        for r in results
                        if r["detector"] == det
                        and r["source"] == src
                        and r["method"] == method
                        and r["payload_level"] == payload_level
                        and r.get("diff") is not None
                    ),
                    None,
                )
                if cell:
                    matrix[i, j] = cell["diff"]
                    if cell.get("p") is not None and cell["p"] < 0.05:
                        sig_mask[i, j] = True

        im = ax.imshow(
            matrix,
            cmap=DIVERGING_CMAP,
            vmin=-vmax,
            vmax=vmax,
            aspect="auto",
        )
        last_im = im
        ax.set_xticks(range(n_src))
        ax.set_xticklabels(sources, rotation=25, ha="right")
        ax.set_yticks(range(n_det))
        ax.set_yticklabels(detectors if col == 0 else [""] * n_det)
        ax.set_title(f"{method} / {payload_level}")
        ax.tick_params(axis="both", which="both", length=0)
        ax.grid(False)
        for spine in ax.spines.values():
            spine.set_visible(False)

        for i in range(n_det):
            for j in range(n_src):
                v = matrix[i, j]
                if np.isnan(v):
                    ax.text(
                        j,
                        i,
                        "–",
                        ha="center",
                        va="center",
                        color=THEME["muted"],
                        fontsize=8,
                    )
                    continue
                txt = f"{v:+.3f}"
                if sig_mask[i, j]:
                    txt += "*"
                ax.text(
                    j,
                    i,
                    txt,
                    ha="center",
                    va="center",
                    fontsize=8.5,
                    color=THEME["text"],
                    fontweight="bold" if sig_mask[i, j] else "normal",
                )

    if last_im is not None:
        cax = fig.add_subplot(gs[0, -1])
        cbar = fig.colorbar(last_im, cax=cax)
        cbar.set_label("Δ-AUC  (Plain − Encrypted)")
        cbar.outline.set_visible(False)

    # Bottom row: grouped bar of mean AUC plain vs encrypted per detector.
    ax_bar = fig.add_subplot(gs[1, :])
    x = np.arange(n_det)
    width = 0.36
    plain_means, enc_means = [], []
    plain_err, enc_err = [], []
    for det in detectors:
        sub = [r for r in results if r["detector"] == det]
        plain_vals = [r["auc_a"] for r in sub if r.get("auc_a") is not None]
        enc_vals = [r["auc_b"] for r in sub if r.get("auc_b") is not None]
        plain_means.append(mean(plain_vals) if plain_vals else 0.0)
        enc_means.append(mean(enc_vals) if enc_vals else 0.0)
        plain_err.append(np.std(plain_vals, ddof=1) if len(plain_vals) > 1 else 0.0)
        enc_err.append(np.std(enc_vals, ddof=1) if len(enc_vals) > 1 else 0.0)

    ax_bar.bar(
        x - width / 2,
        plain_means,
        width,
        yerr=plain_err,
        label="plain",
        color=ENCRYPTION_COLORS["plain"],
        edgecolor="white",
        linewidth=0.8,
        capsize=3,
        error_kw={"ecolor": THEME["spine"], "elinewidth": 0.8},
    )
    ax_bar.bar(
        x + width / 2,
        enc_means,
        width,
        yerr=enc_err,
        label="encrypted",
        color=ENCRYPTION_COLORS["encrypted"],
        edgecolor="white",
        linewidth=0.8,
        capsize=3,
        error_kw={"ecolor": THEME["spine"], "elinewidth": 0.8},
    )
    ax_bar.set_xticks(x)
    ax_bar.set_xticklabels(detectors)
    ax_bar.set_ylabel("Mean ROC-AUC  (across sources, methods, payloads)")
    ax_bar.set_ylim(0.45, 1.02)
    ax_bar.set_title("Mean AUC: Plain vs. Encrypted")
    ax_bar.legend(loc="lower right")
    ax_bar.grid(axis="y", alpha=0.4)

    fig.suptitle(
        "Exp 5 — Encryption Effect on Detectability  (Sanity Check)\n"
        r"Expectation: $\Delta \approx 0$  (AES-256-CBC payloads ≈ uniform random bits)"
        "  ·  $\\ast$ marks $p < 0.05$",
        fontsize=12,
        fontweight="bold",
    )
    _save_fig(fig, out_path)

    # ── Source × Encryption interaction (separate figure) ───────────────────
    _plot_exp5_interaction(results, detectors, figures_dir)

    return out_path


def _plot_exp5_interaction(
    results: list[dict], detectors: list[str], figures_dir: Path,
) -> Path:
    """Source × encryption interaction: does encryption hurt real and ML alike?

    Interaction term per (detector, method, payload):
        ΔΔ = Δ_real − mean(Δ_ml_a, Δ_ml_b)
    where each Δ_source = AUC(plain) − AUC(encrypted) for that source.
    Under the proposal's null (encryption ≈ random bits) we expect ΔΔ ≈ 0
    *and* no source-specific encryption effect.
    """
    out_path = figures_dir / "exp5_source_x_encryption.png"

    # Index per-stratum Δ-AUC by source.
    by_key: dict[tuple[str, str, str, str], dict] = {}
    for r in results:
        if r.get("diff") is None:
            continue
        by_key[(r["detector"], r["method"], r["payload_level"], r["source"])] = r

    interaction: list[dict] = []
    for detector in detectors:
        for method in sorted({k[1] for k in by_key if k[0] == detector}):
            for payload_level in sorted({
                k[2] for k in by_key if k[0] == detector and k[1] == method
            }):
                real_row = by_key.get((detector, method, payload_level, "real"))
                ml_a_row = by_key.get((detector, method, payload_level, "ml_a"))
                ml_b_row = by_key.get((detector, method, payload_level, "ml_b"))
                if real_row is None:
                    continue
                ml_rows = [r for r in (ml_a_row, ml_b_row) if r is not None]
                if not ml_rows:
                    continue
                ml_mean = mean(r["diff"] for r in ml_rows)
                ml_var = sum(((r.get("se") or 0.0) ** 2) for r in ml_rows) / max(
                    len(ml_rows) ** 2, 1
                )
                diff = real_row["diff"] - ml_mean
                se = math.sqrt(max((real_row.get("se") or 0.0) ** 2 + ml_var, 0.0))
                ci_lo = diff - 1.96 * se
                ci_hi = diff + 1.96 * se
                z_val = diff / se if se > 1e-12 else 0.0
                p_value = (
                    2.0 * (1.0 - stats.norm.cdf(abs(z_val))) if se > 1e-12 else 1.0
                )
                interaction.append({
                    "label": f"{detector} / {method} / {payload_level}",
                    "_detector": detector,
                    "diff": diff, "se": se,
                    "ci_lo": ci_lo, "ci_hi": ci_hi,
                    "z": z_val, "p": p_value,
                })

    if not interaction:
        _write_placeholder_plot(
            out_path, "Exp 5 — Source × Encryption Interaction",
            "Insufficient overlapping data for source-specific encryption deltas.",
        )
        return out_path

    # Right panel: per-detector + overall meta-analytic diamond.
    summary: list[dict] = []
    for detector in detectors:
        det_rows = [r for r in interaction if r["_detector"] == detector]
        d = _meta_diamond(det_rows)
        if d is not None:
            summary.append({"label": f"{detector}  ⟨meta⟩", **d})
    overall = _meta_diamond(interaction)
    if overall is not None:
        summary.insert(0, {"label": "All detectors  (meta-analytic)", **overall})

    fig, axes = plt.subplots(
        1, 2,
        figsize=(14, max(3.5, len(interaction) * 0.45 + 1.8)),
        gridspec_kw={"width_ratios": [1.4, 1.0], "wspace": 0.55},
    )
    _forest_plot(
        axes[0], interaction,
        r"Interaction  $\Delta\Delta = \Delta_{real} - \bar{\Delta}_{ML}$",
        color=THEME["ns"], sig_color=THEME["sig"],
    )
    axes[0].set_title("Per-stratum source × encryption interaction")

    if summary:
        _forest_plot(
            axes[1], summary,
            r"Pooled  $\Delta\Delta$",
            color=THEME["ns"], sig_color=THEME["sig"],
        )
        axes[1].set_title("Meta-analytic summary")
    else:
        axes[1].axis("off")

    fig.suptitle(
        "Exp 5 — Source × Encryption Interaction\n"
        r"$\Delta\Delta \approx 0$ under the proposal's null  ·  "
        r"large $|\Delta\Delta|$ implies a source-specific encryption signature",
        fontsize=12, fontweight="bold",
    )
    _save_fig(fig, out_path)
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
        _write_placeholder_plot(
            fig_path, "AUC by Source and Detector", "No source_metrics data available."
        )
        return fig_path

    det_sorted = sorted(detectors)
    src_sorted = sorted(sources)
    x = list(range(len(det_sorted)))
    width = 0.78 / max(len(src_sorted), 1)

    fig, ax = plt.subplots(figsize=(10.5, 4.6))
    for i, source in enumerate(src_sorted):
        values = [
            mean(grouped[(det, source)]) if (det, source) in grouped else 0.0
            for det in det_sorted
        ]
        shift = (i - (len(src_sorted) - 1) / 2.0) * width
        ax.bar(
            [v + shift for v in x],
            values,
            width=width,
            label=source,
            color=SOURCE_COLORS.get(source, THEME["neutral"]),
            edgecolor="white",
            linewidth=0.8,
            alpha=0.92,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(det_sorted)
    ax.set_ylim(0.0, 1.02)
    ax.set_ylabel("ROC-AUC")
    ax.set_title("ROC-AUC by Detector and Source")
    ax.legend(title="Source", loc="lower right")
    ax.grid(axis="y", alpha=0.4)
    _save_fig(fig, fig_path)
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
        _write_placeholder_plot(
            fig_path,
            "AUC by Method and Detector",
            "No condition_metrics data available.",
        )
        return fig_path

    det_sorted = sorted(detectors)
    method_sorted = sorted(methods)
    x = list(range(len(det_sorted)))
    width = 0.78 / max(len(method_sorted), 1)

    fig, ax = plt.subplots(figsize=(10.5, 4.6))
    for i, method in enumerate(method_sorted):
        values = [
            mean(grouped[(det, method)]) if (det, method) in grouped else 0.0
            for det in det_sorted
        ]
        shift = (i - (len(method_sorted) - 1) / 2.0) * width
        ax.bar(
            [v + shift for v in x],
            values,
            width=width,
            label=method,
            color=METHOD_COLORS.get(method, THEME["neutral"]),
            edgecolor="white",
            linewidth=0.8,
            alpha=0.92,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(det_sorted)
    ax.set_ylim(0.0, 1.02)
    ax.set_ylabel("ROC-AUC")
    ax.set_title("ROC-AUC by Detector and Embedding Method")
    ax.legend(title="Method", loc="lower right")
    ax.grid(axis="y", alpha=0.4)
    _save_fig(fig, fig_path)
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


def _plot_roc_condition_panels(
    predictions: list[dict],
    figures_dir: Path,
) -> dict[str, Path]:
    """Emit one ROC PNG per (detector, method, payload, encryption) stratum.

    Files land in ``figures_dir/roc_panels/`` with stable, slugified names.
    Returns a dict mapping figure key → path so the runner can list them.
    """
    panels_dir = figures_dir / "roc_panels"
    panels_dir.mkdir(parents=True, exist_ok=True)

    strata = sorted(
        {
            (r["detector"], r["method"], r["payload_level"], r["encryption"])
            for r in predictions
        }
    )
    out: dict[str, Path] = {}
    if not strata:
        placeholder = panels_dir / "no_data.png"
        _write_placeholder_plot(
            placeholder, "Per-Condition ROC Curves", "No prediction data available."
        )
        out["roc_panel_no_data"] = placeholder
        return out

    for detector, method, payload_level, encryption in strata:
        slug = f"{detector}__{method}__{payload_level}__{encryption}".replace("/", "-")
        fig_path = panels_dir / f"{slug}.png"

        fig, ax = plt.subplots(figsize=(5.0, 4.4))
        any_curve = False
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
            if not fprs:
                continue
            any_curve = True
            auc, _var = _auc_var_for_rows(rows)
            label = f"{source}  (AUC={auc:.3f})" if auc is not None else source
            ax.plot(
                fprs,
                tprs,
                label=label,
                color=SOURCE_COLORS.get(source, THEME["neutral"]),
                linewidth=2.0,
                alpha=0.92,
            )

        ax.plot(
            [0, 1],
            [0, 1],
            color=THEME["muted"],
            linestyle="--",
            linewidth=0.9,
            alpha=0.7,
            label="chance",
        )
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1.02)
        ax.set_xlabel("False Positive Rate")
        ax.set_ylabel("True Positive Rate")
        ax.set_aspect("equal", adjustable="box")
        ax.set_title(
            f"{detector}\n{method} · {payload_level} · {encryption}",
            fontsize=10,
        )
        ax.legend(loc="lower right")
        ax.grid(alpha=0.4)

        if not any_curve:
            ax.text(
                0.5,
                0.5,
                "no curves available",
                ha="center",
                va="center",
                transform=ax.transAxes,
                color=THEME["muted"],
                style="italic",
            )

        _save_fig(fig, fig_path)
        out[f"roc_panel_{slug}"] = fig_path

    out["roc_panels_dir"] = panels_dir
    return out


def _plot_quality_summary(metrics_dir: Path, figures_dir: Path) -> Path:
    """Stego/cover quality across PSNR, SSIM, FSIM (proposal mandate).

    Three stacked panels share x-axis (method × payload). Each bar shows the
    median value with an IQR error bar so the figure is robust to outliers
    introduced by occasional embedding failures.
    """
    out_path = figures_dir / "quality_summary.png"
    rows = _read_csv_rows(metrics_dir / "quality_metrics.csv")

    metric_specs = [
        ("psnr", "PSNR (dB)"),
        ("ssim", "SSIM"),
        ("fsim", "FSIM"),
    ]
    values: dict[str, dict[tuple[str, str], list[float]]] = {
        m: defaultdict(list) for m, _ in metric_specs
    }

    for row in rows:
        method = row.get("method", "")
        payload_level = row.get("payload_level", "")
        if not method or not payload_level:
            continue
        for metric, _label in metric_specs:
            v = _maybe_float(row.get(metric))
            if v is not None:
                values[metric][(method, payload_level)].append(v)

    available = [m for m, _ in metric_specs if values[m]]
    if not available:
        _write_placeholder_plot(
            out_path, "Quality Summary",
            "No PSNR / SSIM / FSIM data available in quality_metrics.csv.",
        )
        return out_path

    keys = sorted({k for m in available for k in values[m].keys()})
    labels = [f"{method}\n{payload}" for method, payload in keys]
    bar_colors = [METHOD_COLORS.get(method, THEME["neutral"]) for method, _ in keys]
    x = np.arange(len(keys))

    n_panels = len(available)
    fig, axes = plt.subplots(
        n_panels, 1,
        figsize=(max(8, len(keys) * 1.0), 2.6 * n_panels + 0.6),
        sharex=True,
        gridspec_kw={"hspace": 0.28},
    )
    if n_panels == 1:
        axes = [axes]

    for ax, metric in zip(axes, available):
        med, lo, hi = [], [], []
        ymin = math.inf
        for key in keys:
            vals = values[metric].get(key, [])
            if not vals:
                med.append(0.0); lo.append(0.0); hi.append(0.0)
                continue
            arr = np.array(vals, dtype=float)
            m = float(np.median(arr))
            q1 = float(np.percentile(arr, 25))
            q3 = float(np.percentile(arr, 75))
            med.append(m)
            lo.append(max(m - q1, 0.0))
            hi.append(max(q3 - m, 0.0))
            ymin = min(ymin, q1)
        yerr = np.array([lo, hi])
        ax.bar(
            x, med, yerr=yerr,
            color=bar_colors, edgecolor="white", linewidth=0.8, alpha=0.92,
            capsize=3,
            error_kw={"ecolor": THEME["spine"], "elinewidth": 0.8},
        )
        label = next(L for m, L in metric_specs if m == metric)
        ax.set_ylabel(f"Median {label}\n(IQR error bars)")
        ax.grid(axis="y", alpha=0.4)
        if metric == "psnr":
            # Add a horizontal reference at 40 dB (publication-quality threshold).
            ax.axhline(40.0, color=THEME["muted"], linestyle=":", linewidth=0.8)
        elif metric in ("ssim", "fsim"):
            ax.set_ylim(min(0.9, ymin - 0.005), 1.005)

    axes[-1].set_xticks(x)
    axes[-1].set_xticklabels(labels)
    axes[0].set_title("Embedding Quality Summary by Method and Payload")
    _save_fig(fig, out_path)
    return out_path


def _collect_exp3_payload_interaction(predictions: list[dict]) -> list[dict]:
    """Per (detector, method, source, payload_level) AUC + 95% CI and per-stratum source gap.

    The Exp 3 forest in plots.py renders the per-source AUC trajectory across
    payload levels. The corresponding tabular export captures the underlying
    numbers — AUC, SE, CI bounds, n — plus the real-vs-pooled-ML source gap.
    """
    rows: list[dict] = []
    if not predictions:
        return rows
    sources = sorted({r["source"] for r in predictions})
    strata = sorted({(r["detector"], r["method"], r["payload_level"]) for r in predictions})

    auc_index: dict[tuple[str, str, str, str], tuple[float | None, float | None, int, int]] = {}
    for detector, method, payload_level in strata:
        for source in sources:
            sel = _filter_preds(
                predictions, detector=detector, source=source,
                method=method, payload_level=payload_level,
            )
            pos, neg = _pos_neg(sel)
            auc, V10, V01 = _delong_components(pos, neg)
            if auc is None:
                auc_index[(detector, method, source, payload_level)] = (None, None, len(pos), len(neg))
                continue
            se = float(np.sqrt(max(_delong_var(V10, V01), 0.0)))
            auc_index[(detector, method, source, payload_level)] = (auc, se, len(pos), len(neg))

    for detector, method, payload_level in strata:
        for source in sources:
            auc, se, n_pos, n_neg = auc_index[(detector, method, source, payload_level)]
            real_auc, *_ = auc_index.get((detector, method, "real", payload_level), (None, None, 0, 0))
            ml_aucs = [
                auc_index.get((detector, method, s, payload_level), (None,))[0]
                for s in ("ml_a", "ml_b")
            ]
            ml_aucs = [v for v in ml_aucs if v is not None]
            gap = (real_auc - mean(ml_aucs)) if (real_auc is not None and ml_aucs) else None
            rows.append({
                "experiment": "exp3_rq3_payload_interaction",
                "detector": detector,
                "method": method,
                "source": source,
                "payload_level": payload_level,
                "auc": auc,
                "se": se,
                "ci_lo": (auc - 1.96 * se) if (auc is not None and se is not None) else None,
                "ci_hi": (auc + 1.96 * se) if (auc is not None and se is not None) else None,
                "n_pos": n_pos,
                "n_neg": n_neg,
                "real_minus_ml_gap": gap,
            })
    return rows


def _collect_exp4_branch_interaction(predictions: list[dict]) -> list[dict]:
    """Per (detector, payload_level): ΔΔ = gap_spatial − gap_frequency with a Wald CI.

    Mirrors the data computed inside ``_plot_exp4``. Each row records both
    per-branch source gaps and their interaction so the report can quote
    numbers directly without re-deriving them from the figure.
    """
    rows: list[dict] = []
    if not predictions:
        return rows
    methods = {r["method"] for r in predictions}
    spatial = sorted(m for m in methods if "lsb" in m.lower() and "dct" not in m.lower())
    frequency = sorted(m for m in methods if "dct" in m.lower())
    if not spatial or not frequency:
        return rows
    sp_method, fr_method = spatial[0], frequency[0]
    PAYLOAD_ORDER = ("low", "medium", "high")
    payload_levels = [pl for pl in PAYLOAD_ORDER if any(r["payload_level"] == pl for r in predictions)]
    detectors = sorted({r["detector"] for r in predictions})

    for detector in detectors:
        for payload_level in payload_levels:
            sp_gap = _source_gap_stats(
                predictions, detector=detector,
                method=sp_method, payload_level=payload_level,
            )
            fr_gap = _source_gap_stats(
                predictions, detector=detector,
                method=fr_method, payload_level=payload_level,
            )
            if sp_gap.get("diff") is None or fr_gap.get("diff") is None:
                continue
            diff = sp_gap["diff"] - fr_gap["diff"]
            se = math.sqrt(max(
                (sp_gap.get("se") or 0.0) ** 2 + (fr_gap.get("se") or 0.0) ** 2, 0.0,
            ))
            z_val = diff / se if se > 1e-12 else 0.0
            p_value = 2.0 * (1.0 - stats.norm.cdf(abs(z_val))) if se > 1e-12 else 1.0
            rows.append({
                "experiment": "exp4_rq4_spatial_vs_frequency",
                "detector": detector,
                "payload_level": payload_level,
                "spatial_method": sp_method,
                "frequency_method": fr_method,
                "gap_spatial": sp_gap["diff"],
                "gap_frequency": fr_gap["diff"],
                "diff": diff,
                "se": se,
                "ci_lo": diff - 1.96 * se,
                "ci_hi": diff + 1.96 * se,
                "z": z_val,
                "p": p_value,
            })
    return rows


def _collect_exp5_source_x_encryption(exp5_per_stratum_rows: list[dict]) -> list[dict]:
    """Per (detector, method, payload_level): ΔΔ = Δ_real − mean(Δ_ml_a, Δ_ml_b).

    Consumes the already-computed paired DeLong rows from Exp 5 (one row per
    (detector, source, method, payload_level)) and synthesises the source ×
    encryption interaction term used by ``_plot_exp5_interaction``.
    """
    rows: list[dict] = []
    by_key: dict[tuple[str, str, str, str], dict] = {}
    for r in exp5_per_stratum_rows:
        if r.get("diff") is None:
            continue
        by_key[(r["detector"], r["method"], r["payload_level"], r["source"])] = r
    detectors = sorted({k[0] for k in by_key})
    methods = sorted({k[1] for k in by_key})
    payload_levels = sorted({k[2] for k in by_key})
    for detector in detectors:
        for method in methods:
            for payload_level in payload_levels:
                real_row = by_key.get((detector, method, payload_level, "real"))
                ml_a_row = by_key.get((detector, method, payload_level, "ml_a"))
                ml_b_row = by_key.get((detector, method, payload_level, "ml_b"))
                if real_row is None:
                    continue
                ml_rows = [r for r in (ml_a_row, ml_b_row) if r is not None]
                if not ml_rows:
                    continue
                ml_mean = mean(r["diff"] for r in ml_rows)
                ml_var = sum(((r.get("se") or 0.0) ** 2) for r in ml_rows) / max(len(ml_rows) ** 2, 1)
                diff = real_row["diff"] - ml_mean
                se = math.sqrt(max((real_row.get("se") or 0.0) ** 2 + ml_var, 0.0))
                z_val = diff / se if se > 1e-12 else 0.0
                p_value = 2.0 * (1.0 - stats.norm.cdf(abs(z_val))) if se > 1e-12 else 1.0
                rows.append({
                    "experiment": "exp5_rq5_source_x_encryption",
                    "detector": detector,
                    "method": method,
                    "payload_level": payload_level,
                    "delta_real": real_row["diff"],
                    "delta_ml_mean": ml_mean,
                    "diff": diff,
                    "se": se,
                    "ci_lo": diff - 1.96 * se,
                    "ci_hi": diff + 1.96 * se,
                    "z": z_val,
                    "p": p_value,
                })
    return rows


_SUMMARY_FIELDS = (
    "experiment", "detector", "method", "payload_level", "source", "encryption",
    "n_pos_a", "n_neg_a", "n_pos_b", "n_neg_b",
    "auc_a", "auc_b", "diff", "se", "ci_lo", "ci_hi", "z", "p", "p_holm",
    "significant_holm_0_05",
)


def _summarise_for_master(experiment: str, rows: list[dict]) -> list[dict]:
    """Project per-experiment rows down to the consolidated summary schema."""
    out: list[dict] = []
    for r in rows:
        out.append({field: r.get(field) for field in _SUMMARY_FIELDS} | {"experiment": experiment})
    return out


def _write_experiment_contrast_tables(
    metrics_dir: Path, predictions: list[dict]
) -> dict[str, Path]:
    outputs: dict[str, Path] = {}
    if not predictions:
        return outputs

    strata = sorted(
        {(r["detector"], r["method"], r["payload_level"]) for r in predictions}
    )

    # ── Exp 1: real vs pooled ML, per stratum (DeLong + Holm) ───────────────
    exp1_rows: list[dict] = []
    for detector, method, payload_level in strata:
        real_rows = _filter_preds(
            predictions, detector=detector, source="real",
            method=method, payload_level=payload_level,
        )
        ml_rows = _filter_preds(
            predictions, detector=detector, source="ml_a",
            method=method, payload_level=payload_level,
        ) + _filter_preds(
            predictions, detector=detector, source="ml_b",
            method=method, payload_level=payload_level,
        )
        stat = _delong_compare(*_pos_neg(real_rows), *_pos_neg(ml_rows), paired=False)
        exp1_rows.append({
            "experiment": "exp1_rq1_real_vs_pooled_ml",
            "detector": detector, "method": method, "payload_level": payload_level,
            **stat,
        })
    _holm_adjust(exp1_rows)
    outputs["exp1_contrasts"] = metrics_dir / "exp1_rq1_real_vs_pooled_ml_contrasts.csv"
    _write_csv(outputs["exp1_contrasts"], exp1_rows)

    # ── Exp 2: ml_a vs ml_b per stratum (DeLong + Holm) ─────────────────────
    exp2_rows: list[dict] = []
    for detector, method, payload_level in strata:
        ml_a_rows = _filter_preds(
            predictions, detector=detector, source="ml_a",
            method=method, payload_level=payload_level,
        )
        ml_b_rows = _filter_preds(
            predictions, detector=detector, source="ml_b",
            method=method, payload_level=payload_level,
        )
        stat = _delong_compare(*_pos_neg(ml_a_rows), *_pos_neg(ml_b_rows), paired=False)
        exp2_rows.append({
            "experiment": "exp2_rq2_mla_vs_mlb",
            "detector": detector, "method": method, "payload_level": payload_level,
            **stat,
        })
    _holm_adjust(exp2_rows)
    outputs["exp2_contrasts"] = metrics_dir / "exp2_rq2_mla_vs_mlb_contrasts.csv"
    _write_csv(outputs["exp2_contrasts"], exp2_rows)

    # ── Exp 3: payload interaction (per source × payload AUC + gap) ─────────
    exp3_rows = _collect_exp3_payload_interaction(predictions)
    if exp3_rows:
        outputs["exp3_contrasts"] = metrics_dir / "exp3_rq3_payload_interaction_contrasts.csv"
        _write_csv(outputs["exp3_contrasts"], exp3_rows)

    # ── Exp 4: spatial vs frequency branch interaction ──────────────────────
    exp4_rows = _collect_exp4_branch_interaction(predictions)
    if exp4_rows:
        outputs["exp4_contrasts"] = metrics_dir / "exp4_rq4_spatial_vs_frequency_contrasts.csv"
        _write_csv(outputs["exp4_contrasts"], exp4_rows)

    # ── Exp 5: paired plain vs encrypted per (detector, source, method, payload) ──
    exp5_rows: list[dict] = []
    for detector, method, payload_level in strata:
        for source in sorted({r["source"] for r in predictions}):
            plain_rows = _filter_preds(
                predictions, detector=detector, source=source,
                method=method, payload_level=payload_level, encryption="plain",
            )
            enc_rows = _filter_preds(
                predictions, detector=detector, source=source,
                method=method, payload_level=payload_level, encryption="encrypted",
            )
            stat = _delong_compare(*_pos_neg(plain_rows), *_pos_neg(enc_rows), paired=True)
            exp5_rows.append({
                "experiment": "exp5_rq5_plain_vs_encrypted",
                "detector": detector, "source": source,
                "method": method, "payload_level": payload_level,
                **stat,
            })
    outputs["exp5_contrasts"] = metrics_dir / "exp5_rq5_encryption_contrasts.csv"
    _write_csv(outputs["exp5_contrasts"], exp5_rows)

    # ── Exp 5 interaction: ΔΔ = Δ_real − mean(Δ_ml_*) ───────────────────────
    exp5_interaction_rows = _collect_exp5_source_x_encryption(exp5_rows)
    if exp5_interaction_rows:
        outputs["exp5_interaction_contrasts"] = metrics_dir / "exp5_rq5_source_x_encryption_contrasts.csv"
        _write_csv(outputs["exp5_interaction_contrasts"], exp5_interaction_rows)

    # ── Consolidated experiments_summary.csv ────────────────────────────────
    summary_rows: list[dict] = []
    summary_rows += _summarise_for_master("exp1_rq1_real_vs_pooled_ml", exp1_rows)
    summary_rows += _summarise_for_master("exp2_rq2_mla_vs_mlb", exp2_rows)
    summary_rows += _summarise_for_master("exp3_rq3_payload_interaction", exp3_rows)
    summary_rows += _summarise_for_master("exp4_rq4_spatial_vs_frequency", exp4_rows)
    summary_rows += _summarise_for_master("exp5_rq5_plain_vs_encrypted", exp5_rows)
    summary_rows += _summarise_for_master("exp5_rq5_source_x_encryption", exp5_interaction_rows)
    if summary_rows:
        outputs["experiments_summary"] = metrics_dir / "experiments_summary.csv"
        _write_csv(outputs["experiments_summary"], summary_rows)

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

    figures.update(_plot_exp1(predictions, figures_dir))
    figures.update(_plot_exp2(predictions, figures_dir))
    figures["exp3a_payload_level"] = _plot_exp3a(predictions, figures_dir)
    figures["exp3b_bd_sens"] = _plot_exp3b(predictions, figures_dir)
    figures["exp4_branch_comparison"] = _plot_exp4(predictions, figures_dir)
    figures["exp5_encryption"] = _plot_exp5(predictions, figures_dir)
    interaction_path = figures_dir / "exp5_source_x_encryption.png"
    if interaction_path.exists():
        figures["exp5_source_x_encryption"] = interaction_path
    figures.update(_plot_roc_condition_panels(predictions, figures_dir))
    figures["quality_summary"] = _plot_quality_summary(metrics_dir, figures_dir)

    for key, path in _write_experiment_contrast_tables(
        metrics_dir, predictions
    ).items():
        figures[key] = path

    return figures
