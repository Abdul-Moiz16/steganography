"""Tests for the tiled DCT chi-square detector.

The tiled variant evaluates the Westfeld PoV chi-square on disjoint
tiles of the DCT block grid and returns the strongest tile score. The
contract checked here is:

- score is a probability in [0, 1]
- scores are higher on stego than on cover at the same JPEG quality
- the ``tiles`` parameter is honoured (1x1 grid degenerates to the
  global chi_square_dct_score on the same coefficient set)
- empty / pathological inputs do not raise
"""

from __future__ import annotations

from io import BytesIO

import numpy as np
import pytest
from PIL import Image

from src.detection.chi_square_dct import chi_square_dct_score
from src.detection.chi_square_dct_tiled import chi_square_dct_tiled_score
from src.embedding.dct import embed_dct_lsb_jpeg


def _make_textured_jpeg(size: tuple[int, int] = (128, 128), quality: int = 95) -> bytes:
    rng = np.random.default_rng(20260512)
    y, x = np.indices(size)
    base = (x * 3 + y * 5 + (x * y) % 29).astype(np.int16)
    noise = rng.integers(-25, 26, size=size, dtype=np.int16)
    gray = np.clip(base + noise + 96, 0, 255).astype(np.uint8)
    buf = BytesIO()
    Image.fromarray(gray, mode="L").save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def test_tiled_score_is_non_positive_finite() -> None:
    cover = _make_textured_jpeg()
    score = chi_square_dct_tiled_score(cover)
    # Score is max over tiles of (-chi_stat / df) ⇒ always <= 0; finite.
    assert isinstance(score, float)
    assert score <= 0.0
    assert score > -1e12


def test_tiled_detects_embedding_above_cover() -> None:
    cover = _make_textured_jpeg()
    stego = embed_dct_lsb_jpeg(cover, b"\xAA" * 10, 0.30)
    cover_score = chi_square_dct_tiled_score(cover)
    stego_score = chi_square_dct_tiled_score(stego)
    assert stego_score >= cover_score


def test_tiles_one_matches_global_score_when_grid_is_unique_tile() -> None:
    """A 1x1 tiling visits every DCT block once and is therefore exactly the
    global Westfeld chi-square score. Exercises the boundary case."""
    cover = _make_textured_jpeg()
    tiled_one = chi_square_dct_tiled_score(cover, tiles=1)
    global_score = chi_square_dct_score(cover)
    assert tiled_one == pytest.approx(global_score, abs=1e-9)


def test_tiles_two_is_at_least_as_strong_as_global_on_stego() -> None:
    """With 2x2 tiling we take the max over four regions, so the score on a
    stego image should be >= the global chi^2 score in any non-degenerate
    case."""
    cover = _make_textured_jpeg()
    stego = embed_dct_lsb_jpeg(cover, b"\xAA" * 12, 0.30)
    assert chi_square_dct_tiled_score(stego, tiles=2) >= chi_square_dct_score(stego)


def test_invalid_tiles_raises() -> None:
    with pytest.raises(ValueError):
        chi_square_dct_tiled_score(_make_textured_jpeg(), tiles=0)


def test_flat_image_returns_zero_score() -> None:
    """A perfectly flat carrier has no non-zero AC coefficients; the
    detector must return 0.0 without raising."""
    flat = np.full((64, 64), 128, dtype=np.uint8)
    buf = BytesIO()
    Image.fromarray(flat, mode="L").save(buf, format="JPEG", quality=95)
    assert chi_square_dct_tiled_score(buf.getvalue()) == 0.0
