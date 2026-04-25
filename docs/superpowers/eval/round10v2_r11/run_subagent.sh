#!/bin/bash
# R10v2 + R11 subagent runner — 11 scenarios × 3 tiers × 2 modes.
#
# Usage: run_subagent.sh <scenario> <mode> <model>
#   mode: with_gpa | code_only
#   model: haiku | sonnet | opus
set -u

SCENARIO=$1
MODE=$2
MODEL=$3

# Shared snapshot mapping helper.
source /tmp/eval_r10v2_r11/snapshot_map.sh

SNAP=$(get_snapshot_for_scenario "$SCENARIO")

SCEN_DIR="/home/jingyulee/gh/gla/tests/eval/$SCENARIO"
if [ ! -d "$SCEN_DIR" ]; then
  echo "[$SCENARIO $MODE $MODEL] missing scenario dir $SCEN_DIR" >&2
  exit 2
fi

OUT_DIR=/tmp/eval_r10v2_r11
SESSION_DIR="$OUT_DIR/sessions/${SCENARIO}_${MODE}_${MODEL}"
OUT="$OUT_DIR/${SCENARIO}_${MODE}_${MODEL}.jsonl"
PROMPT_FILE="$OUT_DIR/${SCENARIO}_${MODE}_${MODEL}.prompt"
CAPTURE_LOG="$OUT_DIR/${SCENARIO}_${MODE}_${MODEL}.capture.log"

export PATH=/home/jingyulee/gh/gla/bin:$PATH

# ---- Build the prompt template via the shared renderer. ----
PROMPT_MODE=code_only
if [ "$MODE" = "with_gpa" ]; then
  PROMPT_MODE=with_gla
fi

python3 /tmp/eval_r10v2_r11/build_prompt.py "$SCENARIO" "$PROMPT_MODE" > "$PROMPT_FILE" || {
  echo "[$SCENARIO $MODE $MODEL] prompt render failed" >&2
  exit 2
}

# ---- With-GPA: start an engine session (auto-port) and capture one frame. ----
FRAME_NOTE=""
SESSION_PORT=""
SESSION_TOKEN=""
if [ "$MODE" = "with_gpa" ]; then
  rm -rf "$SESSION_DIR"
  mkdir -p "$SESSION_DIR"
  # Start daemon with auto-port (R10v2/R11 fix).
  gpa start --session "$SESSION_DIR" --port 0 --daemon > "$SESSION_DIR/start.log" 2>&1
  if [ ! -f "$SESSION_DIR/port" ] || [ ! -f "$SESSION_DIR/token" ]; then
    echo "[$SCENARIO $MODE $MODEL] gpa start failed" >&2
    FRAME_NOTE="no-capture (engine start failed)"
  else
    SESSION_PORT=$(cat "$SESSION_DIR/port")
    SESSION_TOKEN=$(cat "$SESSION_DIR/token")
    # Capture a frame via the GL shim.
    BIN="/home/jingyulee/gh/gla/bazel-bin/tests/eval/$SCENARIO"
    if [ -x "$BIN" ]; then
      (
        eval "$(gpa env --session "$SESSION_DIR")"
        export DISPLAY=:99
        export LD_PRELOAD=/home/jingyulee/gh/gla/bazel-bin/src/shims/gl/libgpa_gl.so
        export GPA_TRACE_NATIVE=1
        export GPA_TRACE_NATIVE_STACK=1
        timeout 5 "$BIN" > "$CAPTURE_LOG" 2>&1 || true
      )
      sleep 0.5
      OVERVIEW=$(curl -s -H "Authorization: Bearer $SESSION_TOKEN" "http://127.0.0.1:$SESSION_PORT/api/v1/frames/current/overview" 2>/dev/null | head -c 400)
      if ! echo "$OVERVIEW" | grep -q '"frame_id"'; then
        FRAME_NOTE="no frames captured"
      fi
    else
      FRAME_NOTE="no-capture (binary missing)"
    fi
  fi
fi

# ---- Model name mapping. ----
case "$MODEL" in
  haiku)  MODELNAME="claude-haiku-4-5" ;;
  sonnet) MODELNAME="claude-sonnet-4-6" ;;
  opus)   MODELNAME="claude-opus-4-7" ;;
  *)      MODELNAME="$MODEL" ;;
esac

# ---- Tool lists. `--dangerously-skip-permissions` bypasses allowedTools,
#      so we rely on --disallowedTools to block mutation tools that could
#      clobber the shared snapshot directory (Edit/Write/NotebookEdit).
ALLOW="Read Grep Glob"
if [ "$MODE" = "with_gpa" ]; then
  ALLOW="Read Grep Glob Bash(curl:*) Bash(gpa:*)"
fi
DENY="Edit Write NotebookEdit MultiEdit"

ADD_DIRS="--add-dir $SCEN_DIR"
if [ -n "$SNAP" ] && [ -d "$SNAP" ]; then
  ADD_DIRS="$ADD_DIRS --add-dir $SNAP"
fi

# Extra prompt tail carrying runtime session info for the with_gpa agent.
FINAL_PROMPT="$OUT_DIR/${SCENARIO}_${MODE}_${MODEL}.final-prompt"
cp "$PROMPT_FILE" "$FINAL_PROMPT"
if [ "$MODE" = "with_gpa" ] && [ -n "$SESSION_TOKEN" ]; then
  {
    echo ""
    echo ""
    echo "# Runtime session (already exported for you)"
    echo ""
    echo "- GPA_SESSION=$SESSION_DIR"
    echo "- GPA_PORT=$SESSION_PORT"
    echo "- GPA_TOKEN=$SESSION_TOKEN"
    if [ -n "$SNAP" ] && [ -d "$SNAP" ]; then
      echo "- Framework snapshot path: $SNAP"
    fi
    if [ -n "$FRAME_NOTE" ]; then
      echo ""
      echo "- Capture status: $FRAME_NOTE"
      echo "  (you can still attempt GPA calls but they may return empty)"
    fi
  } >> "$FINAL_PROMPT"
elif [ "$MODE" = "code_only" ] && [ -n "$SNAP" ] && [ -d "$SNAP" ]; then
  {
    echo ""
    echo ""
    echo "# Runtime"
    echo ""
    echo "- Framework snapshot path: $SNAP"
  } >> "$FINAL_PROMPT"
fi

# ---- Dispatch the agent. Retry once at max-turns=80 if first run hits cap.
MAX_TURNS=${MAX_TURNS:-40}
cd "$OUT_DIR"

RUN_ATTEMPT() {
  local turns=$1 outfile=$2
  if [ "$MODE" = "with_gpa" ] && [ -n "$SESSION_TOKEN" ]; then
    export GPA_SESSION="$SESSION_DIR"
    export GPA_PORT="$SESSION_PORT"
    export GPA_TOKEN="$SESSION_TOKEN"
  fi
  timeout 1200 claude -p \
      --model "$MODELNAME" \
      $ADD_DIRS \
      --allowedTools $ALLOW \
      --disallowedTools $DENY \
      --dangerously-skip-permissions \
      --output-format stream-json \
      --verbose \
      --max-turns "$turns" \
      --no-session-persistence \
      "$(cat "$FINAL_PROMPT")" > "$outfile" 2>&1
}

RUN_ATTEMPT "$MAX_TURNS" "$OUT"
RC=$?

if [ -s "$OUT" ]; then
  LAST=$(tail -5 "$OUT" | tr '\n' ' ')
  if echo "$LAST" | grep -q '"subtype":"error_max_turns"'; then
    cp "$OUT" "${OUT%.jsonl}.retry_1.jsonl"
    RUN_ATTEMPT 80 "$OUT"
    RC=$?
  fi
fi

# ---- Stop session. ----
if [ "$MODE" = "with_gpa" ] && [ -d "$SESSION_DIR" ]; then
  gpa stop --session "$SESSION_DIR" > "$SESSION_DIR/stop.log" 2>&1 || true
fi

echo "[done] $SCENARIO $MODE $MODEL (rc=$RC, frame_note='${FRAME_NOTE}')"
exit "$RC"
