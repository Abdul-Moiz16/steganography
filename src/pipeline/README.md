# `src/pipeline` Guide

`pipeline/` orchestrates the final proposal’s mainline stages.

## Files

- `config.py`
  - image size, JPEG quality, fill rates, seeds
- `runner.py`
  - cover standardization
  - payload / stego manifests
  - grouped splits
  - embedding stage
  - detector stage
  - metric aggregation
  - figure generation
- `cli.py`
  - command-line wrappers around the runner

## Important Differences From The Old Design

- no SRM training-job stage in the default pipeline
- no SRM auto-training inside detector execution
- no DCT-QIM path
- no RGB-only single-format cover pipeline

## Main Commands

```bash
python3 -m src.pipeline.cli --project-root . init-layout
python3 -m src.pipeline.cli --project-root . standardize-covers --input-index <raw_cover_index.csv>
python3 -m src.pipeline.cli --project-root . build-payload-manifest --covers-manifest data/manifests/covers_master.csv
python3 -m src.pipeline.cli --project-root . build-stego-manifest --covers-manifest data/manifests/covers_master.csv --payload-manifest data/manifests/payload_manifest.csv
python3 -m src.pipeline.cli --project-root . run-embedding-stage --stego-manifest data/manifests/stego_manifest.csv
python3 -m src.pipeline.cli --project-root . run-detectors --stego-manifest data/manifests/stego_manifest.csv
python3 -m src.pipeline.cli --project-root . compute-metrics --predictions results/predictions/predictions.csv
python3 -m src.pipeline.cli --project-root . plot-metrics
```
