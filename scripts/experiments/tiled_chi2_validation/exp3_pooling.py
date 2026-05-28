"""Experiment 3: pooling-rule ablation.

Holds T fixed (default T=2, the production value) and sweeps the
pooling rule used to aggregate per-tile chi^2 scores into a single
image-level score:

  - max       (production -- the v4 paper's headline detector)
  - mean      (the global-null counterpart: heterogeneity averages out)
  - median    (robust counterpart of mean)
  - topk_mean (mean of top-K tiles; K=3 by default)

The interpretation:
  - If "max" beats "mean" substantially, the stego signal is sparse and
    localised -- a single tile carrying most of the embedding burden.
  - If "mean" matches or exceeds "max", heterogeneity is not what drives
    the gain and the production detector's claim is weakened.
  - "median" and "topk_mean" interpolate the two extremes.

Output:
  runs/tiled_validation/exp3_pooling/results.csv
  runs/tiled_validation/exp3_pooling/auc_by_pool.png

Usage:
  venv312/bin/python -m scripts.experiments.tiled_chi2_validation.exp3_pooling \
      --run runs/prototype_full_20260513_005357_p8765 \
      --tiles 2 \
      --pools max mean median topk_mean
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
    PALETTE,
    compute_auc_per_cell,
    configure_matplotlib_for_paper,
    enumerate_dct_test_cells,
    score_cells,
    tiled_chi2_score,
    write_csv,
)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, default=Path("runs/tiled_validation/exp3_pooling"))
    p.add_argument("--tiles", type=int, default=2, help="Fixed T value (default 2).")
    p.add_argument("--pools", nargs="+", default=["max", "mean", "median", "topk_mean"],
                   choices=["max", "mean", "median", "topk_mean"])
    p.add_argument("--topk", type=int, default=3, help="K for topk_mean pool.")
    p.add_argument("--max-cells-per-strata", type=int, default=None)
    args = p.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    all_auc_rows: list[dict] = []
    for pool in args.pools:
        t0 = time.time()
        print(f"\n=== pool={pool} (T={args.tiles}) ===")
        cells = list(enumerate_dct_test_cells(
            args.run, max_cells_per_strata=args.max_cells_per_strata
        ))
        score_fn = lambda b, _p=pool: tiled_chi2_score(b, tiles=args.tiles, pool=_p, topk=args.topk)
        rows = score_cells(cells, score_fn)
        auc_rows = compute_auc_per_cell(rows)
        for entry in auc_rows:
            entry["T"] = args.tiles
            entry["pool"] = pool
        all_auc_rows.extend(auc_rows)
        mean_auc = sum(r["auc"] for r in auc_rows) / max(1, len(auc_rows))
        print(f"  {pool}: {len(auc_rows)} strata, mean AUC {mean_auc:.4f}, took {(time.time() - t0) / 60:.1f} min")

    csv_path = args.out_dir / "results.csv"
    write_csv(csv_path, all_auc_rows)
    print(f"\nwrote {csv_path} ({len(all_auc_rows)} rows)")

    _plot(all_auc_rows, args.out_dir / "auc_by_pool.png", args.tiles)
    print(f"wrote {args.out_dir / 'auc_by_pool.png'}")


def _plot(rows: list[dict], out_path: Path, T: int) -> None:
    """Plot mean AUC per pool, faceted by payload."""
    import matplotlib.pyplot as plt
    from collections import defaultdict

    configure_matplotlib_for_paper()
    fig, ax = plt.subplots(figsize=(5.5, 3.0))

    # mean over (source, encryption) per (payload, pool)
    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        grouped[r["pool"]][r["payload_level"]].append(r["auc"])

    pools = list(grouped.keys())
    payloads = ["low", "medium", "high"]
    color = {"low": PALETTE["umdark"], "medium": PALETTE["umlight"], "high": PALETTE["umorange"]}

    x = list(range(len(pools)))
    w = 0.25
    for i, payload in enumerate(payloads):
        ys = [sum(grouped[p][payload]) / max(1, len(grouped[p][payload])) for p in pools]
        ax.bar([xi + (i - 1) * w for xi in x], ys, width=w,
               color=color[payload], edgecolor=PALETTE["umdark"], linewidth=0.4, label=payload)
    ax.set_xticks(x)
    ax.set_xticklabels(pools)
    ax.set_ylabel("mean ROC-AUC over (source, encryption)")
    ax.set_title(rf"Pooling-rule ablation (T={T})")
    ax.legend(loc="best", fontsize=8, title="payload")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)


if __name__ == "__main__":
    main()
