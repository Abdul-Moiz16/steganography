# `src/pipeline` Guide

`pipeline/` orchestrates the full experiment from cover preparation to metric output.

## Files

- `profile.py` — named experiment profiles (`prototype`, `prototype_full`, `full_design`)
- `config.py` — image size, JPEG quality, fill rates, seeds, profile-based scoping
- `runner.py` — main execution: cover prep, manifest building, embedding, detection, metrics
- `cli.py` — command-line interface wrapping the runner

## Profiles

| Profile | Groups | Methods | Payloads | Detectors |
|---------|--------|---------|----------|-----------|
| `prototype` | 20 | LSB | Low | 3 (spatial) |
| `prototype_full` | 100 | LSB + DCT | Low + Medium + High | 5 (spatial + frequency) |
| `full_design` | 500 | LSB + DCT | Low + Medium + High | 5 (spatial + frequency) |

## Usage

```bash
# Full pipeline in one command
python -m src.pipeline.cli --project-root . run-all \
    --covers-manifest data/manifests/covers_master.csv \
    --profile prototype --execute-embeddings --execute-detectors

# Individual stages
python -m src.pipeline.cli --project-root . init-layout
python -m src.pipeline.cli --project-root . build-payload-manifest --covers-manifest data/manifests/covers_master.csv
python -m src.pipeline.cli --project-root . build-stego-manifest --covers-manifest data/manifests/covers_master.csv --payload-manifest data/manifests/payload_manifest.csv
python -m src.pipeline.cli --project-root . run-embedding-stage --stego-manifest data/manifests/stego_manifest.csv
python -m src.pipeline.cli --project-root . run-detectors --stego-manifest data/manifests/stego_manifest.csv
python -m src.pipeline.cli --project-root . compute-metrics --predictions results/predictions/predictions.csv
python -m src.pipeline.cli --project-root . plot-metrics
```

## Output

Results are written to `runs/{profile}_{timestamp}/` containing:
- `config.json` — frozen experiment configuration
- `metrics/` — aggregated CSV tables
- `predictions/` — raw per-image detector scores
- `manifests/` — cover group manifest with image paths
