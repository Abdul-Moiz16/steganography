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
    raise NotImplementedError("Calibration chi-square steganalysis is not implemented yet.")
