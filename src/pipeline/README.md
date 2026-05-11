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
- `metrics/` — aggregated CSV tables (see below)
- `predictions/` — raw per-image detector scores
- `manifests/` — cover group manifest with image paths
- `figures/` — PNG figures for Exp 1–5 plus overview/quality summaries

### Metrics CSVs

After a successful run, `metrics/` contains both the per-detector aggregates and a
family of per-experiment contrast tables aligned with the proposal's RQs:

| CSV | Rows are keyed by | Purpose |
|-----|-------------------|---------|
| `detector_metrics.csv` | detector | AUC / EER / accuracy across all conditions |
| `source_metrics.csv` | detector × source | Per-source AUC summary |
| `condition_metrics.csv` | detector × method × payload × encryption | Per-stratum AUC summary |
| `quality_metrics.csv` | method × payload × source | PSNR / SSIM / FSIM per cover/stego pair |
| `exp1_rq1_real_vs_pooled_ml_contrasts.csv` | detector × method × payload | Paired DeLong + Holm: real vs pooled ML |
| `exp2_rq2_mla_vs_mlb_contrasts.csv` | detector × method × payload | Paired DeLong + Holm: SDXL vs PixArt |
| `exp3_rq3_payload_interaction_contrasts.csv` | detector × method × source × payload | Per-source AUC + 95% CI plus real-vs-ML gap (Exp 3a) |
| `exp4_rq4_spatial_vs_frequency_contrasts.csv` | detector × payload | Branch interaction ΔΔ with Wald CI (Exp 4) |
| `exp5_rq5_encryption_contrasts.csv` | detector × source × method × payload | Paired DeLong: plain vs AES-256-CBC |
| `exp5_rq5_source_x_encryption_contrasts.csv` | detector × method × payload | Source × encryption interaction ΔΔ |
| `experiments_summary.csv` | experiment × stratum | Consolidated all-RQ table for the report results section |
| `wilcoxon_tests.csv` | comparison × detector | Paired Wilcoxon signed-rank robustness check |
| `t_tests.csv` | comparison × detector | Paired t-test robustness check |
| `encryption_invariance.csv` | detector × source × method × payload | Per-stratum AUC-equivalence verdict (CI within margin) |
| `rq_verdicts.json` / `rq_verdicts.md` | one entry per RQ | Pre-computed cross-reference: verdict, pooled effect, significant strata. Drop the `.md` into the report's results overview |
| `power_analysis.csv` | stratum | Per-stratum pilot-extrapolated minimum n for 80%/90% power, plus n needed for the proposal's 0.05 ΔAUC threshold |
| `power_summary.csv` | RQ | Headline minimum-n recommendation per RQ family (Holm-aware) |

The Wilcoxon, t-test, encryption-invariance, RQ verdicts, and power analysis are
all produced automatically by `run_full_pipeline()` after figures are generated.
The encryption-invariance CSV is skipped when only one encryption arm is active.

### Figures

In addition to the canonical `exp{N}` figures, the runner emits two RQ-specific
supplementary plots and a verdict-cards composite:

- `rq3_source_payload_heatmap.png` — AUC heatmap per (detector × method), rows
  are carrier sources, columns are payload levels. Complements the `exp3a` line
  plot for reviewers who prefer a tabular-style view.
- `rq4_branch_auc_bars.png` — side-by-side spatial-vs-frequency AUC bars per
  (detector × payload). Complements the `exp4` interaction forest.
- `rq_summary_cards.png` — one card per RQ with the verdict glyph, headline
  numbers, and one-line takeaway. Generated after `rq_verdicts.json` lands and
  re-rendered automatically by the runner.

## Configurable knobs

Profiles set sensible defaults, but every knob can be overridden from the CLI
or the GUI. All knobs are validated before any work starts.

| Knob | CLI flag | Default | Allowed values |
|------|----------|---------|----------------|
| Groups per source | `--n-groups N` | profile | int ≥ 5 (warns below 20) |
| Embedding methods | `--active-methods lsb [dct]` | profile | subset of `{lsb, dct}` |
| Payload levels | `--active-payload-levels low [medium high]` | profile | subset of `{low, medium, high}` |
| Encryption arms | `--active-encryption plain [encrypted]` | both | subset of `{plain, encrypted}` |
| Detectors | `--active-detectors rs [chi_square_spatial sample_pairs chi_square_dct calibration_chi_square]` | all five | subset |
| BD-Sens (k=2) | `--include-bd-sens` | off | boolean |
| JPEG quality | `--jpeg-quality Q` | 95 | int in [50, 100]; warns when ≠ 95 |
| Dry run | `--dry-run` | off | validates only, prints planned figures, exits 0 |

### Knob compatibility rules

| Rule | Constraint | Affects |
|------|-----------|---------|
| R1 | `n_groups ≥ 5` | All experiments |
| R2 | `n_groups ≥ 20` to keep Exp 1, 2 confirmatory (else exploratory only) | Exp 1, Exp 2 |
| R3 | `active_methods` is a non-empty subset of `{lsb, dct}` | Any run |
| R4 | At least one detector matched to each active method (spatial detectors for LSB, DCT detectors for DCT) | Any run |
| R5 | `active_payload_levels` non-empty | Any run |
| R6 | `active_encryption` non-empty | Any run |
| R7 | `jpeg_quality ∈ [50, 100]`; ≠ 95 triggers a warning | DCT branch |
| R8 | `payload_mode=hardcoded` requires non-empty text within capacity | Any run |

### Figure enablement matrix

`PipelineConfig.planned_figures()` returns the set of figures a config will produce.
The GUI preview endpoint (`POST /api/pipeline/preview`) surfaces this set to the
user before launch. Each figure has its own activation rule:

| Figure | Required knob conditions |
|--------|--------------------------|
| `exp1_real_vs_ml` | always |
| `exp2_ml_a_vs_ml_b` | always |
| `exp3a_payload_interaction` | `len(active_payload_levels) ≥ 2` |
| `exp3b_bd_sens` | `include_bd_sens=True` (else `exp3b_bd_sens_surrogate`) |
| `exp4_branch_interaction` | both methods active AND at least one detector from each branch |
| `exp5_encryption_invariance` | both `plain` and `encrypted` in `active_encryption` |
| `exp5_source_encryption_interaction` | same |
| `quality_summary`, `roc_panels`, `auc_by_*` | any non-empty run |

### Example invocations

```bash
# Default prototype run (profile defaults, all knobs at their proposal values)
python run.py prototype --ml-engine stub

# Spatial-only quick check with custom group count
python run.py prototype_full --ml-engine stub \
    --n-groups 50 --active-methods lsb \
    --active-detectors rs chi_square_spatial sample_pairs

# DCT-only run, no encryption arm
python run.py prototype_full --ml-engine stub \
    --active-methods dct --active-encryption plain \
    --active-detectors chi_square_dct calibration_chi_square

# Validate the config without running anything
python run.py prototype --dry-run --ml-engine stub \
    --n-groups 100 --include-bd-sens --jpeg-quality 90
```
