from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

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


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "dct"
EXPECTED_FIXTURE_SHA256 = {
    "cover_q95.jpg": "a1cdd92231bcadee84e6031a939237e6abfb263fc313381c14a4cf6ac9f60394",
    "chi_square_dct_scores.csv": "790588c90a7acb4002f891bf25cf63d0a660a8f49dc2520139e5e42565867537",
    "eligible_positions.csv": "237ad38a4f19a48d09dca3efa9f0463143aee00b5e0deefb65ade9f03cfb78b3",
    "matlab_jsteg_a53c.jpg": "d273c52f3058ec191bdcde763c50eb35e8fedb9321cbca8f1cddeda4dac89ac5",
    "payload_a53c.bin": "904c198ec5d08ad024c83b9c1e8b5c28ab4a6b8b2bd6ffc7e0debc65f3ce724a",
    "payload_changes.csv": "aac93cbc04dd7cebbd29cc00c6a43dc96660eb9a4e0bbe536c983e975f9ab94f",
}


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


def _changed_positions(before: np.ndarray, after: np.ndarray) -> set[tuple[int, int, int, int]]:
    return {tuple(pos) for pos in np.argwhere(before != after)}


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


def test_matlab_fixture_files_are_pinned_by_hash() -> None:
    for filename, expected_sha256 in EXPECTED_FIXTURE_SHA256.items():
        fixture_bytes = (FIXTURE_DIR / filename).read_bytes()
        assert hashlib.sha256(fixture_bytes).hexdigest() == expected_sha256


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


@pytest.mark.parametrize(
    ("size", "quality", "payload", "fill_rate"),
    [
        ((64, 64), 75, b"\x00", 0.75),
        ((80, 112), 85, b"\xff\x00", 0.75),
        ((96, 96), 95, b"\xa5\x3c", 0.50),
    ],
)
def test_dct_embedding_matches_independent_reference_across_jpeg_settings(
    size: tuple[int, int],
    quality: int,
    payload: bytes,
    fill_rate: float,
) -> None:
    cover = _make_textured_jpeg(size=size, quality=quality)
    cover_coeffs = luminance_coefficients(read_dct_jpeg(cover)).copy()
    expected_coeffs, usable_positions = _jsteg_reference_embed(
        cover_coeffs,
        payload,
        fill_rate,
    )

    stego = embed_dct_lsb_jpeg(cover, payload, fill_rate)
    actual_coeffs = luminance_coefficients(read_dct_jpeg(stego)).copy()

    payload_positions = set(usable_positions[: len(_payload_bits(payload))])
    changed_positions = _changed_positions(cover_coeffs, actual_coeffs)

    assert changed_positions <= payload_positions
    assert np.array_equal(actual_coeffs, expected_coeffs)
    assert decode_dct_lsb_jpeg(stego, len(payload), fill_rate) == payload


def test_dct_embedding_matches_matlab_jpeg_toolbox_fixture() -> None:
    cover = (FIXTURE_DIR / "cover_q95.jpg").read_bytes()
    payload = (FIXTURE_DIR / "payload_a53c.bin").read_bytes()
    matlab_stego = (FIXTURE_DIR / "matlab_jsteg_a53c.jpg").read_bytes()
    matlab_eligible = np.loadtxt(FIXTURE_DIR / "eligible_positions.csv", delimiter=",", dtype=int)
    matlab_changes = np.loadtxt(FIXTURE_DIR / "payload_changes.csv", delimiter=",", dtype=int)

    cover_coeffs = luminance_coefficients(read_dct_jpeg(cover)).copy()
    matlab_coeffs = luminance_coefficients(read_dct_jpeg(matlab_stego)).copy()
    actual_stego = embed_dct_lsb_jpeg(cover, payload, 0.50)
    actual_coeffs = luminance_coefficients(read_dct_jpeg(actual_stego)).copy()

    positions = eligible_positions_helper(cover_coeffs)
    matlab_positions = [tuple(row[:4]) for row in matlab_eligible]

    assert len(positions) == len(matlab_positions) == 223
    assert positions == matlab_positions
    assert decode_dct_lsb_jpeg(matlab_stego, len(payload), 0.50) == payload
    assert decode_dct_lsb_jpeg(actual_stego, len(payload), 0.50) == payload
    assert np.array_equal(actual_coeffs, matlab_coeffs)

    changed_prefix = []
    for block_row, block_col, u, v, _row, _col, cover_coef, stego_coef, bit in matlab_changes:
        pos = (block_row, block_col, u, v)
        changed_prefix.append((pos, int(cover_coef), int(stego_coef), int(bit)))

        assert int(cover_coeffs[pos]) == int(cover_coef)
        assert int(actual_coeffs[pos]) == int(stego_coef)
        assert abs(int(actual_coeffs[pos])) & 1 == int(bit)

    assert changed_prefix == [
        ((0, 0, 0, 1), -125, -125, 1),
        ((0, 0, 0, 2), -33, -32, 0),
        ((0, 0, 0, 3), -10, -11, 1),
        ((0, 0, 0, 4), 5, 4, 0),
        ((0, 0, 0, 5), -2, -2, 0),
        ((0, 0, 0, 6), -2, -3, 1),
        ((0, 0, 1, 0), -162, -162, 0),
        ((0, 0, 1, 1), 10, 11, 1),
        ((0, 0, 1, 2), 11, 10, 0),
        ((0, 0, 1, 4), -7, -6, 0),
        ((0, 0, 1, 5), 3, 3, 1),
        ((0, 0, 1, 6), 2, 3, 1),
        ((0, 0, 1, 7), -2, -3, 1),
        ((0, 0, 2, 0), -28, -29, 1),
        ((0, 0, 2, 3), -2, -2, 0),
        ((0, 0, 2, 5), 2, 2, 0),
    ]

    changed_positions = _changed_positions(cover_coeffs, actual_coeffs)
    expected_changed_positions = {
        tuple(row[:4])
        for row in matlab_changes
        if int(row[6]) != int(row[7])
    }
    payload_positions = {tuple(row[:4]) for row in matlab_changes}

    assert changed_positions == expected_changed_positions
    assert changed_positions <= payload_positions
    assert len(changed_positions) == 10


def test_dct_embedding_rejects_payload_just_over_fill_rate_boundary() -> None:
    cover = (FIXTURE_DIR / "cover_q95.jpg").read_bytes()
    payload = (FIXTURE_DIR / "payload_a53c.bin").read_bytes()
    cover_coeffs = luminance_coefficients(read_dct_jpeg(cover)).copy()
    positions = eligible_positions_helper(cover_coeffs)

    assert len(_payload_bits(payload)) == 16

    exact_fit_fill_rate = 16 / len(positions)
    too_small_fill_rate = 15 / len(positions)

    stego = embed_dct_lsb_jpeg(cover, payload, exact_fit_fill_rate)
    assert decode_dct_lsb_jpeg(stego, len(payload), exact_fit_fill_rate) == payload

    with pytest.raises(ValueError, match="Payload too large"):
        embed_dct_lsb_jpeg(cover, payload, too_small_fill_rate)


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
