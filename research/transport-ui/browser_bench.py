"""Research prototype (transport-ui): drive headless Chromium (Playwright) against server.py and
measure, from inside the page: WebSocket RTT (text JSON and binary), fetch POST RTT, SSE one-way
delay, WS one-way delay (same host so clocks agree), and how long a WebSocket takes to notice a
server that stops responding without closing (SIGSTOP). Not house style; measurement only."""
import asyncio, json, os, signal, statistics, subprocess, sys, time
import playwright.async_api

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(HERE, "pw-browsers")
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8902"

JS_RTT = """
async ({url, n, binary}) => {
	const ws = new WebSocket(url);
	ws.binaryType = 'arraybuffer';
	await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
	const rtts = [];
	const payload = JSON.stringify({t:'set', seq:1, id:'drums.grid', cell:[3,7], v:true});
	const bin = new TextEncoder().encode(payload);
	for (let i = 0; i < n; i++) {
		const t0 = performance.now();
		const p = new Promise(res => { ws.onmessage = res; });
		ws.send(binary ? bin : payload);
		await p;
		rtts.push(performance.now() - t0);
		await new Promise(r => setTimeout(r, 5));
	}
	ws.close();
	return rtts;
}
"""

JS_FETCH = """
async ({url, n}) => {
	const rtts = [];
	const body = JSON.stringify({t:'set', seq:1, id:'drums.grid', cell:[3,7], v:true});
	for (let i = 0; i < n; i++) {
		const t0 = performance.now();
		const r = await fetch(url, {method:'POST', body, headers:{'content-type':'application/json'}});
		await r.json();
		rtts.push(performance.now() - t0);
		await new Promise(r => setTimeout(r, 5));
	}
	return rtts;
}
"""

JS_SSE = """
async ({url, n}) => {
	const es = new EventSource(url);
	const d = [];
	await new Promise(res => { es.onmessage = e => { const ts = JSON.parse(e.data).ts; d.push((performance.timeOrigin + performance.now())/1000 - ts); if (d.length >= n) res(); }; });
	es.close();
	return d.map(x => x*1000);
}
"""

JS_WS_ONEWAY = """
async ({url, n}) => {
	const ws = new WebSocket(url);
	await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
	const d = [];
	ws.send('beats');
	await new Promise(res => { ws.onmessage = e => { const ts = JSON.parse(e.data).ts; d.push((performance.timeOrigin + performance.now())/1000 - ts); if (d.length >= n) res(); }; });
	ws.close();
	return d.map(x => x*1000);
}
"""

JS_CONNECT = """
async ({url, n}) => {
	const xs = [];
	for (let i = 0; i < n; i++) {
		const t0 = performance.now();
		const ws = new WebSocket(url);
		await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
		xs.push(performance.now() - t0);
		ws.close();
		await new Promise(r => setTimeout(r, 10));
	}
	return xs;
}
"""

JS_STALL = """
async ({url, wait}) => {
	// open, then the harness SIGSTOPs the server; report whether onclose fired within `wait` ms
	if (window.__ws) { window.__ws.onclose = null; try { window.__ws.close(); } catch (e) {} }
	const ws = new WebSocket(url);
	await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
	window.__closedAt = null;
	const t0 = performance.now();
	ws.onclose = () => { window.__closedAt = performance.now() - t0; };
	window.__ws = ws;
	return true;
}
"""

def stats(name, xs):
	xs = sorted(xs)
	p = lambda q: xs[min(len(xs) - 1, int(q * len(xs)))]
	print(f"{name:34s} n={len(xs):4d} min {xs[0]:7.2f}  median {statistics.median(xs):7.2f}  p95 {p(0.95):7.2f}  p99 {p(0.99):7.2f}  max {xs[-1]:7.2f} ms")

async def main():
	srv = subprocess.Popen([sys.executable, os.path.join(HERE, "server.py")])
	await asyncio.sleep(1.0)
	try:
		async with playwright.async_api.async_playwright() as p:
			b = await p.chromium.launch()
			page = await b.new_page()
			await page.goto(BASE + "/")
			ver = await page.evaluate("navigator.userAgent")
			print("browser:", ver)
			wsurl = BASE.replace("http", "ws") + "/ws"
			stats("WS text RTT (loopback)", await page.evaluate(JS_RTT, {"url": wsurl, "n": 500, "binary": False}))
			stats("WS binary RTT (loopback)", await page.evaluate(JS_RTT, {"url": wsurl, "n": 500, "binary": True}))
			stats("fetch POST RTT (loopback)", await page.evaluate(JS_FETCH, {"url": BASE + "/cmd", "n": 300}))
			stats("SSE one-way delay (loopback)", await page.evaluate(JS_SSE, {"url": BASE + "/sse", "n": 200}))
			stats("WS one-way delay (loopback)", await page.evaluate(JS_WS_ONEWAY, {"url": wsurl, "n": 20}))
			stats("WS connect->open (loopback)", await page.evaluate(JS_CONNECT, {"url": wsurl, "n": 50}))
			# stall test
			await page.evaluate(JS_STALL, {"url": wsurl, "wait": 30000})
			srv.send_signal(signal.SIGSTOP)
			t0 = time.time()
			closed = None
			while time.time() - t0 < 30:
				await asyncio.sleep(1.0)
				closed = await page.evaluate("window.__closedAt")
				if closed is not None:
					break
			print(f"WS onclose after server SIGSTOP (no FIN, no traffic): {'fired at %.0f ms' % closed if closed is not None else 'NOT fired within 30 s'}")
			srv.send_signal(signal.SIGCONT)
			await asyncio.sleep(0.5)
			# clean close: kill server with FIN
			await page.evaluate(JS_STALL, {"url": wsurl, "wait": 5000})
			await asyncio.sleep(0.3)
			await page.evaluate("window.__ws.send('x')")
			await asyncio.sleep(0.3)
			srv.kill()
			t0 = time.time()
			closed = None
			while time.time() - t0 < 10:
				await asyncio.sleep(0.05)
				closed = await page.evaluate("window.__closedAt")
				if closed is not None:
					break
			print(f"WS onclose after server SIGKILL (kernel closes socket): {'fired at %.0f ms' % closed if closed is not None else 'NOT fired within 10 s'}")
			await b.close()
	finally:
		if srv.poll() is None:
			srv.send_signal(signal.SIGCONT)
			srv.kill()

asyncio.run(main())
