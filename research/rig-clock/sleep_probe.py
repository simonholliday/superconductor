"""Where does a late pulse's time go: the sleep, or after it?

Wraps asyncio.sleep for the sequencer's clock loop and records, per pulse, the
sleep asked for and the sleep taken. Runs 4 bars per tempo on Midi Through.

	python sleep_probe.py 125 130 140 180
"""

import asyncio
import statistics
import sys
import time

import subsequence.sequencer

real_sleep = asyncio.sleep
records: list[tuple[float, float]] = []


async def timed_sleep (delay, result=None):  # type: ignore[no-untyped-def]
	started = time.perf_counter()
	value = await real_sleep(delay, result)

	if delay > 0.001:
		records.append((delay, time.perf_counter() - started))

	return value


subsequence.sequencer.asyncio.sleep = timed_sleep  # the module's reference, so only the clock loop is timed


def run (bpm: float) -> list[float]:
	jitter: list[float] = []

	async def main () -> None:
		seq = subsequence.sequencer.Sequencer(
			output_device_name="*Midi Through*", initial_bpm=bpm, spin_wait=True, _jitter_log=jitter)
		await seq.start()

		try:
			await asyncio.wait_for(asyncio.shield(seq.task), timeout=60.0 / bpm * 16 + 0.5)

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

	asyncio.run(main())
	return jitter


for arg in sys.argv[1:]:
	records.clear()
	bpm = float(arg)
	jitter = run(bpm)
	over = [(taken - asked) * 1000.0 for asked, taken in records]
	asked_ms = [asked * 1000.0 for asked, _ in records]
	late = [j * 1000.0 for j in jitter]
	ordered = sorted(over)

	print(f"{bpm:>5.0f} BPM  sleeps {len(over):<4} asked median {statistics.median(asked_ms):7.3f} ms  "
	      f"overslept median {statistics.median(over):6.3f}  p90 {ordered[int(len(ordered) * 0.9)]:6.3f}  "
	      f"max {max(over):6.3f} ms   pulses late median {statistics.median(late):6.3f} ms", flush=True)
