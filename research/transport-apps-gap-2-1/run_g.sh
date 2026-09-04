#!/bin/bash
# Research prototype runner (2026-09-03), transport-apps gap-2-1.
# Same instrument, venv, machine and load gate as run_coalesce_2.sh in the
# sibling directory; this runner only fills rows block F did not reach and adds
# two the earlier blocks never ran: read-batching at an isolated 5 Hz tap rate,
# and a 500 Hz runaway under read-batching (the safety-valve row).
set -u
S=/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad
D=$S/transport-apps-gap-1-2
G=$S/transport-apps-gap-2-1
PY=$S/topology/venv/bin/python
export ADAPTER_BENCH_DIR=$G
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="/mnt/dev/Apps/2026-02 Sequencer"
R=$G/results; mkdir -p $R
OUT=$R/gap21.jsonl
: > $OUT
LOG=$R/run.log
echo "start $(date -Is) loadavg $(cut -d' ' -f1-3 /proc/loadavg)" > $LOG

QUIET=${QUIET:-110}

load_x100 () {
	local l i f
	l=$(cut -d' ' -f1 /proc/loadavg)
	i=${l%%.*}
	f=${l#*.}
	echo $((10#$i * 100 + 10#$f))
}

others_running () {
	# Another point was running the same bench from the shared gap-1-2 copy on
	# the shared ports while this block started, which corrupted one row.  This
	# block runs its own copy on its own ports and also waits its turn.
	pgrep -f 'transport-apps-gap-1-2/ws_coalesce_bench' > /dev/null
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

run H baseline
run H ws-thread      --rate 5
run H ws-batch-read  --rate 5
run H ws-coalesce    --burst 128  --burst-period 2.0
run H ws-batch-read  --burst 128  --burst-period 2.0
run H ws-direct      --burst 128  --burst-period 2.0
run H ws-batch-read  --burst 1024 --burst-period 4.0
run H ws-thread      --rate 500
run H ws-batch-read  --rate 500
run H baseline
echo "end $(date -Is) loadavg $(cut -d' ' -f1-3 /proc/loadavg)" >> $LOG
echo "ALLDONE" >> $LOG
