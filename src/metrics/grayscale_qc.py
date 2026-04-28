# Main writers: Jimena and Daria

"""Grayscale quality-control checks for cover images.

Used in the quality-control screening step (Section 3.2 of the proposal)
to detect saturation failures in generated cover images before they enter
the embedding pipeline.

The proposal defines two failure modes:
  1. **Saturation** — grayscale mean is above 245 or below 10, indicating
     a near-white or near-black image that offers very little embedding
     capacity in practice.
  2. **Near-uniform** — the image has very low variance across pixel
     intensities, suggesting a flat or degenerate generation.

These checks are applied to all ML-generated covers (ml_a, ml_b).  Failed
images are regenerated with a new seed.
"""

from __future__ import annotations
from PIL import Image, ImageStat

def grayscale_mean(image: Image.Image) -> float:
    """Return the mean grayscale intensity of an image.

    Parameters
    ----------
    image : input image (will be converted to "L" if needed).

    Returns
    -------
    Mean pixel value in [0, 255].
    """
    return float(ImageStat.Stat(image.convert("L")).mean[0])

def grayscale_std(image: Image.Image) -> float:
    """Return the standard deviation of grayscale pixel intensities.

    Parameters
    ----------
    image : input image (will be converted to "L" if needed).

    Returns
    -------
    Standard deviation of pixel values.
    """
    return float(ImageStat.Stat(image.convert("L")).stddev[0])

def is_saturated(image: Image.Image, *, low: float = 10.0, high: float = 245.0) -> bool:
    """Check whether the image is saturated (near-black or near-white).

    Parameters
    ----------
    image : input image (will be converted to "L" if needed).
    low : mean intensity below this threshold is considered near-black.
    high : mean intensity above this threshold is considered near-white.

    Returns
    -------
    True if the grayscale mean falls outside [low, high].
    """
    return grayscale_mean(image) < low or grayscale_mean(image) > high 

def is_near_uniform(image: Image.Image, *, min_std: float = 5.0) -> bool:
    """Check whether the image is near-uniform (very low variance).

    Parameters
    ----------
    image : input image (will be converted to "L" if needed).
    min_std : images with std below this are considered near-uniform.

    Returns
    -------
    True if the pixel standard deviation is below *min_std*.
    """
    return grayscale_std(image)<min_std

def qc_pass(image: Image.Image) -> bool:
    """Run all grayscale quality-control checks.

    Parameters
    ----------
    image : input image (will be converted to "L" if needed).

    Returns
    -------
    True if the image passes all checks (not saturated, not near-uniform).
    """
    return not is_saturated(image) and not is_near_uniform(image)