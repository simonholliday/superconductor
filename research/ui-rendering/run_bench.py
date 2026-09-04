"""Research prototype (not house style): drive bench.html in headless Chromium and record frame statistics.

Usage: run_bench.py <out.jsonl> [throttle_rate] [configs...]
Each config is a query string like "tech=dom-class&cols=16&rows=8&toggles=0".
"""

import collections
import json
import pathlib
import sys
import time

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
URL = (HERE / "bench.html").as_uri()

TRACE_CATS = [
	"devtools.timeline",
	"disabled-by-default-devtools.timeline",
	"disabled-by-default-devtools.timeline.frame",
]
INTERESTING = {"FunctionCall", "UpdateLayoutTree", "Layout", "PrePaint", "Paint", "Layerize", "Commit", "RasterTask", "DrawFrame", "UpdateLayer", "CompositeLayers", "HitTest", "ImageDecodeTask", "GPUTask", "BeginMainThreadFrame", "Animation"}


def run_one(browser, query, throttle):
	ctx = browser.new_context(viewport={"width": 1600, "height": 900})
	page = ctx.new_page()
	cdp = ctx.new_cdp_session(page)
	if throttle and throttle > 1:
		cdp.send("Emulation.setCPUThrottlingRate", {"rate": throttle})
	events = []
	done = {"flag": False}
	cdp.on("Tracing.dataCollected", lambda e: events.extend(e.get("value", [])))
	cdp.on("Tracing.tracingComplete", lambda e: done.__setitem__("flag", True))
	cdp.send("Tracing.start", {"traceConfig": {"includedCategories": TRACE_CATS, "recordMode": "recordContinuously"}, "transferMode": "ReportEvents"})
	page.goto(URL + "?" + query)
	page.wait_for_function("window.__done !== null", timeout=180000)
	result = page.evaluate("window.__done")
	cdp.send("Tracing.end")
	t_end = time.time()
	while not done["flag"] and time.time() - t_end < 30:
		page.wait_for_timeout(100)
	by_name = collections.defaultdict(float)
	counts = collections.Counter()
	for ev in events:
		if ev.get("ph") == "X" and ev.get("name") in INTERESTING:
			by_name[ev["name"]] += ev.get("dur", 0) / 1000.0
			counts[ev["name"]] += 1
	frames = result["frames"]
	result["trace_ms_per_frame"] = {k: round(v / frames, 3) for k, v in sorted(by_name.items())}
	result["trace_counts"] = dict(counts)
	result["throttle"] = throttle
	ctx.close()
	return result


def main():
	out = pathlib.Path(sys.argv[1])
	throttle = float(sys.argv[2]) if len(sys.argv) > 2 else 1
	configs = sys.argv[3:]
	with sync_playwright() as p:
		browser = p.chromium.launch(channel="chromium", args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
		ver = browser.version
		with out.open("a") as fh:
			for q in configs:
				r = run_one(browser, q, throttle)
				r["chromium"] = ver
				fh.write(json.dumps(r) + "\n")
				fh.flush()
				iv = r["interval"]
				print(f"{r['tech']:13s} {r['cells']:5d} cells tog={r['toggles']:2d} thr={throttle:g}  int mean={iv['mean']:.2f} p95={iv['p95']:.2f} max={iv['max']:.1f} >20ms={iv['over20ms']:3d}  script mean={r['script']['mean']:.3f} p95={r['script']['p95']:.3f}  trace={r['trace_ms_per_frame']}", flush=True)
		browser.close()


if __name__ == "__main__":
	main()
