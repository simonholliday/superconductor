"""RESEARCH PROTOTYPE (2026-09-04), not house style.

Renders results/lostgap.jsonl as the rows the finding quotes.
"""

import json
import sys

NAMES = {
	"baseline": "Baseline, nothing in the process",
	"ws-thread": "Per message",
	"ws-coalesce": "Pending flag",
	"ws-batch-read": "Batched at the socket read",
	"ws-drain-beat": "Drained at `beat`",
	"ws-direct": "Off the loop, no crossing",
}


def traffic (r) -> str:
	if r["burst"]:
		return f"{r['burst']} every {r['burst_period']}s"
	if r["rate_hz"]:
		return f"{r['rate_hz']:.0f} Hz"
	return "none"


def lever (r) -> str:
	bits = []
	if r["spin_ms"] != 1.0:
		bits.append(f"spin {r['spin_ms']} ms")
	if r.get("selector") != "epoll":
		bits.append(r.get("selector"))
	return ", ".join(bits) or "-"


def main () -> None:
	path = sys.argv[1] if len(sys.argv) > 1 else "results/lostgap.jsonl"
	print("| Blk | Shape | Traffic | Lever | Msgs | Wake-ups | Largest batch | Mean | P99 | Max | >1ms /1536 | Cross med | Cross p99 | Cross max | Load |")
	print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
	for line in open(path):
		line = line.strip()
		if not line:
			continue
		r = json.loads(line)
		wk = r.get("wakeups", "-")
		bm = r.get("batch_max", "-")
		print("| {tag} | {name} | {tr} | {lv} | {msgs} | {wk} | {bm} | {mean} | {p99} | {mx} | {over} | {cm} | {cp} | {cx} | {ls}-{le} |".format(
			tag=r["tag"], name=NAMES.get(r["scenario"], r["scenario"]), tr=traffic(r), lv=lever(r),
			msgs=r["inbound"], wk=wk, bm=bm,
			mean=r["mean_ms"], p99=r["p99_ms"], mx=r["max_ms"], over=r["over_1ms"],
			cm=r.get("cross_median_ms", "-"), cp=r.get("cross_p99_ms", "-"), cx=r.get("cross_max_ms", "-"),
			ls=r.get("loadavg_start", "?"), le=r.get("loadavg_end", "?")))
		if r.get("dropped"):
			print(f"    !! dropped {r['dropped']}")
		if r["inbound"] != r["applied"]:
			print(f"    note inbound {r['inbound']} applied {r['applied']}")


if __name__ == "__main__":
	main()
