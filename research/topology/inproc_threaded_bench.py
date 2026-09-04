"""Research prototype (not house style): clock jitter with a WebSocket server
running on a daemon THREAD with its own asyncio loop inside the sequencer's
process (Supervisor's start_threaded() shape, supervisor/core.py:91-119).

Same measurement as benchmarks/clock_jitter.py.  The server on port 8794
broadcasts a 16x8 grid to every connected client at RATE_HZ and toggles cells
on inbound taps.  Run load_clients.py against ws://127.0.0.1:8794 while this
runs.  The clock runs on the main thread's loop and never touches the socket.
"""

import asyncio
import json
import logging
import statistics
import sys
import threading
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
peak_clients = 0
seq_ref: list = [None]


async def handler (ws):
	global peak_clients
	clients.add(ws)
	peak_clients = max(peak_clients, len(clients))
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


async def broadcaster ():
	interval = 1.0 / RATE_HZ
	while True:
		await asyncio.sleep(interval)
		if clients:
			seq = seq_ref[0]
			ph = seq.pulse_count if seq is not None else 0
			payload = json.dumps({"type": "state", "grid": grid, "playhead": ph, "t": time.time()})
			websockets.broadcast(clients, payload)


async def server_main ():
	async with websockets.asyncio.server.serve(handler, "127.0.0.1", 8794):
		await broadcaster()


def server_thread ():
	loop = asyncio.new_event_loop()
	asyncio.set_event_loop(loop)
	loop.run_until_complete(server_main())


async def run ():
	jitter: list = []
	total_seconds = (60.0 / BPM) * 4 * BARS
	seq = subsequence.sequencer.Sequencer(output_device_name="NO-SUCH-DEVICE-XYZ", initial_bpm=BPM, spin_wait=True, _jitter_log=jitter)
	seq_ref[0] = seq
	threading.Thread(target=server_thread, daemon=True, name="adapter").start()
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
	return jitter[: BARS * 4 * PPQN]


def report (j):
	ms = [x * 1000 for x in j]
	s = sorted(ms)
	print(f"threaded in-process ws server, {BARS} bars at {BPM:.0f} BPM, broadcast at {RATE_HZ:.0f} Hz")
	print(f"  Pulses measured : {len(ms)}")
	print(f"  Mean jitter     : {statistics.mean(ms):8.3f} ms")
	print(f"  Median jitter   : {statistics.median(ms):8.3f} ms")
	print(f"  Std deviation   : {statistics.stdev(ms):8.3f} ms")
	print(f"  P95 jitter      : {s[int(len(s) * 0.95)]:8.3f} ms")
	print(f"  P99 jitter      : {s[int(len(s) * 0.99)]:8.3f} ms")
	print(f"  Max jitter      : {max(ms):8.3f} ms")
	print(f"  peak clients    : {peak_clients}")


report(asyncio.run(run()))
