"""Research prototype: aggregate results.jsonl into Markdown tables."""

import collections
import json
import sys

rows = [json.loads(l) for l in open(sys.argv[1])]
MAIN = ("FunctionCall", "UpdateLayoutTree", "Layout", "PrePaint", "Paint", "Layerize", "Commit", "UpdateLayer")


def main_ms(r):
	t = r["trace_ms_per_frame"]
	return sum(t.get(k, 0) for k in MAIN)


groups = collections.defaultdict(list)
for r in rows:
	key = (r["throttle"], r["tech"], r["cells"] if not r["tech"].startswith("wave") else r["waves"], r["toggles"])
	groups[key].append(r)

print("| throttle | technique | cells / waves | toggles per frame | init ms | DOM nodes | frame p95 ms | frame max ms | frames over 20 ms of 299 | script ms per frame | main-thread render ms per frame | raster ms per frame | GPU-process ms per frame |")
print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
for key in sorted(groups, key=lambda k: (k[0], k[2], k[3], k[1])):
	rs = groups[key]
	def avg(f):
		return sum(f(r) for r in rs) / len(rs)
	def rng(f):
		vals = [f(r) for r in rs]
		return f"{min(vals):.0f}" if len(vals) == 1 else f"{min(vals):.0f} to {max(vals):.0f}"
	r0 = rs[0]
	print(f"| {key[0]:g} | {key[1]} | {key[2]} | {key[3]} | {avg(lambda r: r['initMs']):.1f} | {r0['nodes']} | {avg(lambda r: r['interval']['p95']):.1f} | {rng(lambda r: r['interval']['max'])} | {rng(lambda r: r['interval']['over20ms'])} | {avg(lambda r: r['script']['mean']):.3f} | {avg(main_ms):.3f} | {avg(lambda r: r['trace_ms_per_frame'].get('RasterTask', 0)):.3f} | {avg(lambda r: r['trace_ms_per_frame'].get('GPUTask', 0)):.3f} |")
print()
print("chromium:", rows[0]["chromium"], " runs:", len(rows))
