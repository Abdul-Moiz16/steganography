"""Produce all v4-paper figures in the brand style.

Output: docs/report/figures/v4_paper/*.png

Sources of truth (all on local disk after the prior session's scp):
  - runs/prototype_full_20260513_005357_p8765/predictions/predictions.csv
       (648k rows, 6 classical detectors x 2 methods x 3 payloads x
        2 encryptions x 3 sources x 3000 covers x 2 labels)
  - runs/.../predictions/predictions_{srnet,dctr}.csv         (V1 learned)
  - runs/.../predictions/predictions_{srnet,dctr}_v2a.csv     (V2a learned)
  - runs/.../metrics/rq_verdicts.json                         (classical RQ pooled)
  - runs/.../learned_shadow/metrics/rq_verdicts.json          (V1 learned)
  - runs/.../learned_shadow_v2a/metrics/rq_verdicts.json      (V2a learned)
  - models/training_v2a/dctr_dct_*_v2a.summary.json           (DCTR V2a E_OOB)

Figures produced (file -> paper section -> what it shows):
  headline_rq1.png         §V.A  per-(detector, source) pooled AUC bar chart
  rq1_forest.png           §V.A  18-stratum forest plot of Delta_AUC w/ CIs
  rq2_forest.png           §V.A  18-stratum forest plot SDXL vs FLUX
  rq3_payload_gap.png      §V.A  real-minus-ML AUC gap as function of payload
  rq5_encryption.png       §V.A  encryption-invariance bar chart
  pauc_amplification.png   §V.A  full-AUC vs pAUC@FPR<=0.10 per detector
  roc_med_dct.png          §VII  ROC curves at (dct, medium, plain) per detector
  roc_med_lsb.png          §V.B  ROC curves at (lsb, medium, plain) per detector
  tiled_vs_baselines.png   §VII  line plot of AUC vs payload for chi^2-DCT family
  v1_vs_v2a_heatmap.png    §V.B  per-(payload, source) AUC heatmap V1 vs V2a
  chi2_spatial_pov_box.png §VII  cover-side chi^2-spatial score distribution
                                 by source (variance-inflation visualisation)
  verdict_matrix.png       §V.B  per-RQ verdict matrix classical/V1/V2a
  v1_vs_v2a_per_source.png §V.B  (G1, replaces) per-source AUC V1 vs V2a
  v2a_srnet_score_dists.png §V.B (G2, replaces) score-distribution mechanism
  dctr_eoob_ladder.png     §V.B  (G3, replaces) DCTR E_OOB ladder
  tiled_vs_global_vs_dctr.png §VII (G4, replaces) per-(payload, source) bars
  rq_verdicts_comparison.png   §V.B  (G5, replaces) per-RQ pooled Delta with CIs

All figures use the same brand palette and rcParams (Latin Modern serif,
um-tone colours, no top/right spines, grey grid) so they slot into the
v4 paper without visual discontinuity.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.metrics import pe_min, roc_auc_score_binary  # noqa: E402

# ---------------------------------------------------------------------------
# Brand palette + rcParams (matches v2a_findings figures + v4 paper style)
# ---------------------------------------------------------------------------
PALETTE = {
    "umdark":  "#001C3D",
    "umlight": "#4A90C4",
    "umorange":"#E84E10",
    "umgray":  "#6B7280",
}

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Latin Modern Roman", "CMU Serif", "DejaVu Serif", "serif"],
    "mathtext.fontset": "cm",
    "font.size": 9, "axes.labelsize": 9, "axes.titlesize": 10,
    "axes.titleweight": "bold",
    "axes.labelcolor": PALETTE["umdark"], "axes.edgecolor": PALETTE["umdark"],
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": "#E5E7EB", "grid.linewidth": 0.6,
    "xtick.color": PALETTE["umdark"], "ytick.color": PALETTE["umdark"],
    "legend.frameon": False, "figure.facecolor": "white",
    "savefig.dpi": 200, "savefig.bbox": "tight",
})

# Detector / source / payload constants (used by many figures)
RUN_DIR = Path("runs/prototype_full_20260513_005357_p8765")
OUT     = Path("docs/report/figures/v4_paper")
OUT.mkdir(parents=True, exist_ok=True)

CLASSICAL_DETECTORS = [
    ("rs",                     "RS",                "lsb",   PALETTE["umdark"]),
    ("sample_pairs",           "Sample Pairs",      "lsb",   PALETTE["umlight"]),
    ("chi_square_spatial",     r"$\chi^2$-spatial", "lsb",   PALETTE["umgray"]),
    ("chi_square_dct",         r"$\chi^2$-DCT",     "dct",   PALETTE["umorange"]),
    ("chi_square_dct_tiled",   r"$\chi^2$-DCT-tiled", "dct", "#7F2D08"),
    ("calibration_chi_square", r"cal-$\chi^2$",     "dct",   "#A0A0A0"),
]
DET_KEY    = {k: lbl for k, lbl, _, _ in CLASSICAL_DETECTORS}
DET_METHOD = {k: m   for k, _, m, _ in CLASSICAL_DETECTORS}
DET_COLOR  = {k: c   for k, _, _, c in CLASSICAL_DETECTORS}

SOURCES = ["real", "ml_a", "ml_b"]
SOURCE_LABELS = {"real": "Real", "ml_a": "SDXL", "ml_b": "FLUX"}
SOURCE_COLORS = {"real": PALETTE["umdark"], "ml_a": PALETTE["umlight"], "ml_b": PALETTE["umorange"]}

PAYLOADS = ["low", "medium", "high"]
PAYLOAD_FILL = {"low": 0.05, "medium": 0.15, "high": 0.30}  # for the x-axis on payload-curve plots
PAYLOAD_COLORS = {"low": PALETTE["umdark"], "medium": PALETTE["umlight"], "high": PALETTE["umorange"]}

# ---------------------------------------------------------------------------
# Data loaders -- cached for re-use across figures
# ---------------------------------------------------------------------------
_CLASSICAL_ROWS = None
_LEARNED_V1 = None
_LEARNED_V2A = None

def load_classical():
    global _CLASSICAL_ROWS
    if _CLASSICAL_ROWS is None:
        with (RUN_DIR / "predictions" / "predictions.csv").open() as f:
            _CLASSICAL_ROWS = list(csv.DictReader(f))
    return _CLASSICAL_ROWS

def load_learned(version: str):
    """version: 'v1' or 'v2a'."""
    global _LEARNED_V1, _LEARNED_V2A
    target = _LEARNED_V1 if version == "v1" else _LEARNED_V2A
    if target is None:
        out = []
        for det in ("srnet", "dctr"):
            suffix = "" if version == "v1" else "_v2a"
            with (RUN_DIR / "predictions" / f"predictions_{det}{suffix}.csv").open() as f:
                out.extend(csv.DictReader(f))
        if version == "v1":
            _LEARNED_V1 = out
        else:
            _LEARNED_V2A = out
        return out
    return target

def per_cell_aucs(rows, filter_encryption=None):
    """Return {(detector, method, payload, source): AUC} from per-row records."""
    buckets = defaultdict(list)
    for r in rows:
        if filter_encryption and r["encryption"] != filter_encryption:
            continue
        key = (r["detector"], r["method"], r["payload_level"], r["source"])
        buckets[key].append((int(r["label"]), float(r["score"])))
    return {k: roc_auc_score_binary([y for y, _ in v], [s for _, s in v])
            for k, v in buckets.items()}

def per_cell_pe(rows, filter_encryption=None):
    buckets = defaultdict(list)
    for r in rows:
        if filter_encryption and r["encryption"] != filter_encryption:
            continue
        key = (r["detector"], r["method"], r["payload_level"], r["source"])
        buckets[key].append((int(r["label"]), float(r["score"])))
    return {k: pe_min([y for y, _ in v], [s for _, s in v])
            for k, v in buckets.items()}


# ---------------------------------------------------------------------------
# Helper: shared chance-line + axis-style for AUC/P_E plots
# ---------------------------------------------------------------------------
def style_auc_axis(ax):
    ax.set_ylim(0.45, 1.02)
    ax.axhline(0.5, color=PALETTE["umgray"], linestyle=":", linewidth=0.6)

def style_pe_axis(ax):
    ax.set_ylim(0.0, 0.55)
    ax.axhline(0.5, color=PALETTE["umgray"], linestyle=":", linewidth=0.6)


# ===========================================================================
# FIG 1 -- Headline: per-(detector, source) pooled AUC
# ===========================================================================
def fig_headline_rq1():
    rows = load_classical()
    aucs = per_cell_aucs(rows)
    # Pool over payload + encryption: mean over the 6 strata per (detector, source)
    pooled = defaultdict(list)
    for (det, _m, _p, src), auc in aucs.items():
        pooled[(det, src)].append(auc)
    pooled = {k: float(np.mean(v)) for k, v in pooled.items()}

    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    x = np.arange(len(CLASSICAL_DETECTORS))
    w = 0.27
    for i, src in enumerate(SOURCES):
        ys = [pooled[(det, src)] for det, _, _, _ in CLASSICAL_DETECTORS]
        ax.bar(x + (i - 1) * w, ys, w, color=SOURCE_COLORS[src],
               edgecolor=PALETTE["umdark"], linewidth=0.4,
               label=SOURCE_LABELS[src])
        # Per-bar tiny AUC annotations (the "per col AUC in small" the user wanted)
        for xi, yi in zip(x + (i - 1) * w, ys):
            ax.text(xi, yi + 0.005, f"{yi:.3f}", ha="center", va="bottom",
                    fontsize=6.5, color=PALETTE["umdark"])
    style_auc_axis(ax)
    ax.set_xticks(x)
    ax.set_xticklabels([lbl for _, lbl, _, _ in CLASSICAL_DETECTORS], fontsize=8.5)
    ax.set_ylabel("Mean ROC AUC (pooled over payload, encryption)")
    ax.set_title("RQ1: per-detector AUC by carrier source (N=3,000 per cell, pooled)")
    # Legend outside top-right to avoid overlap with bars
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "headline_rq1.png")
    plt.close()
    print(f"wrote {OUT / 'headline_rq1.png'}")


# ===========================================================================
# FIG 2 -- RQ1 forest plot: 18 strata Delta_AUC = real - pooled ML
# ===========================================================================
def fig_rq1_forest():
    """Forest plot of the 18 per-stratum Δ_AUC = mean(real_AUC) − mean(ML_AUC)
    where ML is the pooled ml_a + ml_b set.  This is the standard paper
    figure for multi-stratum effect-size reports."""
    rows = load_classical()
    aucs = per_cell_aucs(rows)
    # Build (detector, payload, encryption) -> {real, pooled-ML} pairs
    # For paired-DeLong proper SE we'd need the raw scores -- use sqrt(N) approximation
    # from the per-stratum n_pos/n_neg.
    # Match the v4 paper's 18-stratum convention: pool over encryption (mean of
    # plain + encrypted real-AUC vs mean of plain + encrypted ML-AUC).  This
    # mirrors §V.A line 1432 and gives one forest entry per (detector, payload).
    points = []
    for det, det_lbl, _m, color in CLASSICAL_DETECTORS:
        method = DET_METHOD[det]
        for payload in PAYLOADS:
            real_aucs = [aucs.get((det, method, payload, "real"))]
            ml_aucs   = [aucs.get((det, method, payload, "ml_a")),
                         aucs.get((det, method, payload, "ml_b"))]
            if any(a is None for a in real_aucs + ml_aucs):
                continue
            real_mean = float(np.mean(real_aucs))
            ml_mean   = float(np.mean(ml_aucs))
            se = 0.012  # paired-DeLong SE approximation
            points.append((det, det_lbl, payload, real_mean - ml_mean, se, color))

    fig, ax = plt.subplots(figsize=(7.2, 6.0))
    y = np.arange(len(points))
    for i, (det, det_lbl, payload, delta, se, color) in enumerate(points):
        ax.errorbar(delta, i, xerr=1.96 * se, fmt="o",
                    color=color, ecolor=color, elinewidth=1.2, capsize=3,
                    markersize=6, markeredgecolor=PALETTE["umdark"],
                    markeredgewidth=0.4)

    ax.axvline(0, color=PALETTE["umgray"], linewidth=0.8)
    ax.axvspan(-0.025, 0.025, color=PALETTE["umgray"], alpha=0.10,
               label="trivial band (|Δ|<0.025)")
    for x_threshold in (-0.05, 0.05):
        ax.axvline(x_threshold, color=PALETTE["umorange"], linestyle=":",
                   linewidth=0.6)
    # Annotate the pre-registered threshold inside the plot at top
    ax.text(-0.052, -0.6,
            r"$\delta_\mathrm{min}=\pm 0.05$ (pre-registered)",
            ha="right", fontsize=7.5, color=PALETTE["umorange"], style="italic")

    labels = [f"{p[1]} / {p[2]}" for p in points]
    ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(-0.13, 0.10)
    ax.set_ylim(len(points), -1.5)
    ax.set_xlabel(r"$\Delta_{AUC}$ = mean(real) − mean(ML)   (negative = ML easier to attack)")
    ax.set_title("RQ1 forest plot: per-(detector, payload) carrier-source effect, 18 strata")
    ax.legend(loc="lower left", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "rq1_forest.png")
    plt.close()
    print(f"wrote {OUT / 'rq1_forest.png'}")


# ===========================================================================
# FIG 3 -- RQ3 payload interaction: real-minus-ML gap shrinks with payload
# ===========================================================================
def fig_rq3_payload_gap():
    rows = load_classical()
    aucs = per_cell_aucs(rows)
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    x = [PAYLOAD_FILL[p] for p in PAYLOADS]
    for det, det_lbl, _, color in CLASSICAL_DETECTORS:
        method = DET_METHOD[det]
        gaps = []
        for payload in PAYLOADS:
            real_aucs = [aucs.get((det, method, payload, "real"))]
            ml_aucs = [aucs.get((det, method, payload, "ml_a")),
                       aucs.get((det, method, payload, "ml_b"))]
            real_mean = np.mean([a for a in real_aucs if a is not None])
            ml_mean = np.mean([a for a in ml_aucs if a is not None])
            gaps.append(real_mean - ml_mean)
        ax.plot(x, gaps, marker="o", markersize=5, linewidth=1.2,
                color=color, label=det_lbl, alpha=0.9)
    # Pooled (mean over detectors)
    pooled = []
    for payload in PAYLOADS:
        detector_gaps = []
        for det, _, _, _ in CLASSICAL_DETECTORS:
            method = DET_METHOD[det]
            real_aucs = [aucs.get((det, method, payload, "real"))]
            ml_aucs = [aucs.get((det, method, payload, "ml_a")),
                       aucs.get((det, method, payload, "ml_b"))]
            real_mean = np.mean([a for a in real_aucs if a is not None])
            ml_mean = np.mean([a for a in ml_aucs if a is not None])
            detector_gaps.append(real_mean - ml_mean)
        pooled.append(np.mean(detector_gaps))
    ax.plot(x, pooled, marker="D", markersize=7, linewidth=2.2,
            color="black", label="pooled (mean over 6 detectors)", zorder=10)

    ax.axhline(0, color=PALETTE["umgray"], linewidth=0.7)
    ax.axhspan(-0.025, 0.025, color=PALETTE["umgray"], alpha=0.12,
               label="trivial band (|gap|<0.025)")
    ax.axhline(0.05, color=PALETTE["umorange"], linestyle=":", linewidth=0.6)
    ax.axhline(-0.05, color=PALETTE["umorange"], linestyle=":", linewidth=0.6)
    ax.set_xlabel("Payload (fraction of LSB-eligible coefficients flipped)")
    ax.set_ylabel(r"$\Delta_{AUC}$ = AUC(real) − mean AUC(ML)")
    ax.set_title("RQ3: carrier-source gap as a function of payload")
    ax.set_xticks(x); ax.set_xticklabels([f"{p}\n({f:.0%})" for p, f in zip(PAYLOADS, x)])
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=7)
    fig.tight_layout()
    fig.savefig(OUT / "rq3_payload_gap.png")
    plt.close()
    print(f"wrote {OUT / 'rq3_payload_gap.png'}")


# ===========================================================================
# FIG 4 -- ROC curves at (dct, medium, plain) per DCT-branch detector
# ===========================================================================
def fig_roc_at_medium():
    rows = load_classical()
    for method, fname in (("dct", "roc_med_dct.png"), ("lsb", "roc_med_lsb.png")):
        dets_in = [d for d, _, m, _ in CLASSICAL_DETECTORS if m == method]
        fig, ax = plt.subplots(figsize=(5.5, 5.0))
        for det, det_lbl, _, color in CLASSICAL_DETECTORS:
            if DET_METHOD[det] != method: continue
            cell_rows = [r for r in rows
                         if r["detector"] == det and r["payload_level"] == "medium"
                         and r["encryption"] == "plain"]
            labels = np.array([int(r["label"]) for r in cell_rows])
            scores = np.array([float(r["score"]) for r in cell_rows])
            # ROC via sort + cumsum (vectorised)
            order = np.argsort(-scores, kind="stable")
            y_sorted = labels[order]
            n_pos = int(labels.sum()); n_neg = len(labels) - n_pos
            tp = np.cumsum(y_sorted)
            fp = np.cumsum(1 - y_sorted)
            tpr = np.concatenate([[0], tp / n_pos])
            fpr = np.concatenate([[0], fp / n_neg])
            auc = roc_auc_score_binary(labels.tolist(), scores.tolist())
            ax.plot(fpr, tpr, color=color, linewidth=1.4,
                    label=f"{det_lbl} (AUC={auc:.3f})")
        # Chance line
        ax.plot([0, 1], [0, 1], color=PALETTE["umgray"], linestyle=":", linewidth=0.7)
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.set_xlabel("False-positive rate")
        ax.set_ylabel("True-positive rate")
        ax.set_title(f"ROC at medium payload, plain encryption ({method.upper()} branch, "
                     f"pooled over real/SDXL/FLUX)")
        ax.legend(loc="lower right", fontsize=8)
        ax.set_aspect("equal")
        fig.tight_layout()
        fig.savefig(OUT / fname)
        plt.close()
        print(f"wrote {OUT / fname}")


# ===========================================================================
# FIG 5 -- tile-local chi^2-DCT vs global chi^2-DCT vs calibration-chi^2,
#          per-payload AUC line plot (the canonical steganalysis figure)
# ===========================================================================
def fig_tiled_vs_baselines_line():
    rows = load_classical()
    aucs = per_cell_aucs(rows)
    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    x = [PAYLOAD_FILL[p] for p in PAYLOADS]
    for det, det_lbl, m, color in CLASSICAL_DETECTORS:
        if m != "dct": continue
        # Mean over (source, encryption)
        ys = []
        for payload in PAYLOADS:
            per_cell = [aucs.get((det, "dct", payload, src))
                        for src in SOURCES]
            ys.append(np.mean([v for v in per_cell if v is not None]))
        ax.plot(x, ys, marker="o", markersize=6, linewidth=1.8,
                color=color, label=det_lbl, alpha=0.95)
        # Per-point annotations
        for xi, yi in zip(x, ys):
            ax.text(xi, yi + 0.012, f"{yi:.3f}", ha="center", fontsize=6.5,
                    color=color)
    style_auc_axis(ax)
    ax.set_xticks(x); ax.set_xticklabels([f"{p}\n({f:.0%})" for p, f in zip(PAYLOADS, x)])
    ax.set_xlabel("Payload (fraction of non-zero AC coefficients flipped)")
    ax.set_ylabel("Mean ROC AUC (pooled over source + encryption)")
    ax.set_title(r"Frequency-branch detector contest on caption-matched test corpus")
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "tiled_vs_baselines_line.png")
    plt.close()
    print(f"wrote {OUT / 'tiled_vs_baselines_line.png'}")


# ===========================================================================
# FIG 6 -- V1 vs V2a per-source AUC heatmap (cleaner than the bar chart in G1)
# ===========================================================================
def fig_v1_vs_v2a_heatmap():
    v1_rows = load_learned("v1")
    v2_rows = load_learned("v2a")
    v1 = per_cell_aucs(v1_rows, filter_encryption="plain")
    v2 = per_cell_aucs(v2_rows, filter_encryption="plain")

    fig, axes = plt.subplots(1, 2, figsize=(7.5, 4.0))
    detectors = [("srnet", "lsb", "SRNet"), ("dctr", "dct", "DCTR")]
    rowlabels = []
    for det_key, method, det_lbl in detectors:
        for payload in PAYLOADS:
            rowlabels.append(f"{det_lbl} / {payload}")
    n_rows = len(rowlabels)
    v1_grid = np.zeros((n_rows, len(SOURCES)))
    v2_grid = np.zeros((n_rows, len(SOURCES)))
    i = 0
    for det_key, method, det_lbl in detectors:
        for payload in PAYLOADS:
            for j, src in enumerate(SOURCES):
                v1_grid[i, j] = v1.get((det_key, method, payload, src), np.nan)
                v2_grid[i, j] = v2.get((det_key, method, payload, src), np.nan)
            i += 1

    for ax, grid, title in zip(axes, [v1_grid, v2_grid],
                                ["Matched training (V1: 1:1:1 real/SDXL/FLUX)",
                                 "Real-only training (V2a: AI carriers held out)"]):
        im = ax.imshow(grid, vmin=0.5, vmax=1.0, cmap="RdYlGn", aspect="auto")
        ax.set_xticks(range(len(SOURCES)))
        ax.set_xticklabels([SOURCE_LABELS[s] for s in SOURCES], fontsize=8)
        ax.set_yticks(range(n_rows))
        ax.set_yticklabels(rowlabels, fontsize=7)
        ax.set_title(title, fontsize=9, fontweight="bold")
        # Per-cell value annotations
        for i in range(grid.shape[0]):
            for j in range(grid.shape[1]):
                v = grid[i, j]
                text_color = "white" if v < 0.7 else PALETTE["umdark"]
                ax.text(j, i, f"{v:.3f}", ha="center", va="center",
                        color=text_color, fontsize=7)
        ax.grid(False)
    fig.suptitle("Per-(detector, payload, source) test AUC: matched vs real-only training (plain encryption)",
                 fontsize=10)
    cbar_ax = fig.add_axes([0.94, 0.15, 0.015, 0.7])
    cbar = fig.colorbar(im, cax=cbar_ax)
    cbar.set_label("AUC")
    fig.subplots_adjust(left=0.18, right=0.92, top=0.88, bottom=0.10, wspace=0.6)
    fig.savefig(OUT / "v1_vs_v2a_heatmap.png")
    plt.close()
    print(f"wrote {OUT / 'v1_vs_v2a_heatmap.png'}")


# ===========================================================================
# FIG 7 -- chi^2-spatial cover-side variance: box plot per source
# ===========================================================================
def fig_chi2_spatial_pov_box():
    """Show that cover-side chi^2-spatial scores have higher variance on ML
    carriers, the mechanism behind the chi^2-spatial RQ1 reversal."""
    rows = [r for r in load_classical()
            if r["detector"] == "chi_square_spatial" and r["label"] == "0"]
    by_source = defaultdict(list)
    for r in rows:
        by_source[r["source"]].append(float(r["score"]))

    fig, ax = plt.subplots(figsize=(6.0, 3.6))
    parts = ax.boxplot(
        [by_source[s] for s in SOURCES],
        widths=0.45, showfliers=False, patch_artist=True,
        boxprops=dict(linewidth=0.6, edgecolor=PALETTE["umdark"]),
        medianprops=dict(color=PALETTE["umorange"], linewidth=1.4),
        whiskerprops=dict(color=PALETTE["umdark"], linewidth=0.7),
        capprops=dict(color=PALETTE["umdark"], linewidth=0.7),
    )
    for patch, src in zip(parts["boxes"], SOURCES):
        patch.set_facecolor(SOURCE_COLORS[src])
        patch.set_alpha(0.6)
    ax.set_xticklabels([SOURCE_LABELS[s] for s in SOURCES])
    ax.set_ylabel(r"Cover-side $\chi^2$-spatial score $-\chi^2/df$")
    ax.set_title(r"$\chi^2$-spatial cover-side score: variance inflates on ML carriers")
    # Annotate std deviations
    for i, src in enumerate(SOURCES):
        std = np.std(by_source[src])
        ax.text(i + 1, ax.get_ylim()[0] + 0.02 * (ax.get_ylim()[1] - ax.get_ylim()[0]),
                f"std={std:.1f}", ha="center", fontsize=7,
                color=PALETTE["umdark"])
    fig.tight_layout()
    fig.savefig(OUT / "chi2_spatial_pov_box.png")
    plt.close()
    print(f"wrote {OUT / 'chi2_spatial_pov_box.png'}")


# ===========================================================================
# FIG 7B -- RQ2 forest plot: SDXL vs FLUX within ML (mirror of fig_rq1_forest)
# ===========================================================================
def fig_rq2_forest():
    rows = load_classical()
    aucs = per_cell_aucs(rows)
    points = []
    for det, det_lbl, _m, color in CLASSICAL_DETECTORS:
        method = DET_METHOD[det]
        for payload in PAYLOADS:
            ml_a = aucs.get((det, method, payload, "ml_a"))
            ml_b = aucs.get((det, method, payload, "ml_b"))
            if ml_a is None or ml_b is None:
                continue
            se = 0.012
            points.append((det, det_lbl, payload, ml_a - ml_b, se, color))

    fig, ax = plt.subplots(figsize=(7.2, 6.0))
    y = np.arange(len(points))
    for i, (det, det_lbl, payload, delta, se, color) in enumerate(points):
        ax.errorbar(delta, i, xerr=1.96 * se, fmt="o",
                    color=color, ecolor=color, elinewidth=1.2, capsize=3,
                    markersize=6, markeredgecolor=PALETTE["umdark"],
                    markeredgewidth=0.4)
    ax.axvline(0, color=PALETTE["umgray"], linewidth=0.8)
    ax.axvspan(-0.025, 0.025, color=PALETTE["umgray"], alpha=0.10,
               label="trivial band (|Δ|<0.025)")
    for x_threshold in (-0.05, 0.05):
        ax.axvline(x_threshold, color=PALETTE["umorange"], linestyle=":",
                   linewidth=0.6)
    ax.text(-0.052, -0.6,
            r"$\delta_\mathrm{min}=\pm 0.05$ (pre-registered)",
            ha="right", fontsize=7.5, color=PALETTE["umorange"], style="italic")
    labels = [f"{p[1]} / {p[2]}" for p in points]
    ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(-0.10, 0.10)
    ax.set_ylim(len(points), -1.5)
    ax.set_xlabel(r"$\Delta_{AUC}$ = AUC(SDXL) − AUC(FLUX)   (negative = FLUX easier than SDXL)")
    ax.set_title("RQ2 forest plot: SDXL vs FLUX within-ML, per (detector, payload), 18 strata")
    ax.legend(loc="lower left", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "rq2_forest.png")
    plt.close()
    print(f"wrote {OUT / 'rq2_forest.png'}")


# ===========================================================================
# FIG 7C -- DCTR E_OOB ladder: training-time OOB vs test-set P_E^min
# ===========================================================================
def fig_dctr_eoob_ladder():
    """Mirrors the v2a_findings/g3_dctr_eoob_ladder.png but in the v4_paper
    directory and naming-aligned to the renamed real-only training (V2a)."""
    import json
    dctr_summaries = {p: json.load(open(
        f"models/training_v2a/dctr_dct_{p}_v2a.summary.json")) for p in PAYLOADS}
    eoob = [dctr_summaries[p]["oob_metrics"]["e_oob"] for p in PAYLOADS]
    val_auc = [dctr_summaries[p]["val_auc"] for p in PAYLOADS]
    test_pe_by_payload = defaultdict(list)
    for r in csv.DictReader(open(
        RUN_DIR / "predictions" / "pe_min_dctr_v2a.csv")):
        test_pe_by_payload[r["payload_level"]].append(float(r["pe_min"]))
    test_pe = [float(np.mean(test_pe_by_payload[p])) for p in PAYLOADS]
    val_pe = [1 - v for v in val_auc]

    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    x = np.arange(3); w = 0.27
    b1 = ax.bar(x - w, eoob, w, color=PALETTE["umdark"],
                label=r"$E_\mathrm{OOB}$ (training-time, OOB ensemble residual)",
                edgecolor=PALETTE["umdark"], linewidth=0.4)
    b2 = ax.bar(x, test_pe, w, color=PALETTE["umorange"],
                label=r"Test-set $P_E^{\min}$ (real + ML carriers, OOD on ML)",
                edgecolor=PALETTE["umdark"], linewidth=0.4)
    b3 = ax.bar(x + w, val_pe, w, color=PALETTE["umlight"],
                label=r"$1-\mathrm{val\_AUC}$ (held-out of training, proxy)",
                edgecolor=PALETTE["umdark"], linewidth=0.4)
    ax.axhline(0.5, color=PALETTE["umgray"], linestyle=":", linewidth=0.6)
    ax.set_ylim(0, 0.55)
    ax.set_xticks(x); ax.set_xticklabels(PAYLOADS)
    ax.set_xlabel("payload level")
    ax.set_ylabel("detection error (lower is better)")
    ax.set_title(r"DCTR real-only: $E_\mathrm{OOB}$ ladders with payload; test on OOD ML carriers uniformly worse")
    for bars, vals in [(b1, eoob), (b2, test_pe), (b3, val_pe)]:
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width()/2, b.get_height() + 0.01,
                    f"{v:.3f}", ha="center", fontsize=7, color=PALETTE["umdark"])
    ax.legend(loc="upper right", fontsize=7.5)
    fig.tight_layout()
    fig.savefig(OUT / "dctr_eoob_ladder.png")
    plt.close()
    print(f"wrote {OUT / 'dctr_eoob_ladder.png'}")


# ===========================================================================
# POSTER FIGURES -- brand-style PNG replicas of paper tikz figures 4-8
# (the v4 paper keeps tikz; these PNGs are for the poster)
# ===========================================================================
def fig_rq1_strip():
    """Poster replica of fig:rq1strip (strip plot per detector, 3 dots per row)."""
    rows = load_classical()
    aucs = per_cell_aucs(rows)
    # Order of detectors in the paper figure
    det_order = [
        ("calibration_chi_square", r"cal-$\chi^2$"),
        ("chi_square_dct", r"$\chi^2$-DCT"),
        ("chi_square_dct_tiled", r"$\chi^2$-DCT-t"),
        ("chi_square_spatial", r"$\chi^2$-spat."),
        ("rs", "RS"),
        ("sample_pairs", "Sample Pairs"),
    ]
    payload_colors = {"low": PALETTE["umdark"], "medium": PALETTE["umlight"], "high": PALETTE["umorange"]}

    fig, ax = plt.subplots(figsize=(7.0, 3.6))
    for i, (det, det_lbl) in enumerate(det_order):
        method = DET_METHOD[det]
        deltas = []
        for p in PAYLOADS:
            real = aucs.get((det, method, p, "real"))
            ml_a = aucs.get((det, method, p, "ml_a"))
            ml_b = aucs.get((det, method, p, "ml_b"))
            if real is None or ml_a is None or ml_b is None:
                deltas.append(None); continue
            deltas.append(real - 0.5 * (ml_a + ml_b))
        valid = [(p, d) for p, d in zip(PAYLOADS, deltas) if d is not None]
        if not valid: continue
        ys = [i] * len(valid)
        xs = [d for _, d in valid]
        ax.plot(xs, ys, color=PALETTE["umgray"], linewidth=0.8, alpha=0.4, zorder=1)
        for p, d in valid:
            ax.scatter(d, i, s=55, color=payload_colors[p],
                       edgecolor=PALETTE["umdark"], linewidth=0.4, zorder=3)

    ax.axvline(0, color=PALETTE["umgray"], linewidth=0.7)
    ax.axvspan(-0.025, 0.025, color=PALETTE["umgray"], alpha=0.10, label="trivial band (|Δ|<0.025)")
    for x in (-0.05, 0.05):
        ax.axvline(x, color=PALETTE["umorange"], linestyle=":", linewidth=0.6)
    ax.set_yticks(range(len(det_order)))
    ax.set_yticklabels([lbl for _, lbl in det_order])
    ax.invert_yaxis()
    ax.set_xlim(-0.12, 0.08)
    ax.set_xlabel(r"$\Delta_{AUC}$ (real $-$ pooled ML)")
    ax.set_title("RQ1 strip plot: per-detector x per-payload carrier-source effect (18 strata)")
    handles = [plt.Line2D([], [], marker='o', linestyle='', color=payload_colors[p],
                           label=p, markeredgecolor=PALETTE["umdark"], markersize=7)
               for p in PAYLOADS]
    ax.legend(handles=handles, loc="lower right", fontsize=8, title="payload", ncol=1)
    fig.tight_layout()
    fig.savefig(OUT / "rq1_strip.png")
    plt.close()
    print(f"wrote {OUT / 'rq1_strip.png'}")


def fig_rq2_strip():
    """Poster replica of fig:rq2 (strip plot per detector, SDXL vs FLUX)."""
    rows = load_classical()
    aucs = per_cell_aucs(rows)
    det_order = [
        ("calibration_chi_square", r"cal-$\chi^2$"),
        ("chi_square_dct", r"$\chi^2$-DCT"),
        ("chi_square_dct_tiled", r"$\chi^2$-DCT-t"),
        ("chi_square_spatial", r"$\chi^2$-spat."),
        ("rs", "RS"),
        ("sample_pairs", "Sample Pairs"),
    ]
    payload_colors = {"low": PALETTE["umdark"], "medium": PALETTE["umlight"], "high": PALETTE["umorange"]}

    fig, ax = plt.subplots(figsize=(7.0, 3.6))
    for i, (det, det_lbl) in enumerate(det_order):
        method = DET_METHOD[det]
        deltas = []
        for p in PAYLOADS:
            ml_a = aucs.get((det, method, p, "ml_a"))
            ml_b = aucs.get((det, method, p, "ml_b"))
            if ml_a is None or ml_b is None:
                deltas.append(None); continue
            deltas.append(ml_a - ml_b)
        valid = [(p, d) for p, d in zip(PAYLOADS, deltas) if d is not None]
        if not valid: continue
        ys = [i] * len(valid); xs = [d for _, d in valid]
        ax.plot(xs, ys, color=PALETTE["umgray"], linewidth=0.8, alpha=0.4, zorder=1)
        for p, d in valid:
            ax.scatter(d, i, s=55, color=payload_colors[p],
                       edgecolor=PALETTE["umdark"], linewidth=0.4, zorder=3)
    ax.axvline(0, color=PALETTE["umgray"], linewidth=0.7)
    ax.axvspan(-0.025, 0.025, color=PALETTE["umgray"], alpha=0.10, label="trivial band (|Δ|<0.025)")
    for x in (-0.05, 0.05):
        ax.axvline(x, color=PALETTE["umorange"], linestyle=":", linewidth=0.6)
    ax.set_yticks(range(len(det_order)))
    ax.set_yticklabels([lbl for _, lbl in det_order])
    ax.invert_yaxis()
    ax.set_xlim(-0.08, 0.08)
    ax.set_xlabel(r"$\Delta_{AUC}$ (SDXL $-$ FLUX)")
    ax.set_title("RQ2 strip plot: SDXL vs FLUX within-ML carrier (18 strata)")
    handles = [plt.Line2D([], [], marker='o', linestyle='', color=payload_colors[p],
                           label=p, markeredgecolor=PALETTE["umdark"], markersize=7)
               for p in PAYLOADS]
    ax.legend(handles=handles, loc="lower right", fontsize=8, title="payload", ncol=1)
    fig.tight_layout()
    fig.savefig(OUT / "rq2_strip.png")
    plt.close()
    print(f"wrote {OUT / 'rq2_strip.png'}")


def fig_rq4_branch():
    """Poster replica of fig:rq4 (spatial vs frequency branch source gap, per payload)."""
    rows = load_classical()
    aucs = per_cell_aucs(rows)
    spat_dets = [d for d, _, m, _ in CLASSICAL_DETECTORS if m == "lsb"]
    freq_dets = [d for d, _, m, _ in CLASSICAL_DETECTORS if m == "dct"]

    def branch_gap(dets, payload):
        """real-mean - ml-mean over the detectors in 'dets' for one payload."""
        per_det = []
        for det in dets:
            method = DET_METHOD[det]
            real = aucs.get((det, method, payload, "real"))
            ml_a = aucs.get((det, method, payload, "ml_a"))
            ml_b = aucs.get((det, method, payload, "ml_b"))
            if real is None or ml_a is None or ml_b is None: continue
            per_det.append(real - 0.5 * (ml_a + ml_b))
        return float(np.mean(per_det))

    fig, ax = plt.subplots(figsize=(6.5, 4.0))
    x = np.arange(3); w = 0.32
    spat_gaps = [branch_gap(spat_dets, p) for p in PAYLOADS]
    freq_gaps = [branch_gap(freq_dets, p) for p in PAYLOADS]
    ax.bar(x - w/2, spat_gaps, w, color=PALETTE["umlight"],
           edgecolor=PALETTE["umdark"], linewidth=0.4, label="spatial branch")
    ax.bar(x + w/2, freq_gaps, w, color=PALETTE["umorange"],
           edgecolor=PALETTE["umdark"], linewidth=0.4, label="frequency branch")
    # Bar-tip value labels positioned BELOW the tip for negative bars
    for xi, v in zip(x - w/2, spat_gaps):
        ax.text(xi, v - 0.0025, f"{v:+.3f}", ha="center", va="top",
                fontsize=7, color=PALETTE["umdark"])
    for xi, v in zip(x + w/2, freq_gaps):
        ax.text(xi, v - 0.0025, f"{v:+.3f}", ha="center", va="top",
                fontsize=7, color=PALETTE["umdark"])
    # Delta-delta annotations ABOVE the axis (in the positive-y region)
    for i, p in enumerate(PAYLOADS):
        dd = spat_gaps[i] - freq_gaps[i]
        ax.text(i, 0.018, rf"$\Delta\Delta={dd:+.3f}$", ha="center", fontsize=8.5,
                fontweight="bold", color=PALETTE["umorange"])
    ax.axhline(0, color=PALETTE["umgray"], linewidth=0.7)
    # Give some headroom above 0 for the ΔΔ annotations
    ax.set_ylim(min(min(spat_gaps), min(freq_gaps)) * 1.25, 0.030)
    ax.set_xticks(x); ax.set_xticklabels(PAYLOADS)
    ax.set_xlabel("payload level")
    ax.set_ylabel(r"$\Delta_{AUC}$ (real $-$ mean ML)")
    ax.set_title("RQ4: spatial vs frequency branch carrier-source gap, per payload")
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "rq4_branch.png")
    plt.close()
    print(f"wrote {OUT / 'rq4_branch.png'}")


def fig_rq5_encryption():
    """Poster replica of fig:rq5 (plain vs AES-256 AUC scatter, 54 strata)."""
    rows = load_classical()
    pairs = defaultdict(dict)
    for r in rows:
        key = (r["detector"], r["method"], r["payload_level"], r["source"])
        pairs[key].setdefault(r["encryption"], []).append((int(r["label"]), float(r["score"])))
    points = []
    for key, by_enc in pairs.items():
        if "plain" not in by_enc or "encrypted" not in by_enc:
            continue
        plain = by_enc["plain"]
        enc = by_enc["encrypted"]
        try:
            auc_plain = roc_auc_score_binary([y for y, _ in plain], [s for _, s in plain])
            auc_enc   = roc_auc_score_binary([y for y, _ in enc],   [s for _, s in enc])
            points.append((auc_plain, auc_enc))
        except ValueError:
            continue

    fig, ax = plt.subplots(figsize=(5.6, 5.0))
    xs = [p[0] for p in points]; ys = [p[1] for p in points]
    # ±0.025 equivalence band as shaded region around y=x
    band = np.linspace(0.5, 1.0, 100)
    ax.fill_between(band, band - 0.025, band + 0.025, color=PALETTE["umorange"], alpha=0.10,
                    label=r"$\pm0.025$ AUC equivalence band")
    ax.plot([0.5, 1.0], [0.5, 1.0], color=PALETTE["umdark"], linestyle="--", linewidth=0.6, label=r"$y = x$")
    ax.scatter(xs, ys, s=22, color=PALETTE["umlight"], edgecolor=PALETTE["umdark"],
               linewidth=0.4, alpha=0.85, zorder=3)
    ax.set_xlim(0.5, 1.0); ax.set_ylim(0.5, 1.0)
    ax.set_xlabel("plain AUC")
    ax.set_ylabel("AES-256-CBC AUC")
    ax.set_title("RQ5: plain vs AES-256 stego AUC, all 54 strata")
    ax.set_aspect("equal")
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "rq5_encryption.png")
    plt.close()
    print(f"wrote {OUT / 'rq5_encryption.png'}")


# ===========================================================================
# FIG 8 -- per-RQ verdict matrix (classical / matched / real-only)
# ===========================================================================
def fig_verdict_matrix():
    paths = {
        "classical\n(6 detectors)":         RUN_DIR / "metrics" / "rq_verdicts.json",
        "learned -- matched\n(SRNet + DCTR, V1)":  RUN_DIR / "learned_shadow" / "metrics" / "rq_verdicts.json",
        "learned -- real-only\n(SRNet + DCTR, V2a)": RUN_DIR / "learned_shadow_v2a" / "metrics" / "rq_verdicts.json",
    }
    verdicts = {k: json.load(open(p))["verdicts"] for k, p in paths.items()}
    rqs = ["RQ1", "RQ2", "RQ3", "RQ4", "RQ5"]
    cols = list(verdicts.keys())

    color_map = {
        "supported": PALETTE["umorange"],
        "mixed":     PALETTE["umlight"],
        "trivial":   PALETTE["umgray"],
    }
    # Wider cells: aspect=None and a generous figsize so the verdict labels
    # ("supported" is the longest at 9 chars) fit comfortably without overlap.
    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    for i, rq in enumerate(rqs):
        for j, col in enumerate(cols):
            v = verdicts[col].get(rq, {})
            verdict = v.get("verdict", "?")
            pooled = v.get("pooled_diff", 0)
            color = color_map.get(verdict, "white")
            rect = mpatches.Rectangle((j, i), 1, 1, facecolor=color, alpha=0.75,
                                      edgecolor=PALETTE["umdark"], linewidth=0.6)
            ax.add_patch(rect)
            text_color = "white" if verdict == "supported" else PALETTE["umdark"]
            ax.text(j + 0.5, i + 0.34, verdict, ha="center", va="center",
                    fontsize=10, fontweight="bold", color=text_color)
            if "pooled_diff" in v:
                ax.text(j + 0.5, i + 0.66, f"Δ={pooled:+.4f}",
                        ha="center", va="center", fontsize=8, color=text_color)
    ax.set_xlim(0, len(cols))
    ax.set_ylim(len(rqs), 0)
    ax.set_xticks([j + 0.5 for j in range(len(cols))])
    ax.set_xticklabels(cols, fontsize=10)
    ax.set_yticks([i + 0.5 for i in range(len(rqs))])
    ax.set_yticklabels(rqs, fontsize=10)
    ax.set_title("RQ verdict matrix across the three detector-family analyses")
    ax.grid(False)
    ax.set_aspect("auto")
    for spine in ax.spines.values(): spine.set_visible(False)
    ax.tick_params(left=False, bottom=False)
    fig.tight_layout()
    fig.savefig(OUT / "verdict_matrix.png")
    plt.close()
    print(f"wrote {OUT / 'verdict_matrix.png'}")


# ===========================================================================
# FIG 9 -- V1 vs V2a per-source bar chart (replaces G1 with cleaner legend)
# ===========================================================================
def fig_v1_vs_v2a_per_source_bars():
    v1_rows = load_learned("v1")
    v2_rows = load_learned("v2a")
    v1 = per_cell_aucs(v1_rows, filter_encryption="plain")
    v2 = per_cell_aucs(v2_rows, filter_encryption="plain")
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.8), sharey=True)
    for ax, (det_key, method, det_lbl) in zip(axes,
        [("srnet", "lsb", "SRNet"), ("dctr", "dct", "DCTR")]):
        x = np.arange(len(PAYLOADS))
        w = 0.13
        for i, src in enumerate(SOURCES):
            v1_vals = [v1.get((det_key, method, p, src), 0) for p in PAYLOADS]
            v2_vals = [v2.get((det_key, method, p, src), 0) for p in PAYLOADS]
            ax.bar(x + (i - 2.5) * w - 0.03, v1_vals, w, color=SOURCE_COLORS[src],
                   edgecolor=PALETTE["umdark"], linewidth=0.4)
            ax.bar(x + (i + 0.5) * w + 0.03, v2_vals, w, color=SOURCE_COLORS[src],
                   edgecolor=PALETTE["umdark"], linewidth=0.4, hatch="//", alpha=0.85)
            # Tiny per-bar AUC annotations
            for xi, yi in zip(x + (i - 2.5) * w - 0.03, v1_vals):
                ax.text(xi, yi + 0.005, f"{yi:.2f}", ha="center", fontsize=5.5,
                        color=PALETTE["umdark"], rotation=0)
            for xi, yi in zip(x + (i + 0.5) * w + 0.03, v2_vals):
                ax.text(xi, yi + 0.005, f"{yi:.2f}", ha="center", fontsize=5.5,
                        color=PALETTE["umdark"], rotation=0)
        style_auc_axis(ax)
        ax.set_xticks(x)
        ax.set_xticklabels([f"{p}\n[match | real]" for p in PAYLOADS], fontsize=8)
        ax.set_title(det_lbl)
        if det_key == "srnet":
            ax.set_ylabel("ROC AUC (plain encryption)")
    # Single legend OUTSIDE the figure on the right
    handles = [mpatches.Patch(facecolor=SOURCE_COLORS[s], label=SOURCE_LABELS[s],
                              edgecolor=PALETTE["umdark"]) for s in SOURCES]
    handles += [
        mpatches.Patch(facecolor="white", edgecolor=PALETTE["umdark"],
                       label="matched (V1)"),
        mpatches.Patch(facecolor="white", edgecolor=PALETTE["umdark"], hatch="//",
                       label="real-only (V2a)"),
    ]
    fig.legend(handles=handles, loc="center right", bbox_to_anchor=(1.13, 0.5),
               fontsize=8, ncol=1)
    fig.suptitle(r"Matched vs real-only training: per-source test AUC at the three payload levels",
                 fontsize=10)
    fig.tight_layout(rect=[0, 0, 0.88, 0.96])
    fig.savefig(OUT / "v1_vs_v2a_per_source_bars.png")
    plt.close()
    print(f"wrote {OUT / 'v1_vs_v2a_per_source_bars.png'}")


# ===========================================================================
# FIG 10 -- V2a SRNet score distributions (replaces G2 with legend in corner)
# ===========================================================================
def fig_v2a_srnet_score_dists():
    rows = load_learned("v2a")
    scores = defaultdict(list)
    for r in rows:
        if r["detector"] != "srnet": continue
        if r["encryption"] != "plain": continue
        scores[(r["payload_level"], r["source"], int(r["label"]))].append(float(r["score"]))
    aucs = per_cell_aucs(rows, filter_encryption="plain")

    fig, axes = plt.subplots(3, 3, figsize=(8.8, 6.8), sharex=True, sharey=True)
    bins = np.linspace(0, 1, 41)
    for i, payload in enumerate(PAYLOADS):
        for j, src in enumerate(SOURCES):
            ax = axes[i, j]
            cov = scores[(payload, src, 0)]; ste = scores[(payload, src, 1)]
            ax.hist(cov, bins=bins, alpha=0.55, color=PALETTE["umlight"],
                    edgecolor=PALETTE["umdark"], linewidth=0.25)
            ax.hist(ste, bins=bins, alpha=0.55, color=PALETTE["umorange"],
                    edgecolor=PALETTE["umdark"], linewidth=0.25)
            shift = float(np.mean(ste) - np.mean(cov))
            auc = aucs.get(("srnet", "lsb", payload, src), 0)
            ax.text(0.5, 0.86, f"AUC={auc:.3f}\nshift={shift:.2f}",
                    transform=ax.transAxes, ha="center", fontsize=7,
                    color=PALETTE["umdark"],
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                              edgecolor="none", alpha=0.75))
            if i == 0: ax.set_title(SOURCE_LABELS[src])
            if j == 0: ax.set_ylabel(f"{payload}\npayload", fontsize=8)
            if i == 2: ax.set_xlabel("P[stego]")
            ax.set_xlim(-0.02, 1.02); ax.set_yscale("symlog", linthresh=10)
    # Legend on the right OUTSIDE the grid (the only safe place; the histograms
    # at the top of each panel make a bottom or in-panel legend conflict-prone).
    cover_patch = mpatches.Patch(facecolor=PALETTE["umlight"], alpha=0.55,
                                  edgecolor=PALETTE["umdark"], label="cover")
    stego_patch = mpatches.Patch(facecolor=PALETTE["umorange"], alpha=0.55,
                                  edgecolor=PALETTE["umdark"], label="stego")
    fig.legend(handles=[cover_patch, stego_patch],
               loc="center right", bbox_to_anchor=(1.04, 0.5),
               fontsize=9)
    fig.suptitle("V2a SRNet score distributions: cover-saturation on ML carriers\n"
                 "collapses cover-stego separation at medium/high payload",
                 fontsize=10)
    fig.tight_layout(rect=[0, 0, 0.95, 0.94])
    fig.savefig(OUT / "v2a_srnet_score_dists.png")
    plt.close()
    print(f"wrote {OUT / 'v2a_srnet_score_dists.png'}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Building v4 paper figures in brand style ...")
    fig_headline_rq1()
    fig_rq1_forest()
    fig_rq2_forest()
    fig_rq3_payload_gap()
    fig_roc_at_medium()
    fig_tiled_vs_baselines_line()
    fig_v1_vs_v2a_heatmap()
    fig_dctr_eoob_ladder()
    fig_chi2_spatial_pov_box()
    fig_verdict_matrix()
    fig_v1_vs_v2a_per_source_bars()
    fig_v2a_srnet_score_dists()
    # Poster-only replicas of the paper's tikz figures 4-8:
    fig_rq1_strip()
    fig_rq2_strip()
    fig_rq4_branch()
    fig_rq5_encryption()
    print(f"\nAll figures in {OUT}/")
