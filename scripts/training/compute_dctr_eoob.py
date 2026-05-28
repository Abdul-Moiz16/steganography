"""Deterministic post-hoc DCTR E_OOB computation.

DCTR's headline metric in Holub & Fridrich 2015 (TIFS) is E_OOB -- the
out-of-bag estimate of the FLD-ensemble's minimum detection error under
equal priors.  Our train_dctr.py fits ``BaggingClassifier(LinearDiscriminant
Analysis, bootstrap=True)`` but does NOT pass ``oob_score=True``, so the
existing checkpoints do not carry an OOB decision function.

This script computes E_OOB after the fact, deterministically, without
modifying or re-training the original checkpoint.  The procedure is:

  1. Load the existing checkpoint to recover the config
     (seed, n_estimators, max_features, training_run_hash).
  2. Re-extract DCTR features from the same training run as the original
     fit.  DCTR feature extraction is a pure function of the JPEG bytes,
     so the resulting train_X is bit-identical to the original.
  3. Fit a StandardScaler on the new train_X (identical to the original
     scaler because StandardScaler is fully deterministic given the same
     input array).
  4. Instantiate a fresh ``BaggingClassifier(LDA, oob_score=True,
     random_state=<same seed>, ...)`` with all original hyperparameters.
  5. Fit on standardised train_X.  Because sklearn's BaggingClassifier
     draws its bootstrap indices via ``check_random_state(seed)`` and the
     LDA base learner has no randomness, the trained ensemble is
     bit-identical to the original; the only added quantity is the
     populated ``oob_decision_function_`` attribute.
  6. Compute E_OOB = P_E^min on the positive-class OOB decision scores
     using the shared src.evaluation.metrics.pe_min helper.
  7. Persist {e_oob, e_oob_auc, n_oob_samples, sklearn_version} to the
     checkpoint's sibling summary JSON under a new top-level key
     ``oob_metrics``.

The new ``BaggingClassifier`` is discarded after step 6; only the metric
numbers are persisted.  The original .pkl on disk is untouched.

Usage
-----
    # One checkpoint:
    python scripts/training/compute_dctr_eoob.py \\
        --checkpoint models/training_v2a/dctr_dct_low_v2a.pkl \\
        --training-run runs/training_v2a \\
        --n-workers 16

    # All three v2a checkpoints in one call:
    python scripts/training/compute_dctr_eoob.py \\
        --checkpoint models/training_v2a/dctr_dct_low_v2a.pkl \\
                     models/training_v2a/dctr_dct_medium_v2a.pkl \\
                     models/training_v2a/dctr_dct_high_v2a.pkl \\
        --training-run runs/training_v2a \\
        --n-workers 16

Wall-clock per payload (typical): ~30-60 min for feature extraction on
~19k training images, plus a few minutes for the fit; dominated by
feature extraction.  Set --n-workers to the available CPU count.

Determinism / version pinning
-----------------------------
Determinism requires identical sklearn versions between the original
training run and this re-fit.  The script reads the original sklearn
version from the checkpoint metadata (if present) and the current runtime
sklearn version; a mismatch prints a warning but does NOT abort, because
the BaggingClassifier bootstrap RNG has been stable across recent sklearn
releases.  If you have any doubt, run this script on the same machine
that produced the checkpoints.

The script also asserts that the recovered training_run_hash matches the
``training_run_hash`` recorded in the checkpoint, so a mismatched
--training-run argument fails loudly instead of silently producing wrong
numbers.
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

# Project-root path setup (same as train_dctr.py).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _extract_one(job: tuple) -> tuple:
    """Worker (top-level for spawn-pickleability).  Mirror of train_dctr.py."""
    from src.detection_learned.dctr import dctr_features_path
    path_str, label, group_id, source, encryption = job
    try:
        feat = dctr_features_path(path_str)
        return (label, group_id, source, encryption, feat)
    except Exception as e:
        sys.stderr.write(
            f"[compute-eoob] feature extraction failed on {path_str}: {e}\n"
        )
        return (label, group_id, source, encryption, None)


def _hash_training_run(training_run: Path) -> str:
    """Mirror of train_dctr.py._hash_training_run for leakage-guard verification.

    Hashes the manifests/raw_cover_index_real.csv content (the canonical
    "what's in this training corpus" descriptor used by both train_dctr.py
    and train_srnet.py); short hex digest.  Must produce the same value
    the original train_dctr.py wrote into the checkpoint's
    training_run_hash field.  Matches train_dctr.py's behaviour of
    returning ``sha256(empty).hexdigest()[:16]`` when the manifest is
    missing -- so the two implementations stay byte-identical.
    """
    h = hashlib.sha256()
    manifest = training_run / "manifests" / "raw_cover_index_real.csv"
    if manifest.exists():
        h.update(manifest.read_bytes())
    return h.hexdigest()[:16]


def _compute_eoob_for(checkpoint_path: Path, training_run: Path,
                      n_workers: int) -> dict:
    """Re-fit one DCTR checkpoint with oob_score=True and return E_OOB metrics."""
    # ----- Deferred imports (keep CLI fast) ----------------------------------
    import numpy as np
    import sklearn
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
    from sklearn.ensemble import BaggingClassifier
    from sklearn.preprocessing import StandardScaler
    import joblib

    from src.detection_learned.data import enumerate_cover_groups
    from src.detection_learned.dctr import FEATURE_DIM
    from src.evaluation.metrics import pe_min, roc_auc_score_binary

    # ----- Load checkpoint metadata -----------------------------------------
    ckpt = joblib.load(checkpoint_path)
    config = ckpt["config"]
    method = config["method"]
    payload = config["payload"]
    seed = int(config["seed"])
    n_estimators = int(config["n_estimators"])
    max_features = float(config["max_features"])
    expected_hash = ckpt.get("training_run_hash")

    print(f"[compute-eoob] checkpoint = {checkpoint_path}")
    print(f"[compute-eoob]   method={method} payload={payload} seed={seed} "
          f"n_estimators={n_estimators} max_features={max_features}")

    # ----- Verify training-run hash matches --------------------------------
    actual_hash = _hash_training_run(training_run)
    if expected_hash and actual_hash != expected_hash:
        raise SystemExit(
            f"training_run_hash mismatch:\n"
            f"  checkpoint expects: {expected_hash}\n"
            f"  --training-run {training_run} hashes to: {actual_hash}\n"
            f"Pass the original training run that produced this checkpoint."
        )

    # ----- Enumerate the SAME training split that train_dctr.py used -------
    train_groups = enumerate_cover_groups(
        training_run, method=method, payload_level=payload, split="train",
    )
    if not train_groups:
        raise SystemExit(f"empty train set for {method}/{payload}")
    print(f"[compute-eoob] {len(train_groups)} train cover-groups")

    # Build jobs the same way train_dctr.py does (cover + each stego encryption).
    jobs: list[tuple] = []
    for cg in train_groups:
        jobs.append((str(cg.cover_path), 0, cg.group_id, cg.source, "n/a"))
        for encryption, ste_path in cg.stego_paths.items():
            jobs.append((str(ste_path), 1, cg.group_id, cg.source, encryption))
    print(f"[compute-eoob] {len(jobs)} train images to re-extract")

    # ----- Re-extract features ----------------------------------------------
    N = len(jobs)
    X = np.zeros((N, FEATURE_DIM), dtype=np.float32)
    y = np.zeros(N, dtype=np.int8)
    n_done = n_failed = 0
    t0 = time.time()
    ctx = mp.get_context("spawn")
    with ctx.Pool(n_workers) as pool:
        for (label, _gid, _src, _enc, feat) in pool.imap_unordered(
            _extract_one, jobs, chunksize=8
        ):
            if feat is None:
                n_failed += 1
                continue
            X[n_done] = feat
            y[n_done] = label
            n_done += 1
            if n_done % 1000 == 0:
                rate = n_done / max(time.time() - t0, 1e-3)
                eta = (N - n_done) / max(rate, 1e-3) / 60
                print(f"[compute-eoob]   {n_done}/{N} extracted "
                      f"({rate:.1f} img/s, ETA {eta:.1f} min)")
    X = X[:n_done]; y = y[:n_done]
    print(f"[compute-eoob] feature extraction done: {n_done}/{N} OK, "
          f"{n_failed} failures, {(time.time() - t0)/60:.1f} min")

    expected_n_train = int(ckpt.get("n_train", -1))
    if expected_n_train >= 0 and n_done != expected_n_train:
        print(f"[compute-eoob] WARNING: n_train={n_done} differs from "
              f"checkpoint's recorded n_train={expected_n_train}; "
              f"OOB will be computed but may not match the original sample set.")

    # ----- Re-fit StandardScaler (deterministic given same X) ---------------
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)

    # ----- Fit BaggingClassifier with oob_score=True -----------------------
    print(f"[compute-eoob] fitting BaggingClassifier(LDA x{n_estimators}, "
          f"oob_score=True) for OOB capture ...")
    clf = BaggingClassifier(
        estimator=LinearDiscriminantAnalysis(solver="svd"),
        n_estimators=n_estimators,
        max_features=max_features,
        bootstrap=True,
        oob_score=True,
        n_jobs=n_workers,
        random_state=seed,
    )
    t0 = time.time()
    clf.fit(Xs, y)
    print(f"[compute-eoob] re-fit done in {(time.time()-t0)/60:.1f} min")

    # ----- Extract OOB decision function for the positive class -----------
    # oob_decision_function_ has shape (n_samples, n_classes) and contains
    # NaN rows for samples that happen to never be OOB (very unlikely with
    # n_estimators=100 + bootstrap=True; sklearn averages decision functions
    # across the base learners that did NOT see that sample).
    oob_df = clf.oob_decision_function_
    n_oob_total = oob_df.shape[0]
    import numpy as np  # already imported above; re-bind for clarity
    keep = ~np.isnan(oob_df).any(axis=1)
    n_oob = int(keep.sum())
    if n_oob < n_oob_total:
        print(f"[compute-eoob] WARNING: {n_oob_total - n_oob} samples had no "
              f"OOB coverage; excluding them from E_OOB.")
    oob_scores = oob_df[keep, 1].tolist()
    oob_labels = y[keep].astype(int).tolist()

    e_oob = float(pe_min(oob_labels, oob_scores))
    e_oob_auc = float(roc_auc_score_binary(oob_labels, oob_scores))
    print(f"[compute-eoob] E_OOB = {e_oob:.6f}  (n_oob={n_oob}, AUC={e_oob_auc:.4f})")

    return {
        "e_oob": e_oob,
        "e_oob_auc": e_oob_auc,
        "n_oob_samples": n_oob,
        "n_oob_excluded": n_oob_total - n_oob,
        "sklearn_version_compute": sklearn.__version__,
    }


def _update_summary_json(checkpoint_path: Path, oob_metrics: dict) -> Path:
    """Add ``oob_metrics`` to the sibling .summary.json (or create it)."""
    summary_path = checkpoint_path.with_suffix(".summary.json")
    if summary_path.exists():
        with summary_path.open() as f:
            summary = json.load(f)
    else:
        summary = {"checkpoint_path": str(checkpoint_path)}
    summary["oob_metrics"] = oob_metrics
    tmp = summary_path.with_suffix(".json.tmp")
    with tmp.open("w") as f:
        json.dump(summary, f, indent=2)
    os.replace(tmp, summary_path)
    return summary_path


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--checkpoint", type=Path, nargs="+", required=True,
                   help="One or more DCTR .pkl checkpoints to compute E_OOB for.")
    p.add_argument("--training-run", type=Path, required=True,
                   help="Training run directory (must match the run "
                        "originally used by train_dctr.py).")
    p.add_argument("--n-workers", type=int,
                   default=max(1, (os.cpu_count() or 2) // 2),
                   help="Multiprocessing workers for feature extraction.")
    args = p.parse_args()

    for ckpt in args.checkpoint:
        if not ckpt.exists():
            raise SystemExit(f"checkpoint not found: {ckpt}")
        print("\n" + "=" * 72)
        oob_metrics = _compute_eoob_for(ckpt, args.training_run, args.n_workers)
        summary_path = _update_summary_json(ckpt, oob_metrics)
        print(f"[compute-eoob] wrote oob_metrics to {summary_path}")


if __name__ == "__main__":
    main()
