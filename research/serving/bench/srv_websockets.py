"""websockets-only server: WebSocket plus static files via process_request (Supervisor's shape). Prototype."""

import asyncio
import http
import mimetypes
import os
import sys

import websockets
import websockets.asyncio.server
import websockets.datastructures
import websockets.http11

import common

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18801
grid = common.Grid()
clients: set = set()


def process_request(connection, request):
	if request.headers.get("Upgrade", "").lower() == "websocket":
		return None
	path = "/index.html" if request.path == "/" else request.path
	full = os.path.realpath(os.path.join(common.WWW, path.lstrip("/")))
	if not full.startswith(common.WWW + os.sep) or not os.path.isfile(full):
		return connection.respond(http.HTTPStatus.NOT_FOUND, "Not found\n")
	with open(full, "rb") as fh:
		body = fh.read()
	ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
	return websockets.http11.Response(200, "OK", websockets.datastructures.Headers([("Content-Type", ctype), ("Content-Length", str(len(body)))]), body)


async def handler(ws):
	clients.add(ws)
	try:
		await ws.send(grid.snapshot())
		async for raw in ws:
			grid.handle(raw)
	except websockets.exceptions.ConnectionClosed:
		pass
	finally:
		clients.discard(ws)


async def broadcaster():
	interval = 1.0 / common.BROADCAST_HZ
	while True:
		await asyncio.sleep(interval)
		if clients:
			websockets.broadcast(clients, grid.snapshot())


async def main():
	common.ensure_www()
	async with websockets.asyncio.server.serve(handler, "0.0.0.0", PORT, process_request=process_request):
		asyncio.create_task(broadcaster())
		print("ready", flush=True)
		await asyncio.Future()


asyncio.run(main())
