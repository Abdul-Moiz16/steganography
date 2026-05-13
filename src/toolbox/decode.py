from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

from src.embedding.dct import decode_dct_lsb_jpeg
from src.embedding.lsb import decode_lsb
from src.toolbox.encode import _get_extension


HEADER_BYTES = 4

@dataclass
class DecResult:
    message: str


def decode(image_bytes: bytes, filename: str) -> DecResult:
    extension = _get_extension(filename)

    if extension == ".png":
        return _decode_png(image_bytes)
    else:
        return _decode_jpeg(image_bytes)

def _decode_png(image_bytes: bytes) -> DecResult:
    img = Image.open(io.BytesIO(image_bytes))

    # get 4 byte header top get payload length
    header_raw = decode_lsb(img, fill_rate=1.0, payload_length=HEADER_BYTES)
    msg_length = int.from_bytes(header_raw, "big")

    # get header + body
    full_raw = decode_lsb(img, fill_rate=1.0, payload_length=HEADER_BYTES + msg_length)

    return DecResult(message=_parse_payload(full_raw))


def _decode_jpeg(image_bytes: bytes) -> DecResult:
    """Mirror of ``_decode_png`` for JSteg-style DCT-LSB stego.

    The encoder writes a 4-byte big-endian length prefix into the first
    32 eligible-coefficient positions, followed by the UTF-8 body. We
    read at ``fill_rate=1.0`` (same as the encoder used) and rely on
    the length prefix to bound the body read.
    """
    header_raw = decode_dct_lsb_jpeg(image_bytes, HEADER_BYTES, fill_rate=1.0)
    msg_length = int.from_bytes(header_raw, "big")
    full_raw = decode_dct_lsb_jpeg(
        image_bytes, HEADER_BYTES + msg_length, fill_rate=1.0,
    )
    return DecResult(message=_parse_payload(full_raw))


def _parse_payload(raw: bytes) -> str: # read header and then decode body
    if len(raw) < HEADER_BYTES:
        raise ValueError("Payload too short to contain a valid header.")

    header = raw[:HEADER_BYTES]
    length = int.from_bytes(header, "big")

    body = raw[HEADER_BYTES:HEADER_BYTES + length]

    if len(body) < length:
        raise ValueError("Payload cut off: given length exceeds available bytes.")

    return body.decode("utf-8")
