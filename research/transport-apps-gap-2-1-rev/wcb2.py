"""RESEARCH PROTOTYPE (2026-09-03), not house style.  Revision block.

Extends ws_coalesce_bench.py (same directory, left untouched because the first
block's rows cite it) with the two crossing shapes the first block omitted and
that #2021 measured with a synthetic in-process producer rather than a socket:

	ws-batch-read   the link thread reads every frame the socket has already
	                buffered, queues them all, and crosses onto the clock loop
	                once.  This is #2021's "batching at the socket read",
	                implemented here over a real websockets connection.
	ws-direct       no crossing at all: the link thread writes the value
	                itself, the shape the engine already uses for CC input
	                mappings (subsequence/sequencer.py:770-772, write at 800)
	                and #2021's off-loop column C.

Everything else — the real Sequencer with _jitter_log, 16 bars at 120 BPM,
spin-wait on, no MIDI port, the separate sender process, the wake-up counters,
the crossing stopwatch, the load gate — is ws_coalesce_bench.py's, imported
from it so the two blocks are the same instrument.

Usage: ws_coalesce_bench2.py SCENARIO [--bars N] [--bpm B] [--rate HZ]
                             [--burst N] [--burst-period S] [--spin-ms MS]
                             [--selector epoll|select] [--tag T]
"""

import argparse
import asyncio
import json
import os
import queue
import statistics
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.environ["ADAPTER_BENCH_DIR"])

import adapter_bench as ab
import wcb as wcb

import websockets
import websockets.asyncio.client

import subsequence.sequencer

QUEUE_MAX = wcb.QUEUE_MAX


class WsBatchRead (ab.WsLink):

	"""Batch at the socket read, then cross once.

	The link thread takes the frame that woke it, then keeps taking frames for
	as long as the connection can hand one over without waiting on the network:
	`_recv_now` gives the link loop three passes, each of which polls the
	selector with a zero timeout, so anything already in the kernel buffer or
	already assembled by `websockets` is collected.  Only when a pass yields
	nothing does the thread schedule one `call_soon_threadsafe`.  No timer and
	no added delay: a lone frame crosses as soon as the loop can take it."""

	def __init__ (self, loop) -> None:
		super().__init__(loop, threaded=True)
		self.q: "queue.Queue" = queue.Queue(maxsize=QUEUE_MAX)
		self.dropped = 0
		self.wakeups = 0
		self.batches: list = []
		self.empty_drains = 0
		self._pending = None

	async def _recv_now (self):
		"""A frame if one can be had without waiting on the network, else None."""
		if self._pending is None:
			self._pending = asyncio.ensure_future(self.ws.recv())
		for _ in range(3):
			if self._pending.done():
				break
			await asyncio.sleep(0)
		if not self._pending.done():
			return None
		task = self._pending
		self._pending = None
		return task.result()

	def _queue (self, raw) -> None:
		msg = json.loads(raw)
		ab.state["inbound"] += 1
		try:
			self.q.put_nowait((msg["cell"], msg["value"], time.perf_counter()))
		except queue.Full:
			self.dropped += 1

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
			while True:
				if self._pending is None:
					self._pending = asyncio.ensure_future(self.ws.recv())
				self._queue(await self._pending)
				self._pending = None
				while True:
					raw = await self._recv_now()
					if raw is None:
						break
					self._queue(raw)
				self.wakeups += 1
				self.loop.call_soon_threadsafe(self._drain)
		except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError):
			pass
		finally:
			if self._pending is not None:
				self._pending.cancel()
				self._pending = None

	def _drain (self) -> None:
		n = 0
		while True:
			try:
				cell, value, t0 = self.q.get_nowait()
			except queue.Empty:
				break
			wcb.apply_at(cell, value, t0)
			n += 1
		self.batches.append(n)
		if n == 0:
			self.empty_drains += 1


class WsDirect (ab.WsLink):

	"""No crossing: the link thread applies the value on its own thread.

	The engine's own precedent for a non-loop write into composition.data is
	the rtmidi callback applying CC input mappings inline, on the stated ground
	that "Single dict writes are safe from a non-asyncio thread under CPython's
	GIL" (subsequence/sequencer.py:770-772, the write at 800).  The clock loop
	is never woken, so there is no wake-up to round."""

	def __init__ (self, loop) -> None:
		super().__init__(loop, threaded=True)
		self.wakeups = 0
		self.dropped = 0

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
				wcb.apply_at(msg["cell"], msg["value"], time.perf_counter())
		except websockets.exceptions.ConnectionClosed:
			pass


SCENARIOS = dict(wcb.SCENARIOS)
SCENARIOS["ws-batch-read"] = lambda loop: WsBatchRead(loop)
SCENARIOS["ws-direct"] = lambda loop: WsDirect(loop)


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
		wcb.sender_main(a.rate, a.seconds, a.burst, a.burst_period)
		return
	if a.selector == "select":
		import selectors

		class _Policy (asyncio.DefaultEventLoopPolicy):

			def new_event_loop (self):
				return asyncio.SelectorEventLoop(selectors.SelectSelector())

		asyncio.set_event_loop_policy(_Policy())
	# The sender is spawned from ws_coalesce_bench.py's own __file__, so point
	# it at this module instead: the two files' sender_main is the same code.
	wcb.__dict__["__file__"] = os.path.abspath(__file__)
	wcb.SCENARIOS.update(SCENARIOS)
	r = asyncio.run(wcb.run(a.scenario, a.bpm, a.bars, a.rate, a.burst, a.burst_period, a.spin_ms / 1000.0))
	r["selector"] = a.selector
	r["tag"] = a.tag
	print(json.dumps(r), flush=True)


if __name__ == "__main__":
	main()
