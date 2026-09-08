"""Stands in for the glass: connects, taps two cells, reports what came back."""

import asyncio
import json
import time

import websockets.asyncio.client

import superconductor.protocol


def _first_step_grid (manifest: dict | None) -> tuple[str | None, str | None, str | None]:
	"""The first step grid anybody is offering, and a row of it to tap.

	A probe that names a control and a voice is a probe for one composition.
	This one asks the manifest instead, so it says something useful against any
	app that offers a grid — and says plainly that it found none when it does
	not, rather than timing out against a path nobody declared.
	"""

	for app, offered in (manifest or {}).get("apps", {}).items():
		for control, declared in offered.items():
			if declared.get("type") != "step_grid" or declared.get("unsupported"):
				continue

			rows = declared.get("rows") or []

			if rows:
				return app, control, rows[0]

	return None, None, None


async def main () -> None:
	async with websockets.asyncio.client.connect("ws://127.0.0.1:8090/ws/panel") as ws:
		# Built rather than spelled out, so it cannot go stale. Three tools wrote
		# the contract by hand and drifted three separate ways — two said 1.1.0
		# and two said 1.5.0 against a current 1.13.0 — while CLAUDE.md's own
		# advice for spotting a stale process is to read the contract off a
		# socket. Nothing checks it today, which is exactly why it drifted.
		await ws.send(superconductor.protocol.encode(
			superconductor.protocol.hello("fake-panel", "grid")))

		seen: list[dict] = []
		deadline = time.monotonic() + 3.0

		# Collect the greeting.
		while time.monotonic() < deadline:
			try:
				seen.append(json.loads(await asyncio.wait_for(ws.recv(), timeout=0.5)))
			except asyncio.TimeoutError:
				break

		manifest = next((f for f in seen if f["t"] == "manifest"), None)
		snapshot = next((f for f in seen if f["t"] == "snapshot"), None)
		beats = [f for f in seen if f.get("name") == "beat"]

		print("MANIFEST apps:", list((manifest or {}).get("apps", {})))

		# **Found rather than written down.** This named `subsequence`, the
		# control `grid` and the row `drum_1` — a Vermona DRM1's second voice —
		# so it reported nothing useful against any composition but one, while
		# the README said only "run it against a service with an app dialled
		# in". Everything it needs is in the manifest it has just read.
		app, control, row = _first_step_grid(manifest)

		if manifest is None or app is None or control is None:
			print("NOTHING TO TAP: no app is offering a step grid with a row in it")
			return

		print(f"  tapping {app} {control}/{row}")

		declared = manifest["apps"][app][control]
		print("  rows:", len(declared.get("rows", [])),
		      "steps:", declared.get("steps"), "beats:", declared.get("beats"))
		print("SNAPSHOT first row:",
		      (snapshot or {}).get("state", {}).get(control, {}).get(row))
		print("BEATS seen in greeting window:", len(beats))

		path = f"{control}/{row}/2"

		# Tap a cell that is currently off, and time the confirmation.
		sent_at = time.perf_counter()
		await ws.send(json.dumps({"t": "set", "app": app, "path": path, "v": True, "seq": 1}))

		ack = changed = None
		while (ack is None or changed is None) and time.perf_counter() - sent_at < 3.0:
			frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=3.0))
			if frame["t"] == "ack" and frame["seq"] == 1:
				ack = time.perf_counter() - sent_at
			elif frame["t"] == "changed" and frame["path"] == path:
				changed = time.perf_counter() - sent_at

		print(f"TAP ON  ack in {ack * 1000:.2f} ms, changed in {changed * 1000:.2f} ms"
		      if ack and changed else f"TAP ON  ack={ack} changed={changed}")

		# And switch it back off.
		sent_at = time.perf_counter()
		await ws.send(json.dumps({"t": "set", "app": app, "path": path, "v": False, "seq": 2}))

		off = None
		while off is None and time.perf_counter() - sent_at < 3.0:
			frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=3.0))
			if frame["t"] == "ack" and frame["seq"] == 2:
				off = time.perf_counter() - sent_at

		print(f"TAP OFF ack in {off * 1000:.2f} ms" if off else "TAP OFF no ack")

		# Watch the beat events for a couple of seconds.
		beats = []
		deadline = time.monotonic() + 2.5
		while time.monotonic() < deadline:
			try:
				frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=0.5))
			except asyncio.TimeoutError:
				continue
			if frame.get("name") == "beat":
				beats.append(frame)

		print("BEATS in 2.5 s:", len(beats),
		      "intervals:", [round(b["interval"], 4) for b in beats if b.get("interval")])


asyncio.run(main())
