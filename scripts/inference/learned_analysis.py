"""Run the analysis pipeline on learned-detector predictions only.

This is the Phase D orchestrator from POST_TRAINING_CHECKLIST.md.

What it does
------------
1. Reads ``predictions_srnet.csv`` and ``predictions_dctr.csv`` from the
   test run's ``predictions/`` directory (produced by
   ``apply_srnet_to_run.py`` and ``apply_dctr_to_run.py``).
2. Concatenates them into a single predictions file in a *shadow* run
   directory (``runs/<test-run>/learned_shadow/``) so the existing
   analysis pipeline can process them without touching the classical
   results.
3. Runs the same analysis modules the main pipeline runs:
       - ``compute_metrics_from_predictions``  -> detector/condition/source AUCs
       - ``generate_metrics_figures``          -> ROC panels, contrast tables
       - ``run_t_tests``                       -> paired t-tests on scores
       - ``run_wilcoxon_tests``                -> non-parametric backup
       - ``run_encryption_invariance``         -> RQ5 invariance table
       - ``run_rq_verdicts``                   -> final RQ1-RQ5 verdicts
       - ``run_power_analysis``                -> post-hoc power
4. Reports a one-screen summary of the learned-detector verdicts and
   prints the comparison vs the classical-detector verdicts from the
   primary analysis.

The classical metrics/, figures/, and rq_verdicts.json are NEVER
touched -- they remain byte-identical to the v1 paper's numbers.

Usage
-----
    venv/bin/python scripts/inference/learned_analysis.py \\
        --run runs/prototype_full_20260513_005357_p8765

Outputs land under::

    runs/prototype_full_20260513_005357_p8765/learned_shadow/
        predictions/predictions.csv     # concatenated learned predictions
        config.json                     # copy from parent test run
        metrics/                        # learned-only metrics
            detector_metrics.csv
            condition_metrics.csv
            source_metrics.csv
            exp1_rq1_real_vs_pooled_ml_contrasts.csv
            exp2_rq2_mla_vs_mlb_contrasts.csv
            exp3_rq3_payload_interaction_contrasts.csv
            exp4_rq4_spatial_vs_frequency_contrasts.csv
            exp5_rq5_encryption_contrasts.csv
            rq_verdicts.json
            rq_verdicts.md
            t_tests.csv
            wilcoxon_tests.csv
            encryption_invariance.csv
            power_summary.csv
        figures/                        # learned-only figures
            <same panel set as the classical analysis>
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

# Make project root importable when run as a script.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Shadow run setup
# ---------------------------------------------------------------------------

def _concatenate_predictions(
    srnet_csv: Path,
    dctr_csv: Path,
    out_csv: Path,
) -> dict[str, int]:
    """Concatenate two prediction CSVs (skip duplicate header), return row counts."""
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    counts = {"srnet": 0, "dctr": 0}
    with out_csv.open("w", newline="") as out_fh:
        header_written = False
        for tag, src in (("srnet", srnet_csv), ("dctr", dctr_csv)):
            if not src.exists():
                raise FileNotFoundError(f"missing {tag} predictions at {src}")
            with src.open() as in_fh:
                reader = csv.reader(in_fh)
                writer = csv.writer(out_fh)
                header = next(reader)
                if not header_written:
                    writer.writerow(header)
                    header_written = True
                for row in reader:
                    writer.writerow(row)
                    counts[tag] += 1
    return counts


def _setup_shadow_run(test_run: Path, shadow_dir: Path) -> None:
    """Populate the shadow run dir with everything the analysis modules need."""
    shadow_dir.mkdir(parents=True, exist_ok=True)

    src_config = test_run / "config.json"
    if src_config.exists():
        shutil.copy2(src_config, shadow_dir / "config.json")

    # Copy quality_metrics_raw.csv if present (used for the quality_metrics
    # table by compute_metrics_from_predictions). Optional -- the classical
    # run already has it; for the learned analysis we just want the
    # detector/condition/source AUCs, not new quality numbers.
    src_quality = test_run / "manifests" / "quality_metrics_raw.csv"
    if src_quality.exists():
        (shadow_dir / "manifests").mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_quality, shadow_dir / "manifests" / "quality_metrics_raw.csv")


# ---------------------------------------------------------------------------
# Compare learned verdicts vs classical verdicts
# ---------------------------------------------------------------------------

_VERDICT_STRENGTH = {
    "not_supported": 0,
    "inconclusive_underpowered": 0,
    "trivial": 0,
    "mixed": 1,
    "supported": 2,
}


def _direction_label(classical_effect: float | None, learned_effect: float | None) -> str:
    """Return a short label for the direction of effect comparison."""
    if classical_effect is None or learned_effect is None:
        return "?"
    cl_sign = 1 if classical_effect > 0 else (-1 if classical_effect < 0 else 0)
    ld_sign = 1 if learned_effect > 0 else (-1 if learned_effect < 0 else 0)
    if cl_sign == ld_sign:
        return "same dir"
    if cl_sign == 0 or ld_sign == 0:
        return "near-zero"
    return "OPPOSITE"


def _interpret(classical_verdict: str, learned_verdict: str, direction: str) -> str:
    """Three-way interpretation: corroborates / refines / contradicts."""
    if classical_verdict == learned_verdict:
        return "✅ CORROBORATES (same verdict, same direction)" if direction == "same dir" else "✅ CORROBORATES"
    if direction == "OPPOSITE":
        return "🚨 CONTRADICTS (opposite direction)"
    # Different verdict, same direction
    cl_s = _VERDICT_STRENGTH.get(classical_verdict, 0)
    ld_s = _VERDICT_STRENGTH.get(learned_verdict, 0)
    if ld_s > cl_s:
        return "📈 REFINES (learned shows stronger effect, same direction)"
    if ld_s < cl_s:
        return "📉 REFINES (learned shows weaker effect, same direction)"
    return "≈ MIXED CORROBORATION"


def _compare_verdicts(classical_verdicts: Path, learned_verdicts: Path) -> str:
    """Side-by-side verdict comparison with three-way interpretation.

    Output includes pooled effect sizes from each analysis so the
    "refines / corroborates / contradicts" judgment can be made on
    direction + magnitude, not just verdict-string equality.
    """
    if not classical_verdicts.exists():
        return f"(no classical verdicts found at {classical_verdicts})"
    if not learned_verdicts.exists():
        return f"(no learned verdicts found at {learned_verdicts})"
    classical = json.loads(classical_verdicts.read_text()).get("verdicts", {})
    learned = json.loads(learned_verdicts.read_text()).get("verdicts", {})

    lines: list[str] = []
    lines.append(f"{'RQ':<6}{'classical (Δ)':<24}{'learned (Δ)':<24}{'interpretation':<35}")
    lines.append("-" * 89)
    for rq in ("RQ1", "RQ2", "RQ3", "RQ4", "RQ5"):
        cl = classical.get(rq, {})
        ld = learned.get(rq, {})
        cl_v = cl.get("verdict", "?")
        ld_v = ld.get("verdict", "?")
        # Exploratory RQ3 uses mean_gap_by_payload (no scalar pooled effect);
        # confirmatory RQ1/RQ2/RQ4/RQ5 expose pooled_diff.  Fall back to the
        # high-payload gap for RQ3 so the direction label still works.
        cl_eff = cl.get("pooled_diff")
        ld_eff = ld.get("pooled_diff")
        if cl_eff is None and "mean_gap_by_payload" in cl:
            cl_eff = cl["mean_gap_by_payload"].get("high")
        if ld_eff is None and "mean_gap_by_payload" in ld:
            ld_eff = ld["mean_gap_by_payload"].get("high")
        direction = _direction_label(cl_eff, ld_eff)
        interp = _interpret(cl_v, ld_v, direction)
        cl_str = f"{cl_v} ({cl_eff:+.4f})" if cl_eff is not None else cl_v
        ld_str = f"{ld_v} ({ld_eff:+.4f})" if ld_eff is not None else ld_v
        lines.append(f"{rq:<6}{cl_str:<24}{ld_str:<24}{interp:<35}")
    lines.append("")
    lines.append("Legend:")
    lines.append("  CORROBORATES = same verdict, same direction (best academic outcome)")
    lines.append("  REFINES      = same direction, different magnitude (publishable refinement)")
    lines.append("  CONTRADICTS  = opposite direction (rare; needs investigation)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True,
                   help="Test run directory containing predictions/ and config.json.")
    p.add_argument("--shadow-name", default="learned_shadow",
                   help="Subdirectory name for the shadow analysis run "
                        "(default: 'learned_shadow').")
    p.add_argument("--srnet-csv",
                   help="Path to predictions_srnet.csv (default: "
                        "<run>/predictions/predictions_srnet.csv).")
    p.add_argument("--dctr-csv",
                   help="Path to predictions_dctr.csv (default: "
                        "<run>/predictions/predictions_dctr.csv).")
    args = p.parse_args()

    run = args.run.resolve()
    srnet_csv = Path(args.srnet_csv) if args.srnet_csv else (run / "predictions" / "predictions_srnet.csv")
    dctr_csv = Path(args.dctr_csv) if args.dctr_csv else (run / "predictions" / "predictions_dctr.csv")
    shadow = run / args.shadow_name

    print(f"=== learned_analysis: building shadow run at {shadow} ===")
    _setup_shadow_run(run, shadow)
    print(f"  shadow dir: {shadow}")
    print(f"  reading srnet predictions: {srnet_csv}")
    print(f"  reading dctr  predictions: {dctr_csv}")

    out_csv = shadow / "predictions" / "predictions.csv"
    counts = _concatenate_predictions(srnet_csv, dctr_csv, out_csv)
    print(f"  wrote concatenated predictions: {out_csv}")
    print(f"     srnet rows: {counts['srnet']}")
    print(f"     dctr  rows: {counts['dctr']}")
    print(f"     total:      {sum(counts.values())}")

    # ---------------- Imports (deferred) ----------------
    from src.pipeline.config import PipelineConfig
    from src.pipeline.runner import PipelineRunner
    from src.analysis.t_tests import run_t_tests
    from src.analysis.wilcoxon_tests import run_wilcoxon_tests
    from src.analysis.encryption_invariance import run_encryption_invariance
    from src.analysis.rq_verdicts import run_rq_verdicts
    from src.analysis.power_analysis import run_power_analysis

    # ---------------- Compute metrics ----------------
    print()
    print("=== computing AUC / condition / source metrics ===")
    # We need a PipelineRunner instance to call compute_metrics_from_predictions
    # and generate_metrics_figures.  Both methods accept explicit metrics_dir
    # / figures_dir arguments and fall back to self.paths.* only when those
    # are None, so we can leave runner.paths alone (it is a frozen dataclass
    # and would refuse mutation anyway) and just pass the shadow dirs through.
    cfg = PipelineConfig(project_root=_PROJECT_ROOT, n_groups=0)
    runner = PipelineRunner(cfg)

    metrics_out = runner.compute_metrics_from_predictions(
        out_csv,
        metrics_dir=shadow / "metrics",
    )
    print(f"  metrics: {list(metrics_out.keys())}")

    # ---------------- Generate figures + contrast CSVs ----------------
    print()
    print("=== generating figures + contrast CSVs ===")
    fig_out = runner.generate_metrics_figures(
        metrics_dir=shadow / "metrics",
        figures_dir=shadow / "figures",
    )
    print(f"  figures: {len(fig_out)} files written")

    # ---------------- Score-level tests ----------------
    print()
    print("=== paired t-tests ===")
    t_tests_path = run_t_tests(shadow)
    print(f"  wrote {t_tests_path}")
    print()
    print("=== Wilcoxon signed-rank tests ===")
    wil_path = run_wilcoxon_tests(shadow)
    print(f"  wrote {wil_path}")

    # ---------------- RQ5 encryption-invariance table ----------------
    print()
    print("=== encryption invariance (RQ5) ===")
    try:
        inv_path = run_encryption_invariance(shadow)
        print(f"  wrote {inv_path}")
    except Exception as exc:
        print(f"  skipped: {exc}")

    # ---------------- RQ verdicts + power ----------------
    print()
    print("=== RQ verdicts ===")
    rq_json, rq_md = run_rq_verdicts(shadow)
    print(f"  wrote {rq_json}")
    print(f"  wrote {rq_md}")
    print()
    print("=== power analysis ===")
    pow_detail, pow_summary = run_power_analysis(shadow)
    print(f"  wrote {pow_detail}")
    print(f"  wrote {pow_summary}")

    # ---------------- Side-by-side comparison ----------------
    print()
    print("=" * 76)
    print("=== Verdict comparison: classical (primary) vs learned (supplementary) ===")
    print("=" * 76)
    print(_compare_verdicts(
        classical_verdicts=run / "metrics" / "rq_verdicts.json",
        learned_verdicts=shadow / "metrics" / "rq_verdicts.json",
    ))
    print()

    # ---------------- Top-line learned AUCs (for the paper's headline table) ----------------
    print("=" * 76)
    print("=== Per-detector headline AUC (learned analysis) ===")
    print("=" * 76)
    det_csv = shadow / "metrics" / "detector_metrics.csv"
    with det_csv.open() as fh:
        rdr = csv.DictReader(fh)
        print(f"{'detector':<10}{'n_samples':<12}{'AUC':<10}{'EER':<10}")
        for r in rdr:
            print(f"{r['detector']:<10}{r['n_samples']:<12}{float(r['roc_auc']):<10.4f}{float(r['eer']):<10.4f}")
    print()
    print(f"Full Markdown verdicts: {rq_md}")
    print(f"  cat {rq_md}")


if __name__ == "__main__":
    main()
