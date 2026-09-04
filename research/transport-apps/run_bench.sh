#!/bin/bash
# Research prototype runner (2026-09-03).  Real Sequencer clock, 16 bars at 120 BPM
# (1536 pulses at 20.833 ms), one adapter shape per run, 50 Hz inbound commands
# unless stated.  Output: results/*.jsonl (one JSON line per run).
set -u
S=/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad/transport-apps
PY=$S/../topology/venv/bin/python
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="/mnt/dev/Apps/2026-02 Sequencer"
R=$S/results; mkdir -p $R
OUT=$R/adapter_bench.jsonl
: > $OUT
BARS=${BARS:-16}
echo "load average at start: $(cut -d' ' -f1-3 /proc/loadavg)" > $R/run.log
run () { echo "== $*" >> $R/run.log; timeout 120 $PY $S/adapter_bench.py "$@" --bars $BARS 2>>$R/run.log | tail -1 >> $OUT; sleep 1; }

run baseline
run osc-loop --rate 50
run osc-thread --rate 50
run osc-thread-drain --rate 50
run ws-loop --rate 50
run ws-thread --rate 50
run tcp-thread --rate 50
run osc-thread --rate 5
run ws-thread --rate 5
run baseline --selector select
run osc-loop --rate 50 --selector select
run osc-thread --rate 50 --selector select
run ws-thread --rate 50 --selector select
run tcp-thread --rate 50 --selector select
echo "load average at end: $(cut -d' ' -f1-3 /proc/loadavg)" >> $R/run.log
echo done >> $R/run.log
