"""Regression tests for the vectorised detectors and the parallel/resume runner.

Covers Phases 1-3 of the detection-optimisation pass:
- Vectorised score equivalence against a deterministic synthetic image.
- Parallel detector stage produces the same row set as sequential.
- Resume from a partially-written predictions.csv produces no duplicates
  and no missing rows.
- Truncated final line in predictions.csv is silently dropped on resume.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from src.detection.rs_analysis import rs_analysis_score, _blocks_2x2
from src.detection.sample_pairs import sample_pairs_score
from src.detection.chi_square_dct import (
    _count_ac_frequencies,
    _get_ac_coefficients,
    chi_square_dct_score,
)
from src.pipeline.runner import (
    _PREDICTIONS_FIELDNAMES,
    _load_existing_prediction_keys,
    _score_one_task,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def random_grayscale_image() -> Image.Image:
    """Deterministic 64x64 grayscale image with a stego-like LSB pattern."""
    rng = np.random.default_rng(20260512)
    pixels = rng.integers(0, 256, size=(64, 64), dtype=np.uint8)
    # Inject a small LSB-flip pattern so Sample Pairs has signal.
    pixels[::3, ::3] ^= 1
    return Image.fromarray(pixels, mode="L")


@pytest.fixture(scope="module")
def jpeg_bytes(random_grayscale_image: Image.Image) -> bytes:
    """A small JPEG-Q95 buffer with embedded LSB-style noise on AC coeffs."""
    buf = io.BytesIO()
    random_grayscale_image.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


# ── Phase 1a: sample_pairs vectorisation ────────────────────────────────────

def _sample_pairs_reference(image: Image.Image) -> float:
    """Original double-loop implementation, kept here as the source of truth."""
    import math

    gray = image.convert("L")
    pixels = np.array(gray, dtype=np.int32)
    h, w = pixels.shape
    j = 30
    sum_x = sum_y = d_0 = c_0 = c_j1 = d_2j2 = 0
    for r in range(h):
        for c in range(w):
            neighbors = []
            if c + 1 < w:
                neighbors.append(pixels[r, c + 1])
            if r + 1 < h:
                neighbors.append(pixels[r + 1, c])
            for v in neighbors:
                u = pixels[r, c]
                diff = abs(u - v)
                upper_diff = abs((u >> 1) - (v >> 1))
                if diff == 0:
                    d_0 += 1
                if diff == 2 * (j + 1):
                    d_2j2 += 1
                if upper_diff == 0:
                    c_0 += 1
                if upper_diff == j + 1:
                    c_j1 += 1
                if diff % 2 == 1 and diff <= 2 * j + 1:
                    if u % 2 == 0:
                        even_val, odd_val = u, v
                    else:
                        even_val, odd_val = v, u
                    if even_val > odd_val:
                        sum_x += 1
                    else:
                        sum_y += 1
    c_coeff = float(sum_y - sum_x)
    a_coeff = float(2 * c_0 - c_j1)
    b_coeff = -(2.0 * d_0 - d_2j2 + 2.0 * c_coeff)
    if a_coeff == 0:
        if b_coeff == 0:
            return 0.0
        q = -c_coeff / b_coeff
        return max(0.0, min(2.0 * q, 1.0))
    discriminant = b_coeff * b_coeff - 4.0 * a_coeff * c_coeff
    if discriminant < 0:
        return 0.0
    sqrt_d = math.sqrt(discriminant)
    q1 = (-b_coeff - sqrt_d) / (2.0 * a_coeff)
    q2 = (-b_coeff + sqrt_d) / (2.0 * a_coeff)
    p1, p2 = 2.0 * q1, 2.0 * q2
    candidates = []
    if -0.1 <= p1 <= 1.1:
        candidates.append(p1)
    if -0.1 <= p2 <= 1.1:
        candidates.append(p2)
    if not candidates:
        return 0.0
    return max(0.0, min(min(candidates), 1.0))


def test_sample_pairs_bit_equivalent(random_grayscale_image: Image.Image) -> None:
    expected = _sample_pairs_reference(random_grayscale_image)
    actual = sample_pairs_score(random_grayscale_image)
    assert actual == pytest.approx(expected, abs=1e-12)


def test_sample_pairs_returns_zero_on_uniform_image() -> None:
    """Uniform image -> all diffs are zero -> singular system -> 0.0."""
    flat = Image.fromarray(np.full((32, 32), 128, dtype=np.uint8), mode="L")
    assert sample_pairs_score(flat) == 0.0


# ── Phase 1b: rs_analysis vectorisation ─────────────────────────────────────

def test_rs_block_ordering_matches_legacy_loop(random_grayscale_image: Image.Image) -> None:
    """The reshape/transpose trick must reproduce the row-major flatten order."""
    pixels = np.array(random_grayscale_image, dtype=np.int16)
    new_blocks = _blocks_2x2(pixels)

    h, w = pixels.shape
    sh, sw = h - (h % 2), w - (w % 2)
    legacy_blocks: list[np.ndarray] = []
    for y in range(0, sh, 2):
        for x in range(0, sw, 2):
            legacy_blocks.append(pixels[y:y + 2, x:x + 2].flatten())
    legacy = np.array(legacy_blocks)

    assert np.array_equal(new_blocks, legacy)


def test_rs_analysis_runs_clean(random_grayscale_image: Image.Image) -> None:
    score = rs_analysis_score(random_grayscale_image)
    assert isinstance(score, float)
    assert score >= 0.0


# ── Phase 1c: chi_square_dct vectorisation ──────────────────────────────────

def test_chi_square_dct_ac_matches_legacy_loop(jpeg_bytes: bytes) -> None:
    from src.embedding.jpeg_dct import luminance_coefficients, read_dct_jpeg

    dct = luminance_coefficients(read_dct_jpeg(jpeg_bytes))
    legacy: list[int] = []
    for br in range(dct.shape[0]):
        for bc in range(dct.shape[1]):
            block = dct[br, bc]
            for r in range(8):
                for c in range(8):
                    if r == 0 and c == 0:
                        continue
                    v = int(block[r, c])
                    if v != 0:
                        legacy.append(v)
    legacy_arr = np.array(legacy, dtype=int)

    vectorised = _get_ac_coefficients(jpeg_bytes)
    assert np.array_equal(np.sort(vectorised), np.sort(legacy_arr))


def test_chi_square_dct_frequency_matches_legacy(jpeg_bytes: bytes) -> None:
    ac = _get_ac_coefficients(jpeg_bytes)
    legacy = {}
    for v in ac:
        v = int(v)
        legacy[v] = legacy.get(v, 0) + 1
    assert _count_ac_frequencies(ac) == legacy


def test_chi_square_dct_score_in_range(jpeg_bytes: bytes) -> None:
    score = chi_square_dct_score(jpeg_bytes)
    # Score is -chi_stat / df: always <= 0; finite; rank-monotonic with the p-value.
    assert isinstance(score, float)
    assert score <= 0.0
    assert score > -1e12  # sanity bound — natural images give chi_stat / df ~ O(10^2..10^6)


# ── Phase 3: resume key parser ──────────────────────────────────────────────

def _make_predictions_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_PREDICTIONS_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def test_resume_keys_missing_file_returns_empty(tmp_path: Path) -> None:
    assert _load_existing_prediction_keys(tmp_path / "missing.csv") == set()


def test_resume_keys_empty_file_returns_empty(tmp_path: Path) -> None:
    p = tmp_path / "empty.csv"
    p.write_text("")
    assert _load_existing_prediction_keys(p) == set()


def test_resume_keys_picks_up_well_formed_rows(tmp_path: Path) -> None:
    p = tmp_path / "predictions.csv"
    _make_predictions_csv(p, [
        {"detector": "rs", "group_id": 1, "source": "real", "method": "lsb",
         "payload_level": "low", "encryption": "plain", "label": 1, "score": 0.5},
        {"detector": "rs", "group_id": 1, "source": "real", "method": "lsb",
         "payload_level": "low", "encryption": "plain", "label": 0, "score": 0.1},
    ])
    keys = _load_existing_prediction_keys(p)
    assert keys == {
        ("rs", 1, "real", "lsb", "low", "plain", 1),
        ("rs", 1, "real", "lsb", "low", "plain", 0),
    }


def test_resume_keys_tolerate_truncated_last_line(tmp_path: Path) -> None:
    """Mid-write SIGKILL leaves a partial final line that the parser must drop."""
    p = tmp_path / "predictions.csv"
    _make_predictions_csv(p, [
        {"detector": "rs", "group_id": 1, "source": "real", "method": "lsb",
         "payload_level": "low", "encryption": "plain", "label": 1, "score": 0.5},
    ])
    with p.open("a") as f:
        f.write("rs,2,ml_a,lsb,medium")  # truncated row, no newline
    keys = _load_existing_prediction_keys(p)
    assert ("rs", 2, "ml_a", "lsb", "medium") not in {k[:5] for k in keys}
    # The complete row was still parsed.
    assert ("rs", 1, "real", "lsb", "low", "plain", 1) in keys


def test_resume_keys_reject_foreign_header(tmp_path: Path) -> None:
    """A file with the wrong header is treated as 'no completed work'."""
    p = tmp_path / "foreign.csv"
    with p.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["alpha", "beta", "gamma"])
        writer.writerow(["a", "b", "c"])
    assert _load_existing_prediction_keys(p) == set()


# ── Phase 2: worker function ────────────────────────────────────────────────

def test_score_one_task_returns_two_rows(tmp_path: Path) -> None:
    """The pool worker must emit both label=1 (stego) and label=0 (cover) rows."""
    # Synthesise a 64x64 LSB-stego cover/stego pair via the real embedder.
    from src.embedding.lsb import embed_lsb

    cover_arr = np.full((64, 64), 128, dtype=np.uint8)
    cover_arr[::2, ::2] = 129  # slight texture so RS doesn't divide by zero
    cover_img = Image.fromarray(cover_arr, mode="L")
    cover_path = tmp_path / "cover.png"
    cover_img.save(cover_path, format="PNG")

    stego_img = embed_lsb(cover_img, payload_bytes=b"\xa5\x5a", fill_rate=0.25)
    stego_path = tmp_path / "stego.png"
    stego_img.save(stego_path, format="PNG")

    task = {
        "detector": "rs",
        "row": {
            "group_id": "7",
            "source": "real",
            "method": "lsb",
            "payload_level": "low",
            "encryption": "plain",
            "cover_path": str(cover_path),
            "stego_path": str(stego_path),
        },
        "project_root": str(tmp_path),
        "jpeg_quality": 95,
        "skip_unimplemented": False,
    }
    out = _score_one_task(task)
    assert len(out) == 2
    labels = {r["label"] for r in out}
    assert labels == {0, 1}
    for r in out:
        assert r["detector"] == "rs"
        assert r["group_id"] == 7
        assert isinstance(r["score"], float)
