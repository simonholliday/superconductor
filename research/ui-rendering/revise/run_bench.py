"""Research prototype: drive bench.html in headless Chromium and print frame-time statistics.

Not house style; measurement scaffolding only.
"""

import json
import pathlib
import sys

import playwright.sync_api

HERE = pathlib.Path(__file__).parent
PAGE = (HERE / "bench.html").resolve().as_uri()
CHROME = "/home/si/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"


def run(throttle: float, gpu_args: list[str], label: str, frames: int = 300) -> list[dict]:
	out: list[dict] = []
	with playwright.sync_api.sync_playwright() as p:
		browser = p.chromium.launch(executable_path=CHROME, headless=True, args=["--window-size=1920,1080", *gpu_args])
		page = browser.new_page(viewport={"width": 1920, "height": 1080})
		page.goto(PAGE)
		cdp = page.context.new_cdp_session(page)
		if throttle > 1:
			cdp.send("Emulation.setCPUThrottlingRate", {"rate": throttle})
		info = page.evaluate("""() => { const c = document.createElement('canvas'); const gl = c.getContext('webgl2'); if (!gl) return 'no webgl2'; const d = gl.getExtension('WEBGL_debug_renderer_info'); return d ? gl.getParameter(d.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER); }""")
		out.append({"label": label, "throttle": throttle, "webgl_renderer": info, "ua": page.evaluate("navigator.userAgent")})
		for tech in ("dom", "svg", "canvas", "webgl"):
			for cells in (128, 1024):
				for mode in ("incremental", "full"):
					try:
						r = page.evaluate("([t,c,m,f]) => window.runBench(t,c,m,f)", [tech, cells, mode, frames])
						r["label"] = label
						out.append(r)
						if tech in ("dom", "svg"):
							r2 = page.evaluate("([t,c,m,f]) => window.runBenchSync(t,c,m,f)", [tech, cells, mode, frames])
							r2["label"] = label
							out.append(r2)
					except Exception as exc:  # noqa: BLE001
						out.append({"label": label, "tech": tech, "cells": cells, "mode": mode, "error": str(exc)[:200]})
		for tech in ("svg", "canvas"):
			r = page.evaluate("([t,f]) => window.runWave(t,f)", [tech, frames]); r["label"] = label; out.append(r)
		r = page.evaluate("(f) => window.runPage(f)", frames); r["label"] = label; out.append(r)
		browser.close()
	return out


if __name__ == "__main__":
	throttle = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
	label = sys.argv[2] if len(sys.argv) > 2 else "desktop"
	gpu = sys.argv[3].split() if len(sys.argv) > 3 else []
	results = run(throttle, gpu, label)
	(HERE / f"results_{label}.json").write_text(json.dumps(results, indent=1))
	for r in results:
		if "scenario" in r:
			print(f"{r['label']:>10} {r.get('tech','-'):>6} {r['scenario']:>40}  js mean {r['js']['mean']:7.3f} p95 {r['js']['p95']:7.3f} max {r['js']['max']:7.3f} ms | interval mean {r['interval']['mean']:6.2f} p95 {r['interval']['p95']:6.2f} max {r['interval']['max']:6.2f} ms | long {r['longFrames']}")
		elif "js" in r:
			print(f"{r['label']:>10} {r['tech']:>6} {r['cells']:>5} {r['mode']:>12}  js mean {r['js']['mean']:7.3f} p95 {r['js']['p95']:7.3f} max {r['js']['max']:7.3f} ms | interval mean {r['interval']['mean']:6.2f} p95 {r['interval']['p95']:6.2f} max {r['interval']['max']:6.2f} ms | long {r['longFrames']}")
		elif "jsPlusLayout" in r:
			s = r["jsPlusLayout"]
			print(f"{r['label']:>10} {r['tech']:>6} {r['cells']:>5} {r['mode']:>12}  js+style+layout mean {s['mean']:7.3f} p95 {s['p95']:7.3f} max {s['max']:7.3f} ms")
		else:
			print(r)
