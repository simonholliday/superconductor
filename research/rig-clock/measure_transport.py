"""Read the transport, optionally set tempo and pause, then count beats.

	python measure_transport.py                      read, and count beats for 3 s
	python measure_transport.py --bpm 125 --paused   set both, then count

Waits against a wall-clock deadline, never against the gap between frames, and
takes a bare ack as an answer (a set that changes nothing, #2502).
"""

import argparse
import asyncio
import json
import time

import websockets.asyncio.client

import superconductor.protocol

URL = "ws://127.0.0.1:8090/ws/panel"


async def gather (ws, seconds: float) -> list[dict]:  # type: ignore[no-untyped-def]
	frames: list[dict] = []
	deadline = time.monotonic() + seconds

	while (left := deadline - time.monotonic()) > 0:
		try:
			frames.append(json.loads(await asyncio.wait_for(ws.recv(), timeout=left)))

		except asyncio.TimeoutError:
			break

	return frames


async def answer (ws, seq: int, limit: float = 5.0) -> str:  # type: ignore[no-untyped-def]
	deadline = time.monotonic() + limit

	while (left := deadline - time.monotonic()) > 0:
		try:
			frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=left))

		except asyncio.TimeoutError:
			break

		if frame.get("seq") == seq and frame.get("t") in ("ack", "nack", "changed"):
			return f"{frame['t']} {frame.get('reason') or ''}".strip()

	return "no answer before the deadline"


async def main () -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--bpm", type=float)
	parser.add_argument("--paused", action="store_true")
	parser.add_argument("--playing", action="store_true")
	options = parser.parse_args()

	async with websockets.asyncio.client.connect(URL) as ws:
		await ws.send(superconductor.protocol.encode(
			superconductor.protocol.hello("measure-transport", "grid")))

		greeting = await gather(ws, 2.5)
		snapshot = next((f for f in greeting if f.get("t") == "snapshot"), {})
		apps = (snapshot.get("state") or {})
		print("before:", (apps.get("subsequence") or apps).get("transport") if isinstance(apps, dict) else apps)

		seq = 100

		if options.bpm is not None:
			seq += 1
			await ws.send(json.dumps({"t": "set", "app": "subsequence", "path": "transport/bpm",
			                          "v": options.bpm, "seq": seq}))
			print("bpm:", await answer(ws, seq))

		if options.paused or options.playing:
			seq += 1
			await ws.send(json.dumps({"t": "set", "app": "subsequence", "path": "transport/paused",
			                          "v": bool(options.paused), "seq": seq}))
			print("paused:", await answer(ws, seq))

		counted = await gather(ws, 3.0)
		beats = [f for f in counted if f.get("name") == "beat"]
		print(f"beats in 3 s: {len(beats)}")


asyncio.run(main())
