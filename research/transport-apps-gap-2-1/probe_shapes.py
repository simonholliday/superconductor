"""RESEARCH PROTOTYPE (2026-09-03), not house style.

Which non-blocking probe actually collects frames that a websockets connection
has already buffered?  Three candidates for the read-batching adapter's inner
loop, all on a real localhost websockets link, no Sequencer involved:

	wait_for_0    asyncio.wait_for(ws.recv(), 0)
	wait_0        one long-lived recv task, asyncio.wait({task}, timeout=0)
	sleep0        one long-lived recv task, N passes of asyncio.sleep(0)
	                (the shape ws_coalesce_bench2.py's WsBatchRead uses)

The sender writes N frames back to back, then waits; the reader takes the frame
that woke it and probes for the rest.  The figure is the batch size.
"""

import asyncio
import json
import sys

import websockets
import websockets.asyncio.client
import websockets.asyncio.server

PORT = 9116


async def server (n: int, bursts: int) -> None:
	async def handler (ws):
		for _ in range(bursts):
			await asyncio.sleep(0.25)
			for i in range(n):
				await ws.send(json.dumps({"cell": i, "value": True}))
		await asyncio.sleep(1.0)
	async with websockets.asyncio.server.serve(handler, "127.0.0.1", PORT):
		await asyncio.sleep(0.3 + 0.25 * bursts + 1.5)


async def reader (shape: str, bursts: int, n_expected: int) -> list[int]:
	batches: list[int] = []
	async with websockets.asyncio.client.connect(f"ws://127.0.0.1:{PORT}") as ws:
		pending = None
		try:
			while sum(batches) < bursts * n_expected:
				if shape == "wait_for_0":
					first = await ws.recv()
					n = 1
					while True:
						try:
							await asyncio.wait_for(ws.recv(), 0)
						except TimeoutError:
							break
						n += 1
					batches.append(n)
					continue
				if pending is None:
					pending = asyncio.ensure_future(ws.recv())
				await pending
				pending = None
				n = 1
				while True:
					if pending is None:
						pending = asyncio.ensure_future(ws.recv())
					if shape == "wait_0":
						done, _ = await asyncio.wait({pending}, timeout=0)
						got = bool(done)
					else:
						for _ in range(3):
							if pending.done():
								break
							await asyncio.sleep(0)
						got = pending.done()
					if not got:
						break
					pending.result()
					pending = None
					n += 1
				batches.append(n)
		except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError):
			pass
		finally:
			if pending is not None:
				pending.cancel()
	return batches


async def main () -> None:
	n = int(sys.argv[1]) if len(sys.argv) > 1 else 128
	bursts = 4
	for shape in ("wait_for_0", "wait_0", "sleep0"):
		srv = asyncio.ensure_future(server(n, bursts))
		await asyncio.sleep(0.2)
		batches = await reader(shape, bursts, n)
		srv.cancel()
		try:
			await srv
		except asyncio.CancelledError:
			pass
		total = sum(batches)
		print(f"{shape:11s} burst={n:5d}  crossings={len(batches):5d}  frames={total:6d}  "
		      f"largest={max(batches) if batches else 0:5d}  mean={total / max(1, len(batches)):8.2f}")


asyncio.run(main())
