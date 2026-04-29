#!/usr/bin/env python3
"""
Run the steganography pipeline for a named experiment profile.

Usage
-----
    python run.py prototype              # new prototype run  (auto-ID)
    python run.py full_design            # new full-design run (auto-ID)
    python run.py prototype --run-id my_run_001   # explicit run ID
    python run.py prototype --ml-engine stub      # stub generator (no GPU/API needed)

What this does
--------------
Automatically ensures all input data is present before running, then executes
the full steganography pipeline:

  [1/5] Real covers    — download COCO + Flickr30k via HuggingFace Datasets API
                         (skipped if manifest already has enough rows)
  [2/5] ML covers      — generate SDXL (ml_a) + FLUX (ml_b) from captions
                         (skipped if manifests already have enough rows)
  [3/5] Covers manifest — merge all three sources into one manifest
                         (skipped if already present)
  [4/5] Pipeline       — payload manifest → stego images → detectors
                         → metric aggregation → AUC figures
  [5/5] Run directory  — all outputs written to runs/{profile}_{NNN}/
                         (never overwrites a previous run)

Available profiles
------------------
  prototype    20 groups × 3 sources =   60 images · LSB only  · medium fill · 6 conditions
  full_design 500 groups × 3 sources = 1500 images · LSB + DCT · all fills   · 36 conditions

Cover image breakdown per profile
----------------------------------
  prototype   →  12 COCO + 8 Flickr30k  (real)  +  20 SDXL + 20 FLUX  (ml)
  full_design → 300 COCO + 200 Flickr30k (real)  + 500 SDXL + 500 FLUX (ml)

ML engine options (--ml-engine)
--------------------------------
  diffusers      Local diffusers inference; requires torch + diffusers; GPU recommended
  inference_api  HuggingFace Inference API; requires HF_TOKEN environment variable
  stub           Deterministic synthetic images; no dependencies (testing only)
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

# Force UTF-8 console output on Windows (avoids UnicodeEncodeError with
# non-ASCII characters like ×, …, ✓ on restrictive codepages such as cp1253).
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ── Results summary ───────────────────────────────────────────────────────────

def _fmt_auc(v: str) -> str:
    try:
        return f"{float(v):.3f}"
    except (ValueError, TypeError):
        return "  —  "


def _fmt_pct(v: str) -> str:
    try:
        return f"{float(v)*100:5.1f}%"
    except (ValueError, TypeError):
        return "   — "


def _print_results_summary(run_dir: Path) -> None:
    """Print a concise terminal summary of detector results from a finished run."""
    metrics_dir = run_dir / "metrics"

    def _read(name: str) -> list[dict[str, str]]:
        p = metrics_dir / name
        if not p.exists():
            return []
        with p.open(newline="") as f:
            return list(csv.DictReader(f))

    det_rows  = _read("detector_metrics.csv")
    src_rows  = _read("source_metrics.csv")
    cond_rows = _read("condition_metrics.csv")

    W = 66
    print(f"\n{'═'*W}")
    print(f"  RESULTS — {run_dir.name}")
    print(f"{'═'*W}")

    # ── Overall detector performance ──────────────────────────────────────────
    if det_rows:
        print(f"\n  {'DETECTOR':<22} {'AUC':>6}  {'EER':>6}  {'Accuracy':>9}  {'Samples':>7}")
        print(f"  {'─'*22} {'─'*6}  {'─'*6}  {'─'*9}  {'─'*7}")
        for r in sorted(det_rows, key=lambda x: float(x.get("roc_auc") or 0), reverse=True):
            print(
                f"  {r['detector']:<22} "
                f"{_fmt_auc(r['roc_auc']):>6}  "
                f"{_fmt_pct(r['eer']):>6}  "
                f"{_fmt_pct(r['accuracy_at_youden_j']):>9}  "
                f"{r['n_samples']:>7}"
            )

    # ── By source ─────────────────────────────────────────────────────────────
    if src_rows:
        sources = sorted({r["source"] for r in src_rows})
        detectors = sorted({r["detector"] for r in src_rows})
        # index for fast lookup
        src_idx = {(r["detector"], r["source"]): r for r in src_rows}

        print(f"\n  AUC BY SOURCE")
        header = f"  {'DETECTOR':<22}" + "".join(f"  {s:>8}" for s in sources)
        print(header)
        print(f"  {'─'*22}" + "".join(f"  {'─'*8}" for _ in sources))
        for det in sorted(detectors, key=lambda d: -float(
            src_idx.get((d, sources[0]), {}).get("roc_auc") or 0
        )):
            row_str = f"  {det:<22}"
            for s in sources:
                auc = src_idx.get((det, s), {}).get("roc_auc", "")
                row_str += f"  {_fmt_auc(auc):>8}"
            print(row_str)

    # ── By encryption ─────────────────────────────────────────────────────────
    if cond_rows:
        encryptions = sorted({r["encryption"] for r in cond_rows})
        detectors   = sorted({r["detector"]   for r in cond_rows})
        # average AUC over methods/levels per (detector, encryption)
        from collections import defaultdict
        enc_sums: dict[tuple[str, str], list[float]] = defaultdict(list)
        for r in cond_rows:
            try:
                enc_sums[(r["detector"], r["encryption"])].append(float(r["roc_auc"]))
            except (ValueError, TypeError):
                pass
        enc_avg = {k: sum(v) / len(v) for k, v in enc_sums.items() if v}

        print(f"\n  AUC BY ENCRYPTION")
        header = f"  {'DETECTOR':<22}" + "".join(f"  {e:>10}" for e in encryptions)
        print(header)
        print(f"  {'─'*22}" + "".join(f"  {'─'*10}" for _ in encryptions))
        for det in sorted(detectors, key=lambda d: -enc_avg.get((d, encryptions[0]), 0)):
            row_str = f"  {det:<22}"
            for e in encryptions:
                val = enc_avg.get((det, e), None)
                row_str += f"  {f'{val:.3f}' if val is not None else '  —':>10}"
            print(row_str)

    figures_dir = run_dir / "figures"
    if figures_dir.exists():
        top_pngs = sorted(figures_dir.glob("*.png"))
        nested_pngs = sorted(figures_dir.glob("*/*.png"))
        if top_pngs or nested_pngs:
            total = len(top_pngs) + len(nested_pngs)
            print(f"\n  FIGURES  ({total} PNGs in {figures_dir})")
            for path in top_pngs:
                print(f"    - {path.name}")
            sub_counts: dict[str, int] = {}
            for path in nested_pngs:
                sub_counts[path.parent.name] = sub_counts.get(path.parent.name, 0) + 1
            for sub, count in sorted(sub_counts.items()):
                print(f"    - {sub}/  ({count} PNGs)")

    print(f"\n{'═'*W}\n")

# ── Profile constants ─────────────────────────────────────────────────────────

_PROFILE_N_GROUPS: dict[str, int] = {
    "prototype":   20,
    "full_design": 500,
}

_PROFILE_COCO_TARGET: dict[str, int] = {
    "prototype":   12,   # 12 of 20 real groups per run
    "full_design": 300,
}

_PROFILE_FLICKR_TARGET: dict[str, int] = {
    "prototype":    8,   # 8 of 20 real groups per run
    "full_design": 200,
}


# ── HF token resolution ───────────────────────────────────────────────────────

def _load_env_file(project_root: Path) -> None:
    """Parse a .env file in project_root and inject any new keys into os.environ."""
    env_file = project_root / ".env"
    if not env_file.exists():
        return
    with env_file.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key   = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _resolve_hf_token(project_root: Path, profile: str, ml_engine: str) -> None:
    """Ensure HF_TOKEN is available when needed; handle missing token per profile.

    - Loads .env automatically if present.
    - prototype  : token optional — inference_api will attempt an anonymous request.
    - full_design: token required — prints .env instructions and exits if absent.
    """
    if ml_engine != "inference_api":
        return  # only the inference_api engine needs a token

    _load_env_file(project_root)

    if os.environ.get("HF_TOKEN"):
        return  # already set

    if profile == "prototype":
        print(
            "  Note: HF_TOKEN not set — attempting anonymous HuggingFace Inference API request.\n"
            "  If generation fails, create a .env file in the project root:\n"
            "    echo 'HF_TOKEN=hf_your_token_here' > .env\n"
        )
    else:
        # full_design: token is effectively required for 500 generations
        print(
            "Error: HF_TOKEN is required for full_design ML cover generation.\n"
            "\n"
            "Create a .env file in the project root with your HuggingFace token:\n"
            "\n"
            "    echo 'HF_TOKEN=hf_your_token_here' > .env\n"
            "\n"
            "Get a free token at: https://huggingface.co/settings/tokens\n"
            "(.env is gitignored and will never be committed.)"
        )
        sys.exit(1)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_count(path: Path) -> int:
    """Return number of data rows in a CSV manifest, or 0 if the file is absent."""
    if not path.exists():
        return 0
    with path.open(newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


# ── Per-run cover preparation ─────────────────────────────────────────────────

def _prepare_run_covers(
    project_root: Path,
    run_dir: Path,
    n_groups: int,
    ml_engine: str,
    profile: str,
    seed: int,
) -> Path:
    """Download and generate covers for this run into run_dir/covers/.

    Returns path to run_dir/manifests/covers.csv.
    Idempotent: if covers.csv already has n_groups*3 rows, skips all steps.
    """
    covers_csv = run_dir / "manifests" / "covers.csv"
    if covers_csv.exists() and _row_count(covers_csv) >= n_groups * 3:
        print(f"  ✓ Run covers already present ({_row_count(covers_csv)} rows).")
        return covers_csv

    real_manifest = run_dir / "manifests" / "covers_real.csv"
    prompts_csv   = run_dir / "manifests" / "generation_prompts.csv"
    ml_a_manifest = run_dir / "manifests" / "covers_ml_a.csv"
    ml_b_manifest = run_dir / "manifests" / "covers_ml_b.csv"

    # ── Step 1: real covers ────────────────────────────────────────────────
    if real_manifest.exists() and _row_count(real_manifest) >= n_groups:
        print(f"  [1/3] ✓ Real covers already downloaded.")
    else:
        coco_n   = _PROFILE_COCO_TARGET[profile]
        flickr_n = _PROFILE_FLICKR_TARGET[profile]
        print(f"  [1/3] Downloading {coco_n} COCO + {flickr_n} Flickr30k covers (seed={seed}) …")
        from src.data.download_real_covers import download_real_covers
        download_real_covers(
            project_root=project_root,
            coco_target=coco_n,
            flickr_target=flickr_n,
            seed=seed,
            run_dir=run_dir,
        )

    # ── Step 2: ML covers ──────────────────────────────────────────────────
    ml_ready = (
        ml_a_manifest.exists() and _row_count(ml_a_manifest) >= n_groups
        and ml_b_manifest.exists() and _row_count(ml_b_manifest) >= n_groups
    )
    if ml_ready:
        print(f"  [2/3] ✓ ML covers already generated.")
    else:
        if not prompts_csv.exists():
            print("  Error: generation_prompts.csv not found — real covers must be downloaded first.")
            sys.exit(1)
        print(f"  [2/3] Generating ML covers (engine={ml_engine}) …")
        from src.data.generate_ml_covers import generate_ml_covers_from_prompts
        generate_ml_covers_from_prompts(
            project_root=project_root,
            prompts_csv=prompts_csv,
            engine=ml_engine,
            max_groups=n_groups,
            seed_base=seed,
            run_dir=run_dir,
        )

    # ── Step 3: merge manifests ────────────────────────────────────────────
    print(f"  [3/3] Merging covers manifest ({n_groups} groups × 3 sources = {n_groups * 3} rows) …")
    from src.data.merge_covers_master import merge_covers_master
    covers_csv = merge_covers_master(
        project_root=project_root,
        real_manifest=real_manifest,
        ml_a_manifest=ml_a_manifest,
        ml_b_manifest=ml_b_manifest,
        output_manifest=covers_csv,
        expected_groups=n_groups,
    )
    print(f"  → {covers_csv}")
    return covers_csv


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the steganography pipeline for a named experiment profile.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "profile",
        choices=list(_PROFILE_N_GROUPS.keys()),
        help="Experiment profile: 'prototype' (60 images) or 'full_design' (1500 images).",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Override the auto-generated run identifier (e.g. 'prototype_001').",
    )
    parser.add_argument(
        "--ml-engine",
        choices=["diffusers", "inference_api", "stub"],
        default="inference_api",
        help="Backend for ML cover generation (default: inference_api).",
    )
    args = parser.parse_args()

    profile      = args.profile
    n_groups     = _PROFILE_N_GROUPS[profile]
    project_root = Path(__file__).parent.resolve()

    from src.pipeline.config import PipelineConfig
    from src.pipeline.runner import PipelineRunner

    config = PipelineConfig.from_profile(project_root, profile)
    runner = PipelineRunner(config)

    # ── Generate cover seed and create run directory ──────────────────────────
    import random as _rand
    cover_seed = _rand.randrange(2**31)

    run_dir = (
        project_root / "runs" / args.run_id
        if args.run_id
        else runner._next_run_dir(profile)
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    run_id_str = run_dir.name

    print(f"\n{'='*60}")
    print(f"Profile  : {profile}")
    print(f"Groups   : {n_groups} groups × 3 sources = {n_groups * 3} images")
    print(f"Run dir  : {run_dir}")
    print(f"{'='*60}\n")

    # ── Resolve HF token ──────────────────────────────────────────────────────
    _resolve_hf_token(project_root, profile, args.ml_engine)

    # ── Prepare covers for this run ───────────────────────────────────────────
    print("Preparing covers for this run …")
    covers_manifest = _prepare_run_covers(
        project_root, run_dir, n_groups, args.ml_engine, profile, cover_seed
    )
    print(f"\nCovers ready — starting pipeline …\n")

    # ── Run pipeline ──────────────────────────────────────────────────────────
    cli_args = [
        "--project-root",    str(project_root),
        "run-all",
        "--profile",         profile,
        "--covers-manifest", str(covers_manifest),
        "--run-id",          run_id_str,
        "--cover-seed",      str(cover_seed),
        "--execute-embeddings",
        "--execute-detectors",
        "--skip-unimplemented",
        "--generate-figures",
    ]

    sys.argv = ["run.py"] + cli_args

    from src.pipeline.cli import main as cli_main
    cli_main()

    # ── Print results summary ─────────────────────────────────────────────────
    _print_results_summary(run_dir)


if __name__ == "__main__":
    main()
