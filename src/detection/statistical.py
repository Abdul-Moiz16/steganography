from __future__ import annotations

from PIL import Image


def rs_analysis_score(image: Image.Image) -> float:
    """Return an RS-analysis score for one grayscale spatial image.

    Intended implementation:
    - Follow Fridrich, Goljan, and Du [fridrich2001lsb].
    - Work on the same grayscale row-major spatial branch used by
      ``embed_lsb``.
    - Partition pixels into the group structure required by the paper, apply
      the regular/singular flipping masks, and derive one scalar detection
      score where larger values indicate stronger evidence of LSB replacement.
    """
    raise NotImplementedError("RS analysis is not implemented yet.")


def chi_square_spatial_score(image: Image.Image) -> float:
    """Return the classical chi-square LSB score for one grayscale image.

    Intended implementation:
    - Follow Westfeld and Pfitzmann [westfeld1999chi].
    - Build the pairs-of-values histogram over spatial intensity values
      ``(2k, 2k+1)``.
    - Compare the observed imbalance against the equalization expected under
      LSB replacement.
    - Return one scalar score with larger values meaning stronger stego
      evidence.
    """
    raise NotImplementedError("Spatial chi-square steganalysis is not implemented yet.")


def sample_pairs_score(image: Image.Image) -> float:
    """Return the Sample Pairs steganalysis score for one grayscale image.

    Intended implementation:
    - Follow Dumitrescu, Wu, and Wang [dumitrescu2003sp].
    - Compute the trace multiset statistics over pixel pairs in the row-major
      spatial image.
    - Derive the sample-pair estimate/statistic used to detect sequential
      LSB replacement.
    - Return one scalar score where larger values indicate stronger evidence
      of embedding.
    """
    raise NotImplementedError("Sample Pairs analysis is not implemented yet.")


def chi_square_dct_score(jpeg_bytes: bytes) -> float:
    """Return the DCT-domain chi-square score for one JPEG carrier/stego.

    Intended implementation:
    - Follow the JPEG/JSteg framing from Westfeld and Pfitzmann
      [westfeld1999chi].
    - Parse quantized DCT coefficients directly from the JPEG bitstream.
    - Exclude DC coefficients and operate on the non-zero AC coefficient value
      pairs relevant to DCT-LSB replacement.
    - Return one scalar score where larger values indicate stronger evidence
      of coefficient-LSB embedding.
    """
    raise NotImplementedError("DCT chi-square steganalysis is not implemented yet.")


def calibration_chi_square_score(jpeg_bytes: bytes, *, jpeg_quality: int = 95) -> float:
    """Return the calibration-based chi-square score for one JPEG image.

    Intended implementation:
    - Follow Fridrich, Goljan, and Hogea [fridrich2003calib].
    - Build a calibration reference by taking a non-block-aligned crop,
      recompressing it at the same quality level, and comparing the resulting
      coefficient histogram against the candidate image.
    - Keep the recompression quality aligned with the proposal's Q=95 setup.
    - Return one scalar score where larger values indicate stronger stego
      evidence.
    """
    raise NotImplementedError("Calibration chi-square steganalysis is not implemented yet.")
