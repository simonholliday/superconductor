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
import typing

import websockets.asyncio.client

import superconductor.protocol


URL = "ws://127.0.0.1:8090/ws/panel"
WHERE = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/home/si/superconductor-state.json")


DERIVED: frozenset[str] = frozenset({"labels", "unreachable"})
"""Fields an app works out for itself, which a restore must not try to put back.

A snapshot carries them because a panel arriving late has no other way to learn
them — what each row is called once a pattern is transposed, and which rows have
stopped sounding.  But they are **consequences of `transpose` rather than values
in their own right**, so replaying them is at best redundant and at worst wrong:
the app refuses the path, and `labels` is a dict of rows that this walker would
otherwise take apart into steps that do not exist.

Restoring the offset regenerates both, which is why skipping them loses nothing.

**This is a list of names and lists of names go stale**, so it is the thing to
check when a restore starts nacking after a contract change.  The better fix is
for a declaration to say which of its fields are derived; that does not exist yet
and is not worth inventing for two.
"""


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
			if key in DERIVED:
				continue

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


def _read () -> tuple[dict, bool]:
	"""What was written down, and whether it says which contract it was written
	under.

	A file from before 1.12.0 is the bare mapping of app to state; one from
	after carries that under ``apps`` beside a ``contract``.  The two are told
	apart by shape, which is safe because an app has never been called
	``apps``.
	"""

	held = json.loads(WHERE.read_text())

	if isinstance(held.get("apps"), dict) and "contract" in held:
		return held["apps"], True

	return held, False


def _converted (state: dict, declarations: dict) -> int:
	"""Bring a pre-1.12.0 snapshot up to the grid resolutions in force now.

	**A note's position and its length used to be counted in steps and are now
	counted in the grid's own positions**, of which a step holds ``divisions``.
	Replayed unconverted the numbers are all still legal and all still look like
	a pattern, which is exactly what makes this worth doing rather than
	detecting: a bar would fold into its own first sixth, silently, and the only
	clue would be that it sounded wrong.

	Grids that kept one position to a step are unchanged, which is every grid
	that has not asked for more.
	"""

	moved = 0

	for control, held in state.items():
		declared = declarations.get(control) or {}
		divisions = declared.get("divisions", 1)

		if declared.get("type") != "note_grid" or divisions < 2 or not isinstance(held, dict):
			continue

		for row, notes in held.items():
			if not isinstance(notes, dict):
				continue

			held[row] = {
				str(int(step) * divisions): {
					**note,
					"length": int(note.get("length", 1)) * divisions,
				}
				for step, note in notes.items()
			}

			moved += len(held[row])

	return moved


async def main () -> None:
	"""Replay everything, then say what was refused."""

	held, stamped = _read()

	async with websockets.asyncio.client.connect(URL) as socket:
		# Built rather than spelled out, so it cannot go stale. Three tools wrote
		# the contract by hand and drifted three separate ways — two said 1.1.0
		# and two said 1.5.0 against a current 1.13.0 — while CLAUDE.md's own
		# advice for spotting a stale process is to read the contract off a
		# socket. Nothing checks it today, which is exactly why it drifted.
		await socket.send(superconductor.protocol.encode(
			superconductor.protocol.hello("restore", None)))

		# Read the manifest before sending anything, because converting an old
		# file needs the resolutions the apps are declaring right now — there is
		# nowhere else to learn them, and guessing would be the silent kind of
		# wrong this exists to avoid.
		manifest: dict[str, typing.Any] = {}
		deadline = time.monotonic() + 5

		while not manifest and time.monotonic() < deadline:
			try:
				frame = json.loads(await asyncio.wait_for(socket.recv(), timeout=1.0))

			except asyncio.TimeoutError:
				break

			if frame.get("t") == "manifest":
				manifest = frame.get("apps") or {}

		if not stamped:
			moved = sum((_converted(state, manifest.get(app) or {})
			             for app, state in held.items()), 0)

			if moved:
				print(f"{WHERE} predates contract 1.12.0: "
				      f"{moved} note(s) converted from steps to positions")

		asks = [ask for app, state in held.items() for ask in _sets(app, state)]

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
