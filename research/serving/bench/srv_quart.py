"""Quart on Hypercorn: @app.websocket plus static folder. Prototype."""

import asyncio
import sys

import hypercorn.asyncio
import hypercorn.config
import quart

import common

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18804
grid = common.Grid()
clients: set = set()

common.ensure_www()
app = quart.Quart(__name__, static_folder=common.WWW, static_url_path="")


@app.route("/")
async def index():
	return await quart.send_from_directory(common.WWW, "index.html")


@app.websocket("/ws")
async def ws():
	q: asyncio.Queue = asyncio.Queue()
	clients.add(q)
	try:
		await quart.websocket.send(grid.snapshot())

		async def pump():
			while True:
				await quart.websocket.send(await q.get())

		async def drain():
			while True:
				grid.handle(await quart.websocket.receive())

		await asyncio.gather(pump(), drain())
	except asyncio.CancelledError:
		raise
	finally:
		clients.discard(q)


async def broadcaster():
	interval = 1.0 / common.BROADCAST_HZ
	while True:
		await asyncio.sleep(interval)
		if clients:
			msg = grid.snapshot()
			for q in list(clients):
				q.put_nowait(msg)


@app.before_serving
async def startup():
	app.add_background_task(broadcaster)
	print("ready", flush=True)


cfg = hypercorn.config.Config()
cfg.bind = [f"0.0.0.0:{PORT}"]
cfg.accesslog = None
cfg.errorlog = None
asyncio.run(hypercorn.asyncio.serve(app, cfg))
