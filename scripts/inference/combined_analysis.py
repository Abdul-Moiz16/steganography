"""Produce combined (classical + learned) analysis output.

This is the COMPANION to learned_analysis.py. Whereas learned_analysis.py
runs the analysis on learned-detector predictions ONLY (matching the
paper's pre-registered separation between primary and supplementary
analyses), this script concatenates classical + learned predictions and
runs the analysis on the unified set.

USE CASE: descriptive / visualisation only. The combined analysis is
useful for side-by-side figures (e.g. "all 8 detectors compared across
carrier sources") but should NOT be used for the paper's primary
verdicts -- it would violate the pre-registered Bonferroni-Holm correction.

What it does
------------
1. Reads predictions.csv (classical), predictions_srnet.csv (learned),
   predictions_dctr.csv (learned) from the test run.
2. Concatenates them into combined_shadow/predictions/predictions.csv.
3. Runs the analysis pipeline (compute_metrics, generate_figures,
   t_tests, wilcoxon, encryption_invariance) on the combined set.
4. Writes outputs under runs/<test-run>/combined_shadow/.

The classical metrics/, figures/, and rq_verdicts.json are NEVER
touched -- the v1 paper's numbers remain frozen.

Usage
-----
    venv312/bin/python scripts/inference/combined_analysis.py \\
        --run runs/prototype_full_20260513_005357_p8765
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _concatenate(srcs: list[Path], out: Path) -> dict[str, int]:
    out.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    with out.open("w", newline="") as out_fh:
        writer = None
        for src in srcs:
            if not src.exists():
                raise FileNotFoundError(f"missing predictions file: {src}")
            with src.open() as in_fh:
                reader = csv.reader(in_fh)
                header = next(reader)
                if writer is None:
                    writer = csv.writer(out_fh)
                    writer.writerow(header)
                src_count = 0
                for row in reader:
                    writer.writerow(row)
                    src_count += 1
                counts[src.name] = src_count
    return counts


def _setup_shadow_run(test_run: Path, shadow: Path) -> None:
    shadow.mkdir(parents=True, exist_ok=True)
    for name in ("config.json",):
        if (test_run / name).exists():
            shutil.copy2(test_run / name, shadow / name)
    qmr = test_run / "manifests" / "quality_metrics_raw.csv"
    if qmr.exists():
        (shadow / "manifests").mkdir(parents=True, exist_ok=True)
        shutil.copy2(qmr, shadow / "manifests" / "quality_metrics_raw.csv")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True,
                   help="Test run with predictions/predictions.csv + "
                        "predictions_srnet.csv + predictions_dctr.csv")
    p.add_argument("--shadow-name", default="combined_shadow")
    args = p.parse_args()

    run = args.run.resolve()
    pred_dir = run / "predictions"
    shadow = run / args.shadow_name

    classical = pred_dir / "predictions.csv"
    srnet = pred_dir / "predictions_srnet.csv"
    dctr = pred_dir / "predictions_dctr.csv"

    print(f"=== combined_analysis: shadow dir = {shadow} ===")
    _setup_shadow_run(run, shadow)

    out_csv = shadow / "predictions" / "predictions.csv"
    counts = _concatenate([classical, srnet, dctr], out_csv)
    print(f"  wrote combined predictions: {out_csv}")
    for k, v in counts.items():
        print(f"     {k}: {v} rows")
    total = sum(counts.values())
    print(f"     TOTAL: {total} rows (~{total//1000}k)")

    # Deferred imports
    from src.pipeline.config import PipelineConfig
    from src.pipeline.runner import PipelineRunner
    from src.analysis.t_tests import run_t_tests
    from src.analysis.wilcoxon_tests import run_wilcoxon_tests
    from src.analysis.encryption_invariance import run_encryption_invariance

    # PipelineRunner instance is only used for compute_metrics_from_predictions
    # and generate_metrics_figures; both accept explicit metrics_dir /
    # figures_dir parameters, so the frozen runner.paths is fine as-is.
    cfg = PipelineConfig(project_root=_PROJECT_ROOT, n_groups=0)
    runner = PipelineRunner(cfg)

    print()
    print("=== computing combined metrics ===")
    metrics_out = runner.compute_metrics_from_predictions(
        out_csv, metrics_dir=shadow / "metrics")
    print(f"  metrics tables: {list(metrics_out.keys())}")

    print()
    print("=== generating combined figures + per-RQ contrast CSVs ===")
    fig_out = runner.generate_metrics_figures(
        metrics_dir=shadow / "metrics",
        figures_dir=shadow / "figures",
    )
    print(f"  figure files: {len(fig_out)} (PNGs + sub-panels)")

    print()
    print("=== paired t-tests on combined detectors ===")
    print(f"  wrote {run_t_tests(shadow)}")
    print()
    print("=== Wilcoxon signed-rank tests on combined detectors ===")
    print(f"  wrote {run_wilcoxon_tests(shadow)}")

    print()
    print("=== encryption invariance (RQ5) ===")
    try:
        print(f"  wrote {run_encryption_invariance(shadow)}")
    except Exception as exc:
        print(f"  skipped: {exc}")

    print()
    print("=" * 60)
    print("Combined analysis complete. Outputs:")
    print("=" * 60)
    print(f"  metrics CSVs : {shadow / 'metrics'}/")
    print(f"  figures PNGs : {shadow / 'figures'}/")
    print()
    print("NOTE: this is descriptive / visualisation only. The paper's")
    print("primary verdicts come from the CLASSICAL-ONLY analysis under")
    print(f"  {run / 'metrics' / 'rq_verdicts.json'}")
    print("and the SUPPLEMENTARY learned-only verdicts come from")
    print(f"  {run / 'learned_shadow' / 'metrics' / 'rq_verdicts.json'}")
    print("Do NOT report combined-analysis verdicts as if they were the")
    print("primary findings -- the pre-registered Bonferroni-Holm correction")
    print("would be silently rewritten.")


if __name__ == "__main__":
    main()
