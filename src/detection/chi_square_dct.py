"""DCT-domain chi-square steganalysis detector.

Detects LSB replacement in quantised DCT coefficients of JPEG images
by testing whether the pairs-of-values histogram is more balanced than
expected for an unmodified JPEG.

Reference
---------
- A. Westfeld and A. Pfitzmann,
  "Attacks on steganographic systems,"
  Proc. Information Hiding (IH), LNCS 1768, pp. 61--76, 1999.
"""

from __future__ import annotations


def chi_square_dct_score(jpeg_bytes: bytes) -> float:
    """Return the DCT-domain chi-square score for one JPEG carrier/stego.

    Implementation notes:
    - Parse quantized DCT coefficients directly from the JPEG bitstream.
    - Exclude DC coefficients and operate on the non-zero AC coefficient value
      pairs relevant to DCT-LSB replacement.
    - Return one scalar score where larger values indicate stronger evidence
      of coefficient-LSB embedding.
    """
    raise NotImplementedError("DCT chi-square steganalysis is not implemented yet.")
