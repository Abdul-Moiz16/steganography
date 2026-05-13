#!/usr/bin/env python3
"""Launch a fresh pipeline run that *reuses* the covers of an existing run.

This is the path you want when the covers (real downloads + ML
generations) are still good but the embedding-side knobs have changed
-- new payload fill rates, an added detector, etc. It saves the
expensive cover-prep stages (real downloads, HF ML generation) by
symlinking the existing ``covers/`` directory into a brand new run
dir, copying the cover-side manifests with their paths rewritten to
the new run id, and then driving the pipeline from the payload-manifest
stage onwards.

Usage
-----
    python scripts/rerun_with_existing_covers.py runs/<old_run_id>

Optional flags
--------------
    --new-run-id <id>      Override the auto-generated run id.
    --port-suffix p8765    Port suffix used in the auto-generated id.
    --profile <name>       Profile name; default is parsed from the
                           old run id (e.g. ``prototype_full``).
    --hardlink             Hardlink each cover file instead of one big
                           directory symlink. Slightly slower to set up
                           but the new run keeps its covers if the old
                           run dir is deleted (same-filesystem only).
    --copy                 Physically copy each cover file. Slowest and
                           doubles disk usage; use only when the old
                           run lives on a different filesystem and
                           hardlinks are not available.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import sys
from pathlib import Path


# Make src.* importable when running from anywhere.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


_COVER_MANIFEST_FILES = (
    "covers.csv",
    "covers_real.csv",
    "covers_ml.csv",
    "covers_ml_a.csv",
    "covers_ml_b.csv",
    "generation_prompts.csv",
    "raw_cover_index_real.csv",
)

_PATHLESS_FILES = (
    "ml_generation_summary.json",
    "real_download_summary.json",
)


def _parse_profile(run_id: str) -> str:
    for known in ("prototype_full", "prototype", "full_design"):
        if run_id.startswith(known + "_"):
            return known
    raise SystemExit(
        f"Could not infer profile from run id '{run_id}'. "
        f"Pass --profile explicitly."
    )


def _generate_run_id(profile: str, port_suffix: str) -> str:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{profile}_{ts}_{port_suffix}"


def _prepare_new_run(
    *,
    old_run: Path,
    new_run: Path,
    old_run_id: str,
    new_run_id: str,
    cover_mode: str,
) -> None:
    new_run.mkdir(parents=True)

    old_covers = (old_run / "covers").resolve()
    new_covers = new_run / "covers"

    if cover_mode == "symlink":
        new_covers.symlink_to(old_covers)
        print(f"  symlinked covers/ -> {old_covers}")
    elif cover_mode in ("hardlink", "copy"):
        new_covers.mkdir()
        for src_path in sorted(old_covers.rglob("*")):
            if src_path.is_dir():
                continue
            rel = src_path.relative_to(old_covers)
            dst = new_covers / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if cover_mode == "hardlink":
                try:
                    os.link(src_path, dst)
                    continue
                except OSError:
                    pass  # fall through to copy on cross-device failures
            shutil.copy2(src_path, dst)
        n_files = sum(1 for p in new_covers.rglob("*") if p.is_file())
        verb = {"copy": "copied", "hardlink": "hardlinked"}[cover_mode]
        print(f"  {verb} {n_files} cover files")
    else:
        raise ValueError(f"Unknown cover_mode: {cover_mode!r}")

    new_manifests = new_run / "manifests"
    new_manifests.mkdir()
    n_copied = 0
    for filename in _COVER_MANIFEST_FILES:
        src = old_run / "manifests" / filename
        if not src.exists():
            continue
        text = src.read_text(encoding="utf-8")
        rewritten = text.replace(old_run_id, new_run_id)
        (new_manifests / filename).write_text(rewritten, encoding="utf-8")
        n_copied += 1
    for filename in _PATHLESS_FILES:
        src = old_run / "manifests" / filename
        if src.exists():
            shutil.copyfile(src, new_manifests / filename)
            n_copied += 1
    print(f"  copied {n_copied} manifest files (paths rewritten {old_run_id} -> {new_run_id})")


def _write_meta_json(new_run: Path, *, profile: str, cfg) -> None:
    meta = {
        "payload_mode": cfg.payload_mode,
        "profile": profile,
        # Engine is historical; cover stages are skipped so the value is
        # informational only.
        "engine": "inference_api",
        "n_groups": cfg.n_groups,
        "active_methods": list(cfg.active_methods),
        "active_payload_levels": list(cfg.active_payload_levels),
        "active_encryption": list(cfg.active_encryption),
        "active_detectors": list(cfg.active_detectors),
        "include_bd_sens_auxiliary": cfg.include_bd_sens_auxiliary,
        "jpeg_quality": cfg.jpeg_quality,
    }
    (new_run / ".meta.json").write_text(json.dumps(meta))
    (new_run / ".running").write_text("manual-rerun")


def _build_config(profile: str, old_n_groups: int):
    from src.pipeline.config import PipelineConfig

    return PipelineConfig.from_profile(
        _PROJECT_ROOT,
        profile,
        n_groups=old_n_groups,
    )


def _read_old_n_groups(old_run: Path) -> int:
    config_path = old_run / "config.json"
    if config_path.exists():
        snap = json.loads(config_path.read_text())
        return int(snap.get("n_groups") or 0)
    meta_path = old_run / ".meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        return int(meta.get("n_groups") or 0)
    raise SystemExit(
        f"Could not determine n_groups from {old_run} (no config.json or .meta.json)."
    )


def _drive_pipeline(*, new_run: Path, profile: str, cfg) -> None:
    from src.pipeline.runner import PipelineRunner

    runner = PipelineRunner(cfg)
    covers_manifest = new_run / "manifests" / "covers.csv"
    try:
        out = runner.run_full_pipeline(
            covers_manifest_path=covers_manifest,
            execute_embeddings=True,
            execute_detectors=True,
            skip_unimplemented=True,
            generate_figures=True,
            run_dir=new_run,
            profile_name=profile,
        )
    finally:
        marker = new_run / ".running"
        if marker.exists():
            marker.unlink()

    print()
    print(f"  stego manifest:   {out.get('stego_manifest')}")
    print(f"  predictions:      {out.get('predictions')}")
    print(f"  embedding rows:   {out.get('embedding_rows_processed')}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("old_run", type=Path, help="Existing run dir to reuse covers from.")
    parser.add_argument("--new-run-id", default=None)
    parser.add_argument("--port-suffix", default="p8765")
    parser.add_argument("--profile", default=None)
    cover_group = parser.add_mutually_exclusive_group()
    cover_group.add_argument(
        "--hardlink", action="store_true",
        help="Hardlink each cover file (same disk, deletable independently).",
    )
    cover_group.add_argument(
        "--copy", action="store_true",
        help="Physically copy each cover file (doubles disk usage).",
    )
    args = parser.parse_args()
    cover_mode = "copy" if args.copy else ("hardlink" if args.hardlink else "symlink")

    old_run = args.old_run.resolve()
    if not old_run.exists():
        raise SystemExit(f"Old run dir not found: {old_run}")
    if not (old_run / "covers").exists():
        raise SystemExit(f"Old run dir has no covers/: {old_run}")

    old_run_id = old_run.name
    profile = args.profile or _parse_profile(old_run_id)
    new_run_id = args.new_run_id or _generate_run_id(profile, args.port_suffix)
    new_run = _PROJECT_ROOT / "runs" / new_run_id
    if new_run.exists():
        raise SystemExit(f"New run dir already exists: {new_run}")

    n_groups = _read_old_n_groups(old_run)
    cfg = _build_config(profile, n_groups)

    print(f"Profile         : {profile}")
    print(f"Old run         : {old_run_id}  (n_groups={n_groups})")
    print(f"New run         : {new_run_id}")
    print(f"Payload rates   : {cfg.payload_fill_rates}")
    print(f"Active detectors: {list(cfg.active_detectors)}")
    print()

    print("Preparing new run dir ...")
    _prepare_new_run(
        old_run=old_run,
        new_run=new_run,
        old_run_id=old_run_id,
        new_run_id=new_run_id,
        cover_mode=cover_mode,
    )
    _write_meta_json(new_run, profile=profile, cfg=cfg)
    print(f"  .meta.json + .running written")
    print()

    print(f"Driving pipeline body (payload -> embedding -> detection -> analysis) ...")
    _drive_pipeline(new_run=new_run, profile=profile, cfg=cfg)
    print()
    print(f"Done.")
    print(f"  Run dir: {new_run}")
    print(f"  Open the GUI run-detail page to inspect figures and verdicts.")


if __name__ == "__main__":
    main()
