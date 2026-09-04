#!/bin/bash
# Research prototype runner, second pass (2026-09-02 evening).  Same host, same
# 32 bars at 120 BPM.  Re-runs the baseline and the on-loop server so every
# figure in this pass shares one machine state, then adds the shapes the first
# pass did not measure: a threaded in-process server, and a single adapter link
# (on-loop and threaded) to a separate service that does the fan-out.
set -u
S=/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad/topology
PY=$S/venv/bin/python
SEQ="/mnt/dev/Apps/2026-02 Sequencer"
BENCH="$SEQ/benchmarks/clock_jitter.py"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$SEQ"
R=$S/results2; mkdir -p $R
BARS=${BARS:-32}

cleanup () { pkill -f "$S/load_service.py" 2>/dev/null; pkill -f "$S/load_clients.py" 2>/dev/null; sleep 0.5; }
trap cleanup EXIT

echo "load average at start: $(cut -d' ' -f1-3 /proc/loadavg)"

echo "== A2. baseline, nothing else running"
$PY "$BENCH" --bars $BARS --device NO-SUCH-DEVICE-XYZ 2>/dev/null > $R/A2_baseline.txt
tail -12 $R/A2_baseline.txt

echo "== D2. in-process server ON the sequencer loop, 4 clients, 20 Hz (repeat of D)"
$PY $S/inproc_bench.py $BARS 20 > $R/D2_inproc.txt 2>&1 &
BP=$!
sleep 2
$PY $S/load_clients.py ws://127.0.0.1:8793 4 > $R/D2_clients.log 2>&1 &
wait $BP
cat $R/D2_inproc.txt; tail -1 $R/D2_clients.log
cleanup

echo "== F. in-process server on a daemon THREAD (start_threaded shape), 4 clients, 20 Hz"
$PY $S/inproc_threaded_bench.py $BARS 20 > $R/F_threaded.txt 2>&1 &
BP=$!
sleep 2
$PY $S/load_clients.py ws://127.0.0.1:8794 4 > $R/F_clients.log 2>&1 &
wait $BP
cat $R/F_threaded.txt; tail -1 $R/F_clients.log
cleanup

echo "== G. threaded in-process server, everything pinned to one core (taskset -c 2)"
taskset -c 2 $PY $S/inproc_threaded_bench.py $BARS 20 > $R/G_threaded_pinned.txt 2>&1 &
BP=$!
sleep 2
taskset -c 2 $PY $S/load_clients.py ws://127.0.0.1:8794 4 > $R/G_clients.log 2>&1 &
wait $BP
cat $R/G_threaded_pinned.txt; tail -1 $R/G_clients.log
cleanup

echo "== H. one adapter link on the sequencer LOOP to a separate service that fans out to 4 clients"
$PY $S/load_service.py 8791 8792 128 20 > $R/H_service.log 2>&1 &
sleep 1
$PY $S/load_clients.py ws://127.0.0.1:8791 4 > $R/H_clients.log 2>&1 &
sleep 1
$PY $S/link_bench.py $BARS 20 loop ws://127.0.0.1:8791 > $R/H_link_loop.txt 2>&1
cat $R/H_link_loop.txt; tail -1 $R/H_service.log; tail -1 $R/H_clients.log
cleanup

echo "== I. one adapter link on a daemon THREAD to a separate service that fans out to 4 clients"
$PY $S/load_service.py 8791 8792 128 20 > $R/I_service.log 2>&1 &
sleep 1
$PY $S/load_clients.py ws://127.0.0.1:8791 4 > $R/I_clients.log 2>&1 &
sleep 1
$PY $S/link_bench.py $BARS 20 thread ws://127.0.0.1:8791 > $R/I_link_thread.txt 2>&1
cat $R/I_link_thread.txt; tail -1 $R/I_service.log; tail -1 $R/I_clients.log
cleanup

echo "load average at end: $(cut -d' ' -f1-3 /proc/loadavg)"
echo done
