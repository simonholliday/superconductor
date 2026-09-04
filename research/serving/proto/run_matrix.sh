#!/bin/bash
# Prototype measurement runner: Subsequence clock-jitter benchmark alone and beside each candidate service, idle and under load.
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
SEQ="/mnt/dev/Apps/2026-02 Sequencer"
BENCH="$SEQ/benchmarks/clock_jitter.py"
OUT=results.txt
BARS=${BARS:-32}
SECS=$((BARS * 2 + 4))
echo "# run $(date -Is) on $(hostname) $(nproc) cores; load avg $(cut -d' ' -f1-3 /proc/loadavg)" >> $OUT
run_bench () {  # $1 label, $2 taskset-cpu or ""
	local pin=""; [ -n "$2" ] && pin="taskset -c $2"
	echo "## $1" >> $OUT
	PYTHONPATH="$SEQ" $pin venv-seq/bin/python "$BENCH" --bars $BARS --device SUPERINTENDENT_NO_SUCH_DEVICE 2>/dev/null | grep -E "Mean|Median|Std|P95|P99|Max" >> $OUT
}
run_bench "baseline: no service" ""
for stack in starlette aiohttp websockets quart; do
	case $stack in starlette) port=18771;; aiohttp) port=18772;; websockets) port=18773;; quart) port=18774;; esac
	for mode in idle load4 load16; do
		venv-$stack/bin/python proto/srv_$stack.py $port >/dev/null 2>&1 & SP=$!
		sleep 2.5
		c0=$(venv-seq/bin/python proto/cpu.py $SP)
		LP=""
		if [ $mode = load4 ]; then venv-websockets/bin/python proto/load.py $port $SECS 4 > load.tmp 2>&1 & LP=$!; fi
		if [ $mode = load16 ]; then venv-websockets/bin/python proto/load.py $port $SECS 16 > load.tmp 2>&1 & LP=$!; fi
		run_bench "$stack $mode" ""
		c1=$(venv-seq/bin/python proto/cpu.py $SP)
		[ -n "$LP" ] && wait $LP
		echo "service cpu-seconds before/after: $c0 / $c1 (rss MB is 2nd field); bench wall ~${SECS}s" >> $OUT
		[ -n "$LP" ] && { echo -n "load: " >> $OUT; tail -1 load.tmp >> $OUT; }
		kill $SP; wait $SP 2>/dev/null
	done
done
# Worst case: service under 16-client load pinned to the same core as Subsequence.
taskset -c 3 venv-starlette/bin/python proto/srv_starlette.py 18771 >/dev/null 2>&1 & SP=$!
sleep 2.5
venv-websockets/bin/python proto/load.py 18771 $SECS 16 > load.tmp 2>&1 & LP=$!
run_bench "starlette load16, service and Subsequence both pinned to cpu 3" "3"
wait $LP; echo -n "load: " >> $OUT; tail -1 load.tmp >> $OUT
kill $SP; wait $SP 2>/dev/null
echo "# done $(date -Is)" >> $OUT
