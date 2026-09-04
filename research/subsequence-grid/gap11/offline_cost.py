"""PROTOTYPE (research only, 2026-09-03, not house style).

Reproduces #1915's run G (500 tight-loop on_reschedule() calls) and extends it
in the two directions the on-loop measurement needs:
  - hit_steps() per row (what #1915 used) versus sequence() with per-step
    velocities (the v1 cell schema of #1914),
  - on_reschedule() alone versus on_reschedule() plus the sequencer's
    schedule_pattern(), which is the other half of what the loop actually does
    per cycle and which #1915 never timed,
  - a tight loop versus one call every 32 ms (the real cycle cadence), to see
    how much of the tight-loop figure is cache warmth.

No MIDI port is opened: mido is patched exactly as tests/conftest.py does.
"""

import asyncio
import logging
import statistics
import sys
import time

import mido

logging.basicConfig(level=logging.ERROR)
sys.path.insert(0, "/mnt/dev/Apps/2026-02 Sequencer")


class SpyOut:
	def send (self, m): pass
	def close (self): pass
	def panic (self): pass
	def reset (self): pass


_spy = SpyOut()
mido.get_output_names = lambda: ["Dummy MIDI"]
mido.open_output = lambda name: _spy
mido.get_input_names = lambda: ["Dummy MIDI"]
mido.open_input = lambda name, callback=None: None

import subsequence
import subsequence.constants.durations as dur


def make (steps, voices, fill, verb):
	comp = subsequence.Composition(output_device="Dummy MIDI", bpm=120)
	drum_map = {f"v{i}": 36 + i for i in range(voices)}
	stride = int(round(1.0 / fill))
	cells = {f"v{i}": {s: {"v": 90 + (s % 30)} for s in range(steps) if (s + i) % stride == 0}
	         for i in range(voices)}
	comp.data["g"] = {"steps": steps, "cells": cells}

	@comp.pattern(channel=10, steps=steps, step_duration=dur.SIXTEENTH, drum_note_map=drum_map)
	def grid (p):
		g = p.data["g"]
		n = int(g["steps"])
		p.set_length(n * dur.SIXTEENTH)
		for voice, row in g["cells"].items():
			if not row:
				continue
			idx = sorted(row)
			if verb == "hit_steps":
				p.hit_steps(voice, idx, grid=n, velocity=100)
			else:
				p.sequence(idx, voice, velocities=[row[i]["v"] for i in idx], grid=n)

	pattern = comp._build_pattern_from_pending(comp._pending_patterns[0])
	return comp, pattern


def stats (xs):
	xs = sorted(xs)
	return (statistics.median(xs), xs[int(len(xs) * 0.95)], xs[-1])


async def measure (steps, voices, fill, verb, spaced, iterations=500):
	comp, pattern = make(steps, voices, fill, verb)
	seq = comp._sequencer
	await seq.start()
	seq.running = False
	if seq.task:
		seq.task.cancel()
	rebuild, queue = [], []
	for _ in range(iterations):
		t0 = time.perf_counter()
		pattern.on_reschedule()
		t1 = time.perf_counter()
		await seq.schedule_pattern(pattern, seq.pulse_count)
		t2 = time.perf_counter()
		rebuild.append((t1 - t0) * 1e6)
		queue.append((t2 - t1) * 1e6)
		seq.event_queue.clear()
		if spaced:
			await asyncio.sleep(0.032)
	n = sum(len(s.notes) for s in pattern.steps.values())
	return n, stats(rebuild), stats(queue)


async def main ():
	print("shape            verb        cadence   notes  rebuild us (med/p95/max)   schedule_pattern us (med/p95/max)")
	for steps, voices, fill, tag in [(16, 8, 0.5, "16x8 half"), (16, 8, 1.0, "16x8 full"), (64, 16, 0.5, "64x16 half")]:
		for verb in ("hit_steps", "sequence"):
			for spaced, iters in ((False, 500), (True, 60)):
				n, r, q = await measure(steps, voices, fill, verb, spaced, iters)
				cad = "32 ms" if spaced else "tight"
				print(f"{tag:15s}  {verb:10s}  {cad:7s}  {n:5d}   {r[0]:8.1f} {r[1]:8.1f} {r[2]:8.1f}    {q[0]:8.1f} {q[1]:8.1f} {q[2]:8.1f}")


asyncio.run(main())
