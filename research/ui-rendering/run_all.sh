#!/bin/bash
cd /tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad/ui-rendering
CFG=()
for size in "cols=16&rows=8" "cols=32&rows=32"; do
  for tog in 0 8; do
    for tech in dom-class dom-overlay svg canvas-full canvas-dirty webgl; do
      CFG+=("tech=$tech&$size&toggles=$tog&frames=300")
    done
  done
done
CFG+=("tech=wave-svg&waves=8&frames=300" "tech=wave-canvas&waves=8&frames=300")
for thr in 1 6; do
  ./venv/bin/python run_bench.py results.jsonl $thr "${CFG[@]}"
done
echo ALLDONE
