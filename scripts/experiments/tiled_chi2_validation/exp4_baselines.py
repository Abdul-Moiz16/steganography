"""Experiment 4: comparison against literature-precedent baselines.

Scores every DCT-stego test cell with FOUR detectors on the SAME pairs:

  - global chi^2-DCT     (the textbook Westfeld 1999 detector)
  - sliding-window chi^2 (Westfeld & Pfitzmann 1999, overlapping windows)
  - tile-local chi^2     (this paper's proposal, max-pool, T=2)
  - DCTR (if a trained checkpoint is supplied via --dctr-models)

Tile-local is the contribution being validated; the other three are the
points of comparison.  A clean win for tile-local on (method, payload)
cells where the global chi^2 is weak (low payload, real carriers) is the
positive result the v4 paper claims.  Mixed results in regimes where
DCTR or sliding-window already dominate would temper the claim.

Output:
  runs/tiled_validation/exp4_baselines/results.csv
  runs/tiled_validation/exp4_baselines/auc_by_detector.png

Usage:
  venv312/bin/python -m scripts.experiments.tiled_chi2_validation.exp4_baselines \
      --run runs/prototype_full_20260513_005357_p8765 \
      [--dctr-models models/training_v1/dctr_dct_*.pkl]

DCTR comparison is optional; skipped silently if --dctr-models is not given.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from scripts.experiments.tiled_chi2_validation._lib import (
    ensure_project_root_on_sys_path,
)
ensure_project_root_on_sys_path()

from scripts.experiments.tiled_chi2_validation._lib import (  # noqa: E402
    METRICS,
    PALETTE,
    apply_metric_axis_style,
    compute_auc_per_cell,
    configure_matplotlib_for_paper,
    enumerate_dct_test_cells,
    palette_for_payloads,
    score_cells,
    sliding_chi2_score,
    tiled_chi2_score,
    write_csv,
)

# Reuse the production global chi^2-DCT detector (T=1 case of tile-local
# is mathematically equivalent but the explicit detector is the canonical
# baseline cited in the paper).
from src.detection.chi_square_dct import chi_square_dct_score  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, default=Path("runs/tiled_validation/exp4_baselines"))
    p.add_argument("--tiles", type=int, default=2,
                   help="T for the tile-local detector (default 2; paper's headline value).")
    p.add_argument("--sliding-window", type=int, default=4,
                   help="Window size for sliding chi^2 (default 4).")
    p.add_argument("--sliding-stride", type=int, default=2,
                   help="Stride for sliding chi^2 (default 2).")
    p.add_argument("--dctr-models", nargs="+", type=Path,
                   help="Optional DCTR .pkl checkpoints (per payload). When given, "
                        "DCTR is added to the comparison.")
    p.add_argument("--payload-levels", nargs="+", default=["low", "medium", "high"],
                   help="Payload level directory names (default: low medium high). "
                        "Pass p005 p010 p020 p030 p040 p050 for BOSSBase runs.")
    p.add_argument("--sources", nargs="+", default=["real", "ml_a", "ml_b"],
                   help="Source directory names (default: real ml_a ml_b). "
                        "Pass --sources real for BOSSBase runs.")
    p.add_argument("--max-cells-per-strata", type=int, default=None)
    args = p.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    detectors: dict[str, callable] = {
        "global_chi2_dct": lambda b: chi_square_dct_score(b),
        f"sliding_chi2_w{args.sliding_window}_s{args.sliding_stride}": (
            lambda b: sliding_chi2_score(b, window=args.sliding_window,
                                          stride=args.sliding_stride)
        ),
        f"tiled_chi2_T{args.tiles}_max": (
            lambda b: tiled_chi2_score(b, tiles=args.tiles, pool="max")
        ),
    }

    all_auc_rows: list[dict] = []
    for name, score_fn in detectors.items():
        t0 = time.time()
        print(f"\n=== {name} ===")
        cells = list(enumerate_dct_test_cells(
            args.run,
            payload_levels=args.payload_levels,
            sources=args.sources,
            max_cells_per_strata=args.max_cells_per_strata,
        ))
        rows = score_cells(cells, score_fn)
        auc_rows = compute_auc_per_cell(rows)
        for entry in auc_rows:
            entry["detector"] = name
        all_auc_rows.extend(auc_rows)
        mean_auc = sum(r["auc"] for r in auc_rows) / max(1, len(auc_rows))
        mean_pe = sum(r["pe_min"] for r in auc_rows) / max(1, len(auc_rows))
        print(f"  {name}: {len(auc_rows)} strata, mean AUC {mean_auc:.4f}, "
              f"mean P_E^min {mean_pe:.4f}, took {(time.time() - t0) / 60:.1f} min")

    if args.dctr_models:
        print("\n=== DCTR ===")
        _score_dctr_into(all_auc_rows, args)

    csv_path = args.out_dir / "results.csv"
    write_csv(csv_path, all_auc_rows)
    print(f"\nwrote {csv_path} ({len(all_auc_rows)} rows)")

    for metric, ylabel, _ in METRICS:
        out_path = args.out_dir / f"{metric}_by_detector.png"
        _plot(all_auc_rows, out_path, args.payload_levels, metric=metric, ylabel=ylabel)
        print(f"wrote {out_path}")


def _score_dctr_into(all_auc_rows: list[dict], args: argparse.Namespace) -> None:
    """Add DCTR rows by reading existing predictions or running fresh inference.

    For simplicity this looks for an existing predictions_dctr.csv under
    args.run/predictions/ (which V1's apply_dctr_to_run.py emits) and
    aggregates it into AUC entries with detector="DCTR".  If no such CSV
    exists we print a hint and skip.
    """
    pred = args.run / "predictions" / "predictions_dctr.csv"
    if not pred.exists():
        print(f"  no {pred}; skipping DCTR. "
              f"Run scripts/inference/apply_dctr_to_run.py first.")
        return
    import csv as _csv
    rows = []
    with pred.open() as f:
        for r in _csv.DictReader(f):
            if r["detector"] != "dctr" or r["method"] != "dct":
                continue
            rows.append({
                "method": r["method"],
                "payload_level": r["payload_level"],
                "encryption": r["encryption"],
                "source": r["source"],
                "label": int(r["label"]),
                "score": float(r["score"]),
            })
    auc_rows = compute_auc_per_cell(rows)
    for entry in auc_rows:
        entry["detector"] = "DCTR_v1"
    all_auc_rows.extend(auc_rows)
    print(f"  DCTR: {len(auc_rows)} strata, mean AUC {sum(r['auc'] for r in auc_rows) / len(auc_rows):.4f}")


def _plot(rows: list[dict], out_path: Path, payload_levels: list[str],
          *, metric: str, ylabel: str) -> None:
    """Plot mean ``metric`` per (detector, payload), grouped by detector."""
    import matplotlib.pyplot as plt
    from collections import defaultdict

    configure_matplotlib_for_paper()
    fig, ax = plt.subplots(figsize=(6.5, 3.5))

    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        grouped[r["detector"]][r["payload_level"]].append(float(r[metric]))

    detectors = list(grouped.keys())
    color = palette_for_payloads(payload_levels)

    x = list(range(len(detectors)))
    n = max(len(payload_levels), 1)
    w = 0.8 / n
    offset = (n - 1) / 2
    for i, payload in enumerate(payload_levels):
        ys = [sum(grouped[d].get(payload, [])) / max(1, len(grouped[d].get(payload, [])))
              for d in detectors]
        ax.bar([xi + (i - offset) * w for xi in x], ys, width=w,
               color=color.get(payload, "#888888"),
               edgecolor=PALETTE["umdark"], linewidth=0.4, label=payload)
    apply_metric_axis_style(ax, metric)
    ax.set_xticks(x)
    ax.set_xticklabels(detectors, rotation=15, ha="right", fontsize=7)
    ax.set_ylabel(ylabel)
    metric_title = "AUC" if metric == "auc" else r"$P_E^{\min}$"
    ax.set_title(rf"DCT-domain detectors on shared test corpus: {metric_title}")
    ax.legend(loc="best", fontsize=8, title="payload", ncol=2 if n > 4 else 1)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)


if __name__ == "__main__":
    main()
