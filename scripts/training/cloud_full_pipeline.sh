#!/usr/bin/env bash
# Cloud bootstrap: run the full SRNet-baseline pipeline on a rented GPU.
#
# Stages (each is idempotent / resumable on re-run):
#   1. Install Python deps
#   2. Download real covers (HF datasets, ~15 min)
#   3. Generate ML covers (diffusers on the local GPU, ~3h)
#   4. Embed LSB+DCT stegos (CPU multiprocessing, ~1.5h on 16 cores)
#   5. Train SRNet on LSB/{low,medium,high} (~10-15h GPU)
#
# Designed to be re-run safely after a Vast.ai pre-emption: every stage
# checks for prior work on disk and skips what's already done.
#
# Usage on the cloud instance:
#   cd /workspace/m2-2-steg
#   bash scripts/training/cloud_full_pipeline.sh \
#       --n-groups 3500 \
#       --run-id training_v1 \
#       --exclude-from runs/prototype_full_20260513_005357_p8765
#
# Re-running after a pre-emption: same command. Existing files trigger
# the skip-* flags automatically.

set -euo pipefail

# ---------------- Arg parsing ----------------
N_GROUPS=3500
RUN_ID="training_v1"
EXCLUDE_FROM=""
SEED=4242
EPOCHS=60
BATCH_SIZE=16

while [[ $# -gt 0 ]]; do
    case $1 in
        --n-groups) N_GROUPS="$2"; shift 2 ;;
        --run-id) RUN_ID="$2"; shift 2 ;;
        --exclude-from) EXCLUDE_FROM="$2"; shift 2 ;;
        --seed) SEED="$2"; shift 2 ;;
        --epochs) EPOCHS="$2"; shift 2 ;;
        --batch-size) BATCH_SIZE="$2"; shift 2 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

RUN_DIR="runs/$RUN_ID"
mkdir -p "$RUN_DIR" models

echo "[cloud] === Stage 0: install Python deps ==="
if ! python -c "import torch, diffusers" 2>/dev/null; then
    pip install -q -r requirements.txt -r requirements_learned.txt
fi

# Verify GPU is visible to torch
python - <<'PY'
import torch
assert torch.cuda.is_available(), "CUDA not available on this instance"
print(f"  GPU: {torch.cuda.get_device_name(0)}, VRAM: {torch.cuda.get_device_properties(0).total_memory/1e9:.1f} GB")
PY

# ---------------- Stages 1-3: data assembly ----------------
echo
echo "[cloud] === Stages 1-3: training-data assembly ==="
EXCLUDE_ARG=""
if [[ -n "$EXCLUDE_FROM" ]]; then
    EXCLUDE_ARG="--exclude-captions-from $EXCLUDE_FROM"
fi

# generate_training_set.py is itself idempotent: each sub-stage checks
# whether its output already exists and skips if so. We pass --ml-engine
# diffusers to keep everything on-instance.
python scripts/training/generate_training_set.py \
    --n-groups "$N_GROUPS" \
    --out-run "$RUN_DIR" \
    --seed "$SEED" \
    --ml-engine diffusers \
    $EXCLUDE_ARG

# ---------------- Stage 4: SRNet training (3 cells) ----------------
echo
echo "[cloud] === Stage 4: SRNet training (LSB / {low,medium,high}) ==="
for payload in low medium high; do
    MODEL_PATH="models/srnet_lsb_${payload}_v1.pt"
    echo
    echo "[cloud] ----- cell: LSB / $payload -----"
    python scripts/training/train_srnet.py \
        --training-run "$RUN_DIR" \
        --method lsb \
        --payload "$payload" \
        --epochs "$EPOCHS" \
        --batch-size "$BATCH_SIZE" \
        --device cuda \
        --out "$MODEL_PATH" \
        --resume "$MODEL_PATH" \
        --seed "$SEED"
done

echo
echo "[cloud] === ALL STAGES COMPLETE ==="
echo "[cloud] Checkpoints saved in models/"
ls -lh models/srnet_lsb_*.pt
echo
echo "Next step from your laptop:"
echo "    scp -P <port> 'root@<host>:/workspace/m2-2-steg/models/srnet_lsb_*.pt' models/"
echo "Then run inference locally:"
echo "    python scripts/inference/apply_srnet_to_run.py \\"
echo "        --run runs/prototype_full_20260513_005357_p8765 \\"
echo "        --models models/srnet_lsb_*.pt \\"
echo "        --out runs/prototype_full_20260513_005357_p8765/predictions_srnet.csv"
