#Author: David Wicker
"""Spatial-domain LSB steganography: embedding and decoding.

Implements sequential (row-major) and keyed (SHA-256 shuffled) LSB
replacement on single-channel 8-bit grayscale images.

Proposal alignment
------------------
- Reference: ``docs/proposals/proposal_updated_3.tex``,
  Section "Chosen Approaches -> Embedding Methods".
- The primary pipeline uses **sequential row-major** order so that
  training-free detectors (RS analysis, chi-square, Sample Pairs)
  see the expected embedding pattern.
- A **keyed** mode is provided as an optional extension; it shuffles
  pixel positions via a deterministic SHA-256 seed, which distributes
  embedding distortion more uniformly but breaks detector assumptions
  about sequential order.

References
----------
- J. Fridrich, M. Goljan, and R. Du, "Reliable detection of LSB
  steganography in color and grayscale images," IEEE Multimedia, 2001.
"""

from __future__ import annotations

import hashlib
import random

from PIL import Image


def _keyed_order(num_pixels: int, key: str) -> list[int]:
    """Deterministic shuffled pixel order derived from *key* via SHA-256."""
    key_bytes = key.encode("utf-8")
    hash_object = hashlib.sha256(key_bytes)
    hex_hash = hash_object.hexdigest()
    seed = int(hex_hash, 16)

    indices = list(range(num_pixels))
    rng = random.Random(seed)
    rng.shuffle(indices)
    return indices


# ---------------------------------------------------------------------------
# Sequential LSB (pipeline default)
# ---------------------------------------------------------------------------

def embed_lsb(
    cover_image: Image.Image,
    payload_bytes: bytes,
    fill_rate: float,
    *,
    bit_depth: int = 1,
) -> Image.Image:
    """Embed a payload with sequential row-major grayscale LSB replacement.

    This is the function called by the pipeline runner.
    """
    img = cover_image.convert("L")
    pixels = list(img.get_flattened_data())
    num_pixels = len(pixels)

    bit_chunks = []
    for byte in payload_bytes:
        bit_chunks.append(f"{byte:08b}")
    bits = "".join(bit_chunks)

    usable_pixels = int(num_pixels * fill_rate)
    capacity = usable_pixels * bit_depth

    if len(bits) > capacity:
        raise ValueError(
            f"Payload too large: {len(bits)} bits, "
            f"but capacity is {capacity} bits "
            f"({usable_pixels} pixels * {bit_depth} bit_depth at {fill_rate:.0%} fill)."
        )

    order = list(range(usable_pixels))  # sequential row-major order
    bit_index = 0

    for pixel_pos in order:
        value = pixels[pixel_pos]

        mask = ~((1 << bit_depth) - 1) & 0xFF
        value = value & mask

        for b in range(bit_depth):
            if bit_index >= len(bits):
                break
            bit = int(bits[bit_index])
            pos = bit_depth - 1 - b
            value |= bit << pos
            bit_index += 1

        pixels[pixel_pos] = value

        if bit_index >= len(bits):
            break

    img_out = Image.new("L", img.size)
    img_out.putdata(pixels)
    return img_out


def decode_lsb(
    stego_image: Image.Image,
    fill_rate: float,
    payload_length: int,
    *,
    bit_depth: int = 1,
) -> bytes:
    """Decode a payload embedded with sequential row-major LSB."""
    img = stego_image.convert("L")
    pixels = list(img.get_flattened_data())
    num_pixels = len(pixels)

    usable_pixels = int(num_pixels * fill_rate)
    order = list(range(usable_pixels))

    all_bits: list[str] = []
    total_bits_needed = payload_length * 8

    for pixel_pos in order:
        value = pixels[pixel_pos]

        for b in range(bit_depth):
            bit = (value >> (bit_depth - 1 - b)) & 1
            all_bits.append(str(bit))

        if len(all_bits) >= total_bits_needed:
            break

    all_bits = all_bits[:total_bits_needed]

    byte_list = []
    for i in range(0, len(all_bits), 8):
        chunk = all_bits[i : i + 8]
        if len(chunk) < 8:
            break
        number = int("".join(chunk), 2)
        byte_list.append(number)

    return bytes(byte_list)


# ---------------------------------------------------------------------------
# Keyed LSB (optional extension)
# ---------------------------------------------------------------------------

def embed_lsb_keyed(
    cover_image: Image.Image,
    payload_bytes: bytes,
    fill_rate: float,
    *,
    bit_depth: int = 1,
    key: str,
) -> Image.Image:
    """Embed a payload with keyed (SHA-256 shuffled) grayscale LSB replacement."""
    img = cover_image.convert("L")
    pixels = list(img.get_flattened_data())
    num_pixels = len(pixels)

    bit_chunks = []
    for byte in payload_bytes:
        bit_chunks.append(f"{byte:08b}")
    bits = "".join(bit_chunks)

    usable_pixels = int(num_pixels * fill_rate)
    capacity = usable_pixels * bit_depth

    if len(bits) > capacity:
        raise ValueError(
            f"Payload too large: {len(bits)} bits, "
            f"but capacity is {capacity} bits "
            f"({usable_pixels} pixels * {bit_depth} bit_depth at {fill_rate:.0%} fill)."
        )

    order = _keyed_order(num_pixels, key)[:usable_pixels]
    bit_index = 0

    for pixel_pos in order:
        value = pixels[pixel_pos]

        mask = ~((1 << bit_depth) - 1) & 0xFF
        value = value & mask

        for b in range(bit_depth):
            if bit_index >= len(bits):
                break
            bit = int(bits[bit_index])
            pos = bit_depth - 1 - b
            value |= bit << pos
            bit_index += 1

        pixels[pixel_pos] = value

        if bit_index >= len(bits):
            break

    img_out = Image.new("L", img.size)
    img_out.putdata(pixels)
    return img_out


def decode_lsb_keyed(
    stego_image: Image.Image,
    fill_rate: float,
    payload_length: int,
    *,
    bit_depth: int = 1,
    key: str,
) -> bytes:
    """Decode a payload embedded with keyed LSB."""
    img = stego_image.convert("L")
    pixels = list(img.get_flattened_data())
    num_pixels = len(pixels)

    usable_pixels = int(num_pixels * fill_rate)
    order = _keyed_order(num_pixels, key)[:usable_pixels]

    all_bits: list[str] = []
    total_bits_needed = payload_length * 8

    for pixel_pos in order:
        value = pixels[pixel_pos]

        for b in range(bit_depth):
            bit = (value >> (bit_depth - 1 - b)) & 1
            all_bits.append(str(bit))

        if len(all_bits) >= total_bits_needed:
            break

    all_bits = all_bits[:total_bits_needed]

    byte_list = []
    for i in range(0, len(all_bits), 8):
        chunk = all_bits[i : i + 8]
        if len(chunk) < 8:
            break
        number = int("".join(chunk), 2)
        byte_list.append(number)

    return bytes(byte_list)
