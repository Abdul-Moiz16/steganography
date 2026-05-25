# Learned-detector baselines: SRNet (spatial) + DCTR (frequency)

A standalone training + inference pipeline for two learned baselines that
complement the six training-free detectors already in the main pipeline.

## Design constraints

1. **Training is OUT of the main pipeline.** The main pipeline (run.py
   prototype_full ...) is for training-free detectors only and must stay
   reproducible without any GPU / heavy ML code path.

2. **Training scripts may CALL pipeline modules** to assemble their own
   training dataset (image download, ML generation, embedding) but write
   to a separate `runs/training_<id>/` directory that the main pipeline
   doesn't touch.

3. **Trained model weights are versioned artefacts.** Saved under
   `models/<detector>_<method>_<payload>_v<n>.{pt,pkl}` with a YAML
   manifest. Inference scripts load weights and never retrain.

4. **Inference applies a trained model AS-IS to an existing run.** Output
   is appended to a `predictions_<detector>.csv` matching the schema of
   the existing `predictions.csv`, so the main analysis pipeline can
   incorporate the learned-detector rows without modification.

5. **No leakage.** The 3,000-group test run
   (`runs/prototype_full_20260513_005357_p8765/`) is the FINAL test set.
   Training data must come from a separate run with disjoint caption
   groups.

## Detector choice

| Branch       | Detector | Why                                                        |
|--------------|----------|------------------------------------------------------------|
| Spatial (LSB) | SRNet    | Standard learned baseline for spatial steganalysis. ~470k parameters, end-to-end trainable, designed for 512×512 grayscale. |
| Frequency (DCT) | DCTR     | Standard learned baseline for JPEG steganalysis. Fixed 8000-dim feature extractor + ensemble/LDA classifier. No deep-network training required. |

This avoids the SRNet-on-JPEG mismatch (SRNet is designed for spatial,
not DCT-domain input).

## Feasibility numbers

**Training data:** ~3,500 caption groups (separate from the 3,000-group
test run) gives ~10,500 covers + ~63,000 LSB stegos + ~63,000 DCT stegos.
This matches SRNet's typical training budget (BOSSBase has ~10k images).

- Real images: ~30 min (HF dataset download)
- ML generation: ~5h (HF Inference API, throughput-bound)
- Embedding: ~30 min
- **Total dataset assembly: ~6h wall-clock**

**Training:**
- SRNet: 50-100 epochs per (method, payload) cell. Six cells × ~6h/cell on a single GPU = ~36 GPU-hours. Or three cells (LSB only) = ~18 GPU-hours.
- DCTR: feature extraction ~3-4h on CPU; LDA classifier training is seconds.

**Inference on the 3,000-group test run:**
- SRNet: 63k inferences × ~80 img/s on GPU = **~15 minutes**
- DCTR: 63k inferences × ~1 s/image / 8 cores = **~3-4 hours**

**Bottom line:** a single GPU + one CPU core completes the full SRNet
training + inference cycle in ~1 week wall-clock. DCTR adds an extra day.

## Directory layout

```
src/detection_learned/
├── srnet.py              # PyTorch SRNet model
├── srnet_score.py        # Inference wrapper (load + score)
├── dctr_features.py      # DCTR feature extractor
├── dctr_score.py         # Inference wrapper (extract + classify)
└── data.py               # Shared DataLoader: caption-group-aware splits

scripts/training/
├── generate_training_set.py   # Calls pipeline modules to assemble training run
├── train_srnet.py             # Per (method, payload) cell, saves model + log
└── train_dctr.py              # Extracts features, trains LDA, saves classifier

scripts/inference/
├── apply_srnet_to_run.py      # Loads checkpoints, runs on existing run
└── apply_dctr_to_run.py       # Same for DCTR

models/
├── srnet_lsb_low_v1.pt        # PyTorch state dict
├── srnet_lsb_medium_v1.pt
├── srnet_lsb_high_v1.pt
└── dctr_dct_<payload>_v1.pkl  # scikit-learn classifier + feature normaliser
└── manifest.yaml              # Version, training data hash, val-AUC, etc.

docs/learned_baselines/
├── PLAN.md                    # This file
└── RESULTS.md                 # Generated after training + inference
```

## Workflow

### Step 1 — Assemble training data (one-time, ~6h)

```bash
python scripts/training/generate_training_set.py \
  --n-groups 3500 \
  --out-run runs/training_v1 \
  --seed 42 \
  --exclude-captions-from runs/prototype_full_20260513_005357_p8765
```

The `--exclude-captions-from` flag reads the test run's caption manifest
and excludes those captions from the new training set, guaranteeing
disjoint groups.

### Step 2 — Train SRNet per cell (~36 GPU-hours total)

```bash
for payload in low medium high; do
  python scripts/training/train_srnet.py \
    --training-run runs/training_v1 \
    --method lsb \
    --payload $payload \
    --epochs 80 \
    --batch-size 16 \
    --out models/srnet_lsb_${payload}_v1.pt
done
```

### Step 3 — Train DCTR per cell (~5h total: features dominate)

```bash
for payload in low medium high; do
  python scripts/training/train_dctr.py \
    --training-run runs/training_v1 \
    --method dct \
    --payload $payload \
    --out models/dctr_dct_${payload}_v1.pkl
done
```

### Step 4 — Apply to the test run (~4h DCTR + ~15min SRNet)

```bash
python scripts/inference/apply_srnet_to_run.py \
  --run runs/prototype_full_20260513_005357_p8765 \
  --models models/srnet_lsb_*.pt \
  --out runs/prototype_full_20260513_005357_p8765/predictions_srnet.csv

python scripts/inference/apply_dctr_to_run.py \
  --run runs/prototype_full_20260513_005357_p8765 \
  --models models/dctr_dct_*.pkl \
  --out runs/prototype_full_20260513_005357_p8765/predictions_dctr.csv
```

### Step 5 — Merge into analysis (~5 min)

```bash
python scripts/inference/merge_learned_predictions.py \
  --run runs/prototype_full_20260513_005357_p8765
# Concatenates predictions.csv + predictions_srnet.csv + predictions_dctr.csv
# Re-runs aggregate_by_groups + paired DeLong over the merged file
# Writes updated metrics/*_with_learned.csv
```

## Training-data design

### Why we train on our own data, not BOSSBase

The standard steganalysis baseline is to train SRNet on BOSSBase
(10,000 pure-photo grayscale images). For our research question we
deliberately **do not** do this -- BOSSBase-trained SRNet evaluated
on our caption-matched run would bundle two distinct effects:

  - inherent carrier-source detectability (the thing we want to measure)
  - cover-source mismatch (BOSSBase contains no diffusion images, so any
    ML cover at test time is out-of-distribution to the trained model)

The classical detectors avoid this bundling by being training-free.
SRNet is learned, so we have to provide it with a training distribution
that covers all carrier sources we plan to test. A BOSSBase-trained
SRNet evaluated on our run would conflate carrier-source effects with
cover-source mismatch -- making any AUC gap uninterpretable.

The cleanest design: train on our own mixed-source data with the
sources balanced per batch, then evaluate per-source on the held-out
test run. At test time every source is in-distribution to the model,
so any AUC gap reflects only the inherent carrier-source signal.

A BOSSBase-trained SRNet would still be valuable as a *complementary*
experiment (the cross-domain CSM study), but it answers a different
question and is not a substitute for our primary design.

### Splits per (method, payload) cell

Group-aware split via `group_id % 10`:

| Split | groups | covers per source | stegos (per cell, 2 encryption) |
|---|---|---|---|
| train | ~2,450 | ~2,450 | ~14,700 |
| val | ~700 | ~700 | ~4,200 |
| id_test | ~350 | ~350 | ~2,100 |

The 3,000-group main run is the **held-out OOD test** (disjoint
captions, same generation pipeline). Each carrier source has 2,450 train
covers x 6 (method, payload) cells = 14,700 cover groups per source
across the full training schedule.

### Embedding-time budget

Per the main pipeline's observed rate (~15 stegos/sec on 8 CPU cores):

| Step | Count | Time |
|---|---|---|
| LSB stegos (full training set) | 63,000 | ~1.2h |
| DCT stegos (full training set) | 63,000 | ~1.2h |
| **Total embedding** | **126,000** | **~2.5h** |

Combined with ML cover generation (~5h HF API), total wall-clock for
training-data assembly is **~7-8h**, mostly idle CPU during API calls.

### Group-aware splits

The DataLoader takes `group_id` as a key and a deterministic mod-10 split:
- group_id % 10 ∈ {0..6} → train
- group_id % 10 ∈ {7..8} → val
- group_id % 10 == 9   → in-distribution test

The 3,000-group main run uses its own group_ids that are disjoint by
caption hash; this is the held-out OOD test.

### Class balance (gotcha #2 — properly handled)

The naive approach -- enumerate every (cover, stego) Sample and let the
DataLoader shuffle -- double-counts covers, because each cover has TWO
stego variants per (method, payload) cell (plain + AES-256-CBC). With
two Samples per cover the same cover image enters the dataset twice
per epoch, biasing the loss toward covers and wasting load bandwidth.

Our fix: a custom paired loader (``make_balanced_pair_loader`` in
``src/detection_learned/data.py``). Each batch of size $B$ is built from
$B/2$ cover-stego pairs, each pair drawn from a distinct cover group.
This guarantees:

  - Exactly $B/2$ covers and $B/2$ stegos per batch (50/50 by construction).
  - Each physical cover is loaded at most once per epoch.
  - Sources (real / SDXL / FLUX) are mixed uniformly because they're all
    in the cover-group pool.

### Encryption handling (gotcha #3 — properly handled)

**Training:** RQ5 already established that AES-256-CBC encryption is
invariant; we therefore mix both stego variants under the same "stego"
label. The CoverGroup dataclass holds both stego paths per cover, and
``CoverGroup.sample_stego(rng)`` draws a uniformly-random encryption
variant on every dataset access. Over an epoch each cover sees one
variant (sampled fresh each epoch via the dataset's seed), so over many
epochs plain and encrypted contribute equally.

**Inference:** the test run's predictions.csv schema indexes cover
rows by encryption alongside stego rows, even though the cover bytes
are identical across encryption variants. We score each physical cover
ONCE (in apply_srnet_to_run.py) and emit one prediction row per
encryption variant with the same numeric score. Stegos are scored
independently because they are physically different files. This keeps
the output strictly compatible with the existing analysis pipeline.

## What the SRNet/DCTR results will tell us

| Outcome | Interpretation |
|---|---|
| Same direction as classical (ML easier than real) | Robust carrier-source effect across detector classes. Closes the biggest reviewer concern. |
| Opposite direction or null | More interesting: learned detectors compensate for cover-source heterogeneity that classical methods cannot. Becomes a stronger result. |
| Mixed across cells | Same nuanced story as RQ4. Discuss honestly. |

In all three cases the experiment is publishable — the result is only
"bad" if SRNet fails to train (val-AUC stuck at 0.5), which would
indicate a bug, not a finding.
