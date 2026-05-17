#!/bin/bash
# Round 8 dispatcher — parallel launch of all subagent runs.
# Skips scenarios with NOCAPTURE / ERROR_NOBIN for with_bhdr mode.
set -u
cd /home/jingyulee/gh/gla
export PATH=/home/jingyulee/gh/gla/bin:$PATH
export BHDR_PYTHON=/home/jingyulee/.cache/bazel/_bazel_jingyulee/97df310dd69562eef617a1c4f9fefa27/external/rules_python~~python~python_3_11_x86_64-unknown-linux-gnu/bin/python3.11

LOG=/tmp/eval_round8/dispatch.log
: > "$LOG"

while IFS=',' read -r scen fid dc; do
  [ -z "$scen" ] && continue
  for mode in code_only with_bhdr; do
    # Skip with_bhdr for scenarios that didn't capture
    if [ "$mode" = "with_bhdr" ] && { [ "$fid" = "ERROR_NOBIN" ] || [ "$fid" = "NOCAPTURE" ]; }; then
      echo "skip $scen $mode (no capture)" >> "$LOG"
      continue
    fi
    for model in haiku sonnet; do
      DLOG=/tmp/eval_round8/dispatch_${scen}_${mode}_${model}.log
      (
        bash /tmp/eval_round8/run_subagent.sh "$scen" "$mode" "$model" "$fid" \
          > "$DLOG" 2>&1
        echo "done $scen $mode $model" >> "$LOG"
      ) &
    done
  done
done < /tmp/eval_round8/captures.txt

wait
echo "ALL DONE" >> "$LOG"
