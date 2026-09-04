"""Research prototype (not house style): clock jitter with ONE outbound
WebSocket link from the sequencer process to a separate service process
(the adapter link shapes B and C put inside the composition; the service does
the fan-out to browsers).

The link connects to load_service.py, sends the grid at RATE_HZ and reads every
frame the service sends back (standing in for inbound commands).  Mode
"loop" runs the link on the sequencer's own asyncio loop; mode "thread" runs
it on a daemon thread with its own loop.
"""

import asyncio
import json
import logging
import statistics
import sys
import threading
import time

logging.basicConfig(level=logging.ERROR)

import websockets.asyncio.client

import subsequence.sequencer

PPQN = 24
BPM = 120.0
BARS = int(sys.argv[1]) if len(sys.argv) > 1 else 32
RATE_HZ = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
MODE = sys.argv[3] if len(sys.argv) > 3 else "loop"
URL = sys.argv[4] if len(sys.argv) > 4 else "ws://127.0.0.1:8791"
CELLS = 128

grid = [False] * CELLS
counts = {"sent": 0, "received": 0}
seq_ref: list = [None]


async def link ():
	interval = 1.0 / RATE_HZ
	async with websockets.asyncio.client.connect(URL) as ws:
		async def reader ():
			async for raw in ws:
				counts["received"] += 1
		asyncio.create_task(reader())
		while True:
			await asyncio.sleep(interval)
			seq = seq_ref[0]
			ph = seq.pulse_count if seq is not None else 0
			await ws.send(json.dumps({"type": "state", "grid": grid, "playhead": ph, "t": time.time()}))
			counts["sent"] += 1


def link_thread ():
	loop = asyncio.new_event_loop()
	asyncio.set_event_loop(loop)
	loop.run_until_complete(link())


async def run ():
	jitter: list = []
	total_seconds = (60.0 / BPM) * 4 * BARS
	seq = subsequence.sequencer.Sequencer(output_device_name="NO-SUCH-DEVICE-XYZ", initial_bpm=BPM, spin_wait=True, _jitter_log=jitter)
	seq_ref[0] = seq
	task = None
	if MODE == "thread":
		threading.Thread(target=link_thread, daemon=True, name="adapter").start()
	else:
		task = asyncio.create_task(link())
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
	if task is not None:
		task.cancel()
	return jitter[: BARS * 4 * PPQN]


def report (j):
	ms = [x * 1000 for x in j]
	s = sorted(ms)
	print(f"one adapter link ({MODE}) to a separate service, {BARS} bars at {BPM:.0f} BPM, {RATE_HZ:.0f} Hz out")
	print(f"  Pulses measured : {len(ms)}")
	print(f"  Mean jitter     : {statistics.mean(ms):8.3f} ms")
	print(f"  Median jitter   : {statistics.median(ms):8.3f} ms")
	print(f"  Std deviation   : {statistics.stdev(ms):8.3f} ms")
	print(f"  P95 jitter      : {s[int(len(s) * 0.95)]:8.3f} ms")
	print(f"  P99 jitter      : {s[int(len(s) * 0.99)]:8.3f} ms")
	print(f"  Max jitter      : {max(ms):8.3f} ms")
	print(f"  link frames     : sent={counts['sent']} received={counts['received']}")


report(asyncio.run(run()))
