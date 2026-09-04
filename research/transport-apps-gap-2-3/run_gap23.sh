#!/bin/bash
# RESEARCH PROTOTYPE runner (2026-09-03), not house style.
#
# Block G: the ten rows block F of #2025 never reached, plus block E's three
# 1024-frame rows (which were run by hand and left no log entry), re-taken
# under a load gate on the quiet workstation.
#
# The instrument is unchanged: ws_coalesce_bench2.py in
# scratchpad/transport-apps-gap-1-2/ is invoked in place, untouched, with the
# same venv, the same PYTHONPATH and the same 16 bars at 120 BPM.  The only
# method change is the pairing: a fresh no-adapter baseline is run under the
# gate immediately before every arm, and under the same engine-side lever as
# the arm, so each arm has a contemporaneous control rather than one baseline
# at each end of the block.  This is #2021's paired-pass method.
set -u
S=/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad
D=$S/transport-apps-gap-2-3
B=$S/transport-apps-gap-1-2
PY=$S/topology/venv/bin/python
export ADAPTER_BENCH_DIR=$S/transport-apps
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="/mnt/dev/Apps/2026-02 Sequencer"
R=$D/results; mkdir -p $R
PASS=${PASS:-G}
OUT=$R/gap23_$PASS.jsonl
: > $OUT
LOG=$R/run_$PASS.log
echo "start $(date -Is) loadavg $(cut -d' ' -f1-3 /proc/loadavg)" > $LOG

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

run () {
	tag=$1; shift
	wait_quiet
	export LOAD_START="$(cut -d' ' -f1 /proc/loadavg)"
	echo "== $tag : $*  loadavg $LOAD_START  $(date -Is)" >> $LOG
	timeout 200 $PY $B/ws_coalesce_bench2.py "$@" --tag "$tag" 2>>$LOG | tail -1 >> $OUT
	sleep 1
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
