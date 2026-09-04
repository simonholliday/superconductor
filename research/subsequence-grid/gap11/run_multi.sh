#!/usr/bin/env bash
set -u
PY=~/venvs/subsequence-cookbook/bin/python
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/results/multi.jsonl"
: > "$OUT"
for N in 1 2 4 8; do
	while [ "$(awk '{print ($1 < 3.0) ? 1 : 0}' /proc/loadavg)" != "1" ]; do sleep 10; done
	echo "-- patterns=$N" >&2
	"$PY" "$HERE/grid_jitter_bench.py" --timing --freq --scenario baseline --label "baseline-for-${N}x-16x8full" 2>>"$HERE/results/err.txt" >> "$OUT"
	"$PY" "$HERE/grid_jitter_bench.py" --timing --freq --scenario grid --steps 16 --voices 8 --fill 1.0 \
		--lookahead 1/24 --patterns "$N" --label "${N}-x-16x8-full-la1/24" 2>>"$HERE/results/err.txt" >> "$OUT"
done
echo done >&2
