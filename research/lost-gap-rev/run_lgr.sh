#!/bin/bash
# Research prototype runner (2026-09-04), transport-apps: the revision block.
#
# Block P takes the two control rows the reviser found missing from blocks L,
# M and N: per-message crossing at a 128-frame burst, which every 128-frame
# claim in the finding is read against but which no block of this point ran,
# and the flagged shape at 50 Hz under no lever, which the two lever rows are
# read against but which was quoted from #2025's block F instead.  Baselines
# at both ends.
#
# Same instrument, venv and machine as run_lg.sh in scratchpad/lost-gap: the
# real subsequence.sequencer.Sequencer with _jitter_log, 16 bars at 120 BPM
# (1536 pulses), spin-wait on at the engine's own 1 ms margin, a device name
# matching no MIDI port, asyncio's default epoll selector.  adapter_bench.py,
# wcb.py and wcb2.py here are copies of that block's copies with the four port
# constants moved again, to 9171/9173/9174/9175, so this block collides with
# neither the shared copies nor block L, M or N's.
set -u
S=/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad
G=$S/lost-gap-rev
PY=$S/topology/venv/bin/python
export ADAPTER_BENCH_DIR=$G
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="/mnt/dev/Apps/2026-02 Sequencer"
R=$G/results; mkdir -p $R
OUT=$R/lostgaprev.jsonl
: > $OUT
LOG=$R/run.log
echo "start $(date -Is) loadavg $(cut -d' ' -f1-3 /proc/loadavg)" > $LOG

# QUIET is the one-minute load average in hundredths.  120 is the gate
# run_coalesce_2.sh used for #2025's block F; blocks L, M and N ran at 150.
# This block runs at 120, the tighter of the two, so its rows are admitted on
# the same condition as the block-F rows they replace.  Every row carries its
# own load at start and at end.
QUIET=${QUIET:-120}

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
	pgrep -f 'transport-apps-gap-2-1-rev/wcb' > /dev/null ||
	pgrep -f 'lost-gap/wcb' > /dev/null
}

wait_quiet () {
	local waited=0
	while [ "$(load_x100)" -gt "$QUIET" ] || others_running; do
		sleep 20
		waited=$((waited + 20))
		if [ $waited -ge 1800 ]; then
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

run P baseline
run P ws-thread    --burst 128 --burst-period 2.0
run P ws-coalesce  --rate 50
run P baseline
echo "end $(date -Is) loadavg $(cut -d' ' -f1-3 /proc/loadavg)" >> $LOG
echo "ALLDONE" >> $LOG
