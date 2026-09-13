"""What a pattern's length adds to a build (#2526, design #2548).

Runs off the rig and off the clock, against Subsequence's own PatternBuilder and
Superconductor's own grids, and times the three things the length put on the path
that makes MIDI:

- `_play` stopping at the pattern's `grid`, against `_play` as it was;
- a grid's `now` at its build: no length, a length at its window, a shortened
  pattern, and the short cycle a re-sync makes;
- handing an event to another thread's loop, which is what the link does with the
  `cycle` event a shortened or drifted pattern sends each build.

    PYTHONDONTWRITEBYTECODE=1 python length_cost.py

A build's cost does not depend on the tempo, so this measures no tempo; the clock's
own lateness at several tempos is `stock_clock.py`'s question (#2532).  Numbers from
one machine are not a budget (#2049).
"""

import asyncio
import random
import statistics
import threading
import time
import types

import subsequence.constants.durations
import subsequence.constants.instruments.vermona_drm1_drums as drm1
import subsequence.pattern
import subsequence.pattern_builder

import superconductor.subsequence_adapter as adapter

ROWS = ["kick", "drum_1", "drum_2", "multi", "snare", "clap",
        "hihat_1_closed", "hihat_1_open", "hihat_2_closed", "hihat_2_open"]
STEP = subsequence.constants.durations.SIXTEENTH

OPENING = {"kick": [0, 6, 8, 14], "snare": [4, 12],
           "hihat_1_closed": [0, 2, 4, 6, 8, 10, 12, 14], "hihat_1_open": [7, 15], "clap": [12]}
DENSE = {row: list(range(0, 16, 2)) for row in ROWS}


def shaped (grid):
	return {row: {str(step): {"velocity": 100} for step in steps} for row, steps in grid.items()}


def play_as_it_was (p, grid):
	for row in ROWS:
		steps = grid.get(row)

		if not steps:
			continue

		for step, shape in steps.items():
			p.note(pitch=row, beat=int(step) * STEP, velocity=shape.get("velocity", 100), duration=0.1)


def play_as_it_is (p, grid):
	ends = getattr(p, "grid", None)

	for row in ROWS:
		steps = grid.get(row)

		if not steps:
			continue

		for step, shape in steps.items():
			at = int(step)

			if ends is not None and at >= ends:
				continue

			p.note(pitch=row, beat=at * STEP, velocity=shape.get("velocity", 100), duration=0.1)


def builder (cycle=0):
	pattern = subsequence.pattern.Pattern(channel=10, length=16 * STEP)

	return subsequence.pattern_builder.PatternBuilder(
		pattern=pattern, cycle=cycle, rng=random.Random(1), drum_note_map=drm1.VERMONA_DRM1_DRUM_MAP)


def stats (samples):
	samples.sort()

	return statistics.median(samples) / 1000, samples[int(len(samples) * 0.99)] / 1000


def timed_play (play, grid, rounds=4000):
	samples = []

	for _ in range(rounds):
		p = builder()
		start = time.perf_counter_ns()
		play(p, grid)
		samples.append(time.perf_counter_ns() - start)

	return stats(samples)


class Quiet:
	"""A link that counts what it is told and sends nothing."""

	def __init__ (self):
		self.events = 0

	def happened (self, name, **fields):
		self.events += 1

	def report (self, path, value):
		pass

	def kept_changed (self):
		pass


def resize (p, steps):
	# `set_length(steps=)` is #2546 and not in this Subsequence; the length in beats is
	# the same assignment, which is what is being timed.
	p.set_length(steps * STEP)


def grid_with (length, seed):
	composition = types.SimpleNamespace(data={"grid": {row: list(steps) for row, steps in seed.items()}})
	arguments = {"min_steps": 1, "resize": resize} if length else {}
	grid = adapter.StepGrid(composition, rows=ROWS, steps=16, beats=4, data_key="grid", name="grid",
	                        pattern="drums", **arguments)
	link = Quiet()
	grid.attach(link)

	return grid, link


def timed_now (seed, setup, rounds=4000):
	samples = []
	link = None

	for index in range(rounds):
		grid, link, cycle = setup(seed)
		p = builder(cycle)
		start = time.perf_counter_ns()
		grid.now(p)
		samples.append(time.perf_counter_ns() - start)

	return (*stats(samples), link.events)


def no_length (seed):
	grid, link = grid_with(False, seed)
	return grid, link, 1


def at_window (seed):
	grid, link = grid_with(True, seed)
	return grid, link, 1


def shortened (seed):
	grid, link = grid_with(True, seed)
	grid.apply(["end"], 12)
	return grid, link, 1


def resyncing (seed):
	grid, link = grid_with(True, seed)
	grid.now(builder(0))
	grid.apply(["end"], 12)
	grid.now(builder(1))
	grid.apply(["end"], 16)
	grid.apply(["resync"], True)
	return grid, link, 2


def timed_event (rounds=4000):
	loop = asyncio.new_event_loop()
	thread = threading.Thread(target=loop.run_forever, daemon=True)
	thread.start()

	async def nothing ():
		return None

	samples = []

	for _ in range(rounds):
		start = time.perf_counter_ns()
		asyncio.run_coroutine_threadsafe(nothing(), loop)
		samples.append(time.perf_counter_ns() - start)

	# Let every one of them run before the loop stops, so none is left half-made.
	time.sleep(0.5)
	loop.call_soon_threadsafe(loop.stop)
	thread.join(timeout=2)
	loop.close()

	return stats(samples)


def main ():
	for name, grid in (("opening, 17 hits", OPENING), ("dense, 80 hits", DENSE)):
		held = shaped(grid)
		print(name)

		for label, play in (("_play as it was", play_as_it_was), ("_play stopping at grid", play_as_it_is)):
			median, worst = timed_play(play, held)
			print(f"  {label:<40} median {median:7.3f} us   p99 {worst:7.3f} us")

		for label, setup in (("now, no length", no_length), ("now, length at its window", at_window),
		                     ("now, shortened to 12", shortened), ("now, a re-sync's short cycle", resyncing)):
			median, worst, events = timed_now(grid, setup)
			print(f"  {label:<40} median {median:7.3f} us   p99 {worst:7.3f} us   events {events}")

	median, worst = timed_event()
	print(f"an event handed to another loop            median {median:7.3f} us   p99 {worst:7.3f} us")


if __name__ == "__main__":
	main()
