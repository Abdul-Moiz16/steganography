"""Peak Signal-to-Noise Ratio (PSNR) between a cover and stego image.

Used in the quality-control step (Section 3.4 of the proposal) to rule
out trivial quality loss introduced by embedding.

PSNR is defined as:

    PSNR = 10 * log10(MAX^2 / MSE)

where MAX = 255 for 8-bit grayscale images and MSE is the mean squared
error between the cover and stego pixel arrays.

A higher PSNR indicates less distortion.  Typical LSB-embedded images
at low fill rates produce PSNR > 50 dB.

Reference
---------
- A. Hore and D. Ziou, "Image quality metrics: PSNR vs. SSIM,"
  Proc. ICPR, pp. 2366--2369, 2010.
"""

from __future__ import annotations

import numpy as np
from PIL import Image


def psnr(cover: Image.Image, stego: Image.Image) -> float:
    """Compute PSNR (dB) between a cover and stego grayscale image.

    Parameters
    ----------
    cover : original cover image.
    stego : stego image after embedding.

    Returns
    -------
    PSNR value in decibels.  Returns ``float('inf')`` if the images are
    identical (MSE == 0).

    Raises
    ------
    ValueError
        If the images have different sizes.
    """
    if cover.size != stego.size:
        raise ValueError(f"Size mismatch: {cover.size} vs {stego.size}")
    c = np.asarray(cover.convert("L"), dtype=np.float64)
    s = np.asarray(stego.convert("L"), dtype=np.float64)
    mse = np.mean((c - s) ** 2)
    if mse == 0.0:
        return float("inf")
    return 10.0 * np.log10(255.0 ** 2 / mse)
