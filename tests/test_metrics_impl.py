"""Tests for newly-implemented metrics and detectors.

Covers:
- sample_pairs_score  (src/detection/sample_pairs.py)
- ssim                (src/metrics/ssim.py)
- fsim                (src/metrics/fsim.py)
- brisque_score       (src/metrics/brisque_metric.py)
"""
from __future__ import annotations

import secrets

import numpy as np
import pytest
from PIL import Image

from src.detection.sample_pairs import sample_pairs_score
from src.embedding.lsb import embed_lsb
from src.metrics.psnr import psnr
from src.metrics.ssim import ssim

try:
    from src.metrics.fsim import fsim as _fsim
    _HAS_PIQ = True
except (ImportError, ModuleNotFoundError):
    _HAS_PIQ = False

try:
    from src.metrics.brisque_metric import brisque_score as _brisque_score
    _HAS_BRISQUE = True
except (ImportError, ModuleNotFoundError):
    _HAS_BRISQUE = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _random_image(size: tuple[int, int] = (64, 64), mode: str = "L") -> Image.Image:
    rng = np.random.default_rng(42)
    arr = rng.integers(0, 256, (*size[::-1],) if mode == "L" else (*size[::-1], 3), dtype=np.uint8)
    return Image.fromarray(arr, mode=mode)


def _lsb_stego(cover: Image.Image, fill_rate: float = 0.5) -> Image.Image:
    n_pixels = cover.size[0] * cover.size[1]
    n_bytes = max(1, int(n_pixels * fill_rate) // 8)
    payload = secrets.token_bytes(n_bytes)
    return embed_lsb(cover, payload, fill_rate=fill_rate)


# ---------------------------------------------------------------------------
# Sample Pairs
# ---------------------------------------------------------------------------

class TestSamplePairs:
    def test_returns_float_in_range(self):
        img = _random_image()
        score = sample_pairs_score(img)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_clean_image_low_score(self):
        """A solid-colour image has no embedding signal — score should be 0."""
        img = Image.new("L", (64, 64), 128)
        assert sample_pairs_score(img) == 0.0

    def test_embedded_image_higher_score_than_solid_cover(self):
        """Solid-colour cover has score 0; embedding introduces pairs that raise the score."""
        cover = Image.new("L", (64, 64), 128)  # all pixels even, score = 0
        stego = _lsb_stego(cover, fill_rate=0.5)
        assert sample_pairs_score(stego) > sample_pairs_score(cover)

    def test_accepts_rgb_input(self):
        """Function should handle non-grayscale input (converted internally)."""
        img = _random_image((32, 32), mode="RGB")
        score = sample_pairs_score(img)
        assert 0.0 <= score <= 1.0

    def test_single_pixel_image(self):
        """Degenerate 1×1 image — no pairs, should return 0.0 without crashing."""
        img = Image.new("L", (1, 1), 100)
        assert sample_pairs_score(img) == 0.0

    def test_valid_at_multiple_fill_rates(self):
        """Scores must be valid floats in [0,1] at all fill rates (estimator is non-monotonic)."""
        cover = _random_image((64, 64))
        for fill_rate in (0.25, 0.50, 1.0):
            score = sample_pairs_score(_lsb_stego(cover, fill_rate=fill_rate))
            assert 0.0 <= score <= 1.0, f"fill_rate={fill_rate} gave score={score}"


# ---------------------------------------------------------------------------
# PSNR
# ---------------------------------------------------------------------------

class TestPSNR:
    def test_identical_images_returns_inf(self):
        img = _random_image()
        assert psnr(img, img) == float("inf")

    def test_lsb_stego_high_psnr(self):
        """LSB at low fill rate should produce PSNR > 40 dB."""
        cover = _random_image((64, 64))
        stego = _lsb_stego(cover, fill_rate=0.25)
        assert psnr(cover, stego) > 40.0

    def test_size_mismatch_raises(self):
        a = Image.new("L", (64, 64), 0)
        b = Image.new("L", (32, 32), 0)
        with pytest.raises(ValueError):
            psnr(a, b)

    def test_returns_float(self):
        cover = _random_image()
        stego = _lsb_stego(cover)
        assert isinstance(psnr(cover, stego), float)

    def test_higher_fill_rate_lower_psnr(self):
        cover = _random_image((64, 64))
        psnr_low  = psnr(cover, _lsb_stego(cover, fill_rate=0.25))
        psnr_high = psnr(cover, _lsb_stego(cover, fill_rate=1.0))
        assert psnr_low > psnr_high


# ---------------------------------------------------------------------------
# SSIM
# ---------------------------------------------------------------------------

class TestSSIM:
    def test_identical_images_score_one(self):
        img = _random_image()
        assert ssim(img, img) == pytest.approx(1.0, abs=1e-6)

    def test_range(self):
        cover = _random_image()
        stego = _lsb_stego(cover)
        score = ssim(cover, stego)
        assert -1.0 <= score <= 1.0

    def test_lsb_stego_near_one(self):
        """LSB embedding at low fill rate should produce SSIM > 0.99."""
        cover = _random_image((128, 128))
        stego = _lsb_stego(cover, fill_rate=0.25)
        assert ssim(cover, stego) > 0.99

    def test_size_mismatch_raises(self):
        a = Image.new("L", (64, 64), 0)
        b = Image.new("L", (32, 32), 0)
        with pytest.raises(ValueError):
            ssim(a, b)

    def test_accepts_rgb_input(self):
        """SSIM converts to grayscale internally — RGB input must work."""
        img = _random_image((64, 64), mode="RGB")
        score = ssim(img, img)
        assert score == pytest.approx(1.0, abs=1e-6)

    def test_returns_float(self):
        img = _random_image()
        assert isinstance(ssim(img, img), float)


# ---------------------------------------------------------------------------
# FSIM
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _HAS_PIQ, reason="piq/torch not installed")
class TestFSIM:
    def test_identical_images_score_one(self):
        img = _random_image()
        score = _fsim(img, img)
        assert score == pytest.approx(1.0, abs=1e-4)

    def test_range(self):
        cover = _random_image()
        stego = _lsb_stego(cover)
        score = _fsim(cover, stego)
        assert 0.0 <= score <= 1.0

    def test_lsb_stego_near_one(self):
        cover = _random_image((64, 64))
        stego = _lsb_stego(cover, fill_rate=0.25)
        assert _fsim(cover, stego) > 0.95

    def test_size_mismatch_raises(self):
        a = Image.new("L", (64, 64), 0)
        b = Image.new("L", (32, 32), 0)
        with pytest.raises(ValueError):
            _fsim(a, b)

    def test_returns_float(self):
        img = _random_image()
        assert isinstance(_fsim(img, img), float)


# ---------------------------------------------------------------------------
# BRISQUE
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _HAS_BRISQUE, reason="brisque not installed")
class TestBRISQUE:
    def test_returns_float(self):
        img = _random_image((64, 64), mode="RGB")
        score = _brisque_score(img)
        assert isinstance(score, float)

    def test_natural_image_reasonable_range(self):
        """Natural-ish images should score in a plausible BRISQUE range."""
        img = _random_image((64, 64), mode="RGB")
        score = _brisque_score(img)
        # BRISQUE range is loosely 0–100; allow wider tolerance for random noise
        assert -10.0 <= score <= 200.0
