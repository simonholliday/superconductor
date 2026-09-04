"""Load generator: N WebSocket clients receiving broadcasts and sending toggles, plus an HTTP fetch loop. Prototype.

usage: load.py PORT CLIENTS TOGGLE_HZ HTTP_RPS
"""

import asyncio
import http.client
import json
import sys
import threading
import time

import websockets.asyncio.client

PORT = int(sys.argv[1])
CLIENTS = int(sys.argv[2])
TOGGLE_HZ = float(sys.argv[3])
HTTP_RPS = float(sys.argv[4])
stats = {"recv": 0, "sent": 0, "http": 0, "http_err": 0, "rtt": []}
stop = threading.Event()


def http_loop() -> None:
	conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
	interval = 1.0 / HTTP_RPS if HTTP_RPS > 0 else None
	while not stop.is_set() and interval:
		t0 = time.perf_counter()
		try:
			conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
			conn.request("GET", "/app.js", headers={"Connection": "close"})
			resp = conn.getresponse()
			resp.read()
			stats["http"] += 1
			if resp.status != 200:
				stats["http_err"] += 1
		except Exception:
			stats["http_err"] += 1
		finally:
			conn.close()
		dt = time.perf_counter() - t0
		time.sleep(max(0.0, interval - dt))


async def client(idx: int) -> None:
	uri = f"ws://127.0.0.1:{PORT}/ws"
	async with websockets.asyncio.client.connect(uri) as ws:
		pending: dict = {}

		async def sender() -> None:
			if TOGGLE_HZ <= 0:
				return
			n = 0
			while True:
				await asyncio.sleep(1.0 / TOGGLE_HZ)
				n += 1
				await ws.send(json.dumps({"type": "toggle", "i": (idx * 7 + n) % 128}))
				stats["sent"] += 1

		task = asyncio.create_task(sender())
		try:
			async for raw in ws:
				stats["recv"] += 1
		finally:
			task.cancel()


async def main() -> None:
	th = threading.Thread(target=http_loop, daemon=True)
	th.start()
	t0 = time.time()

	async def report() -> None:
		while True:
			await asyncio.sleep(4)
			el = time.time() - t0
			print(json.dumps({"elapsed": round(el, 1), "recv": stats["recv"], "sent": stats["sent"], "http": stats["http"], "http_err": stats["http_err"], "recv_per_s": round(stats["recv"] / el, 1)}), flush=True)

	asyncio.create_task(report())
	await asyncio.gather(*(client(i) for i in range(CLIENTS)))


try:
	asyncio.run(main())
except KeyboardInterrupt:
	pass
