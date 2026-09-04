#!/bin/bash
# Reviser prototype runner (2026-09-03).  Same method as ../run_bench.sh: real
# Sequencer clock, 16 bars at 120 BPM (1536 pulses), 50 Hz inbound, epoll.
set -u
S=/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad/transport-apps
PY=$S/../topology/venv/bin/python
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="/mnt/dev/Apps/2026-02 Sequencer"
R=$S/revise/results; mkdir -p $R
OUT=$R/ws_drain_bench.jsonl
: > $OUT
echo "load average at start: $(cut -d' ' -f1-3 /proc/loadavg)" > $R/run.log
run () { echo "== $*  load $(cut -d' ' -f1 /proc/loadavg)" >> $R/run.log; timeout 120 $PY $S/revise/ws_drain_bench.py "$1" $S --rate 50 2>>$R/run.log | tail -1 >> $OUT; sleep 1; }

run baseline
run baseline-pattern
run ws-thread
run ws-thread-drain-beat
run ws-thread-drain-resched
run ws-thread-drain-resched-only
echo "load average at end: $(cut -d' ' -f1-3 /proc/loadavg)" >> $R/run.log
echo done >> $R/run.log
