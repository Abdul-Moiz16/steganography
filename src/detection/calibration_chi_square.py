"""Calibration-based chi-square steganalysis detector.

Improves on the basic DCT chi-square test by building a calibration
reference from a non-block-aligned crop of the suspect image,
recompressing it at the same JPEG quality, and comparing coefficient
histograms.

Reference
---------
- J. Fridrich, M. Goljan, and D. Hogea,
  "Steganalysis of JPEG images: breaking the F5 algorithm,"
  Proc. Information Hiding (IH), LNCS 2578, pp. 310--323, 2003.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

from src.embedding.jpeg_dct import luminance_coefficients, read_dct_jpeg


# Eight lowest-frequency AC positions (zig-zag order, excluding DC). These
# carry the strongest stego signal under JSteg/F5-style embedding because
# their dynamic range covers the small magnitudes most affected by
# coefficient-LSB modification.
_LOW_FREQUENCY_AC_POSITIONS: tuple[tuple[int, int], ...] = (
    (0, 1), (1, 0), (1, 1), (0, 2),
    (2, 0), (1, 2), (2, 1), (2, 2),
)

# Cochran's rule of thumb for chi-square applicability: only include bins
# whose expected count is at least 5. This avoids the long-tail
# instability that would otherwise dominate the statistic.
_MIN_EXPECTED_COUNT = 5.0


def calibration_chi_square_score(
    jpeg_bytes: bytes,
    *,
    jpeg_quality: int = 95,
) -> float:
    """Return the Fridrich-Goljan-Hogea calibration chi-square score.

    Implementation outline (Fridrich, Goljan & Hogea, 2003):
    1. Read the candidate's quantized luminance DCT coefficients directly
       from the JPEG bitstream.
    2. Decompress the candidate to spatial pixels, crop four pixels from
       the top-left corner to break the 8x8 block grid, and recompress
       the cropped image at the same JPEG quality factor. The
       recompressed (calibrated) JPEG's DCT histogram is an estimate of
       the cover's histogram even when the candidate is stego, because
       the recompression destroys the small embedding-induced bias on
       low-magnitude AC coefficients.
    3. Aggregate values at the eight lowest-frequency AC positions for
       both the candidate and the calibration.
    4. Build a shared-bin histogram, scale the calibration histogram to
       the candidate's total, and compute Pearson's chi-square distance
       restricting to bins with expected count >= 5 (Cochran's rule).

    The returned score is the raw chi-square distance. Larger values
    indicate stronger divergence of the candidate from cover-like
    statistics, i.e. stronger stego evidence (high score = stego).
    """
    candidate_coeffs = luminance_coefficients(read_dct_jpeg(jpeg_bytes))
    calibrated_coeffs = _calibrated_coefficients(jpeg_bytes, jpeg_quality=jpeg_quality)

    if calibrated_coeffs is None:
        return 0.0

    candidate_values = _gather_low_frequency_ac(candidate_coeffs)
    calibrated_values = _gather_low_frequency_ac(calibrated_coeffs)

    if candidate_values.size == 0 or calibrated_values.size == 0:
        return 0.0

    return _scaled_chi_square(candidate_values, calibrated_values)


def _calibrated_coefficients(
    jpeg_bytes: bytes,
    *,
    jpeg_quality: int,
) -> np.ndarray | None:
    """Decompress, crop 4 px, recompress, and return calibrated DCT coefficients."""
    image = Image.open(io.BytesIO(jpeg_bytes)).convert("L")
    pixels = np.array(image, dtype=np.uint8)

    if pixels.shape[0] <= 4 or pixels.shape[1] <= 4:
        return None

    cropped = pixels[4:, 4:]
    h_aligned = (cropped.shape[0] // 8) * 8
    w_aligned = (cropped.shape[1] // 8) * 8

    if h_aligned == 0 or w_aligned == 0:
        return None

    cropped = cropped[:h_aligned, :w_aligned]

    buffer = io.BytesIO()
    Image.fromarray(cropped, mode="L").save(buffer, format="JPEG", quality=jpeg_quality)
    return luminance_coefficients(read_dct_jpeg(buffer.getvalue()))


def _gather_low_frequency_ac(coefficients: np.ndarray) -> np.ndarray:
    """Concatenate values at the configured low-frequency AC positions."""
    parts: list[np.ndarray] = []
    for row, col in _LOW_FREQUENCY_AC_POSITIONS:
        parts.append(coefficients[:, :, row, col].ravel().astype(np.int64))

    if not parts:
        return np.empty(0, dtype=np.int64)

    return np.concatenate(parts)


def _scaled_chi_square(
    candidate_values: np.ndarray,
    calibrated_values: np.ndarray,
) -> float:
    """Pearson chi-square between candidate and scaled calibration histogram."""
    lo = int(min(candidate_values.min(), calibrated_values.min()))
    hi = int(max(candidate_values.max(), calibrated_values.max()))
    bins = np.arange(lo, hi + 2)

    candidate_hist, _ = np.histogram(candidate_values, bins=bins)
    calibrated_hist, _ = np.histogram(calibrated_values, bins=bins)

    candidate_total = float(candidate_values.size)
    calibrated_total = float(calibrated_values.size)
    if calibrated_total == 0.0:
        return 0.0

    expected = calibrated_hist.astype(np.float64) * (candidate_total / calibrated_total)

    mask = expected >= _MIN_EXPECTED_COUNT
    if not np.any(mask):
        return 0.0

    diff = candidate_hist[mask].astype(np.float64) - expected[mask]
    return float(np.sum((diff ** 2) / expected[mask]))
