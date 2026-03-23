# `src/evaluation` Guide

`evaluation/` contains metric aggregation and plotting helpers.

## Scope

- total groups: `500`
- evaluation is run on the full study table
- metrics are aggregated by detector, by condition, and by source

## Outputs

- `results/metrics/detector_metrics.csv`
- `results/metrics/source_metrics.csv`
- `results/metrics/*.csv`
- `results/figures/*.png`
