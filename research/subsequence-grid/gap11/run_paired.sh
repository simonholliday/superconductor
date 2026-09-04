#!/usr/bin/env bash
# PROTOTYPE runner (research only, 2026-09-03).
# The workstation is shared with other work, so every grid run is paired with a
# baseline run taken immediately before it, and both wait for the one-minute
# load average to fall below THRESH first.  Each row therefore carries its own
# contemporaneous control.
set -u
PY=~/venvs/subsequence-cookbook/bin/python
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/results/${1:-paired}.jsonl"
TIMING="${2:-}"
THRESH="${3:-1.20}"
: > "$OUT"

wait_quiet () {
	local i=0
	while [ "$i" -lt 900 ]; do
		if [ "$(awk -v t="$THRESH" '{print ($1 < t) ? 1 : 0}' /proc/loadavg)" = "1" ]; then
			return 0
		fi
		sleep 10
		i=$((i + 10))
	done
	echo "!! gave up waiting for quiet (load $(cut -d' ' -f1 /proc/loadavg))" >&2
}

run () {
	echo "-- $* (load $(cut -d' ' -f1 /proc/loadavg))" >&2
	"$PY" "$HERE/grid_jitter_bench.py" $TIMING "$@" 2>>"$HERE/results/err.txt" >> "$OUT"
}

pair () {
	local label="$1"; shift
	wait_quiet
	run --scenario baseline --label "baseline-for-$label"
	run --scenario grid --label "$label" "$@"
}

for LA in 1/24 1/4 1; do
	pair "16x8-64notes-la$LA"   --steps 16 --voices 8  --fill 0.5 --lookahead "$LA"
done
for LA in 1/24 1/4 1; do
	pair "16x8-full-la$LA"      --steps 16 --voices 8  --fill 1.0 --lookahead "$LA"
done
for LA in 1/24 1/4 1; do
	pair "64x16-512notes-la$LA" --steps 64 --voices 16 --fill 0.5 --lookahead "$LA"
done

echo "wrote $OUT" >&2
