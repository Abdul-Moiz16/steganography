"""
Power analysis for the steganalysis pipeline.

Two flavours:

A priori (no pilot data)
    Uses the Hanley & McNeil 1982 closed-form variance approximation for
    the AUC of a single ROC curve, then derives the required per-source
    n to detect a target ΔAUC at given α and 1-β. Honours Bonferroni-Holm
    correction across an assumed test family size.

Pilot-based (post-prototype)
    Reads the observed DeLong SE from an existing run's contrast CSVs and
    extrapolates the per-stratum n needed to make the *observed* effect
    statistically detectable. Useful for sizing the final ``full_design``
    run after a ``prototype`` validation pass.

Usage
-----
    # a priori
    python -m src.analysis.power_analysis --a-priori \\
        --target-diff 0.05 --target-auc 0.85 --n-tests 9

    # pilot-based: reads metrics/exp{1,2,4,5}_*_contrasts.csv from a run
    python -m src.analysis.power_analysis runs/<run-id>

Outputs (pilot-based)
---------------------
    metrics/power_analysis.csv      per-stratum recommended n
    metrics/power_summary.csv       headline minimum n per RQ
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

from scipy.stats import norm


CI_Z = 1.96
DEFAULT_ALPHA = 0.05
DEFAULT_POWER = 0.80


# ── Hanley & McNeil variance ────────────────────────────────────────────────

def hanley_mcneil_var(auc: float, n_pos: int, n_neg: int) -> float:
    """Closed-form approximation of var(AUC) for a single ROC curve.

    Reference: Hanley & McNeil (1982), "The meaning and use of the area
    under a receiver operating characteristic (ROC) curve."
    """
    if not 0.0 < auc < 1.0 or n_pos < 1 or n_neg < 1:
        return math.nan
    q1 = auc / (2.0 - auc)
    q2 = 2.0 * auc * auc / (1.0 + auc)
    return (
        auc * (1.0 - auc)
        + (n_pos - 1) * (q1 - auc * auc)
        + (n_neg - 1) * (q2 - auc * auc)
    ) / (n_pos * n_neg)


def hanley_mcneil_se(auc: float, n_pos: int, n_neg: int) -> float:
    v = hanley_mcneil_var(auc, n_pos, n_neg)
    return math.sqrt(v) if not math.isnan(v) and v > 0 else math.nan


# ── A priori sample-size calculator ─────────────────────────────────────────

def _z_for_family(alpha: float, n_tests: int, two_sided: bool = True) -> float:
    """Holm-conservative z for ``n_tests`` simultaneous comparisons.

    For Holm the most stringent step uses α/n_tests. Using that threshold
    gives a conservative bound on the required n (an upper bound).
    """
    n_tests = max(1, n_tests)
    family_alpha = alpha / n_tests
    tail = family_alpha / 2.0 if two_sided else family_alpha
    return float(norm.isf(tail))


def required_n_a_priori(
    *,
    target_diff: float,
    target_auc: float = 0.85,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
    n_tests: int = 1,
    paired: bool = False,
) -> int:
    """Per-source group count needed to detect ``target_diff`` AUC change.

    Assumes both groups have the same operating AUC (``target_auc``) and
    the same per-source group count ``n``. Variance is the Hanley-McNeil
    estimate; for the paired case we shrink the combined variance by 2
    (the paired DeLong test cancels covers, which contribute roughly half
    the variance).
    """
    z_alpha = _z_for_family(alpha, n_tests=n_tests, two_sided=True)
    z_beta = float(norm.isf(1.0 - power))

    def required_var(n: int) -> float:
        var_one = hanley_mcneil_var(target_auc, n_pos=n, n_neg=n)
        var_diff = 2.0 * var_one if not paired else var_one
        return var_diff

    # Doubling-search bracket then bisect — required_var(n) is monotone in n.
    lo, hi = 1, 2
    while True:
        if hi > 10_000_000:
            return hi
        var_diff = required_var(hi)
        se = math.sqrt(var_diff) if var_diff > 0 else math.inf
        if se == 0:
            return hi
        if (z_alpha + z_beta) * se <= target_diff:
            break
        hi *= 2

    while lo + 1 < hi:
        mid = (lo + hi) // 2
        var_diff = required_var(mid)
        se = math.sqrt(var_diff) if var_diff > 0 else math.inf
        if (z_alpha + z_beta) * se <= target_diff:
            hi = mid
        else:
            lo = mid
    return hi


# ── Pilot-based extrapolation ───────────────────────────────────────────────

def _maybe_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def required_n_from_pilot(
    *,
    observed_diff: float,
    observed_se: float,
    pilot_n_per_group: int,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
    n_tests: int = 1,
) -> int | None:
    """Extrapolate per-source n needed to detect ``observed_diff`` reliably.

    DeLong SE shrinks like 1/sqrt(n), so the required scaling is

        n_required = pilot_n * ((z_alpha + z_beta) * observed_se /
                                target_diff)^2 / 1

    Returns None when observed_se is zero (perfect separation; pilot
    already shows significance).
    """
    if observed_se is None or observed_se <= 0 or pilot_n_per_group <= 0:
        return None
    if abs(observed_diff) < 1e-12:
        return None  # nothing to detect — observed effect is zero
    z_alpha = _z_for_family(alpha, n_tests=n_tests, two_sided=True)
    z_beta = float(norm.isf(1.0 - power))
    se_at_one = observed_se * math.sqrt(pilot_n_per_group)
    target_se = abs(observed_diff) / (z_alpha + z_beta)
    if target_se <= 0:
        return None
    n_required = (se_at_one / target_se) ** 2
    return max(1, int(math.ceil(n_required)))


# ── Run-level orchestration ─────────────────────────────────────────────────

_FAMILIES = (
    {
        "rq": "RQ1",
        "file": "exp1_rq1_real_vs_pooled_ml_contrasts.csv",
        "default_n_tests": 9,
        "label": "real vs pooled ML",
    },
    {
        "rq": "RQ2",
        "file": "exp2_rq2_mla_vs_mlb_contrasts.csv",
        "default_n_tests": 9,
        "label": "SDXL vs PixArt-α",
    },
    {
        "rq": "RQ4",
        "file": "exp4_rq4_spatial_vs_frequency_contrasts.csv",
        "default_n_tests": 9,
        "label": "spatial − frequency gap",
    },
    {
        "rq": "RQ5",
        "file": "exp5_rq5_encryption_contrasts.csv",
        "default_n_tests": 18,
        "label": "plain vs encrypted",
    },
)


def _stratum_n_per_group(row: dict) -> int | None:
    """Best-effort pilot per-source n from a contrast CSV row.

    Exp 1/2/4 store n_pos_a, n_neg_a, n_pos_b, n_neg_b. We take the smaller
    side as the pilot group size so the extrapolation is conservative.
    """
    sizes = [
        _maybe_float(row.get(k))
        for k in ("n_pos_a", "n_neg_a", "n_pos_b", "n_neg_b")
    ]
    sizes = [int(v) for v in sizes if v is not None and v > 0]
    if not sizes:
        return None
    return min(sizes)


def run_power_analysis(
    run_dir: Path,
    *,
    target_diff: float = 0.05,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
) -> tuple[Path, Path]:
    """Compute per-stratum and per-RQ minimum-n recommendations.

    Returns paths to ``power_analysis.csv`` and ``power_summary.csv``.
    """
    metrics_dir = run_dir / "metrics"
    if not metrics_dir.exists():
        raise FileNotFoundError(f"metrics/ directory not found under {run_dir}")

    detail_rows: list[dict] = []
    summary_rows: list[dict] = []

    for family in _FAMILIES:
        rows = _read_rows(metrics_dir / family["file"])
        n_tests = max(len(rows), family["default_n_tests"])
        per_stratum_min: list[int] = []
        for r in rows:
            diff = _maybe_float(r.get("diff"))
            se = _maybe_float(r.get("se"))
            pilot_n = _stratum_n_per_group(r)
            if diff is None or se is None or pilot_n is None:
                continue
            n_for_observed_80 = required_n_from_pilot(
                observed_diff=diff, observed_se=se, pilot_n_per_group=pilot_n,
                alpha=alpha, power=0.80, n_tests=n_tests,
            )
            n_for_observed_90 = required_n_from_pilot(
                observed_diff=diff, observed_se=se, pilot_n_per_group=pilot_n,
                alpha=alpha, power=0.90, n_tests=n_tests,
            )
            n_for_target_80 = required_n_from_pilot(
                observed_diff=target_diff, observed_se=se,
                pilot_n_per_group=pilot_n,
                alpha=alpha, power=0.80, n_tests=n_tests,
            )
            detail_rows.append({
                "rq": family["rq"],
                "label": family["label"],
                "detector": r.get("detector", ""),
                "method": r.get("method", ""),
                "payload_level": r.get("payload_level", ""),
                "source": r.get("source", ""),
                "pilot_n_per_group": pilot_n,
                "observed_diff": diff,
                "observed_se": se,
                "n_tests_assumed": n_tests,
                "n_for_observed_80": n_for_observed_80,
                "n_for_observed_90": n_for_observed_90,
                "n_for_target_diff_80": n_for_target_80,
                "target_diff_assumed": target_diff,
            })
            if n_for_observed_80 is not None:
                per_stratum_min.append(n_for_observed_80)

        # A priori envelope for this RQ family (no observed data needed).
        n_a_priori_80 = required_n_a_priori(
            target_diff=target_diff, alpha=alpha, power=0.80,
            n_tests=family["default_n_tests"], paired=(family["rq"] == "RQ5"),
        )

        summary_rows.append({
            "rq": family["rq"],
            "label": family["label"],
            "n_tests_assumed": family["default_n_tests"],
            "target_diff": target_diff,
            "alpha": alpha,
            "power": power,
            "n_a_priori_80pct_power": n_a_priori_80,
            "n_pilot_strata_used": len(per_stratum_min),
            "n_pilot_min": min(per_stratum_min) if per_stratum_min else None,
            "n_pilot_max": max(per_stratum_min) if per_stratum_min else None,
            "n_pilot_p90": (
                sorted(per_stratum_min)[int(0.9 * (len(per_stratum_min) - 1))]
                if per_stratum_min else None
            ),
        })

    detail_path = metrics_dir / "power_analysis.csv"
    if detail_rows:
        with detail_path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(detail_rows[0].keys()))
            writer.writeheader()
            writer.writerows(detail_rows)

    summary_path = metrics_dir / "power_summary.csv"
    with summary_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)

    print(f"Wrote {detail_path}")
    print(f"Wrote {summary_path}")
    return detail_path, summary_path


def _print_a_priori(target_diff: float, target_auc: float, n_tests: int) -> None:
    print(f"A priori power analysis (Hanley–McNeil variance, α=0.05, two-sided):")
    print(f"  target AUC operating point : {target_auc}")
    print(f"  target ΔAUC to detect      : {target_diff}")
    print(f"  family size (Holm)          : {n_tests}")
    for power in (0.80, 0.90):
        n_unpaired = required_n_a_priori(
            target_diff=target_diff, target_auc=target_auc,
            alpha=0.05, power=power, n_tests=n_tests, paired=False,
        )
        n_paired = required_n_a_priori(
            target_diff=target_diff, target_auc=target_auc,
            alpha=0.05, power=power, n_tests=n_tests, paired=True,
        )
        print(f"  required n at {int(power*100)}% power : "
              f"unpaired={n_unpaired}, paired={n_paired}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline power analysis.")
    parser.add_argument("run_dir", nargs="?", type=Path, default=None,
                        help="Existing run dir; required unless --a-priori.")
    parser.add_argument("--a-priori", action="store_true",
                        help="Skip pilot extrapolation; just print closed-form sample sizes.")
    parser.add_argument("--target-diff", type=float, default=0.05,
                        help="Minimum detectable ΔAUC (default 0.05 per proposal).")
    parser.add_argument("--target-auc", type=float, default=0.85,
                        help="Operating AUC point for the variance approximation.")
    parser.add_argument("--n-tests", type=int, default=9,
                        help="Family size for Holm correction (default 9).")
    parser.add_argument("--alpha", type=float, default=DEFAULT_ALPHA)
    parser.add_argument("--power", type=float, default=DEFAULT_POWER)
    args = parser.parse_args()

    if args.a_priori or args.run_dir is None:
        _print_a_priori(
            target_diff=args.target_diff,
            target_auc=args.target_auc,
            n_tests=args.n_tests,
        )
        if args.run_dir is None:
            sys.exit(0)

    run_power_analysis(
        args.run_dir,
        target_diff=args.target_diff,
        alpha=args.alpha,
        power=args.power,
    )


if __name__ == "__main__":
    main()
