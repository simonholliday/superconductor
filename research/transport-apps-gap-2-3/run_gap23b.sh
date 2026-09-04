#!/bin/bash
# RESEARCH PROTOTYPE runner (2026-09-03), not house style.
#
# The rows block F of #2025 never reached, plus block E's three 1024-frame
# rows, re-taken under a load gate on the quiet workstation with a fresh
# no-adapter baseline immediately before every arm.
#
# The instrument is ws_coalesce_bench2.py in
# scratchpad/transport-apps-gap-1-2/, imported unmodified through
# bench_port.py, which changes only the loopback port the stand-in service
# listens on (9114 in the filed harness, GAP23_PORT here).  The first attempt
# at this block, results/gap23_G.jsonl, lost two of five arm rows to another
# process holding 9114.
#
# Two guards the filed runner does not have:
#   - the port is checked free before every row, and the row waits if it is not;
#   - after the block, check.py rejects any row whose sender did not report,
#     or whose reported send count does not match the row's inbound count.
set -u
S=/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad
D=$S/transport-apps-gap-2-3
PY=$S/topology/venv/bin/python
export ADAPTER_BENCH_DIR=$S/transport-apps
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="/mnt/dev/Apps/2026-02 Sequencer"
export GAP23_PORT=${GAP23_PORT:-9214}
R=$D/results; mkdir -p $R
PASS=${PASS:-H}
OUT=$R/gap23_$PASS.jsonl
: > $OUT
LOG=$R/run_$PASS.log
echo "start $(date -Is) loadavg $(cut -d' ' -f1-3 /proc/loadavg) port $GAP23_PORT" > $LOG

QUIET=${QUIET:-120}
MAXWAIT=${MAXWAIT:-5400}

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
		if [ $waited -ge $MAXWAIT ]; then
			echo "!! GATE EXPIRED after ${waited}s at loadavg $(cut -d' ' -f1 /proc/loadavg); row runs loaded and is not quotable" >> $LOG
			return
		fi
	done
}

wait_port () {
	local waited=0
	while ss -ltn 2>/dev/null | grep -q ":$GAP23_PORT "; do
		echo "!! port $GAP23_PORT still held, waiting" >> $LOG
		sleep 5
		waited=$((waited + 5))
		[ $waited -ge 120 ] && { echo "!! PORT NEVER FREED" >> $LOG; return; }
	done
}

run () {
	tag=$1; shift
	wait_quiet
	wait_port
	export LOAD_START="$(cut -d' ' -f1 /proc/loadavg)"
	echo "== $tag : $*  loadavg $LOAD_START  $(date -Is)" >> $LOG
	timeout 200 $PY $D/bench_port.py "$@" --tag "$tag" 2>>$LOG | tail -1 >> $OUT
	sleep 2
}

# Each pair is a no-adapter baseline immediately followed by the arm it
# controls, under the same lever as the arm.
run $PASS baseline
run $PASS ws-batch-read  --burst 16   --burst-period 1.0
run $PASS baseline
run $PASS ws-coalesce    --burst 16   --burst-period 1.0
run $PASS baseline
run $PASS ws-thread      --burst 128  --burst-period 2.0
run $PASS baseline
run $PASS ws-coalesce    --burst 128  --burst-period 2.0
run $PASS baseline
run $PASS ws-batch-read  --burst 128  --burst-period 2.0
run $PASS baseline
run $PASS ws-direct      --burst 128  --burst-period 2.0
run $PASS baseline
run $PASS ws-thread      --burst 1024 --burst-period 4.0
run $PASS baseline
run $PASS ws-coalesce    --burst 1024 --burst-period 4.0
run $PASS baseline
run $PASS ws-batch-read  --burst 1024 --burst-period 4.0
run $PASS baseline
run $PASS ws-drain-beat  --burst 1024 --burst-period 4.0
run $PASS baseline
run $PASS ws-direct      --burst 1024 --burst-period 4.0
run $PASS baseline --spin-ms 2
run $PASS ws-coalesce    --rate 50 --spin-ms 2
run $PASS baseline --selector select
run $PASS ws-coalesce    --rate 50 --selector select
echo "end $(date -Is) loadavg $(cut -d' ' -f1-3 /proc/loadavg)" >> $LOG
echo "ALLDONE" >> $LOG
