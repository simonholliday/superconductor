"""Take everything the panel can see and write it somewhere that survives.

Every restart of a composition throws away every pattern edited on the glass,
because a pattern lives in ``composition.data`` and nothing writes it down
(Subroutine #2067).  That has cost real work three times in one session, and it
will keep costing it until #2067 is settled — so until then, run this before
restarting anything.

    python tools/capture_state.py [where-to-write.json]

Defaults to /home/si/superintendent-state.json, which is on disk rather than in
tmpfs and so survives a reboot as well as a restart.
"""

import asyncio
import json
import pathlib
import sys
import time

import websockets.asyncio.client


URL = "ws://127.0.0.1:8090/ws/panel"
WHERE = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/home/si/superintendent-state.json")


async def main () -> None:
	"""Join as a panel, keep the first snapshot of every app, and write it out."""

	held: dict[str, dict] = {}

	async with websockets.asyncio.client.connect(URL) as socket:
		await socket.send(json.dumps({
			"t": "hello", "contract": "1.4.0", "client": "capture",
			"page": None, "ver": {}, "token": None}))

		deadline = time.monotonic() + 5

		while time.monotonic() < deadline:
			try:
				frame = json.loads(await asyncio.wait_for(socket.recv(), timeout=1.0))

			except asyncio.TimeoutError:
				break

			if frame["t"] == "snapshot":
				held[frame["app"]] = frame["state"]

	WHERE.write_text(json.dumps(held, indent="\t") + "\n")

	for app, state in held.items():
		for control, value in state.items():
			if isinstance(value, dict):
				filled = sum(1 for held_row in value.values() if held_row)
				print(f"  {app}/{control}: {filled} rows or fields with something in them")

	print(f"written to {WHERE}")


asyncio.run(main())
