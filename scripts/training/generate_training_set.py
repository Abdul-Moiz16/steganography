"""Assemble a training-only run for SRNet / DCTR learned baselines.

Calls the same modules the main pipeline uses (real-cover download,
ML-cover generation, LSB/DCT embedding) but writes to a separate
``runs/training_<id>/`` directory. The training pipeline must never
touch the held-out test run, so we explicitly exclude any caption_id
that appears in the test run's manifests.

Usage
-----

    python scripts/training/generate_training_set.py \
        --n-groups 3500 \
        --out-run runs/training_v1 \
        --seed 4242 \
        --exclude-captions-from runs/prototype_full_20260513_005357_p8765

The script writes the same directory layout as the main pipeline:

    runs/training_v1/
        covers/{real,ml_a,ml_b}/
        stego/{lsb,dct}/{low,medium,high}/{plain,encrypted}/{real,ml_a,ml_b}/
        payloads/
        manifests/

so the existing training scripts (train_srnet.py, train_dctr.py) can
discover (cover, stego) pairs by walking the standard layout.

This script is OUT of the main pipeline by design: it has no entry in
run.py and cannot be invoked from the web UI. It is invoked once,
manually, before the first training run.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# Make the script runnable directly (without PYTHONPATH=.) by ensuring
# the project root is on sys.path before any 'from src.xxx' import.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.data.download_real_covers import download_real_covers
from src.data.generate_ml_covers import generate_ml_covers_from_prompts


# ---------------------------------------------------------------------------
# Caption-exclusion helpers
# ---------------------------------------------------------------------------

def load_excluded_caption_ids(test_run: Path) -> set[str]:
    """Return the set of caption_id strings used in ``test_run``.

    Reads ``manifests/raw_cover_index_real.csv`` for caption_id; this is
    the canonical column for "what caption did we draw for this group".
    Captions appearing here are excluded from the training-set
    generation so that no caption is shared between training and test.
    """
    manifest = test_run / "manifests" / "raw_cover_index_real.csv"
    if not manifest.exists():
        raise FileNotFoundError(
            f"Cannot exclude captions: {manifest} not found. "
            "Pass --exclude-captions-from to a completed run with a real-cover manifest."
        )
    captions: set[str] = set()
    with manifest.open() as fh:
        for row in csv.DictReader(fh):
            cid = row.get("caption_id", "").strip()
            if cid:
                captions.add(cid)
    return captions


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--n-groups", type=int, required=True,
                   help="Number of caption groups to assemble for training.")
    p.add_argument("--out-run", type=Path, required=True,
                   help="Destination run directory (e.g. runs/training_v1).")
    p.add_argument("--seed", type=int, default=4242,
                   help="Base seed for all stochastic steps. Distinct from main-pipeline seeds.")
    p.add_argument("--exclude-captions-from", type=Path, default=None,
                   help="Path to a test run; captions used there are excluded here.")
    p.add_argument("--ml-engine", default="inference_api",
                   choices=["diffusers", "inference_api", "stub"],
                   help="Backend for ML cover generation.")
    p.add_argument("--skip-real", action="store_true", help="Skip real-cover download (already on disk).")
    p.add_argument("--skip-ml", action="store_true", help="Skip ML cover generation.")
    p.add_argument("--skip-embed", action="store_true", help="Skip stego embedding stage.")
    p.add_argument("--coco-fraction", type=float, default=0.6,
                   help="Fraction of n-groups to source from COCO (rest from Flickr30k).")
    args = p.parse_args()

    project_root = Path(__file__).resolve().parents[2]
    run_dir = args.out_run.resolve() if args.out_run.is_absolute() else (project_root / args.out_run)
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"[training-set] project_root={project_root}")
    print(f"[training-set] run_dir={run_dir}")

    # Caption exclusion -----------------------------------------------------
    excluded: set[str] = set()
    if args.exclude_captions_from is not None:
        excl_run = args.exclude_captions_from
        if not excl_run.is_absolute():
            excl_run = project_root / excl_run
        excluded = load_excluded_caption_ids(excl_run)
        print(f"[training-set] excluding {len(excluded)} caption_ids from {excl_run.name}")

    # Real-cover download ---------------------------------------------------
    if not args.skip_real:
        # Overshoot the target to leave room for caption-exclusion pruning.
        overshoot = int(args.n_groups * 1.25)
        coco_target = int(overshoot * args.coco_fraction)
        flickr_target = overshoot - coco_target
        print(f"[training-set] downloading real covers (coco={coco_target}, flickr={flickr_target}, overshoot {overshoot})")
        download_real_covers(
            project_root=project_root,
            seed=args.seed,
            coco_target=coco_target,
            flickr_target=flickr_target,
            run_dir=run_dir,
        )
        # Post-filter the run's manifests against the excluded set; covered separately
        # because download_real_covers does not know about our exclusion list.
        if excluded:
            _prune_excluded_real_covers(run_dir, excluded, target_n=args.n_groups)
    else:
        print("[training-set] --skip-real: assuming real covers already in place")

    # ML cover generation ---------------------------------------------------
    prompts_csv = run_dir / "manifests" / "generation_prompts.csv"
    if not args.skip_ml:
        if not prompts_csv.exists():
            raise FileNotFoundError(
                f"{prompts_csv} not found. Either run the real-cover stage first or pass --skip-ml."
            )
        print(f"[training-set] generating ML covers ({args.ml_engine}) from {prompts_csv}")
        generate_ml_covers_from_prompts(
            project_root=project_root,
            prompts_csv=prompts_csv,
            engine=args.ml_engine,
            seed_base=args.seed + 1,  # decouple from real-cover seed
            max_groups=args.n_groups,
            run_dir=run_dir,
        )
    else:
        print("[training-set] --skip-ml: assuming ML covers already in place")

    # Embedding -------------------------------------------------------------
    if not args.skip_embed:
        print("[training-set] embedding stegos (LSB + DCT-LSB, 3 payloads, 2 encryptions)")
        _embed_training_stegos(run_dir, seed=args.seed + 2)
    else:
        print("[training-set] --skip-embed: assuming stegos already in place")

    print(f"[training-set] DONE — training run lives at {run_dir}")
    print("[training-set] next steps:")
    print("  - python scripts/training/train_srnet.py --training-run <run_dir> --method lsb --payload low ...")
    print("  - python scripts/training/train_dctr.py  --training-run <run_dir> --method dct --payload low ...")


# ---------------------------------------------------------------------------
# Stub helpers (filled in once we wire up to existing embedding modules)
# ---------------------------------------------------------------------------

def _count_rows(csv_path: Path) -> int:
    """Count data rows in a CSV (header not counted). Used to keep
    merge_covers_master's expected_groups in sync with what's actually
    on disk after caption-exclusion pruning."""
    with csv_path.open() as fh:
        return max(0, sum(1 for _ in fh) - 1)


def _prune_excluded_real_covers(run_dir: Path, excluded: set[str], target_n: int) -> None:
    """Drop rows whose caption_id is in the excluded set, then truncate to target_n.

    Rewrites the real-cover manifests in-place and unlinks the orphaned image files.
    """
    real_index = run_dir / "manifests" / "raw_cover_index_real.csv"
    if not real_index.exists():
        return
    with real_index.open() as fh:
        rows = list(csv.DictReader(fh))
        fieldnames = list(rows[0].keys()) if rows else []
    kept = [r for r in rows if r.get("caption_id", "").strip() not in excluded][:target_n]
    dropped = [r for r in rows if r not in kept]
    print(f"[training-set] excluded {len(rows)-len(kept)} rows by caption, keeping {len(kept)}")
    # Rewrite manifest
    with real_index.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(kept)
    # Unlink orphaned image files
    for row in dropped:
        img_path = row.get("raw_image_path")
        if img_path:
            p = (Path(img_path) if Path(img_path).is_absolute()
                 else run_dir.parent.parent / img_path)
            if p.exists():
                p.unlink()


def _embed_training_stegos(run_dir: Path, *, seed: int) -> None:
    """Embed LSB + DCT-LSB stegos for the assembled covers.

    Calls the main pipeline's embedding machinery via PipelineRunner,
    routed to ``run_dir/stego/`` so the training-run artefacts are
    isolated from the main runs directory. We never invoke run.py; we
    call the runner's stage methods directly.

    The runner is already idempotent and group-aware, so re-running this
    function with a partially-embedded run skips work already on disk.
    """
    from pathlib import Path as _Path
    from src.pipeline.config import PipelineConfig
    from src.pipeline.runner import PipelineRunner

    project_root = _Path(__file__).resolve().parents[2]

    # The training run lives at runs/<id>/ under project_root.
    # ---- Verify the cover-stage manifests exist ----
    real_manifest = run_dir / "manifests" / "covers_real.csv"
    ml_a_manifest = run_dir / "manifests" / "covers_ml_a.csv"
    ml_b_manifest = run_dir / "manifests" / "covers_ml_b.csv"
    for m in (real_manifest, ml_a_manifest, ml_b_manifest):
        if not m.exists():
            raise FileNotFoundError(
                f"Missing manifest {m}. Did the download/generation stages run?"
            )

    # build_payload_manifest does a strict n_groups check, so we must
    # pass the actual count from the merged manifest (after any caption
    # pruning) rather than the requested --n-groups (which may overshoot).
    n_groups = _count_rows(real_manifest)
    print(f"[embed] {n_groups} groups in covers_real.csv -- using this as n_groups")

    config = PipelineConfig(
        project_root=project_root,
        n_groups=n_groups,
        # Decouple seeds from the main pipeline so a collision in the
        # training set cannot accidentally match a test-run seed.
        split_seed=seed,
        payload_seed=seed,
        embed_seed=seed,
    )
    runner = PipelineRunner(config)

    # ---- Merge into covers_master.csv ----
    # merge_covers_master() validates that group_id sets agree across all
    # three sources, so a mismatch (e.g. an ML cell failed to generate)
    # will raise here rather than producing a half-broken stego manifest.
    print("[embed] merging covers_real + covers_ml_{a,b} -> covers_master")
    from src.data.merge_covers_master import merge_covers_master
    covers_master = merge_covers_master(
        project_root=project_root,
        real_manifest=real_manifest,
        ml_a_manifest=ml_a_manifest,
        ml_b_manifest=ml_b_manifest,
        output_manifest=run_dir / "manifests" / "covers.csv",
        expected_groups=_count_rows(real_manifest),  # match the actual count
    )

    # ---- Build payload manifest (writes payload bytes) ----
    print("[embed] building payload manifest + writing payload files")
    payload_manifest = runner.build_payload_manifest(
        covers_manifest_path=covers_master,
        output_manifest_path=run_dir / "manifests" / "payload_manifest.csv",
        write_payload_files=True,
        payload_root=run_dir / "payloads",
    )

    # ---- Build stego manifest with per-run stego_root ----
    print("[embed] building stego manifest (stego_root=runs/.../stego)")
    stego_manifest = runner.build_stego_manifest(
        covers_manifest_path=covers_master,
        payload_manifest_path=payload_manifest,
        output_manifest_path=run_dir / "manifests" / "stego_manifest.csv",
        stego_root=run_dir / "stego",
    )

    # ---- Execute embedding ----
    print("[embed] embedding stegos (this is the slow step)")
    n = runner.run_embedding_stage(
        stego_manifest,
        execute=True,
        quality_metrics_path=run_dir / "metrics" / "quality_metrics.csv",
    )
    print(f"[embed] DONE — {n} stego rows processed")


if __name__ == "__main__":
    main()
