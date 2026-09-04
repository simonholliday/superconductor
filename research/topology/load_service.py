"""Research prototype (not house style): a stand-in Superintendent UI service.

Runs as its own process on the same host as the clock benchmark.  It does the
two things the candidate single-process service would do: serve static files
over HTTP and hold WebSocket connections to browsers, pushing a 16x8 grid state
at 20 Hz and echoing every inbound "tap" as a toggled cell.

Ports 8791 (WebSocket) and 8792 (HTTP) are used so nothing collides with the
apps' port map (5555, 8080, 8765, 9000-9004).
"""

import asyncio
import http.server
import json
import os
import sys
import threading
import time

import websockets
import websockets.asyncio.server

WS_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8791
HTTP_PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8792
CELLS = int(sys.argv[3]) if len(sys.argv) > 3 else 128
RATE_HZ = float(sys.argv[4]) if len(sys.argv) > 4 else 20.0

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
with open(os.path.join(STATIC_DIR, "bundle.js"), "w") as fh:
	fh.write("// " + ("x" * 200_000) + "\n")

grid = [False] * CELLS
clients: set = set()
taps = 0


async def handler (ws):
	global taps
	clients.add(ws)
	try:
		await ws.send(json.dumps({"type": "snapshot", "grid": grid}))
		async for raw in ws:
			msg = json.loads(raw)
			if msg.get("type") == "tap":
				i = msg["cell"] % CELLS
				grid[i] = not grid[i]
				taps += 1
	except websockets.exceptions.ConnectionClosed:
		pass
	finally:
		clients.discard(ws)


async def broadcaster ():
	interval = 1.0 / RATE_HZ
	pulse = 0
	while True:
		await asyncio.sleep(interval)
		pulse += 1
		if clients:
			payload = json.dumps({"type": "state", "grid": grid, "playhead": pulse % 16, "t": time.time()})
			websockets.broadcast(clients, payload)


def http_thread ():
	class Handler (http.server.SimpleHTTPRequestHandler):
		def __init__ (self, *a, **kw):
			super().__init__(*a, directory=STATIC_DIR, **kw)
		def log_message (self, *a):
			pass
	class Srv (http.server.ThreadingHTTPServer):
		allow_reuse_address = True
	Srv(("127.0.0.1", HTTP_PORT), Handler).serve_forever()


async def main ():
	threading.Thread(target=http_thread, daemon=True).start()
	async with websockets.asyncio.server.serve(handler, "127.0.0.1", WS_PORT):
		asyncio.create_task(broadcaster())
		while True:
			await asyncio.sleep(10)
			print(f"service: clients={len(clients)} taps={taps}", flush=True)


asyncio.run(main())
