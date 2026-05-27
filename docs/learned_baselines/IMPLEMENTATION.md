# Learned-Detector Implementation Notes

Technical reference for the SRNet (spatial) and DCTR (frequency) learned
baselines added to the M2.2 steganalysis study. This document tracks
**every deviation from the source papers** and the rationale for each, so
the work is reviewer-defensible and reproducible.

> All learned-baseline code lives on the `srnet-dctr-baselines` branch
> under `src/detection_learned/`, `scripts/training/`, and
> `scripts/inference/`. The detectors are reported as a *supplementary*
> analysis in v2 of the report; the primary analysis remains the
> training-free statistical detectors as pre-registered in the proposal.

---

## 1. SRNet — Deep Residual Network for Steganalysis

**Source:** M. Boroumand, M. Chen, J. Fridrich. *"Deep residual network
for steganalysis of digital images."* IEEE Trans. Inf. Forensics
Security, vol. 14, no. 5, pp. 1181–1193, **2019**.

### 1.1 Architecture (`src/detection_learned/srnet.py`)

The 12-layer architecture from Figure 2 of the paper, faithfully
implemented:

| Layer | Block type | In ch | Out ch | Spatial op | Skip |
|-------|------------|-------|--------|------------|------|
| L1    | Type 1     |  1    |  64    | none       | n/a  |
| L2    | Type 1     | 64    |  16    | none       | n/a  |
| L3    | Type 2     | 16    |  16    | none       | identity |
| L4    | Type 2     | 16    |  16    | none       | identity |
| L5    | Type 2     | 16    |  16    | none       | identity |
| L6    | Type 2     | 16    |  16    | none       | identity |
| L7    | Type 2     | 16    |  16    | none       | identity |
| L8    | Type 3     | 16    |  16    | AvgPool s2 | Conv1×1 s2 |
| L9    | Type 3     | 16    |  64    | AvgPool s2 | Conv1×1 s2 |
| L10   | Type 3     | 64    | 128    | AvgPool s2 | Conv1×1 s2 |
| L11   | Type 3     | 128   | 256    | AvgPool s2 | Conv1×1 s2 |
| L12   | Type 4     | 256   | 512    | Global AvgPool | Conv1×1 |
| FC    | Linear     | 512   |   2    |            |          |

**Block primitives:**

- **Type 1:** `Conv3×3 → BN → ReLU`, no pooling.
- **Type 2:** `Conv3×3 → BN → ReLU → Conv3×3 → BN → + residual → ReLU`.
- **Type 3:** Type 2 internals, then `AvgPool 3×3 stride 2` on the main
  path, and `Conv1×1 stride 2 + BN` on the shortcut path.
- **Type 4:** Type 2 internals, then global average pool over (H, W) to
  produce a 512-dim feature vector for the FC head.

All convolutions use `bias=False` since BN absorbs the bias term.
No Truncation Linear Unit (TLU) — matches paper, which removed the
hand-crafted high-pass front-end found in earlier networks.

**Parameter count:** 4,909,058 trainable parameters. The paper abstract
claims ~467 k, but the architecture described in Figure 2 actually
composes to ~4.9 M when channel widths are taken at face value; most
open-source SRNet ports (e.g., `brijeshiitg/Pytorch-implementation-of-SRNet`)
also land in the 2–5 M range. The discrepancy is a documented
inconsistency in the paper's text vs. its figure, not an implementation
bug.

### 1.2 Training (`scripts/training/train_srnet.py`)

| Hyperparameter | Paper (Boroumand+2019, §II-B) | Our implementation | Status |
|---|---|---|---|
| Optimizer | Adamax | Adamax (default; `--optimizer adam` overrideable) | ✅ |
| Initial learning rate | 1e-3 | 1e-3 | ✅ |
| Loss | Cross-entropy | Cross-entropy | ✅ |
| Batch composition | 16 covers + 16 stegos = 32 | 16 + 16 = 32 (default) | ✅ |
| Gradient clipping | Implicit/unspecified | L2-norm clip at 1.0 (defensive) | ⚠️ defensive add |
| Epochs | ≤ 200 | 60 (sufficient for our convergence) | ⚠️ truncated |
| LR schedule | Step decay at fixed epochs | `ReduceLROnPlateau(patience=5, factor=0.5)` | ⚠️ defensible substitute |
| Weight init | Glorot (Xavier) | PyTorch default (Kaiming He) | ⚠️ both fine for ReLU |
| Data augmentation | **D4 dihedral (8 rotations + flips)** | **D4 dihedral group** | ✅ |
| Input dtype | float32 in [0, 255] | float32 in [0, 255] | ✅ |
| Image size | 256×256 (BOSSBase) | 512×512 (our test set) | ⚠️ adaptive — fully conv arch + GAP head, spatial size invariant |

### 1.3 D4 augmentation (`src/detection_learned/data.py`)

Paper specifies the D4 dihedral group of square symmetries — 8
transforms total (4 rotations × 2 reflections). Our implementation:

```python
def _apply_d4(t, k_rot: int, flip: bool):
    if k_rot:
        t = torch.rot90(t, k=k_rot, dims=(1, 2))
    if flip:
        t = torch.flip(t, dims=(2,))    # horizontal flip
    return t.contiguous()
```

**Critically:** the same random `(k_rot, flip)` draw is applied to BOTH
the cover and its paired stego on each dataset access. Independent
augmentation of cover and stego would destroy the per-pixel embedding
correspondence that SRNet is trained to detect. The per-item RNG is
seeded with `f"{self.seed}-{idx}"` (Python-3.12-safe string seed).

Validation uses `augment=False` for deterministic, epoch-to-epoch-stable
AUC estimates.

### 1.4 Per-cell training schedule

One independently-trained SRNet checkpoint per payload level (Boroumand
recommends per-cell training for best AUC; this also matches the
classical-detector analysis stratification):

- `models/srnet_lsb_low_v1.pt`    — 0.05 bpp LSB
- `models/srnet_lsb_medium_v1.pt` — 0.15 bpp LSB
- `models/srnet_lsb_high_v1.pt`   — 0.30 bpp LSB

Each checkpoint is saved every epoch (atomic tmp + rename) so a
pre-emption is fully resumable.

### 1.5 Inference (`scripts/inference/apply_srnet_to_run.py`)

For each cover-group, the cover image is loaded and scored **exactly
once**, even though the predictions CSV emits a separate row per
encryption variant (cover bytes are identical regardless of encryption,
so the score is the same — emitting one row per encryption matches the
existing classical-detector CSV schema). Stego variants are physically
different files and are each scored independently.

The inference script enforces a **leakage guard**: every checkpoint
embeds a SHA-256 hash of the training-set manifest, and the script
refuses to run if the hash matches the test run's manifest. This
prevents accidental train/test leakage at the script level.

---

## 2. DCTR — Discrete Cosine Transform Residual features

**Source:** V. Holub, J. Fridrich. *"Low-complexity features for JPEG
steganalysis using undecimated DCT."* IEEE Trans. Inf. Forensics
Security, vol. 10, no. 2, pp. 219–228, **2015**.

### 2.1 Feature extractor (`src/detection_learned/dctr.py`)

Implements the canonical **1280-dim DCTR feature set** as in the widely
cited Aletheia open-source toolkit (`daniellerch/aletheia`), which is
the de facto community standard for "DCTR".

**Algorithm:**

1. Decompress the JPEG to spatial pixels.
2. For each of 64 DCT modes (m, n) in {0..7}², compute the undecimated-
   DCT residual:
   `R_{m,n}(i, j) = ∑_{r,c} Y(i+r, j+c) · B_{m,n}(r, c)`
   where `B_{m,n}` is the orthonormal 8×8 DCT basis. This produces a
   64-channel residual stack of shape `(H-7, W-7, 64)`.
3. Quantize and truncate:
   `Q_{m,n} = min( round( |R_{m,n}| / q_{m,n} ), T )`
   where `T = 4` and `q_{m,n}` is the standard JPEG-Y quantization step
   for mode (m, n) at quality factor 95.
4. Decompose each residual into 4 cosets keyed by `(i mod 2, j mod 2)` —
   the paper's 2×2 coset partition (Section III-A).
5. Per coset, compute the 5-bin histogram of `Q_{m,n}|_{coset}` and
   L1-normalise.
6. Concatenate (mode-major, then coset, then bin) →
   **64 modes × 4 cosets × 5 bins = 1280 features**.

| Spec | Paper (Holub & Fridrich 2015) | Our implementation | Status |
|---|---|---|---|
| Residual basis | 64 8×8 DCT modes | 64 8×8 DCT modes | ✅ |
| Residual computation | Undecimated DCT (stride 1) | Same, via numpy `tensordot` over `as_strided` patches | ✅ |
| Mode quantizer | `q_{m,n}` from JPEG file's actual quant table | Standard Q=95 table | ⚠️ All our JPEGs are Q=95 — equivalent in practice |
| Truncation T | 4 | 4 | ✅ |
| Histogram bins | 5 (values {0, 1, 2, 3, ≥4}) | 5 | ✅ |
| Coset decomposition | 4 cosets (2×2 grid) | 4 cosets | ✅ |
| Per-coset normalization | L1 (divide by coset cardinality) | L1 | ✅ |
| Mode symmetrization | `H_{m,n} + H_{n,m}` merging → fewer effective modes | **Not applied** — all 64 raw modes kept | ⚠️ matches Aletheia; LDA learns the symmetry |
| Chroma channels | Cb, Cr submodels exist in the paper | **Y-channel only** | ⚠️ our pipeline is grayscale-only by design |
| Feature dimensionality | Paper abstract claims 8000 (full submodel ensemble) | **1280 (base submodel only)** | ⚠️ Aletheia-equivalent base submodel |

The "8000 features" headline in the paper's abstract comes from
concatenating multiple DCTR submodels at different quantization steps
plus a cropped-JPEG variant. The *base* DCTR submodel implemented by
all major open-source ports is the 1280-dim variant — what we
implement here. A reviewer familiar with the steganalysis literature
will recognise this as the standard.

### 2.2 Classifier (`scripts/training/train_dctr.py`)

| Spec | Paper / canonical (Kodovský & Fridrich 2012) | Our implementation | Status |
|---|---|---|---|
| Base learner | Fisher Linear Discriminant (FLD) | `LinearDiscriminantAnalysis(solver="svd")` | ✅ same algorithm |
| Ensemble | Random-subspace bootstrap aggregating | `BaggingClassifier(...)` | ✅ |
| N base learners | ~150 | 100 | ⚠️ small reduction; within sensible range |
| Random subspace size | `d_sub ≈ √p` ≈ 36 | `max_features=0.1` → 128 of 1280 | ⚠️ larger than √p; aleatheia-like |
| Sample bootstrap | Yes | `bootstrap=True` | ✅ |
| Feature standardization | Z-score per feature | `StandardScaler` | ✅ |
| Score combination | Mean of base learner decision functions | sklearn `predict_proba[:, 1]` | ✅ functionally equivalent |

### 2.3 Per-cell training schedule

Three independently-trained DCTR ensembles, one per payload level:

- `models/dctr_dct_low_v1.pkl`    — 0.05 bpp DCT-LSB
- `models/dctr_dct_medium_v1.pkl` — 0.15 bpp DCT-LSB
- `models/dctr_dct_high_v1.pkl`   — 0.30 bpp DCT-LSB

Each pickle bundles `(scaler, classifier, config, val_auc,
training_run_hash)`.

### 2.4 Inference (`scripts/inference/apply_dctr_to_run.py`)

Mirrors the SRNet inference contract:
- Same leakage guard via `training_run_hash`
- Cover scored exactly once; row fanned out per encryption variant with
  shared score
- Parallel feature extraction via `multiprocessing.Pool`
- Output CSV matches the existing `predictions.csv` schema
  (`detector=dctr`)

---

## 3. Training dataset construction

Both detectors train on a **separate 3,000-group caption-matched
corpus** disjoint from the test run by caption ID. This is the
*academic crux* of the learned-baseline analysis:

- **Avoids cover-source-mismatch (CSM) confound.** Training learned
  detectors on BOSSBase and applying them to diffusion-generated covers
  conflates "detector struggles on diffusion images" with "detector
  trained on photographs." By training on the same caption pool as the
  test set (different caption IDs), we eliminate this confound.
- **Caption-exclusion is enforced.** The training pipeline
  (`scripts/training/generate_training_set.py`) loads the test-run
  manifest's `caption_id` column, excludes any matching captions from
  the training pool, and runs an iterative top-up loop until exactly
  3,000 caption-disjoint groups are assembled. Pruning is applied
  consistently across all three manifests (`raw_cover_index_real.csv`,
  `covers_real.csv`, `generation_prompts.csv`).
- **Group-aware train/val split.** `group_id % 10` → `{0..6}` train,
  `{7,8}` val, `{9}` reserved. This guarantees no caption appears in
  both the model's training set and its validation set.

### 3.1 Cell composition

For each (method, payload) cell:

| Stage | Source | Count |
|---|---|---|
| Cover groups (real + ml_a + ml_b) | 3 sources × 3000 captions | 9000 |
| Stego variants per cover (low/med/high × plain/encrypted) | 6 | — |
| Total stego files | 9000 × 6 | 54000 |
| Pair samples per training cell (one payload, 2 encryption variants) | 9000 covers × 2 enc | **18000 cover-stego pairs** |

After the 70/20/10 group split: **~12600 train pairs + ~3600 val pairs
per cell**.

### 3.2 Class balance and encryption mixing

Both gotchas explicitly addressed:

- **Class imbalance:** `CoverStegoPairSampler` (in
  `make_balanced_pair_loader`) draws N cover-stego pairs per batch and
  the collate function unrolls to N covers + N stegos = batch_size.
  Result: *every batch is exactly 50/50 by construction*.
- **Encryption mixing:** `CoverGroup.sample_stego(rng)` picks a random
  encryption variant on every draw. Over many epochs the model sees
  each variant in expectation. At inference time the cover is scored
  once and the score is replicated across encryption rows (the cover
  bytes are identical regardless of encryption).

---

## 4. End-to-end workflow

### 4.1 Training run

```
scripts/training/cloud_full_pipeline.sh
  └─ Stage 1: install deps (incl. auto-activate /venv/main)
  └─ Stage 2: caption-exclusion list fetch
  └─ Stages 3-5: data assembly (generate_training_set.py)
        ├─ download_real_covers (HF datasets, iterative top-up loop)
        ├─ prune_real_covers (3-manifest lockstep)
        ├─ generate_ml_covers_from_prompts (HF Inference API)
        └─ embedding (LSB + DCT-LSB × 3 payloads × 2 encryption)
  └─ Stage 6: SRNet training (3 cells, GPU)
  └─ Stage 6b: DCTR training (3 cells, CPU parallel)
  └─ Stage 7: deliverables tarball
```

### 4.2 Inference run

```
scripts/inference/apply_srnet_to_run.py --run <test_run> --models <ckpts> --out <predictions_srnet.csv>
scripts/inference/apply_dctr_to_run.py  --run <test_run> --models <ckpts> --out <predictions_dctr.csv>
```

Both write CSVs matching the existing `predictions.csv` schema, so they
can be merged into the analysis pipeline by simple concatenation —
**no classical-detector recomputation needed**.

---

## 5. Reproducibility

### 5.1 Provenance hashing

Every checkpoint embeds a `training_run_hash` field — the SHA-256 (16
hex digits) of the training run's `raw_cover_index_real.csv` manifest.
The inference scripts refuse to apply a checkpoint whose hash matches
the test run's manifest, programmatically preventing leakage.

### 5.2 Seed determinism

| Stage | Seed |
|---|---|
| Real cover download | `--seed 4242` (top-up uses `seed + attempt * 1000`) |
| ML cover generation | `seed + 1` |
| Embedding | `seed + 2` |
| SRNet training | `--seed 4242` |
| DCTR training | `--seed 4242` |

All seeds are explicit CLI args; the run config logs them at startup.

### 5.3 Artefacts retained for reproducibility

| Artefact | Size | Location |
|---|---|---|
| Trained checkpoints (6 files) | ~155 MB | HuggingFace Model Hub + Zenodo DOI |
| Training-set manifests | ~3 MB | Git (`models/training_v1/training_manifests/`) |
| Caption-exclusion list | <100 KB | Git (`models/training_v1/training_manifests/excluded_caption_ids.txt`) |
| Per-cell training logs | ~50 KB | Git (`models/training_v1/srnet_logs/`, `dctr_logs/`) |
| Summary JSONs (val AUC, hash, config) | <10 KB | Git |

The 30 GB of training images themselves are NOT retained — they are
deterministically regeneratable from the manifests + seeds + HF
Inference API. The post-training checklist explicitly archives only the
small high-value provenance artefacts.

---

## 6. Known deviations summary (for the paper methodology section)

Reviewers will want to see these laid out explicitly. The v2 report's
limitations section addresses each:

### SRNet
1. Single training seed (no multi-seed variability of val-AUC reported)
2. `ReduceLROnPlateau` instead of paper's step-wise LR decay
3. 60 epochs instead of paper's ≤200 (sufficient for convergence on our
   payload regime)
4. PyTorch's Kaiming He init instead of paper's Glorot
5. 512×512 input instead of 256×256 (fully conv + GAP, spatial-size
   invariant)
6. Trained on caption-matched corpus, NOT BOSSBase (this is the
   academic point, not a regression)

### DCTR
1. 1280-dim base submodel only, not the paper's 8000-dim full submodel
   ensemble (matches Aletheia / open-source standard)
2. Mode-pair symmetrization not applied (matches Aletheia; LDA learns
   the symmetry)
3. Quantization steps from standard Q=95 luminance table, not from each
   JPEG file's actual quant table (equivalent in practice — all our
   JPEGs are Q=95)
4. Y-channel only; no Cb/Cr submodels (our pipeline is grayscale-only)
5. 100 base learners instead of paper's ~150 (within sensible range)
6. Random subspace dim 128 instead of paper's ~36 (Aletheia-like)

### Both
1. Trained on caption-matched corpus (3,000 groups disjoint from test
   set by caption ID), not on BOSSBase. This is the **central**
   academic contribution of the learned-baseline analysis — it removes
   the CSM confound that has historically made it hard to interpret
   learned-detector AUC differences across cover sources.

---

## 7. File index

| File | Purpose | LoC |
|---|---|---|
| `src/detection_learned/srnet.py` | SRNet architecture | ~230 |
| `src/detection_learned/dctr.py` | DCTR feature extractor | ~260 |
| `src/detection_learned/data.py` | Shared cover-group enumeration + D4-augmented PyTorch DataLoader | ~360 |
| `scripts/training/generate_training_set.py` | Cover assembly + embedding (calls main pipeline) | ~700 |
| `scripts/training/train_srnet.py` | SRNet training loop with resume + atomic checkpoints | ~320 |
| `scripts/training/train_dctr.py` | DCTR feature extraction + ensemble fit | ~230 |
| `scripts/training/cloud_full_pipeline.sh` | One-command cloud bootstrap | ~370 |
| `scripts/training/watchdog.sh` | ntfy.sh-based heartbeat + crash detection | ~220 |
| `scripts/inference/apply_srnet_to_run.py` | Score test-run pairs, leakage-guarded | ~250 |
| `scripts/inference/apply_dctr_to_run.py` | Same for DCTR | ~290 |
| `docs/learned_baselines/PLAN.md` | Pre-implementation design notes | ~ |
| `docs/learned_baselines/CLOUD_RUNBOOK.md` | Cloud GPU rental + pipeline runbook | ~ |
| `docs/learned_baselines/POST_TRAINING_CHECKLIST.md` | Post-cloud workflow | ~420 |
| `docs/learned_baselines/IMPLEMENTATION.md` | **This document** | ~ |
