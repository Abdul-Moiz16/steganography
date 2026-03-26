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

    print(f"\n{'═'*W}\n")

# ── Profile constants ─────────────────────────────────────────────────────────

_PROFILE_N_GROUPS: dict[str, int] = {
    "prototype":   20,
    "full_design": 500,
}

_PROFILE_COCO_TARGET: dict[str, int] = {
    "prototype":   12,
    "full_design": 300,
}

_PROFILE_FLICKR_TARGET: dict[str, int] = {
    "prototype":   8,
    "full_design": 200,
}

_PROFILE_COVERS_MANIFEST: dict[str, str] = {
    "prototype":   "data/manifests/covers_prototype.csv",
    "full_design": "data/manifests/covers_master.csv",
}

_REAL_MANIFEST = "data/manifests/covers_master_real.csv"
_ML_A_MANIFEST = "data/manifests/covers_master_ml_a.csv"
_ML_B_MANIFEST = "data/manifests/covers_master_ml_b.csv"
_PROMPTS_CSV   = "data/manifests/generation_prompts.csv"


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


# ── Stage 1: real covers ──────────────────────────────────────────────────────

def _ensure_real_covers(project_root: Path, n_groups: int, profile: str) -> None:
    """Download and standardize real covers if the manifest is missing or incomplete."""
    manifest = project_root / _REAL_MANIFEST
    current  = _row_count(manifest)
    if current >= n_groups:
        print(f"  ✓ Real covers already present ({current} rows).")
        return

    coco_n    = _PROFILE_COCO_TARGET[profile]
    flickr_n  = _PROFILE_FLICKR_TARGET[profile]
    print(f"  Downloading {coco_n} COCO + {flickr_n} Flickr30k covers …")
    from src.data.download_real_covers import download_real_covers
    download_real_covers(
        project_root=project_root,
        coco_target=coco_n,
        flickr_target=flickr_n,
    )
    print(f"  → {manifest}")


# ── Stage 2: ML covers ────────────────────────────────────────────────────────

def _ensure_ml_covers(project_root: Path, n_groups: int, ml_engine: str) -> None:
    """Generate ML covers (SDXL + FLUX) if manifests are missing or incomplete."""
    ml_a = project_root / _ML_A_MANIFEST
    ml_b = project_root / _ML_B_MANIFEST
    if _row_count(ml_a) >= n_groups and _row_count(ml_b) >= n_groups:
        print(f"  ✓ ML covers already present ({_row_count(ml_a)} rows each).")
        return

    prompts_csv = project_root / _PROMPTS_CSV
    if not prompts_csv.exists():
        print("  Error: generation_prompts.csv not found — real covers must be downloaded first.")
        sys.exit(1)

    print(f"  Generating ML covers for {n_groups} groups (engine={ml_engine}) …")
    from src.data.generate_ml_covers import generate_ml_covers_from_prompts
    generate_ml_covers_from_prompts(
        project_root=project_root,
        prompts_csv=prompts_csv,
        engine=ml_engine,
        max_groups=n_groups,
    )
    print(f"  → {ml_a}")
    print(f"  → {ml_b}")


# ── Stage 3: merged covers manifest ──────────────────────────────────────────

def _ensure_covers_manifest(project_root: Path, n_groups: int, profile: str) -> Path:
    """Merge component manifests into the profile covers manifest if missing."""
    out     = project_root / _PROFILE_COVERS_MANIFEST[profile]
    needed  = n_groups * 3  # real + ml_a + ml_b
    current = _row_count(out)
    if current >= needed:
        print(f"  ✓ Covers manifest already present ({current} rows).")
        return out

    print(f"  Merging covers manifest ({n_groups} groups × 3 sources = {needed} rows) …")
    from src.data.merge_covers_master import merge_covers_master
    out = merge_covers_master(
        project_root=project_root,
        real_manifest=Path(_REAL_MANIFEST),
        ml_a_manifest=Path(_ML_A_MANIFEST),
        ml_b_manifest=Path(_ML_B_MANIFEST),
        output_manifest=out,
        expected_groups=n_groups,
    )
    print(f"  → {out}")
    return out


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

    print(f"\n{'='*60}")
    print(f"Profile  : {profile}")
    print(f"Groups   : {n_groups} × 3 sources = {n_groups * 3} images")
    print(f"{'='*60}\n")

    # ── Step 1: real covers ───────────────────────────────────────────────────
    print("[1/3] Real covers")
    _ensure_real_covers(project_root, n_groups, profile)

    # ── Step 2: ML covers ─────────────────────────────────────────────────────
    print("[2/3] ML covers")
    _resolve_hf_token(project_root, profile, args.ml_engine)
    _ensure_ml_covers(project_root, n_groups, args.ml_engine)

    # ── Step 3: combined covers manifest ─────────────────────────────────────
    print("[3/3] Covers manifest")
    covers_manifest = _ensure_covers_manifest(project_root, n_groups, profile)

    print(f"\nAll covers ready — starting pipeline …\n")

    # ── Resolve run dir up-front so we can print results afterward ────────────
    from src.pipeline.config import PipelineConfig
    from src.pipeline.runner import PipelineRunner

    config    = PipelineConfig.from_profile(project_root, profile)
    runner    = PipelineRunner(config)
    run_dir   = (
        project_root / "runs" / args.run_id
        if args.run_id
        else runner._next_run_dir(profile)
    )
    run_id_str = run_dir.name

    # ── Run pipeline ──────────────────────────────────────────────────────────
    cli_args = [
        "--project-root",    str(project_root),
        "run-all",
        "--profile",         profile,
        "--covers-manifest", str(covers_manifest),
        "--run-id",          run_id_str,
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
