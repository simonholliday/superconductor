"""Take everything the panel can see and write it somewhere that survives.

Every restart of a composition throws away every pattern edited on the glass,
because a pattern lives in ``composition.data`` and nothing writes it down
(Subroutine #2067).  That has cost real work three times in one session, and it
will keep costing it until #2067 is settled — so until then, run this before
restarting anything.

    python tools/capture_state.py [where-to-write.json]

Defaults to /home/si/superconductor-state.json, which is on disk rather than in
tmpfs and so survives a reboot as well as a restart.
"""

import asyncio
import json
import pathlib
import sys
import time

import websockets.asyncio.client

import superconductor.protocol


URL = "ws://127.0.0.1:8090/ws/panel"
WHERE = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/home/si/superconductor-state.json")


async def main () -> None:
	"""Join as a panel, keep the first snapshot of every app, and write it out."""

	held: dict[str, dict] = {}

	async with websockets.asyncio.client.connect(URL) as socket:
		# Built rather than spelled out, so it cannot go stale. Three tools wrote
		# the contract by hand and drifted three separate ways — two said 1.1.0
		# and two said 1.5.0 against a current 1.13.0 — while CLAUDE.md's own
		# advice for spotting a stale process is to read the contract off a
		# socket. Nothing checks it today, which is exactly why it drifted.
		await socket.send(superconductor.protocol.encode(
			superconductor.protocol.hello("capture", None)))

		deadline = time.monotonic() + 5

		while time.monotonic() < deadline:
			try:
				frame = json.loads(await asyncio.wait_for(socket.recv(), timeout=1.0))

			except asyncio.TimeoutError:
				break

			if frame["t"] == "snapshot":
				held[frame["app"]] = frame["state"]

	# Stamped with the contract it was taken under, because what a note's two
	# numbers are counted in changed at 1.12.0 and a file cannot say which it
	# means by looking at it: a note at 12 is step 12 in one and two steps in
	# the other, and both are patterns a person might have played. A file
	# without this line is older than the stamp and restore_state.py converts
	# it (contract 1.12.0).
	WHERE.write_text(json.dumps(
		{"contract": superconductor.protocol.CONTRACT_VERSION, "apps": held},
		indent="\t") + "\n")

	for app, state in held.items():
		for control, value in state.items():
			if isinstance(value, dict):
				filled = sum(1 for held_row in value.values() if held_row)
				print(f"  {app}/{control}: {filled} rows or fields with something in them")

	print(f"written to {WHERE}")


asyncio.run(main())
