# Carrier-Source Steganalysis Pipeline

> Does the source of a carrier image (real photograph vs. ML-generated) affect
> how detectable steganographic embedding is?

This repository implements an end-to-end steganographic embedding and detection
pipeline for comparing carrier sources, with a web-based explorer for
visualizing results.

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
# Prototype run (20 groups, LSB only, low payload — fast)
python -m src.pipeline.cli --project-root . run-all \
    --covers-manifest data/manifests/covers_master.csv \
    --profile prototype --execute-embeddings --execute-detectors

# Full design (500 groups, LSB + DCT, all payload levels)
python -m src.pipeline.cli --project-root . run-all \
    --covers-manifest data/manifests/covers_master.csv \
    --profile full_design --execute-embeddings --execute-detectors
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
| RQ1 | Primary      | Does carrier source (real vs. ML-generated) affect detectability? |
| RQ2 | Primary      | Within ML carriers, does the generator (SDXL vs. FLUX.1) matter?  |
| RQ3 | Exploratory  | Does payload size change the detectability gap between sources?   |
| RQ4 | Exploratory  | Do spatial (LSB+PNG) and frequency (DCT+JPEG) branches differ?    |
| RQ5 | Verification | Does AES-256-CBC encryption of the payload affect detectability?  |

## Experimental Design

- **Carrier sources**: Real (COCO + Flickr30k), ML-A (SDXL 1.0), ML-B (FLUX.1-schnell)
- **Image format**: Grayscale 512×512
- **Spatial branch**: Sequential row-major LSB replacement → PNG
- **Frequency branch**: JSteg-style DCT-LSB on AC coefficients → JPEG Q=95
- **Payload levels**: Low (25%), Medium (50%), High (75%) fill rate
- **Encryption**: Plain vs. AES-256-CBC
- **Detectors**: RS Analysis, Chi-Square (Spatial), Sample Pairs, Chi-Square (DCT), Calibration Chi-Square
- **Metrics**: ROC-AUC, EER, accuracy at Youden's J, FPR at fixed 10% FNR, PSNR, SSIM

### Full design scale

| Quantity                 | Count                                      |
| ------------------------ | ------------------------------------------ |
| Groups                   | 500 (300 COCO + 200 Flickr30k)             |
| Covers per group         | 3 (real + ML-A + ML-B)                     |
| Total covers             | 1,500                                      |
| Stego variants per cover | 12 (2 methods × 3 payloads × 2 encryption) |
| Total stego images       | 18,000                                     |

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
python -m src.pipeline.cli --project-root . run-all \
    --covers-manifest data/manifests/covers_master.csv \
    --profile prototype --execute-embeddings --execute-detectors

# Full design: complete factorial experiment
python -m src.pipeline.cli --project-root . run-all \
    --covers-manifest data/manifests/covers_master.csv \
    --profile full_design --execute-embeddings --execute-detectors
```

Results are written to `runs/{profile}_{timestamp}/` with self-contained
config, metrics, predictions, and cover manifests.

## Repository Structure

```
src/
├── common/        # Shared enums, filenames, canonical paths
├── data/          # Cover download, ML generation, standardization
├── embedding/     # AES-256-CBC encryption, LSB, DCT-LSB embedding
├── detection/     # RS, Chi-Square, Sample Pairs, Calibration detectors
├── evaluation/    # Metric aggregation (ROC-AUC, EER, accuracy, PSNR/SSIM)
└── pipeline/      # Orchestration, profiles, CLI

public/            # Explorer web UI (HTML, CSS, JS)
viewer.py          # HTTP server for explorer + pipeline API
runs/              # Pipeline output (one directory per run)

docs/
├── proposals/     # LaTeX/PDF proposal documents
├── slides/        # Presentation slides
└── references/    # Reference audit and downloaded papers

tests/             # Unit and integration tests
notebooks/         # Jupyter notebooks for exploration
```

## Manual Pipeline Steps

If you need to run individual stages rather than `run-all`:

```bash
# Initialize directory layout
python -m src.pipeline.cli --project-root . init-layout

# Download real images (prototype: 12 COCO + 8 Flickr30k = 20 groups)
python -m src.data.download_real_covers --project-root . --coco-target 12 --flickr-target 8

# Generate ML covers
python -m src.data.generate_ml_covers --project-root . \
    --prompts-csv data/manifests/generation_prompts.csv \
    --engine inference_api --max-groups 20

# Merge cover manifests
python -m src.data.merge_covers_master --project-root . --expected-groups 20

# Build payload manifest
python -m src.pipeline.cli --project-root . build-payload-manifest \
    --covers-manifest data/manifests/covers_master.csv

# Build stego manifest
python -m src.pipeline.cli --project-root . build-stego-manifest \
    --covers-manifest data/manifests/covers_master.csv \
    --payload-manifest data/manifests/payload_manifest.csv

# Run embedding
python -m src.pipeline.cli --project-root . run-embedding-stage \
    --stego-manifest data/manifests/stego_manifest.csv

# Run detectors
python -m src.pipeline.cli --project-root . run-detectors \
    --stego-manifest data/manifests/stego_manifest.csv

# Compute metrics
python -m src.pipeline.cli --project-root . compute-metrics \
    --predictions results/predictions/predictions.csv

# Generate plots
python -m src.pipeline.cli --project-root . plot-metrics
```

For HuggingFace Inference API access, authenticate first:

```bash
python -c "from huggingface_hub import login; login()"
```

## Proposal Deviation: PixArt-α → FLUX.1-schnell

The proposal specifies PixArt-α as the ML-B generator. During implementation we
discovered PixArt-α is unavailable on the HuggingFace Inference API and its
weights download extremely slowly. We replaced it with **FLUX.1-schnell**.

This preserves the experimental design because both are Diffusion Transformer
(DiT) architectures, the property that matters for RQ2 (contrasting UNet-based
SDXL against a transformer-based generator). FLUX.1-schnell is also widely
adopted, API-accessible, and actively maintained.

## AI Disclosure

> **Note:** Claude Sonnet 4.6 (Anthropic) was used to convert the project report
> from latex into the HTML document served by the explorer
> (`public/docs-content.html`). The pipeline, detectors, evaluation logic, GUI and
> all research code are human-written. The work was divided between teammates.

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
