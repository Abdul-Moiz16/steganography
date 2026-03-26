# `src/detection` Guide

`detection/` implements the five primary statistical detectors from the proposal.

## Detectors

| Function | Domain | Method |
|----------|--------|--------|
| `rs_analysis_score(image)` | Spatial | RS analysis (Fridrich et al.) |
| `chi_square_spatial_score(image)` | Spatial | Chi-square attack on LSB pairs |
| `sample_pairs_score(image)` | Spatial | Sample pairs analysis (Dumitrescu et al.) |
| `chi_square_dct_score(jpeg_bytes)` | Frequency | Chi-square on quantized DCT coefficients |
| `calibration_chi_square_score(jpeg_bytes, jpeg_quality=95)` | Frequency | Calibrated chi-square via cropped re-compression |

All five are classical statistical detectors — no deep learning is used.
