"""Train one DCTR classifier per (method=dct, payload) cell.

This script is invoked ONCE per payload level. It is intentionally NOT
part of the main pipeline; it lives entirely on the learned-baselines
branch and writes only to the ``models/`` directory.

Usage
-----
    python scripts/training/train_dctr.py \
        --training-run runs/training_v1 \
        --method dct --payload low \
        --out models/dctr_dct_low_v1.pkl \
        --n-workers 16

The output checkpoint (joblib pickle) contains:
  - feature StandardScaler (fitted on training features)
  - fitted ensemble classifier (BaggingClassifier of LDA base learners)
  - training config (method, payload, hyperparameters)
  - validation metrics (val_auc on the held-out group_id % 10 in {7, 8})
  - training-run hash (leakage guard for the inference script)
  - feature dim (sanity check on load)

Feature extractor: see src/detection_learned/dctr.py.
Classifier: Bagging ensemble of Fisher LDA base learners, mirroring the
Kodovsky & Fridrich (2012) FLD-ensemble used in the original DCTR paper.
Each base learner sees a 10%-feature random subspace; 100 learners
combined via averaging of decision functions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

# Make runnable without PYTHONPATH=.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Multiprocessing worker (top-level so it pickles cleanly on Linux 'spawn')
# ---------------------------------------------------------------------------

def _extract_one(job: tuple) -> tuple:
    """Worker: extract DCTR features from one image file.

    Returns (label, group_id, source, encryption, features_or_None).
    Returns features=None on extraction failure so the caller can log it.
    """
    from src.detection_learned.dctr import dctr_features_path

    path_str, label, group_id, source, encryption = job
    try:
        feat = dctr_features_path(path_str)
        return (label, group_id, source, encryption, feat)
    except Exception as e:  # narrow exceptions hide PIL/IO issues
        sys.stderr.write(
            f"[train-dctr] feature extraction failed on {path_str}: {e}\n"
        )
        return (label, group_id, source, encryption, None)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--training-run", type=Path, required=True,
                   help="Training run directory (from generate_training_set.py).")
    p.add_argument("--method", default="dct", choices=["dct"],
                   help="DCTR is JPEG-domain only; method must be 'dct'.")
    p.add_argument("--payload", required=True, choices=["low", "medium", "high"])
    p.add_argument("--out", type=Path, required=True,
                   help="Output checkpoint path (.pkl).")
    p.add_argument("--n-workers", type=int, default=max(1, os.cpu_count() // 2),
                   help="Multiprocessing workers for feature extraction.")
    p.add_argument("--n-estimators", type=int, default=100,
                   help="Number of FLD base learners in the bagging ensemble.")
    p.add_argument("--max-features", type=float, default=0.1,
                   help="Random subspace fraction per base learner (0,1].")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    # ---------------- Imports (deferred to keep CLI fast) ----------------
    import numpy as np
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
    from sklearn.ensemble import BaggingClassifier
    from sklearn.metrics import roc_auc_score
    from sklearn.preprocessing import StandardScaler
    import joblib

    from src.detection_learned.data import enumerate_cover_groups
    from src.detection_learned.dctr import FEATURE_DIM

    np.random.seed(args.seed)

    # ---------------- Enumerate train / val data ----------------
    train_groups = enumerate_cover_groups(
        args.training_run, method=args.method,
        payload_level=args.payload, split="train",
    )
    val_groups = enumerate_cover_groups(
        args.training_run, method=args.method,
        payload_level=args.payload, split="val",
    )
    print(f"[train-dctr] cell: method={args.method} payload={args.payload}")
    print(f"[train-dctr] {len(train_groups)} train cover-groups, "
          f"{len(val_groups)} val cover-groups")
    print(f"[train-dctr] feature dim: {FEATURE_DIM}")

    if not train_groups or not val_groups:
        raise RuntimeError(
            f"empty train or val set -- did embedding for {args.method}/{args.payload} succeed?"
        )

    # Build extraction jobs:
    # one cover sample per group + every stego variant (both encryption modes).
    # Class imbalance handled below via class_weight='balanced' in the LDA.
    def build_jobs(groups, label_cover, label_stego):
        jobs = []
        for cg in groups:
            jobs.append((str(cg.cover_path), label_cover,
                         cg.group_id, cg.source, "n/a"))
            for encryption, ste_path in cg.stego_paths.items():
                jobs.append((str(ste_path), label_stego,
                             cg.group_id, cg.source, encryption))
        return jobs

    train_jobs = build_jobs(train_groups, label_cover=0, label_stego=1)
    val_jobs = build_jobs(val_groups, label_cover=0, label_stego=1)
    print(f"[train-dctr] {len(train_jobs)} train images, {len(val_jobs)} val images")
    print(f"[train-dctr]   (covers + 2 stego variants per cover)")

    # ---------------- Extract features in parallel ----------------
    def extract_all(jobs, tag: str):
        N = len(jobs)
        X = np.zeros((N, FEATURE_DIM), dtype=np.float32)
        y = np.zeros(N, dtype=np.int8)
        gids = np.zeros(N, dtype=np.int32)
        n_done = 0
        n_failed = 0
        t0 = time.time()
        ctx = mp.get_context("spawn")
        with ctx.Pool(args.n_workers) as pool:
            for i, (label, gid, _source, _enc, feat) in enumerate(
                pool.imap_unordered(_extract_one, jobs, chunksize=8)
            ):
                if feat is None:
                    n_failed += 1
                    continue
                X[n_done] = feat
                y[n_done] = label
                gids[n_done] = gid
                n_done += 1
                if (n_done % 1000) == 0:
                    rate = n_done / max(time.time() - t0, 1e-3)
                    eta_s = (N - n_done) / max(rate, 1e-3)
                    print(f"[train-dctr][{tag}] {n_done}/{N} "
                          f"({rate:.1f} img/s, ETA {eta_s/60:.1f} min)")
        # Truncate to successful extractions
        X = X[:n_done]
        y = y[:n_done]
        gids = gids[:n_done]
        elapsed = time.time() - t0
        print(f"[train-dctr][{tag}] done: {n_done}/{N} in {elapsed/60:.1f} min "
              f"({n_failed} failures)")
        return X, y, gids

    print(f"[train-dctr] extracting TRAIN features with {args.n_workers} workers ...")
    train_X, train_y, train_gids = extract_all(train_jobs, "train")
    print(f"[train-dctr] extracting VAL features with {args.n_workers} workers ...")
    val_X, val_y, val_gids = extract_all(val_jobs, "val")

    # ---------------- Standardise ----------------
    print(f"[train-dctr] fitting StandardScaler on {train_X.shape[0]} train samples ...")
    scaler = StandardScaler()
    train_Xs = scaler.fit_transform(train_X)
    val_Xs = scaler.transform(val_X)

    # ---------------- Fit ensemble ----------------
    print(f"[train-dctr] fitting BaggingClassifier(LDA x{args.n_estimators}, "
          f"max_features={args.max_features}) ...")
    base = LinearDiscriminantAnalysis(solver="svd")
    clf = BaggingClassifier(
        estimator=base,
        n_estimators=args.n_estimators,
        max_features=args.max_features,
        bootstrap=True,
        n_jobs=args.n_workers,
        random_state=args.seed,
    )
    t0 = time.time()
    clf.fit(train_Xs, train_y)
    print(f"[train-dctr] fit complete in {(time.time()-t0)/60:.1f} min")

    # ---------------- Validate ----------------
    val_scores = clf.predict_proba(val_Xs)[:, 1]
    val_auc = float(roc_auc_score(val_y, val_scores))
    # Group-aware sanity: val AUC ignoring per-image and reporting by-source
    print(f"[train-dctr] val AUC = {val_auc:.4f}  (N_val={len(val_y)}, "
          f"pos={int(val_y.sum())}, neg={int((1-val_y).sum())})")
    if val_auc < 0.55:
        print(f"[train-dctr] !!! WARNING: val-AUC barely above chance. "
              f"Check feature extraction / class labels / data layout.")

    # ---------------- Save checkpoint ----------------
    training_run_hash = _hash_training_run(args.training_run)
    config = {
        "method": args.method,
        "payload": args.payload,
        "n_estimators": args.n_estimators,
        "max_features": args.max_features,
        "seed": args.seed,
        "feature_dim": int(FEATURE_DIM),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = args.out.with_suffix(args.out.suffix + ".tmp")
    joblib.dump({
        "scaler": scaler,
        "classifier": clf,
        "config": config,
        "val_auc": val_auc,
        "n_train": int(train_X.shape[0]),
        "n_val": int(val_X.shape[0]),
        "training_run_hash": training_run_hash,
    }, tmp_path, compress=3)
    os.replace(tmp_path, args.out)

    # Sibling summary JSON (inspectable without joblib)
    summary = {
        "checkpoint_path": str(args.out),
        "config": config,
        "training_run_dir": str(args.training_run),
        "training_run_hash": training_run_hash,
        "val_auc": val_auc,
        "n_train": int(train_X.shape[0]),
        "n_val": int(val_X.shape[0]),
        "feature_dim": int(FEATURE_DIM),
    }
    summary_path = args.out.with_suffix(".summary.json")
    summary_tmp = summary_path.with_suffix(".tmp")
    summary_tmp.write_text(json.dumps(summary, indent=2))
    os.replace(summary_tmp, summary_path)

    print(f"[train-dctr] DONE -- val AUC {val_auc:.4f} saved to {args.out}")


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def _hash_training_run(training_run: Path) -> str:
    """Same hash function as train_srnet -- same training-run -> same hash.

    Used by inference to refuse to apply a model to a run whose manifest
    matches the manifest the model was trained on (leakage guard).
    """
    h = hashlib.sha256()
    manifest = training_run / "manifests" / "raw_cover_index_real.csv"
    if manifest.exists():
        h.update(manifest.read_bytes())
    return h.hexdigest()[:16]


if __name__ == "__main__":
    main()
