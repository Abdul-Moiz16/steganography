"""Round-trip tests for sequential and keyed LSB embedding/decoding.

Adapted from the manual test harness in the original Main.py.
"""

from __future__ import annotations

import pytest
from PIL import Image

from src.embedding.lsb import (
    decode_lsb,
    decode_lsb_keyed,
    embed_lsb,
    embed_lsb_keyed,
)


# ---------------------------------------------------------------------------
# Fixtures (matching Main.py defaults)
# ---------------------------------------------------------------------------

MESSAGE = "this is a super secret message"
FILL_RATE = 0.50
BIT_DEPTH = 1
IMAGE_SIZE = (512, 512)


@pytest.fixture
def cover_image() -> Image.Image:
    """A deterministic grayscale test image."""
    img = Image.new("L", IMAGE_SIZE)
    pix = img.load()
    for y in range(IMAGE_SIZE[1]):
        for x in range(IMAGE_SIZE[0]):
            pix[x, y] = (x * 3 + y * 5) % 256
    return img


@pytest.fixture
def payload() -> bytes:
    return MESSAGE.encode("utf-8")


# ---------------------------------------------------------------------------
# Sequential round-trip (from Main.test_sequential)
# ---------------------------------------------------------------------------

class TestSequentialLSB:

    def test_roundtrip(self, cover_image, payload):
        stego = embed_lsb(cover_image, payload, FILL_RATE, bit_depth=BIT_DEPTH)
        decoded = decode_lsb(stego, FILL_RATE, len(payload), bit_depth=BIT_DEPTH)
        assert decoded == payload
        assert decoded.decode("utf-8") == MESSAGE

    def test_deterministic(self, cover_image, payload):
        s1 = embed_lsb(cover_image, payload, FILL_RATE)
        s2 = embed_lsb(cover_image, payload, FILL_RATE)
        assert list(s1.get_flattened_data()) == list(s2.get_flattened_data())

    def test_cover_not_mutated(self, cover_image, payload):
        original_data = list(cover_image.get_flattened_data())
        _ = embed_lsb(cover_image, payload, FILL_RATE)
        assert list(cover_image.get_flattened_data()) == original_data

    def test_stego_differs_from_cover(self, cover_image, payload):
        stego = embed_lsb(cover_image, payload, FILL_RATE)
        assert list(stego.get_flattened_data()) != list(cover_image.get_flattened_data())

    def test_output_is_grayscale_same_size(self, cover_image, payload):
        stego = embed_lsb(cover_image, payload, FILL_RATE)
        assert stego.mode == "L"
        assert stego.size == cover_image.size

    def test_capacity_exceeded_raises(self, cover_image):
        big_payload = b"x" * 999999
        with pytest.raises(ValueError, match="Payload too large"):
            embed_lsb(cover_image, big_payload, 0.25, bit_depth=1)

    def test_bit_depth_2_roundtrip(self, cover_image, payload):
        stego = embed_lsb(cover_image, payload, FILL_RATE, bit_depth=2)
        decoded = decode_lsb(stego, FILL_RATE, len(payload), bit_depth=2)
        assert decoded == payload


# ---------------------------------------------------------------------------
# Keyed round-trip (from Main.test_keyed)
# ---------------------------------------------------------------------------

class TestKeyedLSB:

    def test_roundtrip(self, cover_image, payload):
        stego = embed_lsb_keyed(cover_image, payload, FILL_RATE, bit_depth=BIT_DEPTH, key="coolKey")
        decoded = decode_lsb_keyed(stego, FILL_RATE, len(payload), bit_depth=BIT_DEPTH, key="coolKey")
        assert decoded == payload
        assert decoded.decode("utf-8") == MESSAGE

    def test_deterministic(self, cover_image, payload):
        s1 = embed_lsb_keyed(cover_image, payload, FILL_RATE, key="coolKey")
        s2 = embed_lsb_keyed(cover_image, payload, FILL_RATE, key="coolKey")
        assert list(s1.get_flattened_data()) == list(s2.get_flattened_data())

    def test_wrong_key_fails_decode(self, cover_image, payload):
        stego = embed_lsb_keyed(cover_image, payload, FILL_RATE, key="coolKey")
        wrong = decode_lsb_keyed(stego, FILL_RATE, len(payload), key="wrongKey")
        assert wrong != payload

    def test_different_keys_different_stego(self, cover_image, payload):
        s1 = embed_lsb_keyed(cover_image, payload, FILL_RATE, key="key1")
        s2 = embed_lsb_keyed(cover_image, payload, FILL_RATE, key="key2")
        assert list(s1.get_flattened_data()) != list(s2.get_flattened_data())

    def test_keyed_differs_from_sequential(self, cover_image, payload):
        seq = embed_lsb(cover_image, payload, FILL_RATE)
        keyed = embed_lsb_keyed(cover_image, payload, FILL_RATE, key="coolKey")
        assert list(seq.get_flattened_data()) != list(keyed.get_flattened_data())

    def test_bit_depth_2_roundtrip(self, cover_image, payload):
        stego = embed_lsb_keyed(cover_image, payload, FILL_RATE, bit_depth=2, key="coolKey")
        decoded = decode_lsb_keyed(stego, FILL_RATE, len(payload), bit_depth=2, key="coolKey")
        assert decoded == payload


# ---------------------------------------------------------------------------
# Fill-rate coverage (all three proposal levels)
# ---------------------------------------------------------------------------

class TestFillRates:

    @pytest.mark.parametrize("fill_rate", [0.25, 0.50, 0.75])
    def test_sequential_roundtrip_at_fill_rate(self, cover_image, payload, fill_rate):
        stego = embed_lsb(cover_image, payload, fill_rate)
        decoded = decode_lsb(stego, fill_rate, len(payload))
        assert decoded == payload

    @pytest.mark.parametrize("fill_rate", [0.25, 0.50, 0.75])
    def test_keyed_roundtrip_at_fill_rate(self, cover_image, payload, fill_rate):
        stego = embed_lsb_keyed(cover_image, payload, fill_rate, key="coolKey")
        decoded = decode_lsb_keyed(stego, fill_rate, len(payload), key="coolKey")
        assert decoded == payload
