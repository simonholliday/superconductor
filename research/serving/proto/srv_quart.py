"""Prototype (not house style): Quart + Hypercorn candidate. Static dir + one WebSocket broadcasting at 30 Hz, echoing taps."""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(__file__))
import common
from quart import Quart, websocket, send_from_directory
from hypercorn.config import Config
from hypercorn.asyncio import serve

ROOT = os.path.dirname(__file__)
app = Quart(__name__)
clients: set[asyncio.Queue] = set()

@app.route("/<path:name>")
async def static_file(name):
	return await send_from_directory(ROOT, name)

@app.websocket("/ws")
async def ws():
	q: asyncio.Queue = asyncio.Queue()
	clients.add(q)
	async def sender():
		while True:
			await websocket.send(await q.get())
	async def receiver():
		while True:
			msg = await websocket.receive()
			for c in list(clients):
				c.put_nowait(msg)
	try:
		await asyncio.gather(sender(), receiver())
	finally:
		clients.discard(q)

@app.before_serving
async def start_bg():
	app.bg = asyncio.create_task(broadcaster())

async def broadcaster():
	step = 0
	while True:
		await asyncio.sleep(1 / 30)
		step += 1
		if clients:
			msg = common.snapshot(step)
			for c in list(clients):
				c.put_nowait(msg)

if __name__ == "__main__":
	cfg = Config(); cfg.bind = [f"127.0.0.1:{sys.argv[1]}"]; cfg.accesslog = None; cfg.errorlog = None
	asyncio.run(serve(app, cfg))
