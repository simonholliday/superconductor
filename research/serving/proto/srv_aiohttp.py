"""Prototype (not house style): aiohttp candidate. Static dir + one WebSocket broadcasting at 30 Hz, echoing taps."""
import asyncio, sys, os, logging
sys.path.insert(0, os.path.dirname(__file__))
import common
from aiohttp import web, WSMsgType

clients: set[web.WebSocketResponse] = set()

async def ws_handler(request: web.Request) -> web.StreamResponse:
	ws = web.WebSocketResponse()
	await ws.prepare(request)
	clients.add(ws)
	try:
		async for msg in ws:
			if msg.type == WSMsgType.TEXT:
				for c in list(clients):
					await c.send_str(msg.data)
	finally:
		clients.discard(ws)
	return ws

async def broadcaster(app: web.Application) -> None:
	step = 0
	while True:
		await asyncio.sleep(1 / 30)
		step += 1
		if clients:
			msg = common.snapshot(step)
			for c in list(clients):
				try:
					await c.send_str(msg)
				except Exception:
					clients.discard(c)

async def index(request: web.Request) -> web.StreamResponse:
	return web.FileResponse(os.path.join(os.path.dirname(__file__), "index.html"))

async def start_bg(app: web.Application):
	app["bg"] = asyncio.create_task(broadcaster(app))
	yield
	app["bg"].cancel()

app = web.Application()
app.add_routes([web.get("/ws", ws_handler), web.get("/", index), web.static("/", os.path.dirname(__file__))])
app.cleanup_ctx.append(start_bg)

if __name__ == "__main__":
	logging.basicConfig(level=logging.WARNING)
	web.run_app(app, host="127.0.0.1", port=int(sys.argv[1]), print=None, access_log=None)
