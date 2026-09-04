"""Render the coalescing benchmark rows as Markdown.  Prototype."""

import json
import sys

NAMES = {
	"baseline": "Baseline, nothing else in the process",
	"ws-thread": "B without coalescing: `call_soon_threadsafe` per message",
	"ws-coalesce": "B as recommended: queued, drain scheduled only when none pending",
	"ws-drain-beat": "A: queued, drained in the `beat` listener",
}

rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]

def rating (mean_ms):
	"""The benchmark's own qualitative scale, which it applies to the MEAN
	(benchmarks/clock_jitter.py:131-141), not to a percentile."""
	if mean_ms < 0.1:
		return "Excellent"
	if mean_ms < 0.5:
		return "Very good"
	if mean_ms < 2.0:
		return "Good"
	if mean_ms < 5.0:
		return "Fair"
	return "Poor"


print("| Block | Shape | Traffic | Mean | Rating | Median | P95 | P99 | Max | >1 ms | Msgs | Wake-ups | Msgs/wake-up | Crossing median | Crossing p99 | Crossing max | applied |")
print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
for r in rows:
	w = r.get("wakeups", "-")
	mpw = r.get("msgs_per_wakeup", "-")
	print("| {tag} | {name} | {tr} | {mean} | {rat} | {med} | {p95} | {p99} | {mx} | {ov} | {inb} | {w} | {mpw} | {cm} | {cp} | {cx} | {ap} |".format(
		tag=r.get("tag", ""), name=NAMES.get(r["scenario"], r["scenario"]), tr=r["traffic"],
		mean=r["mean_ms"], rat=rating(r["mean_ms"]),
		med=r["median_ms"], p95=r["p95_ms"], p99=r["p99_ms"], mx=r["max_ms"], ov=r["over_1ms"],
		inb=r["inbound"], w=w, mpw=mpw,
		cm=r.get("cross_median_ms", "-"), cp=r.get("cross_p99_ms", "-"), cx=r.get("cross_max_ms", "-"),
		ap=r["applied"]))

print()
print("Integrity check (applied == inbound, dropped == 0):")
for r in rows:
	if r["scenario"] == "baseline":
		continue
	ok = r["applied"] == r["inbound"] and r.get("dropped", 0) == 0
	if not ok:
		print("  MISMATCH", r["tag"], r["scenario"], r["traffic"], r["inbound"], r["applied"], r.get("dropped"))
print("  checked", sum(1 for r in rows if r["scenario"] != "baseline"), "rows")
