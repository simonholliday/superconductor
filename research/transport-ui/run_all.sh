#!/bin/bash
# Research prototype (transport-ui): run every loopback measurement in sequence (they share port 8902) and keep the logs.
S=/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad/transport-ui
R=$S/results
PY=$S/.venv/bin/python
{ echo "run: $(date -Is) host: $(hostname) kernel: $(uname -r) python: $($PY --version 2>&1)"; lscpu | grep 'Model name'; } > $R/environment.txt
$PY $S/browser_bench.py > $R/browser_bench_chromium.txt 2>&1
PW_BROWSER=firefox $PY $S/browser_bench_ff.py > $R/browser_bench_firefox.txt 2>&1
$PY $S/verify_fetch_stall.py > $R/fetch_stall_chromium.txt 2>&1
$PY $S/encode_bench.py > $R/encode_bench_python.txt 2>&1
(cd $S/js && node encode_bench.js) > $R/encode_bench_node.txt 2>&1
echo "done $(date -Is)" > $R/DONE
