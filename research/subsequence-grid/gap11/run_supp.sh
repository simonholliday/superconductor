#!/usr/bin/env bash
# PROTOTYPE runner (research only, 2026-09-03).
# Supplementary block: more rebuild samples for the big grid (a 64-step
# sixteenth-note pattern is 16 beats long, so a 16-bar run sees only four
# rebuilds), and a cadence control that forces the 512-note grid to rebuild at
# the four-beat cadence of a drum pattern.
set -u
PY=~/venvs/subsequence-cookbook/bin/python
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/results/${1:-supp}.jsonl"
THRESH="${2:-1.20}"
: > "$OUT"

wait_quiet () {
	local i=0
	while [ "$i" -lt 900 ]; do
		if [ "$(awk -v t="$THRESH" '{print ($1 < t) ? 1 : 0}' /proc/loadavg)" = "1" ]; then return 0; fi
		sleep 10; i=$((i + 10))
	done
	echo "!! gave up waiting for quiet (load $(cut -d' ' -f1 /proc/loadavg))" >&2
}

run () {
	echo "-- $* (load $(cut -d' ' -f1 /proc/loadavg))" >&2
	"$PY" "$HERE/grid_jitter_bench.py" --timing "$@" 2>>"$HERE/results/err.txt" >> "$OUT"
}

# 64 bars so the 16-beat grid pattern rebuilds sixteen times.
for LA in 1/24 1/4 1; do
	wait_quiet
	run --scenario baseline --bars 64 --label "baseline64-for-64x16-la$LA"
	run --scenario grid --bars 64 --steps 64 --voices 16 --fill 0.5 --lookahead "$LA" --label "64x16-512notes-64bars-la$LA"
done

# Cadence control: the same 512 notes forced into a four-beat cycle, so the
# rebuild lands every 96 pulses like a one-bar drum grid.
for LA in 1/24 1; do
	wait_quiet
	run --scenario baseline --label "baseline-for-64x16-4beat-la$LA"
	run --scenario grid --steps 64 --voices 16 --fill 0.5 --length-beats 4 --lookahead "$LA" --label "64x16-512notes-in-4-beats-la$LA"
done

# Where does it break?  A grid big enough to overrun a pulse, four-beat cycle.
for V in 32 64; do
	wait_quiet
	run --scenario baseline --label "baseline-for-64x${V}-4beat"
	run --scenario grid --steps 64 --voices "$V" --fill 0.5 --length-beats 4 --lookahead 1/24 --label "64x${V}-in-4-beats-la1/24"
done

echo "wrote $OUT" >&2
