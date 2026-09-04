#!/usr/bin/env bash
# PROTOTYPE runner (research only, 2026-09-03).
# Pass A: jitter only (no timing wrappers).  Pass B: same matrix with the
# on-loop rebuild timers.  Baselines bracket each pass.
set -u
PY=~/venvs/subsequence-cookbook/bin/python
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/results/${1:-matrix}.jsonl"
TIMING="${2:-}"
: > "$OUT"

run () {
	echo "-- $* (load $(cut -d' ' -f1 /proc/loadavg))" >&2
	"$PY" "$HERE/grid_jitter_bench.py" $TIMING "$@" 2>>"$HERE/results/err.txt" >> "$OUT"
}

run --scenario baseline --label "baseline-start"

for LA in 1/24 1/4 1; do
	run --scenario grid --steps 16 --voices 8  --fill 0.5 --lookahead "$LA" --label "16x8-64notes"
done
for LA in 1/24 1/4 1; do
	run --scenario grid --steps 16 --voices 8  --fill 1.0 --lookahead "$LA" --label "16x8-full"
done
for LA in 1/24 1/4 1; do
	run --scenario grid --steps 64 --voices 16 --fill 0.5 --lookahead "$LA" --label "64x16-512notes"
done

run --scenario baseline --label "baseline-end"
echo "wrote $OUT" >&2
