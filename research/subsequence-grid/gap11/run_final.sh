#!/usr/bin/env bash
# PROTOTYPE runner (research only, 2026-09-03).
# Final block: the CPU-frequency confirmation of the bimodal rebuild cost, and
# the same grids at 180 BPM, where a pulse is 13.889 ms instead of 20.833 ms.
set -u
PY=~/venvs/subsequence-cookbook/bin/python
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/results/${1:-final}.jsonl"
THRESH="${2:-1.20}"
: > "$OUT"

wait_quiet () {
	local i=0
	while [ "$i" -lt 900 ]; do
		if [ "$(awk -v t="$THRESH" '{print ($1 < t) ? 1 : 0}' /proc/loadavg)" = "1" ]; then return 0; fi
		sleep 10; i=$((i + 10))
	done
}

run () {
	echo "-- $* (load $(cut -d' ' -f1 /proc/loadavg))" >&2
	"$PY" "$HERE/grid_jitter_bench.py" --timing --freq "$@" 2>>"$HERE/results/err.txt" >> "$OUT"
}

wait_quiet
run --scenario grid --steps 16 --voices 8  --fill 0.5 --lookahead 1/24 --label "freq-16x8-64notes"
run --scenario grid --steps 16 --voices 8  --fill 1.0 --lookahead 1/24 --label "freq-16x8-full"
run --scenario grid --steps 64 --voices 16 --fill 0.5 --lookahead 1/24 --length-beats 4 --label "freq-64x16-in-4-beats"

wait_quiet
run --scenario baseline --bpm 180 --label "baseline-180"
run --scenario grid --bpm 180 --steps 16 --voices 8  --fill 1.0 --lookahead 1/24 --label "16x8-full-180bpm"
run --scenario grid --bpm 180 --steps 64 --voices 16 --fill 0.5 --lookahead 1/24 --length-beats 4 --label "64x16-in-4-beats-180bpm"

echo "wrote $OUT" >&2
