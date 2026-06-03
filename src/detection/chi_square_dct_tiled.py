"""Tiled DCT-domain chi-square steganalysis detector.

Partition the JPEG into a coarse grid of tiles, compute the Westfeld
pairs-of-values chi-square statistic within each tile separately, and
return the strongest stego score across tiles.

This is a localised variant of :func:`chi_square_dct_score`. The
motivation is that DCT statistics are not spatially uniform across
typical photographic carriers (textured vs flat regions yield very
different PoV histograms), and even more so across diffusion-generated
carriers, which often contain unnaturally large flat regions. The
global :func:`chi_square_dct_score` mixes all blocks into a single
histogram, which can wash out localised embedding signal as well as
carrier-source heterogeneity. The tiled variant exposes both.

Reference
---------
- A. Westfeld and A. Pfitzmann,
  "Attacks on steganographic systems,"
  Proc. Information Hiding (IH), LNCS 1768, pp. 61--76, 1999.
  The per-tile statistic is the same Westfeld PoV chi-square, here
  evaluated on disjoint tile-shaped subsets of the image's DCT blocks.
"""

from __future__ import annotations

import numpy as np

from src.detection.chi_square_dct import _build_pairs, _count_ac_frequencies
from src.embedding.jpeg_dct import luminance_coefficients, read_dct_jpeg


DEFAULT_TILES = 2  # 2x2 grid → 4 tiles; coarse enough to keep PoV counts stable.


_AC_MASK_8x8: np.ndarray | None = None


def chi_square_dct_tiled_score(jpeg_bytes: bytes, *, tiles: int = DEFAULT_TILES) -> float:
    """Return the strongest tile-local Westfeld PoV chi-square score.

    The image is divided into ``tiles x tiles`` disjoint regions of
    DCT blocks. For each tile we build the PoV histogram on its
    non-zero AC coefficients (skipping DC and |c|<=1, same as the
    global detector) and compute the Westfeld 1999 chi-square test
    statistic. Per-tile score is ``-chi_stat / df`` (rank-monotonic
    with the p-value, but underflow-free); the returned score is the
    maximum across tiles. Higher score = stronger localised stego
    evidence.

    Returns 0.0 when no tile yields enough paired coefficients to
    form a valid chi-square test (e.g. an extremely flat image).
    """
    if tiles < 1:
        raise ValueError(f"tiles must be >= 1, got {tiles}")

    jpeg_struct = read_dct_jpeg(jpeg_bytes)
    dct = luminance_coefficients(jpeg_struct)  # shape (Bh, Bw, 8, 8)

    global _AC_MASK_8x8
    if _AC_MASK_8x8 is None:
        mask = np.ones((8, 8), dtype=bool)
        mask[0, 0] = False
        _AC_MASK_8x8 = mask

    bh, bw = dct.shape[:2]
    if bh == 0 or bw == 0:
        return 0.0

    best_score: float | None = None
    for ti in range(tiles):
        r0 = (bh * ti) // tiles
        r1 = (bh * (ti + 1)) // tiles
        if r0 == r1:
            continue
        for tj in range(tiles):
            c0 = (bw * tj) // tiles
            c1 = (bw * (tj + 1)) // tiles
            if c0 == c1:
                continue
            tile = dct[r0:r1, c0:c1]
            ac = tile[..., _AC_MASK_8x8].ravel()
            ac = ac[ac != 0]
            if ac.size == 0:
                continue
            frequencies = _count_ac_frequencies(ac.astype(int, copy=False))
            pairs = _build_pairs(frequencies)
            if not pairs:
                continue
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
                continue
            tile_score = -float(chi_stat) / (pair_count - 1)
            if best_score is None or tile_score > best_score:
                best_score = tile_score
    return 0.0 if best_score is None else best_score
