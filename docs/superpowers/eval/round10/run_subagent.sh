#!/bin/bash
# Round 10 subagent runner — maintainer-framing on 9 scenarios.
#
# Usage: run_subagent.sh <scenario> <mode> <model>
#   mode: with_bhdr | code_only
#   model: haiku | sonnet | opus
set -u

SCENARIO=$1
MODE=$2
MODEL=$3

# Shared snapshot mapping helper.
source /tmp/eval_round10/snapshot_map.sh

SNAP=$(get_snapshot_for_scenario "$SCENARIO")

SCEN_DIR="/home/jingyulee/gh/gla/tests/eval/$SCENARIO"
if [ ! -d "$SCEN_DIR" ]; then
  echo "[$SCENARIO $MODE $MODEL] missing scenario dir $SCEN_DIR" >&2
  exit 2
fi

OUT_DIR=/tmp/eval_round10
SESSION_DIR="$OUT_DIR/sessions/${SCENARIO}_${MODE}_${MODEL}"
OUT="$OUT_DIR/${SCENARIO}_${MODE}_${MODEL}.jsonl"
PROMPT_FILE="$OUT_DIR/${SCENARIO}_${MODE}_${MODEL}.prompt"
CAPTURE_LOG="$OUT_DIR/${SCENARIO}_${MODE}_${MODEL}.capture.log"

export PATH=/home/jingyulee/gh/gla/bin:$PATH

# ---- Pick a free port (avoids collisions in parallel dispatch). ----
PORT=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')

# ---- Build the prompt template via the shared renderer. ----
PROMPT_MODE=code_only
if [ "$MODE" = "with_bhdr" ]; then
  PROMPT_MODE=with_gla
fi

python3 /tmp/eval_round10/build_prompt.py "$SCENARIO" "$PROMPT_MODE" > "$PROMPT_FILE" || {
  echo "[$SCENARIO $MODE $MODEL] prompt render failed" >&2
  exit 2
}

# ---- With-GPA: start an engine session and (try to) capture one frame. ----
FRAME_NOTE=""
if [ "$MODE" = "with_bhdr" ]; then
  rm -rf "$SESSION_DIR"
  mkdir -p "$SESSION_DIR"
  # Start daemon on the free port.
  gpa start --session "$SESSION_DIR" --port "$PORT" --daemon > "$SESSION_DIR/start.log" 2>&1
  if [ ! -f "$SESSION_DIR/port" ]; then
    echo "[$SCENARIO $MODE $MODEL] gpa start failed" >&2
    FRAME_NOTE="no-capture (engine start failed)"
  else
    # Capture frame via the GL shim. Run the scenario binary briefly.
    BIN="/home/jingyulee/gh/gla/bazel-bin/tests/eval/$SCENARIO"
    if [ -x "$BIN" ]; then
      (
        set -e
        eval "$(gpa env --session "$SESSION_DIR")"
        export DISPLAY=:99
        export LD_PRELOAD=/home/jingyulee/gh/gla/bazel-bin/src/shims/gl/libbhdr_gl.so
        export BHDR_TRACE_NATIVE=1
        export BHDR_TRACE_NATIVE_STACK=1
        timeout 5 "$BIN" > "$CAPTURE_LOG" 2>&1 || true
      )
      # Verify capture by asking the REST API for the current frame overview.
      sleep 0.5
      BHDR_TOKEN=$(cat "$SESSION_DIR/token")
      OVERVIEW=$(curl -s -H "Authorization: Bearer $BHDR_TOKEN" "http://127.0.0.1:$PORT/api/v1/frames/current/overview" 2>/dev/null | head -c 400)
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
if [ "$MODE" = "with_bhdr" ]; then
  ALLOW="Read Grep Glob Bash(curl:*) Bash(gpa:*)"
fi
DENY="Edit Write NotebookEdit MultiEdit"

ADD_DIRS="--add-dir $SCEN_DIR"
if [ -n "$SNAP" ] && [ -d "$SNAP" ]; then
  ADD_DIRS="$ADD_DIRS --add-dir $SNAP"
fi

# Extra prompt tail carrying runtime session info for the with_bhdr agent.
FINAL_PROMPT="$OUT_DIR/${SCENARIO}_${MODE}_${MODEL}.final-prompt"
cp "$PROMPT_FILE" "$FINAL_PROMPT"
if [ "$MODE" = "with_bhdr" ] && [ -f "$SESSION_DIR/token" ]; then
  TOKEN=$(cat "$SESSION_DIR/token")
  {
    echo ""
    echo ""
    echo "# Runtime session (already exported for you)"
    echo ""
    echo "- BHDR_SESSION=$SESSION_DIR"
    echo "- BHDR_PORT=$PORT"
    echo "- BHDR_TOKEN=$TOKEN"
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

# ---- Dispatch the agent. Retry once at max-turns=80 if the first run hits the cap.
MAX_TURNS=${MAX_TURNS:-40}
cd "$OUT_DIR"

RUN_ATTEMPT() {
  local turns=$1 outfile=$2
  # Wrap GPA env export in the spawned shell if with_bhdr, so Bash(gpa:*) sees them.
  if [ "$MODE" = "with_bhdr" ] && [ -f "$SESSION_DIR/token" ]; then
    export BHDR_SESSION="$SESSION_DIR"
    export BHDR_PORT="$PORT"
    export BHDR_TOKEN=$(cat "$SESSION_DIR/token")
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

# Detect max-turns hit and retry once at 80.
if [ -s "$OUT" ]; then
  LAST=$(tail -5 "$OUT" | tr '\n' ' ')
  if echo "$LAST" | grep -q '"subtype":"error_max_turns"'; then
    cp "$OUT" "${OUT%.jsonl}.retry_1.jsonl"
    RUN_ATTEMPT 80 "$OUT"
    RC=$?
  fi
fi

# ---- Stop session. ----
if [ "$MODE" = "with_bhdr" ] && [ -d "$SESSION_DIR" ]; then
  gpa stop --session "$SESSION_DIR" > "$SESSION_DIR/stop.log" 2>&1 || true
fi

echo "[done] $SCENARIO $MODE $MODEL (rc=$RC, frame_note='${FRAME_NOTE}')"
exit "$RC"
