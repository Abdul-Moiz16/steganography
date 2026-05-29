#!/usr/bin/env bash
# v2a recovery from Phase 4 onward.
#
# Reason this exists: the original cloud_v2a_pipeline.sh sampled nproc()
# once at the top of Phase 4 and baked the result into NW.  On Vast.ai
# the cgroup CPU set occasionally reports nproc=1 briefly at container
# warmup, which caused the in-flight run to pin --n-workers=1 for the
# DCTR phases (and Phase 6b inference) -- ~30h of unnecessary wall-clock
# on a 16-core-budget machine.  This script resumes after Phase 3
# (SRNet x 3 already trained) with NW re-evaluated NOW, and chains
# Phases 4 -> 5 -> 6a -> 6b -> 7 -> 8 idempotently.
#
# Idempotent: each phase skips itself if its outputs already exist.
# Safe to re-launch on partial failure.
#
# Usage on the Vast.ai instance:
#   cd /workspace/m2-2_steganography
#   nohup bash scripts/training/v2a_recover_from_phase4.sh \
#       > logs/v2a_recovery/00_orchestrator.log 2>&1 &
#   tail -f logs/v2a_recovery/00_orchestrator.log
#
# Optional: export NTFY_TOPIC=<your-secret-topic> before launching to
# get phone push notifications at each phase boundary (matches the
# original orchestrator's notification scheme).

set -euo pipefail

# ---------------- Config ----------------
PROJECT_ROOT="${PROJECT_ROOT:-/workspace/m2-2_steganography}"
PY="${PY:-/venv/main/bin/python}"
TEST_RUN="$PROJECT_ROOT/runs/prototype_full_20260513_005357_p8765"
V2A_RUN="$PROJECT_ROOT/runs/training_v2a"
MODELS_DIR="$PROJECT_ROOT/models/training_v2a"
LOG_DIR="$PROJECT_ROOT/logs/v2a_recovery"
SEED=4242
EXPECTED_TEST_ROWS=108000
NTFY_TOPIC="${NTFY_TOPIC:-}"

mkdir -p "$LOG_DIR"
cd "$PROJECT_ROOT"

# Re-evaluate worker count NOW (fixing the bug that motivated this script).
NCPU=$(nproc)
NW=$(( NCPU > 16 ? 16 : NCPU ))
T0=$(date +%s)

# ---------------- Helpers ----------------
banner() {
    printf '\n========================================================================\n'
    printf '[%s] %s\n' "$(date -u '+%Y-%m-%d %H:%M:%S UTC')" "$1"
    printf '========================================================================\n'
}

elapsed() {
    local now=$(date +%s)
    local sec=$(( now - T0 ))
    printf '%dh%02dm' $(( sec / 3600 )) $(( (sec % 3600) / 60 ))
}

notify() {
    local title="$1"
    local body="${2:-}"
    local prio="${3:-default}"
    if [[ -n "$NTFY_TOPIC" ]]; then
        curl -fsS -H "Title: $title" -H "Priority: $prio" \
             -d "$body" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null 2>&1 || true
    fi
    printf '[notify %s] %s | %s\n' "$prio" "$title" "$body"
}

gate() {
    if ! eval "$1"; then
        notify "v2a recovery FAILED" "$2" "urgent"
        echo "[recover] FAIL: $2"
        exit 1
    fi
}

banner "v2a recovery launched (NCPU=$NCPU -> NW=$NW)"
notify "v2a recovery launched" "NCPU=$NCPU NW=$NW, picking up after SRNet Phase 3" "high"

# ---------------- Phase 4: DCTR x 3 payloads ----------------
banner "Phase 4: DCTR x 3 payloads at NW=$NW"
for payload in low medium high; do
    OUT="$MODELS_DIR/dctr_dct_${payload}_v2a.pkl"
    SUM="${OUT%.pkl}.summary.json"
    LOG="$LOG_DIR/04_dctr_${payload}.log"

    if [[ -f "$OUT" && -f "$SUM" ]]; then
        echo "[recover] Phase 4 dctr/$payload already done, skipping"
        continue
    fi

    banner "Phase 4: train DCTR $payload -> $(basename $OUT)"
    notify "v2a: Phase 4 DCTR $payload start" "elapsed $(elapsed)" "default"
    OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2 \
    "$PY" scripts/training/train_dctr.py \
        --training-run "$V2A_RUN" \
        --method dct --payload "$payload" \
        --out "$OUT" \
        --n-workers "$NW" \
        --seed "$SEED" \
        2>&1 | tee "$LOG"

    gate "[[ -f '$OUT' ]]" "Phase 4 $payload: checkpoint $OUT not written"
    gate "[[ -f '$SUM' ]]" "Phase 4 $payload: summary $SUM not written"
    VAL_AUC=$("$PY" -c "import json; print(json.load(open('$SUM')).get('val_auc', 0))")
    echo "[recover] Phase 4 dctr/$payload: val_auc=$VAL_AUC"
    awk -v v="$VAL_AUC" 'BEGIN { exit (v+0 >= 0.55) ? 0 : 1 }' || \
        gate "false" "Phase 4 $payload: val_auc=$VAL_AUC below 0.55 sanity floor"
    notify "v2a: DCTR $payload trained" "val_auc=$VAL_AUC, elapsed $(elapsed)" "high"
done

# ---------------- Phase 5: summary ----------------
banner "Phase 5: per-cell val-AUC summary"
{
    for ckpt in "$MODELS_DIR"/srnet_lsb_*_v2a.summary.json "$MODELS_DIR"/dctr_dct_*_v2a.summary.json; do
        [[ -f "$ckpt" ]] || continue
        name=$(basename "$ckpt" .summary.json)
        val_auc=$("$PY" -c "import json; d=json.load(open('$ckpt')); print(d.get('val_auc', d.get('best_val_auc', 'N/A')))")
        printf '  %-32s val_auc=%s\n' "$name" "$val_auc"
    done
} | tee "$LOG_DIR/05_summary.log"

# ---------------- Phase 6a: apply SRNet ----------------
SRNET_OUT="$TEST_RUN/predictions/predictions_srnet_v2a.csv"
expected_lines=$(( EXPECTED_TEST_ROWS + 1 ))
if [[ -f "$SRNET_OUT" ]] && [[ $(wc -l < "$SRNET_OUT") -eq $expected_lines ]]; then
    echo "[recover] Phase 6a: $SRNET_OUT already complete, skipping"
else
    banner "Phase 6a: apply SRNet-v2a to test corpus"
    notify "v2a: Phase 6a SRNet inference start" "elapsed $(elapsed)" "default"
    "$PY" scripts/inference/apply_srnet_to_run.py \
        --run "$TEST_RUN" \
        --models "$MODELS_DIR"/srnet_lsb_low_v2a.pt \
                 "$MODELS_DIR"/srnet_lsb_medium_v2a.pt \
                 "$MODELS_DIR"/srnet_lsb_high_v2a.pt \
        --out "$SRNET_OUT" \
        --device cuda --batch-size 32 \
        2>&1 | tee "$LOG_DIR/06_apply_srnet.log"
    gate "[[ -f '$SRNET_OUT' ]]" "Phase 6a: $SRNET_OUT not written"
    SRNET_ROWS=$(( $(wc -l < "$SRNET_OUT") - 1 ))
    echo "[recover] Phase 6a: $SRNET_ROWS rows (expected $EXPECTED_TEST_ROWS)"
    [[ "$SRNET_ROWS" -eq "$EXPECTED_TEST_ROWS" ]] || \
        gate "false" "Phase 6a: $SRNET_ROWS rows, expected $EXPECTED_TEST_ROWS"
    notify "v2a: SRNet inference done" "$SRNET_ROWS rows, elapsed $(elapsed)" "high"
fi

# ---------------- Phase 6b: apply DCTR ----------------
DCTR_OUT="$TEST_RUN/predictions/predictions_dctr_v2a.csv"
if [[ -f "$DCTR_OUT" ]] && [[ $(wc -l < "$DCTR_OUT") -eq $expected_lines ]]; then
    echo "[recover] Phase 6b: $DCTR_OUT already complete, skipping"
else
    banner "Phase 6b: apply DCTR-v2a to test corpus (NW=$NW)"
    notify "v2a: Phase 6b DCTR inference start" "NW=$NW, elapsed $(elapsed)" "default"
    OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2 \
    "$PY" scripts/inference/apply_dctr_to_run.py \
        --run "$TEST_RUN" \
        --models "$MODELS_DIR"/dctr_dct_low_v2a.pkl \
                 "$MODELS_DIR"/dctr_dct_medium_v2a.pkl \
                 "$MODELS_DIR"/dctr_dct_high_v2a.pkl \
        --out "$DCTR_OUT" \
        --n-workers "$NW" \
        2>&1 | tee "$LOG_DIR/06_apply_dctr.log"
    gate "[[ -f '$DCTR_OUT' ]]" "Phase 6b: $DCTR_OUT not written"
    DCTR_ROWS=$(( $(wc -l < "$DCTR_OUT") - 1 ))
    echo "[recover] Phase 6b: $DCTR_ROWS rows (expected $EXPECTED_TEST_ROWS)"
    [[ "$DCTR_ROWS" -eq "$EXPECTED_TEST_ROWS" ]] || \
        gate "false" "Phase 6b: $DCTR_ROWS rows, expected $EXPECTED_TEST_ROWS"
    notify "v2a: DCTR inference done" "$DCTR_ROWS rows, elapsed $(elapsed)" "high"
fi

# ---------------- Phase 7: post-training metrics ----------------
banner "Phase 7: P_E^min summaries + strict DCTR E_OOB"
notify "v2a: Phase 7 metrics start" "elapsed $(elapsed)" "default"
bash scripts/training/v2a_phase7_metrics.sh 2>&1 | tee "$LOG_DIR/07_metrics.log"

# Emit a compact E_OOB summary line for notification.
EOOB_TEXT=$(for payload in low medium high; do
    summary="$MODELS_DIR/dctr_dct_${payload}_v2a.summary.json"
    if [[ -f "$summary" ]] && grep -q '"oob_metrics"' "$summary"; then
        eoob=$("$PY" -c "import json; print(f\"{json.load(open('$summary'))['oob_metrics']['e_oob']:.4f}\")")
        echo "$payload=$eoob"
    fi
done | paste -sd' ' -)
notify "v2a: Phase 7 done" "DCTR E_OOB: $EOOB_TEXT" "high"

# ---------------- Phase 8: DONE + scp instructions ----------------
banner "Phase 8: DONE -- v2a recovery complete in $(elapsed)"
echo ""
echo "Checkpoints in $MODELS_DIR:"
ls -lh "$MODELS_DIR/"
echo ""
echo "Test predictions + P_E^min summaries in $TEST_RUN/predictions/:"
ls -lh "$TEST_RUN"/predictions/{predictions,pe_min}_*v2a*.csv 2>/dev/null || true
echo ""
cat <<EOSCP

============================================================
scp commands to run ON THE LAPTOP:
============================================================
  # 1) Checkpoints + summary JSONs (~70 MB)
  mkdir -p models/training_v2a
  scp -P 16523 'root@185.17.198.196:/workspace/m2-2_steganography/models/training_v2a/*' \\
      models/training_v2a/

  # 2) Test predictions + P_E^min summaries (~10 MB)
  scp -P 16523 'root@185.17.198.196:/workspace/m2-2_steganography/runs/prototype_full_20260513_005357_p8765/predictions/predictions_*_v2a.csv' \\
      runs/prototype_full_20260513_005357_p8765/predictions/
  scp -P 16523 'root@185.17.198.196:/workspace/m2-2_steganography/runs/prototype_full_20260513_005357_p8765/predictions/pe_min_*_v2a.csv' \\
      runs/prototype_full_20260513_005357_p8765/predictions/

  # 3) Training manifests for provenance (~5 MB)
  mkdir -p models/training_v2a/training_v2a_manifests
  scp -P 16523 -r 'root@185.17.198.196:/workspace/m2-2_steganography/runs/training_v2a/manifests/*' \\
      models/training_v2a/training_v2a_manifests/

  # 4) Recovery logs (audit trail of this rerun)
  mkdir -p logs/v2a_recovery
  scp -P 16523 -r 'root@185.17.198.196:/workspace/m2-2_steganography/logs/v2a_recovery/*' \\
      logs/v2a_recovery/

  # 5) Run learned_analysis with v2a predictions (writes learned_shadow_v2a/)
  venv312/bin/python scripts/inference/learned_analysis.py \\
      --run runs/prototype_full_20260513_005357_p8765 \\
      --srnet-csv runs/prototype_full_20260513_005357_p8765/predictions/predictions_srnet_v2a.csv \\
      --dctr-csv  runs/prototype_full_20260513_005357_p8765/predictions/predictions_dctr_v2a.csv \\
      --shadow-name learned_shadow_v2a

  # 6) Compare V1 vs V2a per-source AUCs side by side
  diff <(jq -r '.verdicts | to_entries[] | "\(.key) \(.value.verdict) \(.value.pooled_diff)"' \\
            runs/prototype_full_20260513_005357_p8765/learned_shadow/metrics/rq_verdicts.json) \\
       <(jq -r '.verdicts | to_entries[] | "\(.key) \(.value.verdict) \(.value.pooled_diff)"' \\
            runs/prototype_full_20260513_005357_p8765/learned_shadow_v2a/metrics/rq_verdicts.json)
EOSCP

notify "v2a recovery COMPLETE" "elapsed $(elapsed). DCTR E_OOB: $EOOB_TEXT" "high"
echo "[recover] DONE in $(elapsed)"
