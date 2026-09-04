#!/bin/bash
# Waits up to 25 minutes for the workstation to go quiet, then runs anyway and
# records the load with every row.  Each arm is paired with a baseline run
# immediately before it so the comparison is contemporaneous.
cd "$(dirname "$0")"
export PYTHONPATH="/mnt/dev/Apps/2026-02 Sequencer"
export PYTHONDONTWRITEBYTECODE=1
deadline=$(( $(date +%s) + 1500 ))
while (( $(echo "$(cut -d' ' -f1 /proc/loadavg) > 1.2" | bc -l) )) && (( $(date +%s) < deadline )); do sleep 20; done
run () { ./venv/bin/python crossing_bench2.py "$@" 2>/dev/null >> results_focus.jsonl; }
for pass in 1 2 3; do
  run none  sustained 5 1 8
  run batch burst 5 8 8
  run none  sustained 5 1 8
  run per_message burst 5 8 8
  run none  sustained 5 1 8
  run coalesced burst 5 8 8
done
echo FOCUS_DONE
