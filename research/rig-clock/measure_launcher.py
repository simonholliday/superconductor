"""Run the rig's composition with each pulse's rebuild and first send timed.

Measurement only (Subroutine #2045, brought forward on 2026-09-13 for #2034,
#2035 and #2036). Its numbers describe this rig and never set a product rule.

Subsequence's Sequencer is patched at class level before the composition runs,
so nothing in either repository changes on disk. What the clock loop records
goes into lists in memory; the file is written after play() has returned, never
from the loop.

Environment:
	MEASURE_BPM       tempo the composition opens at
	MEASURE_PORT      MIDI output it opens, a pattern as the composition uses
	MEASURE_SECONDS   how long to play before a polite SIGTERM
	MEASURE_OUT       JSON output path, on local disk
	MEASURE_SEQ       the sequencer commit, read in the command that started this
"""

import json
import os
import pathlib
import platform
import runpy
import signal
import sys
import threading
import time

import subsequence.composition
import subsequence.sequencer

COMPOSITION = os.environ.get("MEASURE_COMPOSITION", "/mnt/dev/Apps/Superconductor/compositions/drm1_grid.py")

BPM = float(os.environ["MEASURE_BPM"])
PORT = os.environ["MEASURE_PORT"]
SECONDS = float(os.environ["MEASURE_SECONDS"])
OUT = pathlib.Path(os.environ["MEASURE_OUT"])

rebuilds: list[tuple[int, float, float, int]] = []	# pulse, entered, left, patterns due
sends: list[tuple[int, float]] = []			# pulse, first MIDI send of that pulse
tempo: list[tuple[int, float]] = []			# pulse, seconds_per_pulse whenever it changes
sequencers: list[subsequence.sequencer.Sequencer] = []

Sequencer = subsequence.sequencer.Sequencer

_init = Sequencer.__init__
_reschedule = Sequencer._maybe_reschedule_patterns
_dispatch = Sequencer._dispatch_with_compensation


def recording_init (self, *args, **kwargs):  # type: ignore[no-untyped-def]
	_init(self, *args, **kwargs)
	sequencers.append(self)


async def timed_reschedule (self, pulse):  # type: ignore[no-untyped-def]
	queue = self.reschedule_queue
	due = 0

	if queue and queue[0][0] <= pulse:
		due = sum(1 for entry in queue if entry[0] <= pulse)

	if not tempo or tempo[-1][1] != self.seconds_per_pulse:
		tempo.append((pulse, self.seconds_per_pulse))

	entered = time.perf_counter()
	await _reschedule(self, pulse)
	rebuilds.append((pulse, entered, time.perf_counter(), due))


last_sent = [-1]


def timed_dispatch (self, event):  # type: ignore[no-untyped-def]
	pulse = self.pulse_count

	if pulse != last_sent[0]:
		last_sent[0] = pulse
		sends.append((pulse, time.perf_counter()))

	return _dispatch(self, event)


Sequencer.__init__ = recording_init
Sequencer._maybe_reschedule_patterns = timed_reschedule
Sequencer._dispatch_with_compensation = timed_dispatch

_composition_init = subsequence.composition.Composition.__init__


def overriding_init (self, *args, **kwargs):  # type: ignore[no-untyped-def]
	kwargs["bpm"] = BPM
	kwargs["output_device"] = PORT
	_composition_init(self, *args, **kwargs)


subsequence.composition.Composition.__init__ = overriding_init


def read (path: str) -> str:
	try:
		with open(path) as source:
			return source.read().strip()

	except OSError:
		return "unreadable"


def stop_later () -> None:
	time.sleep(SECONDS)
	os.kill(os.getpid(), signal.SIGTERM)


threading.Thread(target=stop_later, daemon=True).start()

started_wall = time.time()
sys.argv = [COMPOSITION]

try:
	runpy.run_path(COMPOSITION, run_name="__main__")

finally:
	seq = sequencers[-1] if sequencers else None

	result = {
		"meta": {
			"bpm": BPM,
			"port": PORT,
			"seconds": SECONDS,
			"started_wall": started_wall,
			"sequencer_commit": os.environ.get("MEASURE_SEQ"),
			"python": platform.python_version(),
			"host": platform.node(),
			"governor": read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"),
			"epp": read("/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference"),
			"start_time": seq.start_time if seq else None,
			"seconds_per_pulse": seq.seconds_per_pulse if seq else None,
			"pulses_per_beat": seq.pulses_per_beat if seq else None,
			"sequencers_made": len(sequencers),
			"pid": os.getpid(),
		},
		"tempo": tempo,
		"rebuilds": rebuilds,
		"sends": sends,
	}

	with open(OUT, "x") as target:
		json.dump(result, target)

	print(f"wrote {OUT}: {len(rebuilds)} pulses, {len(sends)} pulses with sends", file=sys.stderr)
