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
    # create a AnalyzeResult object with all the scores for the corresponding embedding method
    img = Image.open(io.BytesIO(image_bytes))

    #Run through test
    chi_score = chi_square_spatial_score(img)
    rs_score = rs_analysis_score(img)
    sp_score = sample_pairs_score(img)

    #Save the score
    score_list = [
        DetectorScore(detector="Chi-Square (Spatial)", score=chi_score),
        DetectorScore(detector="RS Analysis", score=rs_score),
        DetectorScore(detector="Sample Pairs", score=sp_score)
    ]    
    
    return AnalyzeResult(scores=score_list, format="png")

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
