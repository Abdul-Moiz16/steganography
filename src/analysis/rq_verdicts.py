"""
RQ verdicts: read the per-experiment contrast CSVs and emit structured
verdicts plus a human-readable Markdown summary.

This is the "did our proposal hold up?" layer that the report's results
overview pastes from. For each research question we consume the matching
``exp{N}_*_contrasts.csv`` file and decide:

    - n_strata           : how many cells the experiment compared
    - n_significant      : how many cells reach significance after the
                           experiment's own multiple-testing correction
                           (Holm for RQ1/RQ2; CI-excludes-zero for the
                           exploratory experiments; CI-within-margin for
                           the RQ5 verification check)
    - pooled_effect      : inverse-variance meta-analytic mean Δ
    - pooled_ci          : ±1.96·SE on the pooled estimate
    - verdict            : one of {supported, mixed, not_supported,
                           inconclusive_underpowered}

Usage
-----
    python -m src.analysis.rq_verdicts runs/<run-id>

Output
------
    metrics/rq_verdicts.json    machine-readable structured summary
    metrics/rq_verdicts.md      one-page human-readable summary
"""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

EQUIVALENCE_MARGIN = 0.025   # RQ5: encryption is "invariant" if |ΔAUC|<=0.025
CI_Z = 1.96                  # 95% CI in Wald form
MIN_PAIRS_CONFIRMATORY = 20  # mirrors PipelineConfig.MIN_N_GROUPS_CONFIRMATORY


# ── Generic helpers ──────────────────────────────────────────────────────────

def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def _maybe_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pooled_meta(rows: list[dict], diff_key: str = "diff", se_key: str = "se") -> dict | None:
    """Inverse-variance pooled mean of Δ across strata, with 95% CI.

    Returns None if no row has a usable (diff, se) pair.
    """
    usable: list[tuple[float, float]] = []
    for r in rows:
        d = _maybe_float(r.get(diff_key))
        s = _maybe_float(r.get(se_key))
        if d is None or s is None or s <= 0:
            continue
        usable.append((d, s))
    if not usable:
        return None
    weights = [1.0 / (s ** 2) for _, s in usable]
    diffs = [d for d, _ in usable]
    total_w = sum(weights)
    if total_w <= 0:
        return None
    pooled = sum(w * d for w, d in zip(weights, diffs)) / total_w
    pooled_se = math.sqrt(1.0 / total_w)
    return {
        "pooled_diff": pooled,
        "pooled_se": pooled_se,
        "pooled_ci_lo": pooled - CI_Z * pooled_se,
        "pooled_ci_hi": pooled + CI_Z * pooled_se,
        "n_pooled": len(usable),
    }


# ── Per-RQ classifiers ───────────────────────────────────────────────────────

def _verdict_from_holm_family(
    rows: list[dict],
    *,
    alpha: float = 0.05,
) -> dict:
    """Classify a confirmatory family (RQ1, RQ2) where Holm-adjusted p<alpha
    matters. Direction consistency informs whether the verdict is unified
    or mixed.
    """
    n_strata = len(rows)
    n_underpowered = 0
    n_significant_pos = 0
    n_significant_neg = 0
    for r in rows:
        n_a = _maybe_float(r.get("n_pos_a")) or 0
        n_b = _maybe_float(r.get("n_pos_b")) or 0
        if min(n_a, n_b) < MIN_PAIRS_CONFIRMATORY:
            n_underpowered += 1
        p_holm = _maybe_float(r.get("p_holm"))
        diff = _maybe_float(r.get("diff"))
        if p_holm is None or diff is None:
            continue
        if p_holm <= alpha:
            if diff > 0:
                n_significant_pos += 1
            elif diff < 0:
                n_significant_neg += 1

    n_significant = n_significant_pos + n_significant_neg
    pooled = _pooled_meta(rows) or {}

    if n_strata == 0:
        verdict = "no_data"
    elif n_underpowered == n_strata:
        verdict = "inconclusive_underpowered"
    elif n_significant == 0:
        verdict = "not_supported"
    elif n_significant_pos > 0 and n_significant_neg > 0:
        verdict = "mixed"
    else:
        verdict = "supported"

    return {
        "n_strata": n_strata,
        "n_significant_holm_0_05": n_significant,
        "n_significant_positive": n_significant_pos,
        "n_significant_negative": n_significant_neg,
        "n_underpowered_strata": n_underpowered,
        "verdict": verdict,
        **pooled,
    }


def _verdict_from_ci_family(rows: list[dict], *, alpha: float = 0.05) -> dict:
    """Classify an exploratory family (RQ4) where the 95% CI excluding zero
    is the de-facto significance criterion. RQ3's payload-interaction table
    is treated separately by ``_verdict_for_rq3`` because its rows are
    per-(source × payload) AUCs rather than contrasts.
    """
    n_strata = len(rows)
    n_significant_pos = 0
    n_significant_neg = 0
    for r in rows:
        diff = _maybe_float(r.get("diff"))
        lo = _maybe_float(r.get("ci_lo"))
        hi = _maybe_float(r.get("ci_hi"))
        if diff is None or lo is None or hi is None:
            continue
        if lo > 0:
            n_significant_pos += 1
        elif hi < 0:
            n_significant_neg += 1

    n_significant = n_significant_pos + n_significant_neg
    pooled = _pooled_meta(rows) or {}

    if n_strata == 0:
        verdict = "no_data"
    elif n_significant == 0:
        verdict = "not_supported"
    elif n_significant_pos > 0 and n_significant_neg > 0:
        verdict = "mixed"
    else:
        verdict = "supported"

    return {
        "n_strata": n_strata,
        "n_significant_ci_excludes_0": n_significant,
        "n_significant_positive": n_significant_pos,
        "n_significant_negative": n_significant_neg,
        "verdict": verdict,
        **pooled,
    }


def _verdict_for_rq3(rows: list[dict]) -> dict:
    """RQ3 (exploratory): does payload size change the real-vs-ML detectability gap?

    The contrast file records per-source AUC + the real-vs-ML gap per
    (detector, method, payload). We summarise the gap distribution across
    payload levels and look for monotone amplification.
    """
    by_pl: dict[str, list[float]] = {"low": [], "medium": [], "high": []}
    n_strata = 0
    for r in rows:
        if r.get("source") != "real":
            continue
        pl = r.get("payload_level")
        gap = _maybe_float(r.get("real_minus_ml_gap"))
        if pl not in by_pl or gap is None:
            continue
        by_pl[pl].append(gap)
        n_strata += 1

    means = {pl: (sum(vs) / len(vs) if vs else None) for pl, vs in by_pl.items()}
    populated = [(pl, m) for pl, m in [("low", means["low"]), ("medium", means["medium"]),
                                       ("high", means["high"])] if m is not None]

    if len(populated) < 2:
        verdict = "no_data"
        monotone = None
    else:
        levels_present = [pl for pl, _ in populated]
        deltas = [populated[i + 1][1] - populated[i][1] for i in range(len(populated) - 1)]
        monotone_up = all(d > 0 for d in deltas)
        monotone_down = all(d < 0 for d in deltas)
        monotone = "increasing" if monotone_up else ("decreasing" if monotone_down else "non_monotonic")
        max_gap = max(abs(m) for _, m in populated)
        verdict = "supported" if (monotone in ("increasing", "decreasing") and max_gap > 0.02) else (
            "not_supported" if max_gap < 0.01 else "mixed"
        )

    return {
        "n_strata": n_strata,
        "mean_gap_by_payload": means,
        "monotone_trend": monotone,
        "verdict": verdict,
    }


def _verdict_for_rq5(rows: list[dict], *, margin: float = EQUIVALENCE_MARGIN) -> dict:
    """RQ5 (verification): encryption is "invariant" if the CI lies inside
    [-margin, +margin] for every stratum.
    """
    n_strata = len(rows)
    n_within = 0
    n_violating = 0
    for r in rows:
        lo = _maybe_float(r.get("ci_lo"))
        hi = _maybe_float(r.get("ci_hi"))
        if lo is None or hi is None:
            continue
        if -margin <= lo and hi <= margin:
            n_within += 1
        else:
            n_violating += 1

    pooled = _pooled_meta(rows) or {}
    if n_strata == 0:
        verdict = "no_data"
    elif n_violating == 0:
        verdict = "supported"  # invariance holds
    elif n_within == 0:
        verdict = "not_supported"  # invariance fully violated
    else:
        verdict = "mixed"

    return {
        "n_strata": n_strata,
        "margin": margin,
        "n_within_margin": n_within,
        "n_outside_margin": n_violating,
        "verdict": verdict,
        **pooled,
    }


# ── Verdict assembly ─────────────────────────────────────────────────────────

_RQ_SPECS = (
    {
        "rq": "RQ1",
        "title": "Real vs pooled ML carrier sources",
        "test": "DeLong + Bonferroni–Holm (confirmatory)",
        "file": "exp1_rq1_real_vs_pooled_ml_contrasts.csv",
        "classifier": _verdict_from_holm_family,
    },
    {
        "rq": "RQ2",
        "title": "SDXL vs FLUX.1-schnell within ML",
        "test": "DeLong + Bonferroni–Holm (confirmatory)",
        "file": "exp2_rq2_mla_vs_mlb_contrasts.csv",
        "classifier": _verdict_from_holm_family,
    },
    {
        "rq": "RQ3",
        "title": "Payload-level interaction with carrier source",
        "test": "Real–ML AUC gap across payload levels (exploratory)",
        "file": "exp3_rq3_payload_interaction_contrasts.csv",
        "classifier": _verdict_for_rq3,
    },
    {
        "rq": "RQ4",
        "title": "Embedding branch × source interaction",
        "test": "Wald CI on (spatial gap − frequency gap) (exploratory)",
        "file": "exp4_rq4_spatial_vs_frequency_contrasts.csv",
        "classifier": _verdict_from_ci_family,
    },
    {
        "rq": "RQ5",
        "title": "Encryption invariance (plain vs AES-256-CBC)",
        "test": "Paired DeLong, equivalence check within ±2.5% AUC margin",
        "file": "exp5_rq5_encryption_contrasts.csv",
        "classifier": _verdict_for_rq5,
    },
)


def compute_rq_verdicts(metrics_dir: Path) -> dict:
    """Build the verdict dictionary from contrast CSVs in ``metrics_dir``."""
    out = {"verdicts": {}, "metrics_dir": str(metrics_dir)}
    for spec in _RQ_SPECS:
        rows = _read_rows(metrics_dir / spec["file"])
        verdict_payload = spec["classifier"](rows)
        out["verdicts"][spec["rq"]] = {
            "title": spec["title"],
            "test": spec["test"],
            "contrasts_file": spec["file"],
            "rows_available": len(rows),
            **verdict_payload,
        }
    return out


# ── Markdown rendering ───────────────────────────────────────────────────────

_VERDICT_GLYPH = {
    "supported": "✔  supported",
    "mixed": "✖  mixed",
    "not_supported": "—  not supported",
    "inconclusive_underpowered": "?  underpowered",
    "no_data": "·  no data",
}


def _fmt_pooled(v: dict) -> str:
    pooled = v.get("pooled_diff")
    lo = v.get("pooled_ci_lo")
    hi = v.get("pooled_ci_hi")
    if pooled is None or lo is None or hi is None:
        return "—"
    return f"{pooled:+.4f}  (95% CI [{lo:+.4f}, {hi:+.4f}])"


def render_markdown(verdicts: dict) -> str:
    lines: list[str] = ["# Research Question Verdicts", ""]
    lines.append(
        "Auto-generated from the per-experiment contrast CSVs. Drop this into "
        "the report's results overview or use the JSON sibling for downstream "
        "cross-referencing."
    )
    lines.append("")

    for rq, v in verdicts["verdicts"].items():
        lines.append(f"## {rq} — {v['title']}")
        lines.append("")
        lines.append(f"- **Verdict:** {_VERDICT_GLYPH.get(v.get('verdict', ''), v.get('verdict', '—'))}")
        lines.append(f"- **Test:** {v['test']}")
        lines.append(f"- **Strata evaluated:** {v.get('n_strata', 0)}")
        if "n_significant_holm_0_05" in v:
            lines.append(
                f"- **Significant after Holm (α=0.05):** "
                f"{v['n_significant_holm_0_05']} / {v.get('n_strata', 0)}  "
                f"(+ {v.get('n_significant_positive', 0)}, − {v.get('n_significant_negative', 0)})"
            )
        if "n_significant_ci_excludes_0" in v:
            lines.append(
                f"- **Strata with 95% CI excluding 0:** "
                f"{v['n_significant_ci_excludes_0']} / {v.get('n_strata', 0)}  "
                f"(+ {v.get('n_significant_positive', 0)}, − {v.get('n_significant_negative', 0)})"
            )
        if "n_within_margin" in v:
            lines.append(
                f"- **Strata within ±{v['margin']:.3f} AUC margin:** "
                f"{v['n_within_margin']} / {v.get('n_strata', 0)}  "
                f"(violating: {v['n_outside_margin']})"
            )
        if v.get("monotone_trend"):
            lines.append(f"- **Real–ML gap trend across payload:** {v['monotone_trend']}")
            means = v.get("mean_gap_by_payload") or {}
            for pl in ("low", "medium", "high"):
                if means.get(pl) is not None:
                    lines.append(f"    - {pl}: {means[pl]:+.4f}")
        if "pooled_diff" in v:
            lines.append(f"- **Pooled Δ-AUC (inverse-variance):** {_fmt_pooled(v)}")
        if v.get("n_underpowered_strata"):
            lines.append(
                f"- **Underpowered strata (n_pairs < {MIN_PAIRS_CONFIRMATORY}):** "
                f"{v['n_underpowered_strata']}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def run_rq_verdicts(run_dir: Path) -> tuple[Path, Path]:
    """Compute verdicts and write the JSON + Markdown reports under metrics/.

    Returns ``(json_path, markdown_path)``.
    """
    metrics_dir = run_dir / "metrics"
    if not metrics_dir.exists():
        raise FileNotFoundError(f"metrics/ directory not found under {run_dir}")
    data = compute_rq_verdicts(metrics_dir)
    json_path = metrics_dir / "rq_verdicts.json"
    md_path = metrics_dir / "rq_verdicts.md"
    json_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    md_path.write_text(render_markdown(data), encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return json_path, md_path


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python -m src.analysis.rq_verdicts <run_dir>")
        sys.exit(1)
    run_rq_verdicts(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
