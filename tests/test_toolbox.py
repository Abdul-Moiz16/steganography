"""Smoke + roundtrip tests for the standalone toolbox (encode / decode / analyze).

The toolbox is the single-image entry point used by the /toolbox web UI.
PNG hides a message via the pipeline's spatial LSB embedder; JPEG hides it
via the JSteg-style DCT-LSB embedder. Both paths are exercised here.
"""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from src.toolbox.analyze import analyze
from src.toolbox.decode import decode
from src.toolbox.encode import encode


def _make_png_bytes(size: tuple[int, int] = (128, 128), seed: int = 42) -> bytes:
    rng = np.random.default_rng(seed)
    pixels = rng.integers(0, 256, size=size, dtype=np.uint8)
    img = Image.fromarray(pixels, mode="L")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_jpeg_bytes(size: tuple[int, int] = (128, 128), quality: int = 95, seed: int = 123) -> bytes:
    rng = np.random.default_rng(seed)
    y, x = np.indices(size)
    base = (x * 3 + y * 5 + (x * y) % 31).astype(np.int16)
    noise = rng.integers(-20, 21, size=size, dtype=np.int16)
    gray = np.clip(base + noise + 96, 0, 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(gray, mode="L").save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


# ── PNG path (spatial LSB) ────────────────────────────────────────────────────

def test_png_encode_decode_roundtrip() -> None:
    cover = _make_png_bytes()
    msg = "Hello, stego!"
    result = encode(cover, "cover.png", msg)
    assert result.format == "png"
    assert isinstance(result.image_bytes, bytes)
    decoded = decode(result.image_bytes, "cover.png")
    assert decoded.message == msg


def test_png_encode_decode_handles_unicode() -> None:
    cover = _make_png_bytes()
    msg = "héllo — 漢字 ✓"
    result = encode(cover, "cover.png", msg)
    decoded = decode(result.image_bytes, "cover.png")
    assert decoded.message == msg


def test_png_encode_rejects_oversized_payload() -> None:
    cover = _make_png_bytes(size=(16, 16))  # 256 pixels = 32 bytes capacity
    # 36+4-byte payload won't fit at 1 bit-per-pixel
    huge_msg = "x" * 36
    with pytest.raises(ValueError, match="Payload too large"):
        encode(cover, "tiny.png", huge_msg)


def test_png_analyze_returns_three_spatial_scores() -> None:
    cover = _make_png_bytes()
    result = analyze(cover, "cover.png")
    assert result.format == "png"
    detectors = {s.detector for s in result.scores}
    assert detectors == {"Chi-Square (Spatial)", "RS Analysis", "Sample Pairs"}
    for s in result.scores:
        assert isinstance(s.score, float)


# ── JPEG path (DCT-LSB / JSteg) ───────────────────────────────────────────────

def test_jpeg_encode_decode_roundtrip() -> None:
    cover = _make_jpeg_bytes()
    msg = "hi"
    result = encode(cover, "cover.jpg", msg)
    assert result.format == "jpeg"
    decoded = decode(result.image_bytes, "cover.jpg")
    assert decoded.message == msg


def test_jpeg_analyze_returns_two_frequency_scores() -> None:
    cover = _make_jpeg_bytes()
    result = analyze(cover, "cover.jpg")
    assert result.format == "jpeg"
    detectors = {s.detector for s in result.scores}
    assert detectors == {"Chi-Square (DCT)", "Calibration Chi-Square"}
    for s in result.scores:
        assert isinstance(s.score, float)


# ── Format dispatch ───────────────────────────────────────────────────────────

def test_unsupported_extension_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported file type"):
        encode(b"\x00\x01", "cover.gif", "msg")
    with pytest.raises(ValueError, match="Unsupported file type"):
        decode(b"\x00\x01", "cover.gif")
    with pytest.raises(ValueError, match="Unsupported file type"):
        analyze(b"\x00\x01", "cover.gif")


def test_jpeg_extension_aliases() -> None:
    """``.jpg`` and ``.jpeg`` route to the same backend."""
    cover = _make_jpeg_bytes()
    for ext in (".jpg", ".jpeg"):
        result = encode(cover, f"cover{ext}", "ok")
        assert result.format == "jpeg"
