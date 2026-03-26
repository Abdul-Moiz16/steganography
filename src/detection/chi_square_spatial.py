"""Spatial-domain chi-square steganalysis detector.

Detects LSB replacement by testing whether the pairs-of-values histogram
(2k, 2k+1) is more balanced than expected for a natural image.

Reference
---------
- A. Westfeld and A. Pfitzmann,
  "Attacks on steganographic systems,"
  Proc. Information Hiding (IH), LNCS 1768, pp. 61--76, 1999.
"""

from __future__ import annotations

import numpy as np
from PIL import Image
from scipy.stats import chi2


def chi_square_spatial_score(image: Image.Image) -> float:
    """Return the classical chi-square LSB score for one grayscale image.

    Builds the pairs-of-values histogram over spatial intensity values
    (2k, 2k+1), compares the observed imbalance against the equalization
    expected under LSB replacement, and returns a score where larger
    values mean stronger stego evidence.
    """
    pixels = np.array(image.convert("L")).flatten()

    counts = np.bincount(pixels, minlength=256)

    chi_stat = 0.0
    degrees_of_frdm = 0

    for k in range(128):
        n_2k = counts[2 * k]
        n_2k_plus_1 = counts[2 * k + 1]

        expected = (n_2k + n_2k_plus_1) / 2.0
        if expected > 0:
            chi_stat += ((n_2k - expected) ** 2) / expected
            degrees_of_frdm += 1

    if degrees_of_frdm <= 1:
        return 0.0

    # chi2.sf = 1 − chi2.cdf (survival function).
    # A stego image has equalised pairs → low chi_stat → high survival probability
    # → score close to 1.  A clean cover has unequal pairs → large chi_stat →
    # survival probability near 0.  This aligns with the convention that
    # larger score = stronger stego evidence (Westfeld & Pfitzmann, 1999).
    embedding_probability = chi2.sf(chi_stat, df=degrees_of_frdm - 1)

    return float(embedding_probability)
