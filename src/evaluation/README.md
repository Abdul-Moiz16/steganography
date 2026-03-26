# `src/evaluation` Guide

`evaluation/` aggregates detector predictions into experiment-level metrics.

## Aggregation Levels

- **Per-detector**: overall ROC-AUC, EER, accuracy across all conditions
- **Per-source**: ROC-AUC broken down by carrier source (real, ML-A, ML-B)
- **Per-condition**: ROC-AUC for each (detector × method × payload × encryption)
- **Per-group quality**: PSNR and SSIM measuring embedding imperceptibility

## Outputs

Written to `runs/{run_id}/metrics/`:

- `detector_metrics.csv` — aggregated per detector
- `source_metrics.csv` — per detector × source
- `condition_metrics.csv` — per detector × method × payload level × encryption
- `quality_metrics.csv` — PSNR/SSIM per group × source × condition
