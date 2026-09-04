"""PROTOTYPE (research only, 2026-09-03, not house style, not for the package).

Closes the orphan named in #1915 / #1914 / #2018: the wall-clock effect of a
real grid-bearing pattern's rebuild on benchmarks/clock_jitter.py's figure.

Method: benchmarks/clock_jitter.py's own method, as #1926's harness drives it —
the real subsequence.sequencer.Sequencer with a _jitter_log, 16 bars at 120 BPM,
spin-wait on, output device name matching nothing so no MIDI port is opened.
The difference from every earlier run: a REAL grid pattern is scheduled
repeating on the clock loop, built by a real Composition's decorator, whose
builder reads a StepGrid-shaped sparse cell map out of composition.data and
calls p.sequence() once per row.

Per run it reports the clock_jitter.py statistics, plus two things that
benchmark cannot see: the wall-clock cost of each rebuild measured ON the loop
(pattern.on_reschedule() and the sequencer's schedule_pattern() that follows
it), and the jitter sample of the pulse that absorbed each rebuild.

Usage:
	grid_jitter_bench.py --scenario NAME [--steps N] [--voices V] [--fill F]
	                     [--lookahead L] [--bars B] [--bpm BPM]
"""

import argparse
import asyncio
import json
import logging
import statistics
import sys
import time
import typing

logging.basicConfig(level=logging.ERROR)

sys.path.insert(0, "/mnt/dev/Apps/2026-02 Sequencer")

import subsequence
import subsequence.constants.durations as dur
import subsequence.pattern
import subsequence.sequencer

PPQN          = 24
BEATS_PER_BAR = 4
NO_DEVICE     = "NO-SUCH-DEVICE-XYZ-SUPERINTENDENT"


def make_cells (steps: int, voices: int, fill: float) -> dict:

	"""A StepGrid-shaped sparse cell map: row name -> {step index: {"v": velocity}}.

	fill 0.5 sets every other step of every row, fill 1.0 sets every step.
	Cells carry the v1 field set of #1914 (presence plus velocity).
	"""

	stride = int(round(1.0 / fill))
	out = {}
	for i in range(voices):
		row = {}
		for s in range(steps):
			if (s + i) % stride == 0:
				row[s] = {"v": 90 + (s % 30)}
		out[f"v{i}"] = row
	return out


def build_composition (steps: int, voices: int, fill: float, lookahead: float, bpm: float,
                       length_beats: typing.Optional[float] = None, count: int = 1):

	"""Real Composition, real decorator pattern, grid read from composition.data.

	length_beats overrides the natural sixteenth-note length (steps/4 beats) so a
	large grid can be forced to rebuild at a small pattern's cadence.
	"""

	comp = subsequence.Composition(output_device = NO_DEVICE, bpm = bpm)
	drum_map = {f"v{i}": 36 + i for i in range(voices)}
	cells = make_cells(steps, voices, fill)

	for k in range(count):
		comp.data[f"grid{k}"] = {"steps": steps, "cells": cells, "length": length_beats}

		def make (key):
			def grid (p):
				g = p.data[key]
				n = int(g["steps"])
				p.set_length(g["length"] if g["length"] else n * dur.SIXTEENTH)
				for voice, row in g["cells"].items():
					if not row:
						continue
					idx  = sorted(row)
					vels = [row[i].get("v", 100) for i in idx]
					p.sequence(idx, voice, velocities = vels, grid = n)
			grid.__name__ = key
			return grid

		comp.pattern(channel = 10 + k, steps = steps, step_duration = dur.SIXTEENTH,
		             drum_note_map = drum_map, reschedule_lookahead = lookahead)(make(f"grid{k}"))

	return comp


async def run (args) -> dict:

	jitter: typing.List[float] = []
	total_seconds = (60.0 / args.bpm) * BEATS_PER_BAR * args.bars
	pulses        = args.bars * BEATS_PER_BAR * PPQN

	rebuild_us:  typing.List[float] = []   # pattern.on_reschedule() alone
	queue_us:    typing.List[float] = []   # sequencer.schedule_pattern() alone
	block_us:    typing.List[float] = []   # reschedule_pulse listener -> end of schedule_pattern
	rebuild_idx: typing.List[int]   = []   # index into the jitter log of the absorbing pulse
	notes_seen:  typing.List[int]   = []
	freq_mhz:    typing.List[float] = []   # CPU frequency of the running core at each rebuild

	def current_mhz () -> float:
		"""Frequency of the core this process is on, read after the timed block."""
		try:
			cpu = int(open("/proc/self/stat").read().rsplit(") ", 1)[1].split()[36])
			return int(open(f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_cur_freq").read()) / 1000.0
		except Exception:
			return 0.0

	if args.scenario == "baseline":
		seq = subsequence.sequencer.Sequencer(
			output_device_name = NO_DEVICE, initial_bpm = args.bpm,
			spin_wait = True, _jitter_log = jitter)
		pattern = None
	else:
		comp = build_composition(args.steps, args.voices, args.fill, args.lookahead, args.bpm, args.length_beats, args.patterns)
		seq  = comp._sequencer
		seq._jitter_log = jitter
		patterns_built = [comp._build_pattern_from_pending(pp) for pp in comp._pending_patterns]
		pattern = patterns_built[0]

		t_block = [0.0]

		if args.timing:
			orig_on_reschedule = pattern.on_reschedule
			orig_schedule      = seq.schedule_pattern

			def timed_on_reschedule () -> None:
				t0 = time.perf_counter()
				orig_on_reschedule()
				rebuild_us.append((time.perf_counter() - t0) * 1e6)

			async def timed_schedule (pat, start_pulse):
				t0 = time.perf_counter()
				r  = await orig_schedule(pat, start_pulse)
				t1 = time.perf_counter()
				queue_us.append((t1 - t0) * 1e6)
				if t_block[0]:
					block_us.append((t1 - t_block[0]) * 1e6)
				if args.freq:
					freq_mhz.append(current_mhz())
				return r

			pattern.on_reschedule = timed_on_reschedule   # type: ignore[method-assign]
			seq.schedule_pattern  = timed_schedule        # type: ignore[method-assign]

		def on_reschedule_pulse (pulse, patterns) -> None:
			t_block[0] = time.perf_counter()
			rebuild_idx.append(len(jitter))

		seq.on_event("reschedule_pulse", on_reschedule_pulse)

	await seq.start()

	if pattern is not None:
		for pat in patterns_built:
			await seq.schedule_pattern_repeating(pat, 0)

	try:
		await asyncio.wait_for(asyncio.shield(seq.task), timeout = total_seconds + 2.0)
	except asyncio.TimeoutError:
		pass

	seq.running = False
	if seq.task and not seq.task.done():
		try:
			await asyncio.wait_for(seq.task, timeout = 2.0)
		except (asyncio.TimeoutError, asyncio.CancelledError):
			seq.task.cancel()

	if seq.midi_out:
		seq.midi_out.close()
		seq.midi_out = None

	if pattern is not None:
		notes_seen.append(sum(len(s.notes) for s in pattern.steps.values()))
		rebuild_count = len(rebuild_idx)
	else:
		rebuild_count = 0

	raw = jitter[:pulses]
	ms  = sorted(x * 1000.0 for x in raw)

	def q (fraction: float) -> float:
		return ms[min(int(len(ms) * fraction), len(ms) - 1)]

	# Jitter of the pulses that absorbed a rebuild, and of the pulse after
	# (which is the cycle's own first pulse when the lookahead is one pulse).
	at   = [raw[i] * 1000.0 for i in rebuild_idx if i < len(raw)]
	nxt  = [raw[i + 1] * 1000.0 for i in rebuild_idx if i + 1 < len(raw)]
	win  = [[round(raw[i + k] * 1000.0, 3) for k in range(0, 4) if i + k < len(raw)] for i in rebuild_idx]
	# The cycle the rebuild built starts `lookahead` pulses later; with one-pulse
	# lookahead that is the very next pulse, with one beat it is 24 pulses on.
	la_pulses = int(round((args.lookahead or 0) * PPQN)) if args.scenario != "baseline" else 0
	cyc  = [raw[i + la_pulses] * 1000.0 for i in rebuild_idx if i + la_pulses < len(raw)]

	def stat (values: typing.List[float]) -> dict:
		if not values:
			return {}
		s = sorted(values)
		return {"n": len(s), "median": round(statistics.median(s), 4),
		        "p95": round(s[min(int(len(s) * 0.95), len(s) - 1)], 4),
		        "max": round(s[-1], 4)}

	return {
		"scenario":      args.scenario,
		"steps":         args.steps if args.scenario != "baseline" else None,
		"voices":        args.voices if args.scenario != "baseline" else None,
		"fill":          args.fill if args.scenario != "baseline" else None,
		"lookahead":     args.lookahead if args.scenario != "baseline" else None,
		"length_beats":  args.length_beats,
		"bpm":           args.bpm,
		"bars":          args.bars,
		"pulses_expected": pulses,
		"pulses_logged": len(raw),
		"notes_per_cycle": notes_seen[-1] if notes_seen else 0,
		"patterns":      args.patterns,
		"rebuilds":      rebuild_count,
		"timing":        bool(args.timing),
		"median_ms":     round(statistics.median(ms), 4),
		"mean_ms":       round(statistics.mean(ms), 4),
		"p95_ms":        round(q(0.95), 4),
		"p99_ms":        round(q(0.99), 4),
		"max_ms":        round(ms[-1], 4),
		"over_1ms":      sum(1 for x in ms if x > 1.0),
		"rebuild_us":    stat(rebuild_us),
		"queue_us":      stat(queue_us),
		"block_us":      stat(block_us),
		"raw_rebuild_us": [round(x, 1) for x in rebuild_us],
		"raw_queue_us":   [round(x, 1) for x in queue_us],
		"raw_block_us":   [round(x, 1) for x in block_us],
		"raw_freq_mhz":   [round(x) for x in freq_mhz],
		"raw_jitter_window_ms": win if pattern is not None else [],
		"raw_jitter_at_rebuild_ms": [round(x, 4) for x in at],
		"raw_jitter_at_cycle_start_ms": [round(x, 3) for x in cyc],
		"jitter_at_cycle_start_ms": stat(cyc),
		"jitter_at_rebuild_ms": stat(at),
		"jitter_after_rebuild_ms": stat(nxt),
		"load_at_start": args.load_at_start,
	}


def _fraction (text: str) -> float:

	"""Accept 1, 0.25 or 1/24."""

	if "/" in text:
		num, den = text.split("/", 1)
		return float(num) / float(den)
	return float(text)


def main () -> None:

	ap = argparse.ArgumentParser()
	ap.add_argument("--scenario",  default = "grid")
	ap.add_argument("--steps",     type = int,   default = 16)
	ap.add_argument("--voices",    type = int,   default = 8)
	ap.add_argument("--fill",      type = float, default = 0.5)
	ap.add_argument("--lookahead", type = _fraction, default = 1.0)
	ap.add_argument("--bars",      type = int,   default = 16)
	ap.add_argument("--bpm",       type = float, default = 120.0)
	ap.add_argument("--length-beats", dest = "length_beats", type = _fraction, default = None)
	ap.add_argument("--patterns",  type = int, default = 1, help = "how many identical grid patterns share the loop")
	ap.add_argument("--freq",      action = "store_true", help = "sample the running core's clock frequency after each rebuild")
	ap.add_argument("--timing",    action = "store_true", help = "wrap on_reschedule/schedule_pattern to time them on the loop")
	ap.add_argument("--label",     default = "")
	a = ap.parse_args()
	a.load_at_start = round(__import__("os").getloadavg()[0], 2)
	r = asyncio.run(run(a))
	r["label"] = a.label
	print(json.dumps(r), flush = True)


if __name__ == "__main__":
	main()
