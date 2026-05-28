#!/usr/bin/env bash
# Phase 7 (post-training metrics) STANDALONE for the v2a pipeline.
#
# This script does exactly what the "Phase 7" block in
# cloud_v2a_pipeline.sh does, but as a standalone invocation.  Use it
# when the orchestrator was already running before Phase 7 was added to
# the pipeline file (bash reads the script once at process startup, so
# an in-flight orchestrator won't pick up later additions to its own
# source file).  Once Phase 8 in the orchestrator prints "DONE", run
# this script in a fresh shell against the same checkpoints + run dirs.
#
# Idempotent: each step skips itself if its output already exists.
# Deterministic: identical to the pipeline's Phase 7 block.
#
# Usage on the Vast.ai instance (recommended -- avoids sklearn-version skew):
#
#     cd /workspace/m2-2_steganography
#     bash scripts/training/v2a_phase7_metrics.sh \
#         2>&1 | tee logs/v2a/07_metrics.log
#
# Usage locally after SCP-ing back checkpoints + training run:
#
#     bash scripts/training/v2a_phase7_metrics.sh \
#         /path/to/models/training_v2a /path/to/runs/training_v2a \
#         /path/to/runs/<test-run>
#
# Default paths assume the Vast.ai layout under /workspace/m2-2_steganography.
# Wall-clock: ~30 sec for 7a + ~1.5-3h for 7b (DCTR feature re-extraction).

set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/workspace/m2-2_steganography}"
MODELS_DIR="${1:-$PROJECT_ROOT/models/training_v2a}"
V2A_RUN="${2:-$PROJECT_ROOT/runs/training_v2a}"
TEST_RUN="${3:-$PROJECT_ROOT/runs/prototype_full_20260513_005357_p8765}"
PY="${PY:-/venv/main/bin/python}"
NW="${NW:-$(nproc 2>/dev/null || echo 8)}"

if [[ ! -x "$PY" ]]; then
    PY="$(command -v python3 || true)"
    [[ -n "$PY" ]] || { echo "ERROR: no python interpreter found" >&2; exit 1; }
    echo "WARNING: /venv/main/bin/python not found; using $PY" >&2
fi

cd "$PROJECT_ROOT"

SRNET_OUT="$TEST_RUN/predictions/predictions_srnet_v2a.csv"
DCTR_OUT="$TEST_RUN/predictions/predictions_dctr_v2a.csv"
PE_SRNET_OUT="$TEST_RUN/predictions/pe_min_srnet_v2a.csv"
PE_DCTR_OUT="$TEST_RUN/predictions/pe_min_dctr_v2a.csv"

printf '\n[phase7] Models dir: %s\n[phase7] V2a run:    %s\n[phase7] Test run:   %s\n[phase7] Python:     %s\n[phase7] Workers:    %s\n\n' \
    "$MODELS_DIR" "$V2A_RUN" "$TEST_RUN" "$PY" "$NW"

# -----------------------------------------------------------------------------
# 7a: test-set P_E^min for both detectors (trivial, ~30 sec each)
# -----------------------------------------------------------------------------
printf '========== 7a: P_E^min from predictions ==========\n'
for f in "$SRNET_OUT" "$DCTR_OUT"; do
    [[ -f "$f" ]] || { echo "ERROR: $f missing; Phase 6 not complete?" >&2; exit 1; }
done
if [[ -f "$PE_SRNET_OUT" && -f "$PE_DCTR_OUT" ]]; then
    echo "[phase7] 7a already done; pe_min_*_v2a.csv exist. Skipping."
else
    "$PY" scripts/inference/compute_pe_min_from_predictions.py \
        --predictions "$SRNET_OUT" "$DCTR_OUT"
fi
ls -lh "$PE_SRNET_OUT" "$PE_DCTR_OUT"

# -----------------------------------------------------------------------------
# 7b: strict E_OOB via deterministic re-fit of each DCTR ensemble
# -----------------------------------------------------------------------------
printf '\n========== 7b: strict DCTR E_OOB ==========\n'
NEED_EOOB=()
for payload in low medium high; do
    summary="$MODELS_DIR/dctr_dct_${payload}_v2a.summary.json"
    [[ -f "$MODELS_DIR/dctr_dct_${payload}_v2a.pkl" ]] || {
        echo "ERROR: missing $MODELS_DIR/dctr_dct_${payload}_v2a.pkl" >&2; exit 1; }
    if [[ -f "$summary" ]] && grep -q '"oob_metrics"' "$summary"; then
        echo "[phase7] $payload already has oob_metrics; skipping."
    else
        NEED_EOOB+=("$MODELS_DIR/dctr_dct_${payload}_v2a.pkl")
    fi
done

if [[ ${#NEED_EOOB[@]} -eq 0 ]]; then
    echo "[phase7] All three DCTR checkpoints already have E_OOB. Nothing to do."
else
    "$PY" scripts/training/compute_dctr_eoob.py \
        --checkpoint "${NEED_EOOB[@]}" \
        --training-run "$V2A_RUN" \
        --n-workers "$NW"
fi

# -----------------------------------------------------------------------------
# Final summary
# -----------------------------------------------------------------------------
printf '\n========== Phase 7 summary ==========\n'
for payload in low medium high; do
    summary="$MODELS_DIR/dctr_dct_${payload}_v2a.summary.json"
    if [[ -f "$summary" ]] && grep -q '"oob_metrics"' "$summary"; then
        python3 -c "
import json
s = json.load(open('$summary'))
o = s['oob_metrics']
print(f\"  dctr/$payload: E_OOB={o['e_oob']:.4f} (AUC={o['e_oob_auc']:.4f}, n_oob={o['n_oob_samples']})\")
"
    else
        echo "  dctr/$payload: E_OOB NOT computed"
    fi
done
echo ""
echo "[phase7] Test-set P_E^min summaries: $PE_SRNET_OUT, $PE_DCTR_OUT"
echo "[phase7] DCTR E_OOB: persisted in $MODELS_DIR/dctr_dct_*_v2a.summary.json under .oob_metrics"
