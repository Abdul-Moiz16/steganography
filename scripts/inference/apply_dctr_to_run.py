"""Apply trained DCTR classifiers to an existing run, AS-IS.

Mirrors apply_srnet_to_run.py but for the DCT branch:
  - Loads one or more (scaler, classifier) joblib pickles
  - Extracts DCTR features from every (cover, stego) JPEG in the test run
  - Scores via the classifier
  - Writes predictions to predictions_dctr.csv matching predictions.csv schema

NOTE: this is a stub. Requires src/detection_learned/dctr.py to be
implemented first.

Usage
-----
    python scripts/inference/apply_dctr_to_run.py \
        --run runs/prototype_full_20260513_005357_p8765 \
        --models models/dctr_dct_low_v1.pkl \
                 models/dctr_dct_medium_v1.pkl \
                 models/dctr_dct_high_v1.pkl \
        --out runs/prototype_full_20260513_005357_p8765/predictions_dctr.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--models", type=Path, nargs="+", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--n-workers", type=int, default=8)
    args = p.parse_args()

    raise NotImplementedError(
        "DCTR inference script is not yet implemented. Skeleton:\n"
        "  1. For each classifier: load (scaler, lda, hash) via joblib\n"
        "  2. Refuse if hash matches the test run (leakage guard)\n"
        "  3. enumerate_samples(run, method='dct', payload=cfg.payload, split=None)\n"
        "  4. Parallel feature extraction via multiprocessing.Pool on dctr_features()\n"
        "  5. score = lda.decision_function(scaler.transform(features))\n"
        "  6. Write row to CSV matching predictions.csv schema (detector='dctr')\n"
    )


if __name__ == "__main__":
    main()
