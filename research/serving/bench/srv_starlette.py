"""Starlette (or FastAPI) on uvicorn: WebSocketRoute plus StaticFiles(html=True). Prototype."""

import asyncio
import contextlib
import sys

import starlette.applications
import starlette.routing
import starlette.staticfiles
import starlette.websockets
import uvicorn

import common

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18802
USE_FASTAPI = len(sys.argv) > 2 and sys.argv[2] == "fastapi"
grid = common.Grid()
clients: set = set()


async def ws_endpoint(websocket: starlette.websockets.WebSocket) -> None:
	await websocket.accept()
	clients.add(websocket)
	try:
		await websocket.send_text(grid.snapshot())
		async for raw in websocket.iter_text():
			grid.handle(raw)
	except starlette.websockets.WebSocketDisconnect:
		pass
	finally:
		clients.discard(websocket)


async def broadcaster() -> None:
	interval = 1.0 / common.BROADCAST_HZ
	while True:
		await asyncio.sleep(interval)
		if clients:
			msg = grid.snapshot()
			dead = []
			for c in list(clients):
				try:
					await c.send_text(msg)
				except Exception:
					dead.append(c)
			for c in dead:
				clients.discard(c)


@contextlib.asynccontextmanager
async def lifespan(app):
	task = asyncio.create_task(broadcaster())
	print("ready", flush=True)
	yield
	task.cancel()


common.ensure_www()
routes = [
	starlette.routing.WebSocketRoute("/ws", ws_endpoint),
	starlette.routing.Mount("/", app=starlette.staticfiles.StaticFiles(directory=common.WWW, html=True)),
]
if USE_FASTAPI:
	import fastapi
	app = fastapi.FastAPI(lifespan=lifespan)
	app.router.routes.extend(routes)
else:
	app = starlette.applications.Starlette(routes=routes, lifespan=lifespan)

uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning", access_log=False)
