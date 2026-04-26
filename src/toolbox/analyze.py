from __future__ import annotations

from dataclasses import dataclass

from src.toolbox.encode import _get_extension
from src.detection.chi_square_spatial import chi_square_spatial_score
from src.detection.rs_analysis import rs_analysis_score
from src.detection.sample_pairs import sample_pairs_score


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
        DetectorScore(detector="Chi-Square (Spatial)", score=stego_score),
        DetectorScore(detector="RS Analysis", score=rs_score),
        DetectorScore(detector="Sample Pairs", score=sp_score)
    ]    
    
    return AnalyzeResult(scores=score_list, format="png")


def _analyze_jpeg(image_bytes: bytes) -> AnalyzeResult:
    #same here just for jpeg, some are not pushed yet
    raise NotImplementedError("to be done")
