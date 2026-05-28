# Tile-Local χ²-DCT Validation Experiments

Five experiments to establish the tile-local Westfeld χ² detector
(`src/detection/chi_square_dct_tiled.py`, paper §VII.A) beyond the
caption-matched corpus of the main paper. These scripts are
**deliberately outside** the main analysis pipeline so they can be
launched, killed, and re-run independently without touching `runs/`.

Each experiment writes results under `runs/tiled_validation/<exp_id>/`.
Plots use the v4 paper's brand palette (umdark / umlight / umorange /
umgray) so they drop straight into the paper if needed.

## What each experiment tests

| # | Script | Question answered |
|---|---|---|
| 0 | `import_bossbase.py` | (Setup) Imports BOSSBase 1.01 into our pipeline's run layout so the experiments below work on the field's reference dataset, not just our caption-matched corpus. |
| 1 | `exp1_tsweep.py` | Is the tile-grid size T=2 chosen by the paper actually optimal, or would a different T give better AUC? |
| 2 | `exp2_payload_invariance.py` | Does the optimal T depend on payload level (carrier-frequency-sensitive) or is one T best across all payloads? |
| 3 | `exp3_pooling.py` | Is max-pooling essential, or do mean / median / top-K pools match it? Tests whether the gain comes from a sparse-localised stego signal or from heterogeneity averaging. |
| 4 | `exp4_baselines.py` | How does tile-local χ² compare against (a) the textbook global Westfeld χ²-DCT, (b) Westfeld & Pfitzmann's sliding-window variant, and (c) DCTR (learned, optional)? |
| 5 | `exp5_quality_sweep.py` | Is the tile-local advantage JPEG-quality-dependent? Sweeps Q∈{75,85,90,95,98}. SKELETON — requires fresh embedding cycle. |

## Choosing a test corpus

Every experiment script takes `--run <dir>` and works on **any** test corpus that follows our standard layout (`covers/<source>/`, `stego/dct/<payload>/<encryption>/<source>/`, `manifests/covers_real.csv`). Two such corpora are intended:

| Corpus | How to get it | What it tells you |
|---|---|---|
| **Our caption-matched real-vs-AI** | already on disk at `runs/prototype_full_20260513_005357_p8765/` | Reproduces / extends the v4 paper headline numbers (the data the tile-local proposal was developed on). |
| **BOSSBase 1.01** | run `import_bossbase.py` (Step 0 below) | External validation against the steganalysis community's reference dataset; comparable to the DCTR / SRNet papers' evaluation setting. |

Run each experiment on both, compare. Same script, different `--run`.

## Running the experiments

All scripts are run as Python modules from the project root (so the
`from src...` imports resolve via the project sys.path).

### Step 0 — Import BOSSBase 1.01 (one-time setup, optional but recommended)

BOSSBase 1.01 is the field-reference dataset: 10,000 grayscale 512×512 images from 7 camera models, used by DCTR, SRNet, and most modern steganalysis evaluations. Available from CVUT (http://agents.fel.cvut.cz/boss/) or Binghamton (http://dde.binghamton.edu/download/) as a ~3 GB zip of PGM files.

After downloading + extracting (so you have a directory of `1.pgm`, `2.pgm`, ..., `10000.pgm`):

```bash
# Full import at Q=95 (matches our main corpus' JPEG quality, ~3h on laptop)
venv312/bin/python -m scripts.experiments.tiled_chi2_validation.import_bossbase \
    --bossbase-dir /path/to/BOSSbase_1.01 \
    --out-run runs/bossbase_q95 \
    --quality 95

# Same at Q=75 (matches DCTR's headline quality)
... --quality 75 --out-run runs/bossbase_q75

# Quick smoke run on first 100 images (~3 min instead of ~3h)
... --n-images 100 --out-run runs/bossbase_q95_smoke
```

Each subsequent experiment then accepts `--run runs/bossbase_q95` (or whatever name you chose) in place of the caption-matched corpus path. The validation work consists of running each experiment on BOTH corpora and comparing.

### Experiment 1 — tile-size sweep (~30 min on laptop)
```bash
venv312/bin/python -m scripts.experiments.tiled_chi2_validation.exp1_tsweep \
    --run runs/prototype_full_20260513_005357_p8765 \
    --tiles 1 2 3 4 6 8 \
    --pool max
```
Outputs:
- `runs/tiled_validation/exp1_tsweep/results.csv` (T × cell × AUC)
- `runs/tiled_validation/exp1_tsweep/auc_vs_T.png` (line plot)

For a quick dry run cap cells per stratum:
```bash
... --max-cells-per-strata 100      # ~2 min instead of 30
```

### Experiment 2 — cross-payload tile-size invariance (~10 sec, reuses exp1)
```bash
venv312/bin/python -m scripts.experiments.tiled_chi2_validation.exp2_payload_invariance \
    --exp1-results runs/tiled_validation/exp1_tsweep/results.csv
```
Outputs:
- `runs/tiled_validation/exp2_payload_invariance/argmax_T_by_payload.csv`
- `runs/tiled_validation/exp2_payload_invariance/argmax_T_by_payload.png`

### Experiment 3 — pooling-rule ablation (~30 min, T=2 fixed)
```bash
venv312/bin/python -m scripts.experiments.tiled_chi2_validation.exp3_pooling \
    --run runs/prototype_full_20260513_005357_p8765 \
    --tiles 2 \
    --pools max mean median topk_mean
```
Outputs:
- `runs/tiled_validation/exp3_pooling/results.csv`
- `runs/tiled_validation/exp3_pooling/auc_by_pool.png`

### Experiment 4 — baseline detectors (~20 min, plus optional DCTR fold-in)
```bash
venv312/bin/python -m scripts.experiments.tiled_chi2_validation.exp4_baselines \
    --run runs/prototype_full_20260513_005357_p8765
```
With DCTR included (reads existing `predictions_dctr.csv` if present):
```bash
... --dctr-models models/training_v1/dctr_dct_*.pkl
```
Outputs:
- `runs/tiled_validation/exp4_baselines/results.csv`
- `runs/tiled_validation/exp4_baselines/auc_by_detector.png`

### Experiment 5 — JPEG-quality sweep (SKELETON, requires re-embedding)
Requires you to first re-embed the test corpus at each target Q.
That re-embedding step is **not in this scaffold** — it's a small
extension to the main pipeline that produces
`runs/quality_sweep_Q{75,85,90,95,98}/` directories.

Once those exist:
```bash
venv312/bin/python -m scripts.experiments.tiled_chi2_validation.exp5_quality_sweep \
    --quality-runs runs/quality_sweep_Q75 runs/quality_sweep_Q85 \
                   runs/quality_sweep_Q90 runs/quality_sweep_Q95 \
                   runs/quality_sweep_Q98
```

## Suggested run order

1. **Exp 1** first — establishes the T-sweep baseline (~30 min)
2. **Exp 2** immediately after (~10 sec; re-uses exp1 CSV)
3. **Exp 3** next — independent, ~30 min
4. **Exp 4** in parallel with 3 if you have spare cores (~20 min)
5. **Exp 5** last — needs the re-embedding cycle prepared separately

Total laptop wall-clock for experiments 1–4: ~1.5 h. Experiment 5
adds 3–5 h of cloud time for re-embedding plus ~30 min of laptop
scoring once the runs exist.

## Metrics reported

Every experiment writes both metrics to its `results.csv`:

| Column | Definition | Range | Convention used by |
|---|---|---|---|
| `auc` | Area under the ROC curve | 0.5 (chance) → 1.0 (perfect) | Our main paper (v4); steganalysis-eval literature post-2010 |
| `pe_min` | Minimum total detection error: ½·min_τ(FPR(τ) + FNR(τ)) | 0.5 (chance) → 0.0 (perfect) | Fridrich/Goljan & Westfeld classical-detector papers; DCTR (as E_OOB of a trained ensemble) |

`pe_min` is added so the results are directly comparable to the operational error rates reported in Fridrich's RS analysis (IEEE Multimedia 2001), the calibration-χ² paper (SPIE 2003), and Holub & Fridrich's DCTR (IEEE T-IFS 2015 — their `E_OOB` is the trained-ensemble estimate of this same quantity). Plot scripts default to AUC but you can re-plot from the CSV using `pe_min` for any cross-paper comparison.

## Reproducibility

All experiments are deterministic given a fixed test corpus + a fixed
PRNG seed in the detector (none used here — chi² is deterministic on
the same JPEG bytes). Re-running an experiment overwrites the CSV +
PNG in its output directory. To preserve a previous result, copy or
rename the output directory before re-running.

## Adding a new experiment

Add another `expN_<name>.py` in this directory. Import the common
helpers from `_lib.py` (detectors, scoring, AUC, plotting setup) and
follow the same CLI/output convention so a future reader can run them
all uniformly. Update this README's table with the new experiment.
