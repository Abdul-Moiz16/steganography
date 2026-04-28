from __future__ import annotations

from io import BytesIO

import numpy as np
import pytest
from PIL import Image

from src.embedding.dct import (
    decode_dct_lsb_jpeg,
    eligible_positions_helper,
    embed_dct_lsb_jpeg,
)
from src.embedding.jpeg_dct import (
    LIBJPEG_BACKEND,
    ensure_libjpeg_backend,
    luminance_coefficients,
    read_dct_jpeg,
    write_dct_jpeg,
)


def _make_textured_jpeg(size: tuple[int, int] = (96, 96), *, quality: int = 95) -> bytes:
    """Create a deterministic grayscale JPEG with enough non-zero AC coefficients."""
    rng = np.random.default_rng(20260428)
    y, x = np.indices(size)
    base = (x * 5 + y * 7 + (x * y) % 29).astype(np.int16)
    noise = rng.integers(-18, 19, size=size, dtype=np.int16)
    pixels = np.clip(base + noise + 96, 0, 255).astype(np.uint8)

    buf = BytesIO()
    Image.fromarray(pixels, mode="L").save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _payload_bits(payload: bytes) -> np.ndarray:
    return np.unpackbits(np.frombuffer(payload, dtype=np.uint8))


def _jsteg_reference_embed(
    cover_coeffs: np.ndarray,
    payload: bytes,
    fill_rate: float,
) -> tuple[np.ndarray, list[tuple[int, int, int, int]]]:
    """Independent JSteg-style reference from Westfeld/Pfitzmann's rule.

    The reference walks non-zero, non-abs(1) AC coefficients in block row-major
    order, skips DC coefficients, and replaces the absolute-value LSB while
    preserving sign. It deliberately does not call production embedding code.
    """
    reference = cover_coeffs.copy()
    positions = eligible_positions_helper(cover_coeffs)
    usable = positions[: int(len(positions) * fill_rate)]
    bits = _payload_bits(payload)

    if len(bits) > len(usable):
        raise ValueError("payload too large for reference fixture")

    for pos, bit in zip(usable, bits):
        coef = int(reference[pos])
        if coef > 0:
            reference[pos] = (coef & ~1) | int(bit)
        else:
            reference[pos] = -((abs(coef) & ~1) | int(bit))

    return reference, usable


def test_jpeglib_uses_pinned_libjpeg_6b_backend() -> None:
    assert ensure_libjpeg_backend() == LIBJPEG_BACKEND == "6b"


def test_reference_fixture_has_stable_eligible_position_order() -> None:
    coeffs = luminance_coefficients(read_dct_jpeg(_make_textured_jpeg())).copy()
    positions = eligible_positions_helper(coeffs)

    expected_prefix = [
        ((0, 0, 0, 1), -125),
        ((0, 0, 0, 2), -33),
        ((0, 0, 0, 3), -10),
        ((0, 0, 0, 4), 5),
        ((0, 0, 0, 5), -2),
        ((0, 0, 0, 6), -2),
        ((0, 0, 1, 0), -162),
        ((0, 0, 1, 1), 10),
        ((0, 0, 1, 2), 11),
        ((0, 0, 1, 4), -7),
        ((0, 0, 1, 5), 3),
        ((0, 0, 1, 6), 2),
        ((0, 0, 1, 7), -2),
        ((0, 0, 2, 0), -28),
        ((0, 0, 2, 3), -2),
        ((0, 0, 2, 5), 2),
    ]

    assert len(positions) == 223
    assert [(pos, int(coeffs[pos])) for pos in positions[:16]] == expected_prefix


def test_jpeglib_read_write_preserves_quantized_dct_coefficients() -> None:
    jpeg_bytes = _make_textured_jpeg()
    jpeg_struct = read_dct_jpeg(jpeg_bytes)

    y_before = luminance_coefficients(jpeg_struct).copy()
    qt_before = jpeg_struct.qt.copy()

    rewritten = write_dct_jpeg(jpeg_struct)
    reread = read_dct_jpeg(rewritten)

    assert np.array_equal(luminance_coefficients(reread), y_before)
    assert np.array_equal(reread.qt, qt_before)


def test_jpeglib_targeted_coefficient_edit_survives_write_roundtrip() -> None:
    jpeg_struct = read_dct_jpeg(_make_textured_jpeg())
    coeffs = luminance_coefficients(jpeg_struct)
    edited = coeffs.copy()

    pos = eligible_positions_helper(coeffs)[0]
    original = int(coeffs[pos])
    replacement = original + 2 if original > 0 else original - 2
    coeffs[pos] = replacement

    reread = read_dct_jpeg(write_dct_jpeg(jpeg_struct))

    edited[pos] = replacement
    assert np.array_equal(luminance_coefficients(reread), edited)


def test_dct_embedding_sets_payload_bits_only_in_expected_prefix() -> None:
    cover = _make_textured_jpeg()
    payload = b"\xa5\x3c"
    fill_rate = 0.50

    cover_coeffs = luminance_coefficients(read_dct_jpeg(cover)).copy()
    positions = eligible_positions_helper(cover_coeffs)
    payload_bits = _payload_bits(payload)
    assert len(positions) * fill_rate >= len(payload_bits)

    stego = embed_dct_lsb_jpeg(cover, payload, fill_rate)
    stego_coeffs = luminance_coefficients(read_dct_jpeg(stego))

    payload_positions = positions[: len(payload_bits)]
    untouched_positions = positions[len(payload_bits):]

    for pos, bit in zip(payload_positions, payload_bits):
        assert abs(int(stego_coeffs[pos])) & 1 == int(bit)
        assert abs(int(stego_coeffs[pos])) != 0
        assert np.sign(stego_coeffs[pos]) == np.sign(cover_coeffs[pos])

    changed_positions = {
        pos for pos in payload_positions if int(stego_coeffs[pos]) != int(cover_coeffs[pos])
    }
    for pos in untouched_positions:
        assert int(stego_coeffs[pos]) == int(cover_coeffs[pos])

    assert changed_positions


def test_dct_embedding_matches_independent_jsteg_reference_coefficients() -> None:
    cover = _make_textured_jpeg()
    payload = b"\xa5\x3c"
    fill_rate = 0.50

    cover_coeffs = luminance_coefficients(read_dct_jpeg(cover)).copy()
    expected_coeffs, _usable = _jsteg_reference_embed(cover_coeffs, payload, fill_rate)

    stego = embed_dct_lsb_jpeg(cover, payload, fill_rate)
    actual_coeffs = luminance_coefficients(read_dct_jpeg(stego)).copy()

    expected_changed_prefix = [
        ((0, 0, 0, 2), -33, -32),
        ((0, 0, 0, 3), -10, -11),
        ((0, 0, 0, 4), 5, 4),
        ((0, 0, 0, 6), -2, -3),
        ((0, 0, 1, 1), 10, 11),
        ((0, 0, 1, 2), 11, 10),
        ((0, 0, 1, 4), -7, -6),
        ((0, 0, 1, 6), 2, 3),
        ((0, 0, 1, 7), -2, -3),
        ((0, 0, 2, 0), -28, -29),
    ]
    actual_changed_prefix = [
        (pos, int(cover_coeffs[pos]), int(actual_coeffs[pos]))
        for pos in eligible_positions_helper(cover_coeffs)[: len(_payload_bits(payload))]
        if int(cover_coeffs[pos]) != int(actual_coeffs[pos])
    ]

    assert actual_changed_prefix == expected_changed_prefix
    assert np.array_equal(actual_coeffs, expected_coeffs)


def test_dct_embed_decode_roundtrip_is_deterministic() -> None:
    cover = _make_textured_jpeg()
    payload = b"paper-check"

    stego_a = embed_dct_lsb_jpeg(cover, payload, 0.75)
    stego_b = embed_dct_lsb_jpeg(cover, payload, 0.75)

    assert stego_a == stego_b
    assert decode_dct_lsb_jpeg(stego_a, len(payload), 0.75) == payload


def test_dct_embedding_rejects_payload_that_exceeds_fill_rate_capacity() -> None:
    cover = _make_textured_jpeg(size=(32, 32))
    payload = bytes(range(64))

    with pytest.raises(ValueError, match="Payload too large"):
        embed_dct_lsb_jpeg(cover, payload, 0.01)
