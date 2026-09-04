"""Research prototype (playhead), not house style: start pw_server.py, drive a headless browser
(Playwright; Chromium by default, PW_BROWSER=firefox for Firefox) through bench.html and print
JSON: rAF pacing and per-frame cost of moving a playhead highlight over 128 and 1024 cells in
three rendering modes, and NTP-style clock-offset estimation noise over a loopback WebSocket.
Headless: no display, no vsync, software compositor; figures are indicative only."""
import asyncio, json, os, socket, subprocess, sys, time
import playwright.async_api

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad/transport-ui/pw-browsers"
BROWSER = os.environ.get("PW_BROWSER", "chromium")


def wait_port (port, timeout=10):
	t0 = time.time()
	while time.time() - t0 < timeout:
		try:
			socket.create_connection(("127.0.0.1", port), timeout=0.2).close(); return
		except OSError:
			time.sleep(0.1)
	raise RuntimeError("server did not start")


async def main ():
	server = subprocess.Popen([sys.executable, os.path.join(HERE, "pw_server.py")])
	try:
		wait_port(8903)
		async with playwright.async_api.async_playwright() as pw:
			bt = getattr(pw, BROWSER)
			browser = await bt.launch(headless=True)
			page = await browser.new_page(viewport={"width": 1920, "height": 1080})
			await page.goto("http://127.0.0.1:8903/")
			ver = browser.version
			out = {"browser": BROWSER, "version": ver, "results": []}
			cases = []
			for rows, cols in ((8, 16), (16, 64)):
				for mode in ("dom", "overlay", "canvas"):
					for step in (0, 125):
						cases.append({"rows": rows, "cols": cols, "mode": mode, "stepMs": step, "seconds": 4})
			for c in cases:
				r = await page.evaluate("c => renderBench(c)", c)
				out["results"].append(r)
				print(json.dumps(r), flush=True)
			off = await page.evaluate("c => offsetBench(c)", {"n": 320, "gapMs": 20})
			out["offset"] = off
			print(json.dumps({"offset": off}), flush=True)
			await browser.close()
		with open(os.path.join(HERE, "results", f"pw_{BROWSER}.json"), "w") as f:
			json.dump(out, f, indent=1)
	finally:
		server.terminate(); server.wait()


asyncio.run(main())
