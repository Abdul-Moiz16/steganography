from __future__ import annotations

import random
from pathlib import Path

import numpy as np

from src.embedding.jpeg_dct import (
    luminance_coefficients,
    read_dct_jpeg,
    write_dct_jpeg,
)


BS = 8
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "dct"
JPEG_FIXTURES = [
    FIXTURE_DIR / "cover_q95.jpg",
    FIXTURE_DIR / "matlab_jsteg_a53c.jpg",
]


def _count_nnz_ac(coeffs: np.ndarray) -> int:
    count = 0
    for block_row in range(coeffs.shape[0]):
        for block_col in range(coeffs.shape[1]):
            block = coeffs[block_row, block_col]
            ac_block = block.copy()
            ac_block[0, 0] = 0
            count += int(np.count_nonzero(ac_block))
    return count


def test_repeat_read_dct_jpegs_without_state_leakage() -> None:
    rng = random.Random(20260429)
    expected_shapes = {
        path.name: luminance_coefficients(read_dct_jpeg(path.read_bytes())).shape
        for path in JPEG_FIXTURES
    }

    for _ in range(100):
        path = rng.choice(JPEG_FIXTURES)
        jpeg = read_dct_jpeg(path.read_bytes())
        assert luminance_coefficients(jpeg).shape == expected_shapes[path.name]
        jpeg.close()


def test_dct_block_array_shape_matches_coefficient_grid() -> None:
    for path in JPEG_FIXTURES:
        jpeg = read_dct_jpeg(path.read_bytes())
        coeffs = luminance_coefficients(jpeg)

        assert coeffs.shape[-2:] == (BS, BS)
        assert jpeg.block_dims[0].tolist() == [coeffs.shape[0], coeffs.shape[1]]
        assert jpeg.height_in_blocks(0) == coeffs.shape[0]
        assert jpeg.width_in_blocks(0) == coeffs.shape[1]


def test_dct_blocks_match_direct_coefficient_indexing() -> None:
    for path in JPEG_FIXTURES:
        coeffs = luminance_coefficients(read_dct_jpeg(path.read_bytes()))

        for block_row in range(coeffs.shape[0]):
            for block_col in range(coeffs.shape[1]):
                coef_block = coeffs[block_row, block_col]
                assert np.array_equal(coef_block, coeffs[block_row, block_col, :, :])


def test_count_nonzero_ac_coefficients_matches_expected_fixture_values() -> None:
    expected_counts = {
        "cover_q95.jpg": 381,
        "matlab_jsteg_a53c.jpg": 381,
    }

    for path in JPEG_FIXTURES:
        coeffs = luminance_coefficients(read_dct_jpeg(path.read_bytes()))
        assert _count_nnz_ac(coeffs) == expected_counts[path.name]


def test_write_dct_coefficient_edit_survives_roundtrip() -> None:
    for path in JPEG_FIXTURES:
        jpeg = read_dct_jpeg(path.read_bytes())
        coeffs = luminance_coefficients(jpeg)
        expected = coeffs.copy()

        block_row = min(1, coeffs.shape[0] - 1)
        block_col = min(1, coeffs.shape[1] - 1)
        pos = (block_row, block_col, 0, 1)
        replacement = int(coeffs[pos]) + 2

        coeffs[pos] = replacement
        expected[pos] = replacement

        reread = read_dct_jpeg(write_dct_jpeg(jpeg))
        assert np.array_equal(luminance_coefficients(reread), expected)


def test_write_quantization_table_edit_survives_roundtrip() -> None:
    for path in JPEG_FIXTURES:
        jpeg = read_dct_jpeg(path.read_bytes())
        expected_qt = jpeg.qt.copy()
        expected_coeffs = luminance_coefficients(jpeg).copy()

        replacement = int(jpeg.qt[0, 0, 0]) + 1
        jpeg.qt[0, 0, 0] = replacement
        expected_qt[0, 0, 0] = replacement

        reread = read_dct_jpeg(write_dct_jpeg(jpeg))

        assert np.array_equal(reread.qt, expected_qt)
        assert np.array_equal(luminance_coefficients(reread), expected_coeffs)
