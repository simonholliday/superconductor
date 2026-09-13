"""Measure Subsequence's clock lateness across tempos and two levers.

Runs the Sequencer exactly as benchmarks/clock_jitter.py does (no patterns,
_jitter_log set, Midi Through), and keeps the raw per-pulse lateness.

	python clock_sweep.py <out.json> <spec> [<spec> ...]

A spec is BPM[:threshold_ms][:select|:epoll][:nospin], for example 125,
180:2, 180:1:select.  SWEEP_BARS sets the bars per spec (default 8); the 60 to
200 BPM map in #2532 was taken with SWEEP_BARS=4.
"""

import asyncio
import json
import os
import selectors
import statistics
import sys
import time

import subsequence.sequencer

BARS = int(os.environ.get("SWEEP_BARS", "8"))


def run (bpm: float, threshold_ms: float | None, selector: str, spin: bool) -> list[float]:
	jitter: list[float] = []

	async def main () -> None:
		seq = subsequence.sequencer.Sequencer(
			output_device_name="*Midi Through*", initial_bpm=bpm, spin_wait=spin, _jitter_log=jitter)

		if threshold_ms is not None:
			seq._spin_threshold = threshold_ms / 1000.0

		await seq.start()

		try:
			await asyncio.wait_for(asyncio.shield(seq.task), timeout=60.0 / bpm * 4 * BARS + 0.5)

		except asyncio.TimeoutError:
			pass

		seq.running = False

		try:
			await asyncio.wait_for(seq.task, timeout=2.0)

		except (asyncio.TimeoutError, asyncio.CancelledError):
			seq.task.cancel()

		if seq.midi_out:
			seq.midi_out.close()
			seq.midi_out = None

	if selector == "select":
		loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
		asyncio.set_event_loop(loop)
		loop.run_until_complete(main())
		loop.close()

	else:
		asyncio.run(main())

	return jitter[: BARS * 96]


def main () -> None:
	out = sys.argv[1]
	results = []

	for spec in sys.argv[2:]:
		parts = spec.split(":")
		bpm = float(parts[0])
		threshold = float(parts[1]) if len(parts) > 1 and parts[1] else None
		selector = "select" if "select" in parts else "epoll"
		spin = "nospin" not in parts

		lateness = [j * 1000.0 for j in run(bpm, threshold, selector, spin)]
		ordered = sorted(lateness)
		p99 = ordered[int(len(ordered) * 0.99)]
		over = sum(1 for v in lateness if v > 1.0)

		print(f"{spec:<16} pulses {len(lateness):<5} median {statistics.median(lateness):7.3f}  "
		      f"p99 {p99:7.3f}  max {max(lateness):7.3f} ms   over 1 ms: {over}", flush=True)

		results.append({"spec": spec, "bpm": bpm, "threshold_ms": threshold, "selector": selector,
		                "spin": spin, "lateness_ms": lateness})

	with open(out, "x") as target:
		json.dump({"when": time.time(), "bars": BARS, "results": results}, target)


if __name__ == "__main__":
	main()
