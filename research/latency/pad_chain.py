"""Research prototype for the latency point of Superintendent. Not house style.

Measures the software half of the pad path on one host:

  synthetic tap -> pointerdown handler -> class change -> WebSocket send
  -> aiohttp "service" (stamp, forward) -> "adapter" WebSocket client on its
  own daemon thread with its own loop (the shape of #1928) -> stamp.

The adapter does not open a MIDI port; the hop from a mido output into
Subsample's virtual port was measured by #1937 at 0.235 ms median and is
added in the finding, not here.

Also records, inside the page: input timestamp -> handler, handler ->
next rAF, rAF -> post-rAF task (approximate commit), and the rAF cadence.

Usage: venv/bin/python pad_chain.py [--taps N] [--browsers chromium,firefox]
Writes results/pad_chain_<browser>_<input>.json and prints a summary.
"""

import argparse
import asyncio
import json
import os
import statistics
import threading
import time

import aiohttp
import aiohttp.web
import playwright.async_api
import websockets.asyncio.client

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8912
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", os.path.join(HERE, "..", "transport-ui", "pw-browsers"))

service_records = {}     # seq -> {"at": page wall ms, "t_svc": ms}
adapter_records = {}     # seq -> t_ad ms
adapter_conns = set()
service_loop = None


def now_ms():
	return time.time() * 1000.0


async def ws_browser(request):
	ws = aiohttp.web.WebSocketResponse(compress=False)
	await ws.prepare(request)
	async for msg in ws:
		if msg.type != aiohttp.WSMsgType.TEXT:
			continue
		t_svc = now_ms()
		m = json.loads(msg.data)
		if m["t"] == "ping":
			await ws.send_str(json.dumps({"t": "pong", "at": m["at"], "server_at": now_ms()}))
		elif m["t"] == "fire":
			service_records[m["seq"]] = {"at": m["at"], "t_svc": t_svc}
			out = json.dumps({"t": "fire", "seq": m["seq"], "path": m["path"], "v": m["v"], "at": m["at"], "t_svc": t_svc})
			for a in list(adapter_conns):
				await a.send_str(out)
			# no ack for fire (#1920): the sound is the ack
	return ws


async def ws_adapter(request):
	ws = aiohttp.web.WebSocketResponse(compress=False)
	await ws.prepare(request)
	adapter_conns.add(ws)
	try:
		async for msg in ws:
			pass
	finally:
		adapter_conns.discard(ws)
	return ws


async def page_handler(request):
	with open(os.path.join(HERE, "page.html"), "rb") as f:
		return aiohttp.web.Response(body=f.read(), content_type="text/html")


def adapter_thread():
	"""The app-side adapter: own loop on a daemon thread, one outbound WebSocket."""
	async def run():
		async with websockets.asyncio.client.connect(f"ws://127.0.0.1:{PORT}/adapter", compression=None) as ws:
			async for raw in ws:
				t_ad = now_ms()
				m = json.loads(raw)
				adapter_records[m["seq"]] = t_ad
	asyncio.run(run())


def pct(xs, p):
	if not xs:
		return float("nan")
	s = sorted(xs)
	return s[min(len(s) - 1, int(round(p / 100.0 * (len(s) - 1))))]


def summarise(name, xs):
	xs = [x for x in xs if x is not None]
	if not xs:
		return f"{name:48s} n=0"
	return (f"{name:48s} n={len(xs):4d} min {min(xs):7.2f} median {statistics.median(xs):7.2f} "
	        f"p95 {pct(xs, 95):7.2f} p99 {pct(xs, 99):7.2f} max {max(xs):7.2f} ms")


async def drive(browser_name, taps, input_kind, tag=""):
	async with playwright.async_api.async_playwright() as p:
		bt = getattr(p, browser_name)
		browser = await bt.launch(headless=True, args=[a for a in os.environ.get("PW_ARGS","").split() if a])
		ctx = await browser.new_context(viewport={"width": 1920, "height": 1080}, has_touch=(input_kind == "touch"))
		page = await ctx.new_page()
		await page.goto(f"http://127.0.0.1:{PORT}/")
		await page.wait_for_function("window.wsOpen === true")
		service_records.clear()
		adapter_records.clear()
		# Clock offset: 40 pings at 50 ms, min-RTT sample kept (#1924's rule).
		for _ in range(40):
			await page.evaluate("window.ping()")
			await asyncio.sleep(0.05)
		await asyncio.sleep(0.2)
		off = await page.evaluate("window.offsetEstimate()")
		# warm-up taps
		for _ in range(10):
			if input_kind == "touch":
				await page.touchscreen.tap(400, 400)
			else:
				await page.mouse.click(400, 400)
			await asyncio.sleep(0.06)
		await page.evaluate("window.records.length = 0; window.rafIntervals.length = 0")
		service_records.clear()
		adapter_records.clear()
		py_before = []
		for _ in range(taps):
			py_before.append(now_ms())
			if input_kind == "touch":
				await page.touchscreen.tap(400, 400)
			else:
				await page.mouse.click(400, 400)
			await asyncio.sleep(0.06)
		await asyncio.sleep(0.3)
		records = await page.evaluate("window.records")
		raf = await page.evaluate("window.rafIntervals")
		time_origin = await page.evaluate("performance.timeOrigin")
		ua = await page.evaluate("navigator.userAgent")
		await browser.close()

	offset = off["off"] if off else 0.0   # server_at - page_wall; add to page time to get server clock
	rows = []
	for i, r in enumerate(records):
		s = r["seq"]
		svc = service_records.get(s)
		ad = adapter_records.get(s)
		page_send_wall = time_origin + r["tSend"]
		row = {
			"seq": s,
			"pointerType": r.get("pointerType"),
			"input_to_handler": r["tHandler"] - r["tInput"],
			"handler_to_class": r["tClass"] - r["tHandler"],
			"class_to_send": r["tSend"] - r["tClass"],
			"handler_to_raf": (r["tRaf"] - r["tHandler"]) if r["tRaf"] is not None else None,
			"raf_to_commit": (r["tCommit"] - r["tRaf"]) if (r["tRaf"] is not None and r["tCommit"] is not None) else None,
			"input_to_commit": (r["tCommit"] - r["tInput"]) if r["tCommit"] is not None else None,
			"send_to_service": (svc["t_svc"] - (page_send_wall + offset)) if svc else None,
			"service_to_adapter": (ad - svc["t_svc"]) if (svc and ad) else None,
			"send_to_adapter": (ad - (page_send_wall + offset)) if ad else None,
			"driver_to_input": ((time_origin + r["tInput"] + offset) - py_before[i]) if i < len(py_before) else None,
		}
		rows.append(row)

	out = {
		"browser": browser_name, "input": input_kind, "ua": ua, "taps": taps,
		"offset_estimate": off, "raf_interval_median": statistics.median(raf) if raf else None,
		"raf_interval_max": max(raf) if raf else None, "rows": rows,
	}
	os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
	with open(os.path.join(HERE, "results", f"pad_chain_{browser_name}_{input_kind}{tag}.json"), "w") as f:
		json.dump(out, f, indent=1)

	print(f"\n== {browser_name} / {input_kind}: {ua}")
	print(f"   clock offset estimate (min-RTT of {off['n'] if off else 0}): off={offset:.3f} ms rtt={off['rtt'] if off else None} ms; rAF median {out['raf_interval_median']} max {out['raf_interval_max']} ms")
	for k in ["driver_to_input", "input_to_handler", "handler_to_class", "class_to_send", "handler_to_raf", "raf_to_commit", "input_to_commit", "send_to_service", "service_to_adapter", "send_to_adapter"]:
		print("   " + summarise(k, [r[k] for r in rows]))


async def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("--taps", type=int, default=200)
	ap.add_argument("--browsers", default="chromium,firefox")
	ap.add_argument("--kinds", default="")
	ap.add_argument("--tag", default="")
	args = ap.parse_args()

	app = aiohttp.web.Application()
	app.router.add_get("/", page_handler)
	app.router.add_get("/ws", ws_browser)
	app.router.add_get("/adapter", ws_adapter)
	runner = aiohttp.web.AppRunner(app)
	await runner.setup()
	site = aiohttp.web.TCPSite(runner, "127.0.0.1", PORT)
	await site.start()

	th = threading.Thread(target=adapter_thread, daemon=True)
	th.start()
	for _ in range(50):
		if adapter_conns:
			break
		await asyncio.sleep(0.1)
	print("adapter connected:", bool(adapter_conns), "aiohttp", aiohttp.__version__, "load", os.getloadavg())

	for b in args.browsers.split(","):
		kinds = args.kinds.split(",") if args.kinds else (["touch", "mouse"] if b == "chromium" else ["mouse", "touch"])
		for k in kinds:
			try:
				await drive(b, args.taps, k, args.tag)
			except Exception as exc:
				print(f"\n== {b} / {k}: FAILED: {exc!r}")
	await runner.cleanup()


if __name__ == "__main__":
	asyncio.run(main())
