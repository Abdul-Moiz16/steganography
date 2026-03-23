# `src/data` Guide

`data/` handles carrier preparation and manifest persistence.

## Final-Proposal Assumptions

- all carriers become grayscale `512x512`
- every cover is exported twice:
  - spatial PNG
  - frequency JPEG Q=95
- quality control records stay in `covers_master.csv`

## Main Files

- `images.py`
  - grayscale standardization
  - PNG/JPEG writers
  - raw byte loading for JPEG-detector paths
- `manifests.py`
  - dataclasses and CSV/JSON helpers
- `download_real_covers.py`
  - builds the real-image set and prompt manifest
- `generate_ml_covers.py`
  - creates SDXL / PixArt-alpha covers from prompts
- `merge_covers_master.py`
  - merges real + ML manifests into final `covers_master.csv`

## Covers Manifest Schema

- `group_id`, `source`, `dataset`, `orig_id`, `caption_id`, `caption_text`
- `spatial_path`, `frequency_path`
- `qc_pass`, `qc_score`, `seed`
