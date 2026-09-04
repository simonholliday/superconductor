"""Measurement prototype (not house style): drives bench.html in headless Firefox (Playwright build) and prints frame statistics."""
import asyncio, json, statistics, sys, pathlib, http.server, threading, functools, os
import playwright.async_api as pa

HERE = pathlib.Path(__file__).parent
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(HERE / ".pw-browsers")

def serve(port):
	handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(HERE))
	handler.log_message = lambda *a, **k: None
	srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
	threading.Thread(target=srv.serve_forever, daemon=True).start()
	return srv

def pct(xs, p):
	xs = sorted(xs); k = int(round((len(xs) - 1) * p)); return xs[k]

async def run(techniques, cellsets, full_list, port, unthrottled):
	rows = []
	prefs = {}
	if unthrottled:
		prefs = {"layout.frame_rate": 1000, "privacy.reduceTimerPrecision": False}
	async with pa.async_playwright() as p:
		b = await p.firefox.launch(headless=True, firefox_user_prefs=prefs)
		ctx = await b.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
		page = await ctx.new_page()
		ver = b.version
		webgl = await page.evaluate("() => { const c=document.createElement('canvas'); const gl=c.getContext('webgl2'); if(!gl) return 'none'; const d=gl.getExtension('WEBGL_debug_renderer_info'); return d? gl.getParameter(d.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER); }")
		print(json.dumps({"browser": "firefox", "version": ver, "webgl": webgl, "unthrottled": unthrottled}), flush=True)
		for tech in techniques:
			for cells in cellsets:
				for full in full_list:
					url = f"http://127.0.0.1:{port}/bench.html?technique={tech}&cells={cells}&full={1 if full else 0}&frames=240&warm=30"
					await page.goto(url)
					await page.wait_for_function("window.__benchDone === true", timeout=120000)
					r = await page.evaluate("window.__benchResult")
					fm = r["frameMs"]; js = r["jsMs"]
					row = dict(mode="firefox-" + ("unthrottled" if unthrottled else "throttled"), technique=tech, cells=cells, full=full,
						fps=round(1000.0 / statistics.mean(fm), 1),
						frame_med=round(statistics.median(fm), 2), frame_p95=round(pct(fm, 0.95), 2), frame_max=round(max(fm), 2),
						js_med=round(statistics.median(js), 3), js_p95=round(pct(js, 0.95), 3))
					rows.append(row)
					print(json.dumps(row), flush=True)
		await b.close()
	return rows

if __name__ == "__main__":
	port = int(sys.argv[1])
	unthrottled = sys.argv[2] == "unthrottled"
	techs = ["dom", "domoverlay", "svg", "svgoverlay", "canvas", "canvasdirty", "webgl"]
	srv = serve(port)
	rows = asyncio.run(run(techs, [128, 1024], [False, True], port, unthrottled))
	(HERE / f"results_firefox_{sys.argv[2]}.json").write_text(json.dumps(rows, indent=1))
	srv.shutdown()
