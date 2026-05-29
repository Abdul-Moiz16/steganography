#!/usr/bin/env bash
# Single-phase BOSSBase validation: import + exp1-4 for ONE (Q, method).
# Used by the parallel-execution path so we can run 3+ (Q, method)
# combinations simultaneously on a high-core-count box.
#
# Differences from run_bossbase_validation_remote.sh:
#   - Takes (Q, method) as positional args; no outer loop.
#   - Calls each exp script directly with an explicit --out-dir under a
#     per-phase intermediate path, so parallel invocations don't clobber
#     each other's outputs (run_all_useful_experiments.sh writes to a
#     hard-coded global path which is fine for serial use but races
#     under parallelism).
#   - Renames the intermediate output to the standard
#     runs/tiled_validation/bossbase_q${Q}_${METHOD}/ location at the end.
#
# Usage:
#   nohup bash scripts/experiments/tiled_chi2_validation/bossbase_phase_runner.sh \
#         <Q> <METHOD> > logs/bossbase/phase_q<Q>_<METHOD>.log 2>&1 &
#
# Idempotent: if the per-(Q, method) import + all 4 exp outputs already
# exist, the script no-ops.

set -euo pipefail

Q="${1:?Usage: $0 <quality> <method>}"
METHOD="${2:?Usage: $0 <quality> <method>}"
NW="${NW:-32}"
PROJECT_ROOT="${PROJECT_ROOT:-/workspace/m2-2_steganography}"
PY="${PY:-/venv/main/bin/python}"
BOSSBASE_DIR="${BOSSBASE_DIR:-/workspace/bossbase_src}"
LOG_DIR="$PROJECT_ROOT/logs/bossbase"

RUN_DIR="$PROJECT_ROOT/runs/bossbase_q${Q}_${METHOD}"
EXP_OUT_BASE="$PROJECT_ROOT/runs/tiled_validation/bossbase_q${Q}_${METHOD}"
INTER_DIR="$PROJECT_ROOT/runs/tiled_validation_tmp_q${Q}_${METHOD}"
TAG="Q=${Q} ${METHOD}"

mkdir -p "$LOG_DIR"
cd "$PROJECT_ROOT"

T0=$(date +%s)
banner() {
    printf '\n========================================================================\n'
    printf '[%s] %s\n' "$(date -u '+%Y-%m-%d %H:%M:%S UTC')" "$1"
    printf '========================================================================\n'
}
elapsed() {
    local s=$(( $(date +%s) - T0 )); printf '%dh%02dm' $((s/3600)) $((s%3600/60))
}

banner "Phase runner ($TAG) launched (NW=$NW)"

# --- Phase A: import ----------------------------------------------------
if [[ -f "$RUN_DIR/manifests/stegos.csv" ]] && \
   [[ $(wc -l < "$RUN_DIR/manifests/stegos.csv") -gt 100000 ]]; then
    banner "Phase A ($TAG): import already complete -- skipping"
else
    banner "Phase A ($TAG): import BOSSBase -> $RUN_DIR"
    "$PY" -m scripts.experiments.tiled_chi2_validation.import_bossbase \
        --bossbase-dir "$BOSSBASE_DIR" \
        --out-run "$RUN_DIR" \
        --quality "$Q" \
        --method "$METHOD" \
        --n-workers "$NW"
    [[ -f "$RUN_DIR/manifests/stegos.csv" ]] || { echo "ERROR: import failed"; exit 1; }
fi

# --- Phase B: exp1-4 with per-phase intermediate output dir -------------
# Each exp script accepts --out-dir; we route to a per-(Q, method) tmp dir
# so parallel runners don't share the global runs/tiled_validation/expN_*.
banner "Phase B ($TAG): exp1-4 (elapsed $(elapsed))"
mkdir -p "$INTER_DIR"

# exp1: T-sweep
"$PY" -m scripts.experiments.tiled_chi2_validation.exp1_tsweep \
    --run "$RUN_DIR" --out-dir "$INTER_DIR/exp1_tsweep" \
    --tiles 1 2 3 4 6 8 --pool max \
    --payload-levels p005 p010 p020 p030 p040 p050 \
    --sources real --n-workers "$NW"

# exp2: payload-invariance replot (cheap, reads exp1 CSV)
"$PY" -m scripts.experiments.tiled_chi2_validation.exp2_payload_invariance \
    --exp1-results "$INTER_DIR/exp1_tsweep/results.csv" \
    --out-dir "$INTER_DIR/exp2_payload_invariance"

# exp3: pooling ablation
"$PY" -m scripts.experiments.tiled_chi2_validation.exp3_pooling \
    --run "$RUN_DIR" --out-dir "$INTER_DIR/exp3_pooling" \
    --tiles 2 --pools max mean median topk_mean \
    --payload-levels p005 p010 p020 p030 p040 p050 \
    --sources real --n-workers "$NW"

# exp4: baseline-detector contest
"$PY" -m scripts.experiments.tiled_chi2_validation.exp4_baselines \
    --run "$RUN_DIR" --out-dir "$INTER_DIR/exp4_baselines" \
    --tiles 2 --sliding-window 4 --sliding-stride 2 \
    --payload-levels p005 p010 p020 p030 p040 p050 \
    --sources real --n-workers "$NW"

# Move to final location.  Idempotent: if EXP_OUT_BASE already has these
# subdirs (from a previous run), the mv would fail; we rm -rf first.
mkdir -p "$EXP_OUT_BASE"
for exp in exp1_tsweep exp2_payload_invariance exp3_pooling exp4_baselines; do
    rm -rf "$EXP_OUT_BASE/$exp"
    mv "$INTER_DIR/$exp" "$EXP_OUT_BASE/$exp"
done
rmdir "$INTER_DIR" 2>/dev/null || true

banner "Phase runner ($TAG): DONE in $(elapsed)"
ls "$EXP_OUT_BASE"
