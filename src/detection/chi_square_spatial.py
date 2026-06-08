#Author: David Wicker and Jimena Narvaez
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


def chi_square_spatial_score(image: Image.Image) -> float:
    """Return the classical Westfeld 1999 chi-square LSB score for one
    grayscale image. Higher score = stronger stego evidence.

    Builds the pairs-of-values histogram over spatial intensity values
    (2k, 2k+1), compares the observed imbalance against the equalization
    expected under random LSB replacement. The underlying Westfeld &
    Pfitzmann (1999) test statistic is unchanged; we return
    ``-chi_stat / df`` rather than the p-value ``chi2.sf(chi_stat, df)``
    because the latter saturates to 0.0 on natural cover images whose
    chi_stat exceeds the float64 representable range -- losing rank
    information that ROC AUC depends on. The two scores are monotonic
    in each other, so ranking-based metrics (AUC, DeLong) are unaffected
    on non-degenerate inputs while the new score preserves discrimination
    on the underflow-prone tail.
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

    return -float(chi_stat) / (degrees_of_frdm - 1)
