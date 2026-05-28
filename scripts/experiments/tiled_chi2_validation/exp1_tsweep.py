"""Experiment 1: tile-size sweep for the tile-local chi^2-DCT detector.

Sweeps the tile-grid size T over a configurable list (default
{1, 2, 3, 4, 6, 8}) and reports per-(method, payload, encryption, source)
AUC for each T value, on the existing DCT-stego test corpus.

The expected outcome shape:
  - T=1 recovers the global Westfeld chi^2 (single tile = whole image).
  - The production detector uses T=2.
  - An interior optimum at T=2 or T=3 would confirm the gain is not
    monotone with finer tiling (i.e. the choice of T matters).
  - A monotone-increasing curve would suggest going even finer.
  - A flat curve would suggest T=1 (global) is already optimal -- which
    contradicts the v4 paper's headline claim.

Output:
  runs/tiled_validation/exp1_tsweep/results.csv  (T, method, payload, ..., auc)
  runs/tiled_validation/exp1_tsweep/auc_vs_T.png (line plot, one line per cell)

Cost (laptop CPU):
  ~5 min per T value on a 3000-group test corpus, ~30 min total for the
  default 6-value sweep.  Use --max-cells-per-strata to dry-run faster.

Usage:
  venv312/bin/python -m scripts.experiments.tiled_chi2_validation.exp1_tsweep \
      --run runs/prototype_full_20260513_005357_p8765 \
      --tiles 1 2 3 4 6 8 \
      --pool max
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

# ---- sys.path setup ----
from scripts.experiments.tiled_chi2_validation._lib import (
    ensure_project_root_on_sys_path,
)
ensure_project_root_on_sys_path()

from scripts.experiments.tiled_chi2_validation._lib import (  # noqa: E402  (after path setup)
    METRICS,
    apply_metric_axis_style,
    compute_auc_per_cell,
    configure_matplotlib_for_paper,
    enumerate_dct_test_cells,
    palette_for_payloads,
    score_cells,
    tiled_chi2_score,
    write_csv,
)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", type=Path, required=True,
                   help="Test run directory with covers/dct and stego/dct subdirs.")
    p.add_argument("--out-dir", type=Path,
                   default=Path("runs/tiled_validation/exp1_tsweep"),
                   help="Output directory (default: runs/tiled_validation/exp1_tsweep).")
    p.add_argument("--tiles", type=int, nargs="+", default=[1, 2, 3, 4, 6, 8],
                   help="T values to sweep.")
    p.add_argument("--pool", choices=["max", "mean", "median", "topk_mean"], default="max",
                   help="Pooling rule across tiles (default: max).")
    p.add_argument("--payload-levels", nargs="+", default=["low", "medium", "high"],
                   help="Payload level directory names to iterate under stego/dct/. "
                        "Default matches the main pipeline (low/medium/high). For BOSSBase "
                        "runs from import_bossbase.py pass p005 p010 p020 p030 p040 p050.")
    p.add_argument("--sources", nargs="+", default=["real", "ml_a", "ml_b"],
                   help="Source directory names to iterate (default: real ml_a ml_b). "
                        "BOSSBase runs only have 'real'; pass --sources real for those.")
    p.add_argument("--max-cells-per-strata", type=int, default=None,
                   help="Cap cells per (payload, encryption, source) for quick dry runs.")
    args = p.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    all_auc_rows: list[dict] = []
    for T in args.tiles:
        t0 = time.time()
        print(f"\n=== T={T} ===")
        cells = list(enumerate_dct_test_cells(
            args.run,
            payload_levels=args.payload_levels,
            sources=args.sources,
            max_cells_per_strata=args.max_cells_per_strata,
        ))
        print(f"  scoring {len(cells)} cells with tile-local chi^2 (T={T}, pool={args.pool})")
        rows = score_cells(cells, lambda b: tiled_chi2_score(b, tiles=T, pool=args.pool))
        auc_rows = compute_auc_per_cell(rows)
        for entry in auc_rows:
            entry["T"] = T
            entry["pool"] = args.pool
        all_auc_rows.extend(auc_rows)
        mean_auc = sum(r["auc"] for r in auc_rows) / len(auc_rows)
        mean_pe = sum(r["pe_min"] for r in auc_rows) / len(auc_rows)
        print(f"  T={T}: {len(auc_rows)} strata, mean AUC {mean_auc:.4f}, "
              f"mean P_E^min {mean_pe:.4f}, took {(time.time() - t0) / 60:.1f} min")

    csv_path = args.out_dir / "results.csv"
    write_csv(csv_path, all_auc_rows)
    print(f"\nwrote {csv_path} ({len(all_auc_rows)} rows)")

    for metric, ylabel, _ in METRICS:
        out_path = args.out_dir / f"{metric}_vs_T.png"
        _plot(all_auc_rows, out_path, args.payload_levels, metric=metric, ylabel=ylabel)
        print(f"wrote {out_path}")


def _plot(rows: list[dict], out_path: Path, payload_levels: list[str],
          *, metric: str, ylabel: str) -> None:
    """Plot ``metric`` vs T, one line per (payload, encryption) averaged over source."""
    import matplotlib.pyplot as plt
    from collections import defaultdict

    configure_matplotlib_for_paper()
    fig, ax = plt.subplots(figsize=(5.5, 3.5))

    grouped: dict[tuple[str, str], dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        grouped[(r["payload_level"], r["encryption"])][int(r["T"])].append(float(r[metric]))

    colors = palette_for_payloads(payload_levels)
    styles = {"plain": "-", "encrypted": "--"}
    for payload in payload_levels:
        for encryption in ("plain", "encrypted"):
            per_T = grouped.get((payload, encryption))
            if not per_T:
                continue
            xs = sorted(per_T.keys())
            ys = [sum(per_T[t]) / len(per_T[t]) for t in xs]
            ax.plot(xs, ys, color=colors.get(payload, "#888888"),
                    linestyle=styles[encryption],
                    marker="o", markersize=3.5,
                    label=f"{payload}/{encryption}")

    apply_metric_axis_style(ax, metric)
    ax.set_xlabel("tile-grid size T")
    ax.set_ylabel(ylabel)
    metric_title = "AUC" if metric == "auc" else r"$P_E^{\min}$"
    ax.set_title(rf"Tile-local $\chi^2$-DCT: {metric_title} vs.\ tile-size $T$")
    ax.legend(loc="best", fontsize=7, ncol=2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)


if __name__ == "__main__":
    main()
