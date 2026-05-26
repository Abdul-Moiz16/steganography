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
#   - Sends one notification per interval with the latest log line.
#   - Immediately notifies (high priority) if the pipeline process dies,
#     the log file stops growing for >1 hour, or the deliverables tarball
#     appears (= training complete).
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

last_log_size=0
last_growth_at=$(date +%s)

echo "[watchdog] run_id=$RUN_ID interval=${INTERVAL_MIN}m topic=ntfy.sh/$NTFY_TOPIC"

notify "watchdog ARMED" "Watching $RUN_ID every ${INTERVAL_MIN}m. Mute topic if noisy."

while true; do
    sleep "${INTERVAL_MIN}m"

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
            notify "pipeline DIED" "$RUN_ID PID $pid not running. Tail: $tail_lines" urgent
            break
        fi
    fi

    # Heartbeat: check log growth
    if [[ -f "$LOG_FILE" ]]; then
        cur_size=$(wc -c < "$LOG_FILE" 2>/dev/null || echo 0)
        if (( cur_size > last_log_size )); then
            last_log_size=$cur_size
            last_growth_at=$now
        fi
        stalled_for=$(( now - last_growth_at ))

        last_line=$(tail -n 1 "$LOG_FILE" 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' | cut -c1-220)

        if (( stalled_for > STALL_THRESHOLD_S )); then
            notify "pipeline STALLED" "$RUN_ID: no log growth for $((stalled_for/60))m. Last: $last_line" urgent
        else
            notify "training heartbeat" "stalled_for=$((stalled_for/60))m | $last_line"
        fi
    else
        notify "no log yet" "$LOG_FILE missing -- pipeline may not have created it yet"
    fi
done

echo "[watchdog] exiting at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
