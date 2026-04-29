from __future__ import annotations

"""CLI entrypoint for the proposal-aligned pipeline stages."""

import argparse
from pathlib import Path

from src.pipeline.config import PipelineConfig
from src.pipeline.profile import PROFILES
from src.pipeline.runner import PipelineRunner


def _resolve_path(path: Path, project_root: Path) -> Path:
    """Resolve a possibly-relative CLI path against the project root."""
    return path if path.is_absolute() else (project_root / path)


def _print_figure_outputs(out: dict) -> None:
    """Summarise figures produced by ``generate_metrics_figures``."""
    pngs = [v for v in out.values() if isinstance(v, Path) and v.suffix == ".png"]
    if not pngs:
        print("Figures: none generated")
        return
    parents = {p.parent for p in pngs}
    figures_root = min(parents, key=lambda p: len(p.parts))
    top_level = sorted(p for p in pngs if p.parent == figures_root)
    nested_counts: dict[Path, int] = {}
    for path in pngs:
        if path.parent != figures_root:
            nested_counts[path.parent] = nested_counts.get(path.parent, 0) + 1

    print(f"Figures dir: {figures_root}  ({len(pngs)} PNGs)")
    for path in top_level:
        print(f"  - {path.name}")
    for sub_dir, count in sorted(nested_counts.items()):
        print(f"  - {sub_dir.name}/  ({count} PNGs)")


def _parser() -> argparse.ArgumentParser:
    """Create the command parser for all supported pipeline stages."""
    parser = argparse.ArgumentParser(
        description="Pipeline scaffold utilities for project-proposal."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Project root (default: current working directory).",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-layout", help="Create expected data/results directory layout.")

    p_std = sub.add_parser(
        "standardize-covers",
        help="Read raw cover index CSV and write grayscale PNG/JPEG cover variants plus covers_master.csv.",
    )
    p_std.add_argument(
        "--input-index",
        type=Path,
        required=True,
        help="CSV with raw_image_path and cover metadata.",
    )

    p_payload = sub.add_parser("build-payload-manifest", help="Write payload manifest.")
    p_payload.add_argument(
        "--covers-manifest",
        type=Path,
        required=True,
        help="Path to covers_master.csv",
    )
    p_payload.add_argument(
        "--write-files",
        action="store_true",
        help="Write payload binary files. Encrypted rows call the AES placeholder.",
    )

    p_stego = sub.add_parser("build-stego-manifest", help="Write stego manifest.")
    p_stego.add_argument("--covers-manifest", type=Path, required=True)
    p_stego.add_argument("--payload-manifest", type=Path, required=True)

    p_embed = sub.add_parser(
        "run-embedding-stage",
        help="Run embedding stage from stego manifest (placeholder embedding functions).",
    )
    p_embed.add_argument("--stego-manifest", type=Path, required=True)
    p_embed.add_argument(
        "--execute",
        action="store_true",
        help="Actually invoke embedding placeholders; default is dry-run count only.",
    )

    p_det = sub.add_parser(
        "run-detectors",
        help="Run detector stage on the full evaluation table and write predictions.",
    )
    p_det.add_argument("--stego-manifest", type=Path, required=True)
    p_det.add_argument(
        "--execute",
        action="store_true",
        help="Actually invoke detector functions; default writes dry-run rows with empty scores.",
    )
    p_det.add_argument(
        "--skip-unimplemented",
        action="store_true",
        help="Skip detectors that raise NotImplementedError instead of failing.",
    )

    p_metrics = sub.add_parser(
        "compute-metrics",
        help="Aggregate detector predictions into detector/condition/source metric tables.",
    )
    p_metrics.add_argument("--predictions", type=Path, required=True)
    p_metrics.add_argument(
        "--quality-metrics-input",
        type=Path,
        required=False,
        help="Optional precomputed quality metrics CSV to copy into results/metrics.",
    )

    p_plot = sub.add_parser(
        "plot-metrics",
        help="Generate metrics figures (AUC by source and by method).",
    )
    p_plot.add_argument(
        "--metrics-dir",
        type=Path,
        required=False,
        help="Optional metrics directory (defaults to results/metrics).",
    )
    p_plot.add_argument(
        "--figures-dir",
        type=Path,
        required=False,
        help="Optional figures output directory (defaults to results/figures).",
    )

    p_all = sub.add_parser(
        "run-all",
        help="Run full pipeline orchestration in one command.",
    )
    p_all.add_argument("--covers-manifest", type=Path, required=True)
    p_all.add_argument(
        "--profile",
        choices=list(PROFILES.keys()),
        default=None,
        help=(
            "Named experiment profile ('prototype' or 'full_design'). "
            "When set, config is scoped to that profile and results are "
            "written to runs/{profile}_{NNN}/."
        ),
    )
    p_all.add_argument(
        "--run-id",
        type=str,
        default=None,
        help=(
            "Override the auto-generated run identifier (e.g. 'prototype_001'). "
            "Output is written to runs/{run-id}/. Ignored when --profile is not set."
        ),
    )
    p_all.add_argument(
        "--execute-embeddings",
        action="store_true",
        help="Execute embedding functions (disabled by default).",
    )
    p_all.add_argument(
        "--execute-detectors",
        action="store_true",
        help="Execute detector functions (disabled by default).",
    )
    p_all.add_argument(
        "--skip-unimplemented",
        action="store_true",
        help="Skip deferred functions that raise NotImplementedError.",
    )
    p_all.add_argument(
        "--quality-metrics-input",
        type=Path,
        required=False,
        help="Optional precomputed quality metrics CSV to copy into results/metrics.",
    )
    p_all.add_argument(
        "--generate-figures",
        action="store_true",
        help="Generate summary AUC figures after metric aggregation.",
    )
    p_all.add_argument(
        "--cover-seed",
        type=int,
        default=None,
        help="Cover selection seed (recorded in config.json for reproducibility).",
    )
    return parser


def main() -> None:
    """Dispatch one CLI command to the corresponding ``PipelineRunner`` stage."""
    args = _parser().parse_args()
    project_root = args.project_root.resolve()

    # Build a profile-scoped config when --profile is given, else use full defaults.
    profile_name: str | None = getattr(args, "profile", None)
    if profile_name:
        config = PipelineConfig.from_profile(project_root, profile_name)
    else:
        config = PipelineConfig.from_project_root(project_root)

    runner = PipelineRunner(config)

    if args.command == "init-layout":
        runner.init_layout()
        print("Layout initialized.")
    elif args.command == "standardize-covers":
        out = runner.standardize_covers_from_index(
            input_index_csv=_resolve_path(args.input_index, project_root),
        )
        print(f"Covers manifest: {out}")
    elif args.command == "build-payload-manifest":
        out = runner.build_payload_manifest(
            covers_manifest_path=_resolve_path(args.covers_manifest, project_root),
            write_payload_files=args.write_files,
        )
        print(f"Payload manifest: {out}")
    elif args.command == "build-stego-manifest":
        out = runner.build_stego_manifest(
            covers_manifest_path=_resolve_path(args.covers_manifest, project_root),
            payload_manifest_path=_resolve_path(args.payload_manifest, project_root),
        )
        print(f"Stego manifest: {out}")
    elif args.command == "run-embedding-stage":
        n = runner.run_embedding_stage(
            stego_manifest_path=_resolve_path(args.stego_manifest, project_root),
            execute=args.execute,
        )
        print(f"Embedding rows processed: {n}")
    elif args.command == "run-detectors":
        out = runner.run_detector_stage(
            stego_manifest_path=_resolve_path(args.stego_manifest, project_root),
            execute=args.execute,
            skip_unimplemented=args.skip_unimplemented,
        )
        print(f"Predictions CSV: {out}")
    elif args.command == "compute-metrics":
        out = runner.compute_metrics_from_predictions(
            predictions_path=_resolve_path(args.predictions, project_root),
            quality_metrics_input=(
                _resolve_path(args.quality_metrics_input, project_root)
                if args.quality_metrics_input
                else None
            ),
        )
        print(f"Detector metrics CSV: {out['detector_metrics']}")
        print(f"Condition metrics CSV: {out['condition_metrics']}")
        print(f"Source metrics CSV: {out['source_metrics']}")
        print(f"Quality metrics CSV: {out['quality_metrics']}")
    elif args.command == "plot-metrics":
        out = runner.generate_metrics_figures(
            metrics_dir=(
                _resolve_path(args.metrics_dir, project_root) if args.metrics_dir else None
            ),
            figures_dir=(
                _resolve_path(args.figures_dir, project_root) if args.figures_dir else None
            ),
        )
        _print_figure_outputs(out)
    elif args.command == "run-all":
        # Resolve run directory when a profile is active.
        run_dir: Path | None = None
        if profile_name:
            if args.run_id:
                run_dir = project_root / "runs" / args.run_id
            else:
                run_dir = runner._next_run_dir(profile_name)
            print(f"Profile  : {profile_name}")
            print(f"Run dir  : {run_dir}")

        out = runner.run_full_pipeline(
            covers_manifest_path=_resolve_path(args.covers_manifest, project_root),
            execute_embeddings=args.execute_embeddings,
            execute_detectors=args.execute_detectors,
            skip_unimplemented=args.skip_unimplemented,
            quality_metrics_input=(
                _resolve_path(args.quality_metrics_input, project_root)
                if args.quality_metrics_input
                else None
            ),
            generate_figures=args.generate_figures,
            run_dir=run_dir,
            profile_name=profile_name,
            cover_seed=getattr(args, "cover_seed", None),
        )
        print(f"Payload manifest: {out['payload_manifest']}")
        print(f"Stego manifest: {out['stego_manifest']}")
        print(f"Embedding rows processed: {out['embedding_rows_processed']}")
        print(f"Predictions CSV: {out['predictions']}")
        print(f"Detector metrics CSV: {out['detector_metrics']}")
        print(f"Condition metrics CSV: {out['condition_metrics']}")
        print(f"Source metrics CSV: {out['source_metrics']}")
        print(f"Quality metrics CSV: {out['quality_metrics']}")
        if args.generate_figures:
            _print_figure_outputs(out)
    else:
        raise ValueError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    main()
