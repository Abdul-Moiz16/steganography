from __future__ import annotations

import csv
from io import BytesIO
import inspect
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from scipy.stats import chi2

from src.detection.chi_square_dct import (
    _build_pairs,
    _count_ac_frequencies,
    _get_ac_coefficients,
    chi_square_dct_score,
)
from src.embedding.dct import embed_dct_lsb_jpeg
from src.embedding.jpeg_dct import luminance_coefficients, read_dct_jpeg, write_dct_jpeg


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "dct"


def test_dct_chi_square_source_does_not_import_jpegio() -> None:
    source = inspect.getsource(chi_square_dct_score)
    module_source = inspect.getsource(__import__("src.detection.chi_square_dct").detection.chi_square_dct)

    assert "jpegio" not in source
    assert "jpegio" not in module_source


def _make_textured_jpeg(
    size: tuple[int, int] = (96, 96),
    *,
    quality: int = 95,
    mode: str = "L",
    subsampling: int | None = None,
) -> bytes:
    rng = np.random.default_rng(20260429)
    y, x = np.indices(size)
    base = (x * 5 + y * 7 + (x * y) % 31).astype(np.int16)
    noise = rng.integers(-20, 21, size=size, dtype=np.int16)
    gray = np.clip(base + noise + 96, 0, 255).astype(np.uint8)

    if mode == "RGB":
        pixels = np.stack(
            [
                gray,
                np.roll(gray, 3, axis=0),
                np.roll(gray, 5, axis=1),
            ],
            axis=-1,
        )
    else:
        pixels = gray

    buf = BytesIO()
    save_kwargs = {"format": "JPEG", "quality": quality}
    if subsampling is not None:
        save_kwargs["subsampling"] = subsampling
    Image.fromarray(pixels, mode=mode).save(buf, **save_kwargs)
    return buf.getvalue()


def _independent_chi_square_score(jpeg_bytes: bytes) -> float:
    coeffs = luminance_coefficients(read_dct_jpeg(jpeg_bytes))
    ac_values = []

    for block_row in range(coeffs.shape[0]):
        for block_col in range(coeffs.shape[1]):
            block = coeffs[block_row, block_col]
            for row in range(8):
                for col in range(8):
                    if row == 0 and col == 0:
                        continue
                    value = int(block[row, col])
                    if value != 0:
                        ac_values.append(value)

    frequencies = {value: ac_values.count(value) for value in sorted(set(ac_values))}
    values = sorted(frequencies)

    chi2_stat = 0.0
    pair_count = 0
    i = 0
    while i < len(values):
        value = values[i]
        next_value = value + 1
        if next_value in frequencies:
            n_lower = frequencies[value]
            n_upper = frequencies[next_value]
            total = n_lower + n_upper
            chi2_stat += ((n_lower - n_upper) ** 2) / total
            pair_count += 1
            i += 2
        else:
            i += 1

    if pair_count == 0:
        return 0.0
    return float(1.0 - chi2.sf(chi2_stat, pair_count))


def _read_matlab_score_fixture() -> dict[str, dict[str, float]]:
    with (FIXTURE_DIR / "chi_square_dct_scores.csv").open(newline="", encoding="utf-8") as f:
        rows = csv.DictReader(f)
        return {
            row["case"]: {
                "chi2_stat": float(row["chi2_stat"]),
                "df": float(row["df"]),
                "score": float(row["score"]),
                "nonzero_ac_count": float(row["nonzero_ac_count"]),
                "pair_count": float(row["pair_count"]),
            }
            for row in rows
        }


def test_dct_chi_square_builds_adjacent_coefficient_pairs() -> None:
    frequencies = {
        -5: 7,
        -4: 11,
        -3: 13,
        -2: 17,
        -1: 19,
        1: 23,
        2: 29,
        3: 31,
        4: 37,
        5: 41,
    }

    assert _build_pairs(frequencies) == [
        (7, 11),
        (13, 17),
        (23, 29),
        (31, 37),
    ]


def test_dct_chi_square_matches_matlab_reference_scores() -> None:
    cover = (FIXTURE_DIR / "cover_q95.jpg").read_bytes()
    expected = _read_matlab_score_fixture()
    cases = {
        "cover_q95": cover,
        "stego_25": embed_dct_lsb_jpeg(cover, bytes([0xAA]) * 6, 0.25),
        "stego_50": embed_dct_lsb_jpeg(cover, bytes([0xAA]) * 13, 0.50),
        "stego_75": embed_dct_lsb_jpeg(cover, bytes([0xAA]) * 20, 0.75),
    }

    for case_name, jpeg_bytes in cases.items():
        assert chi_square_dct_score(jpeg_bytes) == pytest.approx(
            expected[case_name]["score"],
            abs=1e-12,
        )
        assert len(_get_ac_coefficients(jpeg_bytes)) == int(
            expected[case_name]["nonzero_ac_count"]
        )
        assert len(_build_pairs(_count_ac_frequencies(_get_ac_coefficients(jpeg_bytes)))) == int(
            expected[case_name]["pair_count"]
        )


@pytest.mark.parametrize(
    ("size", "quality", "fill_rate"),
    [
        ((64, 64), 75, 0.25),
        ((80, 112), 85, 0.50),
        ((128, 96), 95, 0.75),
    ],
)
def test_dct_chi_square_handles_multiple_sizes_qualities_and_payload_rates(
    size: tuple[int, int],
    quality: int,
    fill_rate: float,
) -> None:
    cover = _make_textured_jpeg(size=size, quality=quality)
    cover_score = chi_square_dct_score(cover)
    payload_bits = max(8, int(len(_get_ac_coefficients(cover)) * fill_rate * 0.25))
    payload = bytes([0xAA]) * max(1, payload_bits // 8)
    stego = embed_dct_lsb_jpeg(cover, payload, fill_rate)
    stego_score = chi_square_dct_score(stego)

    assert np.isfinite(cover_score)
    assert np.isfinite(stego_score)
    assert 0.0 <= cover_score <= 1.0
    assert 0.0 <= stego_score <= 1.0
    assert stego_score >= cover_score - 0.05


def test_dct_chi_square_scores_generally_increase_with_payload_rate() -> None:
    cover = (FIXTURE_DIR / "cover_q95.jpg").read_bytes()
    scores = [
        chi_square_dct_score(cover),
        chi_square_dct_score(embed_dct_lsb_jpeg(cover, bytes([0xAA]) * 6, 0.25)),
        chi_square_dct_score(embed_dct_lsb_jpeg(cover, bytes([0xAA]) * 13, 0.50)),
        chi_square_dct_score(embed_dct_lsb_jpeg(cover, bytes([0xAA]) * 20, 0.75)),
    ]

    assert scores[0] < scores[1] < scores[2]
    assert scores[3] >= scores[2] - 0.00001
    assert scores[3] > scores[0]


def test_dct_chi_square_returns_finite_deterministic_probability() -> None:
    cover = (FIXTURE_DIR / "cover_q95.jpg").read_bytes()

    score_a = chi_square_dct_score(cover)
    score_b = chi_square_dct_score(cover)

    assert isinstance(score_a, float)
    assert np.isfinite(score_a)
    assert 0.0 <= score_a <= 1.0
    assert score_a == score_b


def test_dct_chi_square_matches_independent_reference_implementation() -> None:
    cover = (FIXTURE_DIR / "cover_q95.jpg").read_bytes()
    stego = embed_dct_lsb_jpeg(cover, bytes([0xAA]) * 20, 0.75)

    assert chi_square_dct_score(cover) == pytest.approx(
        _independent_chi_square_score(cover),
        abs=1e-12,
    )
    assert chi_square_dct_score(stego) == pytest.approx(
        _independent_chi_square_score(stego),
        abs=1e-12,
    )


def test_dct_chi_square_handles_all_zero_ac_coefficients() -> None:
    jpeg = read_dct_jpeg(_make_textured_jpeg(size=(16, 16), quality=95))
    coeffs = luminance_coefficients(jpeg)
    coeffs[:, :, 1:, :] = 0
    coeffs[:, :, 0, 1:] = 0

    zero_ac_jpeg = write_dct_jpeg(jpeg)

    assert len(_get_ac_coefficients(zero_ac_jpeg)) == 0
    assert chi_square_dct_score(zero_ac_jpeg) == 0.0


def test_dct_chi_square_handles_tiny_jpeg() -> None:
    tiny = _make_textured_jpeg(size=(8, 8), quality=95)
    score = chi_square_dct_score(tiny)

    assert isinstance(score, float)
    assert np.isfinite(score)
    assert 0.0 <= score <= 1.0


def test_dct_chi_square_rejects_malformed_jpeg_bytes() -> None:
    with pytest.raises(Exception):
        chi_square_dct_score(b"not-a-jpeg")


def test_dct_chi_square_handles_color_subsampled_jpeg() -> None:
    color_jpeg = _make_textured_jpeg(
        size=(96, 96),
        quality=90,
        mode="RGB",
        subsampling=2,
    )

    jpeg = read_dct_jpeg(color_jpeg)
    assert jpeg.has_chrominance

    score = chi_square_dct_score(color_jpeg)
    assert isinstance(score, float)
    assert np.isfinite(score)
    assert 0.0 <= score <= 1.0


def test_dct_chi_square_increases_for_high_payload_jsteg_fixture() -> None:
    cover = (FIXTURE_DIR / "cover_q95.jpg").read_bytes()
    payload = bytes([0xAA]) * 20
    stego = embed_dct_lsb_jpeg(cover, payload, 0.75)

    cover_score = chi_square_dct_score(cover)
    stego_score = chi_square_dct_score(stego)

    assert stego_score > cover_score
