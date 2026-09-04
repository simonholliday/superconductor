"""Stands in for the glass: connects, taps two cells, reports what came back."""

import asyncio
import json
import time

import websockets.asyncio.client


async def main () -> None:
	async with websockets.asyncio.client.connect("ws://127.0.0.1:8090/ws/panel") as ws:
		await ws.send(json.dumps({"t": "hello", "contract": "1.1.0", "client": "fake-panel",
		                          "page": "grid", "ver": {}, "token": None}))

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
		if manifest and manifest.get("apps"):
			grid = list(manifest["apps"].values())[0].get("grid", {})
			print("  rows:", len(grid.get("rows", [])), "steps:", grid.get("steps"), "beats:", grid.get("beats"))
		print("SNAPSHOT kick:", (snapshot or {}).get("state", {}).get("grid", {}).get("kick"))
		print("BEATS seen in greeting window:", len(beats))

		# Tap a cell that is currently off, and time the confirmation.
		sent_at = time.perf_counter()
		await ws.send(json.dumps({"t": "set", "app": "subsequence", "path": "grid/drum_1/2",
		                          "v": True, "seq": 1}))

		ack = changed = None
		while (ack is None or changed is None) and time.perf_counter() - sent_at < 3.0:
			frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=3.0))
			if frame["t"] == "ack" and frame["seq"] == 1:
				ack = time.perf_counter() - sent_at
			elif frame["t"] == "changed" and frame["path"] == "grid/drum_1/2":
				changed = time.perf_counter() - sent_at

		print(f"TAP ON  ack in {ack * 1000:.2f} ms, changed in {changed * 1000:.2f} ms"
		      if ack and changed else f"TAP ON  ack={ack} changed={changed}")

		# And switch it back off.
		sent_at = time.perf_counter()
		await ws.send(json.dumps({"t": "set", "app": "subsequence", "path": "grid/drum_1/2",
		                          "v": False, "seq": 2}))

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
