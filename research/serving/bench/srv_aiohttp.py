"""aiohttp: WebSocketResponse plus web.static. Prototype."""

import asyncio
import os
import sys

import aiohttp
import aiohttp.web

import common

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18803
grid = common.Grid()
clients: set = set()


async def ws_handler(request):
	ws = aiohttp.web.WebSocketResponse()
	await ws.prepare(request)
	clients.add(ws)
	try:
		await ws.send_str(grid.snapshot())
		async for msg in ws:
			if msg.type == aiohttp.WSMsgType.TEXT:
				grid.handle(msg.data)
	finally:
		clients.discard(ws)
	return ws


async def index(request):
	return aiohttp.web.FileResponse(os.path.join(common.WWW, "index.html"))


async def broadcaster(app):
	interval = 1.0 / common.BROADCAST_HZ
	while True:
		await asyncio.sleep(interval)
		if clients:
			msg = grid.snapshot()
			for c in list(clients):
				try:
					await c.send_str(msg)
				except Exception:
					clients.discard(c)


async def on_startup(app):
	app["bcast"] = asyncio.create_task(broadcaster(app))
	print("ready", flush=True)


common.ensure_www()
app = aiohttp.web.Application()
app.router.add_get("/ws", ws_handler)
app.router.add_get("/", index)
app.router.add_static("/", common.WWW)
app.on_startup.append(on_startup)
aiohttp.web.run_app(app, host="0.0.0.0", port=PORT, print=None, access_log=None)
