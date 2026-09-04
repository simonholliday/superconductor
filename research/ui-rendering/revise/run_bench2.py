"""Reviser prototype (not house style): serve bench2.html locally and drive it in headless Chromium at several CPU throttle rates."""
import functools, http.server, json, pathlib, sys, threading
import playwright.sync_api

HERE = pathlib.Path(__file__).parent
CHROME = "/home/si/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
SCEN = ["dom_same", "dom_invert", "dom_snapshot", "dom_inc_class", "dom_inc_overlay", "svg_invert", "svg_snapshot", "canvas_invert", "canvas_inc", "preact_full"]

def serve():
	handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(HERE))
	handler.log_message = lambda *a, **k: None
	srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
	threading.Thread(target=srv.serve_forever, daemon=True).start()
	return srv

def main(rates, gpu_args, label):
	srv = serve(); port = srv.server_address[1]
	out = []
	with playwright.sync_api.sync_playwright() as p:
		b = p.chromium.launch(executable_path=CHROME, headless=True, args=["--window-size=1920,1080", *gpu_args])
		page = b.new_page(viewport={"width": 1920, "height": 1080})
		page.goto(f"http://127.0.0.1:{port}/bench2.html")
		page.wait_for_function("window.__ready === true", timeout=60000)
		cdp = page.context.new_cdp_session(page)
		info = page.evaluate("""() => { const c = document.createElement('canvas'); const gl = c.getContext('webgl2'); if (!gl) return 'no webgl2'; const d = gl.getExtension('WEBGL_debug_renderer_info'); return d ? gl.getParameter(d.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER); }""")
		out.append({"label": label, "webgl_renderer": info, "ua": page.evaluate("navigator.userAgent")})
		print(out[0], flush=True)
		for rate in rates:
			cdp.send("Emulation.setCPUThrottlingRate", {"rate": rate})
			for name in SCEN:
				try:
					r = page.evaluate("([n]) => window.runScenario(n)", [name])
					r["rate"] = rate; r["label"] = label
					out.append(r)
					s = r["js"]; g = r["interval"]
					print(f"{label:>8} rate {rate:>2} {name:>20} {r['change']:>8}  js+sl mean {s['mean']:7.3f} p50 {s['p50']:6.2f} p95 {s['p95']:6.2f} max {s['max']:6.2f} ms | interval mean {g['mean']:6.2f} p95 {g['p95']:6.2f} max {g['max']:6.2f} | long {r['longFrames']}", flush=True)
				except Exception as exc:  # noqa: BLE001
					out.append({"label": label, "rate": rate, "scenario": name, "error": str(exc)[:300]})
					print(f"{label:>8} rate {rate:>2} {name:>20} ERROR {str(exc)[:200]}", flush=True)
		b.close()
	srv.shutdown()
	(HERE / f"results2_{label}.json").write_text(json.dumps(out, indent=1))

if __name__ == "__main__":
	label = sys.argv[1]
	rates = [float(x) for x in sys.argv[2].split(",")]
	gpu = sys.argv[3].split() if len(sys.argv) > 3 else []
	main(rates, gpu, label)
