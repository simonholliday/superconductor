#!/bin/bash
# Prototype repeat runner (not house style): repeats of the two conditions whose single-run P99 moved
# in results.txt, two more baselines to bracket them, and the plain-uvicorn variant that the design recommends.
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
SEQ="/mnt/dev/Apps/2026-02 Sequencer"
BENCH="$SEQ/benchmarks/clock_jitter.py"
OUT=results-repeats.txt
BARS=${BARS:-32}
SECS=$((BARS * 2 + 4))
echo "# repeats $(date -Is) on $(hostname) $(nproc) cores; load avg $(cut -d' ' -f1-3 /proc/loadavg)" >> $OUT
run_bench () {  # $1 label
	echo "## $1" >> $OUT
	PYTHONPATH="$SEQ" venv-seq/bin/python "$BENCH" --bars $BARS --device SUPERINTENDENT_NO_SUCH_DEVICE 2>/dev/null | grep -E "Mean|Median|Std|P95|P99|Max" >> $OUT
}
run_service () {  # $1 label, $2 venv suffix, $3 server script, $4 port, $5 client count (0 = idle)
	venv-$2/bin/python proto/$3 $4 >/dev/null 2>&1 & SP=$!
	sleep 2.5
	c0=$(venv-seq/bin/python proto/cpu.py $SP)
	LP=""
	if [ "$5" != 0 ]; then venv-websockets/bin/python proto/load.py $4 $SECS $5 > load-repeats.tmp 2>&1 & LP=$!; fi
	run_bench "$1"
	c1=$(venv-seq/bin/python proto/cpu.py $SP)
	[ -n "$LP" ] && wait $LP
	echo "service cpu-seconds before/after: $c0 / $c1 (rss MB is 2nd field); bench wall ~${SECS}s" >> $OUT
	[ -n "$LP" ] && { echo -n "load: " >> $OUT; tail -1 load-repeats.tmp >> $OUT; }
	kill $SP; wait $SP 2>/dev/null
}
run_bench "baseline: no service (repeat 2)"
run_service "starlette load4 (repeat 2)" starlette srv_starlette.py 18771 4
run_service "websockets load16 (repeat 2)" websockets srv_websockets.py 18773 16
run_service "starlette-plain idle" starlette-plain srv_starlette.py 18775 0
run_service "starlette-plain load16" starlette-plain srv_starlette.py 18775 16
run_bench "baseline: no service (repeat 3)"
run_service "starlette load4 (repeat 3)" starlette srv_starlette.py 18771 4
run_service "websockets load16 (repeat 3)" websockets srv_websockets.py 18773 16
run_service "starlette-plain load16 (repeat 2)" starlette-plain srv_starlette.py 18775 16
echo "# done $(date -Is)" >> $OUT
