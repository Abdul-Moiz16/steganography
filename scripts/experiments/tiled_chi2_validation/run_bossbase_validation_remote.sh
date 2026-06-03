#!/usr/bin/env bash
# Full BOSSBase 1.01 validation of the tile-local chi^2-DCT detector,
# end-to-end on a Vast.ai-style remote box.
#
# What it does
# ------------
# For each quality factor in {Q=75, Q=95} (DCTR-canonical + matches our
# main paper):
#   1. Import BOSSBase 1.01 into our standard run layout
#      (10,000 covers + 120,000 stegos at six bpnzAC levels and two
#      encryption modes), via the parallel import_bossbase.py with
#      --n-workers <N>.
#   2. Run exp1 (T-sweep), exp2 (replot), exp3 (pooling ablation),
#      exp4 (baseline-detector contest) against the resulting run dir,
#      with --payload-levels p005 p010 p020 p030 p040 p050 --sources real
#      and --n-workers <N>.
#
# Idempotent
# ----------
# - Importer skips JPEG re-encode if the cover .jpg already exists at
#   that path; it does NOT skip stego embedding if the .pkl is missing,
#   but Stage 2 writes one file per stego task and a partial run can be
#   restarted by deleting the partial output directory.
# - Each experiment writes results.csv + plots into a fixed output
#   directory; re-running OVERWRITES.
#
# Usage on Vast.ai
# ----------------
#   cd /workspace/m2-2_steganography
#   nohup bash scripts/experiments/tiled_chi2_validation/run_bossbase_validation_remote.sh \
#       > logs/bossbase/00_orchestrator.log 2>&1 &
#   tail -f logs/bossbase/00_orchestrator.log
#
# Total expected wall-clock on a 128-core RTX-class box at NW=32:
#   - Import x2 qualities: ~30 min total (sequential; parallel would
#     halve but logs get tangled).
#   - exp1-4 per quality:  ~45 min.
#   - Two qualities total: ~2 h.

set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/workspace/m2-2_steganography}"
PY="${PY:-/venv/main/bin/python}"
BOSSBASE_DIR="${BOSSBASE_DIR:-/workspace/bossbase_src}"
NW="${NW:-32}"
LOG_DIR="$PROJECT_ROOT/logs/bossbase"

mkdir -p "$LOG_DIR"
cd "$PROJECT_ROOT"

banner() {
    printf '\n========================================================================\n'
    printf '[%s] %s\n' "$(date -u '+%Y-%m-%d %H:%M:%S UTC')" "$1"
    printf '========================================================================\n'
}

elapsed() {
    local now=$(date +%s); local sec=$(( now - T0 ))
    printf '%dh%02dm' $(( sec / 3600 )) $(( (sec % 3600) / 60 ))
}

T0=$(date +%s)
banner "BOSSBase validation launched (BOSSBASE_DIR=$BOSSBASE_DIR, NW=$NW)"

# Sanity: BOSSBase PGMs exist
PGM_COUNT=$(find "$BOSSBASE_DIR" -name "*.pgm" | wc -l)
if [[ "$PGM_COUNT" -lt 100 ]]; then
    echo "ERROR: only $PGM_COUNT PGMs under $BOSSBASE_DIR; expected ~10000."
    exit 1
fi
echo "Found $PGM_COUNT BOSSBase PGMs."

# Sanity: Python deps present
"$PY" -c "import numpy, PIL, matplotlib, jpeglib" || {
    echo "ERROR: missing Python deps (numpy/PIL/matplotlib/jpeglib)."
    exit 1
}

for Q in 95 75; do
    for METHOD in jsteg outguess; do
        RUN_DIR="$PROJECT_ROOT/runs/bossbase_q${Q}_${METHOD}"
        EXP_OUT_BASE="$PROJECT_ROOT/runs/tiled_validation/bossbase_q${Q}_${METHOD}"
        TAG="Q=${Q} ${METHOD}"

        # --- Phase A: import BOSSBase at this (Q, method) ---
        if [[ -f "$RUN_DIR/manifests/stegos.csv" ]] && \
           [[ $(wc -l < "$RUN_DIR/manifests/stegos.csv") -gt 100000 ]]; then
            banner "Phase A ($TAG): import already complete -- skipping"
        else
            banner "Phase A ($TAG): import BOSSBase -> $RUN_DIR (elapsed $(elapsed))"
            "$PY" -m scripts.experiments.tiled_chi2_validation.import_bossbase \
                --bossbase-dir "$BOSSBASE_DIR" \
                --out-run "$RUN_DIR" \
                --quality "$Q" \
                --method "$METHOD" \
                --n-workers "$NW" \
                2>&1 | tee "$LOG_DIR/01_import_q${Q}_${METHOD}.log"
            [[ -f "$RUN_DIR/manifests/stegos.csv" ]] || { echo "ERROR: import failed"; exit 1; }
        fi

        # --- Phase B: run exp1-4 against this corpus ---
        banner "Phase B ($TAG): exp1-4 on $RUN_DIR (elapsed $(elapsed))"
        PY="$PY" bash scripts/experiments/tiled_chi2_validation/run_all_useful_experiments.sh \
            "$RUN_DIR" \
            --payload-levels p005 p010 p020 p030 p040 p050 \
            --sources real \
            --n-workers "$NW" \
            2>&1 | tee "$LOG_DIR/02_exp_q${Q}_${METHOD}.log"

        # Move output to per-(Q,method) directory
        for exp in exp1_tsweep exp2_payload_invariance exp3_pooling exp4_baselines; do
            src_dir="$PROJECT_ROOT/runs/tiled_validation/$exp"
            dst_dir="$EXP_OUT_BASE/$exp"
            if [[ -d "$src_dir" ]]; then
                mkdir -p "$(dirname "$dst_dir")"
                mv "$src_dir" "$dst_dir"
            fi
        done
        echo "[orch] Phase B ($TAG) results moved to $EXP_OUT_BASE/"
    done
done

banner "DONE -- BOSSBase validation complete in $(elapsed)"
echo ""
echo "Output layout:"
ls -la "$PROJECT_ROOT/runs/bossbase_q"*/ 2>/dev/null | head
echo ""
ls -la "$PROJECT_ROOT/runs/tiled_validation/bossbase_q"*/ 2>/dev/null | head
echo ""
echo "============================================================"
echo "scp commands to run ON THE LAPTOP:"
echo "============================================================"
cat <<EOSCP
  # Pull the per-Q experiment outputs (CSV + PNG, small)
  mkdir -p runs/tiled_validation
  scp -P 39148 -r 'root@117.18.102.40:/workspace/m2-2_steganography/runs/tiled_validation/bossbase_q*' \\
      runs/tiled_validation/

  # Pull the BOSSBase import manifests for provenance (covers_real.csv + stegos.csv per Q)
  mkdir -p models/bossbase_manifests
  for Q in 75 95; do
      mkdir -p models/bossbase_manifests/q\$Q
      scp -P 39148 'root@117.18.102.40:/workspace/m2-2_steganography/runs/bossbase_q'\$Q'/manifests/*' \\
          models/bossbase_manifests/q\$Q/
  done

  # Pull the orchestrator + per-phase logs
  mkdir -p logs/bossbase
  scp -P 39148 -r 'root@117.18.102.40:/workspace/m2-2_steganography/logs/bossbase/*' logs/bossbase/

  # Once everything is local, destroy the Vast.ai instance
  # (BOSSBase imports themselves are reproducible from the BOSSBase PGMs +
  # the seed=42 in import_bossbase.py)
EOSCP
