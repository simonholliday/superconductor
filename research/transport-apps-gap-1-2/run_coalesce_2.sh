#!/bin/bash
# Research prototype runner, revision block (2026-09-03).  Same method,
# machine, venv, load gate and conditions as run_coalesce.sh; this one runs
# ws_coalesce_bench2.py, which adds the two shapes the first runner omitted
# (read-batching over the socket, and applying off the loop on the link
# thread), and carries the 1024-frame burst rows, which the first block ran by
# hand outside run_coalesce.sh and so left with no log entry.
#
# Block F is the whole revision block, run once.
set -u
S=/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad
D=$S/transport-apps-gap-1-2
PY=$S/topology/venv/bin/python
export ADAPTER_BENCH_DIR=$S/transport-apps
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="/mnt/dev/Apps/2026-02 Sequencer"
R=$D/results; mkdir -p $R
OUT=$R/ws_coalesce_bench2.jsonl
: > $OUT
LOG=$R/run2.log
echo "start $(date -Is) loadavg $(cut -d' ' -f1-3 /proc/loadavg)" > $LOG

QUIET=${QUIET:-120}

load_x100 () {
	local l i f
	l=$(cut -d' ' -f1 /proc/loadavg)
	i=${l%%.*}
	f=${l#*.}
	echo $((10#$i * 100 + 10#$f))
}

wait_quiet () {
	local waited=0
	while [ "$(load_x100)" -gt "$QUIET" ]; do
		sleep 20
		waited=$((waited + 20))
		if [ $waited -ge 5400 ]; then
			echo "!! gave up waiting for a quiet machine after ${waited}s" >> $LOG
			return
		fi
	done
}

run () {
	tag=$1; shift
	wait_quiet
	export LOAD_START="$(cut -d' ' -f1 /proc/loadavg)"
	echo "== $tag : $*  loadavg $LOAD_START" >> $LOG
	timeout 150 $PY $D/ws_coalesce_bench2.py "$@" --tag "$tag" 2>>$LOG | tail -1 >> $OUT
	sleep 1
}

run F baseline
run F ws-thread      --rate 25
run F ws-coalesce    --rate 25
run F ws-batch-read  --rate 25
run F ws-direct      --rate 25
run F ws-thread      --rate 50
run F ws-coalesce    --rate 50
run F ws-batch-read  --rate 50
run F ws-direct      --rate 50
run F ws-thread      --burst 128  --burst-period 2.0
run F ws-coalesce    --burst 128  --burst-period 2.0
run F ws-batch-read  --burst 128  --burst-period 2.0
run F ws-direct      --burst 128  --burst-period 2.0
run F ws-thread      --burst 1024 --burst-period 4.0
run F ws-coalesce    --burst 1024 --burst-period 4.0
run F ws-batch-read  --burst 1024 --burst-period 4.0
run F ws-drain-beat  --burst 1024 --burst-period 4.0
run F ws-coalesce    --rate 50 --spin-ms 2
run F ws-coalesce    --rate 50 --selector select
run F baseline
echo "end $(date -Is) loadavg $(cut -d' ' -f1-3 /proc/loadavg)" >> $LOG
echo "ALLDONE" >> $LOG
