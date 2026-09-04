#!/bin/bash
# Research prototype runner (2026-09-04), transport-apps: the re-take block.
#
# Same instrument, venv, machine and load gate as run_coalesce_2.sh in
# scratchpad/transport-apps-gap-1-2: the real subsequence.sequencer.Sequencer
# with _jitter_log, 16 bars at 120 BPM (1536 pulses), spin-wait on, a device
# name matching no MIDI port, asyncio's default epoll selector unless a row
# says otherwise.  adapter_bench.py, wcb.py and wcb2.py in this directory are
# copies of that block's files with the four port constants moved to
# 9161/9163/9164/9165, so this block cannot collide with another point running
# the shared copies on the shared ports.
#
# Block N re-takes the one row of block L that the load spoiled: read-batching
# at 1024 frames, whose one-minute load average drifted from 1.22 to 3.70 while
# another session on this workstation started heavy work.  That row is kept in
# lostgap.jsonl and is quoted nowhere.  Baselines at both ends.
set -u
S=/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad
G=$S/lost-gap
PY=$S/topology/venv/bin/python
export ADAPTER_BENCH_DIR=$G
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="/mnt/dev/Apps/2026-02 Sequencer"
R=$G/results; mkdir -p $R
OUT=$R/lostgap2.jsonl
: > $OUT
LOG=$R/run2.log
echo "start $(date -Is) loadavg $(cut -d' ' -f1-3 /proc/loadavg)" > $LOG

# The workstation is shared with the other points of this run.  QUIET is the
# one-minute load average in hundredths; 120 means 1.20, which is
# run_coalesce_2.sh's own gate.  This block runs at 150, for the reason
# #2033's block K raised its own gate: another session on this workstation was
# holding the one-minute average between 1.27 and 1.43 throughout, so the 1.20
# gate could not clear.  Every row carries its own load at start and at end.
QUIET=${QUIET:-150}

load_x100 () {
	local l i f
	l=$(cut -d' ' -f1 /proc/loadavg)
	i=${l%%.*}
	f=${l#*.}
	echo $((10#$i * 100 + 10#$f))
}

others_running () {
	pgrep -f 'transport-apps-gap-1-2/ws_coalesce_bench' > /dev/null ||
	pgrep -f 'transport-apps-gap-2-1/wcb' > /dev/null ||
	pgrep -f 'transport-apps-gap-2-1-rev/wcb' > /dev/null
}

wait_quiet () {
	local waited=0
	while [ "$(load_x100)" -gt "$QUIET" ] || others_running; do
		sleep 20
		waited=$((waited + 20))
		if [ $waited -ge 2400 ]; then
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
	timeout 150 $PY $G/wcb2.py "$@" --tag "$tag" 2>>$LOG | tail -1 >> $OUT
	sleep 1
}

run N baseline
run N ws-batch-read  --burst 1024 --burst-period 4.0
run N baseline
echo "end $(date -Is) loadavg $(cut -d' ' -f1-3 /proc/loadavg)" >> $LOG
echo "ALLDONE" >> $LOG
