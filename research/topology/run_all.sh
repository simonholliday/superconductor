#!/bin/bash
# Research prototype runner.  Four conditions, 32 bars at 120 BPM each (64 s).
set -u
S=/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad/topology
PY=$S/venv/bin/python
SEQ="/mnt/dev/Apps/2026-02 Sequencer"
BENCH="$SEQ/benchmarks/clock_jitter.py"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$SEQ"
R=$S/results; mkdir -p $R
BARS=${BARS:-32}

cleanup () { pkill -f "$S/load_service.py" 2>/dev/null; pkill -f "$S/load_clients.py" 2>/dev/null; sleep 0.5; }
trap cleanup EXIT

echo "== A. baseline, nothing else running"
$PY "$BENCH" --bars $BARS --device NO-SUCH-DEVICE-XYZ 2>/dev/null > $R/A_baseline.txt
tail -12 $R/A_baseline.txt

echo "== B. separate-process service + 4 clients + static fetch loop, same host, free scheduling"
$PY $S/load_service.py 8791 8792 128 20 > $R/B_service.log 2>&1 &
sleep 1
$PY $S/load_clients.py ws://127.0.0.1:8791 4 http://127.0.0.1:8792/bundle.js > $R/B_clients.log 2>&1 &
sleep 2
$PY "$BENCH" --bars $BARS --device NO-SUCH-DEVICE-XYZ 2>/dev/null > $R/B_separate.txt
tail -12 $R/B_separate.txt; tail -1 $R/B_service.log; tail -1 $R/B_clients.log
cleanup

echo "== C. same as B but service, clients and sequencer all pinned to one core (taskset -c 2)"
taskset -c 2 $PY $S/load_service.py 8791 8792 128 20 > $R/C_service.log 2>&1 &
sleep 1
taskset -c 2 $PY $S/load_clients.py ws://127.0.0.1:8791 4 http://127.0.0.1:8792/bundle.js > $R/C_clients.log 2>&1 &
sleep 2
taskset -c 2 $PY "$BENCH" --bars $BARS --device NO-SUCH-DEVICE-XYZ 2>/dev/null > $R/C_pinned.txt
tail -12 $R/C_pinned.txt; tail -1 $R/C_service.log; tail -1 $R/C_clients.log
cleanup

echo "== D. in-process WebSocket server on the sequencer's loop, 4 clients tapping, 20 Hz broadcast"
$PY $S/inproc_bench.py $BARS 20 > $R/D_inproc.txt 2>&1 &
BP=$!
sleep 2
$PY $S/load_clients.py ws://127.0.0.1:8793 4 > $R/D_clients.log 2>&1 &
wait $BP
cat $R/D_inproc.txt; tail -1 $R/D_clients.log
cleanup

echo "== E. in-process, 60 Hz broadcast, 4 clients"
$PY $S/inproc_bench.py $BARS 60 > $R/E_inproc60.txt 2>&1 &
BP=$!
sleep 2
$PY $S/load_clients.py ws://127.0.0.1:8793 4 > $R/E_clients.log 2>&1 &
wait $BP
cat $R/E_inproc60.txt; tail -1 $R/E_clients.log
cleanup
echo done
