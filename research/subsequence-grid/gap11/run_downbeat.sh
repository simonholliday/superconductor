#!/usr/bin/env bash
set -u
PY=~/venvs/subsequence-cookbook/bin/python
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/results/downbeat.jsonl"
: > "$OUT"
for LA in 1/24 1/4 1; do
	while [ "$(awk '{print ($1 < 1.2) ? 1 : 0}' /proc/loadavg)" != "1" ]; do sleep 10; done
	echo "-- la=$LA" >&2
	"$PY" "$HERE/grid_jitter_bench.py" --timing --freq --scenario grid --steps 64 --voices 64 \
		--fill 0.5 --length-beats 4 --lookahead "$LA" --label "64x64-2048notes-4beats-la$LA" \
		2>>"$HERE/results/err.txt" >> "$OUT"
done
echo done >&2
