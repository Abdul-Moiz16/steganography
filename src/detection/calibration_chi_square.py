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
from scipy.fft import dctn, idctn   
import numpy as np
from PIL import Image
from scipy.stats import chi2         
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
    pixels = pixels[:h8, :w8] - 128  # center values around 0 so it each pixel is in range of [-128, 127] rather than [0, 255] 

    # 8x8 blocks is how jpeg stores data in 
    def blockwise_dct(arr):
        H, W = arr.shape
        blocks = arr.reshape(H // 8, 8, W // 8, 8).transpose(0, 2, 1, 3)
        return dctn(blocks, type=2, norm="ortho", axes=(-2, -1))
  
    candidate_dct = blockwise_dct(pixels)

    # Calibration : shit block grid by 4 pixels
    # reload pixels fresh with out -128 shift to recrop cleanly

    img_ref = Image.open(io.BytesIO(jpeg_bytes)).convert("L")
    ref_pixels = np.array(img_ref, dtype=np.float64)

    # crop 4 pixels off the top-left corner so block grid is now misalligned\
    ref_pixels = ref_pixels[4:, 4:]

    # realign to multiples of 8 after crop
    h2, w2 = ref_pixels.shape
    h28, w28 = (h2 // 8) * 8, (w2 // 8) * 8
    ref_pixels = ref_pixels[:h28, :w28] - 128

    calibration_dct = blockwise_dct(ref_pixels)
