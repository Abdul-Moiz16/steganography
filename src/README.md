# Source Code Guide

This `src/` tree now reflects the final proposal only.

## Module Map

- `common/`: shared enums, filenames, and canonical paths
- `data/`: grayscale standardization, dual cover export, manifest helpers
- `embedding/`: AES, spatial LSB, and JPEG DCT-LSB stubs
- `detection/`: primary statistical-detector stubs
- `evaluation/`: grouped splits, metrics, and figures
- `pipeline/`: orchestration and CLI

## Main Execution Flow

1. Standardize raw images into grayscale PNG and JPEG carrier variants.
2. Build payload manifest for `low/medium/high x plain/encrypted`.
3. Build stego manifest for `lsb` and `dct`.
4. Run embedding stage.
5. Run detector stage.
6. Aggregate metrics and figures.

## Design Rules

- `group_id` is the canonical matching unit.
- Covers are stored twice: PNG for spatial, JPEG Q=95 for frequency.
- Mainline detectors are classical statistical detectors.
- Deferred functions stay pure in-memory; the runner owns file I/O.
