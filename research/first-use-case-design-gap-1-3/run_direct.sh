#!/bin/bash
# Prices the off-loop arm against a fresh baseline and a contemporaneous
# per-message arm, paired the way run_focus.sh pairs its runs.
cd "$(dirname "$0")"
export PYTHONPATH="/mnt/dev/Apps/2026-02 Sequencer"
export PYTHONDONTWRITEBYTECODE=1
run () { ./venv/bin/python crossing_bench3.py "$@" 2>/dev/null >> results_direct.jsonl; }
for pass in 1 2 3; do
  run none sustained 5 1 8
  run direct burst 5 8 8
  run none sustained 5 1 8
  run per_message burst 5 8 8
done
echo DIRECT_DONE
