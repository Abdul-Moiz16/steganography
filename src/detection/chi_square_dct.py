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
    - Exclude DC coefficients and operate on the non-zero AC coefficient value
      pairs relevant to DCT-LSB replacement.
    - Return one scalar score where larger values indicate stronger evidence
      of coefficient-LSB embedding.
    """
    ac_values = _get_ac_coefficients(jpeg_bytes)
    frequencies = _count_ac_frequencies(ac_values)
    pairs = _build_pairs(frequencies)

    if not pairs:
        return 0.0

    chi2_stat = 0.0

    for n_lower, n_upper in pairs:
        total = n_lower + n_upper

        if total == 0:
            continue

        difference = n_lower - n_upper
        chi2_stat += (difference ** 2) / total

    df = len(pairs)
    p_value = chi2.sf(chi2_stat, df)

    return float(1.0 - p_value)


def _get_ac_coefficients(jpeg_bytes: bytes) -> np.ndarray:
    """Read luminance AC coefficients from JPEG bytes and drop DC/zero values."""
    jpeg_struct = read_dct_jpeg(jpeg_bytes)
    dct = luminance_coefficients(jpeg_struct)

    ac_values = []

    for block_row in range(dct.shape[0]):
        for block_col in range(dct.shape[1]):
            block = dct[block_row, block_col]
            for row in range(8):
                for col in range(8):
                    if row == 0 and col == 0:
                        continue

                    value = int(block[row, col])
                    if value != 0:
                        ac_values.append(value)

    return np.array(ac_values, dtype=int)


def _count_ac_frequencies(ac_values: np.ndarray) -> dict[int, int]:
    frequencies = {}

    for value in ac_values:
        if value not in frequencies:
            frequencies[value] = 0
        frequencies[value] += 1

    return frequencies


def _build_pairs(frequencies: dict[int, int]) -> list[tuple[int, int]]:
    pairs = []

    all_values = sorted(frequencies.keys())
    i = 0

    while i < len(all_values):
        value = all_values[i]
        next_value = value + 1

        if next_value in frequencies:
            pairs.append((frequencies[value], frequencies[next_value]))
            i += 2
        else:
            i += 1

    return pairs
