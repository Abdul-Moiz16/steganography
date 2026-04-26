from __future__ import annotations

from dataclasses import dataclass

from src.toolbox.encode import _get_extension
from src.detection.chi_square_spatial import chi_square_spatial_score


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

    #Save the score
    score_data = DetectorScore(detector="Chi-Square (Spatial)", score=stego_score)
    
    return AnalyzeResult(scores=[score_data], format="png")


def _analyze_jpeg(image_bytes: bytes) -> AnalyzeResult:
    #same here just for jpeg, some are not pushed yet
    raise NotImplementedError("to be done")
