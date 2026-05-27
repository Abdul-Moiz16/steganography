#!/usr/bin/env bash
# V2a ablation: real-only training corpus, end-to-end on Vast.ai.
#
# This is a SUPPLEMENTARY ablation that pairs with V1 (the source-balanced
# training from runs/training_v1).  The goal is to disentangle two
# possible explanations for SRNet's near-zero per-source AUC variation
# observed in V1:
#   (a) genuine architectural source-invariance: a CNN trained on the
#       cover/stego objective abstracts away source-correlated features
#       regardless of which sources it sees during training.
#   (b) balanced-training artefact: V1 saw real / SDXL / FLUX in 1:1:1
#       proportion, so it had no incentive to learn source-specific
#       features in the first place.
#
# V2a-B trains SRNet and DCTR on REAL-ONLY carriers (Flickr30k + COCO)
# with the same per-checkpoint sample count as V1 (~18.9k train,
# ~5.3k val).  If the resulting models still score AUC near V1's on
# the AI-generated halves of the existing test corpus, (a) wins.  If
# they drop substantially on ml_a / ml_b cells, (b) wins.  Either
# outcome is publishable.
#
# Design constraint: the 3,000 caption_ids used in the test run
# (runs/prototype_full_20260513_005357_p8765) MUST NOT appear in the
# V2a training corpus.  The --exclude-captions-from flag enforces this
# at caption-id level; the train_v2a output directory is physically
# disjoint from the test corpus on disk.
#
# Usage
# -----
# On the Vast.ai instance, ideally inside tmux / screen so it survives
# SSH disconnects:
#
#     cd /workspace/m2-2_steganography
#     nohup bash scripts/training/cloud_v2a_pipeline.sh \
#         > logs/v2a/00_orchestrator.log 2>&1 &
#     tail -f logs/v2a/00_orchestrator.log
#
# Total wall-clock: ~6h (1h generation + 4h SRNet + 30 min DCTR
# + 30 min inference).  Cost at typical Vast.ai RTX 5880 Ada rates: ~$5.

set -euo pipefail

# ---------------- Config ----------------
PROJECT_ROOT="/workspace/m2-2_steganography"
PY="/venv/main/bin/python"
TEST_RUN="$PROJECT_ROOT/runs/prototype_full_20260513_005357_p8765"
V2A_RUN="$PROJECT_ROOT/runs/training_v2a"
SEED=4242
N_GROUPS=9000           # 3x V1 to keep per-checkpoint sample count matched
LOG_DIR="$PROJECT_ROOT/logs/v2a"
MODELS_DIR="$PROJECT_ROOT/models/training_v2a"

cd "$PROJECT_ROOT"
mkdir -p "$LOG_DIR" "$MODELS_DIR"

banner() { printf "\n============================================================\n%s\n============================================================\n" "$1"; }

# ---------------- 0. git pull ----------------
banner "Phase 0: git pull"
git fetch origin
git pull --ff-only origin srnet-dctr-baselines
echo "HEAD: $(git log --oneline -1)"

# ---------------- 1. Generate real-only training corpus ----------------
banner "Phase 1: generate real-only training corpus (n=$N_GROUPS captions)"
if [[ -d "$V2A_RUN/manifests" && -s "$V2A_RUN/manifests/covers.csv" ]]; then
    echo "  found existing $V2A_RUN -- skipping generation"
    echo "  (delete $V2A_RUN if you want a fresh regenerate)"
else
    "$PY" scripts/training/generate_training_set.py \
        --n-groups "$N_GROUPS" \
        --seed "$SEED" \
        --out-run "$V2A_RUN" \
        --exclude-captions-from "$TEST_RUN" \
        --skip-ml \
        2>&1 | tee "$LOG_DIR/01_generate.log"
fi

# ---------------- 2. Sanity check: disjointness + source-only ----------------
banner "Phase 2: sanity check (disjointness + per-source counts)"
TRAIN_CAPS=$(awk -F, 'NR>1 {print $5}' "$V2A_RUN/manifests/covers.csv" | sort -u)
TEST_CAPS=$(awk -F, 'NR>1 {print $5}' "$TEST_RUN/manifests/covers.csv" | sort -u)
N_TRAIN=$(echo "$TRAIN_CAPS" | wc -l | tr -d ' ')
N_TEST=$(echo "$TEST_CAPS" | wc -l | tr -d ' ')
N_OVERLAP=$(comm -12 <(echo "$TRAIN_CAPS") <(echo "$TEST_CAPS") | wc -l | tr -d ' ')
echo "  train caption_ids:    $N_TRAIN"
echo "  test  caption_ids:    $N_TEST"
echo "  caption_id overlap:   $N_OVERLAP  (MUST be 0)"
if [[ "$N_OVERLAP" -ne 0 ]]; then
    echo "FATAL: caption overlap > 0 -- train/test leakage detected, aborting."
    exit 2
fi
echo "  per-source breakdown in V2a covers.csv:"
awk -F, 'NR>1 {print "    " $2}' "$V2A_RUN/manifests/covers.csv" | sort | uniq -c
N_NON_REAL=$(awk -F, 'NR>1 && $2 != "real" {print}' "$V2A_RUN/manifests/covers.csv" | wc -l | tr -d ' ')
if [[ "$N_NON_REAL" -ne 0 ]]; then
    echo "FATAL: $N_NON_REAL non-real rows in V2a covers.csv -- --skip-ml did not work."
    exit 2
fi
echo "  ok: all sources are 'real'"

# ---------------- 3. Train SRNet x 3 payloads ----------------
banner "Phase 3: train SRNet x 3 payloads (~1.3h each, ~4h total)"
for payload in low medium high; do
    OUT="$MODELS_DIR/srnet_lsb_${payload}_v2a.pt"
    LOG="$LOG_DIR/03_srnet_${payload}.log"
    echo "--- SRNet $payload --> $OUT ---"
    "$PY" scripts/training/train_srnet.py \
        --training-run "$V2A_RUN" \
        --method lsb --payload "$payload" \
        --epochs 60 --batch-size 32 \
        --lr 1e-3 --optimizer adamax --grad-clip 1.0 \
        --device cuda \
        --seed "$SEED" \
        --resume "$OUT" \
        --out "$OUT" \
        2>&1 | tee "$LOG"
done

# ---------------- 4. Train DCTR x 3 payloads ----------------
banner "Phase 4: train DCTR x 3 payloads (~10 min each)"
NCPU=$(nproc)
NW=$(( NCPU > 16 ? 16 : NCPU ))
for payload in low medium high; do
    OUT="$MODELS_DIR/dctr_dct_${payload}_v2a.pkl"
    LOG="$LOG_DIR/04_dctr_${payload}.log"
    echo "--- DCTR $payload --> $OUT (n-workers=$NW) ---"
    OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2 \
    "$PY" scripts/training/train_dctr.py \
        --training-run "$V2A_RUN" \
        --method dct --payload "$payload" \
        --out "$OUT" \
        --n-workers "$NW" \
        --seed "$SEED" \
        2>&1 | tee "$LOG"
done

# ---------------- 5. Per-cell val-AUC sanity ----------------
banner "Phase 5: per-cell validation AUCs"
for f in "$MODELS_DIR"/*.summary.json; do
    "$PY" -c "
import json
d = json.load(open('$f'))
cfg = d['config']
auc = d.get('best_val_auc', d.get('val_auc'))
n_train = d.get('n_train', '?')
n_val = d.get('n_val', '?')
print(f'  {cfg[\"method\"]}/{cfg[\"payload\"]}: val_auc={auc:.4f}  n_train={n_train}  n_val={n_val}  hash={d.get(\"training_run_hash\",\"?\")}')
"
done

# ---------------- 6. Apply SRNet-v2a to the existing test corpus ----------------
banner "Phase 6a: apply SRNet-v2a to test corpus"
SRNET_OUT="$TEST_RUN/predictions/predictions_srnet_v2a.csv"
"$PY" scripts/inference/apply_srnet_to_run.py \
    --run "$TEST_RUN" \
    --models "$MODELS_DIR/srnet_lsb_low_v2a.pt" \
             "$MODELS_DIR/srnet_lsb_medium_v2a.pt" \
             "$MODELS_DIR/srnet_lsb_high_v2a.pt" \
    --out "$SRNET_OUT" \
    --device cuda \
    2>&1 | tee "$LOG_DIR/06_apply_srnet.log"

# ---------------- 7. Apply DCTR-v2a to the existing test corpus ----------------
banner "Phase 6b: apply DCTR-v2a to test corpus"
DCTR_OUT="$TEST_RUN/predictions/predictions_dctr_v2a.csv"
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2 \
"$PY" scripts/inference/apply_dctr_to_run.py \
    --run "$TEST_RUN" \
    --models "$MODELS_DIR/dctr_dct_low_v2a.pkl" \
             "$MODELS_DIR/dctr_dct_medium_v2a.pkl" \
             "$MODELS_DIR/dctr_dct_high_v2a.pkl" \
    --out "$DCTR_OUT" \
    --n-workers "$NW" \
    2>&1 | tee "$LOG_DIR/06_apply_dctr.log"

# ---------------- 8. Summary + scp suggestions ----------------
banner "DONE -- V2a-B pipeline complete"
echo ""
echo "Checkpoints (pull back to laptop models/training_v2a/):"
ls -lh "$MODELS_DIR/"
echo ""
echo "Test-corpus predictions (pull back to laptop runs/<test>/predictions/):"
wc -l "$SRNET_OUT" "$DCTR_OUT" 2>/dev/null
ls -lh "$SRNET_OUT" "$DCTR_OUT"
echo ""
echo "Logs are in $LOG_DIR/"
echo ""
echo "============================================================"
echo "scp commands to run ON THE LAPTOP:"
echo "============================================================"
cat <<EOSCP
  # 1) Checkpoints + summary JSONs (~70 MB)
  mkdir -p models/training_v2a
  scp -P 16523 'root@185.17.198.196:/workspace/m2-2_steganography/models/training_v2a/*' models/training_v2a/

  # 2) Test predictions (~10 MB)
  scp -P 16523 'root@185.17.198.196:/workspace/m2-2_steganography/runs/prototype_full_20260513_005357_p8765/predictions/predictions_*_v2a.csv' runs/prototype_full_20260513_005357_p8765/predictions/

  # 3) Training manifests for provenance (~5 MB)
  scp -P 16523 -r 'root@185.17.198.196:/workspace/m2-2_steganography/runs/training_v2a/manifests' models/training_v2a/training_v2a_manifests

  # 4) Run learned_analysis with the v2a predictions (writes learned_shadow_v2a/)
  venv312/bin/python scripts/inference/learned_analysis.py \\
      --run runs/prototype_full_20260513_005357_p8765 \\
      --srnet-csv runs/prototype_full_20260513_005357_p8765/predictions/predictions_srnet_v2a.csv \\
      --dctr-csv  runs/prototype_full_20260513_005357_p8765/predictions/predictions_dctr_v2a.csv \\
      --shadow-name learned_shadow_v2a

  # 5) Compare V1 vs V2a per-source AUCs side by side
  diff <(jq -r '.verdicts | to_entries[] | "\(.key) \(.value.verdict) \(.value.pooled_diff)"' \\
            runs/prototype_full_20260513_005357_p8765/learned_shadow/metrics/rq_verdicts.json) \\
       <(jq -r '.verdicts | to_entries[] | "\(.key) \(.value.verdict) \(.value.pooled_diff)"' \\
            runs/prototype_full_20260513_005357_p8765/learned_shadow_v2a/metrics/rq_verdicts.json)
EOSCP
echo ""
echo "Once predictions are local, the Vast.ai instance can be destroyed."
