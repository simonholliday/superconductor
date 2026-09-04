"""PROTOTYPE (research only). Renders a results JSONL as a Markdown table."""

import json
import sys


def frac (x):
	if x is None:
		return "-"
	if abs(x - 1 / 24) < 1e-9:
		return "1/24"
	if abs(x - 0.25) < 1e-9:
		return "1/4"
	if abs(x - 1.0) < 1e-9:
		return "1"
	return f"{x:g}"


def cell (d, key):
	return f"{d[key]:.3f}" if d else "-"


rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
mode = sys.argv[2] if len(sys.argv) > 2 else "jitter"

if mode == "jitter":
	print("| Run | Lookahead | Notes/cycle | Rebuilds | Median | P95 | P99 | Max | Pulses over 1 ms | Jitter on the rebuild pulse (med/max) | Load |")
	print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
	for r in rows:
		a = r["jitter_at_rebuild_ms"]
		at = f"{a['median']:.3f} / {a['max']:.3f}" if a else "-"
		print(f"| {r['label']} | {frac(r['lookahead'])} | {r['notes_per_cycle']} | {r['rebuilds']} | "
		      f"{r['median_ms']:.3f} ms | {r['p95_ms']:.3f} ms | {r['p99_ms']:.3f} ms | {r['max_ms']:.3f} ms | "
		      f"{r['over_1ms']} of {r['pulses_logged']} | {at} | {r['load_at_start']} |")
else:
	print("| Run | Lookahead | Notes/cycle | Rebuilds | on_reschedule med/max us | schedule_pattern med/max us | whole block med/max us | block as % of a 20.833 ms pulse |")
	print("| --- | --- | --- | --- | --- | --- | --- | --- |")
	for r in rows:
		rb, q, b = r["rebuild_us"], r["queue_us"], r["block_us"]
		pct = f"{b['median'] / 20833.0 * 100:.1f}% / {b['max'] / 20833.0 * 100:.1f}%" if b else "-"
		print(f"| {r['label']} | {frac(r['lookahead'])} | {r['notes_per_cycle']} | {r['rebuilds']} | "
		      f"{cell(rb,'median')} / {cell(rb,'max')} | {cell(q,'median')} / {cell(q,'max')} | "
		      f"{cell(b,'median')} / {cell(b,'max')} | {pct} |")
