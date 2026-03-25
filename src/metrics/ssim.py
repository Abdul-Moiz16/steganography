"""Structural Similarity Index (SSIM) between a cover and stego image.

Used in the quality-control step (Section 3.4 of the proposal) to verify
that embedding does not introduce perceptually visible structural changes.

SSIM compares local luminance, contrast, and structure between two images
using a sliding window.  The index ranges from -1 to 1, where 1 means
the images are identical.  Typical LSB-embedded images produce SSIM > 0.99.

Reference
---------
- Z. Wang, A. C. Bovik, H. R. Sheikh, and E. P. Simoncelli,
  "Image quality assessment: from error visibility to structural
  similarity," IEEE Trans. Image Process., vol. 13, no. 4,
  pp. 600--612, 2004.
"""

from __future__ import annotations

import numpy as np
from PIL import Image


def ssim(cover: Image.Image, stego: Image.Image) -> float:
    """Compute SSIM between a cover and stego grayscale image.

    Parameters
    ----------
    cover : original cover image.
    stego : stego image after embedding.

    Returns
    -------
    SSIM value in [-1, 1].  Values close to 1 indicate near-identical
    perceptual quality.

    Raises
    ------
    ValueError
        If the images have different sizes.
    """
    raise NotImplementedError("SSIM is not implemented yet.")
