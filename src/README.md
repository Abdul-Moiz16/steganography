# Source Code Guide

The `src/` tree implements the full carrier-source steganalysis pipeline.

## Module Map

- `common/`: shared enums, filenames, and canonical paths
- `data/`: real-image download, ML cover generation, grayscale standardization, manifest helpers
- `embedding/`: AES-256-CBC encryption, spatial LSB, and JPEG DCT-LSB embedding
- `detection/`: RS Analysis, Chi-Square (spatial + DCT), Sample Pairs, Calibration Chi-Square
- `evaluation/`: metric aggregation (ROC-AUC, EER, accuracy, PSNR/SSIM) and figure generation
- `pipeline/`: orchestration profiles, runner, and CLI

## Main Execution Flow

1. Download real images and generate ML covers (SDXL + FLUX.1-schnell).
2. Standardize all covers into grayscale 512×512 PNG and JPEG variants.
3. Build payload manifest for `low/medium/high × plain/encrypted`.
4. Build stego manifest for `lsb` and `dct` branches.
5. Run embedding stage (LSB on PNG, DCT-LSB on JPEG Q=95).
6. Run detector stage (5 classical statistical detectors).
7. Aggregate metrics and generate figures.

## Design Rules

- `group_id` is the canonical matching unit across sources.
- Covers are stored twice: PNG for spatial branch, JPEG Q=95 for frequency branch.
- Mainline detectors are classical statistical detectors only.
- The runner owns file I/O; core functions operate in-memory.
