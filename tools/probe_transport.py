"""Exercises the transport from the panel's side, over the real socket.

Measures what a person would experience: how long a pause takes to confirm,
whether the clock really stops, whether resuming dumps a burst of held beats,
and whether a refused tempo comes back with a reason.
"""

import asyncio
import json
import time
import typing

import websockets.asyncio.client

import superconductor.protocol


URL = "ws://127.0.0.1:8090/ws/panel"


async def collect (ws: typing.Any, seconds: float, into: list[dict]) -> None:
	"""Gather frames for a while, keeping the beats separately."""

	deadline = time.monotonic() + seconds

	while time.monotonic() < deadline:
		try:
			frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=max(0.05, deadline - time.monotonic())))

		except asyncio.TimeoutError:
			break

		into.append(frame)


def beats (frames: list[dict]) -> list[dict]:
	"""Just the beat events."""

	return [f for f in frames if f.get("name") == "beat"]


async def await_change (ws: typing.Any, path: str, value: typing.Any,
                        limit: float = 5.0) -> tuple[float | None, str | None]:
	"""Wait for the app to report a path holding a value, and time it."""

	started = time.perf_counter()

	while time.perf_counter() - started < limit:
		frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=limit))

		if frame["t"] == "changed" and frame.get("path") == path and frame.get("v") == value:
			return time.perf_counter() - started, None

		if frame["t"] == "nack" and frame.get("path") == path:
			return time.perf_counter() - started, frame.get("reason")

	return None, "nothing arrived"


async def main () -> None:
	async with websockets.asyncio.client.connect(URL) as ws:
		# Built rather than spelled out, so it cannot go stale. Three tools wrote
		# the contract by hand and drifted three separate ways — two said 1.1.0
		# and two said 1.5.0 against a current 1.13.0 — while CLAUDE.md's own
		# advice for spotting a stale process is to read the contract off a
		# socket. Nothing checks it today, which is exactly why it drifted.
		await ws.send(superconductor.protocol.encode(
			superconductor.protocol.hello("transport-test", "grid")))

		greeting: list[dict] = []
		await collect(ws, 2.5, greeting)

		manifest = next((f for f in greeting if f["t"] == "manifest"), {})
		controls = list(manifest.get("apps", {}).values())
		transport = controls[0].get("transport") if controls else None
		snapshot = next((f for f in greeting if f["t"] == "snapshot"), {})

		found = (snapshot.get("state") or {}).get("transport") or {}

		print("DECLARED   ", transport)
		print("SNAPSHOT   ", found)
		print("BEATS/2.5s ", len(beats(greeting)), "before pausing")

		# Pause, and time the confirmation the composition sends back.
		await ws.send(json.dumps({"t": "set", "app": "subsequence", "path": "transport/paused",
		                          "v": True, "seq": 1}))
		took, refused = await await_change(ws, "transport/paused", True)
		print(f"PAUSE      confirmed in {took * 1000:.1f} ms" if took and not refused
		      else f"PAUSE      refused: {refused}")

		held: list[dict] = []
		await collect(ws, 2.5, held)
		print("BEATS/2.5s ", len(beats(held)), "while held  (0 means the clock really stopped)")

		# Resume, and watch for a burst of the beats the pause held back.
		resumed_at = time.perf_counter()
		await ws.send(json.dumps({"t": "set", "app": "subsequence", "path": "transport/paused",
		                          "v": False, "seq": 2}))
		took, refused = await await_change(ws, "transport/paused", False)
		print(f"RESUME     confirmed in {took * 1000:.1f} ms" if took and not refused
		      else f"RESUME     refused: {refused}")

		burst: list[dict] = []
		await collect(ws, 0.6, burst)
		print("BEATS/0.6s ", len(beats(burst)), "just after resuming  (about 1 at 120 BPM; a flood is the burst bug)")

		after: list[dict] = []
		await collect(ws, 2.5, after)
		intervals = [round(b["interval"], 4) for b in beats(after) if b.get("interval")]
		print("INTERVALS  ", intervals, "after resuming")

		# Tempo, accepted and refused.
		await ws.send(json.dumps({"t": "set", "app": "subsequence", "path": "transport/bpm",
		                          "v": 132, "seq": 3}))
		took, refused = await await_change(ws, "transport/bpm", 132)
		print(f"TEMPO 132  confirmed in {took * 1000:.1f} ms" if took and not refused
		      else f"TEMPO 132  refused: {refused}")

		await ws.send(json.dumps({"t": "set", "app": "subsequence", "path": "transport/bpm",
		                          "v": 300, "seq": 4}))
		took, refused = await await_change(ws, "transport/bpm", 300, limit=3.0)
		print(f"TEMPO 300  refused: {refused}" if refused else "TEMPO 300  ACCEPTED — it should not have been")

		# **Put back what was there, not what was assumed to be there.** This
		# restored a hard-coded 120 while its own README promises the probe
		# leaves the composition as it found it — so running it against a rig at
		# any other tempo silently changed the music. Caught on 2026-09-06 by
		# running it against a composition sitting at 130.
		was = found.get("bpm")

		if isinstance(was, (int, float)):
			await ws.send(json.dumps({"t": "set", "app": "subsequence", "path": "transport/bpm",
			                          "v": was, "seq": 5}))
			await await_change(ws, "transport/bpm", was)
			print(f"TEMPO      restored to {was}")

		else:
			print("TEMPO      left as it is: the snapshot carried no tempo to restore")

		# And the hold, for the same reason: a probe that starts a paused
		# composition playing has changed the thing it came to measure.
		if found.get("paused") is True:
			await ws.send(json.dumps({"t": "set", "app": "subsequence",
			                          "path": "transport/paused", "v": True, "seq": 6}))
			await await_change(ws, "transport/paused", True)
			print("PAUSE      restored, as it was found")


asyncio.run(main())
