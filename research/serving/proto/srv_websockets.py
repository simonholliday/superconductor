"""Prototype (not house style): websockets candidate. process_request serves the static file; one WebSocket broadcasting at 30 Hz, echoing taps."""
import asyncio, sys, os, mimetypes
sys.path.insert(0, os.path.dirname(__file__))
import common
import websockets
import websockets.asyncio.server
from websockets.datastructures import Headers
from websockets.http11 import Response

ROOT = os.path.dirname(__file__)
clients: set = set()

def process_request(connection, request):
	if request.path == "/ws":
		return None
	rel = request.path.lstrip("/") or "index.html"
	full = os.path.realpath(os.path.join(ROOT, rel))
	if not full.startswith(ROOT + os.sep) or not os.path.isfile(full):
		return Response(404, "Not Found", Headers(), b"not found")
	with open(full, "rb") as fh:
		body = fh.read()
	return Response(200, "OK", Headers([("Content-Type", mimetypes.guess_type(full)[0] or "application/octet-stream"), ("Content-Length", str(len(body)))]), body)

async def handler(ws) -> None:
	clients.add(ws)
	try:
		async for msg in ws:
			websockets.broadcast(clients, msg)
	finally:
		clients.discard(ws)

async def broadcaster() -> None:
	step = 0
	while True:
		await asyncio.sleep(1 / 30)
		step += 1
		if clients:
			websockets.broadcast(clients, common.snapshot(step))

async def main() -> None:
	async with websockets.asyncio.server.serve(handler, "127.0.0.1", int(sys.argv[1]), process_request=process_request):
		await broadcaster()

asyncio.run(main())
