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
# Notifications (optional, recommended)
# -------------------------------------
# Install the "ntfy" app on your phone (iOS / Android).  Pick a private
# topic name (any random-looking string) and subscribe to it in the app.
# Then launch with NTFY_TOPIC set, e.g.:
#
#     NTFY_TOPIC=davidwh-v2a-d8f4 \
#     nohup bash scripts/training/cloud_v2a_pipeline.sh \
#         > logs/v2a/00_orchestrator.log 2>&1 &
#
# You'll get:
#   - a notification at every phase boundary (start, success, failure)
#   - a heartbeat digest every 30 minutes with the latest log line,
#     elapsed time, current phase
#   - urgent-priority notification on any verification gate failure
#
# If NTFY_TOPIC is unset the script still runs and prints all
# notifications to stdout, just without remote delivery.
#
# Usage
# -----
# On the Vast.ai instance, inside tmux/screen so it survives SSH drops:
#
#     cd /workspace/m2-2_steganography
#     mkdir -p logs/v2a
#     NTFY_TOPIC=<your-secret-topic> \
#         nohup bash scripts/training/cloud_v2a_pipeline.sh \
#             > logs/v2a/00_orchestrator.log 2>&1 &
#     tail -f logs/v2a/00_orchestrator.log
#
# Total wall-clock: ~6h.  Cost at typical Vast.ai RTX 5880 Ada rates: ~$5.

set -euo pipefail

# ---------------- Config ----------------
PROJECT_ROOT="/workspace/m2-2_steganography"
PY="/venv/main/bin/python"
TEST_RUN="$PROJECT_ROOT/runs/prototype_full_20260513_005357_p8765"
V2A_RUN="$PROJECT_ROOT/runs/training_v2a"
SEED=4242
N_GROUPS=9000
# COCO_FRACTION=0.0 -- 100% Flickr30k.  V1 used a ~49/51 COCO/Flickr30k mix
# but COCO only has ~3,997 disjoint-from-test captions in the indexed pool,
# which is below the 9450 a 0.6 fraction would need at n_groups=9000.
# Flickr30k has ~152k disjoint candidates so going 100% Flickr is safe and
# academically equivalent (both are natural-image datasets; the source-
# invariance hypothesis being tested is agnostic to the specific dataset).
COCO_FRACTION=0.0
LOG_DIR="$PROJECT_ROOT/logs/v2a"
MODELS_DIR="$PROJECT_ROOT/models/training_v2a"
EXPECTED_TEST_ROWS=108000   # per detector
NTFY_TOPIC="${NTFY_TOPIC:-}"
HEARTBEAT_SECS=1800          # 30 minutes
START_TIME=$(date +%s)

cd "$PROJECT_ROOT"
mkdir -p "$LOG_DIR" "$MODELS_DIR"

# ---------------- Helpers ----------------
banner() {
    printf "\n============================================================\n%s\n============================================================\n" "$1"
}

human_elapsed() {
    local s=$(( $(date +%s) - START_TIME ))
    printf '%dh%02dm' $((s/3600)) $(((s%3600)/60))
}

# Send a notification.  Priority is one of: min/low/default/high/urgent.
# Always echoes to stdout; only POSTs to ntfy if NTFY_TOPIC is set.
notify() {
    local title="$1"
    local msg="$2"
    local priority="${3:-default}"
    local tag="${4:-zap}"
    printf "[notify %s] %s | %s\n" "$priority" "$title" "$msg"
    if [[ -n "$NTFY_TOPIC" ]]; then
        curl -sf --max-time 10 \
             -H "Title: $title" \
             -H "Priority: $priority" \
             -H "Tags: $tag" \
             -d "$msg" \
             "https://ntfy.sh/$NTFY_TOPIC" > /dev/null 2>&1 || true
    fi
}

# Record the current phase + active log file for the heartbeat digest to read.
set_phase() {
    local phase_name="$1"
    local log_file="${2:-}"
    echo "$phase_name" > "$LOG_DIR/PHASE.txt"
    echo "$log_file"   > "$LOG_DIR/CURRENT_LOG.txt"
    notify "V2a: $phase_name" "Starting [$(human_elapsed)]" "default" "rocket"
}

# Verification gate.  Fails loudly with an urgent notification + non-zero exit.
gate_fail() {
    local what="$1"
    local detail="$2"
    notify "V2a FAILED: $what" "$detail at [$(human_elapsed)] -- see $LOG_DIR/" "urgent" "warning"
    echo "FATAL: $what -- $detail"
    exit 2
}

# Background heartbeat: every HEARTBEAT_SECS, send a status digest.
# Uses "default" priority (audible buzz on iOS) so the user notices.
# IMPORTANT: tqdm progress bars in generate_training_set / train_srnet /
# train_dctr / apply_*_to_run write thousands of refresh-frames separated
# by '\r' (carriage return) rather than '\n'.  A naive `tail -3 | tr -d '\r'`
# concatenates all of those frames into one multi-MB "line" that overruns
# ntfy's POST-body limit and silently fails the curl (eaten by `|| true`).
# We instead read only the last 8 KB of the file, translate '\r' INTO '\n'
# (so each tqdm frame becomes its own line), skip empties, take the last,
# and hard-cap at 250 chars.
heartbeat_loop() {
    while true; do
        sleep "$HEARTBEAT_SECS"
        local phase="unknown"
        local cur_log=""
        [[ -f "$LOG_DIR/PHASE.txt"   ]] && phase=$(cat "$LOG_DIR/PHASE.txt")
        [[ -f "$LOG_DIR/CURRENT_LOG.txt" ]] && cur_log=$(cat "$LOG_DIR/CURRENT_LOG.txt")
        local latest=""
        if [[ -n "$cur_log" && -f "$cur_log" ]]; then
            latest=$(tail -c 8192 "$cur_log" 2>/dev/null \
                     | tr '\r' '\n' \
                     | grep -v '^$' \
                     | tail -1 \
                     | head -c 250)
            [[ -z "$latest" ]] && latest="(no recent log output)"
        fi
        local extra=""
        # Phase-specific enrichment: live file counts for generation, latest
        # epoch line for SRNet training, progress fragment for inference.
        case "$phase" in
            *generate*)
                local nc=$(find "$V2A_RUN/covers/real"   -type f 2>/dev/null | wc -l | tr -d ' ')
                local nl=$(find "$V2A_RUN/stego/lsb"     -type f 2>/dev/null | wc -l | tr -d ' ')
                local nd=$(find "$V2A_RUN/stego/dct"     -type f 2>/dev/null | wc -l | tr -d ' ')
                extra=" | covers=$nc lsb=$nl dct=$nd"
                ;;
            *SRNet*|*srnet*)
                if [[ -n "$cur_log" && -f "$cur_log" ]]; then
                    local epoch_line=$(grep -E "epoch.*val_auc|epoch.*loss" "$cur_log" 2>/dev/null | tail -1 | head -c 200)
                    [[ -n "$epoch_line" ]] && extra=" | $epoch_line"
                fi
                ;;
            *inference*|*apply_*)
                if [[ -n "$cur_log" && -f "$cur_log" ]]; then
                    local prog=$(grep -E "[0-9]+/[0-9]+|[0-9]+%" "$cur_log" 2>/dev/null | tail -1 | head -c 200)
                    [[ -n "$prog" ]] && extra=" | $prog"
                fi
                ;;
        esac
        notify "V2a heartbeat @ $(human_elapsed)" "Phase: $phase$extra | $latest" "default" "heart"
    done
}

# ---------------- Trap for failures ----------------
on_exit() {
    local rc=$?
    if [[ -n "${HEARTBEAT_PID:-}" ]]; then
        kill "$HEARTBEAT_PID" 2>/dev/null || true
    fi
    if [[ "$rc" -ne 0 ]]; then
        local phase="unknown"
        [[ -f "$LOG_DIR/PHASE.txt" ]] && phase=$(cat "$LOG_DIR/PHASE.txt")
        notify "V2a CRASHED" "exit=$rc, last phase=$phase, elapsed=$(human_elapsed)" "urgent" "skull"
    fi
}
trap on_exit EXIT

# ---------------- Start ----------------
notify "V2a launched" "n_groups=$N_GROUPS, seed=$SEED, test=$(basename $TEST_RUN)" "high" "rocket"
heartbeat_loop &
HEARTBEAT_PID=$!

# ============================================================
# Phase 0: git pull (cheap, fail-fast on remote / network)
# ============================================================
set_phase "Phase 0: git pull"
banner "Phase 0: git pull"
git fetch origin
git pull --ff-only origin srnet-dctr-baselines
HEAD_SHORT=$(git log --oneline -1)
echo "HEAD: $HEAD_SHORT"
notify "V2a: git pull ok" "HEAD: $HEAD_SHORT" "default" "git"

# ============================================================
# Phase 0.5: verify dependencies BEFORE wasting time on downloads
# ============================================================
# Cloud instances provisioned for V1 DCTR-only inference are missing
# embedding-pipeline deps (jpeglib, cryptography, ...).  Three previous
# V2a launches crashed mid-Phase-1 after burning an hour of downloads
# because we discovered missing deps stage-by-stage.  This step does
# the full transitive import the embedding stage will need, and if
# anything fails, installs both requirements files automatically.
set_phase "Phase 0.5: verify deps"
banner "Phase 0.5: verify Python dependencies"
TRY_IMPORTS='
import sys; sys.path.insert(0, ".")
from src.pipeline.runner import PipelineRunner       # triggers cryptography, jpeglib
from src.detection_learned.srnet import SRNet         # triggers torch
from src.detection_learned.dctr import dctr_features  # triggers numpy/PIL
from src.embedding.encryption import encrypt_payload_aes_256_cbc
import jpeglib, cryptography, torch, sklearn, joblib, scipy, tqdm, PIL
print(f"OK torch={torch.__version__} cuda={torch.cuda.is_available()} jpeglib={jpeglib.__version__} cryptography={cryptography.__version__}")
'
if ! "$PY" -c "$TRY_IMPORTS" 2>&1 | tee "$LOG_DIR/00_deps_check.log"; then
    echo "  some imports failed -- installing BOTH requirements files now"
    notify "V2a: installing missing deps" "Auto-install in progress" "default" "package"
    "$PY" -m pip install --quiet -r requirements.txt 2>&1 | tee -a "$LOG_DIR/00_deps_check.log" | tail -5
    "$PY" -m pip install --quiet -r requirements_learned.txt 2>&1 | tee -a "$LOG_DIR/00_deps_check.log" | tail -5
    echo "  re-verifying..."
    "$PY" -c "$TRY_IMPORTS" 2>&1 | tee -a "$LOG_DIR/00_deps_check.log" || \
        gate_fail "Phase 0.5" "deps still missing after pip install -- see $LOG_DIR/00_deps_check.log"
fi
notify "V2a: deps OK" "$(tail -1 "$LOG_DIR/00_deps_check.log")" "default" "white_check_mark"

# ============================================================
# Phase 1: generate real-only training corpus
# ============================================================
set_phase "Phase 1: generate corpus" "$LOG_DIR/01_generate.log"
banner "Phase 1: generate real-only training corpus (n=$N_GROUPS captions)"
if [[ -d "$V2A_RUN/manifests" && -s "$V2A_RUN/manifests/covers.csv" ]]; then
    EXIST_N=$(awk 'NR>1' "$V2A_RUN/manifests/covers.csv" | wc -l | tr -d ' ')
    echo "  found existing $V2A_RUN with $EXIST_N rows -- reusing"
    notify "V2a: reusing existing corpus" "covers.csv has $EXIST_N rows" "default" "recycle"
else
    "$PY" scripts/training/generate_training_set.py \
        --n-groups "$N_GROUPS" \
        --seed "$SEED" \
        --out-run "$V2A_RUN" \
        --exclude-captions-from "$TEST_RUN" \
        --coco-fraction "$COCO_FRACTION" \
        --skip-ml \
        2>&1 | tee "$LOG_DIR/01_generate.log"
fi

# -------- gate 1: corpus content sanity --------
banner "Gate 1: verify training corpus is real-only, disjoint from test"
[[ -f "$V2A_RUN/manifests/covers.csv" ]] || gate_fail "Phase 1" "covers.csv not produced"

TRAIN_ROWS=$(awk 'NR>1' "$V2A_RUN/manifests/covers.csv" | wc -l | tr -d ' ')
echo "  train rows: $TRAIN_ROWS"
[[ "$TRAIN_ROWS" -ge $(( N_GROUPS * 80 / 100 )) ]] || \
    gate_fail "Phase 1" "covers.csv has $TRAIN_ROWS rows, expected at least $(( N_GROUPS * 80 / 100 ))"

TRAIN_CAPS=$(awk -F, 'NR>1 {print $5}' "$V2A_RUN/manifests/covers.csv" | sort -u)
TEST_CAPS=$(awk  -F, 'NR>1 {print $5}' "$TEST_RUN/manifests/covers.csv" | sort -u)
N_TRAIN=$(echo "$TRAIN_CAPS" | wc -l | tr -d ' ')
N_TEST=$(echo  "$TEST_CAPS"  | wc -l | tr -d ' ')
N_OVERLAP=$(comm -12 <(echo "$TRAIN_CAPS") <(echo "$TEST_CAPS") | wc -l | tr -d ' ')
echo "  train caption_ids:  $N_TRAIN"
echo "  test  caption_ids:  $N_TEST"
echo "  caption_id overlap: $N_OVERLAP (MUST be 0)"
[[ "$N_OVERLAP" -eq 0 ]] || gate_fail "Phase 1" "train/test caption overlap = $N_OVERLAP (leakage)"

N_NON_REAL=$(awk -F, 'NR>1 && $2 != "real" {print}' "$V2A_RUN/manifests/covers.csv" | wc -l | tr -d ' ')
echo "  non-real rows:      $N_NON_REAL (MUST be 0)"
[[ "$N_NON_REAL" -eq 0 ]] || gate_fail "Phase 1" "$N_NON_REAL non-real rows in covers.csv (--skip-ml broken?)"

# File-count sanity: covers + 6 stego variants per cover (3 payloads x 2 enc), per method
COVER_COUNT=$(find "$V2A_RUN/covers/real" -type f \( -name '*.png' -o -name '*.jpg' \) 2>/dev/null | wc -l | tr -d ' ')
LSB_STEGO_COUNT=$(find "$V2A_RUN/stego/lsb" -type f 2>/dev/null | wc -l | tr -d ' ')
DCT_STEGO_COUNT=$(find "$V2A_RUN/stego/dct" -type f 2>/dev/null | wc -l | tr -d ' ')
echo "  on-disk covers:     $COVER_COUNT"
echo "  on-disk LSB stegos: $LSB_STEGO_COUNT"
echo "  on-disk DCT stegos: $DCT_STEGO_COUNT"
[[ "$COVER_COUNT" -ge $(( TRAIN_ROWS * 2 * 80 / 100 )) ]] || \
    gate_fail "Phase 1" "cover file count $COVER_COUNT too low (expected ~$(( TRAIN_ROWS * 2 )) for png+jpg)"
[[ "$LSB_STEGO_COUNT" -ge $(( TRAIN_ROWS * 6 * 80 / 100 )) ]] || \
    gate_fail "Phase 1" "LSB stego file count $LSB_STEGO_COUNT too low (expected ~$(( TRAIN_ROWS * 6 )))"
[[ "$DCT_STEGO_COUNT" -ge $(( TRAIN_ROWS * 6 * 80 / 100 )) ]] || \
    gate_fail "Phase 1" "DCT stego file count $DCT_STEGO_COUNT too low (expected ~$(( TRAIN_ROWS * 6 )))"

notify "V2a: gate 1 OK" "train=$N_TRAIN caps, overlap=0, covers=$COVER_COUNT, lsb=$LSB_STEGO_COUNT, dct=$DCT_STEGO_COUNT" "default" "white_check_mark"

# ============================================================
# Phase 3: train SRNet x 3 payloads
# ============================================================
for payload in low medium high; do
    OUT="$MODELS_DIR/srnet_lsb_${payload}_v2a.pt"
    SUM="${OUT%.pt}.summary.json"
    LOG="$LOG_DIR/03_srnet_${payload}.log"
    set_phase "Phase 3: train SRNet $payload" "$LOG"
    banner "Phase 3: train SRNet $payload -> $OUT (~1.3h)"
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

    # -------- gate: SRNet checkpoint --------
    [[ -f "$OUT" ]] || gate_fail "Phase 3 ($payload)" "checkpoint $OUT not written"
    [[ -f "$SUM" ]] || gate_fail "Phase 3 ($payload)" "summary $SUM not written"
    VAL_AUC=$("$PY" -c "import json; d=json.load(open('$SUM')); print(d.get('best_val_auc', d.get('val_auc', 0)))")
    echo "  val_auc = $VAL_AUC"
    awk -v v="$VAL_AUC" 'BEGIN { exit (v+0 >= 0.55) ? 0 : 1 }' || \
        gate_fail "Phase 3 ($payload)" "val_auc=$VAL_AUC below 0.55 sanity floor"
    notify "V2a: SRNet $payload trained" "val_auc=$VAL_AUC, ckpt=$(basename $OUT)" "high" "trophy"
done

# ============================================================
# Phase 4: train DCTR x 3 payloads
# ============================================================
NCPU=$(nproc)
NW=$(( NCPU > 16 ? 16 : NCPU ))
echo "  using n-workers=$NW (NCPU=$NCPU)"
for payload in low medium high; do
    OUT="$MODELS_DIR/dctr_dct_${payload}_v2a.pkl"
    SUM="${OUT%.pkl}.summary.json"
    LOG="$LOG_DIR/04_dctr_${payload}.log"
    set_phase "Phase 4: train DCTR $payload" "$LOG"
    banner "Phase 4: train DCTR $payload -> $OUT (~10 min)"
    OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2 \
    "$PY" scripts/training/train_dctr.py \
        --training-run "$V2A_RUN" \
        --method dct --payload "$payload" \
        --out "$OUT" \
        --n-workers "$NW" \
        --seed "$SEED" \
        2>&1 | tee "$LOG"

    # -------- gate: DCTR checkpoint --------
    [[ -f "$OUT" ]] || gate_fail "Phase 4 ($payload)" "checkpoint $OUT not written"
    [[ -f "$SUM" ]] || gate_fail "Phase 4 ($payload)" "summary $SUM not written"
    VAL_AUC=$("$PY" -c "import json; d=json.load(open('$SUM')); print(d.get('val_auc', d.get('best_val_auc', 0)))")
    echo "  val_auc = $VAL_AUC"
    awk -v v="$VAL_AUC" 'BEGIN { exit (v+0 >= 0.55) ? 0 : 1 }' || \
        gate_fail "Phase 4 ($payload)" "val_auc=$VAL_AUC below 0.55 sanity floor"
    notify "V2a: DCTR $payload trained" "val_auc=$VAL_AUC, ckpt=$(basename $OUT)" "high" "trophy"
done

# ============================================================
# Phase 5: per-cell val-AUC summary
# ============================================================
set_phase "Phase 5: training summary"
banner "Phase 5: per-cell validation AUCs"
SUMMARY_TEXT=""
for f in "$MODELS_DIR"/*.summary.json; do
    LINE=$("$PY" -c "
import json
d = json.load(open('$f'))
cfg = d['config']
auc = d.get('best_val_auc', d.get('val_auc'))
n_train = d.get('n_train', '?')
n_val = d.get('n_val', '?')
print(f'  {cfg[\"method\"]}/{cfg[\"payload\"]}: val_auc={auc:.4f}  n_train={n_train}  n_val={n_val}')
")
    echo "$LINE"
    SUMMARY_TEXT+="$LINE
"
done
notify "V2a: training summary" "$SUMMARY_TEXT" "high" "chart_with_upwards_trend"

# ============================================================
# Phase 6a: apply SRNet-v2a to existing test corpus
# ============================================================
SRNET_OUT="$TEST_RUN/predictions/predictions_srnet_v2a.csv"
set_phase "Phase 6a: inference SRNet-v2a" "$LOG_DIR/06_apply_srnet.log"
banner "Phase 6a: apply SRNet-v2a to test corpus"
"$PY" scripts/inference/apply_srnet_to_run.py \
    --run "$TEST_RUN" \
    --models "$MODELS_DIR/srnet_lsb_low_v2a.pt" \
             "$MODELS_DIR/srnet_lsb_medium_v2a.pt" \
             "$MODELS_DIR/srnet_lsb_high_v2a.pt" \
    --out "$SRNET_OUT" \
    --device cuda \
    2>&1 | tee "$LOG_DIR/06_apply_srnet.log"

# -------- gate: SRNet predictions --------
[[ -f "$SRNET_OUT" ]] || gate_fail "Phase 6a" "predictions $SRNET_OUT not written"
SRNET_ROWS=$(( $(wc -l < "$SRNET_OUT") - 1 ))
echo "  srnet rows: $SRNET_ROWS (expected $EXPECTED_TEST_ROWS)"
[[ "$SRNET_ROWS" -eq "$EXPECTED_TEST_ROWS" ]] || \
    gate_fail "Phase 6a" "SRNet predictions has $SRNET_ROWS rows, expected $EXPECTED_TEST_ROWS"
notify "V2a: SRNet inference done" "$SRNET_ROWS rows in predictions_srnet_v2a.csv" "high" "white_check_mark"

# ============================================================
# Phase 6b: apply DCTR-v2a to existing test corpus
# ============================================================
DCTR_OUT="$TEST_RUN/predictions/predictions_dctr_v2a.csv"
set_phase "Phase 6b: inference DCTR-v2a" "$LOG_DIR/06_apply_dctr.log"
banner "Phase 6b: apply DCTR-v2a to test corpus"
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2 \
"$PY" scripts/inference/apply_dctr_to_run.py \
    --run "$TEST_RUN" \
    --models "$MODELS_DIR/dctr_dct_low_v2a.pkl" \
             "$MODELS_DIR/dctr_dct_medium_v2a.pkl" \
             "$MODELS_DIR/dctr_dct_high_v2a.pkl" \
    --out "$DCTR_OUT" \
    --n-workers "$NW" \
    2>&1 | tee "$LOG_DIR/06_apply_dctr.log"

# -------- gate: DCTR predictions --------
[[ -f "$DCTR_OUT" ]] || gate_fail "Phase 6b" "predictions $DCTR_OUT not written"
DCTR_ROWS=$(( $(wc -l < "$DCTR_OUT") - 1 ))
echo "  dctr rows: $DCTR_ROWS (expected $EXPECTED_TEST_ROWS)"
[[ "$DCTR_ROWS" -eq "$EXPECTED_TEST_ROWS" ]] || \
    gate_fail "Phase 6b" "DCTR predictions has $DCTR_ROWS rows, expected $EXPECTED_TEST_ROWS"
notify "V2a: DCTR inference done" "$DCTR_ROWS rows in predictions_dctr_v2a.csv" "high" "white_check_mark"

# ============================================================
# Phase 8: final summary + scp instructions
# ============================================================
set_phase "DONE"
banner "DONE -- V2a-B pipeline complete in $(human_elapsed)"
echo ""
echo "Checkpoints (pull back to laptop models/training_v2a/):"
ls -lh "$MODELS_DIR/"
echo ""
echo "Test-corpus predictions (pull back to laptop runs/<test>/predictions/):"
wc -l "$SRNET_OUT" "$DCTR_OUT" 2>/dev/null
ls -lh "$SRNET_OUT" "$DCTR_OUT"
echo ""
echo "Logs in $LOG_DIR/"
echo ""
echo "============================================================"
echo "scp commands to run ON THE LAPTOP:"
echo "============================================================"
cat <<'EOSCP'
  # 1) Checkpoints + summary JSONs (~70 MB)
  mkdir -p models/training_v2a
  scp -P 16523 'root@185.17.198.196:/workspace/m2-2_steganography/models/training_v2a/*' models/training_v2a/

  # 2) Test predictions (~10 MB)
  scp -P 16523 'root@185.17.198.196:/workspace/m2-2_steganography/runs/prototype_full_20260513_005357_p8765/predictions/predictions_*_v2a.csv' \
      runs/prototype_full_20260513_005357_p8765/predictions/

  # 3) Training manifests for provenance (~5 MB)
  mkdir -p models/training_v2a/training_v2a_manifests
  scp -P 16523 -r 'root@185.17.198.196:/workspace/m2-2_steganography/runs/training_v2a/manifests/*' \
      models/training_v2a/training_v2a_manifests/

  # 4) Run learned_analysis with the v2a predictions (writes learned_shadow_v2a/)
  venv312/bin/python scripts/inference/learned_analysis.py \
      --run runs/prototype_full_20260513_005357_p8765 \
      --srnet-csv runs/prototype_full_20260513_005357_p8765/predictions/predictions_srnet_v2a.csv \
      --dctr-csv  runs/prototype_full_20260513_005357_p8765/predictions/predictions_dctr_v2a.csv \
      --shadow-name learned_shadow_v2a

  # 5) Compare V1 vs V2a per-source AUCs side by side
  diff <(jq -r '.verdicts | to_entries[] | "\(.key) \(.value.verdict) \(.value.pooled_diff)"' \
            runs/prototype_full_20260513_005357_p8765/learned_shadow/metrics/rq_verdicts.json) \
       <(jq -r '.verdicts | to_entries[] | "\(.key) \(.value.verdict) \(.value.pooled_diff)"' \
            runs/prototype_full_20260513_005357_p8765/learned_shadow_v2a/metrics/rq_verdicts.json)
EOSCP

notify "V2a COMPLETE" "wall-clock $(human_elapsed). srnet=$SRNET_ROWS dctr=$DCTR_ROWS rows. scp commands printed to log." "high" "tada"

echo ""
echo "Once predictions are local, the Vast.ai instance can be destroyed."
