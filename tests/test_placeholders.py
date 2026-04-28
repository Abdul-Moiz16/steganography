from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from src.detection.statistical import (
    calibration_chi_square_score,
    chi_square_dct_score,
    chi_square_spatial_score,
    rs_analysis_score,
    sample_pairs_score,
)
from src.embedding.encryption import (
    decrypt_payload_aes_256_cbc,
    encrypt_payload_aes_256_cbc,
)
from src.embedding.lsb import embed_lsb


def _make_jpeg_bytes(size: tuple[int, int] = (64, 64)) -> bytes:
    buf = BytesIO()
    Image.new("L", size, color=128).save(buf, format="JPEG", quality=95)
    return buf.getvalue()


@pytest.mark.parametrize(
    ("fn", "args", "match"),
    [
        (chi_square_dct_score, (b"jpeg-bytes",), "DCT chi-square"),
    ],
)
def test_deferred_functions_raise_not_implemented(fn, args, match: str) -> None:
    with pytest.raises(NotImplementedError, match=match):
        fn(*args)


# --- Tests for now-implemented functions ---

def test_encrypt_decrypt_roundtrip() -> None:
    ct = encrypt_payload_aes_256_cbc(b"abc", b"k" * 32, b"i" * 16)
    assert isinstance(ct, bytes)
    pt = decrypt_payload_aes_256_cbc(ct, b"k" * 32, b"i" * 16)
    assert pt == b"abc"


def test_embed_lsb_returns_image() -> None:
    cover = Image.new("L", (64, 64), color=128)
    stego = embed_lsb(cover, b"\x01\x02\x03", 0.50)
    assert isinstance(stego, Image.Image)
    assert stego.size == cover.size
    assert stego.mode == "L"


def test_chi_square_spatial_returns_float() -> None:
    img = Image.new("L", (64, 64), color=128)
    score = chi_square_spatial_score(img)
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_calibration_chi_square_returns_float() -> None:
    score = calibration_chi_square_score(_make_jpeg_bytes())
    assert isinstance(score, float)


def test_rs_analysis_returns_float() -> None:
    img = Image.new("L", (64, 64), color=128)
    score = rs_analysis_score(img)
    assert isinstance(score, float)
