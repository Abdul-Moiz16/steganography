#!/usr/bin/env bash
# Pipeline watchdog: sends push notifications to your phone via ntfy.sh.
#
# Setup (one-time, on your phone):
#   1. Install the ntfy app from https://ntfy.sh (iOS App Store or Google Play)
#   2. Subscribe to a topic of your choosing (use a long random string, e.g.
#      "m22stego-$(head -c 8 /dev/urandom | base64 | tr -d '/+=')") -- anyone
#      who knows the topic name can publish to it, so keep it private.
#
# Usage on the cloud instance (after the pipeline is running):
#   export NTFY_TOPIC=<your-long-random-topic>
#   nohup bash scripts/training/watchdog.sh training_v1 30 \
#       > logs/watchdog.log 2>&1 &
#
# Args:
#   $1 = run_id      (default: training_v1)
#   $2 = interval    minutes between heartbeats (default: 30)
#
# Behavior:
#   - Sends one notification per interval with the detected stage + last log line.
#   - Sends a high-priority "STAGE" notification the moment we detect we
#     have moved into a new pipeline stage (e.g. download -> ml gen -> embed
#     -> train -> package). This is independent of the heartbeat interval.
#   - Immediately notifies (urgent) if the pipeline process dies or the
#     log file stops growing for >1 hour. Notifies (high) when the
#     deliverables tarball appears (= training complete).
#   - Exits on terminal states (DIED / DONE) so you don't get spammed.

set -uo pipefail

RUN_ID="${1:-training_v1}"
INTERVAL_MIN="${2:-30}"

if [[ -z "${NTFY_TOPIC:-}" ]]; then
    echo "ERROR: set NTFY_TOPIC env var. Example:"
    echo "  export NTFY_TOPIC=m22stego-\$(head -c 8 /dev/urandom | base64 | tr -d '/+=')"
    echo "Then install ntfy from https://ntfy.sh on your phone and subscribe to that topic."
    exit 1
fi

PID_FILE="logs/${RUN_ID}.pid"
LOG_FILE="logs/${RUN_ID}/pipeline.log"
RUN_DIR="runs/${RUN_ID}"
STALL_THRESHOLD_S=$((60 * 60))  # 1h of zero log growth = stall

notify() {
    local title="$1"
    local body="$2"
    local priority="${3:-default}"
    curl -fsS --max-time 15 \
        -H "Title: $title" \
        -H "Priority: $priority" \
        -d "$body" \
        "https://ntfy.sh/${NTFY_TOPIC}" >/dev/null 2>&1 \
      && echo "[$(date -u +%H:%M:%SZ)] notified: $title" \
      || echo "[$(date -u +%H:%M:%SZ)] notify FAILED: $title"
}

# Detect which pipeline stage we are in by scanning the ENTIRE log file
# for definitive `=== Stage N: ===` banners emitted by cloud_full_pipeline.sh.
# These banners are unique and unambiguous; using them avoids two bugs in
# the previous detection logic:
#   (a) false-match on `inference_api` in the boot banner (which says
#       "ML_ENGINE = inference_api") triggering Stage 4 at startup
#   (b) tail-window scrolling: once banners scroll past the recent-N
#       window, the stage falls back to "?/7 starting up" even though
#       the pipeline is happily in the middle of stage 3
# We scan the whole log (typically <50 MB even after 13h) and find the
# highest banner that has appeared.
detect_stage() {
    local log="$1"
    [[ ! -f "$log" ]] && echo "?/7 no log" && return

    # Highest stage banner seen so far -- order matters (largest first).
    local seen_stage7=0  seen_stage6b=0  seen_stage6=0
    local seen_stage35=0  seen_stage1=0

    grep -q "=== Stage 7:"   "$log" 2>/dev/null && seen_stage7=1
    grep -q "=== Stage 6b:"  "$log" 2>/dev/null && seen_stage6b=1
    grep -q "=== Stage 6:"   "$log" 2>/dev/null && seen_stage6=1
    grep -q "=== Stages 3-5:" "$log" 2>/dev/null && seen_stage35=1
    grep -q "=== Stage 1:"   "$log" 2>/dev/null && seen_stage1=1

    if (( seen_stage7 == 1 )); then
        echo "7/7 packaging deliverables"; return
    fi

    if (( seen_stage6b == 1 )); then
        # DCTR sub-progress
        if grep -q "\[train-dctr\] DONE" "$log" 2>/dev/null; then
            local cells_done
            cells_done=$(grep -c "\[train-dctr\] DONE" "$log" 2>/dev/null || echo 0)
            echo "6b/7 dctr cell $cells_done/3 done"; return
        fi
        if grep -q "fitting BaggingClassifier" "$log" 2>/dev/null; then
            echo "6b/7 fitting dctr ensemble"; return
        fi
        if grep -qE "extracting (TRAIN|VAL) features" "$log" 2>/dev/null; then
            echo "6b/7 dctr feature extraction"; return
        fi
        echo "6b/7 dctr training started"; return
    fi

    if (( seen_stage6 == 1 )); then
        # SRNet sub-progress: find the LAST `epoch N/M` printed and the
        # current cell label.
        local last_epoch
        last_epoch=$(grep -oE "epoch [0-9]+/[0-9]+" "$log" 2>/dev/null | tail -1)
        # Detect which cell we're on by counting "cell: LSB" banners
        local cells_started
        cells_started=$(grep -c "\-\-\-\-\- cell: LSB" "$log" 2>/dev/null || echo 0)
        if [[ -n "$last_epoch" ]]; then
            echo "6/7 srnet cell $cells_started/3 ($last_epoch)"; return
        fi
        echo "6/7 srnet warmup"; return
    fi

    if (( seen_stage35 == 1 )); then
        # Data assembly sub-progress (Stages 3, 4, 5 share one banner)
        if grep -qE "embedding complete|stego_manifest.*written" "$log" 2>/dev/null; then
            echo "5/7 embedding done -> training next"; return
        fi
        if grep -qE "\[embed|embedding stegos|run_embedding_stage|build_stego_manifest" "$log" 2>/dev/null; then
            # Try to parse tqdm progress out
            local emb_pct
            emb_pct=$(grep -oE "[0-9]+%\|[^|]*\| *[0-9]+/[0-9]+" "$log" 2>/dev/null | tail -1)
            if [[ -n "$emb_pct" ]]; then
                echo "5/7 embedding ($emb_pct)"
            else
                echo "5/7 embedding lsb+dct stegos"
            fi
            return
        fi
        if grep -qE "ml covers complete|ml.cover.*done|generate_ml_covers.*done" "$log" 2>/dev/null; then
            echo "4/7 ml covers done -> embedding next"; return
        fi
        if grep -qE "generating ml covers|generate_ml_covers" "$log" 2>/dev/null; then
            local mlpct
            mlpct=$(grep -oE "[0-9]+%\|[^|]*\| *[0-9]+/[0-9]+" "$log" 2>/dev/null | tail -1)
            if [[ -n "$mlpct" ]]; then
                echo "4/7 ml gen ($mlpct)"
            else
                echo "4/7 generating ml covers (hf inference)"
            fi
            return
        fi
        if grep -qE "real covers complete|covers_real\.csv.*written" "$log" 2>/dev/null; then
            echo "3/7 real covers done -> ml gen next"; return
        fi
        if grep -q "downloading real covers" "$log" 2>/dev/null; then
            # Pull tqdm progress out of the tail (last progress bar)
            local pct
            pct=$(grep -oE "[0-9]+%\|[^|]*\| *[0-9]+/[0-9]+" "$log" 2>/dev/null | tail -1)
            if [[ -n "$pct" ]]; then
                echo "3/7 real cover dl ($pct)"
            else
                echo "3/7 downloading real covers"
            fi
            return
        fi
        echo "3/7 data assembly"; return
    fi

    if (( seen_stage1 == 1 )); then
        echo "1/7 deps + gpu check"; return
    fi

    echo "?/7 starting up"
}

last_log_size=0
last_growth_at=$(date +%s)
prev_stage=""

echo "[watchdog] run_id=$RUN_ID interval=${INTERVAL_MIN}m topic=ntfy.sh/$NTFY_TOPIC"

notify "watchdog ARMED" "Watching $RUN_ID every ${INTERVAL_MIN}m. Stage transitions push instantly; heartbeats include current stage. Mute topic if noisy."

# Detect initial stage so the first transition notification is meaningful
prev_stage=$(detect_stage "$LOG_FILE")
echo "[watchdog] initial stage: $prev_stage"

# Poll every minute for stage transitions; emit heartbeat every INTERVAL_MIN.
TICK_S=60
INTERVAL_S=$(( INTERVAL_MIN * 60 ))
last_heartbeat_at=$(date +%s)

while true; do
    sleep "$TICK_S"

    now=$(date +%s)

    # Terminal state 1: deliverables tarball present = success
    if [[ -f "$RUN_DIR/deliverables.tar.gz" ]] || ls "$RUN_DIR"/deliverables*.tar.gz 2>/dev/null | grep -q .; then
        size=$(ls -lh "$RUN_DIR"/deliverables*.tar.gz 2>/dev/null | head -1 | awk '{print $5}')
        notify "training DONE" "$RUN_ID: deliverables ready (~${size}). scp it down and destroy the instance." high
        break
    fi

    # Terminal state 2: pipeline process died
    if [[ -f "$PID_FILE" ]]; then
        pid=$(cat "$PID_FILE")
        if ! kill -0 "$pid" 2>/dev/null; then
            tail_lines=$(tail -n 5 "$LOG_FILE" 2>/dev/null | tr '\n' ' | ' | cut -c1-350)
            notify "pipeline DIED" "$RUN_ID PID $pid not running. Last stage: $prev_stage. Tail: $tail_lines" urgent
            break
        fi
    fi

    # Stage transition: check every minute, push instantly when detected
    cur_stage=$(detect_stage "$LOG_FILE")
    if [[ "$cur_stage" != "$prev_stage" ]]; then
        last_line=$(tail -n 1 "$LOG_FILE" 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' | cut -c1-180)
        notify "STAGE: $cur_stage" "(was: $prev_stage) | $last_line" high
        prev_stage="$cur_stage"
    fi

    # Heartbeat (every INTERVAL_MIN): log-growth + stall check
    if (( now - last_heartbeat_at >= INTERVAL_S )); then
        last_heartbeat_at=$now

        if [[ -f "$LOG_FILE" ]]; then
            cur_size=$(wc -c < "$LOG_FILE" 2>/dev/null || echo 0)
            if (( cur_size > last_log_size )); then
                last_log_size=$cur_size
                last_growth_at=$now
            fi
            stalled_for=$(( now - last_growth_at ))

            last_line=$(tail -n 1 "$LOG_FILE" 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' | cut -c1-200)

            if (( stalled_for > STALL_THRESHOLD_S )); then
                notify "pipeline STALLED" "$RUN_ID at $cur_stage: no log growth for $((stalled_for/60))m. Last: $last_line" urgent
            else
                notify "heartbeat: $cur_stage" "stalled=$((stalled_for/60))m | $last_line"
            fi
        else
            notify "no log yet" "$LOG_FILE missing -- pipeline may not have created it yet"
        fi
    fi
done

echo "[watchdog] exiting at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
