"""Apply trained DCTR classifiers to an existing run, AS-IS.

Mirrors apply_srnet_to_run.py but for the DCT branch:
  - Loads one or more (scaler, classifier) joblib pickles
  - Extracts DCTR features in parallel from every (cover, stego) JPEG
    in the test run for the corresponding (method, payload) cell
  - Scores each image via the trained classifier
  - Writes predictions to predictions_dctr.csv matching predictions.csv
    schema (one row per cover per encryption variant, with shared score;
    one row per stego variant with its actual encryption)

The trained model is treated as a frozen, immutable artefact. This
script does NOT fine-tune, train, or modify the checkpoint in any way.

Usage
-----
    python scripts/inference/apply_dctr_to_run.py \
        --run runs/prototype_full_20260513_005357_p8765 \
        --models models/dctr_dct_low_v1.pkl \
                 models/dctr_dct_medium_v1.pkl \
                 models/dctr_dct_high_v1.pkl \
        --out runs/prototype_full_20260513_005357_p8765/predictions_dctr.csv

The script will:
  1. Refuse to run if any model's training_run_hash matches the test
     run (guards against train/test leakage).
  2. For each model, identify its (method, payload) cell from the
     checkpoint config and run inference on the matching subset.
  3. Score each physical cover image ONCE (cover bytes are identical
     regardless of encryption) and emit one row per encryption variant
     with the shared score (gotcha #3).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import multiprocessing as mp
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

# Make runnable without PYTHONPATH=.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


PREDICTION_FIELDS = [
    "detector", "group_id", "source", "method",
    "payload_level", "encryption", "label", "score",
]


# ---------------------------------------------------------------------------
# Multiprocessing worker (top-level so it pickles cleanly on Linux 'spawn')
# ---------------------------------------------------------------------------

def _extract_one(job: tuple) -> tuple:
    """Worker: extract DCTR features for one image and tag it.

    Returns (idx, features_or_None).
    """
    from src.detection_learned.dctr import dctr_features_path
    idx, path_str = job
    try:
        return (idx, dctr_features_path(path_str))
    except Exception as e:
        sys.stderr.write(f"[apply-dctr] feature extraction failed on {path_str}: {e}\n")
        return (idx, None)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class _ScoreEntry:
    idx: int
    path: Path
    kind: str               # "cover" | "stego"
    group_id: int
    source: str
    method: str
    payload_level: str
    encryption: str | None  # set for stegos; None for covers
    # For covers, we need the list of encryption variants to fan out the rows.
    cover_encryptions: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True,
                   help="Test run directory (e.g. runs/prototype_full_...).")
    p.add_argument("--models", type=Path, nargs="+", required=True,
                   help="One or more DCTR checkpoints (.pkl files).")
    p.add_argument("--out", type=Path, required=True,
                   help="Output predictions CSV.")
    p.add_argument("--n-workers", type=int, default=max(1, os.cpu_count() // 2),
                   help="Multiprocessing workers for feature extraction.")
    args = p.parse_args()

    # ---------------- Imports (deferred to keep CLI fast) ----------------
    import numpy as np
    import joblib

    from src.detection_learned.data import enumerate_cover_groups
    from src.detection_learned.dctr import FEATURE_DIM

    print(f"[apply-dctr] run={args.run}  n_workers={args.n_workers}")
    args.out.parent.mkdir(parents=True, exist_ok=True)

    # ---------------- Leakage guard ----------------
    run_hash = _hash_run(args.run)
    for ckpt_path in args.models:
        ckpt = joblib.load(ckpt_path)
        if ckpt.get("training_run_hash") == run_hash:
            raise RuntimeError(
                f"REFUSING TO RUN: checkpoint {ckpt_path} was trained on the "
                f"same run we're now testing on ({args.run}). This would be "
                "data leakage. Train on a different run."
            )

    # ---------------- Open output CSV ----------------
    with args.out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=PREDICTION_FIELDS)
        writer.writeheader()

        # ---------------- Iterate over checkpoints ----------------
        for ckpt_path in args.models:
            ckpt = joblib.load(ckpt_path)
            cfg = ckpt["config"]
            method, payload = cfg["method"], cfg["payload"]
            scaler = ckpt["scaler"]
            clf = ckpt["classifier"]
            print(f"[apply-dctr] {ckpt_path.name}: {method}/{payload}  "
                  f"(val_auc={ckpt.get('val_auc', 'n/a')})")

            # Sanity: feature dim consistent
            ck_dim = int(cfg.get("feature_dim", FEATURE_DIM))
            if ck_dim != FEATURE_DIM:
                raise RuntimeError(
                    f"checkpoint feature dim {ck_dim} != module FEATURE_DIM "
                    f"{FEATURE_DIM}. Did dctr.py change between training and "
                    f"inference? Refusing to score with a dim-mismatched model."
                )

            cover_groups = enumerate_cover_groups(
                args.run, method=method, payload_level=payload, split=None,
            )
            n_cov = len(cover_groups)
            n_ste = sum(len(cg.stego_paths) for cg in cover_groups)
            print(f"  {n_cov} covers + {n_ste} stegos to score "
                  f"(covers loaded once, written {n_ste} times with shared score)")

            entries = _build_entries(cover_groups, method, payload)

            # ---------------- Extract features in parallel ----------------
            N = len(entries)
            X = np.zeros((N, FEATURE_DIM), dtype=np.float32)
            n_failed = 0
            t0 = time.time()
            jobs = [(e.idx, str(e.path)) for e in entries]
            ctx = mp.get_context("spawn")
            with ctx.Pool(args.n_workers) as pool:
                done = 0
                for idx, feat in pool.imap_unordered(_extract_one, jobs, chunksize=8):
                    if feat is None:
                        n_failed += 1
                        continue
                    X[idx] = feat
                    done += 1
                    if (done % 1000) == 0:
                        rate = done / max(time.time() - t0, 1e-3)
                        eta_s = (N - done) / max(rate, 1e-3)
                        print(f"  features {done}/{N} "
                              f"({rate:.1f} img/s, ETA {eta_s/60:.1f} min)")
            print(f"  feature extraction done in {(time.time()-t0)/60:.1f} min "
                  f"({n_failed} failures)")

            # ---------------- Score ----------------
            Xs = scaler.transform(X)
            # decision_function gives a real-valued score; predict_proba a [0,1]
            # probability. The downstream merge expects scores compatible with
            # the existing predictions.csv (float in [0, 1] preferred), so we
            # use predict_proba and emit prob_class_1 (the "is stego" probability).
            if hasattr(clf, "predict_proba"):
                scores = clf.predict_proba(Xs)[:, 1]
            else:
                # Fallback: map decision_function through a sigmoid-like squash
                df = clf.decision_function(Xs)
                # min-max normalise per-checkpoint -- monotonic, AUC-preserving
                lo, hi = float(df.min()), float(df.max())
                scores = (df - lo) / max(hi - lo, 1e-9)

            # ---------------- Emit prediction rows ----------------
            for entry, score in zip(entries, scores):
                score_str = f"{float(score):.6f}"
                if entry.kind == "cover":
                    # Fan out: one row per encryption variant with shared score
                    for enc in entry.cover_encryptions:
                        writer.writerow({
                            "detector": "dctr",
                            "group_id": entry.group_id,
                            "source": entry.source,
                            "method": entry.method,
                            "payload_level": entry.payload_level,
                            "encryption": enc,
                            "label": 0,
                            "score": score_str,
                        })
                else:
                    writer.writerow({
                        "detector": "dctr",
                        "group_id": entry.group_id,
                        "source": entry.source,
                        "method": entry.method,
                        "payload_level": entry.payload_level,
                        "encryption": entry.encryption,
                        "label": 1,
                        "score": score_str,
                    })
            fh.flush()

    print(f"[apply-dctr] DONE -> {args.out}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_entries(cover_groups, method: str, payload: str) -> list[_ScoreEntry]:
    """Build the flat list of physical images to extract features for.

    One entry per physical file: cover image (1 per group) + each stego
    variant. cover_encryptions records which encryption rows to fan out
    in the predictions CSV after scoring.
    """
    entries: list[_ScoreEntry] = []
    idx = 0
    for cg in cover_groups:
        encryptions = tuple(sorted(cg.stego_paths.keys()))
        entries.append(_ScoreEntry(
            idx=idx,
            path=cg.cover_path,
            kind="cover",
            group_id=cg.group_id,
            source=cg.source,
            method=method,
            payload_level=payload,
            encryption=None,
            cover_encryptions=encryptions,
        ))
        idx += 1
        for enc, ste_path in cg.stego_paths.items():
            entries.append(_ScoreEntry(
                idx=idx,
                path=ste_path,
                kind="stego",
                group_id=cg.group_id,
                source=cg.source,
                method=method,
                payload_level=payload,
                encryption=enc,
            ))
            idx += 1
    return entries


def _hash_run(run_dir: Path) -> str:
    h = hashlib.sha256()
    manifest = run_dir / "manifests" / "raw_cover_index_real.csv"
    if manifest.exists():
        h.update(manifest.read_bytes())
    return h.hexdigest()[:16]


if __name__ == "__main__":
    main()
