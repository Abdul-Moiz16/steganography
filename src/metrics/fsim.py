"""Feature Similarity Index (FSIM) between a cover and stego image.

Used in the quality-control step (Section 3.4 of the proposal) alongside
PSNR and SSIM to rule out trivial quality loss from embedding.

FSIM is based on the idea that low-level features (phase congruency and
gradient magnitude) are the primary perceptual cues for image quality.
It correlates more strongly with human perception than PSNR and SSIM for
many distortion types.  Values range from 0 to 1, where 1 means perfect
structural fidelity.

Reference
---------
- L. Zhang, L. Zhang, X. Mou, and D. Zhang,
  "FSIM: A feature similarity index for image quality assessment,"
  IEEE Trans. Image Process., vol. 20, no. 8, pp. 2378--2386, 2011.
"""

from __future__ import annotations

import numpy as np
from PIL import Image


def fsim(cover: Image.Image, stego: Image.Image) -> float:
    """Compute FSIM between a cover and stego grayscale image.

    Parameters
    ----------
    cover : original cover image.
    stego : stego image after embedding.

    Returns
    -------
    FSIM value in [0, 1].  Values close to 1 indicate near-identical
    perceptual quality.

    Raises
    ------
    ValueError
        If the images have different sizes.
    """
    raise NotImplementedError("FSIM is not implemented yet.")
