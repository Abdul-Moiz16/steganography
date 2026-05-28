#!/usr/bin/env bash
# Run experiments 1..4 of the tile-local chi^2-DCT validation scaffold in
# sequence on a single test-corpus run directory.  Experiment 5 is skipped:
# it depends on a re-embedding cycle that is not part of this scaffold (see
# its module docstring).
#
# Usage:
#   bash scripts/experiments/tiled_chi2_validation/run_all_useful_experiments.sh \
#        [run_dir] [extra args passed to exp1/exp3/exp4]
#
#   run_dir defaults to runs/prototype_full_20260513_005357_p8765 (the
#   caption-matched reference corpus the v4 paper headline numbers come
#   from).  Pass any other standard-layout run directory -- e.g.
#   runs/bossbase_q95 once import_bossbase.py has been run -- to validate
#   the same experiments against a different corpus.
#
#   Extra args after run_dir are forwarded to exp1/exp3/exp4 so you can
#   pass e.g. --max-cells-per-strata 100 for a fast dry run on all four.
#
#   For a BOSSBase run produced by import_bossbase.py, the experiments
#   need to know about the six-level numerical payload axis and the
#   single 'real' source.  Pass those as extra args after the run dir:
#
#     bash .../run_all_useful_experiments.sh \
#          runs/bossbase_q95 \
#          --payload-levels p005 p010 p020 p030 p040 p050 \
#          --sources real
#
# Expected total wall-clock on laptop: ~1.5 h on the full reference corpus,
# ~5 min with --max-cells-per-strata 100.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

PY="venv312/bin/python"
if [[ ! -x "$PY" ]]; then
    echo "ERROR: $PY not found.  Activate the project's Python 3.12 venv first." >&2
    exit 1
fi

RUN_DIR="${1:-runs/prototype_full_20260513_005357_p8765}"
shift || true
EXTRA_ARGS=("$@")  # forwarded to exp1, exp3, exp4

if [[ ! -d "$RUN_DIR" ]]; then
    echo "ERROR: run_dir not found: $RUN_DIR" >&2
    echo "Hint: pass a run directory as the first argument, or import BOSSBase first:" >&2
    echo "  $PY -m scripts.experiments.tiled_chi2_validation.import_bossbase --bossbase-dir <path> --out-run runs/bossbase_q95" >&2
    exit 1
fi

EXP1_OUT="runs/tiled_validation/exp1_tsweep"
EXP2_OUT="runs/tiled_validation/exp2_payload_invariance"
EXP3_OUT="runs/tiled_validation/exp3_pooling"
EXP4_OUT="runs/tiled_validation/exp4_baselines"

step() {
    local title="$1"
    printf '\n========================================================================\n'
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$title"
    printf '========================================================================\n'
}

OVERALL_T0=$(date +%s)

# --- Experiment 1: tile-size sweep ----------------------------------------
step "Experiment 1 / 4: tile-size sweep (~30 min full corpus)"
"$PY" -m scripts.experiments.tiled_chi2_validation.exp1_tsweep \
    --run "$RUN_DIR" \
    --out-dir "$EXP1_OUT" \
    --tiles 1 2 3 4 6 8 \
    --pool max \
    "${EXTRA_ARGS[@]}"

# --- Experiment 2: payload-invariance replot (reuses exp1 CSV) ------------
step "Experiment 2 / 4: payload-invariance replot (~10 sec)"
"$PY" -m scripts.experiments.tiled_chi2_validation.exp2_payload_invariance \
    --exp1-results "$EXP1_OUT/results.csv" \
    --out-dir "$EXP2_OUT"

# --- Experiment 3: pooling-rule ablation ----------------------------------
step "Experiment 3 / 4: pooling-rule ablation at T=2 (~30 min full corpus)"
"$PY" -m scripts.experiments.tiled_chi2_validation.exp3_pooling \
    --run "$RUN_DIR" \
    --out-dir "$EXP3_OUT" \
    --tiles 2 \
    --pools max mean median topk_mean \
    "${EXTRA_ARGS[@]}"

# --- Experiment 4: baseline detectors -------------------------------------
# DCTR is folded in only if predictions_dctr.csv already exists under
# $RUN_DIR/predictions/; otherwise exp4 prints a hint and skips it.
step "Experiment 4 / 4: baseline detectors (~20 min full corpus)"
"$PY" -m scripts.experiments.tiled_chi2_validation.exp4_baselines \
    --run "$RUN_DIR" \
    --out-dir "$EXP4_OUT" \
    --tiles 2 \
    --sliding-window 4 \
    --sliding-stride 2 \
    "${EXTRA_ARGS[@]}"

OVERALL_T1=$(date +%s)
ELAPSED_MIN=$(( (OVERALL_T1 - OVERALL_T0) / 60 ))

printf '\n========================================================================\n'
printf '[%s] All four experiments completed in %d min\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$ELAPSED_MIN"
printf '========================================================================\n'
printf 'Results:\n'
printf '  exp1: %s/{results.csv,auc_vs_T.png}\n'              "$EXP1_OUT"
printf '  exp2: %s/{argmax_T_by_payload.csv,argmax_T_by_payload.png}\n' "$EXP2_OUT"
printf '  exp3: %s/{results.csv,auc_by_pool.png}\n'           "$EXP3_OUT"
printf '  exp4: %s/{results.csv,auc_by_detector.png}\n'       "$EXP4_OUT"
