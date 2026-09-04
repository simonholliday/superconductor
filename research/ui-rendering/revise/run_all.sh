#!/bin/bash
cd /tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad/ui-rendering/revise
PY=../.venv/bin/python
GPU="--enable-gpu --use-angle=gl-egl --ignore-gpu-blocklist"
echo "== bench2 swiftshader $(date)"
$PY run_bench2.py sw 1,6,16 > log_bench2_sw.txt 2>&1
echo "== bench2 gpu $(date)"
$PY run_bench2.py gpu 1,6 "$GPU" > log_bench2_gpu.txt 2>&1
echo "== bench gpu 1x $(date)"
$PY run_bench.py 1 gpu "$GPU" > log_gpu.txt 2>&1
echo "== bench gpu 6x $(date)"
$PY run_bench.py 6 gpu6x "$GPU" > log_gpu6x.txt 2>&1
echo "== speedometer 16x $(date)"
$PY speedometer.py 16 > speedometer16.txt 2>&1
echo "== done $(date)"
