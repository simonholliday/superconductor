#!/bin/bash
# Revision matrix: dispatch lateness on the rebuild pulse, 2026-09-04.
PY=~/venvs/subsequence-cookbook/bin/python
OUT=results/disp2.jsonl
: > $OUT
gate () {
  for i in $(seq 1 60); do
    L=$(cut -d' ' -f1 /proc/loadavg)
    if [ "$(echo "$L < 1.2" | bc -l)" = "1" ]; then return 0; fi
    sleep 5
  done
}
run () {
  gate
  echo "--- $* (load $(cut -d' ' -f1 /proc/loadavg))" >&2
  $PY dispatch_probe.py "$@" >> $OUT 2>> results/disp2.err
}
for LA in 1/24 1/4 1; do
  run --steps 16 --voices 8 --fill 0.5 --lookahead $LA --bars 16 --label "16x8-64notes-la$LA"
done
for LA in 1/24 1/4 1; do
  run --steps 16 --voices 8 --fill 1.0 --lookahead $LA --bars 16 --label "16x8full-128notes-la$LA"
done
for LA in 1/24 1/4 1; do
  run --steps 64 --voices 16 --fill 0.5 --lookahead $LA --bars 32 --label "64x16-512notes-la$LA"
done
run --scenario baseline --bars 16 --label "baseline-120"
echo DONE >&2
