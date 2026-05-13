#!/usr/bin/env python3
"""Supplementary pAUC (partial AUC at FPR <= 0.10) analysis for RQ1 and RQ2.

The primary analysis in the deck uses full ROC AUC. This script computes the
McClish-normalised pAUC@FPR<=0.10 per stratum and re-emits the RQ1
(real vs pooled ML) and RQ2 (SDXL vs FLUX) contrasts with bootstrap
standard errors and the same Holm + practical-significance gate as the
primary analysis.

FPR cap rationale
-----------------
FPR <= 0.10 matches McClish (1989), the standard low-FPR partial AUC
convention, and reflects the operational regime of steganalysis as
screening: a deployed detector cannot tolerate FPR >> 0.1 on
million-image scans. Going lower (0.05) saturates strong detectors at
the McClish maximum; going higher (0.2) approaches full AUC.

Outputs
-------
metrics/exp1_rq1_real_vs_pooled_ml_pauc_contrasts.csv
metrics/exp2_rq2_mla_vs_mlb_pauc_contrasts.csv
metrics/pauc_verdicts.md
metrics/pauc_verdicts.json

Usage
-----
    python scripts/compute_pauc_analysis.py runs/<run_id> [--fpr-cap 0.10]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np


FPR_CAP_DEFAULT = 0.10
BOOTSTRAP_N = 500
RNG_SEED = 20260513
PROPOSAL_DELTA_MIN = 0.05


def _pauc(labels: np.ndarray, scores: np.ndarray, fpr_cap: float) -> float:
    """McClish-normalised pAUC at FPR <= fpr_cap.

    Returns the trapezoidal area under the truncated ROC, normalised so
    that random guessing scores 0.5 and a perfect detector scores 1.0
    (same scale as full AUC). Equivalent to sklearn's
    ``roc_auc_score(..., max_fpr=fpr_cap)`` but implemented in pure
    numpy to avoid a sklearn dependency.

    McClish (1989) normalisation:
        pAUC_min = fpr_cap^2 / 2     (chance-line area under truncation)
        pAUC_max = fpr_cap            (perfect detector area)
        pAUC_norm = 0.5 * (1 + (pAUC_raw - pAUC_min) / (pAUC_max - pAUC_min))
    """
    n_pos = int((labels == 1).sum())
    n_neg = int((labels == 0).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    # Order by score descending; break ties by averaging ranks via stable sort.
    order = np.argsort(-scores, kind="stable")
    y = labels[order]
    # Cumulative FP / TP as we walk the sorted list.
    cum_fp = np.cumsum(y == 0).astype(np.float64)
    cum_tp = np.cumsum(y == 1).astype(np.float64)
    fpr = cum_fp / n_neg
    tpr = cum_tp / n_pos
    # Prepend (0,0) so the ROC starts at the origin.
    fpr = np.concatenate([[0.0], fpr])
    tpr = np.concatenate([[0.0], tpr])
    # Slice up to and including fpr_cap, interpolating TPR at the boundary.
    idx = int(np.searchsorted(fpr, fpr_cap, side="right"))
    if idx >= len(fpr):
        fpr_used, tpr_used = fpr, tpr
    elif fpr[idx - 1] < fpr_cap:
        slope = (tpr[idx] - tpr[idx - 1]) / max(fpr[idx] - fpr[idx - 1], 1e-12)
        interp_tpr = tpr[idx - 1] + slope * (fpr_cap - fpr[idx - 1])
        fpr_used = np.concatenate([fpr[:idx], [fpr_cap]])
        tpr_used = np.concatenate([tpr[:idx], [interp_tpr]])
    else:
        fpr_used, tpr_used = fpr[:idx], tpr[:idx]
    raw_pauc = float(np.trapezoid(tpr_used, fpr_used))
    pauc_min = fpr_cap * fpr_cap / 2.0
    pauc_max = fpr_cap
    return 0.5 * (1.0 + (raw_pauc - pauc_min) / (pauc_max - pauc_min))


def _pauc_diff_bootstrap(
    labels_a: np.ndarray, scores_a: np.ndarray,
    labels_b: np.ndarray, scores_b: np.ndarray,
    fpr_cap: float, n_resamples: int = BOOTSTRAP_N, rng_seed: int = RNG_SEED,
) -> tuple[float, float, float, float]:
    """Return (pauc_a, pauc_b, diff, se_diff).

    Standard error of the pAUC difference is computed by bootstrap
    resampling within each group (positives and negatives are
    resampled independently). The two strata are resampled
    independently because the contrasts are between disjoint cover sets
    in RQ1 (real vs ML) and disjoint generator outputs in RQ2.
    """
    pauc_a = _pauc(labels_a, scores_a, fpr_cap)
    pauc_b = _pauc(labels_b, scores_b, fpr_cap)
    diff = pauc_a - pauc_b

    rng = np.random.default_rng(rng_seed)
    pos_a = np.where(labels_a == 1)[0]
    neg_a = np.where(labels_a == 0)[0]
    pos_b = np.where(labels_b == 1)[0]
    neg_b = np.where(labels_b == 0)[0]

    diffs = np.empty(n_resamples, dtype=np.float64)
    for i in range(n_resamples):
        idx_a = np.concatenate([
            rng.choice(pos_a, size=len(pos_a), replace=True),
            rng.choice(neg_a, size=len(neg_a), replace=True),
        ])
        idx_b = np.concatenate([
            rng.choice(pos_b, size=len(pos_b), replace=True),
            rng.choice(neg_b, size=len(neg_b), replace=True),
        ])
        p_a = _pauc(labels_a[idx_a], scores_a[idx_a], fpr_cap)
        p_b = _pauc(labels_b[idx_b], scores_b[idx_b], fpr_cap)
        diffs[i] = p_a - p_b

    se = float(np.nanstd(diffs, ddof=1))
    return pauc_a, pauc_b, diff, se


def _read_predictions(path: Path) -> dict:
    """Group prediction rows by (detector, method, payload, source).

    Returns {(detector, method, payload, source): (labels[], scores[])}.
    """
    by_key: dict[tuple, list[tuple[int, float]]] = defaultdict(list)
    with path.open() as f:
        for r in csv.DictReader(f):
            key = (r["detector"], r["method"], r["payload_level"], r["source"], r["encryption"])
            try:
                by_key[key].append((int(r["label"]), float(r["score"])))
            except (TypeError, ValueError):
                continue
    out = {}
    for k, rows in by_key.items():
        labels = np.array([r[0] for r in rows], dtype=np.int8)
        scores = np.array([r[1] for r in rows], dtype=np.float64)
        out[k] = (labels, scores)
    return out


def _holm(pvals: list[float]) -> list[float]:
    """Holm-Bonferroni step-down adjustment."""
    n = len(pvals)
    order = sorted(range(n), key=lambda i: pvals[i])
    adj = [0.0] * n
    running_max = 0.0
    for rank, i in enumerate(order):
        v = pvals[i] * (n - rank)
        running_max = max(running_max, v)
        adj[i] = min(1.0, running_max)
    return adj


def _pool_strata(preds: dict, *, source_a: str, source_b_set: set[str]) -> dict:
    """Build per-stratum paired groups for an experiment.

    Returns {(detector, method, payload): {'a': (labels, scores), 'b': (labels, scores)}}
    where 'a' is source_a's pooled (plain + encrypted) and 'b' is the
    union over source_b_set.
    """
    grouped: dict[tuple, dict[str, list]] = defaultdict(lambda: {"a": [], "b": []})
    for (det, method, pl, src, enc), (labels, scores) in preds.items():
        key = (det, method, pl)
        if src == source_a:
            grouped[key]["a"].append((labels, scores))
        elif src in source_b_set:
            grouped[key]["b"].append((labels, scores))

    out = {}
    for key, parts in grouped.items():
        if not parts["a"] or not parts["b"]:
            continue
        la = np.concatenate([x[0] for x in parts["a"]])
        sa = np.concatenate([x[1] for x in parts["a"]])
        lb = np.concatenate([x[0] for x in parts["b"]])
        sb = np.concatenate([x[1] for x in parts["b"]])
        out[key] = {"a": (la, sa), "b": (lb, sb)}
    return out


def _emit_contrasts(
    strata: dict, *, label_a: str, label_b: str,
    fpr_cap: float, alpha: float = 0.05, delta_min: float = PROPOSAL_DELTA_MIN,
) -> tuple[list[dict], dict]:
    """Compute pAUC contrasts across strata + verdict summary."""
    rows = []
    for (det, method, pl), groups in sorted(strata.items()):
        la, sa = groups["a"]
        lb, sb = groups["b"]
        pa, pb, diff, se = _pauc_diff_bootstrap(la, sa, lb, sb, fpr_cap)
        if se > 0 and not math.isnan(diff):
            z = diff / se
            # two-sided p-value via normal approximation
            p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2))))
            ci_lo = diff - 1.96 * se
            ci_hi = diff + 1.96 * se
        else:
            z, p, ci_lo, ci_hi = float("nan"), float("nan"), float("nan"), float("nan")
        rows.append({
            "detector": det, "method": method, "payload_level": pl,
            f"pauc_{label_a}": pa, f"pauc_{label_b}": pb,
            "diff": diff, "se": se, "ci_lo": ci_lo, "ci_hi": ci_hi,
            "z": z, "p": p,
        })

    pvals = [r["p"] for r in rows if not math.isnan(r["p"])]
    holm = _holm(pvals)
    pi = 0
    for r in rows:
        if math.isnan(r["p"]):
            r["p_holm"] = float("nan")
            r["significant_holm_0_05"] = False
        else:
            r["p_holm"] = holm[pi]
            r["significant_holm_0_05"] = holm[pi] <= alpha
            pi += 1

    n_strata = len(rows)
    n_sig = sum(1 for r in rows if r["significant_holm_0_05"])
    n_sig_pos = sum(1 for r in rows if r["significant_holm_0_05"] and r["diff"] > 0)
    n_sig_neg = sum(1 for r in rows if r["significant_holm_0_05"] and r["diff"] < 0)
    n_practical = sum(
        1 for r in rows
        if r["significant_holm_0_05"] and abs(r["diff"]) >= delta_min
    )
    n_practical_pos = sum(
        1 for r in rows
        if r["significant_holm_0_05"] and r["diff"] >= delta_min
    )
    n_practical_neg = sum(
        1 for r in rows
        if r["significant_holm_0_05"] and -r["diff"] >= delta_min
    )

    # Inverse-variance pooled mean diff (ignoring NaNs and zero-SE).
    weights = []
    diffs = []
    for r in rows:
        if r["se"] > 0 and not math.isnan(r["diff"]):
            weights.append(1.0 / r["se"] ** 2)
            diffs.append(r["diff"])
    if weights:
        total_w = sum(weights)
        pooled = sum(w * d for w, d in zip(weights, diffs)) / total_w
        pooled_se = math.sqrt(1.0 / total_w)
    else:
        pooled, pooled_se = float("nan"), float("nan")

    if n_strata == 0:
        verdict = "no_data"
    elif n_sig == 0:
        verdict = "not_supported"
    elif n_practical == 0:
        verdict = "trivial"
    elif n_practical_pos > 0 and n_practical_neg > 0:
        verdict = "mixed"
    elif n_sig_pos > 0 and n_sig_neg > 0:
        verdict = "mixed"
    else:
        verdict = "supported"

    summary = {
        "n_strata": n_strata,
        "n_significant_holm_0_05": n_sig,
        "n_significant_positive": n_sig_pos,
        "n_significant_negative": n_sig_neg,
        "n_practical_holm_0_05": n_practical,
        "n_practical_positive": n_practical_pos,
        "n_practical_negative": n_practical_neg,
        "delta_min": delta_min,
        "pooled_diff": pooled,
        "pooled_se": pooled_se,
        "pooled_ci_lo": pooled - 1.96 * pooled_se if not math.isnan(pooled_se) else float("nan"),
        "pooled_ci_hi": pooled + 1.96 * pooled_se if not math.isnan(pooled_se) else float("nan"),
        "verdict": verdict,
    }
    return rows, summary


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys())
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _render_md(rq1: dict, rq2: dict, fpr_cap: float) -> str:
    def block(title: str, s: dict) -> str:
        return (
            f"## {title}\n\n"
            f"- Strata evaluated: {s['n_strata']}\n"
            f"- Significant after Holm (α=0.05): {s['n_significant_holm_0_05']}/{s['n_strata']} "
            f"(+ {s['n_significant_positive']}, − {s['n_significant_negative']})\n"
            f"- Practically relevant (|Δ| ≥ {s['delta_min']:.3f}): "
            f"{s['n_practical_holm_0_05']}/{s['n_significant_holm_0_05']}\n"
            f"- Pooled Δ-pAUC: {s['pooled_diff']:+.4f} "
            f"(95% CI [{s['pooled_ci_lo']:+.4f}, {s['pooled_ci_hi']:+.4f}])\n"
            f"- Verdict: **{s['verdict']}**\n\n"
        )
    return (
        f"# Partial AUC (FPR ≤ {fpr_cap:.2f}) Verdicts -- Supplementary\n\n"
        "Re-runs the RQ1 and RQ2 confirmatory contrasts on the McClish-normalised\n"
        f"partial AUC at FPR ≤ {fpr_cap:.2f}, with bootstrap SE (n={BOOTSTRAP_N} resamples) on\n"
        "the per-stratum pAUC difference. Same Holm correction and "
        f"δ_min = {PROPOSAL_DELTA_MIN:.3f} practical-significance gate as the primary analysis.\n\n"
    ) + block("RQ1 — Real vs pooled ML (pAUC)", rq1) + block(
        "RQ2 — SDXL vs FLUX within ML (pAUC)", rq2
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--fpr-cap", type=float, default=FPR_CAP_DEFAULT)
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    if not run_dir.exists():
        raise SystemExit(f"Run directory not found: {run_dir}")

    pred_path = run_dir / "predictions" / "predictions.csv"
    if not pred_path.exists():
        raise SystemExit(f"predictions.csv missing under {pred_path}")

    print(f"Loading predictions from {pred_path} ...")
    preds = _read_predictions(pred_path)
    print(f"  {len(preds)} strata loaded")

    print(f"\n=== RQ1 — real vs pooled ML, pAUC@FPR<={args.fpr_cap} ===")
    rq1_strata = _pool_strata(preds, source_a="real", source_b_set={"ml_a", "ml_b"})
    rq1_rows, rq1_summary = _emit_contrasts(
        rq1_strata, label_a="real", label_b="ml", fpr_cap=args.fpr_cap,
    )
    print(f"  {rq1_summary['n_strata']} strata, "
          f"{rq1_summary['n_significant_holm_0_05']} significant, "
          f"{rq1_summary['n_practical_holm_0_05']} practical, "
          f"verdict={rq1_summary['verdict']}")

    print(f"\n=== RQ2 — SDXL vs FLUX, pAUC@FPR<={args.fpr_cap} ===")
    rq2_strata = _pool_strata(preds, source_a="ml_a", source_b_set={"ml_b"})
    rq2_rows, rq2_summary = _emit_contrasts(
        rq2_strata, label_a="sdxl", label_b="flux", fpr_cap=args.fpr_cap,
    )
    print(f"  {rq2_summary['n_strata']} strata, "
          f"{rq2_summary['n_significant_holm_0_05']} significant, "
          f"{rq2_summary['n_practical_holm_0_05']} practical, "
          f"verdict={rq2_summary['verdict']}")

    metrics_dir = run_dir / "metrics"
    _write_csv(metrics_dir / "exp1_rq1_real_vs_pooled_ml_pauc_contrasts.csv", rq1_rows)
    _write_csv(metrics_dir / "exp2_rq2_mla_vs_mlb_pauc_contrasts.csv", rq2_rows)
    payload = {
        "fpr_cap": args.fpr_cap,
        "bootstrap_resamples": BOOTSTRAP_N,
        "delta_min": PROPOSAL_DELTA_MIN,
        "rq1": rq1_summary,
        "rq2": rq2_summary,
    }
    (metrics_dir / "pauc_verdicts.json").write_text(
        json.dumps(payload, indent=2, default=str)
    )
    (metrics_dir / "pauc_verdicts.md").write_text(
        _render_md(rq1_summary, rq2_summary, args.fpr_cap)
    )
    print(f"\nWrote:")
    print(f"  {metrics_dir / 'exp1_rq1_real_vs_pooled_ml_pauc_contrasts.csv'}")
    print(f"  {metrics_dir / 'exp2_rq2_mla_vs_mlb_pauc_contrasts.csv'}")
    print(f"  {metrics_dir / 'pauc_verdicts.md'}")
    print(f"  {metrics_dir / 'pauc_verdicts.json'}")


if __name__ == "__main__":
    main()
