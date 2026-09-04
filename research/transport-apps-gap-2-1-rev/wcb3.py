"""RESEARCH PROTOTYPE (2026-09-04), not house style.  Revision block J/K.

Adds to wcb2.py the three things the verifiers found missing from the block
that was run on 2026-09-03:

	* a paint-rate (25 Hz) row for every shape, taken on a quiet machine in a
	  block with its own clean baselines.  The figure the design quoted came
	  from a block whose baseline itself logged 25 late pulses;
	* a *second client's tap arriving inside another client's burst*, which is
	  the one case where "no cell in a bulk edit has a finger resting on it"
	  fails.  The sender injects one frame on cell TAP_CELL half way through
	  each burst and one between bursts, and their crossings are reported
	  separately from the burst's;
	* a **bounded** read batch: the same shape as wcb2.WsBatchRead but with the
	  inner read loop capped, so the batch cannot grow to a whole burst.

Everything else is wcb.py's and wcb2.py's, imported from them, so the rows are
comparable with the earlier blocks row for row.  Ports are moved again
(9141/9143/9144/9145) so this block cannot collide with anything.

Usage: wcb3.py SCENARIO [--bars N] [--bpm B] [--rate HZ] [--burst N]
                        [--burst-period S] [--cap N] [--tag T]
Environment: TAP_IN_BURST=1 makes the sender inject the tap frames.
"""

import argparse
import asyncio
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.environ["ADAPTER_BENCH_DIR"])

import adapter_bench as ab
import wcb
import wcb2

import websockets
import websockets.asyncio.client
import websockets.asyncio.server

TAP_CELL = 999

# Crossings of the tap frames only, kept apart from wcb.cross so the burst's
# own crossing statistics stay exactly what the earlier blocks reported.
tap_in_burst: list = []
tap_between: list = []


def apply_at (cell, value, t0: float) -> None:
	"""Replaces wcb.apply_at.  Same work, plus the tap stopwatch."""
	dt = time.perf_counter() - t0
	wcb.cross.append(dt)
	if cell == TAP_CELL:
		(tap_in_burst if value else tap_between).append(dt)
	ab.apply(cell, value)


wcb.apply_at = apply_at


def sender_main (rate: float, seconds: float, burst: int, burst_period: float) -> None:
	"""Stand-in service, wcb.sender_main plus the second client's taps.

	`value` carries the tap's kind so the reader can tell them apart without a
	second field: True is a tap that landed inside a burst, False one that
	landed in the quiet between bursts."""
	sent = [0]
	taps = [0]
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

		def send_one (cell, value):
			websockets.broadcast(conns, json.dumps({"type": "set", "cell": cell, "value": value}))

		async with websockets.asyncio.server.serve(handler, "127.0.0.1", ab.WS_PORT):
			while time.perf_counter() < end:
				await asyncio.sleep(burst_period)
				if not conns:
					continue
				for i in range(burst):
					send_one(sent[0] % 128, bool(sent[0] % 2))
					sent[0] += 1
					if i == burst // 2:
						send_one(TAP_CELL, True)
						taps[0] += 1
				await asyncio.sleep(min(0.4, burst_period / 4.0))
				send_one(TAP_CELL, False)
				taps[0] += 1

	asyncio.run(main())
	print(json.dumps({"sender_sent": sent[0], "sender_taps": taps[0], "sender_received": received[0]}), flush=True)


class WsBatchReadCapped (wcb2.WsBatchRead):

	"""wcb2.WsBatchRead with the inner read loop bounded.

	wcb2's loop reads until the socket yields nothing, so one batch can be a
	whole burst and any frame behind it — another client's tap included —
	waits for the whole burst.  This one stops after `cap` frames and crosses,
	which puts a ceiling on that wait and on the drain."""

	cap = 64

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
				n = 1
				while n < self.cap:
					raw = await self._recv_now()
					if raw is None:
						break
					self._queue(raw)
					n += 1
				self.wakeups += 1
				self.loop.call_soon_threadsafe(self._drain)
		except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError):
			pass
		finally:
			if self._pending is not None:
				self._pending.cancel()
				self._pending = None


def _stats (name: str, xs: list, r: dict) -> None:
	if not xs:
		return
	c = sorted(x * 1000 for x in xs)
	r[f"{name}_n"] = len(c)
	r[f"{name}_median_ms"] = round(statistics.median(c), 4)
	r[f"{name}_p95_ms"] = round(c[int(len(c) * 0.95)], 4)
	r[f"{name}_max_ms"] = round(max(c), 4)


def main () -> None:
	ap = argparse.ArgumentParser()
	ap.add_argument("scenario", nargs="?", default="baseline")
	ap.add_argument("--bars", type=int, default=16)
	ap.add_argument("--bpm", type=float, default=120.0)
	ap.add_argument("--rate", type=float, default=50.0)
	ap.add_argument("--burst", type=int, default=0)
	ap.add_argument("--burst-period", type=float, default=2.0)
	ap.add_argument("--spin-ms", type=float, default=1.0)
	ap.add_argument("--cap", type=int, default=64)
	ap.add_argument("--send", action="store_true")
	ap.add_argument("--seconds", type=float, default=10.0)
	ap.add_argument("--tag", default="")
	a = ap.parse_args()
	if a.send:
		if os.environ.get("TAP_IN_BURST") == "1" and a.burst:
			sender_main(a.rate, a.seconds, a.burst, a.burst_period)
		else:
			wcb.sender_main(a.rate, a.seconds, a.burst, a.burst_period)
		return
	WsBatchReadCapped.cap = a.cap
	wcb.__dict__["__file__"] = os.path.abspath(__file__)
	wcb.SCENARIOS.update(wcb2.SCENARIOS)
	wcb.SCENARIOS["ws-batch-read-capped"] = lambda loop: WsBatchReadCapped(loop)
	r = asyncio.run(wcb.run(a.scenario, a.bpm, a.bars, a.rate, a.burst, a.burst_period, a.spin_ms / 1000.0))
	_stats("tap_in_burst", tap_in_burst, r)
	_stats("tap_between", tap_between, r)
	if a.scenario == "ws-batch-read-capped":
		r["cap"] = a.cap
	r["tap_mode"] = os.environ.get("TAP_IN_BURST") == "1"
	r["tag"] = a.tag
	print(json.dumps(r), flush=True)


if __name__ == "__main__":
	main()
