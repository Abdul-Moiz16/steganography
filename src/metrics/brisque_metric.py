# Main worker: Daria
# Contributor: David (Template)

"""Blind/Referenceless Image Spatial Quality Evaluator (BRISQUE).

BRISQUE is a no-reference image quality metric that operates in the spatial
domain.  It models the statistics of locally normalised luminance
coefficients and compares them against a learned model of natural scene
statistics.

Note: in the proposal (Section 3.2) we considered BRISQUE for quality-control
screening of ML-generated covers, but concluded it is unreliable for
AI-generated content (see Li et al., AIGIQA-20K).  It is included here
for completeness and optional exploratory analysis.

References
----------
- A. Mittal, A. K. Moorthy, and A. C. Bovik,
  "No-reference image quality assessment in the spatial domain,"
  IEEE Trans. Image Process., vol. 21, no. 12, pp. 4695--4708, 2012.
- Y. Li et al., "AIGIQA-20K: A large database for AI-generated image
  quality assessment," arXiv:2404.03407, 2024.
"""

from __future__ import annotations
from PIL import Image
import numpy as np
from brisque import BRISQUE
# reference: https://pypi.org/project/brisque/

def brisque_score(image: Image.Image) -> float:
    """Compute the BRISQUE score for a single grayscale image.

    Parameters
    ----------
    image : input image (should be given in RGB as it will be converted to grayscale).

    Returns
    -------
    BRISQUE score.  Lower values indicate better perceptual quality
    (typical natural images score 0-50).
    """
    img = np.array(image)
    obj = BRISQUE(url=False)
    score = obj.score(img)
    return score
