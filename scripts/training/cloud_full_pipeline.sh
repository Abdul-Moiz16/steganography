#!/usr/bin/env bash
# Cloud bootstrap: run the full SRNet-baseline pipeline on a rented GPU.
#
# Stages (each is idempotent / resumable on re-run):
#   1. Install Python deps
#   2. (optional) Fetch the test-run real-cover manifest for caption exclusion
#   3. Download real covers (HF datasets, ~15 min)
#   4. Generate ML covers via HF Inference API (~5h, default), or via
#      local diffusers on the GPU if --ml-engine diffusers (~3h, needs
#      ~30 GB extra disk for SDXL+FLUX weights)
#   5. Embed LSB+DCT stegos (CPU multiprocessing, ~1.5h on 16 cores)
#   6. Train SRNet on LSB/{low,medium,high} (~10-15h GPU)
#   7. Package a deliverables tarball for one-command scp back to laptop
#
# All output is also `tee`'d to logs/<run-id>/pipeline.log so a tmux
# disconnect or browser timeout cannot lose training history.
#
# Designed to be re-run safely after a Vast.ai pre-emption: every stage
# checks for prior work on disk and skips what's already done.
#
# Usage on the cloud instance:
#   cd /workspace/m2-2-steg
#   bash scripts/training/cloud_full_pipeline.sh \
#       --n-groups 3500 \
#       --run-id training_v1
#
# To enable caption exclusion against the held-out test run, pass:
#       --exclude-manifest-url <https://path/to/raw_cover_index_real.csv>
# or, after manually rsync'ing the manifest to the instance:
#       --exclude-manifest-path runs/prototype_full_<id>/manifests/raw_cover_index_real.csv

set -euo pipefail

# ---------------- Arg parsing ----------------
N_GROUPS=3500
RUN_ID="training_v1"
EXCLUDE_PATH=""
EXCLUDE_URL=""
SEED=4242
EPOCHS=60
BATCH_SIZE=16
# inference_api is the default because it matches how the test run was
# generated and saves a ~30 GB SDXL+FLUX weights download. Override with
# --ml-engine diffusers if you want maximum throughput and don't care
# about the slight inference-config drift between SDXL via HF API and
# SDXL via local diffusers (different defaults for steps / scheduler).
ML_ENGINE="inference_api"

while [[ $# -gt 0 ]]; do
    case $1 in
        --n-groups)                  N_GROUPS="$2"; shift 2 ;;
        --run-id)                    RUN_ID="$2"; shift 2 ;;
        --exclude-manifest-path)     EXCLUDE_PATH="$2"; shift 2 ;;
        --exclude-manifest-url)      EXCLUDE_URL="$2"; shift 2 ;;
        --seed)                      SEED="$2"; shift 2 ;;
        --epochs)                    EPOCHS="$2"; shift 2 ;;
        --batch-size)                BATCH_SIZE="$2"; shift 2 ;;
        --ml-engine)                 ML_ENGINE="$2"; shift 2 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

RUN_DIR="runs/$RUN_ID"
LOG_DIR="logs/$RUN_ID"
mkdir -p "$RUN_DIR" "$LOG_DIR" models
LOG_FILE="$LOG_DIR/pipeline.log"

# Redirect all subsequent stdout/stderr to a tee'd log file.
# Use process substitution so we still see output in tmux AND archive it.
exec > >(tee -a "$LOG_FILE") 2>&1

echo "============================================================"
echo "[cloud] cloud_full_pipeline.sh starting at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "[cloud]   N_GROUPS    = $N_GROUPS"
echo "[cloud]   RUN_ID      = $RUN_ID"
echo "[cloud]   SEED        = $SEED"
echo "[cloud]   EPOCHS      = $EPOCHS"
echo "[cloud]   BATCH_SIZE  = $BATCH_SIZE"
echo "[cloud]   ML_ENGINE   = $ML_ENGINE"
echo "[cloud]   EXCLUDE_URL  = ${EXCLUDE_URL:-<none>}"
echo "[cloud]   EXCLUDE_PATH = ${EXCLUDE_PATH:-<none>}"
echo "[cloud]   git HEAD    = $(git rev-parse --short HEAD 2>/dev/null || echo '<not a git checkout>')"
echo "[cloud]   git branch  = $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '<unknown>')"
echo "============================================================"
echo

# ---------------- Stage 1: install deps ----------------
echo "[cloud] === Stage 1: install Python deps ==="

# Auto-activate the cloud venv if it exists and is not already active.
# Vast.ai's PyTorch image ships a venv at /venv/main; without it, the
# `python` binary may not exist on PATH and we exit 127 before any work.
if [[ -z "${VIRTUAL_ENV:-}" ]] && [[ -f /venv/main/bin/activate ]]; then
    echo "  [cloud] activating /venv/main"
    # shellcheck disable=SC1091
    source /venv/main/bin/activate
fi
echo "  [cloud] python: $(command -v python || echo MISSING)"
echo "  [cloud] VIRTUAL_ENV: ${VIRTUAL_ENV:-<none>}"

if ! command -v python >/dev/null 2>&1; then
    echo "  [cloud] FATAL: no python on PATH. Activate your venv before running this script." >&2
    exit 1
fi

if ! python -c "import torch, diffusers, sklearn" 2>/dev/null; then
    pip install -q -r requirements.txt -r requirements_learned.txt
else
    echo "  (already installed, skipping)"
fi

# Verify GPU is visible to torch (required for SRNet training only).
python - <<'PY'
import torch
assert torch.cuda.is_available(), "CUDA not available on this instance -- abort and re-rent a GPU instance"
print(f"  GPU         : {torch.cuda.get_device_name(0)}")
print(f"  VRAM        : {torch.cuda.get_device_properties(0).total_memory/1e9:.1f} GB")
print(f"  torch       : {torch.__version__}")
PY
# If the user chose --ml-engine diffusers, sanity-check that the heavy
# deps are present so we fail fast rather than mid-generation.
if [[ "$ML_ENGINE" == "diffusers" ]]; then
    python -c "import diffusers; print(f'  diffusers   : {diffusers.__version__}')"
fi
echo

# ---------------- Stage 2 (optional): fetch caption-exclusion manifest ----------------
EXCLUDE_ARG=""
if [[ -n "$EXCLUDE_URL" ]]; then
    EXCLUDE_PATH="$LOG_DIR/excluded_real_index.csv"
    echo "[cloud] === Stage 2: fetch caption-exclusion manifest ==="
    echo "[cloud]   downloading $EXCLUDE_URL -> $EXCLUDE_PATH"
    curl -sSL -o "$EXCLUDE_PATH" "$EXCLUDE_URL"
    echo "[cloud]   fetched $(wc -l < "$EXCLUDE_PATH") rows"
    echo
fi
if [[ -n "$EXCLUDE_PATH" ]]; then
    # generate_training_set.py wants a RUN dir, not a manifest path, so we
    # synthesise a minimal run-dir with just the manifest the exclusion
    # logic reads.
    SYNTH_RUN="$LOG_DIR/excluded_synth_run"
    mkdir -p "$SYNTH_RUN/manifests"
    cp "$EXCLUDE_PATH" "$SYNTH_RUN/manifests/raw_cover_index_real.csv"
    EXCLUDE_ARG="--exclude-captions-from $SYNTH_RUN"
    echo "[cloud] caption exclusion ENABLED via $EXCLUDE_PATH"
    echo
fi

# ---------------- Stages 3-5: data assembly ----------------
echo "[cloud] === Stages 3-5: training-data assembly ==="
# generate_training_set.py is itself idempotent: each sub-stage checks
# whether its output already exists and skips if so.
python scripts/training/generate_training_set.py \
    --n-groups "$N_GROUPS" \
    --out-run "$RUN_DIR" \
    --seed "$SEED" \
    --ml-engine "$ML_ENGINE" \
    $EXCLUDE_ARG
echo

# Sanity-check: enumerate cover groups across all 6 (method, payload)
# cells and verify counts match expectations. Bails out early before
# we start a 12-hour training run if the data is malformed.
python - <<PY
from pathlib import Path
from src.detection_learned.data import enumerate_cover_groups
run = Path("$RUN_DIR")
expected_min = int($N_GROUPS * 0.9)   # allow up to 10% caption-exclusion loss
for method, payload in [("lsb","low"),("lsb","medium"),("lsb","high"),
                         ("dct","low"),("dct","medium"),("dct","high")]:
    cgs = enumerate_cover_groups(run, method=method, payload_level=payload)
    n_cov = len(cgs); n_ste = sum(len(c.stego_paths) for c in cgs)
    # 3 sources per group, so n_cov should be ~3*N_groups
    print(f"  {method:3s}/{payload:6s}: {n_cov:5d} cover-groups, {n_ste:5d} stegos")
    assert n_cov >= expected_min * 3, f"only {n_cov} cover-groups in {method}/{payload}"
print("  OK -- all 6 cells have the expected counts")
PY
echo

# ---------------- Stage 6: SRNet training (3 cells) ----------------
echo "[cloud] === Stage 6: SRNet training (LSB / {low,medium,high}) ==="
for payload in low medium high; do
    MODEL_PATH="models/srnet_lsb_${payload}_v1.pt"
    CELL_LOG="$LOG_DIR/train_srnet_lsb_${payload}.log"
    echo
    echo "[cloud] ----- cell: LSB / $payload -----"
    echo "[cloud]   started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "[cloud]   cell log: $CELL_LOG"
    python scripts/training/train_srnet.py \
        --training-run "$RUN_DIR" \
        --method lsb \
        --payload "$payload" \
        --epochs "$EPOCHS" \
        --batch-size "$BATCH_SIZE" \
        --device cuda \
        --out "$MODEL_PATH" \
        --resume "$MODEL_PATH" \
        --seed "$SEED" 2>&1 | tee "$CELL_LOG"
    echo "[cloud]   completed: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
done
echo

# ---------------- Stage 6b: DCTR training (3 cells, CPU-only) ----------------
echo "[cloud] === Stage 6b: DCTR training (DCT / {low,medium,high}) ==="
DCTR_WORKERS="${DCTR_WORKERS:-$(nproc)}"
for payload in low medium high; do
    MODEL_PATH="models/dctr_dct_${payload}_v1.pkl"
    CELL_LOG="$LOG_DIR/train_dctr_dct_${payload}.log"
    echo
    echo "[cloud] ----- cell: DCT / $payload (DCTR) -----"
    echo "[cloud]   started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "[cloud]   cell log: $CELL_LOG"
    python scripts/training/train_dctr.py \
        --training-run "$RUN_DIR" \
        --method dct \
        --payload "$payload" \
        --out "$MODEL_PATH" \
        --n-workers "$DCTR_WORKERS" \
        --seed "$SEED" 2>&1 | tee "$CELL_LOG"
    echo "[cloud]   completed: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
done
echo

# ---------------- Stage 7: deliverables bundle ----------------
echo "[cloud] === Stage 7: package deliverables ==="
DELIV_DIR="deliverables/$RUN_ID"
mkdir -p "$DELIV_DIR/models" "$DELIV_DIR/manifests" "$DELIV_DIR/logs"

# Copy the small high-value artefacts. We deliberately do NOT bundle the
# full training-run directory (~30 GB); the manifests carry enough info
# to regenerate it.
cp models/srnet_lsb_*.pt              "$DELIV_DIR/models/" 2>/dev/null || true
cp models/srnet_lsb_*.summary.json    "$DELIV_DIR/models/" 2>/dev/null || true
cp models/dctr_dct_*.pkl              "$DELIV_DIR/models/" 2>/dev/null || true
cp models/dctr_dct_*.summary.json     "$DELIV_DIR/models/" 2>/dev/null || true
cp "$RUN_DIR/.meta.json"              "$DELIV_DIR/training_run_meta.json" 2>/dev/null || true
cp -r "$RUN_DIR/manifests/"           "$DELIV_DIR/manifests/" 2>/dev/null || true
cp "$LOG_FILE"                        "$DELIV_DIR/logs/pipeline.log"
cp "$LOG_DIR"/train_srnet_*.log       "$DELIV_DIR/logs/" 2>/dev/null || true
cp "$LOG_DIR"/train_dctr_*.log        "$DELIV_DIR/logs/" 2>/dev/null || true

# Self-describing README so a future reader (or reviewer) understands
# what each file is for without rooting around in the codebase.
cat > "$DELIV_DIR/README.md" <<EOF
# SRNet training run: $RUN_ID

Generated by \`scripts/training/cloud_full_pipeline.sh\` at $(date -u +%Y-%m-%dT%H:%M:%SZ).

## Contents

- \`summary.json\` -- per-cell val-AUC, epoch counts, training-run hashes.
  Inspectable without PyTorch.
- \`training_run_meta.json\` -- config used to assemble the training set
  (n_groups, seed, ml_engine, caption-exclusion source).
- \`models/srnet_lsb_<payload>_v1.pt\` -- PyTorch state dicts plus full
  training state (optimiser + scheduler + history). Load with
  \`torch.load()\`.
- \`models/srnet_lsb_<payload>_v1.summary.json\` -- same metadata as
  the .pt but without the model weights, for quick inspection.
- \`manifests/\` -- COPY of the training run's manifests, providing
  full provenance: which captions were used, which ML model IDs and
  seeds, what payload bits and AES IVs, where every cover and stego
  came from.
- \`logs/pipeline.log\` -- full stdout from the cloud pipeline script.
- \`logs/train_srnet_lsb_<payload>.log\` -- per-cell SRNet training log
  (epoch-by-epoch train/val loss and val-AUC).
- \`logs/train_dctr_dct_<payload>.log\` -- per-cell DCTR training log
  (feature-extraction throughput, fit time, val-AUC).

## How to apply these checkpoints to a held-out test run

On your laptop, in the project root:

\`\`\`bash
python scripts/inference/apply_srnet_to_run.py \\
    --run runs/<test-run-id> \\
    --models $RUN_ID/models/srnet_lsb_low_v1.pt \\
             $RUN_ID/models/srnet_lsb_medium_v1.pt \\
             $RUN_ID/models/srnet_lsb_high_v1.pt \\
    --out runs/<test-run-id>/predictions_srnet.csv
\`\`\`

The apply script enforces a leakage guard: if the checkpoint's
\`training_run_hash\` matches the test run's manifest hash, the script
refuses to run. So you cannot accidentally evaluate on the same data
the model was trained on.

## What is **not** in this bundle (intentionally)

- The full training run directory (~30 GB of images + stegos).
  Regenerable from the manifests + seeds in this bundle. If you want
  it back, re-run \`scripts/training/generate_training_set.py\` with
  the same seed.
- The PyTorch checkpoint optimiser/scheduler state suffices for resume
  but is large; consider stripping it from the .pt before long-term
  archival if you only need inference.
EOF

# Aggregate summary across all cells (SRNet + DCTR) for one-glance inspection.
python - <<PY
import json, glob
from pathlib import Path

deliv = Path("$DELIV_DIR")
summary = {
    "run_id": "$RUN_ID",
    "n_groups_requested": $N_GROUPS,
    "seed": $SEED,
    "epochs": $EPOCHS,
    "batch_size": $BATCH_SIZE,
    "cells": {},
}
for js in sorted(glob.glob(str(deliv / "models" / "*.summary.json"))):
    s = json.loads(Path(js).read_text())
    cfg = s["config"]
    # SRNet summary uses "best_val_auc"; DCTR summary uses "val_auc".
    val_auc = s.get("best_val_auc", s.get("val_auc"))
    arch = "srnet" if "best_val_auc" in s else "dctr"
    cell = f"{arch}_{cfg['method']}_{cfg['payload']}"
    summary["cells"][cell] = {
        "architecture": arch,
        "val_auc": val_auc,
        "epochs_completed": s.get("epochs_completed"),
        "n_train": s.get("n_train"),
        "n_val": s.get("n_val"),
        "training_run_hash": s["training_run_hash"],
        "checkpoint_path": s["checkpoint_path"],
    }
(deliv / "summary.json").write_text(json.dumps(summary, indent=2))
print("[cloud]   wrote", deliv / "summary.json")
print(json.dumps(summary, indent=2))
PY

# Create a single tarball for one-command scp.
TARBALL="deliverables_${RUN_ID}.tar.gz"
tar -czf "$TARBALL" -C deliverables "$RUN_ID"
SZ=$(du -h "$TARBALL" | cut -f1)
echo "[cloud]   tarball: $TARBALL ($SZ)"
echo

# ---------------- Final report ----------------
echo "============================================================"
echo "[cloud] ALL STAGES COMPLETE at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "============================================================"
echo
echo "To retrieve everything from your laptop (single command):"
echo
echo "    scp -P <port> root@<host>:/workspace/m2-2-steg/$TARBALL ."
echo "    tar -xzf $(basename "$TARBALL")"
echo
echo "The tarball contains:"
echo "    $RUN_ID/summary.json                  # at-a-glance per-cell val-AUCs"
echo "    $RUN_ID/models/srnet_lsb_*.pt         # 3 SRNet checkpoints (spatial branch)"
echo "    $RUN_ID/models/dctr_dct_*.pkl         # 3 DCTR checkpoints (frequency branch)"
echo "    $RUN_ID/models/*.summary.json         # torch/joblib-free metadata"
echo "    $RUN_ID/manifests/                    # full provenance (which captions, which seeds)"
echo "    $RUN_ID/logs/pipeline.log             # full stdout from this run"
echo "    $RUN_ID/logs/train_srnet_*.log        # per-cell SRNet training curves"
echo "    $RUN_ID/logs/train_dctr_*.log         # per-cell DCTR training logs"
echo
echo "Then run inference locally:"
echo "    python scripts/inference/apply_srnet_to_run.py \\"
echo "        --run runs/prototype_full_20260513_005357_p8765 \\"
echo "        --models $RUN_ID/models/srnet_lsb_*.pt \\"
echo "        --out runs/prototype_full_20260513_005357_p8765/predictions_srnet.csv"
echo "    python scripts/inference/apply_dctr_to_run.py \\"
echo "        --run runs/prototype_full_20260513_005357_p8765 \\"
echo "        --models $RUN_ID/models/dctr_dct_*.pkl \\"
echo "        --out runs/prototype_full_20260513_005357_p8765/predictions_dctr.csv"
echo
echo "When you are done, REMEMBER to terminate the cloud instance."
