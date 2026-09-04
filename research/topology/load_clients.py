"""Research prototype (not house style): simulated browsers.

Opens N WebSocket clients against the stand-in service, reads every frame,
sends a tap every 100 ms per client, and (optionally) fetches a 200 KB static
bundle over HTTP in a tight loop to stand in for page reloads.
"""

import asyncio
import json
import sys
import time
import urllib.request

WS_URL = sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:8791"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 4
HTTP_URL = sys.argv[3] if len(sys.argv) > 3 else ""

import websockets.asyncio.client

frames = 0
rtts: list = []


async def client (idx: int):
	global frames
	async with websockets.asyncio.client.connect(WS_URL) as ws:
		async def reader ():
			global frames
			async for raw in ws:
				frames += 1
		asyncio.create_task(reader())
		while True:
			await asyncio.sleep(0.1)
			await ws.send(json.dumps({"type": "tap", "cell": (idx * 7 + frames) % 128}))


async def fetcher ():
	loop = asyncio.get_running_loop()
	while True:
		t0 = time.perf_counter()
		await loop.run_in_executor(None, lambda: urllib.request.urlopen(HTTP_URL, timeout=5).read())
		rtts.append(time.perf_counter() - t0)
		await asyncio.sleep(0.05)


async def main ():
	tasks = [asyncio.create_task(client(i)) for i in range(N)]
	if HTTP_URL:
		tasks.append(asyncio.create_task(fetcher()))
	while True:
		await asyncio.sleep(10)
		print(f"clients: frames={frames} fetches={len(rtts)}", flush=True)


asyncio.run(main())
