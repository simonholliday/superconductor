"""Put back what capture_state.py wrote down, through the panel's own socket.

Every value is replayed as an ordinary `set`, which is what a finger would send:
the app applies it, confirms it, and every panel sees it. Nothing here reaches
into a composition, so a restore is exactly as legitimate as a tap.

    python tools/restore_state.py [what-to-read.json]

Pairs with capture_state.py and exists for the same reason: a pattern edited on
the glass does not survive a restart (Subroutine #2067).
"""

import asyncio
import json
import pathlib
import sys
import time

import websockets.asyncio.client


URL = "ws://127.0.0.1:8090/ws/panel"
WHERE = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/home/si/superintendent-state.json")


def _sets (app: str, state: dict) -> list[tuple[str, str, object]]:
	"""Every value in a snapshot, as the sets that would put it there.

	A note is placed before it is shaped, because a length written to a cell
	holding no note is refused — which is the app being right, not an obstacle.
	"""

	asks: list[tuple[str, str, object]] = []

	for control, held in (state or {}).items():
		if not isinstance(held, dict):
			continue

		for key, value in held.items():
			if isinstance(value, list) and all(isinstance(one, int) for one in value):
				for step in value:
					asks.append((app, f"{control}/{key}/{step}", True))

			elif isinstance(value, list):
				# A list that is not a list of step numbers is a value in its
				# own right — a stack of generators, whose order is part of
				# what it means — so it goes back whole rather than a member at
				# a time.  Sending it a member at a time produced paths with a
				# whole object where a step number belongs.
				asks.append((app, f"{control}/{key}", value))

			elif isinstance(value, dict):
				for step, note in value.items():
					asks.append((app, f"{control}/{key}/{step}", True))

					for field, amount in note.items():
						asks.append((app, f"{control}/{key}/{step}/{field}", amount))

			else:
				asks.append((app, f"{control}/{key}", value))

	return asks


async def main () -> None:
	"""Replay everything, then say what was refused."""

	held = json.loads(WHERE.read_text())

	asks = [ask for app, state in held.items() for ask in _sets(app, state)]

	async with websockets.asyncio.client.connect(URL) as socket:
		await socket.send(json.dumps({
			"t": "hello", "contract": "1.4.0", "client": "restore",
			"page": None, "ver": {}, "token": None}))

		for seq, (app, path, value) in enumerate(asks):
			await socket.send(json.dumps({
				"t": "set", "app": app, "path": path, "v": value, "seq": seq}))

		refused, deadline = [], time.monotonic() + 5

		while time.monotonic() < deadline:
			try:
				frame = json.loads(await asyncio.wait_for(socket.recv(), timeout=1.0))

			except asyncio.TimeoutError:
				break

			if frame["t"] == "nack":
				refused.append((frame.get("path"), frame.get("reason")))

	print(f"{len(asks)} values replayed from {WHERE}")

	for path, reason in refused:
		print(f"  refused {path}: {reason}")


asyncio.run(main())
