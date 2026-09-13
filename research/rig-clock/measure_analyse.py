"""Summarise a measurement run: rebuild cost, send lateness, CPU state.

	python measure_analyse.py <run.json> [<sampler.json>] [--skip-seconds N]
"""

import argparse
import bisect
import json
import statistics


def pct (values: list[float], p: float) -> float | None:
	"""Nearest-rank percentile."""

	if not values:
		return None

	ordered = sorted(values)
	return ordered[max(0, min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1))))]


def line (label: str, values: list[float], unit: str = "ms") -> str:
	if not values:
		return f"{label:<44} n=0"

	return (f"{label:<44} n={len(values):<6} median {statistics.median(values):8.3f}  "
	        f"p90 {pct(values, 90):8.3f}  p99 {pct(values, 99):8.3f}  max {max(values):8.3f} {unit}")


def main () -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("run")
	parser.add_argument("sampler", nargs="?")
	parser.add_argument("--skip-seconds", type=float, default=10.0)
	options = parser.parse_args()

	run = json.load(open(options.run))
	meta = run["meta"]
	spp = meta["seconds_per_pulse"]
	start = meta["start_time"]
	ms = 1000.0

	print(f"bpm {meta['bpm']}  port {meta['port']}  played {meta['seconds']} s  "
	      f"pulse {spp * ms:.3f} ms  governor {meta['governor']}  epp {meta['epp']}  "
	      f"sequencer {meta['sequencer_commit']}  python {meta['python']}")

	if len(run["tempo"]) > 1:
		print(f"WARNING: tempo changed during the run: {run['tempo']}")

	skip_pulse = int(options.skip_seconds / spp)
	ideal = lambda pulse: start + pulse * spp  # noqa: E731

	rebuilds = [r for r in run["rebuilds"] if r[0] >= skip_pulse]
	early = [r for r in run["rebuilds"] if r[0] < skip_pulse]
	sends = {pulse: when for pulse, when in run["sends"]}

	print(f"steady state from pulse {skip_pulse} ({options.skip_seconds:.0f} s): "
	      f"{len(rebuilds)} pulses; start-up excluded: {len(early)} pulses")

	wake = [(entered - ideal(pulse)) * ms for pulse, entered, _, _ in rebuilds]
	print(line("pulse entered late by", wake))
	print(f"{'':<44} pulses entered more than 1 ms late: {sum(1 for w in wake if w > 1.0)}")

	due = [r for r in rebuilds if r[3] > 0]
	idle = [r for r in rebuilds if r[3] == 0]
	print(line("rebuild, pulses with patterns due", [(left - entered) * ms for _, entered, left, _ in due]))
	print(line("same call, pulses with nothing due", [(left - entered) * ms for _, entered, left, _ in idle]))

	for count in sorted({r[3] for r in due}):
		some = [(left - entered) * ms for _, entered, left, n in due if n == count]
		print(line(f"  rebuild with {count} pattern(s) due", some))

	if due:
		worst = max((left - entered) for _, entered, left, _ in due)
		print(f"{'':<44} worst rebuild is {worst / spp * 100:.1f}% of one pulse")

	overran = [pulse for pulse, entered, left, n in due if left - ideal(pulse) > spp]
	print(f"{'':<44} rebuilds finishing after the next pulse was due: {len(overran)}")

	due_pulses = {r[0] for r in due}
	on_rebuild = [(sends[p] - ideal(p)) * ms for p in sends if p >= skip_pulse and p in due_pulses]
	elsewhere = [(sends[p] - ideal(p)) * ms for p in sends if p >= skip_pulse and p not in due_pulses]
	print(line("first send late by, on a rebuild pulse", on_rebuild))
	print(line("first send late by, on any other pulse", elsewhere))

	if early:
		start_cost = [(left - entered) * ms for _, entered, left, n in early if n > 0]
		print(line("start-up rebuilds (excluded above)", start_cost))

	if options.sampler:
		sampled = json.load(open(options.sampler))["rows"]
		times = [row[0] for row in sampled]
		at_rebuild = []

		for _, entered, _, _ in due:
			index = bisect.bisect_right(times, entered) - 1

			if index >= 0 and entered - times[index] < 0.05:
				at_rebuild.append(sampled[index])

		khz = [row[2] / 1000.0 for row in at_rebuild]
		cpus = sorted({row[1] for row in sampled})
		migrations = sum(1 for a, b in zip(sampled, sampled[1:]) if a[1] != b[1])
		print(line("clock thread's CPU frequency near a rebuild", khz, "MHz"))
		print(f"{'':<44} below 1000 MHz near a rebuild: {sum(1 for k in khz if k < 1000)} of {len(khz)}")
		print(f"{'':<44} CPUs the clock thread ran on: {cpus}; changes between samples: {migrations}")


if __name__ == "__main__":
	main()
