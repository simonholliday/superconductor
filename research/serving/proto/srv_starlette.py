"""Prototype (not house style): Starlette + uvicorn candidate. Static dir + one WebSocket broadcasting at 30 Hz, echoing taps."""
import asyncio, sys, os, contextlib
sys.path.insert(0, os.path.dirname(__file__))
import common
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

clients: set[WebSocket] = set()

async def ws_endpoint(ws: WebSocket) -> None:
	await ws.accept()
	clients.add(ws)
	try:
		async for msg in ws.iter_text():
			for c in list(clients):
				await c.send_text(msg)
	except WebSocketDisconnect:
		pass
	finally:
		clients.discard(ws)

async def broadcaster() -> None:
	step = 0
	while True:
		await asyncio.sleep(1 / 30)
		step += 1
		if clients:
			msg = common.snapshot(step)
			for c in list(clients):
				try:
					await c.send_text(msg)
				except Exception:
					clients.discard(c)

@contextlib.asynccontextmanager
async def lifespan(app):
	task = asyncio.create_task(broadcaster())
	yield
	task.cancel()

app = Starlette(routes=[WebSocketRoute("/ws", ws_endpoint), Mount("/", app=StaticFiles(directory=os.path.dirname(__file__), html=True))], lifespan=lifespan)

if __name__ == "__main__":
	uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning", ws=sys.argv[2] if len(sys.argv) > 2 else "auto")
