#!/bin/bash
# Round 10 parallel dispatcher.
#
# Reads /tmp/eval_round10/tasks.txt — one line per run: `<scenario> <mode> <model>`.
# Fires every task via run_subagent.sh as a background job, then waits for them
# all to finish. Skips any task whose output jsonl already contains a `result`
# event (so a partial resume is idempotent).
set -u
cd /tmp/eval_round10
: > dispatch_log.txt

N=0
while read -r scen mode model; do
  OUT="/tmp/eval_round10/${scen}_${mode}_${model}.jsonl"
  if [ -s "$OUT" ] && tail -1 "$OUT" | grep -q '"type":"result"'; then
    echo "[skip-done] $scen $mode $model" >> /tmp/eval_round10/dispatch_log.txt
    continue
  fi
  (
    bash /tmp/eval_round10/run_subagent.sh "$scen" "$mode" "$model" > /dev/null 2>&1
    echo "[done] $scen $mode $model" >> /tmp/eval_round10/dispatch_log.txt
  ) &
  N=$((N+1))
done < /tmp/eval_round10/tasks.txt
echo "Dispatched $N runs, waiting..." >> /tmp/eval_round10/dispatch_log.txt
wait
echo "All done." >> /tmp/eval_round10/dispatch_log.txt
