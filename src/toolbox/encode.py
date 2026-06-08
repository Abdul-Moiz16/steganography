#Author: David Wicker
from __future__ import annotations

import io
import secrets
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from src.embedding.dct import dct_payload_capacity_bytes, embed_dct_lsb_jpeg
from src.embedding.lsb import embed_lsb

SUPPORTED_FORMATS = (".png", ".jpg", ".jpeg")
HEADER_BYTES = 4  # 4-byte big-endian length prefix; matches src/toolbox/decode.py.
DCT_JPEG_QUALITY = 95  # re-saves the stego at the same Q the pipeline uses.

# Target fill rates for the demo. Real user messages are tiny (kilobits at
# most) and would touch < 1% of the LSB plane -- far below the detection
# threshold of the classical detectors in this study. We pad the embedded
# payload with random bytes so the demo runs at full saturation: every
# eligible LSB / DCT coefficient is touched. The 4-byte length header in
# the embedded payload lets the decoder return only the user's message,
# so the padding is invisible to the user but present to the detector.
#
# Full saturation also makes chi-square scores image-size-invariant:
# under random-LSB null, chi_stat ~ df, so -chi_stat/(df-1) ~ -1
# regardless of cover dimensions. Partial fill leaves natural-histogram
# imbalance untouched in the unembedded regions, which dominates chi_stat
# and scales with image size -- bad for a user-facing readout.
DEMO_FILL_RATE_PNG = 1.0
DEMO_FILL_RATE_JPEG = 1.0

@dataclass
class StegOutput:
    image_bytes: bytes
    format: str


def encode(image_bytes: bytes, filename: str, message: str) -> StegOutput:
    # for png we use lsb spatial embedding and for jpg dct embedding
    extension = _get_extension(filename)
    payload = _build_payload(message)

    if extension == ".png":
        return _encode_png(image_bytes, payload)
    else:
        return _encode_jpeg(image_bytes, payload)

def _encode_png(image_bytes: bytes, payload: bytes) -> StegOutput:
    """Spatial LSB embedding via src.embedding.lsb.embed_lsb.

    Pads the payload with random bytes to reach DEMO_FILL_RATE_PNG so
    classical detectors can see the embedding during demos; the 4-byte
    length header in ``payload`` keeps decode message-only.
    """
    image = Image.open(io.BytesIO(image_bytes))
    total_pixels = image.width * image.height
    target_bytes = max(len(payload), int(total_pixels * DEMO_FILL_RATE_PNG / 8))
    if target_bytes > total_pixels // 8:
        target_bytes = total_pixels // 8  # never exceed cover capacity
    padded = _pad_with_random(payload, target_bytes)
    fill_rate = _compute_fill_rate(len(padded), total_pixels)
    stego = embed_lsb(image, padded, fill_rate)
    buf = io.BytesIO()
    stego.save(buf, format="PNG")
    return StegOutput(image_bytes=buf.getvalue(), format="png")


def _encode_jpeg(image_bytes: bytes, payload: bytes) -> StegOutput:
    """JSteg-style DCT-LSB embedding via src.embedding.dct.embed_dct_lsb_jpeg.

    Pads the payload with random bytes to reach DEMO_FILL_RATE_JPEG of the
    eligible AC-coefficient pool, so the frequency-branch detectors can
    see the embedding during demos. The 4-byte length header in ``payload``
    means the decoder still returns only the user's message.
    """
    capacity_full = dct_payload_capacity_bytes(image_bytes, fill_rate=1.0)
    if len(payload) > capacity_full:
        raise ValueError(
            f"Payload too large for JPEG cover: needs {len(payload)} bytes, "
            f"DCT capacity is {capacity_full} bytes at 100% fill."
        )
    target_bytes = max(len(payload), int(capacity_full * DEMO_FILL_RATE_JPEG))
    target_bytes = min(target_bytes, capacity_full)
    padded = _pad_with_random(payload, target_bytes)
    stego_bytes = embed_dct_lsb_jpeg(
        image_bytes, padded, fill_rate=1.0, jpeg_quality=DCT_JPEG_QUALITY,
    )
    return StegOutput(image_bytes=stego_bytes, format="jpeg")


def _pad_with_random(payload: bytes, target_bytes: int) -> bytes:
    """Append cryptographically-random bytes so ``len(result) == target_bytes``.

    No-op when ``target_bytes <= len(payload)``. The random padding lives
    after the user's message; the decoder reads the length header and
    returns only the message bytes, so the padding is invisible.
    """
    if target_bytes <= len(payload):
        return payload
    return payload + secrets.token_bytes(target_bytes - len(payload))

def _compute_fill_rate(payload_bytes: int, total_pixels: int, bit_depth: int = 1) -> float: # returns fill rate needed to fit payload in image
    bits_needed = payload_bytes * 8
    bits_available = total_pixels * bit_depth
    if bits_needed > bits_available:
        raise ValueError(
            f"Payload too large: needs {bits_needed} bits but image only holds {bits_available}."
        )
    return bits_needed / bits_available


def _build_payload(message: str) -> bytes: # appends 4 byte header to message in order to decode
    body = message.encode("utf-8")
    return len(body).to_bytes(4, "big") + body


def _get_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported file type: '{ext}'. Use PNG or JPEG.")
    return ext
