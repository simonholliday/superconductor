#!/bin/bash
# Research prototype runner (2026-09-03).  Same method, machine, venv and
# conditions as scratchpad/transport-apps/revise/run_drain.sh: the real
# Sequencer clock with _jitter_log, 16 bars at 120 BPM (1536 pulses), spin-wait
# on, no MIDI port, asyncio's default epoll selector unless a row says
# otherwise.  Blocks A and B are the crossing shapes under the engine's own
# settings, B a repeat of A's key rows.  Blocks C and D re-run them under the
# two engine-side levers the crossing short list's C column names: a 2 ms spin
# margin (default 1 ms, sequencer.py:465) and a SelectSelector loop.
set -u
S=/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad
D=$S/transport-apps-gap-1-2
PY=$S/topology/venv/bin/python
export ADAPTER_BENCH_DIR=$S/transport-apps
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="/mnt/dev/Apps/2026-02 Sequencer"
R=$D/results; mkdir -p $R
OUT=$R/ws_coalesce_bench.jsonl
: > $OUT
LOG=$R/run.log
echo "start $(date -Is) loadavg $(cut -d' ' -f1-3 /proc/loadavg)" > $LOG

# The workstation is shared.  A timing row taken while another job is using the
# cores is worthless, so wait for a quiet machine before every row and record
# the one-minute load average at the row's start and end on the row itself.
# QUIET is that average in hundredths: 120 means 1.20.
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
	timeout 150 $PY $D/ws_coalesce_bench.py "$@" --tag "$tag" 2>>$LOG | tail -1 >> $OUT
	sleep 1
}

full_block () {
	B=$1
	run $B baseline
	run $B ws-thread     --rate 5
	run $B ws-coalesce   --rate 5
	run $B ws-drain-beat --rate 5
	run $B ws-thread     --rate 25
	run $B ws-coalesce   --rate 25
	run $B ws-drain-beat --rate 25
	run $B ws-thread     --rate 50
	run $B ws-coalesce   --rate 50
	run $B ws-drain-beat --rate 50
	run $B ws-thread     --rate 200
	run $B ws-coalesce   --rate 200
	run $B ws-thread     --rate 500
	run $B ws-coalesce   --rate 500
	run $B ws-thread     --burst 16  --burst-period 1.0
	run $B ws-coalesce   --burst 16  --burst-period 1.0
	run $B ws-thread     --burst 128 --burst-period 2.0
	run $B ws-coalesce   --burst 128 --burst-period 2.0
	run $B ws-drain-beat --burst 128 --burst-period 2.0
	run $B baseline
}

repeat_block () {
	B=$1
	run $B baseline
	run $B ws-thread     --rate 5
	run $B ws-coalesce   --rate 5
	run $B ws-thread     --rate 25
	run $B ws-coalesce   --rate 25
	run $B ws-drain-beat --rate 25
	run $B ws-thread     --rate 50
	run $B ws-coalesce   --rate 50
	run $B ws-thread     --burst 128 --burst-period 2.0
	run $B ws-coalesce   --burst 128 --burst-period 2.0
	run $B baseline
}

lever_block () {
	B=$1
	run $B baseline    --spin-ms 2
	run $B ws-thread   --rate 25 --spin-ms 2
	run $B ws-coalesce --rate 25 --spin-ms 2
	run $B ws-thread   --rate 50 --spin-ms 2
	run $B baseline    --selector select
	run $B ws-thread   --rate 25 --selector select
	run $B ws-coalesce --rate 25 --selector select
	run $B ws-thread   --rate 50 --selector select
}

full_block A
repeat_block B
lever_block C
lever_block D
echo "end $(date -Is) loadavg $(cut -d' ' -f1-3 /proc/loadavg)" >> $LOG
echo "ALLDONE" >> $LOG
