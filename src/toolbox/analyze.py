from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

from src.detection.calibration_chi_square import calibration_chi_square_score
from src.detection.chi_square_dct import chi_square_dct_score
from src.detection.chi_square_spatial import chi_square_spatial_score
from src.detection.rs_analysis import rs_analysis_score
from src.detection.sample_pairs import sample_pairs_score
from src.toolbox.encode import _get_extension

@dataclass
class DetectorScore:
    detector: str
    score: float

@dataclass
class AnalyzeResult:
    scores: list[DetectorScore]
    format: str

def analyze(image_bytes: bytes,filename: str) -> AnalyzeResult:
    extension = _get_extension(filename)

    if extension == ".png":
        return _analyze_png(image_bytes)
    else:
        return _analyze_jpeg(image_bytes)


def _analyze_png(image_bytes: bytes) -> AnalyzeResult:
    img = Image.open(io.BytesIO(image_bytes))

    chi_score = chi_square_spatial_score(img)
    rs_score = _normalised_rs(img)
    sp_score = sample_pairs_score(img)

    score_list = [
        DetectorScore(detector="Chi-Square (Spatial)", score=chi_score),
        DetectorScore(detector="RS Analysis", score=rs_score),
        DetectorScore(detector="Sample Pairs", score=sp_score),
    ]
    return AnalyzeResult(scores=score_list, format="png")


def _normalised_rs(image: Image.Image) -> float:
    """Image-size-invariant RS rate.

    The pipeline's :func:`rs_analysis_score` returns the raw mask-
    disagreement count ``|R_m - R_-m| + |S_m - S_-m|``, which scales
    with the number of 2x2 pixel groups in the image. AUC-based pipeline
    comparisons don't care about that scaling (ranks are preserved), but
    a single-image toolbox readout needs a number that doesn't depend on
    cover size. We normalise by the total 2x2 group count so the result
    is roughly a per-group disagreement rate in [0, 2].
    """
    raw = rs_analysis_score(image)
    img = image.convert("L")
    w, h = img.size
    total_groups = max(1, (h // 2) * (w // 2))
    return raw / total_groups

def _analyze_jpeg(image_bytes: bytes) -> AnalyzeResult:
    """Frequency-branch detectors: chi^2-DCT + Calibration chi^2.

    Both return ``-chi_stat / df`` (rank-monotonic with the Westfeld
    1999 p-value but underflow-free) -- more negative = stronger
    cover-like statistics; closer to zero = stronger stego evidence.
    """
    chi_dct = chi_square_dct_score(image_bytes)
    cal_chi = calibration_chi_square_score(image_bytes)
    scores = [
        DetectorScore(detector="Chi-Square (DCT)", score=chi_dct),
        DetectorScore(detector="Calibration Chi-Square", score=cal_chi),
    ]
    return AnalyzeResult(scores=scores, format="jpeg")
