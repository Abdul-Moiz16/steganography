"""Experiment 2: cross-payload tile-size invariance.

This is a second view of the same data Experiment 1 produces.  It exists
as a separate script so that the user can run it as a one-shot replot
once exp1's results.csv is on disk, without re-scoring everything.

The question this experiment answers:
  Does the optimal T (from Exp 1's per-cell argmax) depend on payload
  level?  If yes, the tile size is locking onto a particular spatial
  frequency of carrier heterogeneity that varies with embedding rate.
  If no, the tile size is selecting a universal grain of the carrier.

Output:
  runs/tiled_validation/exp2_payload_invariance/argmax_T_by_payload.csv
  runs/tiled_validation/exp2_payload_invariance/argmax_T_by_payload.png

Usage (requires exp1 to have been run first):
  venv312/bin/python -m scripts.experiments.tiled_chi2_validation.exp2_payload_invariance \
      --exp1-results runs/tiled_validation/exp1_tsweep/results.csv
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from scripts.experiments.tiled_chi2_validation._lib import (
    ensure_project_root_on_sys_path,
)
ensure_project_root_on_sys_path()

from scripts.experiments.tiled_chi2_validation._lib import (  # noqa: E402
    PALETTE,
    configure_matplotlib_for_paper,
    write_csv,
)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--exp1-results", type=Path, required=True,
                   help="Path to exp1_tsweep/results.csv.")
    p.add_argument("--out-dir", type=Path,
                   default=Path("runs/tiled_validation/exp2_payload_invariance"))
    args = p.parse_args()

    rows: list[dict] = list(csv.DictReader(args.exp1_results.open()))
    if not rows:
        raise SystemExit(f"empty {args.exp1_results}; did exp1 run?")

    # Group by (payload, encryption, source) and compute best-T per stratum
    # for BOTH metrics: argmax T over AUC and argmin T over P_E^min.  Reporting
    # both lets the cross-payload invariance question be answered consistently
    # whether the reader prefers higher-AUC-is-better (modern convention) or
    # lower-P_E-is-better (Fridrich-lab convention used by DCTR's E_OOB).
    per_stratum_auc: dict[tuple[str, str, str], dict[int, float]] = defaultdict(dict)
    per_stratum_pe: dict[tuple[str, str, str], dict[int, float]] = defaultdict(dict)
    has_pe = "pe_min" in rows[0]
    for r in rows:
        key = (r["payload_level"], r["encryption"], r["source"])
        per_stratum_auc[key][int(r["T"])] = float(r["auc"])
        if has_pe:
            per_stratum_pe[key][int(r["T"])] = float(r["pe_min"])

    best_rows: list[dict] = []
    for (payload, encryption, source), aucs in sorted(per_stratum_auc.items()):
        best_T_auc = max(aucs.items(), key=lambda kv: kv[1])
        entry = {
            "payload_level": payload,
            "encryption": encryption,
            "source": source,
            "best_T_auc": best_T_auc[0],
            "best_auc": best_T_auc[1],
            "T_values_tested": ",".join(str(t) for t in sorted(aucs.keys())),
        }
        if has_pe:
            pes = per_stratum_pe[(payload, encryption, source)]
            best_T_pe = min(pes.items(), key=lambda kv: kv[1])
            entry["best_T_pe"] = best_T_pe[0]
            entry["best_pe_min"] = best_T_pe[1]
        best_rows.append(entry)

    out_csv = args.out_dir / "best_T_by_payload.csv"
    write_csv(out_csv, best_rows)
    print(f"wrote {out_csv} ({len(best_rows)} strata)")

    _plot(best_rows, args.out_dir / "argmax_T_by_payload.png", key="best_T_auc",
          subtitle="argmax T (AUC)")
    print(f"wrote {args.out_dir / 'argmax_T_by_payload.png'}")
    if has_pe:
        _plot(best_rows, args.out_dir / "argmin_T_by_payload.png", key="best_T_pe",
              subtitle=r"argmin T ($P_E^{\min}$)")
        print(f"wrote {args.out_dir / 'argmin_T_by_payload.png'}")


def _plot(rows: list[dict], out_path: Path, *, key: str, subtitle: str) -> None:
    """Faceted bar chart of best-T per payload, where ``key`` selects the
    'best' column (``best_T_auc`` for AUC argmax, ``best_T_pe`` for P_E^min
    argmin).  ``subtitle`` is appended to the figure title."""
    import matplotlib.pyplot as plt
    from collections import Counter

    configure_matplotlib_for_paper()

    # Order: low/medium/high if those are present (preserves prior look);
    # otherwise the lexicographic order in the CSV (covers p005..p050 case).
    seen = []
    seen_set: set[str] = set()
    for r in rows:
        p = r["payload_level"]
        if p not in seen_set:
            seen_set.add(p)
            seen.append(p)
    if set(seen) >= {"low", "medium", "high"}:
        payload_order = ["low", "medium", "high"]
    else:
        payload_order = sorted(seen)

    n = len(payload_order)
    # Cap facet width: scale figure with n but stay readable.
    fig, axes = plt.subplots(1, n, figsize=(2.5 * n, 2.4), sharey=True, squeeze=False)
    axes = axes[0]
    color_by_T = {1: PALETTE["umgray"], 2: PALETTE["umdark"], 3: PALETTE["umlight"],
                  4: PALETTE["umorange"], 6: "#A0A0A0", 8: "#7F2D08"}

    for ax, payload in zip(axes, payload_order):
        Ts = [int(r[key]) for r in rows if r["payload_level"] == payload]
        if not Ts:
            ax.axis("off"); continue
        counts = Counter(Ts)
        sorted_T = sorted(counts.keys())
        ax.bar(sorted_T, [counts[t] for t in sorted_T],
               color=[color_by_T.get(t, PALETTE["umgray"]) for t in sorted_T],
               edgecolor=PALETTE["umdark"], linewidth=0.4)
        ax.set_title(f"{payload} payload")
        ax.set_xlabel(subtitle)
        ax.set_xticks(sorted_T)
    axes[0].set_ylabel("# of (encryption, source) strata")
    fig.suptitle(rf"Optimal $T$ per payload ({subtitle})", fontsize=10)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)


if __name__ == "__main__":
    main()
