#!/bin/bash
# Round 8 capture — robust: probe max frame id before + after each scenario.
set -u
cd /home/jingyulee/gh/gla
export DISPLAY=:99
export PATH=/home/jingyulee/gh/gla/bin:$PATH
export GPA_PYTHON=/home/jingyulee/.cache/bazel/_bazel_jingyulee/97df310dd69562eef617a1c4f9fefa27/external/rules_python~~python~python_3_11_x86_64-unknown-linux-gnu/bin/python3.11

eval "$(gpa env)"
echo "session: $GPA_SESSION port=$GPA_PORT"

probe_fid() {
  # Walk upward from the given lower bound until we find a 'not found' response.
  local start=$1
  local last=-1
  local i=$start
  while true; do
    local r=$(curl -sH "Authorization: Bearer $GPA_TOKEN" "http://127.0.0.1:$GPA_PORT/api/v1/frames/$i/overview" 2>/dev/null)
    if echo "$r" | grep -q '"frame_id"'; then
      last=$i
      i=$((i+1))
    else
      break
    fi
  done
  echo $last
}

# Initial max frame
BEFORE=$(probe_fid 1)
echo "initial max fid: $BEFORE"

: > /tmp/eval_round8/captures.txt
for scen in $(cat /tmp/round8_scenarios.txt); do
  BIN="bazel-bin/tests/eval/$scen"
  if [ ! -x "$BIN" ]; then
    echo "$scen,ERROR_NOBIN,0" >> /tmp/eval_round8/captures.txt
    echo "[capture] $scen -> NO BIN"
    continue
  fi

  LOG=/tmp/eval_round8/capture_${scen}.log
  timeout 4 env \
    LD_PRELOAD=bazel-bin/src/shims/gl/libgpa_gl.so \
    GPA_SOCKET_PATH="$GPA_SOCKET_PATH" \
    GPA_SHM_NAME="$GPA_SHM_NAME" \
    DISPLAY=:99 \
    "$BIN" >"$LOG" 2>&1 || true

  sleep 0.5
  AFTER=$(probe_fid $((BEFORE+1)))
  if [ "$AFTER" = "-1" ]; then
    echo "$scen,NOCAPTURE,0" >> /tmp/eval_round8/captures.txt
    echo "[capture] $scen -> NOCAPTURE"
    continue
  fi
  FID=$AFTER
  OV=$(curl -sH "Authorization: Bearer $GPA_TOKEN" http://127.0.0.1:$GPA_PORT/api/v1/frames/$FID/overview)
  DC=$(echo "$OV" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('draw_call_count',0))" 2>/dev/null)
  echo "$scen,$FID,$DC" >> /tmp/eval_round8/captures.txt
  echo "[capture] $scen -> frame=$FID draws=$DC"
  BEFORE=$AFTER
done

echo "DONE"
cat /tmp/eval_round8/captures.txt
