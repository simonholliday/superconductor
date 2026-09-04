"""Prototype (not house style): load generator. N WebSocket clients receiving broadcasts and sending a tap at 10 Hz each; one HTTP client fetching the static page at 10 req/s. Prints message counts and one-way latency of broadcasts."""
import asyncio, sys, json, time, statistics
import websockets
import websockets.asyncio.client
import urllib.request

async def ws_client(url, seconds, stats):
	async with websockets.asyncio.client.connect(url) as ws:
		end = time.time() + seconds
		last_tap = 0.0
		while time.time() < end:
			try:
				raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
			except asyncio.TimeoutError:
				continue
			m = json.loads(raw)
			if m.get("type") == "state":
				stats["state"] += 1
				stats["lat"].append(time.time() - m["t"])
			else:
				stats["echo"] += 1
			if time.time() - last_tap > 0.1:
				last_tap = time.time()
				await ws.send(json.dumps({"type": "set", "cell": 5, "on": True}))

def http_loop(url, seconds, stats):
	end = time.time() + seconds
	while time.time() < end:
		t0 = time.time()
		with urllib.request.urlopen(url) as r:
			stats["bytes"] += len(r.read())
		stats["http"] += 1
		time.sleep(max(0, 0.1 - (time.time() - t0)))

async def main():
	port, seconds, n = int(sys.argv[1]), float(sys.argv[2]), int(sys.argv[3])
	stats = {"state": 0, "echo": 0, "http": 0, "bytes": 0, "lat": []}
	http = asyncio.to_thread(http_loop, f"http://127.0.0.1:{port}/index.html", seconds, stats)
	await asyncio.gather(http, *[ws_client(f"ws://127.0.0.1:{port}/ws", seconds, stats) for _ in range(n)])
	lat = sorted(stats["lat"])
	print(json.dumps({"state_msgs": stats["state"], "echo_msgs": stats["echo"], "http_reqs": stats["http"], "http_MB": round(stats["bytes"] / 1e6, 1), "bcast_oneway_ms_median": round(statistics.median(lat) * 1000, 2) if lat else None, "bcast_oneway_ms_p99": round(lat[int(len(lat) * 0.99)] * 1000, 2) if lat else None}))

asyncio.run(main())
