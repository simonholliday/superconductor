"""Put back the tempo and the pause a capture holds, and prove the pause by counting beats.

A composition's pattern store keeps what is made on the glass and neither the
pause nor the tempo, because those are how a piece is being played rather than
anything somebody made (#2487).  So a restarted rig comes back **playing**, at
whatever tempo its composition declares, and this is the half of a restart that
`restore_state.py` is not: run it every time, once the composition has declared.

    python tools/restore_transport.py [what-to-read.json]

Reads what `capture_state.py` wrote, by default `/home/si/superconductor-state.json`,
and sends every connected app's transport its tempo and then its pause, as
ordinary `set`s through the panel's own socket.  Exits non-zero when a value is
refused or the clock disagrees with what was put back.

**A pause is believed from the clock and never from the field.**  The field says
what was asked, and it reads `true` for a clock that is held and for one that took
the pause and went on beating — so after the pause lands this counts beats, and a
held rig must send none while a playing one must send some (#2054, #2446).
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

FIELDS: tuple[str, ...] = ("bpm", "paused")
"""What goes back, in the order it goes back: the pause last, so the rig ends held."""


def _read (where: pathlib.Path) -> dict[str, typing.Any]:
	"""Every app's state from a capture, whichever of its two shapes it was written in.

	A file from 1.12.0 on holds the apps under ``apps`` beside a contract; one from
	before is the bare mapping, as `restore_state.py` reads it too.
	"""

	held: dict[str, typing.Any] = json.loads(where.read_text())
	apps = held.get("apps")

	return apps if isinstance(apps, dict) else held


def _asks (held: dict[str, typing.Any], manifest: dict[str, typing.Any]) -> list[tuple[str, str, typing.Any]]:
	"""The sets that put each app's transport back, tempo before pause.

	**A transport is found by its kind, not its name**, because a composition names
	its own controls (#1465); and a field goes back only where the transport still
	declares it, so a composition that can no longer pause is not asked to.  An app
	that is not connected has no manifest and is passed over — `main` says so.
	"""

	asks: list[tuple[str, str, typing.Any]] = []

	for app, state in held.items():
		declared = manifest.get(app) or {}

		for control, value in state.items():
			said = declared.get(control) or {}

			if said.get("type") != "transport" or not isinstance(value, dict):
				continue

			offered = said.get("fields") or []

			asks.extend((app, f"{control}/{field}", value[field])
			            for field in FIELDS if field in value and field in offered)

	return asks


def _window (bpm: typing.Any, least: float) -> float:
	"""How long to count beats for: *least*, or two and a half beats at a slow tempo."""

	if isinstance(bpm, (int, float)) and not isinstance(bpm, bool) and bpm > 0:
		return max(least, 2.5 * 60.0 / bpm)

	return least


async def main (url: str = URL, where: pathlib.Path = WHERE, window: float = 3.0) -> int:
	"""Put the transports back, count the beats, and say what happened; 0 when all agree."""

	held = _read(where)
	failed = False

	async with websockets.asyncio.client.connect(url) as socket:
		# Built rather than spelled out, so the contract cannot go stale (capture_state.py).
		await socket.send(superconductor.protocol.encode(
			superconductor.protocol.hello("restore-transport", None)))

		manifest: dict[str, typing.Any] = {}
		deadline = time.monotonic() + 5

		while not manifest and time.monotonic() < deadline:
			try:
				frame = json.loads(await asyncio.wait_for(socket.recv(), timeout=1.0))

			except asyncio.TimeoutError:
				break

			if frame.get("t") == "manifest":
				manifest = frame.get("apps") or {}

		for app in held:
			if app not in manifest:
				print(f"{app} is not connected, so nothing of its transport went back")
				failed = True

		asks = _asks(held, manifest)

		if not asks:
			print(f"{where} holds no transport for any connected app")
			return 1

		# One at a time and answered before the next, so the pause is last in fact as
		# well as in order: a tempo landing after it would be a set nobody checked.
		for seq, (app, path, value) in enumerate(asks):
			await socket.send(json.dumps({"t": "set", "app": app, "path": path, "v": value, "seq": seq}))

			answer = None
			deadline = time.monotonic() + 5

			while answer is None and time.monotonic() < deadline:
				try:
					frame = json.loads(await asyncio.wait_for(
						socket.recv(), timeout=max(0.05, deadline - time.monotonic())))

				except asyncio.TimeoutError:
					break

				if frame.get("t") in ("ack", "nack") and frame.get("seq") == seq:
					answer = frame

			if answer is None:
				print(f"  {app}/{path} was never answered")
				failed = True

			elif answer["t"] == "nack":
				print(f"  refused {path}: {answer.get('reason')}")
				failed = True

			else:
				print(f"  {app}/{path} is {value!r}")

		# **Counted after a moment's grace**, because a beat already on the wire when
		# the pause landed is not the clock disagreeing.
		await asyncio.sleep(min(0.3, window / 2))

		wanted = {app: bool(value) for app, path, value in asks if path.endswith("/paused")}
		tempo = {app: value for app, path, value in asks if path.endswith("/bpm")}
		counting = max((_window(tempo.get(app), window) for app in wanted), default=window)
		beats = {app: 0 for app in wanted}
		deadline = time.monotonic() + counting

		while wanted and time.monotonic() < deadline:
			try:
				frame = json.loads(await asyncio.wait_for(
					socket.recv(), timeout=max(0.05, deadline - time.monotonic())))

			except asyncio.TimeoutError:
				break

			if frame.get("name") == "beat" and frame.get("app") in beats:
				beats[str(frame["app"])] += 1

	for app, paused in wanted.items():
		if paused and beats[app]:
			print(f"{app}: {beats[app]} beats arrived in {counting:.1f} s, so its clock is not held")
			failed = True

		elif not paused and not beats[app]:
			print(f"{app}: no beats arrived in {counting:.1f} s, though it was captured playing")
			failed = True

		else:
			print(f"{app}: {'held' if paused else 'playing'}, {beats[app]} beats in {counting:.1f} s")

	return 1 if failed else 0


if __name__ == "__main__":
	sys.exit(asyncio.run(main(where=pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else WHERE)))
