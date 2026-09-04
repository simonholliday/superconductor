"""RESEARCH PROTOTYPE (2026-09-03), not house style.

A thin entry point around scratchpad/transport-apps-gap-1-2/ws_coalesce_bench2.py,
which is imported and used unmodified.  It changes exactly one thing: the
loopback port the stand-in service listens on, which is
adapter_bench.WS_PORT = 9114 in the filed harness and is taken from
GAP23_PORT here.

Why: the first attempt at this block found port 9114 already bound by another
process on this shared workstation, twice in five arm rows.  The row's own
sender then died at bind and its client attached to whatever else was on the
port, so the row measured somebody else's traffic.  Both failures are visible
in results/run_G.log as `OSError: [Errno 98] ... 9114` with `sender_sent`
absent from the row.  Nothing else about the instrument is altered: the same
Sequencer, the same adapters, the same statistics, the same venv.

The sender is respawned from this file rather than from ws_coalesce_bench2.py
so that the child process reads GAP23_PORT too.

Usage: identical to ws_coalesce_bench2.py.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad/transport-apps-gap-1-2")
sys.path.insert(0, os.environ["ADAPTER_BENCH_DIR"])

import adapter_bench as ab

ab.WS_PORT = int(os.environ.get("GAP23_PORT", "9214"))

import ws_coalesce_bench as wcb
import ws_coalesce_bench2 as b2


def spawn_sender (rate: float, seconds: float, burst: int, burst_period: float):
	"""As wcb.spawn_sender, but re-entering this file so GAP23_PORT is read."""
	return subprocess.Popen(
		[sys.executable, os.path.abspath(__file__), "--send", "--rate", str(rate),
		 "--seconds", str(seconds), "--burst", str(burst), "--burst-period", str(burst_period)],
		stdout=subprocess.PIPE, text=True)


wcb.spawn_sender = spawn_sender


if __name__ == "__main__":
	b2.main()
