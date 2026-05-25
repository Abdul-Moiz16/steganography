"""DCTR -- Low-Complexity Features for JPEG Steganalysis (Holub & Fridrich 2015).

Reference
---------
V. Holub and J. Fridrich,
"Low-complexity features for JPEG steganalysis using undecimated DCT,"
IEEE Trans. Inf. Forensics Security, vol. 10, no. 2, pp. 219-228, 2015.

DCTR computes 8,000-dim histograms of decompressed-DCT-coefficient
differences. It is a fixed feature extractor (no learning) combined
with a linear classifier (FLD / LDA in the original paper; logistic
regression or a small EnsembleClassifier work just as well in
practice). We use scikit-learn's LDA for the classifier here to avoid
the dependency on MATLAB-style ensemble classifiers.

This file holds the FEATURE EXTRACTOR. The classifier is fitted in
scripts/training/train_dctr.py and saved as a joblib artefact next to
the feature mean/std normaliser.

NOTE: this is currently a stub. The DCTR feature extractor is ~200
lines once written; we leave the implementation to the next commit on
this branch. Two acceptable options:

  1. Port the reference MATLAB implementation
     (http://dde.binghamton.edu/download/feature_extractors/) to numpy.
     This is the textbook reference but the published code is GPL.

  2. Use the existing pyjpegio-based DCTR implementation from the
     PyTorch-Steganalysis-Toolbox or similar open-source project,
     vendored under src/detection_learned/_third_party/dctr/.

Either way, the public surface is:

    def dctr_features(jpeg_bytes: bytes) -> np.ndarray
        '''Return a (8000,) float32 feature vector for one JPEG image.'''
"""
from __future__ import annotations

import numpy as np


def dctr_features(jpeg_bytes: bytes) -> np.ndarray:
    """Extract the 8,000-dim DCTR feature vector for one JPEG image.

    Parameters
    ----------
    jpeg_bytes : bytes
        Raw JPEG file bytes (Q=95 in our pipeline).

    Returns
    -------
    ndarray of shape (8000,), dtype float32
        Co-occurrence histogram features as defined in
        Holub & Fridrich 2015 (sections 3.2-3.4).
    """
    raise NotImplementedError(
        "DCTR feature extractor is not yet implemented on this branch. "
        "Implement either by porting the reference MATLAB or by vendoring "
        "an existing GPL-compatible Python port. See module docstring."
    )
