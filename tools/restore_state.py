"""Put back what capture_state.py wrote down, through the panel's own socket.

Every value is replayed as an ordinary `set`, which is what a finger would send:
the app applies it, confirms it, and every panel sees it. Nothing here reaches
into a composition, so a restore is exactly as legitimate as a tap.

    python tools/restore_state.py [what-to-read.json]

Pairs with capture_state.py and exists for the same reason: a pattern edited on
the glass does not survive a restart (Subroutine #2067).  Since #2487 a
composition may keep what is made on it by itself, and then these two are the
safety net rather than the routine.

**A grid goes back exactly** (#2465).  It is replayed as one whole-grid write,
which is how a grid is cleared, so a step the composition seeds on every start
and somebody had taken out stays out.  It used to be replayed a cell at a time,
which can only add: a clap came back at 10:54 on 2026-09-11 and five cells at
12:05, each with a clean summary, because nothing had been refused.
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
WHERE = pathlib.Path("/home/si/superconductor-state.json")
"""Where a capture is read from when nothing else is named."""


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

GRIDS: tuple[str, ...] = ("step_grid", "note_grid")
"""The kinds whose state is rows, which go back whole — the pair the client calls GRIDS."""

BESIDE_THE_ROWS: frozenset[str] = frozenset({"enabled", "transpose"}) | DERIVED
"""What a grid's snapshot holds beside its rows, which a whole-grid write does not carry."""


def _sets (app: str, state: dict, declared: dict) -> list[tuple[str, str, object]]:
	"""Every value in a snapshot, as the sets that would put it back.

	*declared* is what the app declares right now, by control, and is what says
	which controls are grids.

	- **A grid is one write of all its rows**, which replaces what it holds —
	  seeded steps included — and then its mute and transposition on their own.
	- **A rack goes first**: the grids it made exist only once it has made them,
	  and a stack may route from one.
	- **Anything else is walked a value at a time**, as every control used to be.
	  That includes a grid the manifest does not describe yet — one a rack is
	  about to make — which comes back exactly anyway, because it starts empty.
	"""

	asks: list[tuple[str, str, object]] = []

	racks_first = sorted(state, key=lambda control: (declared.get(control) or {}).get("type") != "grids")

	for control in racks_first:
		held = state[control]

		if not isinstance(held, dict):
			continue

		if (declared.get(control) or {}).get("type") in GRIDS:
			asks.append((app, f"{control}/rows",
			             {row: value for row, value in held.items() if row not in BESIDE_THE_ROWS}))
			asks.extend((app, f"{control}/{field}", held[field])
			            for field in ("enabled", "transpose") if field in held)
			continue

		asks.extend(_walked(app, control, held))

	return asks


def _walked (app: str, control: str, held: dict) -> list[tuple[str, str, object]]:
	"""One control's values, each as the set that would put it there.

	A note is placed before it is shaped, because a length written to a cell
	holding no note is refused — which is the app being right, not an obstacle.
	"""

	asks: list[tuple[str, str, object]] = []

	for key, value in held.items():
		if key in DERIVED:
			continue

		if isinstance(value, list) and all(isinstance(one, int) for one in value):
			for step in value:
				asks.append((app, f"{control}/{key}/{step}", True))

		elif isinstance(value, list):
			# A list that is not a list of step numbers is a value in its own
			# right — a stack of generators, whose order is part of what it
			# means — so it goes back whole rather than a member at a time.
			# Sending it a member at a time produced paths with a whole object
			# where a step number belongs.
			asks.append((app, f"{control}/{key}", value))

		elif isinstance(value, dict):
			for step, note in value.items():
				asks.append((app, f"{control}/{key}/{step}", True))

				for field, amount in note.items():
					asks.append((app, f"{control}/{key}/{step}/{field}", amount))

		else:
			asks.append((app, f"{control}/{key}", value))

	return asks


def _taken_out (captured: dict, live: dict, declared: dict) -> list[str]:
	"""Every cell a grid holds now and the capture does not: what a restore takes out.

	**Only grids the capture holds.**  A grid made since the capture was taken is
	left exactly as it is rather than emptied, because the capture knows nothing
	about it — which is #2465's second caution.
	"""

	gone: list[str] = []

	for control, held in captured.items():
		if (declared.get(control) or {}).get("type") not in GRIDS or not isinstance(held, dict):
			continue

		for row, now in (live.get(control) or {}).items():
			if row in BESIDE_THE_ROWS or not now:
				continue

			kept = held.get(row) or []
			gone.extend(f"{control}/{row}/{step}" for step in now if step not in kept)

	return gone


def _read (where: pathlib.Path) -> tuple[dict, bool]:
	"""What was written down, and whether it says which contract it was written
	under.

	A file from before 1.12.0 is the bare mapping of app to state; one from
	after carries that under ``apps`` beside a ``contract``.  The two are told
	apart by shape, which is safe because an app has never been called
	``apps``.
	"""

	held = json.loads(where.read_text())

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
	"""Replay everything, then say what was taken out and what was refused."""

	where = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else WHERE
	held, stamped = _read(where)

	async with websockets.asyncio.client.connect(URL) as socket:
		# Built rather than spelled out, so it cannot go stale. Three tools wrote
		# the contract by hand and drifted three separate ways — two said 1.1.0
		# and two said 1.5.0 against a current 1.13.0 — while CLAUDE.md's own
		# advice for spotting a stale process is to read the contract off a
		# socket. Nothing checks it today, which is exactly why it drifted.
		await socket.send(superconductor.protocol.encode(
			superconductor.protocol.hello("restore", None)))

		# The manifest, and then each app's snapshot, which is what the service
		# greets a panel with: the first says what every control *is* — which is
		# how a grid is told from anything else, and what converting an old file
		# needs — and the second what each holds now, which is what saying what a
		# restore took out needs.  There is nowhere else to learn either.
		manifest: dict[str, typing.Any] = {}
		live: dict[str, typing.Any] = {}
		deadline = time.monotonic() + 5

		while (not manifest or any(app not in live for app in held)) and time.monotonic() < deadline:
			try:
				frame = json.loads(await asyncio.wait_for(socket.recv(), timeout=1.0))

			except asyncio.TimeoutError:
				break

			if frame.get("t") == "manifest":
				manifest = frame.get("apps") or {}

			elif frame.get("t") == "snapshot":
				live[str(frame.get("app"))] = frame.get("state") or {}

		if not manifest:
			print("no manifest arrived, so no grid can be told from anything else: every value "
			      "goes back one at a time, and a step the composition seeds cannot be taken out")

		if not stamped:
			moved = sum((_converted(state, manifest.get(app) or {})
			             for app, state in held.items()), 0)

			if moved:
				print(f"{where} predates contract 1.12.0: "
				      f"{moved} note(s) converted from steps to positions")

		gone = [one for app, state in held.items()
		        for one in _taken_out(state, live.get(app) or {}, manifest.get(app) or {})]
		asks = [ask for app, state in held.items()
		        for ask in _sets(app, state, manifest.get(app) or {})]

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

	print(f"{len(asks)} values replayed from {where}")

	if gone:
		print(f"  {len(gone)} step(s) the capture did not hold were taken out: {', '.join(gone)}")

	for path, reason in refused:
		print(f"  refused {path}: {reason}")


if __name__ == "__main__":
	asyncio.run(main())
