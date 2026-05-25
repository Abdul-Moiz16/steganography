"""Train one DCTR classifier per (method, payload) cell.

Like train_srnet.py, this script is outside the main pipeline. DCTR
feature extraction is the slow step (~1s/image on a single CPU core);
fitting the LDA classifier on top is essentially free.

Output checkpoint contains:
  - feature mean / std (StandardScaler)
  - fitted LDA / logistic-regression classifier
  - training-run hash (leakage guard)

Usage
-----
    python scripts/training/train_dctr.py \
        --training-run runs/training_v1 \
        --method dct --payload low \
        --out models/dctr_dct_low_v1.pkl

NOTE: this is a stub. Requires the DCTR feature extractor in
src/detection_learned/dctr.py to be implemented first.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--training-run", type=Path, required=True)
    p.add_argument("--method", required=True, choices=["dct"],
                   help="DCT only -- DCTR is a JPEG-domain feature.")
    p.add_argument("--payload", required=True, choices=["low", "medium", "high"])
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--n-workers", type=int, default=8,
                   help="Multiprocessing workers for feature extraction.")
    args = p.parse_args()

    raise NotImplementedError(
        "DCTR training script is not yet implemented. Skeleton:\n"
        "  1. enumerate_samples(training_run, method='dct', payload=PAYLOAD, split='train')\n"
        "  2. Parallel feature extraction via multiprocessing.Pool on dctr_features()\n"
        "  3. Stack to (n_samples, 8000) feature matrix; same for val\n"
        "  4. Fit StandardScaler + LinearDiscriminantAnalysis (sklearn)\n"
        "  5. joblib.dump((scaler, lda, hashes, val_auc), args.out)\n"
    )


if __name__ == "__main__":
    main()
