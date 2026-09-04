"""PROTOTYPE, not house style. Extends jitter_probe.py with the scenarios verification asked for.

Scenarios:
	osc-thread-drain  python-osc ThreadingOSCUDPServer on a daemon thread; datagrams into queue.SimpleQueue; the clock drains once per beat (Subsample's receiver shape plus the keystroke drain)
	snap-loop-encode  ws-thread-drain plus, once per beat ON THE CLOCK LOOP, build a state dict for 8 patterns x 8 named voices x 16 steps (1024 cells) and json.dumps it; the side thread broadcasts the latest string at 10 Hz
	snap-loop-dict    as above but only the dict is built on the loop; the side thread encodes it
	baseline, osc-loop, ws-thread, ws-thread-drain  re-exported from jitter_probe for --selector runs

--selector epoll|select picks the asyncio loop's selector. EpollSelector rounds timeouts up to whole ms (selectors.py); SelectSelector passes them through.
Ports as jitter_probe.py: 9111 (OSC), 9112 (WS).
"""

import argparse
import asyncio
import json
import os
import queue
import selectors
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jitter_probe as jp
import pythonosc.dispatcher
import pythonosc.osc_server
import websockets.asyncio.server

PPQN = jp.PPQN
VOICES = ["kick", "snare", "hat_closed", "hat_open", "clap", "rim", "tom_low", "tom_high"]


def build_state (patterns: int, beat: int) -> dict:
	pats = {}
	for p in range(patterns):
		pats[f"pattern_{p}"] = {
			"voices": VOICES,
			"length_beats": 4,
			"muted": False,
			"cells": [[((r * 7 + c * 3 + p + beat) % 5) == 0 for c in range(16)] for r in range(8)],
		}
	return {"type": "state", "beat": beat, "bpm": 120.0, "patterns": pats}


async def clock_with_beat (bpm, seconds, spin, log, on_beat) -> None:
	spp = 60.0 / bpm / PPQN
	start = time.perf_counter() + 0.05
	nxt = start
	end = start + seconds
	pulse = 0
	while nxt < end:
		now = time.perf_counter()
		if now < nxt:
			s = nxt - now
			if s > spin:
				await asyncio.sleep(s - spin)
			while time.perf_counter() < nxt:
				pass
		log.append(time.perf_counter() - nxt)
		if pulse % PPQN == 0:
			on_beat(pulse // PPQN)
		pulse += 1
		nxt += spp
		await asyncio.sleep(0)


async def run_osc_thread_drain (bpm, seconds, spin, rate) -> dict:
	log: list = []
	count = [0]
	q: "queue.SimpleQueue" = queue.SimpleQueue()
	disp = pythonosc.dispatcher.Dispatcher()
	def h (addr, *args):
		q.put((addr, args))
	disp.map("/grid/*", h)
	server = pythonosc.osc_server.ThreadingOSCUDPServer(("127.0.0.1", jp.OSC_PORT), disp)
	server.daemon_threads = True
	st = threading.Thread(target=server.serve_forever, daemon=True)
	st.start()
	p = jp.spawn_sender("osc", rate, seconds)
	def drain (beat):
		while True:
			try:
				q.get_nowait()
				count[0] += 1
			except queue.Empty:
				break
	await clock_with_beat(bpm, seconds, spin, log, drain)
	server.shutdown()
	server.server_close()
	r = jp.summarise("osc-thread-drain", log)
	r["inbound_handled"] = count[0]
	jp.finish_sender(p, r)
	return r


async def _snap (name, bpm, seconds, spin, rate, encode_on_loop: bool, patterns: int) -> dict:
	log: list = []
	count = [0]
	q: "queue.SimpleQueue" = queue.SimpleQueue()
	latest: list = [None]
	sent = [0]
	ready = threading.Event()
	stop = threading.Event()
	def server_thread () -> None:
		loop = asyncio.new_event_loop()
		asyncio.set_event_loop(loop)
		clients: set = set()
		async def handler (ws):
			clients.add(ws)
			try:
				async for m in ws:
					q.put(json.loads(m))
			finally:
				clients.discard(ws)
		async def broadcaster ():
			while True:
				await asyncio.sleep(0.1)
				snap = latest[0]
				if clients and snap is not None:
					websockets.asyncio.server.broadcast(clients, snap if encode_on_loop else json.dumps(snap))
					sent[0] += 1
		async def main ():
			server = await websockets.asyncio.server.serve(handler, "127.0.0.1", jp.WS_PORT)
			b = asyncio.create_task(broadcaster())
			ready.set()
			while not stop.is_set():
				await asyncio.sleep(0.05)
			b.cancel()
			server.close()
			await server.wait_closed()
		loop.run_until_complete(main())
		loop.close()
	st = threading.Thread(target=server_thread, daemon=True)
	st.start()
	ready.wait()
	p = jp.spawn_sender("ws", rate, seconds)
	await asyncio.sleep(0.3)
	build_us: list = []
	def on_beat (beat):
		while True:
			try:
				q.get_nowait()
				count[0] += 1
			except queue.Empty:
				break
		t0 = time.perf_counter()
		state = build_state(patterns, beat)
		latest[0] = json.dumps(state) if encode_on_loop else state
		build_us.append((time.perf_counter() - t0) * 1e6)
	await clock_with_beat(bpm, seconds, spin, log, on_beat)
	stop.set()
	st.join(timeout=2)
	r = jp.summarise(name, log)
	r["inbound_handled"] = count[0]
	r["snapshot_build_us_mean"] = round(sum(build_us) / len(build_us), 1)
	r["snapshot_build_us_max"] = round(max(build_us), 1)
	r["snapshot_bytes"] = len(latest[0] if encode_on_loop else json.dumps(latest[0]))
	r["patterns"] = patterns
	jp.finish_sender(p, r)
	return r


async def run_snap_loop_encode (bpm, seconds, spin, rate) -> dict:
	return await _snap("snap-loop-encode", bpm, seconds, spin, rate, True, 8)


async def run_snap_loop_dict (bpm, seconds, spin, rate) -> dict:
	return await _snap("snap-loop-dict", bpm, seconds, spin, rate, False, 8)


SCENARIOS = {
	"baseline": jp.run_baseline,
	"osc-loop": jp.run_osc_loop,
	"ws-thread": jp.run_ws_thread,
	"ws-thread-drain": jp.run_ws_thread_drain,
	"osc-thread-drain": run_osc_thread_drain,
	"snap-loop-encode": run_snap_loop_encode,
	"snap-loop-dict": run_snap_loop_dict,
}


def main () -> None:
	ap = argparse.ArgumentParser()
	ap.add_argument("--bpm", type=float, default=120)
	ap.add_argument("--seconds", type=float, default=20)
	ap.add_argument("--spin", type=float, default=0.001)
	ap.add_argument("--rate", type=float, default=50)
	ap.add_argument("--only", default=None, help="comma-separated scenario names")
	ap.add_argument("--selector", default="epoll", choices=["epoll", "select"])
	a = ap.parse_args()
	wanted = a.only.split(",") if a.only else list(SCENARIOS)
	for name in wanted:
		fn = SCENARIOS[name]
		loop = asyncio.SelectorEventLoop(selectors.SelectSelector()) if a.selector == "select" else asyncio.SelectorEventLoop()
		asyncio.set_event_loop(loop)
		r = loop.run_until_complete(fn(a.bpm, a.seconds, a.spin, a.rate))
		loop.close()
		r["selector"] = a.selector
		print(json.dumps(r), flush=True)
		time.sleep(0.5)


if __name__ == "__main__":
	main()
