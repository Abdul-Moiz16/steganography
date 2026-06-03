# Carrier-Source Steganalysis Pipeline

> Does the source of a carrier image (real photograph vs. AI-generated) affect
> how detectable steganographic embedding is?

This repository implements an end-to-end steganographic embedding and detection
pipeline for comparing real-photograph vs. diffusion-generated carriers
(SDXL 1.0, FLUX.1-schnell) under non-adaptive LSB-style embeddings, with a
web-based explorer for visualising results.

## Paper

The final paper is at
[`docs/report/final_report_draft_v4.pdf`](docs/report/final_report_draft_v4.pdf)
(LaTeX source: `final_report_draft_v4.tex`). Headline findings:

- Across 3{,}000 caption-matched image groups and six training-free detectors,
  the carrier-source effect is small (pooled $|\Delta_\text{AUC}|\!\approx\!0.013$),
  payload-dependent, and consistently signed toward AI carriers being easier
  to attack in five of six detectors; the partial-AUC view at FPR$\leq$0.10
  amplifies the effect 3-7$\times$.
- Cross-validation on SRNet and DCTR (with an LDA ensemble) trained on a
  separate caption-matched corpus reproduces the classical pattern. A
  real-only-training ablation reveals SRNet's apparent source-invariance is a
  training-mix artefact: withholding AI carriers opens a per-source gap of
  up to 0.44 AUC on AI test images.
- A new **tile-local Westfeld $\chi^2$-DCT detector** beats the global
  baseline by +0.09 AUC on BOSSBase 1.01 (JSteg, Q=75 and Q=95) and is the
  strongest frequency-branch classical detector on our test corpus.
- A candidate cover-side variance-inflation mechanism is offered for the
  $\chi^2$-spatial reversal (operationally negligible: dissolves under pAUC).

## Table of Contents

- [Quick Start](#quick-start)
- [Stego Explorer (Web UI)](#stego-explorer-web-ui)
- [Research Questions](#research-questions)
- [Experimental Design](#experimental-design)
- [Prototype vs Full Design](#prototype-vs-full-design)
- [Pipeline Profiles](#pipeline-profiles)
- [Repository Structure](#repository-structure)
- [Manual Pipeline Steps](#manual-pipeline-steps)
- [Proposal Deviation: PixArt-α → FLUX.1-schnell](#proposal-deviation-pixart-α--flux1-schnell)
- [Notes for Teammates](#notes-for-teammates)

## Quick Start

```bash
# 1. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # macOS/Linux
# .\venv\Scripts\Activate.ps1  # Windows PowerShell

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch the explorer (serves UI + API on port 8765)
python viewer.py
```

Open `http://localhost:8765` in your browser. From the explorer you can launch
pipeline runs, monitor progress, and browse results interactively.

To run a pipeline directly from the CLI:

```bash
# Prototype run (20 groups, LSB only, medium payload — fast)
python run.py prototype

# Full design (500 groups, LSB + DCT, all payload levels)
python run.py full_design

# Use stub ML engine (no GPU/API needed — for testing)
python run.py prototype --ml-engine stub

# Explicit run ID
python run.py prototype --run-id my_experiment_001

# Override individual knobs (any subset; profile defaults fill the rest)
python run.py prototype_full --ml-engine stub \
    --n-groups 50 --active-methods lsb \
    --active-detectors rs chi_square_spatial sample_pairs \
    --active-encryption plain --jpeg-quality 95

# Validate a config without running anything
python run.py prototype --dry-run --ml-engine stub --include-bd-sens
```

All outputs are written to `runs/{profile}_{timestamp}/`, keeping each run
self-contained (covers, manifests, stego images, predictions, metrics, figures).
The runner automatically writes per-experiment contrast CSVs (`exp1`…`exp5`),
a consolidated `experiments_summary.csv`, and supplementary `wilcoxon_tests.csv`
+ `t_tests.csv` + `encryption_invariance.csv` to `metrics/` after the figures
are generated. See [`src/pipeline/README.md`](src/pipeline/README.md) for the
full knob compatibility matrix and figure-enablement rules.

To run all tests:

```bash
pytest tests/
```

## Stego Explorer (Web UI)

The explorer (`viewer.py`) provides a single-page application for managing runs:

- **Runs list** — browse all completed and active pipeline runs
- **Overview** — run configuration and experimental contract
- **Results** — research-question-oriented analysis with per-RQ comparison
  cards, AUC breakdowns, and embedded charts
- **Gallery** — cover image grid with expandable per-group detector scores,
  PSNR/SSIM quality metrics, and cover/stego separation bars
- **Conditions** — full AUC matrix (detector × method × payload × encryption)
  with foldable rows showing EER, accuracy, and FPR
- **Launch** — start new pipeline runs from the browser

Prototype runs display an orange banner noting results are not statistically
significant but validate pipeline functionality and LSB integration.

## Research Questions

| ID  | Type         | Question                                                          |
| --- | ------------ | ----------------------------------------------------------------- |
| RQ1 | Primary      | Does carrier source (real vs. AI-generated) affect detectability? |
| RQ2 | Primary      | Within AI carriers, does the generator (SDXL vs. FLUX.1) matter?  |
| RQ3 | Exploratory  | Does payload size change the detectability gap between sources?   |
| RQ4 | Exploratory  | Do spatial (LSB+PNG) and frequency (DCT+JPEG) branches differ?    |
| RQ5 | Verification | Does AES-256-CBC encryption of the payload affect detectability?  |

## Experimental Design

- **Carrier sources**: Real (COCO + Flickr30k), AI-A (SDXL 1.0), AI-B (FLUX.1-schnell)
- **Image format**: Grayscale 512×512
- **Spatial branch**: Sequential row-major LSB replacement → PNG
- **Frequency branch**: JSteg-style DCT-LSB on AC coefficients → JPEG Q=95
- **Payload levels**: 0.05 / 0.15 / 0.30 bpp (low / medium / high)
- **Encryption**: Plain (seeded uniform random bytestream) vs. AES-256-CBC
- **Classical detectors** (6): RS Analysis, Sample Pairs, Spatial χ², global DCT χ², **tile-local DCT χ² (ours)**, Calibration χ²
- **Learned detectors** (2): SRNet (spatial branch), DCTR + LDA ensemble (frequency branch); trained on a separate caption-matched corpus
- **External validation**: BOSSBase 1.01 at Q=75 and Q=95 (JSteg + OutGuess) for the tile-local detector
- **Metrics**: ROC-AUC, EER, accuracy at Youden's J, FPR at fixed 10% FNR, PSNR, SSIM; partial AUC at FPR≤0.10

### Final-run scale ($N\!=\!3{,}000$ confirmatory)

| Quantity                 | Count                                                          |
| ------------------------ | -------------------------------------------------------------- |
| Caption groups           | 3,000 (mixed COCO + Flickr30k)                                 |
| Covers per group         | 3 (real + AI-A + AI-B)                                         |
| Logical covers           | 9,000                                                          |
| Cover files on disk      | 18,000 (each logical cover stored as PNG + JPEG)               |
| Stego variants per cover | 12 (2 methods × 3 payloads × 2 encryption)                     |
| Total stego files        | 108,000                                                        |
| Classical predictions    | 648,000                                                        |
| Learned predictions      | 4 × 108,000 (2 detectors × 2 training configurations)          |

## Prototype vs Full Design

| Aspect         | Prototype                    | Full Design             |
| -------------- | ---------------------------- | ----------------------- |
| Groups         | 20                           | 500                     |
| Methods        | LSB only                     | LSB + DCT               |
| Payload levels | Low only                     | Low + Medium + High     |
| Detectors      | 3 (spatial)                  | 5 (spatial + frequency) |
| Purpose        | Validate pipeline end-to-end | Publishable results     |

## Pipeline Profiles

The pipeline supports named profiles that scope the experimental configuration:

```bash
# Prototype: fast validation run
python run.py prototype

# Full design: complete factorial experiment
python run.py full_design
```

Each run automatically downloads/generates covers, builds manifests, embeds
payloads, runs detectors, computes metrics, and generates figures. Results are
written to `runs/{profile}_{timestamp}/` with self-contained config, covers,
metrics, predictions, and figures.

## Repository Structure

```
src/
├── common/        # Shared enums, filenames, canonical paths
├── data/          # Cover download, ML generation, standardization
├── embedding/     # AES-256-CBC encryption, LSB, DCT-LSB embedding
├── detection/     # RS, Chi-Square, Sample Pairs, Calibration detectors
├── evaluation/    # Metric aggregation (ROC-AUC, EER, accuracy, PSNR/SSIM)
├── metrics/       # Quality metrics (PSNR, SSIM, FSIM, BRISQUE)
└── pipeline/      # Orchestration, profiles, CLI

run.py             # Top-level pipeline entry point
viewer.py          # HTTP server for explorer + pipeline API
public/            # Explorer web UI (HTML, CSS, JS)

runs/              # Pipeline output (one directory per run)
├── prototype_20260327_120000/
│   ├── config.json        # Run configuration snapshot
│   ├── manifests/         # covers.csv, payload_manifest.csv, stego_manifest.csv
│   ├── covers/            # Cover images (real/, ml_a/, ml_b/)
│   ├── stego/             # Stego images
│   ├── payloads/          # Payload binary files
│   ├── predictions/       # Detector score CSVs
│   ├── metrics/           # Aggregated metric tables
│   └── figures/           # Generated plots
└── ...

docs/
├── proposals/     # LaTeX/PDF proposal documents
├── slides/        # Presentation slides
└── references/    # Reference audit and downloaded papers

tests/             # Unit and integration tests
notebooks/         # Jupyter notebooks for exploration
```

## Manual Pipeline Steps

The recommended way to run the pipeline is via `python run.py <profile>`, which
handles cover preparation and orchestrates all stages automatically. All outputs
are written under `runs/{profile}_{timestamp}/`.

If you need to run individual low-level CLI stages against an existing run
directory (e.g. `runs/prototype_20260327_120000`):

```bash
RUN=runs/prototype_20260327_120000

# Build payload manifest
python -m src.pipeline.cli --project-root . build-payload-manifest \
    --covers-manifest $RUN/manifests/covers.csv

# Build stego manifest
python -m src.pipeline.cli --project-root . build-stego-manifest \
    --covers-manifest $RUN/manifests/covers.csv \
    --payload-manifest $RUN/manifests/payload_manifest.csv

# Run embedding
python -m src.pipeline.cli --project-root . run-embedding-stage \
    --stego-manifest $RUN/manifests/stego_manifest.csv --execute

# Run detectors
python -m src.pipeline.cli --project-root . run-detectors \
    --stego-manifest $RUN/manifests/stego_manifest.csv --execute

# Compute metrics
python -m src.pipeline.cli --project-root . compute-metrics \
    --predictions $RUN/predictions/predictions.csv

# Generate plots
python -m src.pipeline.cli --project-root . plot-metrics \
    --metrics-dir $RUN/metrics --figures-dir $RUN/figures
```

For HuggingFace Inference API access, set your token in `.env`:

```bash
echo 'HF_TOKEN=hf_your_token_here' > .env
```

## Proposal Deviation: PixArt-α → FLUX.1-schnell

The proposal specifies PixArt-α as the ML-B generator. During implementation we
discovered PixArt-α is unavailable on the HuggingFace Inference API and its
weights download extremely slowly. We replaced it with **FLUX.1-schnell**.

This preserves the experimental design because both are Diffusion Transformer
(DiT) architectures, the property that matters for RQ2 (contrasting UNet-based
SDXL against a transformer-based generator). FLUX.1-schnell is also widely
adopted, API-accessible, and actively maintained.

## References

A complete list of references can be found in the Project Proposal (`proposal_updated_3.pdf`).
All the papers we reviewed that we were able to download for later review (i.e. not behind paywalls or download restrictions), are available at `docs/references`

### Steganography & Steganalysis

- J. Fridrich, M. Goljan, and R. Du, "Reliable detection of LSB steganography in color and grayscale images," _Proc. ACM Workshop on Multimedia and Security_, 2001. (RS Analysis)
- A. Westfeld and A. Pfitzmann, "Attacks on steganographic systems," _Proc. Information Hiding_, LNCS 1768, Springer, 2000. (Chi-Square Attack)
- S. Dumitrescu, X. Wu, and Z. Wang, "Detection of LSB steganography via sample pair analysis," _IEEE Trans. Signal Processing_, vol. 51, no. 7, pp. 1995–2007, 2003. (Sample Pairs)
- J. Fridrich, M. Goljan, and D. Hogea, "Steganalysis of JPEG images: Breaking the F5 algorithm," _Proc. Information Hiding_, LNCS 2578, Springer, 2003. (Calibration Chi-Square)
- D. Upham, "JSteg," 1993. (DCT-LSB / JSteg embedding method)

### Image Generation Models

- Stability AI, "SDXL 1.0 — Stable Diffusion XL," 2023. (ML-A carrier source)
- Black Forest Labs, "FLUX.1-schnell," 2024. (ML-B carrier source, replacing PixArt-α)

### Web UI

- Google, "Material Design 3 — Design tokens and color system," https://m3.material.io/. (M3 design system used for the explorer UI)
- Google Fonts, "Material Symbols Outlined," https://fonts.google.com/icons. (Icon set)
- Google Fonts, "Inter typeface," https://fonts.google.com/specimen/Inter. (Typography)

### Datasets

- T.-Y. Lin et al., "Microsoft COCO: Common Objects in Context," _Proc. ECCV_, Springer, 2014. (Real carrier images — COCO subset)
- P. Young, A. Lai, M. Hodosh, and J. Hockenmaier, "From image descriptions to visual denotations," _TACL_, vol. 2, pp. 67–78, 2014. (Real carrier images — Flickr30k subset)

### Cryptography

- NIST, "Advanced Encryption Standard (AES)," FIPS PUB 197, 2001. (AES-256-CBC payload encryption)
