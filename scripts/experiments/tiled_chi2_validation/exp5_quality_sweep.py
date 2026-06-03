"""Experiment 5: JPEG-quality sweep (SKELETON -- requires fresh embedding cycle).

Tests whether the tile-local detector's advantage over the global
chi^2-DCT is JPEG-quality-dependent.  Sweeps Q in {75, 85, 90, 95, 98}.

UNLIKE experiments 1-4, this one CANNOT reuse the existing test corpus
directly: the corpus is embedded at Q=95 only.  To run experiment 5
you need to re-embed the existing covers at each target Q value first,
then score with the tile-local + global detectors.

This file documents the two missing pieces and provides the
post-embedding scoring loop.  The re-embedding step itself is a small
extension to scripts/training/generate_training_set.py (or to a new
scripts/inference/rerun_with_quality_sweep.py wrapper) that:

  1. Reads the existing test covers (real + ml_a + ml_b at Q=95).
  2. For each target Q in {75, 85, 90, 95, 98}:
       a. Re-encode covers at Q using PIL (or jpeglib for header fidelity).
       b. Embed LSB+DCT stegos using runner.run_embedding_stage with the
          new covers + same payloads, write to runs/quality_sweep_Q{q}/.
  3. Once those runs exist, this script loops over them and produces the
     comparison plot.

Estimated cost:
  Re-embed:  ~3-5 hours on Vast.ai (5 Q values x existing test corpus size).
  Score:     ~30 min on laptop after embed completes.

This skeleton is intentionally not runnable end-to-end without that
embed step.  When the re-embedding script lands it can be added as an
import here and the pipeline becomes one command.

Output target (when complete):
  runs/tiled_validation/exp5_quality_sweep/results.csv
  runs/tiled_validation/exp5_quality_sweep/auc_vs_quality.png
"""
from __future__ import annotations

import argparse
import sys
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
    score_cells,
    tiled_chi2_score,
    write_csv,
)
from src.detection.chi_square_dct import chi_square_dct_score  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--quality-runs", nargs="+", type=Path, required=True,
                   help="Test-run directories already re-embedded at each target Q. "
                        "Example: runs/quality_sweep_Q75 runs/quality_sweep_Q85 ... "
                        "Each directory must follow the standard runs/<id>/ layout.")
    p.add_argument("--tiles", type=int, default=2)
    p.add_argument("--out-dir", type=Path, default=Path("runs/tiled_validation/exp5_quality_sweep"))
    p.add_argument("--max-cells-per-strata", type=int, default=None)
    args = p.parse_args()

    if not args.quality_runs:
        print("No --quality-runs supplied.  See the module docstring for the missing "
              "re-embedding step that has to land before this experiment can run.")
        sys.exit(2)

    args.out_dir.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict] = []
    for run_dir in args.quality_runs:
        Q = _infer_quality_from_run_name(run_dir)
        if Q is None:
            print(f"  could not infer Q from {run_dir.name}; skipping. "
                  f"Name your runs like 'quality_sweep_Q85' so the parser picks it up.")
            continue
        print(f"\n=== Q={Q} ({run_dir}) ===")
        cells = list(enumerate_dct_test_cells(
            run_dir, max_cells_per_strata=args.max_cells_per_strata
        ))
        if not cells:
            print(f"  no DCT cells in {run_dir}; was the re-embedding step run?")
            continue
        for det_name, score_fn in [
            ("global_chi2_dct", lambda b: chi_square_dct_score(b)),
            (f"tiled_chi2_T{args.tiles}", lambda b: tiled_chi2_score(b, tiles=args.tiles)),
        ]:
            t0 = time.time()
            rows = score_cells(cells, score_fn)
            auc_rows = compute_auc_per_cell(rows)
            for r in auc_rows:
                r["detector"] = det_name
                r["jpeg_quality"] = Q
            all_rows.extend(auc_rows)
            mean_auc = sum(r["auc"] for r in auc_rows) / max(1, len(auc_rows))
            print(f"  {det_name}: {len(auc_rows)} strata, mean AUC {mean_auc:.4f}, took {(time.time() - t0) / 60:.1f} min")

    csv_path = args.out_dir / "results.csv"
    write_csv(csv_path, all_rows)
    print(f"\nwrote {csv_path} ({len(all_rows)} rows)")
    for metric, ylabel, _ in METRICS:
        out_path = args.out_dir / f"{metric}_vs_quality.png"
        _plot(all_rows, out_path, metric=metric, ylabel=ylabel)
        print(f"wrote {out_path}")


def _infer_quality_from_run_name(run_dir: Path) -> int | None:
    import re
    m = re.search(r"Q(\d{2,3})", run_dir.name)
    if m:
        return int(m.group(1))
    return None


def _plot(rows: list[dict], out_path: Path, *, metric: str, ylabel: str) -> None:
    import matplotlib.pyplot as plt
    from collections import defaultdict

    configure_matplotlib_for_paper()
    fig, ax = plt.subplots(figsize=(5.5, 3.0))
    grouped: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        grouped[r["detector"]][int(r["jpeg_quality"])].append(float(r[metric]))

    color_by_detector = {
        "global_chi2_dct": PALETTE["umgray"],
        "tiled_chi2_T2": PALETTE["umorange"],
        "tiled_chi2_T3": PALETTE["umdark"],
    }
    for det, by_Q in grouped.items():
        xs = sorted(by_Q.keys())
        ys = [sum(by_Q[q]) / len(by_Q[q]) for q in xs]
        ax.plot(xs, ys, color=color_by_detector.get(det, PALETTE["umdark"]),
                marker="o", markersize=4, label=det)
    apply_metric_axis_style(ax, metric)
    ax.set_xlabel("JPEG quality factor")
    ax.set_ylabel(ylabel)
    metric_title = "AUC" if metric == "auc" else r"$P_E^{\min}$"
    ax.set_title(rf"Tile-local vs.\ global $\chi^2$-DCT across JPEG quality: {metric_title}")
    ax.legend(loc="best", fontsize=8)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)


if __name__ == "__main__":
    main()
