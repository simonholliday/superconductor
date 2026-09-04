"""Research prototype (transport-ui): one aiohttp process on 127.0.0.1:8902 serving
- GET /            a test page
- WS  /ws          echo (text and binary), plus a server-side beat stream when asked
- GET /sse         server-sent events, one event every 100 ms carrying time.time()
- POST /cmd        command endpoint returning {"ok":true,"ts":time.time()}
Not house style; measurement only. Port 8902 is outside the forbidden set."""
import asyncio, json, time, sys
import aiohttp.web

PAGE = b"<!doctype html><title>transport-ui bench</title><body>bench</body>"

async def index(req):
	return aiohttp.web.Response(body=PAGE, content_type="text/html")

async def ws(req):
	w = aiohttp.web.WebSocketResponse(heartbeat=None, autoping=True)
	await w.prepare(req)
	async for m in w:
		if m.type == aiohttp.WSMsgType.TEXT:
			if m.data == "beats":
				asyncio.create_task(beats(w))
			else:
				await w.send_str(m.data)
		elif m.type == aiohttp.WSMsgType.BINARY:
			await w.send_bytes(m.data)
	return w

async def beats(w):
	# emulate a 24 PPQN beat event at 120 BPM: one message every 500 ms with the server clock
	try:
		while not w.closed:
			await w.send_str(json.dumps({"t": "beat", "ts": time.time()}))
			await asyncio.sleep(0.5)
	except Exception:
		pass

async def sse(req):
	r = aiohttp.web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"})
	await r.prepare(req)
	try:
		i = 0
		while True:
			await r.write(f"id: {i}\ndata: {json.dumps({'ts': time.time()})}\n\n".encode())
			i += 1
			await asyncio.sleep(0.1)
	except (ConnectionResetError, asyncio.CancelledError):
		pass
	return r

async def cmd(req):
	await req.read()
	return aiohttp.web.json_response({"ok": True, "ts": time.time()})

app = aiohttp.web.Application()
app.add_routes([aiohttp.web.get("/", index), aiohttp.web.get("/ws", ws), aiohttp.web.get("/sse", sse), aiohttp.web.post("/cmd", cmd)])
host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
aiohttp.web.run_app(app, host=host, port=8902, print=None)
