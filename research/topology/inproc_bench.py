"""Research prototype (not house style): clock jitter with a WebSocket server
running INSIDE the sequencer's own asyncio loop (the Supervisor-style
in-process adapter shape).

Same measurement as benchmarks/clock_jitter.py, but a websockets server on
port 8793 lives on the same loop, broadcasts a 16x8 grid every 50 ms to all
connected clients and toggles cells on inbound taps.  Run load_clients.py
against ws://127.0.0.1:8793 while this runs.
"""

import asyncio
import json
import logging
import statistics
import sys
import time

logging.basicConfig(level=logging.ERROR)

import websockets
import websockets.asyncio.server

import subsequence.sequencer

PPQN = 24
BPM = 120.0
BARS = int(sys.argv[1]) if len(sys.argv) > 1 else 32
RATE_HZ = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
CELLS = 128

grid = [False] * CELLS
clients: set = set()


async def handler (ws):
	clients.add(ws)
	try:
		await ws.send(json.dumps({"type": "snapshot", "grid": grid}))
		async for raw in ws:
			msg = json.loads(raw)
			if msg.get("type") == "tap":
				i = msg["cell"] % CELLS
				grid[i] = not grid[i]
	except websockets.exceptions.ConnectionClosed:
		pass
	finally:
		clients.discard(ws)


async def broadcaster (seq):
	interval = 1.0 / RATE_HZ
	while True:
		await asyncio.sleep(interval)
		if clients:
			payload = json.dumps({"type": "state", "grid": grid, "playhead": seq.pulse_count, "t": time.time()})
			websockets.broadcast(clients, payload)


async def run ():
	jitter: list = []
	total_seconds = (60.0 / BPM) * 4 * BARS
	seq = subsequence.sequencer.Sequencer(output_device_name="NO-SUCH-DEVICE-XYZ", initial_bpm=BPM, spin_wait=True, _jitter_log=jitter)
	async with websockets.asyncio.server.serve(handler, "127.0.0.1", 8793):
		bcast = asyncio.create_task(broadcaster(seq))
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
		bcast.cancel()
	return jitter[: BARS * 4 * PPQN]


def report (j):
	ms = [x * 1000 for x in j]
	s = sorted(ms)
	print(f"in-process ws server, {BARS} bars at {BPM:.0f} BPM, clients broadcast at {RATE_HZ:.0f} Hz")
	print(f"  Pulses measured : {len(ms)}")
	print(f"  Mean jitter     : {statistics.mean(ms):8.3f} ms")
	print(f"  Median jitter   : {statistics.median(ms):8.3f} ms")
	print(f"  Std deviation   : {statistics.stdev(ms):8.3f} ms")
	print(f"  P95 jitter      : {s[int(len(s) * 0.95)]:8.3f} ms")
	print(f"  P99 jitter      : {s[int(len(s) * 0.99)]:8.3f} ms")
	print(f"  Max jitter      : {max(ms):8.3f} ms")
	print(f"  clients at end  : {len(clients)}")


report(asyncio.run(run()))
