#!/bin/bash
# Continuation of run_j.sh (2026-09-04): the four rows the first run could not
# reach.  The only difference is the load gate, raised from 1.10 to 1.50,
# because this session's own work kept the one-minute average above 1.10 and
# the original gate could not clear.  Every row still stamps its own load at
# start and end, and a closing baseline is taken under the same gate.
set -u
S=/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad
G=$S/transport-apps-gap-2-1-rev
PY=$S/topology/venv/bin/python
export ADAPTER_BENCH_DIR=$G
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="/mnt/dev/Apps/2026-02 Sequencer"
R=$G/results
OUT=$R/gap21rev.jsonl
LOG=$R/run.log
echo "resume $(date -Is) loadavg $(cut -d' ' -f1-3 /proc/loadavg)" >> $LOG

QUIET=${QUIET:-150}

load_x100 () {
	local l i f
	l=$(cut -d' ' -f1 /proc/loadavg)
	i=${l%%.*}
	f=${l#*.}
	echo $((10#$i * 100 + 10#$f))
}

others_running () {
	pgrep -f 'transport-apps-gap-1-2/ws_coalesce_bench' > /dev/null || \
	pgrep -f 'transport-apps-gap-2-1/wcb' > /dev/null
}

wait_quiet () {
	local waited=0
	while [ "$(load_x100)" -gt "$QUIET" ] || others_running; do
		sleep 20
		waited=$((waited + 20))
		if [ $waited -ge 900 ]; then
			echo "!! gave up waiting for a quiet machine after ${waited}s" >> $LOG
			return
		fi
	done
}

run () {
	tag=$1; shift
	wait_quiet
	export LOAD_START="$(cut -d' ' -f1 /proc/loadavg)"
	echo "== $tag : $*  loadavg $LOAD_START  tap=${TAP_IN_BURST:-0}  gate $QUIET" >> $LOG
	timeout 150 $PY $G/wcb3.py "$@" --tag "$tag" 2>>$LOG | tail -1 >> $OUT
	sleep 1
}

export TAP_IN_BURST=1
run K ws-thread              --burst 1024 --burst-period 4.0
run K ws-batch-read          --burst 1024 --burst-period 4.0
run K ws-batch-read-capped   --burst 1024 --burst-period 4.0 --cap 64
export TAP_IN_BURST=0
run K baseline

echo "end $(date -Is) loadavg $(cut -d' ' -f1-3 /proc/loadavg)" >> $LOG
echo "ALLDONE" >> $LOG
