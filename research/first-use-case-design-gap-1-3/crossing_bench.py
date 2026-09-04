"""PROTOTYPE, not house style.

Measures what one panel write costs Subsequence's clock loop under each of the
three crossing rules the first-use-case assembly short-lists, using the real
`subsequence.sequencer.Sequencer` driven exactly as `benchmarks/clock_jitter.py`
drives it.

The transport is deliberately absent.  #1926 measured that the cost is per
wake-up of the clock loop and independent of the transport (OSC on the loop,
OSC on a thread, a WebSocket link on the loop or on a thread and a TCP link on
a thread all landed within noise of each other), so what is varied here is only
the crossing rule, with an identical arrival process in every arm:

  none         no arrivals at all (baseline)
  per_message  a thread calls loop.call_soon_threadsafe(apply, msg) per message
  coalesced    a thread queues the message and schedules one drain callback only
               when none is already pending
  hooks        a thread queues the message; a `beat` listener drains the queue

Arrival patterns:

  sustained    one message every 1/rate seconds
  burst        `burst` messages 1 ms apart, once every 1/rate seconds

Usage: crossing_bench.py <arm> <pattern> <rate_hz> [burst] [bars]
Prints one JSON object on stdout.
"""

import asyncio
import json
import logging
import os
import queue
import statistics
import sys
import threading
import time
import typing

logging.basicConfig(level=logging.ERROR)

import subsequence.sequencer


PPQN = 24
BEATS_PER_BAR = 4


def _percentile (values: typing.List[float], q: float) -> float:

	ordered = sorted(values)
	if not ordered:
		return 0.0
	idx = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
	return ordered[idx]


def main () -> None:

	arm = sys.argv[1]
	pattern = sys.argv[2]
	rate_hz = float(sys.argv[3])
	burst = int(sys.argv[4]) if len(sys.argv) > 4 else 1
	bars = int(sys.argv[5]) if len(sys.argv) > 5 else 16

	bpm = 120.0
	pulses = bars * BEATS_PER_BAR * PPQN
	total_seconds = (60.0 / bpm) * BEATS_PER_BAR * bars

	jitter_log: typing.List[float] = []
	# The "grid" the messages are applied into: one dict write per message,
	# standing in for composition.data[key] = value.
	grid: typing.Dict[int, int] = {}
	applied = 0
	wakeups = 0
	inbound: "queue.Queue[int]" = queue.Queue(maxsize=8192)
	drain_pending = False
	stop_flag = threading.Event()
	produced = 0

	async def _run () -> None:

		nonlocal applied, wakeups, drain_pending, produced

		seq = subsequence.sequencer.Sequencer(
			output_device_name = "SUPERINTENDENT_NO_SUCH_DEVICE",
			initial_bpm = bpm,
			spin_wait = True,
			_jitter_log = jitter_log,
		)
		loop = asyncio.get_running_loop()

		def apply_one (value: int) -> None:
			nonlocal applied, wakeups
			grid[value % 128] = value
			applied += 1
			wakeups += 1

		def drain () -> None:
			nonlocal applied, wakeups, drain_pending
			drain_pending = False
			wakeups += 1
			while True:
				try:
					value = inbound.get_nowait()
				except queue.Empty:
					break
				grid[value % 128] = value
				applied += 1

		def drain_at_hook (_beat: int) -> None:
			drain()

		if arm == "hooks":
			seq.events.on("beat", drain_at_hook)

		def producer () -> None:
			nonlocal produced, drain_pending
			interval = 1.0 / rate_hz
			next_at = time.perf_counter() + interval
			while not stop_flag.is_set():
				now = time.perf_counter()
				if now < next_at:
					time.sleep(min(0.002, next_at - now))
					continue
				next_at += interval
				for i in range(burst if pattern == "burst" else 1):
					produced += 1
					value = produced
					if arm == "per_message":
						loop.call_soon_threadsafe(apply_one, value)
					elif arm in ("coalesced", "hooks"):
						inbound.put(value)
						if arm == "coalesced" and not drain_pending:
							drain_pending = True
							loop.call_soon_threadsafe(drain)
					if burst > 1 and pattern == "burst":
						time.sleep(0.001)

		await seq.start()

		thread: typing.Optional[threading.Thread] = None
		if arm != "none":
			thread = threading.Thread(target = producer, daemon = True)
			thread.start()

		try:
			await asyncio.wait_for(asyncio.shield(seq.task), timeout = total_seconds + 2.0)
		except asyncio.TimeoutError:
			pass

		stop_flag.set()
		seq.running = False
		if seq.task and not seq.task.done():
			try:
				await asyncio.wait_for(seq.task, timeout = 2.0)
			except (asyncio.TimeoutError, asyncio.CancelledError):
				seq.task.cancel()
		if thread is not None:
			thread.join(timeout = 2.0)

	load_before = os.getloadavg()[0]
	asyncio.run(_run())
	load_after = os.getloadavg()[0]

	jitter_ms = [abs(value) * 1000.0 for value in jitter_log[:pulses]]

	print(json.dumps({
		"arm": arm,
		"pattern": pattern,
		"rate_hz": rate_hz,
		"burst": burst,
		"pulses": len(jitter_ms),
		"median_ms": round(statistics.median(jitter_ms), 4) if jitter_ms else None,
		"p95_ms": round(_percentile(jitter_ms, 0.95), 4),
		"p99_ms": round(_percentile(jitter_ms, 0.99), 4),
		"max_ms": round(max(jitter_ms), 4) if jitter_ms else None,
		"over_1ms": sum(1 for value in jitter_ms if value > 1.0),
		"produced": produced,
		"applied": applied,
		"loop_wakeups_charged": wakeups,
		"load_before": load_before,
		"load_after": load_after,
	}))


if __name__ == "__main__":
	main()
