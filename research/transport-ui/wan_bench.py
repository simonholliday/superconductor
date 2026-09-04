"""Research prototype (transport-ui): WebSocket RTT from Python to a public echo service over the
home WAN, and ICMP to the same host for comparison. Indicative only: the far end is a cloud PoP,
not Simon's server. Not house style."""
import asyncio, statistics, sys, time, subprocess
import websockets.asyncio.client

async def rtt(url, n=100):
	xs = []
	t0 = time.perf_counter()
	async with websockets.asyncio.client.connect(url, ping_interval=None) as ws:
		# some echo services send a greeting first
		print(f"  connect (TCP+TLS+WS handshake) to {url}: {(time.perf_counter()-t0)*1000:.1f} ms")
		try:
			await asyncio.wait_for(ws.recv(), 1.0)
		except Exception:
			pass
		for i in range(n):
			t0 = time.perf_counter()
			await ws.send('{"t":"set","seq":1,"id":"drums.grid","cell":[3,7],"v":true}')
			await ws.recv()
			xs.append((time.perf_counter() - t0) * 1000)
			await asyncio.sleep(0.02)
	return xs

def stats(name, xs):
	xs = sorted(xs)
	p = lambda q: xs[min(len(xs) - 1, int(q * len(xs)))]
	print(f"{name:40s} n={len(xs):3d} min {xs[0]:7.1f}  median {statistics.median(xs):7.1f}  p95 {p(0.95):7.1f}  max {xs[-1]:7.1f} ms")

for url in sys.argv[1:]:
	try:
		stats(f"WS RTT {url}", asyncio.run(rtt(url)))
	except Exception as e:
		print(url, "failed:", e)
