"""What placing a drum grid onto a pattern costs, for each way of placing it (#2525).

Runs Subsequence's own PatternBuilder with the DRM1 drum map, off the rig and
off the clock, and times the play function alone: the part of a build a step
carrying its velocity changed.  Four ways, on the opening pattern (17 hits) and
on a dense grid (80 hits):

- `hit_steps` once a row at one velocity, as `_play` was;
- steps grouped by velocity, one `hit_steps` a group, at one velocity and varied;
- one `note` a step, which is what `_play` does now.

    PYTHONDONTWRITEBYTECODE=1 python play_cost.py

Numbers from one machine are not a budget (#2049).
"""

import random
import statistics
import time

import subsequence.constants.durations
import subsequence.constants.instruments.vermona_drm1_drums as drm1
import subsequence.pattern
import subsequence.pattern_builder

ROWS = ["kick", "drum_1", "drum_2", "multi", "snare", "clap",
        "hihat_1_closed", "hihat_1_open", "hihat_2_closed", "hihat_2_open"]
STEP = subsequence.constants.durations.SIXTEENTH

OPENING = {"kick": [0, 6, 8, 14], "snare": [4, 12],
           "hihat_1_closed": [0, 2, 4, 6, 8, 10, 12, 14], "hihat_1_open": [7, 15], "clap": [12]}
DENSE = {row: list(range(0, 16, 2)) for row in ROWS}


def by_row (p, grid):
	for row in ROWS:
		steps = grid.get(row)

		if steps:
			p.hit_steps(row, list(steps), velocity=100)


def by_velocity (p, grid):
	for row in ROWS:
		steps = grid.get(row)

		if not steps:
			continue

		grouped = {}

		for step, shape in steps.items():
			grouped.setdefault(shape.get("velocity", 100), []).append(int(step))

		for velocity, placed in grouped.items():
			p.hit_steps(row, placed, velocity=velocity)


def by_step (p, grid):
	for row in ROWS:
		steps = grid.get(row)

		if not steps:
			continue

		for step, shape in steps.items():
			p.note(pitch=row, beat=int(step) * STEP, velocity=shape.get("velocity", 100), duration=0.1)


def shaped (grid, varied):
	return {row: {str(step): {"velocity": (30 + (step * 37) % 97) if varied else 100} for step in steps}
	        for row, steps in grid.items()}


def builder ():
	pattern = subsequence.pattern.Pattern(channel=10, length=16 * STEP)

	return subsequence.pattern_builder.PatternBuilder(
		pattern=pattern, cycle=0, rng=random.Random(1), drum_note_map=drm1.VERMONA_DRM1_DRUM_MAP)


def timed (play, grid, rounds=4000):
	samples = []

	for _ in range(rounds):
		p = builder()
		start = time.perf_counter_ns()
		play(p, grid)
		samples.append(time.perf_counter_ns() - start)

	samples.sort()

	return statistics.median(samples) / 1000, samples[int(len(samples) * 0.99)] / 1000


def main ():
	for name, grid in (("opening, 17 hits", OPENING), ("dense, 80 hits", DENSE)):
		print(name)

		for label, play, held in (
			("hit_steps a row, one velocity", by_row, grid),
			("hit_steps a velocity, one velocity", by_velocity, shaped(grid, False)),
			("hit_steps a velocity, varied", by_velocity, shaped(grid, True)),
			("note a step, varied", by_step, shaped(grid, True)),
		):
			median, worst = timed(play, held)
			print(f"  {label:<36} median {median:7.3f} us   p99 {worst:7.3f} us")

		# The one built has to place what hit_steps placed.
		a, b = builder(), builder()
		by_velocity(a, shaped(grid, True))
		by_step(b, shaped(grid, True))
		key = lambda note: (note.pitch, round(note.position, 6), note.velocity)
		print("  a note a step places the same notes:", sorted(map(key, a.placed())) == sorted(map(key, b.placed())))


if __name__ == "__main__":
	main()
