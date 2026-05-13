#!/usr/bin/env python3
"""Resume a run from the detection stage onwards.

When a long run dies mid-detection (or the user kills it because the
detector stage is slow), all the expensive artefacts -- real covers, ML
covers, stego images, quality metrics, manifests -- are already on disk.
There is no reason to redo any of that. This script:

  1. Loads the run's frozen config snapshot.
  2. Re-instantiates a PipelineRunner against that config.
  3. Runs detection -> metrics -> figures -> analysis (verdicts, power,
     wilcoxon, t-tests, encryption-invariance) directly, picking up any
     partial predictions.csv that resume-aware run_detector_stage left.
  4. Removes the .running marker that the GUI wrapper writes so the
     run-detail page transitions to "complete".

Usage
-----
    python scripts/resume_pipeline_body.py runs/<run-id>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make ``src.*`` importable when running the script from anywhere.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _load_config_snapshot(run_dir: Path):
    from src.pipeline.config import PipelineConfig

    snap_path = run_dir / "config.json"
    if not snap_path.exists():
        raise SystemExit(f"config.json not found under {run_dir}; cannot resume.")
    snap = json.loads(snap_path.read_text())

    project_root = Path.cwd().resolve()
    kwargs = dict(
        project_root=project_root,
        image_size=tuple(snap.get("image_size", [512, 512])),
        n_groups=snap["n_groups"],
        split_seed=snap.get("split_seed", 42),
        payload_seed=snap.get("payload_seed", 42),
        payload_mode=snap.get("payload_mode", "random"),
        hardcoded_payload_text=None,
        embed_seed=snap.get("embed_seed", 42),
        aes_key_id=snap.get("aes_key_id", "aes256cbc-v1"),
        jpeg_quality=snap.get("jpeg_quality", 95),
        primary_lsb_bit_depth=snap.get("primary_lsb_bit_depth", 1),
        payload_fill_rates=snap.get("payload_fill_rates", {"low": 0.25, "medium": 0.5, "high": 0.75}),
        active_methods=tuple(snap.get("active_methods", ["lsb", "dct"])),
        active_payload_levels=tuple(snap.get("active_payload_levels", ["low", "medium", "high"])),
    )
    if snap.get("active_detectors"):
        kwargs["active_detectors"] = tuple(snap["active_detectors"])
    if snap.get("active_encryption"):
        kwargs["active_encryption"] = tuple(snap["active_encryption"])
    return PipelineConfig(**kwargs)


def resume(run_dir: Path) -> None:
    from src.pipeline.runner import PipelineRunner

    config = _load_config_snapshot(run_dir)
    runner = PipelineRunner(config)

    stego_manifest = run_dir / "manifests" / "stego_manifest.csv"
    quality_metrics_raw = run_dir / "manifests" / "quality_metrics_raw.csv"
    metrics_dir = run_dir / "metrics"
    figures_dir = run_dir / "figures"
    predictions_csv = run_dir / "predictions" / "predictions.csv"

    metrics_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    predictions_csv.parent.mkdir(parents=True, exist_ok=True)

    if not stego_manifest.exists():
        raise SystemExit(f"stego_manifest.csv missing at {stego_manifest}.")

    print(f"\n=== Resuming pipeline body for {run_dir.name} ===\n")
    print("[1/4] Detection (parallel + resume-aware) ...")
    runner.run_detector_stage(
        stego_manifest_path=stego_manifest,
        output_path=predictions_csv,
        execute=True,
        skip_unimplemented=True,
    )
    print(f"  -> {predictions_csv}")

    print("\n[2/4] Metrics aggregation ...")
    metrics_outputs = runner.compute_metrics_from_predictions(
        predictions_path=predictions_csv,
        metrics_dir=metrics_dir,
        quality_metrics_input=quality_metrics_raw if quality_metrics_raw.exists() else None,
    )
    for key, val in metrics_outputs.items():
        print(f"  {key:24s} {val}")

    print("\n[3/4] Figures + contrast tables ...")
    figures_outputs = runner.generate_metrics_figures(
        metrics_dir=metrics_dir,
        figures_dir=figures_dir,
    )
    n_pngs = sum(1 for v in figures_outputs.values() if isinstance(v, Path) and v.suffix == ".png")
    n_csvs = sum(1 for v in figures_outputs.values() if isinstance(v, Path) and v.suffix == ".csv")
    print(f"  -> {n_pngs} PNGs, {n_csvs} CSVs in {figures_dir} / {metrics_dir}")

    print("\n[4/4] Analysis modules (Wilcoxon, t-tests, encryption-invariance, verdicts, power) ...")
    from src.analysis.wilcoxon_tests import run_wilcoxon_tests
    from src.analysis.t_tests import run_t_tests
    from src.analysis.rq_verdicts import run_rq_verdicts
    from src.analysis.power_analysis import run_power_analysis

    for label, fn in [
        ("wilcoxon", run_wilcoxon_tests),
        ("t_tests", run_t_tests),
        ("rq_verdicts", run_rq_verdicts),
        ("power_analysis", run_power_analysis),
    ]:
        try:
            fn(run_dir)
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] analysis '{label}' failed: {exc}")

    if "encrypted" in config.active_encryption and "plain" in config.active_encryption:
        try:
            from src.analysis.encryption_invariance import run_encryption_invariance
            run_encryption_invariance(run_dir)
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] analysis 'encryption_invariance' failed: {exc}")

    # Refresh RQ summary cards once verdicts.json is on disk.
    try:
        from src.evaluation.plots import render_rq_summary_cards
        verdicts_path = metrics_dir / "rq_verdicts.json"
        if verdicts_path.exists():
            payload = json.loads(verdicts_path.read_text())
            render_rq_summary_cards(figures_dir, payload)
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] summary-card refresh failed: {exc}")

    # Clear the GUI's .running marker.
    running_marker = run_dir / ".running"
    if running_marker.exists():
        running_marker.unlink()

    print(f"\n=== Done. Open the run in the GUI to inspect results. ===\n")


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/resume_pipeline_body.py runs/<run-id>")
        sys.exit(1)
    run_dir = Path(sys.argv[1]).resolve()
    if not run_dir.exists():
        sys.exit(f"Run directory not found: {run_dir}")
    resume(run_dir)


if __name__ == "__main__":
    main()
