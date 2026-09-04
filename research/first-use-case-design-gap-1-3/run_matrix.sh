#!/bin/bash
cd "$(dirname "$0")"
export PYTHONPATH="/mnt/dev/Apps/2026-02 Sequencer"
export PYTHONDONTWRITEBYTECODE=1
run () { ./venv/bin/python crossing_bench.py "$@" 2>/dev/null >> results.jsonl; }
for pass in 1 2; do
  run none sustained 5 1 16
  run per_message burst 5 8 16
  run coalesced burst 5 8 16
  run hooks burst 5 8 16
  run per_message sustained 5 1 16
  run coalesced sustained 5 1 16
  run per_message sustained 50 1 16
  run coalesced sustained 50 1 16
  run hooks sustained 50 1 16
done
echo DONE
