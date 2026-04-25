from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from src.embedding.lsb import embed_lsb

SUPPORTED_FORMATS = (".png", ".jpg", ".jpeg")

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
    image = Image.open(io.BytesIO(image_bytes))
    total_pixels = image.width * image.height
    fill_rate = _compute_fill_rate(len(payload), total_pixels)
    stego = embed_lsb(image, payload, fill_rate)
    buf = io.BytesIO()
    stego.save(buf, format="PNG")
    return StegOutput(image_bytes=buf.getvalue(), format="png")


def _encode_jpeg(image_bytes: bytes, payload: bytes) -> StegOutput: #todo
    raise NotImplementedError("JPEG DCT not pushed yet")

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
