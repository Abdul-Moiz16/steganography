#Author: David Wicker
"""JPEG DCT coefficient I/O helpers.

This module is intentionally small: the DCT embedding code only needs to
read quantized coefficients, modify them in memory, and write the same JPEG
structure back without a pixel-domain recompression step.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any

import jpeglib
import numpy as np

LIBJPEG_BACKEND = "6b"


def ensure_libjpeg_backend() -> str:
    """Force and verify the libjpeg backend used for DCT operations."""
    if jpeglib.version.get() != LIBJPEG_BACKEND:
        jpeglib.version.set(LIBJPEG_BACKEND)
    return jpeglib.version.get()


def read_dct_jpeg(jpeg_bytes: bytes) -> Any:
    """Read JPEG bytes into a jpeglib DCT-domain object."""
    ensure_libjpeg_backend()
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_in:
        tmp_in.write(jpeg_bytes)
        tmp_in_path = tmp_in.name
    try:
        return jpeglib.read_dct(tmp_in_path)
    finally:
        os.unlink(tmp_in_path)


def write_dct_jpeg(jpeg_struct: Any) -> bytes:
    """Write a jpeglib DCT-domain object back to JPEG bytes."""
    ensure_libjpeg_backend()
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_out:
        tmp_out_path = tmp_out.name
    try:
        jpeg_struct.write_dct(tmp_out_path)
        with open(tmp_out_path, "rb") as f:
            return f.read()
    finally:
        os.unlink(tmp_out_path)


def luminance_coefficients(jpeg_struct: Any) -> np.ndarray:
    """Return the quantized luminance DCT coefficients.

    jpeglib exposes coefficients as ``(block_row, block_col, 8, 8)`` arrays.
    The current pipeline standardizes frequency-branch covers as grayscale
    JPEGs, so the Y plane is the only plane used for embedding.
    """
    return jpeg_struct.Y
