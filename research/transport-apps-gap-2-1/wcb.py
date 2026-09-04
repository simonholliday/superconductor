"""RESEARCH PROTOTYPE (2026-09-03), not house style.

Extends scratchpad/transport-apps/revise/ws_drain_bench.py with the shape the
first-use-case design recommends for the thread-to-loop crossing and that no
point measured: **wake the loop, but coalesce**.  Inbound frames are queued on
the link thread and a drain is scheduled onto the clock loop with
call_soon_threadsafe *only when one is not already pending*, so a burst is
meant to cost one wake-up rather than one per message.

The original file is left untouched (it is cited in #1926's provenance); this
is a copy with the coalescing shape, the wake-up counters and a burst sender
added.  adapter_bench.py is reused unchanged for the WsLink base, the apply
step and the statistics.

Scenarios
	baseline        nothing else in the process
	ws-thread       per-message call_soon_threadsafe (the control #1926 measured)
	ws-coalesce     queued on the thread, drain scheduled only when none pending
	ws-drain-beat   queued on the thread, drained in the beat listener (no wake-up)

Traffic shapes (sender side)
	steady --rate HZ            one frame every 1/HZ seconds
	burst  --burst N --burst-period S   N frames back to back every S seconds

Every scenario reports the same jitter statistics as the existing rows plus
the wake-up accounting: how many times the clock loop was actually woken, how
many messages each wake-up carried, and therefore whether coalescing happened.

Usage: ws_coalesce_bench.py SCENARIO ADAPTER_BENCH_DIR [--bars N] [--bpm B]
                            [--rate HZ] [--burst N] [--burst-period S]
"""

import argparse
import asyncio
import json
import queue
import statistics
import sys
import threading
import time

import os

sys.path.insert(0, os.environ["ADAPTER_BENCH_DIR"])
import adapter_bench as ab

import websockets
import websockets.asyncio.client
import websockets.asyncio.server

import subsequence.sequencer

QUEUE_MAX = 4096

# Crossing latency: seconds between the frame being taken off the link thread
# and the write landing on the clock loop.  This is the term the crossing short
# list prices as "a few milliseconds"; nothing measured it.
cross: list = []


def apply_at (cell, value, t0: float) -> None:
	"""Runs on the clock loop.  ab.apply plus the crossing stopwatch."""
	cross.append(time.perf_counter() - t0)
	ab.apply(cell, value)


# ------------------------------------------------------------------ sender

def sender_main (rate: float, seconds: float, burst: int, burst_period: float) -> None:
	"""Stand-in service.  Either a steady stream at `rate` Hz, or `burst`
	frames back to back every `burst_period` seconds.  Counts frames back."""
	sent = [0]
	received = [0]
	end = time.perf_counter() + seconds

	async def main () -> None:
		conns: set = set()

		async def handler (ws):
			conns.add(ws)
			try:
				async for _raw in ws:
					received[0] += 1
			except websockets.exceptions.ConnectionClosed:
				pass
			finally:
				conns.discard(ws)

		async with websockets.asyncio.server.serve(handler, "127.0.0.1", ab.WS_PORT):
			if burst:
				while time.perf_counter() < end:
					await asyncio.sleep(burst_period)
					if not conns:
						continue
					for _ in range(burst):
						payload = json.dumps({"type": "set", "cell": sent[0] % 128, "value": bool(sent[0] % 2)})
						websockets.broadcast(conns, payload)
						sent[0] += 1
			else:
				interval = 1.0 / rate
				while time.perf_counter() < end:
					await asyncio.sleep(interval)
					if conns:
						payload = json.dumps({"type": "set", "cell": sent[0] % 128, "value": bool(sent[0] % 2)})
						websockets.broadcast(conns, payload)
						sent[0] += 1

	asyncio.run(main())
	print(json.dumps({"sender_sent": sent[0], "sender_received": received[0]}), flush=True)


def spawn_sender (rate: float, seconds: float, burst: int, burst_period: float):
	import subprocess
	return subprocess.Popen(
		[sys.executable, __file__, "--send", "--rate", str(rate), "--seconds", str(seconds),
		 "--burst", str(burst), "--burst-period", str(burst_period)],
		stdout=subprocess.PIPE, text=True)


# ------------------------------------------------------------------ adapters

class WsCounting (ab.WsLink):
	"""Per-message call_soon_threadsafe, with the wake-ups counted.

	Identical in behaviour to adapter_bench.WsLink(threaded=True); the only
	addition is the counter, so this row is the control and is directly
	comparable with #1926's ws-thread rows."""

	def __init__ (self, loop) -> None:
		super().__init__(loop, threaded=True)
		self.wakeups = 0

	async def link (self) -> None:
		for _ in range(50):
			try:
				self.ws = await websockets.asyncio.client.connect(f"ws://127.0.0.1:{ab.WS_PORT}")
				break
			except OSError:
				await asyncio.sleep(0.1)
		self.ready.set()
		if self.ws is None:
			return
		try:
			async for raw in self.ws:
				msg = json.loads(raw)
				ab.state["inbound"] += 1
				self.wakeups += 1
				self.loop.call_soon_threadsafe(apply_at, msg["cell"], msg["value"], time.perf_counter())
		except websockets.exceptions.ConnectionClosed:
			pass


class WsCoalesce (ab.WsLink):
	"""Wake the loop, but coalesce: queue every frame on the link thread and
	schedule the drain onto the clock loop only when one is not already
	pending.

	`pending` is cleared at the *start* of the drain, not the end: a frame
	queued while the drain is running then schedules a fresh drain, which may
	find the queue already empty (an empty drain, counted) but can never leave
	a frame sitting unscheduled.  Clearing at the end would be the other way
	round and would lose a frame until the next one arrived."""

	def __init__ (self, loop) -> None:
		super().__init__(loop, threaded=True)
		self.q: "queue.Queue" = queue.Queue(maxsize=QUEUE_MAX)
		self.lock = threading.Lock()
		self.pending = False
		self.dropped = 0
		self.wakeups = 0
		self.drains = 0
		self.empty_drains = 0
		self.batches: list = []

	async def link (self) -> None:
		for _ in range(50):
			try:
				self.ws = await websockets.asyncio.client.connect(f"ws://127.0.0.1:{ab.WS_PORT}")
				break
			except OSError:
				await asyncio.sleep(0.1)
		self.ready.set()
		if self.ws is None:
			return
		try:
			async for raw in self.ws:
				msg = json.loads(raw)
				ab.state["inbound"] += 1
				try:
					self.q.put_nowait((msg["cell"], msg["value"], time.perf_counter()))
				except queue.Full:
					self.dropped += 1
					continue
				with self.lock:
					schedule = not self.pending
					self.pending = True
				if schedule:
					self.wakeups += 1
					self.loop.call_soon_threadsafe(self._drain)
		except websockets.exceptions.ConnectionClosed:
			pass

	def _drain (self) -> None:
		with self.lock:
			self.pending = False
		n = 0
		while True:
			try:
				cell, value, t0 = self.q.get_nowait()
			except queue.Empty:
				break
			apply_at(cell, value, t0)
			n += 1
		self.drains += 1
		self.batches.append(n)
		if n == 0:
			self.empty_drains += 1


class WsDrainBeat (ab.WsLink):
	"""Queued on the thread, drained in the beat listener: no wake-up at all.
	The A-column control, reproduced here so it shares this session's block."""

	def __init__ (self, loop) -> None:
		super().__init__(loop, threaded=True)
		self.q: "queue.Queue" = queue.Queue(maxsize=QUEUE_MAX)
		self.dropped = 0
		self.wakeups = 0
		self.drains = 0
		self.batches: list = []

	async def link (self) -> None:
		for _ in range(50):
			try:
				self.ws = await websockets.asyncio.client.connect(f"ws://127.0.0.1:{ab.WS_PORT}")
				break
			except OSError:
				await asyncio.sleep(0.1)
		self.ready.set()
		if self.ws is None:
			return
		try:
			async for raw in self.ws:
				msg = json.loads(raw)
				ab.state["inbound"] += 1
				try:
					self.q.put_nowait((msg["cell"], msg["value"], time.perf_counter()))
				except queue.Full:
					self.dropped += 1
		except websockets.exceptions.ConnectionClosed:
			pass

	def on_beat (self, beat: int) -> None:
		n = 0
		while True:
			try:
				cell, value, t0 = self.q.get_nowait()
			except queue.Empty:
				break
			apply_at(cell, value, t0)
			n += 1
		self.drains += 1
		self.batches.append(n)
		super().on_beat(beat)


SCENARIOS = {
	"baseline": None,
	"ws-thread": lambda loop: WsCounting(loop),
	"ws-coalesce": lambda loop: WsCoalesce(loop),
	"ws-drain-beat": lambda loop: WsDrainBeat(loop),
}


async def run (scenario: str, bpm: float, bars: int, rate: float, burst: int, burst_period: float, spin: float) -> dict:
	factory = SCENARIOS[scenario]
	jitter: list = []
	total_seconds = (60.0 / bpm) * 4 * bars
	loop = asyncio.get_running_loop()
	sender = None
	adapter = None
	if factory is not None:
		sender = spawn_sender(rate, total_seconds + 3.0, burst, burst_period)
		await asyncio.sleep(0.3)
		adapter = factory(loop)
		await adapter.start()
	seq = subsequence.sequencer.Sequencer(output_device_name="NO-SUCH-DEVICE-XYZ", initial_bpm=bpm, spin_wait=True, _jitter_log=jitter)
	# Lever, not a code change: the engine's own spin margin, set on the
	# instance.  Default is 0.001 (sequencer.py:465).
	seq._spin_threshold = spin
	ab.seq_ref[0] = seq
	if adapter is not None:
		seq.on_event("beat", adapter.on_beat)
	await seq.start()
	try:
		await asyncio.wait_for(asyncio.shield(seq.task), timeout=total_seconds + 2.0)
	except asyncio.TimeoutError:
		pass
	seq.running = False
	try:
		await asyncio.wait_for(seq.task, timeout=2.0)
	except (asyncio.TimeoutError, asyncio.CancelledError):
		seq.task.cancel()
	if adapter is not None:
		await adapter.stop()
	j = jitter[: bars * 4 * ab.PPQN]
	ms = sorted(x * 1000 for x in j)
	r = {
		"scenario": scenario, "bpm": bpm, "bars": bars, "spin_ms": round(spin * 1000, 3),
		"traffic": (f"burst {burst} every {burst_period}s" if burst else f"steady {rate} Hz") if factory else "none",
		"rate_hz": (0 if burst else rate) if factory else 0,
		"burst": burst if factory else 0, "burst_period": burst_period if factory else 0,
		"pulses": len(ms),
		"mean_ms": round(statistics.mean(ms), 4), "median_ms": round(statistics.median(ms), 4),
		"p95_ms": round(ms[int(len(ms) * 0.95)], 4), "p99_ms": round(ms[int(len(ms) * 0.99)], 4),
		"max_ms": round(max(ms), 4), "over_1ms": sum(1 for x in ms if x > 1.0),
		"inbound": ab.state["inbound"], "applied": ab.state["applied"], "pushed": ab.state["pushed"],
	}
	if adapter is not None:
		r["wakeups"] = getattr(adapter, "wakeups", 0)
		r["dropped"] = getattr(adapter, "dropped", 0)
		batches = getattr(adapter, "batches", None)
		if batches is not None:
			r["drains"] = len(batches)
			r["empty_drains"] = getattr(adapter, "empty_drains", sum(1 for b in batches if b == 0))
			nonempty = [b for b in batches if b]
			r["batch_max"] = max(batches) if batches else 0
			r["batch_mean_nonempty"] = round(statistics.mean(nonempty), 3) if nonempty else 0
		if r["wakeups"]:
			r["msgs_per_wakeup"] = round(ab.state["inbound"] / r["wakeups"], 3)
	if cross:
		c = sorted(x * 1000 for x in cross)
		r.update({
			"cross_n": len(c),
			"cross_median_ms": round(statistics.median(c), 4),
			"cross_p95_ms": round(c[int(len(c) * 0.95)], 4),
			"cross_p99_ms": round(c[int(len(c) * 0.99)], 4),
			"cross_max_ms": round(max(c), 4),
			"cross_over_10ms": sum(1 for x in c if x > 10.0),
		})
	if sender is not None:
		ab.finish_sender(sender, r)
	r["loadavg_end"] = open("/proc/loadavg").read().split()[0]
	r["loadavg_start"] = os.environ.get("LOAD_START", "")
	return r


def main () -> None:
	ap = argparse.ArgumentParser()
	ap.add_argument("scenario", nargs="?", default="baseline")
	ap.add_argument("bench_dir", nargs="?", default="")
	ap.add_argument("--bars", type=int, default=16)
	ap.add_argument("--bpm", type=float, default=120.0)
	ap.add_argument("--rate", type=float, default=50.0)
	ap.add_argument("--burst", type=int, default=0)
	ap.add_argument("--burst-period", type=float, default=2.0)
	ap.add_argument("--spin-ms", type=float, default=1.0)
	ap.add_argument("--selector", default="epoll")
	ap.add_argument("--send", action="store_true")
	ap.add_argument("--seconds", type=float, default=10.0)
	ap.add_argument("--tag", default="")
	a = ap.parse_args()
	if a.send:
		sender_main(a.rate, a.seconds, a.burst, a.burst_period)
		return
	if a.selector == "select":
		import selectors

		class _Policy (asyncio.DefaultEventLoopPolicy):

			def new_event_loop (self):
				return asyncio.SelectorEventLoop(selectors.SelectSelector())

		asyncio.set_event_loop_policy(_Policy())
	r = asyncio.run(run(a.scenario, a.bpm, a.bars, a.rate, a.burst, a.burst_period, a.spin_ms / 1000.0))
	r["selector"] = a.selector
	r["tag"] = a.tag
	print(json.dumps(r), flush=True)


if __name__ == "__main__":
	main()
