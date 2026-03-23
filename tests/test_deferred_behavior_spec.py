from __future__ import annotations

import random
from typing import Callable

import pytest
from PIL import Image

from src.detection.statistical import (
    calibration_chi_square_score,
    chi_square_dct_score,
    chi_square_spatial_score,
    rs_analysis_score,
    sample_pairs_score,
)
from src.embedding.dct import embed_dct_lsb_jpeg
from src.embedding.encryption import (
    decrypt_payload_aes_256_cbc,
    encrypt_payload_aes_256_cbc,
)
from src.embedding.lsb import embed_lsb


def _call_or_xfail(fn: Callable, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except NotImplementedError as exc:
        pytest.xfail(f"Deferred implementation pending: {exc}")


def _sample_payload(n: int = 128, seed: int = 7) -> bytes:
    rng = random.Random(seed)
    return bytes(rng.getrandbits(8) for _ in range(n))


def _make_cover(size: tuple[int, int] = (64, 64)) -> Image.Image:
    img = Image.new("L", size)
    pix = img.load()
    for y in range(size[1]):
        for x in range(size[0]):
            pix[x, y] = (x * 3 + y * 5) % 256
    return img


def _assert_float(x: object) -> None:
    assert isinstance(x, float)
    assert x == x
    assert abs(x) != float("inf")


def test_encrypt_roundtrip_and_determinism_spec() -> None:
    payload = _sample_payload(256)
    key = b"k" * 32
    iv = b"i" * 16

    c1 = _call_or_xfail(encrypt_payload_aes_256_cbc, payload, key, iv)
    c2 = _call_or_xfail(encrypt_payload_aes_256_cbc, payload, key, iv)

    assert isinstance(c1, bytes)
    assert c1 == c2
    assert c1 != payload

    p1 = _call_or_xfail(decrypt_payload_aes_256_cbc, c1, key, iv)
    assert p1 == payload


def test_embed_lsb_contract_and_determinism_spec() -> None:
    cover = _make_cover()
    cover_before = cover.tobytes()
    payload = _sample_payload(64)

    s1 = _call_or_xfail(embed_lsb, cover, payload, 0.25)
    s2 = _call_or_xfail(embed_lsb, cover, payload, 0.25)
    s3 = _call_or_xfail(embed_lsb, cover, payload, 0.75)

    assert isinstance(s1, Image.Image)
    assert s1.size == cover.size
    assert s1.mode == cover.mode
    assert cover.tobytes() == cover_before
    assert s1.tobytes() == s2.tobytes()
    assert s1.tobytes() != s3.tobytes()


def test_embed_dct_contract_and_determinism_spec() -> None:
    payload = _sample_payload(64)

    s1 = _call_or_xfail(embed_dct_lsb_jpeg, b"jpeg-cover", payload, 0.25)
    s2 = _call_or_xfail(embed_dct_lsb_jpeg, b"jpeg-cover", payload, 0.25)
    s3 = _call_or_xfail(embed_dct_lsb_jpeg, b"jpeg-cover", payload, 0.75)

    assert isinstance(s1, bytes)
    assert s1 == s2
    assert s1 != s3


def test_statistical_detectors_return_finite_deterministic_scores_spec() -> None:
    cover = _make_cover()

    for fn in [rs_analysis_score, chi_square_spatial_score, sample_pairs_score]:
        a = _call_or_xfail(fn, cover)
        b = _call_or_xfail(fn, cover)
        _assert_float(a)
        _assert_float(b)
        assert a == b

    for fn in [chi_square_dct_score, calibration_chi_square_score]:
        a = _call_or_xfail(fn, b"jpeg-cover")
        b = _call_or_xfail(fn, b"jpeg-cover")
        _assert_float(a)
        _assert_float(b)
        assert a == b
