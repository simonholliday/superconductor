#!/usr/bin/env bash
# PROTOTYPE runner (research only, 2026-09-03).
# Where does the damage land when a rebuild overruns its pulse?  A 1024-note
# grid on a four-beat cycle overruns sometimes; run it at all three lookaheads
# and record the jitter of the rebuild pulse and the three pulses after it.
set -u
PY=~/venvs/subsequence-cookbook/bin/python
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/results/overrun.jsonl"
: > "$OUT"
for LA in 1/24 1/4 1; do
	while [ "$(awk '{print ($1 < 1.2) ? 1 : 0}' /proc/loadavg)" != "1" ]; do sleep 10; done
	echo "-- la=$LA (load $(cut -d' ' -f1 /proc/loadavg))" >&2
	"$PY" "$HERE/grid_jitter_bench.py" --timing --freq --scenario grid --steps 64 --voices 32 \
		--fill 0.5 --length-beats 4 --lookahead "$LA" --label "64x32-1024notes-4beats-la$LA" \
		2>>"$HERE/results/err.txt" >> "$OUT"
done
echo done >&2
