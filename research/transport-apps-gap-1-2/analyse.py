"""Saturation analysis: late pulses against messages and against wake-ups."""

import collections
import json
import statistics
import sys

rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]

print("Late pulses against traffic (epoll, 1 ms spin margin only)")
print()
print("| Shape | Traffic | Msgs | Msgs/pulse | Wake-ups | Msgs/wake-up | >1 ms of 1536 | Late per wake-up | P99 |")
print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
for r in rows:
	if r.get("selector") != "epoll" or r.get("spin_ms", 1.0) != 1.0:
		continue
	if r["scenario"] == "baseline":
		continue
	w = r.get("wakeups", 0)
	print("| {s} | {t} | {m} | {mp:.2f} | {w} | {mpw} | {ov} | {lpw} | {p99} |".format(
		s=r["scenario"], t=r["traffic"], m=r["inbound"], mp=r["inbound"] / max(r["pulses"], 1),
		w=w, mpw=r.get("msgs_per_wakeup", "-"), ov=r["over_1ms"],
		lpw=(round(r["over_1ms"] / w, 4) if w else "n/a"), p99=r["p99_ms"]))

print()
print("Repeatability: rows appearing in more than one block")
print()
key = lambda r: (r["scenario"], r["traffic"], r.get("selector", "epoll"), r.get("spin_ms", 1.0))
groups = collections.defaultdict(list)
for r in rows:
	groups[key(r)].append(r)
print("| Shape | Traffic | Selector | Spin | P99 per block | Max per block | >1 ms per block | Msgs/wake-up per block |")
print("| --- | --- | --- | --- | --- | --- | --- | --- |")
for k, g in groups.items():
	if len(g) < 2:
		continue
	print("| {s} | {t} | {sel} | {sp} ms | {p99} | {mx} | {ov} | {mpw} |".format(
		s=k[0], t=k[1], sel=k[2], sp=k[3],
		p99=", ".join(str(x["p99_ms"]) for x in g),
		mx=", ".join(str(x["max_ms"]) for x in g),
		ov=", ".join(str(x["over_1ms"]) for x in g),
		mpw=", ".join(str(x.get("msgs_per_wakeup", "-")) for x in g)))

print()
print("Levers (25 and 50 Hz steady only)")
print()
print("| Shape | Traffic | Selector | Spin | P99 | Max | >1 ms | Crossing p99 |")
print("| --- | --- | --- | --- | --- | --- | --- | --- |")
for r in rows:
	if r.get("selector") == "epoll" and r.get("spin_ms", 1.0) == 1.0:
		continue
	print("| {s} | {t} | {sel} | {sp} ms | {p99} | {mx} | {ov} | {cp} |".format(
		s=r["scenario"], t=r["traffic"], sel=r.get("selector"), sp=r.get("spin_ms"),
		p99=r["p99_ms"], mx=r["max_ms"], ov=r["over_1ms"], cp=r.get("cross_p99_ms", "-")))

print()
print("Baselines by block:", [(r["tag"], r.get("selector"), r.get("spin_ms"), r["p99_ms"], r["max_ms"], r["over_1ms"], r.get("loadavg_start"), r.get("loadavg_end")) for r in rows if r["scenario"] == "baseline"])
