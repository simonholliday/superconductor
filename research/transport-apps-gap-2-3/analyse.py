"""RESEARCH PROTOTYPE (2026-09-03), not house style.

Pairs each arm row in a gap23 jsonl with the no-adapter baseline row that ran
immediately before it, and prints the columns the point asks for: late-pulse
count and p99 per burst size for each crossing shape, beside its paired
baseline, with the load stamped at the start and end of both.

Usage: analyse.py results/gap23_G.jsonl [more.jsonl ...]
"""

import json
import sys


def rows (paths):
	out = []
	for p in paths:
		for line in open(p):
			line = line.strip()
			if line:
				out.append(json.loads(line))
	return out


def drift (r):
	try:
		return abs(float(r["loadavg_end"]) - float(r["loadavg_start"]))
	except (ValueError, KeyError):
		return -1.0


def fmt (r):
	return (f"{r['scenario']:<14} {r['traffic']:<22} spin={r['spin_ms']:<4} sel={r['selector']:<7} "
	        f"p99={r['p99_ms']:>8.4f} max={r['max_ms']:>8.4f} over1ms={r['over_1ms']:>4} "
	        f"in={r.get('inbound', 0):>5} wk={r.get('wakeups', 0):>5} "
	        f"bmax={r.get('batch_max', 0):>5} bmean={r.get('batch_mean_nonempty', 0):>8} "
	        f"xmed={r.get('cross_median_ms', 0):>8} xp99={r.get('cross_p99_ms', 0):>8} "
	        f"xmax={r.get('cross_max_ms', 0):>8} load={r.get('loadavg_start', '?')}->{r.get('loadavg_end', '?')}")


def main ():
	rs = rows(sys.argv[1:])
	base = None
	for r in rs:
		if r["scenario"] == "baseline":
			base = r
			print("BASE  " + fmt(r))
			continue
		print("  ARM  " + fmt(r))
		if base is not None:
			print(f"       paired baseline: p99={base['p99_ms']:.4f} max={base['max_ms']:.4f} "
			      f"over1ms={base['over_1ms']}  |  arm minus baseline: "
			      f"dp99={r['p99_ms'] - base['p99_ms']:+.4f} dover1ms={r['over_1ms'] - base['over_1ms']:+d}")
		print(f"       load drift baseline {drift(base) if base else -1:.2f}, arm {drift(r):.2f}")
		print()


if __name__ == "__main__":
	main()
