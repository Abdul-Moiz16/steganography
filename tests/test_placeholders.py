from __future__ import annotations

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


@pytest.mark.parametrize(
    ("fn", "args", "match"),
    [
        (
            encrypt_payload_aes_256_cbc,
            (b"abc", b"k" * 32, b"i" * 16),
            "AES-256-CBC encryption",
        ),
        (
            decrypt_payload_aes_256_cbc,
            (b"abc", b"k" * 32, b"i" * 16),
            "AES-256-CBC decryption",
        ),
        (
            embed_lsb,
            (Image.new("L", (8, 8), color=0), b"abc", 0.25),
            "Sequential grayscale LSB embedding",
        ),
        (
            embed_dct_lsb_jpeg,
            (b"jpeg-bytes", b"abc", 0.25),
            "JPEG DCT-LSB embedding",
        ),
        (rs_analysis_score, (Image.new("L", (8, 8), color=0),), "RS analysis"),
        (
            chi_square_spatial_score,
            (Image.new("L", (8, 8), color=0),),
            "Spatial chi-square",
        ),
        (
            sample_pairs_score,
            (Image.new("L", (8, 8), color=0),),
            "Sample Pairs",
        ),
        (chi_square_dct_score, (b"jpeg-bytes",), "DCT chi-square"),
        (
            calibration_chi_square_score,
            (b"jpeg-bytes",),
            "Calibration chi-square",
        ),
    ],
)
def test_deferred_functions_raise_not_implemented(fn, args, match: str) -> None:
    with pytest.raises(NotImplementedError, match=match):
        fn(*args)
