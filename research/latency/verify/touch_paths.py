"""Verifier prototype, not house style. Drives the researcher's page.html through
several CDP injection paths in headless Chromium to see whether the two-frame
input-to-commit seen with page.touchscreen.tap follows the injection path or the
renderer's touch pipeline. Serves page.html on 127.0.0.1:8913 with a /ws that
answers ping and swallows fire."""
import asyncio, json, os, statistics, sys, time
import aiohttp, aiohttp.web
import playwright.async_api

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "..", "page.html")
PORT = 8913
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", os.path.join(HERE, "..", "..", "transport-ui", "pw-browsers"))

async def ws(request):
	w = aiohttp.web.WebSocketResponse(compress=False)
	await w.prepare(request)
	async for msg in w:
		if msg.type != aiohttp.WSMsgType.TEXT: continue
		m = json.loads(msg.data)
		if m["t"] == "ping":
			await w.send_str(json.dumps({"t": "pong", "at": m["at"], "server_at": time.time()*1000}))
	return w

async def page_handler(request):
	return aiohttp.web.Response(body=open(PAGE, "rb").read(), content_type="text/html")

def pct(xs, p):
	s = sorted(xs); return s[min(len(s)-1, int(round(p/100*(len(s)-1))))]

def summ(name, xs):
	xs = [x for x in xs if x is not None]
	return f"   {name:20s} n={len(xs):3d} min {min(xs):6.2f} med {statistics.median(xs):6.2f} p95 {pct(xs,95):6.2f} max {max(xs):6.2f}"

async def run_case(browser, label, has_touch, tapper, taps=100, args=None):
	ctx = await browser.new_context(viewport={"width":1920,"height":1080}, has_touch=has_touch)
	page = await ctx.new_page()
	cdp = await ctx.new_cdp_session(page)
	await page.goto(f"http://127.0.0.1:{PORT}/")
	await page.wait_for_function("window.wsOpen === true")
	for _ in range(10):
		await tapper(page, cdp); await asyncio.sleep(0.06)
	await page.evaluate("window.records.length = 0")
	for _ in range(taps):
		await tapper(page, cdp); await asyncio.sleep(0.06)
	await asyncio.sleep(0.3)
	recs = await page.evaluate("window.records")
	pts = sorted(set(r["pointerType"] for r in recs))
	print(f"== {label}  (has_touch={has_touch}, pointerType={pts}, n={len(recs)})")
	print(summ("input_to_handler", [r["tHandler"]-r["tInput"] for r in recs]))
	print(summ("handler_to_raf", [r["tRaf"]-r["tHandler"] for r in recs if r["tRaf"] is not None]))
	print(summ("input_to_commit", [r["tCommit"]-r["tInput"] for r in recs if r["tCommit"] is not None]))
	await ctx.close()

async def tap_pw(page, cdp):
	await page.touchscreen.tap(400, 400)

async def click_pw(page, cdp):
	await page.mouse.click(400, 400)

async def tap_cdp_split(page, cdp):
	await cdp.send("Input.dispatchTouchEvent", {"type":"touchStart","touchPoints":[{"x":400,"y":400}]})
	await asyncio.sleep(0.03)
	await cdp.send("Input.dispatchTouchEvent", {"type":"touchEnd","touchPoints":[]})

async def tap_cdp_start_only_then_end(page, cdp):
	# same as Playwright but with explicit modifiers/timestamps absent; sanity duplicate of tap_pw
	await cdp.send("Input.dispatchTouchEvent", {"type":"touchStart","touchPoints":[{"x":400,"y":400}]})
	await cdp.send("Input.dispatchTouchEvent", {"type":"touchEnd","touchPoints":[]})

async def emulate_touch_from_mouse(page, cdp):
	await cdp.send("Input.emulateTouchFromMouseEvent", {"type":"mousePressed","x":400,"y":400,"button":"left","clickCount":1})
	await asyncio.sleep(0.03)
	await cdp.send("Input.emulateTouchFromMouseEvent", {"type":"mouseReleased","x":400,"y":400,"button":"left","clickCount":1})

async def pen_cdp(page, cdp):
	await cdp.send("Input.dispatchMouseEvent", {"type":"mousePressed","x":400,"y":400,"button":"left","clickCount":1,"pointerType":"pen"})
	await cdp.send("Input.dispatchMouseEvent", {"type":"mouseReleased","x":400,"y":400,"button":"left","clickCount":1,"pointerType":"pen"})

async def main():
	app = aiohttp.web.Application()
	app.router.add_get("/", page_handler); app.router.add_get("/ws", ws)
	runner = aiohttp.web.AppRunner(app); await runner.setup()
	await aiohttp.web.TCPSite(runner, "127.0.0.1", PORT).start()
	async with playwright.async_api.async_playwright() as p:
		browser = await p.chromium.launch(headless=True)
		print("UA:", await (await (await browser.new_context()).new_page()).evaluate("navigator.userAgent"))
		await run_case(browser, "A playwright touchscreen.tap", True, tap_pw)
		await run_case(browser, "B CDP dispatchTouchEvent start, 30ms, end", True, tap_cdp_split)
		await run_case(browser, "C CDP dispatchTouchEvent start+end back to back", True, tap_cdp_start_only_then_end)
		await run_case(browser, "D CDP emulateTouchFromMouseEvent", True, emulate_touch_from_mouse)
		await run_case(browser, "E playwright mouse.click, has_touch=True", True, click_pw)
		await run_case(browser, "F playwright mouse.click, has_touch=False", False, click_pw)
		await run_case(browser, "G CDP mouse with pointerType pen", False, pen_cdp)
		await browser.close()
	await runner.cleanup()

asyncio.run(main())
