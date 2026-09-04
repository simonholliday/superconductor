"""PROTOTYPE (verification only, 2026-09-03, not house style, not for the package).

Measures what benchmarks/clock_jitter.py's _jitter_log cannot see: how late a
pulse's MIDI dispatch is relative to that pulse's ideal instant, when the
rebuild for that pulse runs inline ahead of it.

_jitter_log is appended after the sleep that precedes a pulse (sequencer.py:1567),
i.e. before _advance_pulse dispatches it, so the in-pulse cost of
_maybe_reschedule_patterns (sequencer.py:1484) never appears in the figure.
Here _dispatch_with_compensation is wrapped and the wall clock at the moment of
the first send for each pulse is compared with start_time + pulse * seconds_per_pulse.

No MIDI port is opened (device name matches nothing).
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
import subsequence.sequencer

PPQN = 24
NO_DEVICE = "NO-SUCH-DEVICE-XYZ-VERIFY"


def make_cells(steps, voices, fill):
	stride = int(round(1.0 / fill))
	out = {}
	for i in range(voices):
		row = {}
		for s in range(steps):
			if (s + i) % stride == 0:
				row[s] = {"v": 90 + (s % 30)}
		out[f"v{i}"] = row
	return out


def build_composition(steps, voices, fill, lookahead, bpm):
	comp = subsequence.Composition(output_device=NO_DEVICE, bpm=bpm)
	drum_map = {f"v{i}": 36 + i for i in range(voices)}
	comp.data["grid"] = {"steps": steps, "cells": make_cells(steps, voices, fill)}

	def grid(p):
		g = p.data["grid"]
		n = int(g["steps"])
		p.set_length(n * dur.SIXTEENTH)
		for voice, row in g["cells"].items():
			if not row:
				continue
			idx = sorted(row)
			vels = [row[i].get("v", 100) for i in idx]
			p.sequence(idx, voice, velocities=vels, grid=n)

	comp.pattern(channel=10, steps=steps, step_duration=dur.SIXTEENTH,
	             drum_note_map=drum_map, reschedule_lookahead=lookahead)(grid)
	return comp


async def run(args):
	jitter: typing.List[float] = []
	total_seconds = (60.0 / args.bpm) * 4 * args.bars

	comp = build_composition(args.steps, args.voices, args.fill, args.lookahead, args.bpm)
	seq = comp._sequencer
	seq._jitter_log = jitter
	pattern = comp._build_pattern_from_pending(comp._pending_patterns[0])

	dispatch: typing.Dict[int, float] = {}      # pulse -> lateness of its first send, ms
	rebuild_pulses: typing.List[int] = []
	block_us: typing.List[float] = []
	t_block = [0.0]

	orig_dispatch = seq._dispatch_with_compensation

	def wrapped(event):
		now = time.perf_counter()
		ideal = seq.start_time + seq.pulse_count * seq.seconds_per_pulse
		dispatch.setdefault(seq.pulse_count, (now - ideal) * 1000.0)
		orig_dispatch(event)

	seq._dispatch_with_compensation = wrapped  # type: ignore[method-assign]

	orig_schedule = seq.schedule_pattern

	async def timed_schedule(pat, start_pulse):
		r = await orig_schedule(pat, start_pulse)
		if t_block[0]:
			block_us.append((time.perf_counter() - t_block[0]) * 1e6)
		return r

	seq.schedule_pattern = timed_schedule  # type: ignore[method-assign]

	def on_reschedule_pulse(pulse, patterns):
		t_block[0] = time.perf_counter()
		rebuild_pulses.append(pulse)

	seq.on_event("reschedule_pulse", on_reschedule_pulse)

	await seq.start()
	await seq.schedule_pattern_repeating(pattern, 0)

	try:
		await asyncio.wait_for(asyncio.shield(seq.task), timeout=total_seconds + 2.0)
	except asyncio.TimeoutError:
		pass

	seq.running = False
	if seq.task and not seq.task.done():
		try:
			await asyncio.wait_for(seq.task, timeout=2.0)
		except (asyncio.TimeoutError, asyncio.CancelledError):
			seq.task.cancel()

	rebuilt = set(rebuild_pulses)
	on_rebuild = [v for k, v in dispatch.items() if k in rebuilt]
	other = [v for k, v in dispatch.items() if k not in rebuilt]
	ms = sorted(x * 1000.0 for x in jitter)

	def stat(vals):
		if not vals:
			return {}
		s = sorted(vals)
		return {"n": len(s), "median": round(statistics.median(s), 3),
		        "p95": round(s[min(int(len(s) * 0.95), len(s) - 1)], 3),
		        "max": round(s[-1], 3)}

	return {
		"steps": args.steps, "voices": args.voices, "fill": args.fill,
		"lookahead": args.lookahead, "bpm": args.bpm, "bars": args.bars,
		"notes_per_cycle": sum(len(s.notes) for s in pattern.steps.values()),
		"jitter_log_median_ms": round(statistics.median(ms), 4),
		"jitter_log_p99_ms": round(ms[min(int(len(ms) * 0.99), len(ms) - 1)], 4),
		"jitter_log_max_ms": round(ms[-1], 4),
		"jitter_log_over_1ms": sum(1 for x in ms if x > 1.0),
		"block_ms": {k: round(v / 1000.0, 3) for k, v in stat(block_us).items()} if block_us else {},
		"dispatch_lateness_on_rebuild_pulses_ms": stat(on_rebuild),
		"dispatch_lateness_other_pulses_ms": stat(other),
		"raw_on_rebuild_ms": [round(x, 3) for x in on_rebuild],
		"load_at_start": round(__import__("os").getloadavg()[0], 2),
	}


def _fraction(text):
	if "/" in text:
		n, d = text.split("/", 1)
		return float(n) / float(d)
	return float(text)


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("--steps", type=int, default=16)
	ap.add_argument("--voices", type=int, default=8)
	ap.add_argument("--fill", type=float, default=0.5)
	ap.add_argument("--lookahead", type=_fraction, default=1.0)
	ap.add_argument("--bars", type=int, default=16)
	ap.add_argument("--bpm", type=float, default=120.0)
	a = ap.parse_args()
	print(json.dumps(asyncio.run(run(a))), flush=True)


if __name__ == "__main__":
	main()
