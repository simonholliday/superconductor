"""Research prototype (playhead), not house style: aiohttp server on 127.0.0.1:8903 serving
the bench page and a WebSocket that answers {"t":"ping","at":x} with
{"t":"pong","at":x,"server_at":<time.time()*1000>} so a page can estimate clock offset
NTP-style.  Port 8903 is outside the reserved set (5555, 8080, 8765, 9000-9004)."""
import asyncio, json, os, time
import aiohttp.web

HERE = os.path.dirname(os.path.abspath(__file__))


async def ws_handler (request):
	ws = aiohttp.web.WebSocketResponse(compress=False)
	await ws.prepare(request)
	async for msg in ws:
		if msg.type != aiohttp.WSMsgType.TEXT:
			continue
		d = json.loads(msg.data)
		if d.get("t") == "ping":
			await ws.send_str(json.dumps({"t": "pong", "at": d["at"], "server_at": time.time() * 1000.0}))
	return ws


async def page (request):
	with open(os.path.join(HERE, "bench.html")) as f:
		return aiohttp.web.Response(text=f.read(), content_type="text/html")


app = aiohttp.web.Application()
app.router.add_get("/", page)
app.router.add_get("/ws", ws_handler)
aiohttp.web.run_app(app, host="127.0.0.1", port=8903, print=None)
