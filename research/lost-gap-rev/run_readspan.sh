#!/bin/bash
# Research prototype (2026-09-04): how much of the batched crossing is the
# prototype's per-frame probe rather than the batching device?  Measures the
# span from the first frame of a burst being taken off the connection to the
# last, under the three read patterns: the plain `async for` every non-batching
# shape in the bench uses, and the two probes a batching reader can be built
# from.  Sender and reader share one process here, so the absolute spans are
# not the bench's; the ratio between the patterns is what this measures.
# Waits for block P to finish and for a quiet machine first.
set -u
S=/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad
G=$S/lost-gap-rev
PY=$S/topology/venv/bin/python
LOG=$G/results/readspan.txt
QUIET=${QUIET:-120}
load_x100 () { local l i f; l=$(cut -d' ' -f1 /proc/loadavg); i=${l%%.*}; f=${l#*.}; echo $((10#$i * 100 + 10#$f)); }
# wait for block P
for _ in $(seq 1 300); do grep -q ALLDONE $G/results/run.log 2>/dev/null && break; sleep 20; done
waited=0
while [ "$(load_x100)" -gt "$QUIET" ]; do sleep 20; waited=$((waited+20)); [ $waited -ge 1800 ] && { echo "!! gave up waiting after ${waited}s" >> $LOG; break; }; done
echo "start $(date -Is) loadavg $(cut -d' ' -f1-3 /proc/loadavg)" > $LOG
for m in asyncfor batchsleep batchwait; do
	echo "-- $m  loadavg $(cut -d' ' -f1 /proc/loadavg)" >> $LOG
	timeout 90 $PY $G/readspan.py $m >> $LOG 2>&1
	sleep 2
done
echo "end $(date -Is) loadavg $(cut -d' ' -f1-3 /proc/loadavg)" >> $LOG
echo "ALLDONE" >> $LOG
