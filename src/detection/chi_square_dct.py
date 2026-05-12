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

import numpy as np
from scipy.stats import chi2

from src.embedding.jpeg_dct import luminance_coefficients, read_dct_jpeg


def chi_square_dct_score(jpeg_bytes: bytes) -> float:
    """Return the DCT-domain chi-square score for one JPEG carrier/stego.

    Implementation notes:
    - Parse quantized DCT coefficients directly from the JPEG bitstream.
    - Exclude DC coefficients and zero-valued AC coefficients (these are
      never modified by the JSteg-style embedding rule used in this study).
    - Build pairs of values that map to each other under LSB replacement,
      following Westfeld & Pfitzmann (1999): on the magnitude-LSB convention
      used by the JSteg embedder, the relevant pairs are (2k, 2k+1) for
      k >= 1 on the positive side and (-(2k+1), -2k) for k >= 1 on the
      negative side. Coefficients with |c| <= 1 are excluded because the
      embedder leaves them untouched (they would otherwise contribute a
      large natural-imbalance chi-square term that drowns out the
      embedding-induced flattening).
    - Score follows the spatial-domain detector convention: return the
      survival probability chi2.sf(chi_stat, df). A natural cover gives a
      large chi_stat -> tiny survival probability -> score near 0; a
      randomly-embedded stego image flattens the pairs -> small chi_stat
      -> survival probability near 1. Larger score = stronger stego
      evidence.
    """
    ac_values = _get_ac_coefficients(jpeg_bytes)
    frequencies = _count_ac_frequencies(ac_values)
    pairs = _build_pairs(frequencies)

    if not pairs:
        return 0.0

    chi_stat = 0.0
    pair_count = 0

    for n_lower, n_upper in pairs:
        total = n_lower + n_upper
        if total == 0:
            continue
        expected = total / 2.0
        chi_stat += ((n_lower - expected) ** 2) / expected
        pair_count += 1

    if pair_count <= 1:
        return 0.0

    return float(chi2.sf(chi_stat, df=pair_count - 1))


_AC_MASK_8x8: np.ndarray | None = None


def _get_ac_coefficients(jpeg_bytes: bytes) -> np.ndarray:
    """Read luminance AC coefficients from JPEG bytes and drop DC/zero values.

    Vectorised: a 8x8 boolean mask (DC=False, AC=True) selects the 63 AC
    positions out of every block in one indexing op; remaining non-zero
    filter is a single comparison. Bit-equivalent to the previous nested
    Python loop, ~30x faster on a typical 512x512 JPEG.
    """
    global _AC_MASK_8x8
    if _AC_MASK_8x8 is None:
        mask = np.ones((8, 8), dtype=bool)
        mask[0, 0] = False
        _AC_MASK_8x8 = mask

    jpeg_struct = read_dct_jpeg(jpeg_bytes)
    dct = luminance_coefficients(jpeg_struct)
    ac_values = dct[..., _AC_MASK_8x8].ravel()
    return ac_values[ac_values != 0].astype(int, copy=False)


def _count_ac_frequencies(ac_values: np.ndarray) -> dict[int, int]:
    """Build a {value: count} histogram via a single NumPy reduction."""
    if ac_values.size == 0:
        return {}
    unique, counts = np.unique(ac_values, return_counts=True)
    return {int(v): int(c) for v, c in zip(unique, counts)}


def _build_pairs(frequencies: dict[int, int]) -> list[tuple[int, int]]:
    """Build Westfeld pairs of coefficient values that swap under LSB embedding.

    Under the JSteg-style magnitude-LSB rule used in this study, the
    embedder skips zero-valued and unit-magnitude coefficients. The
    coefficient values that swap under random embedding are therefore
    the pairs

        (2,3), (4,5), (6,7), ...                # positive side
        (-3,-2), (-5,-4), (-7,-6), ...          # negative side

    A missing key on either side is treated as a count of zero so the
    pair is still emitted whenever at least one of its members appears.
    """
    pairs: list[tuple[int, int]] = []

    if not frequencies:
        return pairs

    pos_values = [v for v in frequencies.keys() if v > 0]
    pos_max = max(pos_values, default=0)
    for k in range(1, pos_max // 2 + 1):
        lower, upper = 2 * k, 2 * k + 1
        if lower in frequencies or upper in frequencies:
            pairs.append((frequencies.get(lower, 0), frequencies.get(upper, 0)))

    neg_values = [v for v in frequencies.keys() if v < 0]
    neg_min = min(neg_values, default=0)
    for k in range(1, abs(neg_min) // 2 + 1):
        lower, upper = -(2 * k + 1), -2 * k
        if lower in frequencies or upper in frequencies:
            pairs.append((frequencies.get(lower, 0), frequencies.get(upper, 0)))

    return pairs
