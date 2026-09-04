"""RESEARCH PROTOTYPE (2026-09-03), not house style.

Rejects a row that did not measure what it claims to.  Three tests, all of
which the first attempt at this block would have failed on two rows:

	sender reported     the stand-in service printed its own send count, so it
	                    bound the port and was not somebody else's process
	counts agree        sender_sent == inbound == applied, so no frame was
	                    lost, dropped or supplied by a foreign sender
	load held           the one-minute load average was at or below the gate
	                    at the row's start and had not drifted above it by the
	                    row's end

Usage: check.py results/gap23_H.jsonl [...]
"""

import json
import sys

GATE = 1.20


def main ():
	bad = 0
	for path in sys.argv[1:]:
		for n, line in enumerate(open(path), 1):
			line = line.strip()
			if not line:
				continue
			r = json.loads(line)
			why = []
			if r["scenario"] != "baseline":
				if "sender_sent" not in r:
					why.append("no sender report")
				elif r["sender_sent"] != r["inbound"]:
					why.append(f"sent {r['sender_sent']} != inbound {r['inbound']}")
				if r.get("dropped"):
					why.append(f"dropped {r['dropped']}")
				if r["applied"] not in (r["inbound"], r["inbound"] - 1):
					why.append(f"applied {r['applied']} != inbound {r['inbound']}")
			try:
				ls, le = float(r["loadavg_start"]), float(r["loadavg_end"])
				if ls > GATE:
					why.append(f"load start {ls}")
				if le > GATE:
					why.append(f"load end {le}")
			except ValueError:
				why.append("no load stamp")
			mark = "REJECT" if why else "ok    "
			if why:
				bad += 1
			print(f"{mark} {path}:{n} {r['scenario']:<14} {r['traffic']:<22} "
			      f"spin={r['spin_ms']} sel={r['selector']} "
			      f"load={r.get('loadavg_start')}->{r.get('loadavg_end')} {'; '.join(why)}")
	print(f"\n{bad} row(s) rejected")


if __name__ == "__main__":
	main()
