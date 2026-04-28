"""Calibration-based chi-square steganalysis detector.

Improves on the basic DCT chi-square test by building a calibration
reference from a non-block-aligned crop of the suspect image,
recompressing it, and comparing coefficient histograms.

Reference
---------
- J. Fridrich, M. Goljan, and D. Hogea,
  "Steganalysis of JPEG images: breaking the F5 algorithm,"
  Proc. Information Hiding (IH), LNCS 2578, pp. 310--323, 2003.
"""

from __future__ import annotations

from scipy.fft import dctn
import numpy as np
from PIL import Image
import io


def calibration_chi_square_score(jpeg_bytes: bytes, *, jpeg_quality: int = 95) -> float:
    """Return the calibration-based chi-square score for one JPEG image.

    Implementation notes:
    - Build a calibration reference by taking a non-block-aligned crop,
      recompressing it at the same quality level, and comparing the resulting
      coefficient histogram against the candidate image.
    - Keep the recompression quality aligned with the proposal's Q=95 setup.
    - Return one scalar score where larger values indicate stronger stego
      evidence.
    """
    # decompress the jpeg bytes into a pixel array
    img = Image.open(io.BytesIO(jpeg_bytes)).convert("L")  # convert to grayscale
    pixels = np.array(img, dtype=np.float64)

    h, w = pixels.shape
    # this guarantees that we can split the image into 8x8 blocks, although the images passed is 512x512 but just an extra safety measure
    h8, w8 = (h // 8) * 8, (w // 8) * 8
    pixels = pixels[:h8, :w8] - 128  # center values around 0 so each pixel is in range [-128, 127] rather than [0, 255]

    # 8x8 blocks is how jpeg stores data in
    def blockwise_dct(arr):
        H, W = arr.shape
        blocks = arr.reshape(H // 8, 8, W // 8, 8).transpose(0, 2, 1, 3)
        return dctn(blocks, type=2, norm="ortho", axes=(-2, -1))

    candidate_dct = blockwise_dct(pixels)

    # Calibration: shift block grid by 4 pixels
    # reload pixels fresh without the -128 shift so we can recrop cleanly
    img_ref = Image.open(io.BytesIO(jpeg_bytes)).convert("L")
    ref_pixels = np.array(img_ref, dtype=np.float64)

    # crop 4 pixels off the top-left corner so the block grid is now misaligned
    ref_pixels = ref_pixels[4:, 4:]

    # realign to multiples of 8 after the crop
    h2, w2 = ref_pixels.shape
    h28, w28 = (h2 // 8) * 8, (w2 // 8) * 8
    ref_pixels = ref_pixels[:h28, :w28] - 128

    calibration_dct = blockwise_dct(ref_pixels)

    # collect low-frequency AC coefficients from every block
    # these 8 coefficient slots in each block actually carry signal and are most likely to contain embedded bits
    ac_positions = [(0, 1), (1, 0), (1, 1), (0, 2),
                    (2, 0), (1, 2), (2, 1), (2, 2)]

    candidate_coeffs = []
    calibration_coeffs = []

    for (r, c) in ac_positions:
        candidate_coeffs.append(candidate_dct[:, :, r, c].ravel())
        calibration_coeffs.append(calibration_dct[:, :, r, c].ravel())

    candidate_coeffs = np.rint(np.concatenate(candidate_coeffs)).astype(int)
    calibration_coeffs = np.rint(np.concatenate(calibration_coeffs)).astype(int)

    # Build histograms over a shared value range
    lo = min(candidate_coeffs.min(), calibration_coeffs.min())
    hi = max(candidate_coeffs.max(), calibration_coeffs.max())
    bins = np.arange(lo, hi + 2)

    cand_hist, _ = np.histogram(candidate_coeffs, bins=bins)
    cal_hist,  _ = np.histogram(calibration_coeffs, bins=bins)

    # Chi-square between the two histograms (skip empty reference bins)
    mask = cal_hist > 0
    cand_hist = cand_hist[mask]
    cal_hist = cal_hist[mask]

    chi_stat = float(np.sum((cand_hist - cal_hist) ** 2 / cal_hist))
    return chi_stat
