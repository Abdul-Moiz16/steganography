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

    # Write a top-level .meta.json mirroring the main pipeline's
    # convention. This captures the configuration used to assemble
    # the training set so post-hoc analysis can verify reproducibility
    # without re-deriving anything from the manifests.
    import json as _json
    from datetime import datetime as _dt
    meta = {
        "purpose": "SRNet / DCTR learned-baseline training set",
        "created_utc": _dt.utcnow().isoformat() + "Z",
        "n_groups_requested": args.n_groups,
        "seed": args.seed,
        "ml_engine": args.ml_engine,
        "coco_fraction": args.coco_fraction,
        "excluded_captions_from": (str(args.exclude_captions_from)
                                    if args.exclude_captions_from else None),
        "skip_stages": {
            "real": args.skip_real,
            "ml": args.skip_ml,
            "embed": args.skip_embed,
        },
    }
    (run_dir / ".meta.json").write_text(_json.dumps(meta, indent=2))

    # Caption exclusion -----------------------------------------------------
    excluded: set[str] = set()
    if args.exclude_captions_from is not None:
        excl_run = args.exclude_captions_from
        if not excl_run.is_absolute():
            excl_run = project_root / excl_run
        excluded = load_excluded_caption_ids(excl_run)
        print(f"[training-set] excluding {len(excluded)} caption_ids from {excl_run.name}")
        # Archive the excluded list under manifests/ for full provenance.
        excl_archive = run_dir / "manifests" / "excluded_caption_ids.txt"
        excl_archive.parent.mkdir(parents=True, exist_ok=True)
        excl_archive.write_text(
            f"# {len(excluded)} caption_ids excluded from this training set\n"
            f"# Source: {excl_run}\n"
            f"# Reason: prevent train/test leakage at the caption level\n"
            + "\n".join(sorted(excluded))
        )

    # Real-cover download ---------------------------------------------------
    if not args.skip_real:
        # Caption-exclusion can drop a sizeable fraction of the downloaded
        # pool (we observe ~36% overlap between a random caption sample and
        # the 3000-caption test set, because both come from the same
        # COCO+Flickr30K validation corpus). Rather than guess a single
        # overshoot factor, we use a top-up loop: download an initial batch
        # with a generous overshoot, prune by caption, and if we land short
        # of target_n, download another batch with a fresh seed and merge
        # it in. Repeat until we hit target_n or hit MAX_ATTEMPTS.
        _download_real_covers_until_target(
            project_root=project_root,
            run_dir=run_dir,
            target_n=args.n_groups,
            base_seed=args.seed,
            coco_fraction=args.coco_fraction,
            excluded=excluded,
        )
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


def _prune_excluded_real_covers(
    run_dir: Path,
    excluded: set[str],
    target_n: int,
) -> int:
    """Drop rows whose caption_id is in the excluded set from ALL real-cover
    manifests, then truncate to target_n. Rewrites the manifests in-place,
    unlinks orphaned image files, and returns the number of surviving rows
    (caller decides whether shortfall is fatal or just needs a top-up).

    Bug history: earlier versions of this function only pruned
    raw_cover_index_real.csv, leaving covers_real.csv and
    generation_prompts.csv with the full overshoot intact. ML cover
    generation then read from the un-pruned prompts manifest and produced
    ml_a / ml_b covers for ~1080 test-set captions, causing both
    train/test leakage AND a downstream merge_covers_master failure due
    to mismatched group_id sets. Both manifests are now pruned in lockstep.
    """
    manifest_paths = [
        run_dir / "manifests" / "raw_cover_index_real.csv",
        run_dir / "manifests" / "covers_real.csv",
        run_dir / "manifests" / "generation_prompts.csv",
    ]
    real_index = manifest_paths[0]
    if not real_index.exists():
        return 0

    # Decide which group_ids survive based on the canonical raw index.
    with real_index.open() as fh:
        rows = list(csv.DictReader(fh))
    total = len(rows)
    kept_rows = [r for r in rows if r.get("caption_id", "").strip() not in excluded][:target_n]
    kept_gids = {int(r["group_id"]) for r in kept_rows}

    print(
        f"[training-set] excluded {total - len(kept_rows)} rows by caption "
        f"({len(excluded)} caption_ids on excl list, {total} downloaded); "
        f"keeping {len(kept_rows)} (target {target_n})"
    )

    # Prune every real-cover manifest to the same kept group_id set so the
    # downstream merge_covers_master ids_real == ids_ml_a == ids_ml_b check
    # holds. Preserve each manifest's own ordering and column set.
    for mpath in manifest_paths:
        if not mpath.exists():
            continue
        with mpath.open() as fh:
            all_rows = list(csv.DictReader(fh))
            fieldnames = list(all_rows[0].keys()) if all_rows else []
        kept = [r for r in all_rows if _row_gid(r) in kept_gids]
        with mpath.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(kept)

    # Unlink orphaned image files (use the canonical raw-index dropped set).
    dropped_rows = [r for r in rows if _row_gid(r) not in kept_gids]
    for row in dropped_rows:
        img_path = row.get("raw_image_path")
        if img_path:
            p = (Path(img_path) if Path(img_path).is_absolute()
                 else run_dir.parent.parent / img_path)
            if p.exists():
                p.unlink()

    return len(kept_rows)


def _row_gid(row: dict) -> int:
    """Robust int(group_id) accessor for csv.DictReader rows."""
    try:
        return int(row.get("group_id", ""))
    except (ValueError, TypeError):
        return -1


def _download_real_covers_until_target(
    *,
    project_root: Path,
    run_dir: Path,
    target_n: int,
    base_seed: int,
    coco_fraction: float,
    excluded: set[str],
) -> None:
    """Download real covers, top-up the download with fresh seeds until we
    have exactly ``target_n`` covers surviving caption-exclusion (or we hit
    MAX_ATTEMPTS, in which case we abort loudly).

    Strategy
    --------
    Attempt 1: pull an initial overshoot batch (1.75x when caption exclusion
    is active, 1.10x otherwise). Caption-prune.
    Attempt 2..N: if we are short by ``deficit``, pull another batch sized
    to roughly ``deficit / (1 - observed_exclusion_rate)`` (with a generous
    safety multiplier) using a fresh seed. Merge into the existing manifests
    with collision-safe group_id renumbering. Caption-prune again.

    We stop as soon as the surviving cover count reaches ``target_n`` and
    truncate any overshoot via the standard prune-with-cap call.
    """
    from src.data.download_real_covers import download_real_covers

    MAX_ATTEMPTS = 6
    INITIAL_OVERSHOOT = 1.75 if excluded else 1.10
    survivors = 0

    for attempt in range(1, MAX_ATTEMPTS + 1):
        if attempt == 1:
            overshoot = int(target_n * INITIAL_OVERSHOOT)
            coco_target = int(overshoot * coco_fraction)
            flickr_target = overshoot - coco_target
            print(
                f"[training-set] download attempt 1/{MAX_ATTEMPTS} (initial): "
                f"coco={coco_target}, flickr={flickr_target}, "
                f"overshoot {overshoot} for target {target_n}"
            )
            download_real_covers(
                project_root=project_root,
                seed=base_seed,
                coco_target=coco_target,
                flickr_target=flickr_target,
                run_dir=run_dir,
            )
        else:
            deficit = target_n - survivors
            # Estimate observed exclusion rate from the previous attempt to
            # size the next batch. Fall back to a conservative 0.5 if we
            # have no prior info.
            exclusion_rate = _estimate_exclusion_rate(run_dir, excluded)
            # 2.0x safety multiplier on top of the inverse-survival rate so
            # that even an unlucky second batch lands us above target.
            topup_n = max(50, int(deficit / max(0.05, 1.0 - exclusion_rate) * 2.0))
            coco_target = int(topup_n * coco_fraction)
            flickr_target = topup_n - coco_target
            print(
                f"[training-set] download attempt {attempt}/{MAX_ATTEMPTS} (topup): "
                f"deficit={deficit}, est_excl={exclusion_rate:.2%}, "
                f"requesting coco={coco_target}, flickr={flickr_target}, "
                f"topup_n={topup_n}"
            )
            _topup_real_covers(
                project_root=project_root,
                run_dir=run_dir,
                seed=base_seed + attempt * 1000,
                coco_target=coco_target,
                flickr_target=flickr_target,
            )

        # Prune + report
        if excluded:
            survivors = _prune_excluded_real_covers(run_dir, excluded, target_n=target_n)
        else:
            # No exclusion: just truncate to target_n
            survivors = _truncate_real_covers(run_dir, target_n=target_n)

        if survivors >= target_n:
            print(
                f"[training-set] reached target after {attempt} attempt(s): "
                f"{survivors}/{target_n} survivors"
            )
            return

    raise RuntimeError(
        f"After {MAX_ATTEMPTS} download attempts only {survivors}/{target_n} "
        f"covers survived caption exclusion. The COCO+Flickr30K pool may be "
        f"exhausted at this exclusion rate -- consider reducing --n-groups or "
        f"broadening the source corpus."
    )


def _estimate_exclusion_rate(run_dir: Path, excluded: set[str]) -> float:
    """Estimate fraction of the downloaded raw pool that gets excluded."""
    raw_idx = run_dir / "manifests" / "raw_cover_index_real.csv"
    if not raw_idx.exists():
        return 0.5  # conservative default
    with raw_idx.open() as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return 0.5
    n_excl = sum(1 for r in rows if r.get("caption_id", "").strip() in excluded)
    return n_excl / len(rows)


def _topup_real_covers(
    *,
    project_root: Path,
    run_dir: Path,
    seed: int,
    coco_target: int,
    flickr_target: int,
) -> None:
    """Download additional real covers and merge them into the run's
    manifests. New rows are dedup'd by (orig_id, caption_id) against the
    existing set and renumbered to avoid group_id collisions.

    Implementation: download to a temp subdirectory, then merge.
    """
    import shutil
    import tempfile
    from src.data.download_real_covers import download_real_covers

    manifests_dir = run_dir / "manifests"
    covers_dir = run_dir / "covers" / "real"

    # Read existing rows to know what we already have.
    existing_raw = _read_csv_rows(manifests_dir / "raw_cover_index_real.csv")
    existing_real = _read_csv_rows(manifests_dir / "covers_real.csv")
    existing_prompts = _read_csv_rows(manifests_dir / "generation_prompts.csv")

    existing_orig_ids = {r.get("orig_id") for r in existing_raw}
    existing_caption_ids = {r.get("caption_id") for r in existing_raw}
    current_max_gid = max((_row_gid(r) for r in existing_raw), default=0)

    # Download topup into a temp subdirectory of the run (same filesystem
    # so the eventual file moves are cheap).
    tmp_run = run_dir / f"_topup_{seed}"
    if tmp_run.exists():
        shutil.rmtree(tmp_run)
    tmp_run.mkdir(parents=True)
    try:
        download_real_covers(
            project_root=project_root,
            seed=seed,
            coco_target=coco_target,
            flickr_target=flickr_target,
            run_dir=tmp_run,
        )

        # Read the temp manifests, drop duplicates (we'll get some across
        # batches because download_real_covers is seed-deterministic but
        # the pools overlap), and renumber group_ids to land after our
        # current max.
        tmp_raw = _read_csv_rows(tmp_run / "manifests" / "raw_cover_index_real.csv")
        tmp_real = _read_csv_rows(tmp_run / "manifests" / "covers_real.csv")
        tmp_prompts = _read_csv_rows(tmp_run / "manifests" / "generation_prompts.csv")

        # Build a dedup mask + gid remap from the raw index.
        keep_old_gids: list[int] = []
        old_to_new: dict[int, int] = {}
        next_gid = current_max_gid + 1
        for r in tmp_raw:
            if r.get("orig_id") in existing_orig_ids:
                continue
            if r.get("caption_id") in existing_caption_ids:
                continue
            old_gid = _row_gid(r)
            old_to_new[old_gid] = next_gid
            keep_old_gids.append(old_gid)
            next_gid += 1
            existing_orig_ids.add(r.get("orig_id"))
            existing_caption_ids.add(r.get("caption_id"))

        n_dedup = len(tmp_raw) - len(keep_old_gids)
        print(
            f"[training-set]   topup downloaded {len(tmp_raw)}, "
            f"deduped {n_dedup}, kept {len(keep_old_gids)} new covers"
        )

        # Move dedup'd image files into the main covers/real dir, with
        # filenames renamed to the new group_id.
        for r in tmp_raw:
            old_gid = _row_gid(r)
            if old_gid not in old_to_new:
                continue
            new_gid = old_to_new[old_gid]
            src_rel = r.get("raw_image_path") or ""
            src_path = (Path(src_rel) if Path(src_rel).is_absolute()
                        else project_root / src_rel)
            if not src_path.exists():
                continue
            new_name = src_path.name.replace(
                f"g{old_gid:04d}", f"g{new_gid:04d}", 1,
            )
            dst_path = covers_dir / new_name
            shutil.move(str(src_path), str(dst_path))
            # Update row path in-place (relative to project root).
            try:
                rel = dst_path.relative_to(project_root)
            except ValueError:
                rel = dst_path
            r["raw_image_path"] = str(rel)

        # Renumber all rows across the three manifests, then append.
        def _renumber_and_filter(rows, also_rewrite_paths=False):
            out = []
            for r in rows:
                old_gid = _row_gid(r)
                if old_gid not in old_to_new:
                    continue
                r["group_id"] = str(old_to_new[old_gid])
                out.append(r)
            return out

        new_raw = _renumber_and_filter(tmp_raw)
        new_real = _renumber_and_filter(tmp_real)
        new_prompts = _renumber_and_filter(tmp_prompts)

        # Patch path columns in covers_real (spatial_path / frequency_path)
        # and generation_prompts (real_spatial_path / real_frequency_path)
        # so they reference the new filenames. Old filenames embed the old
        # group_id like "g0123__src-real.png".
        def _patch_paths(rows, columns):
            for r in rows:
                old_gid = _find_old_gid_for_new(r, old_to_new)
                if old_gid is None:
                    continue
                for col in columns:
                    val = r.get(col)
                    if val:
                        r[col] = val.replace(
                            f"g{old_gid:04d}", f"g{old_to_new[old_gid]:04d}", 1,
                        )

        _patch_paths(new_real, ["spatial_path", "frequency_path"])
        _patch_paths(new_prompts, ["real_spatial_path", "real_frequency_path"])

        # Append to the run's manifests.
        _append_rows(manifests_dir / "raw_cover_index_real.csv",
                     existing_raw, new_raw)
        _append_rows(manifests_dir / "covers_real.csv",
                     existing_real, new_real)
        _append_rows(manifests_dir / "generation_prompts.csv",
                     existing_prompts, new_prompts)
    finally:
        # Clean up the temp subdir (its image files have already been moved
        # out, but any leftover JSONs / partial files should be cleaned).
        if tmp_run.exists():
            shutil.rmtree(tmp_run, ignore_errors=True)


def _find_old_gid_for_new(row: dict, old_to_new: dict[int, int]) -> int | None:
    """Reverse-lookup an old gid given a row whose group_id is already new."""
    try:
        new_gid = int(row.get("group_id", ""))
    except (ValueError, TypeError):
        return None
    for old, new in old_to_new.items():
        if new == new_gid:
            return old
    return None


def _read_csv_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as fh:
        return list(csv.DictReader(fh))


def _append_rows(path: Path, existing: list[dict], new_rows: list[dict]) -> None:
    """Rewrite ``path`` as ``existing + new_rows``, preserving the existing
    header / column order. The two row sets should already share the same
    schema (they came from the same ``download_real_covers`` writer).
    """
    if not (existing or new_rows):
        return
    fieldnames = list((existing or new_rows)[0].keys())
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(existing)
        w.writerows(new_rows)


def _truncate_real_covers(run_dir: Path, target_n: int) -> int:
    """Truncate all three real-cover manifests to the first ``target_n`` rows
    (no caption exclusion needed). Used when ``excluded`` is empty.
    """
    manifest_paths = [
        run_dir / "manifests" / "raw_cover_index_real.csv",
        run_dir / "manifests" / "covers_real.csv",
        run_dir / "manifests" / "generation_prompts.csv",
    ]
    n = 0
    for mpath in manifest_paths:
        if not mpath.exists():
            continue
        rows = _read_csv_rows(mpath)
        if rows and len(rows) > target_n:
            fieldnames = list(rows[0].keys())
            with mpath.open("w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=fieldnames)
                w.writeheader()
                w.writerows(rows[:target_n])
            n = target_n
        else:
            n = len(rows)
    return n


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
