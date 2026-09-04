"""REVISER PROTOTYPE (2026-09-03), not house style.

Runs the shape the design recommends and adapter_bench.py never ran: a
websockets client link on a daemon thread with its own loop, inbound frames
queued (bounded queue) and drained on the clock loop at the sequencer's own
hooks.  Reuses adapter_bench.py unchanged for the sender, the WsLink base and
the statistics; only the scenario set and the run loop differ.

Scenarios
	baseline                    nothing else in the process (repeat, same block)
	baseline-pattern            an empty 4-beat Pattern scheduled repeating, no adapter
	ws-thread                   per-message call_soon_threadsafe (repeat, same block)
	ws-thread-drain-beat        queued, drained in the beat listener
	ws-thread-drain-resched     pattern scheduled; drained in reschedule_pulse (awaited
	                            inline before the rebuild) and in beat
	ws-thread-drain-resched-only  pattern scheduled; drained only in reschedule_pulse

Usage: ws_drain_bench.py SCENARIO ADAPTER_BENCH_DIR [--bars N] [--rate HZ]
"""

import argparse
import asyncio
import json
import queue
import statistics
import sys
import time

sys.path.insert(0, sys.argv[2])
import adapter_bench as ab

import websockets
import websockets.asyncio.client

import subsequence.pattern
import subsequence.sequencer

QUEUE_MAX = 4096


class WsDrain (ab.WsLink):

	def __init__ (self, loop, drain_beat: bool, drain_resched: bool) -> None:
		super().__init__(loop, threaded=True)
		self.drain_beat = drain_beat
		self.drain_resched = drain_resched
		self.q: "queue.Queue" = queue.Queue(maxsize=QUEUE_MAX)
		self.dropped = 0
		self.drains_resched = 0
		self.drains_beat = 0

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
					self.q.put_nowait((msg["cell"], msg["value"]))
				except queue.Full:
					self.dropped += 1
		except websockets.exceptions.ConnectionClosed:
			pass

	def _drain (self) -> int:
		n = 0
		while True:
			try:
				cell, value = self.q.get_nowait()
			except queue.Empty:
				return n
			ab.apply(cell, value)
			n += 1

	def on_reschedule_pulse (self, pulse: int, patterns) -> None:
		if self.drain_resched:
			self._drain()
			self.drains_resched += 1

	def on_beat (self, beat: int) -> None:
		if self.drain_beat:
			self._drain()
			self.drains_beat += 1
		super().on_beat(beat)   # one state frame per beat, handed to the link loop


SCENARIOS = {
	"baseline": (None, None, False),
	"baseline-pattern": (None, None, True),
	"ws-thread": ("ws", lambda loop: ab.WsLink(loop, threaded=True), False),
	"ws-thread-drain-beat": ("ws", lambda loop: WsDrain(loop, True, False), False),
	"ws-thread-drain-resched": ("ws", lambda loop: WsDrain(loop, True, True), True),
	"ws-thread-drain-resched-only": ("ws", lambda loop: WsDrain(loop, False, True), True),
}


async def run (scenario: str, bpm: float, bars: int, rate: float) -> dict:
	kind, factory, with_pattern = SCENARIOS[scenario]
	jitter: list = []
	total_seconds = (60.0 / bpm) * 4 * bars
	loop = asyncio.get_running_loop()
	sender = None
	adapter = None
	if kind is not None:
		sender = ab.spawn_sender(kind, rate, total_seconds + 3.0)
		await asyncio.sleep(0.3)
		adapter = factory(loop)
		await adapter.start()
	seq = subsequence.sequencer.Sequencer(output_device_name="NO-SUCH-DEVICE-XYZ", initial_bpm=bpm, spin_wait=True, _jitter_log=jitter)
	ab.seq_ref[0] = seq
	resched_count = [0]
	def count_resched (pulse, patterns):
		resched_count[0] += 1
	seq.on_event("reschedule_pulse", count_resched)
	if adapter is not None:
		seq.on_event("beat", adapter.on_beat)
		if isinstance(adapter, WsDrain):
			seq.on_event("reschedule_pulse", adapter.on_reschedule_pulse)
	await seq.start()
	if with_pattern:
		# An empty pattern: 4 beats, 1 beat lookahead, no notes, so
		# reschedule_pulse fires once per 96 pulses with no MIDI to send.
		pat = subsequence.pattern.Pattern(channel=0, length=4, reschedule_lookahead=1)
		await seq.schedule_pattern_repeating(pat, 0)
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
		"scenario": scenario, "bpm": bpm, "bars": bars, "rate_hz": rate if kind else 0,
		"pulses": len(ms),
		"mean_ms": round(statistics.mean(ms), 4), "median_ms": round(statistics.median(ms), 4),
		"p95_ms": round(ms[int(len(ms) * 0.95)], 4), "p99_ms": round(ms[int(len(ms) * 0.99)], 4),
		"max_ms": round(max(ms), 4), "over_1ms": sum(1 for x in ms if x > 1.0),
		"inbound": ab.state["inbound"], "applied": ab.state["applied"], "pushed": ab.state["pushed"],
		"reschedule_pulse_events": resched_count[0],
	}
	if isinstance(adapter, WsDrain):
		r.update({"dropped": adapter.dropped, "drains_resched": adapter.drains_resched, "drains_beat": adapter.drains_beat})
	if sender is not None:
		ab.finish_sender(sender, r)
	r["selector"] = "epoll"
	return r


def main () -> None:
	ap = argparse.ArgumentParser()
	ap.add_argument("scenario")
	ap.add_argument("bench_dir")
	ap.add_argument("--bars", type=int, default=16)
	ap.add_argument("--bpm", type=float, default=120.0)
	ap.add_argument("--rate", type=float, default=50.0)
	a = ap.parse_args()
	r = asyncio.run(run(a.scenario, a.bpm, a.bars, a.rate))
	print(json.dumps(r), flush=True)


if __name__ == "__main__":
	main()
