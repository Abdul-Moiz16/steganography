#!/usr/bin/env bash
# One-command Phase A-D orchestrator for the post-training workflow.
#
# Run this AFTER the cloud training has produced `runs/training_v1/training_done.marker`.
# It scp's the artefacts back, applies the learned detectors to the test
# run, and runs the supplementary analysis -- all in one go.
#
# Usage:
#   export VAST_PORT=<port>      # e.g. 12345
#   export VAST_HOST=79.161.30.134
#   bash scripts/inference/post_training_workflow.sh
#
# Total wall-clock: ~45-60 minutes (scp + ~30 min inference + ~10 min analysis).

set -euo pipefail

# ---------------- Config ----------------
VAST_PORT="${VAST_PORT:?need VAST_PORT}"
VAST_HOST="${VAST_HOST:?need VAST_HOST}"
TEST_RUN="${TEST_RUN:-runs/prototype_full_20260513_005357_p8765}"
MODELS_DIR="${MODELS_DIR:-models/training_v1}"
PY="${PY:-venv/bin/python}"

if [[ ! -d "$TEST_RUN" ]]; then
    echo "FATAL: test run not found at $TEST_RUN" >&2
    exit 1
fi
if [[ ! -x "$PY" ]]; then
    echo "FATAL: python not found at $PY (set PY=...)" >&2
    exit 1
fi

# ---------------- Phase A: retrieve artefacts ----------------
echo "============================================================"
echo "Phase A: scp artefacts from Vast.ai"
echo "============================================================"
mkdir -p "$MODELS_DIR"

scp -P "$VAST_PORT" \
    "root@${VAST_HOST}:/workspace/m2-2_steganography/models/srnet_lsb_*.pt" \
    "$MODELS_DIR/"
scp -P "$VAST_PORT" \
    "root@${VAST_HOST}:/workspace/m2-2_steganography/models/srnet_lsb_*.summary.json" \
    "$MODELS_DIR/"
scp -P "$VAST_PORT" \
    "root@${VAST_HOST}:/workspace/m2-2_steganography/models/dctr_dct_*.pkl" \
    "$MODELS_DIR/"
scp -P "$VAST_PORT" \
    "root@${VAST_HOST}:/workspace/m2-2_steganography/models/dctr_dct_*.summary.json" \
    "$MODELS_DIR/"

# Provenance: manifests + per-cell training logs
scp -P "$VAST_PORT" -r \
    "root@${VAST_HOST}:/workspace/m2-2_steganography/runs/training_v1/manifests" \
    "$MODELS_DIR/training_manifests"
scp -P "$VAST_PORT" -r \
    "root@${VAST_HOST}:/workspace/m2-2_steganography/logs/training_v1_final" \
    "$MODELS_DIR/training_logs" 2>/dev/null || true

echo
echo "Retrieved artefacts:"
ls -lh "$MODELS_DIR/"

# ---------------- Sanity check: val-AUC per cell ----------------
echo
echo "Per-cell validation AUCs (from training summaries):"
for f in "$MODELS_DIR"/srnet_lsb_*.summary.json "$MODELS_DIR"/dctr_dct_*.summary.json; do
    [[ -f "$f" ]] || continue
    $PY -c "
import json
d = json.load(open('$f'))
auc = d.get('best_val_auc', d.get('val_auc'))
print(f'  {d[\"config\"][\"method\"]}/{d[\"config\"][\"payload\"]}: val_auc={auc:.4f}, hash={d[\"training_run_hash\"]}')
"
done
echo

# ---------------- Phase B reminder ----------------
echo "============================================================"
echo "Phase B reminder: destroy the Vast.ai instance NOW"
echo "  (\$0.72/day storage drain if left running)"
echo "  Browser: Vast.ai > Instances > trash icon > confirm"
echo "============================================================"
echo "Press Enter once the instance is destroyed (or Ctrl-C to skip)..."
read -r

# ---------------- Phase C: apply learned detectors to test run ----------------
echo
echo "============================================================"
echo "Phase C: apply SRNet to test run"
echo "============================================================"
$PY scripts/inference/apply_srnet_to_run.py \
    --run "$TEST_RUN" \
    --models "$MODELS_DIR"/srnet_lsb_low_v1.pt \
             "$MODELS_DIR"/srnet_lsb_medium_v1.pt \
             "$MODELS_DIR"/srnet_lsb_high_v1.pt \
    --out "$TEST_RUN/predictions/predictions_srnet.csv"

echo
echo "============================================================"
echo "Phase C: apply DCTR to test run"
echo "============================================================"
NCPU=$(sysctl -n hw.ncpu 2>/dev/null || nproc)
$PY scripts/inference/apply_dctr_to_run.py \
    --run "$TEST_RUN" \
    --models "$MODELS_DIR"/dctr_dct_low_v1.pkl \
             "$MODELS_DIR"/dctr_dct_medium_v1.pkl \
             "$MODELS_DIR"/dctr_dct_high_v1.pkl \
    --out "$TEST_RUN/predictions/predictions_dctr.csv" \
    --n-workers "$NCPU"

echo
echo "Phase C outputs:"
wc -l "$TEST_RUN/predictions/predictions_srnet.csv" "$TEST_RUN/predictions/predictions_dctr.csv"

# ---------------- Phase D: learned-only supplementary analysis ----------------
echo
echo "============================================================"
echo "Phase D: supplementary learned-detector analysis"
echo "============================================================"
$PY scripts/inference/learned_analysis.py --run "$TEST_RUN"

# ---------------- Done ----------------
echo
echo "============================================================"
echo "Phases A-D complete."
echo "============================================================"
echo "  Learned predictions:  $TEST_RUN/predictions/predictions_srnet.csv"
echo "                        $TEST_RUN/predictions/predictions_dctr.csv"
echo "  Learned metrics:      $TEST_RUN/learned_shadow/metrics/"
echo "  Learned figures:      $TEST_RUN/learned_shadow/figures/"
echo "  Verdicts (Markdown):  $TEST_RUN/learned_shadow/metrics/rq_verdicts.md"
echo
echo "Next step (Phase E): open docs/report/final_report_draft_v2.tex and"
echo "fill in the \\TBD{...} placeholders from the learned_shadow/ outputs."
echo "See docs/learned_baselines/POST_TRAINING_CHECKLIST.md for the full list."
