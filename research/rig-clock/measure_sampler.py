"""Sample which CPU a process's main thread is on, and that CPU's frequency.

A separate process, so it never takes the measured composition's GIL. Timestamps
are perf_counter, which is CLOCK_MONOTONIC on Linux and so shared with the
composition's own records. Reads /proc and /sys only; writes to local disk after
the process it watches has gone.

	python measure_sampler.py <pid> <out.json> [interval_seconds]
"""

import json
import sys
import time

pid = int(sys.argv[1])
out = sys.argv[2]
interval = float(sys.argv[3]) if len(sys.argv) > 3 else 0.01

rows: list[tuple[float, int, int, int]] = []	# when, cpu, kHz, utime+stime ticks

while True:
	try:
		with open(f"/proc/{pid}/stat") as source:
			fields = source.read().rsplit(")", 1)[1].split()

	except (FileNotFoundError, ProcessLookupError):
		break

	cpu = int(fields[36])
	ticks = int(fields[11]) + int(fields[12])

	try:
		with open(f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_cur_freq") as source:
			khz = int(source.read())

	except OSError:
		khz = -1

	rows.append((time.perf_counter(), cpu, khz, ticks))
	time.sleep(interval)

with open(out, "x") as target:
	json.dump({"pid": pid, "interval": interval, "rows": rows}, target)
