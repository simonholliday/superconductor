"""PROTOTYPE, not house style. Measures what an in-process control adapter costs a 24 PPQN asyncio clock.

The clock is a mimic of subsequence.sequencer.Sequencer._run_loop_internal_clock
(asyncio.sleep to within a 1 ms spin threshold, then busy-wait; record
perf_counter minus the ideal pulse time). No MIDI port is opened. The traffic
source is a SEPARATE PROCESS (as the real service would be), so the only extra
threads in the clock process are the adapter's own.

Scenarios:
	baseline      nothing else in the process
	osc-loop      python-osc AsyncIOOSCUDPServer on the clock loop; N msg/s inbound
	ws-loop       websockets server on the clock loop; N msg/s inbound, 10 Hz JSON grid broadcast
	ws-thread     websockets server on its own thread+loop; inbound handed to the clock loop via call_soon_threadsafe; 10 Hz broadcast from the thread
	udp-thread    python-osc ThreadingOSCUDPServer (per-datagram threads) handing to the clock loop via call_soon_threadsafe
	ws-thread-cpu ws-thread plus a 32x32 grid JSON encode on the side thread at 10 Hz (GIL cost of doing work off-loop)

Ports used: 9111 (OSC), 9112 (WS). Never 5555, 8080, 8765 or 9000-9004.
"""

import argparse
import asyncio
import json
import statistics
import subprocess
import sys
import threading
import time

import pythonosc.dispatcher
import pythonosc.osc_server
import pythonosc.udp_client
import websockets.asyncio.server
import websockets.sync.client

PPQN = 24
OSC_PORT = 9111
WS_PORT = 9112


async def clock (bpm: float, seconds: float, spin_threshold: float, log: list) -> None:
	spp = 60.0 / bpm / PPQN
	start = time.perf_counter() + 0.05
	nxt = start
	end = start + seconds
	while nxt < end:
		now = time.perf_counter()
		if now < nxt:
			s = nxt - now
			if s > spin_threshold:
				await asyncio.sleep(s - spin_threshold)
			while time.perf_counter() < nxt:
				pass
		log.append(time.perf_counter() - nxt)
		_ = {i: i for i in range(32)}
		nxt += spp
		await asyncio.sleep(0)


def summarise (name: str, log: list) -> dict:
	us = [x * 1e6 for x in log[PPQN:]]
	us_sorted = sorted(us)
	return {
		"scenario": name,
		"pulses": len(us),
		"mean_us": round(statistics.fmean(us), 1),
		"p50_us": round(us_sorted[len(us) // 2], 1),
		"p99_us": round(us_sorted[int(len(us) * 0.99)], 1),
		"max_us": round(us_sorted[-1], 1),
		"over_1ms": sum(1 for x in us if x > 1000),
	}


def grid_json (rows: int, cols: int) -> str:
	return json.dumps({"type": "grid", "pattern": "drums", "cells": [[(r * c) % 3 == 0 for c in range(cols)] for r in range(rows)]})


GRID_SMALL = grid_json(8, 16)


# ---- sender side (separate process) ----

def sender_main (kind: str, rate: float, seconds: float) -> None:
	interval = 1.0 / rate
	deadline = time.time() + seconds
	n = 0
	if kind == "osc":
		client = pythonosc.udp_client.SimpleUDPClient("127.0.0.1", OSC_PORT)
		while time.time() < deadline:
			client.send_message("/grid/drums/cell", [n % 8, n % 16, 1])
			n += 1
			time.sleep(interval)
	else:
		received = [0]
		for _ in range(50):
			try:
				ws = websockets.sync.client.connect(f"ws://127.0.0.1:{WS_PORT}")
				break
			except OSError:
				time.sleep(0.1)
		with ws:
			def reader () -> None:
				try:
					for m in ws:
						received[0] += 1
				except Exception:
					pass
			threading.Thread(target=reader, daemon=True).start()
			while time.time() < deadline:
				ws.send(json.dumps({"type": "set", "pattern": "drums", "row": n % 8, "col": n % 16, "on": True}))
				n += 1
				time.sleep(interval)
		print(json.dumps({"sender": kind, "sent": n, "broadcasts_received": received[0]}), flush=True)
		return
	print(json.dumps({"sender": kind, "sent": n}), flush=True)


def spawn_sender (kind: str, rate: float, seconds: float) -> subprocess.Popen:
	return subprocess.Popen([sys.executable, __file__, "--send", kind, "--rate", str(rate), "--seconds", str(seconds)], stdout=subprocess.PIPE, text=True)


def finish_sender (p: subprocess.Popen, r: dict) -> None:
	out, _ = p.communicate(timeout=30)
	for line in out.splitlines():
		try:
			r.update(json.loads(line))
		except ValueError:
			pass


# ---- scenarios (clock process) ----

async def run_baseline (bpm, seconds, spin, rate) -> dict:
	log: list = []
	await clock(bpm, seconds, spin, log)
	return summarise("baseline", log)


async def run_osc_loop (bpm, seconds, spin, rate) -> dict:
	log: list = []
	count = [0]
	disp = pythonosc.dispatcher.Dispatcher()
	def h (addr, *args):
		count[0] += 1
	disp.map("/grid/*", h)
	server = pythonosc.osc_server.AsyncIOOSCUDPServer(("127.0.0.1", OSC_PORT), disp, asyncio.get_running_loop())
	transport, _ = await server.create_serve_endpoint()
	p = spawn_sender("osc", rate, seconds)
	await clock(bpm, seconds, spin, log)
	transport.close()
	r = summarise("osc-loop", log)
	r["inbound_handled"] = count[0]
	finish_sender(p, r)
	return r


async def run_ws_loop (bpm, seconds, spin, rate) -> dict:
	log: list = []
	count = [0]
	clients: set = set()
	async def handler (ws):
		clients.add(ws)
		try:
			async for m in ws:
				json.loads(m)
				count[0] += 1
		finally:
			clients.discard(ws)
	async def broadcaster ():
		while True:
			await asyncio.sleep(0.1)
			if clients:
				websockets.asyncio.server.broadcast(clients, GRID_SMALL)
	server = await websockets.asyncio.server.serve(handler, "127.0.0.1", WS_PORT)
	btask = asyncio.create_task(broadcaster())
	p = spawn_sender("ws", rate, seconds)
	await asyncio.sleep(0.3)
	await clock(bpm, seconds, spin, log)
	btask.cancel()
	server.close()
	await server.wait_closed()
	r = summarise("ws-loop", log)
	r["inbound_handled"] = count[0]
	finish_sender(p, r)
	return r


async def _ws_thread (name: str, bpm, seconds, spin, rate, cpu: bool) -> dict:
	log: list = []
	count = [0]
	clock_loop = asyncio.get_running_loop()
	def apply (msg: dict) -> None:
		count[0] += 1
	ready = threading.Event()
	stop_server = threading.Event()
	def server_thread () -> None:
		loop = asyncio.new_event_loop()
		asyncio.set_event_loop(loop)
		clients: set = set()
		async def handler (ws):
			clients.add(ws)
			try:
				async for m in ws:
					clock_loop.call_soon_threadsafe(apply, json.loads(m))
			finally:
				clients.discard(ws)
		async def broadcaster ():
			while True:
				await asyncio.sleep(0.1)
				payload = grid_json(32, 32) if cpu else GRID_SMALL
				if clients:
					websockets.asyncio.server.broadcast(clients, payload)
		async def main ():
			server = await websockets.asyncio.server.serve(handler, "127.0.0.1", WS_PORT)
			b = asyncio.create_task(broadcaster())
			ready.set()
			while not stop_server.is_set():
				await asyncio.sleep(0.05)
			b.cancel()
			server.close()
			await server.wait_closed()
		loop.run_until_complete(main())
		loop.close()
	st = threading.Thread(target=server_thread, daemon=True)
	st.start()
	ready.wait()
	p = spawn_sender("ws", rate, seconds)
	await asyncio.sleep(0.3)
	await clock(bpm, seconds, spin, log)
	stop_server.set()
	st.join(timeout=2)
	r = summarise(name, log)
	r["inbound_handled"] = count[0]
	finish_sender(p, r)
	return r


async def run_ws_thread (bpm, seconds, spin, rate) -> dict:
	return await _ws_thread("ws-thread", bpm, seconds, spin, rate, cpu=False)


async def run_ws_thread_cpu (bpm, seconds, spin, rate) -> dict:
	return await _ws_thread("ws-thread-cpu", bpm, seconds, spin, rate, cpu=True)


async def run_udp_thread (bpm, seconds, spin, rate) -> dict:
	log: list = []
	count = [0]
	clock_loop = asyncio.get_running_loop()
	def apply (*args) -> None:
		count[0] += 1
	disp = pythonosc.dispatcher.Dispatcher()
	def h (addr, *args):
		clock_loop.call_soon_threadsafe(apply, addr, *args)
	disp.map("/grid/*", h)
	server = pythonosc.osc_server.ThreadingOSCUDPServer(("127.0.0.1", OSC_PORT), disp)
	server.daemon_threads = True
	st = threading.Thread(target=server.serve_forever, daemon=True)
	st.start()
	p = spawn_sender("osc", rate, seconds)
	await clock(bpm, seconds, spin, log)
	server.shutdown()
	server.server_close()
	r = summarise("udp-thread", log)
	r["inbound_handled"] = count[0]
	finish_sender(p, r)
	return r


async def run_ws_thread_drain (bpm, seconds, spin, rate) -> dict:
	"""websockets server on its own thread; inbound goes into a queue.SimpleQueue; the clock drains it once per beat (24 pulses) with no loop wake-up — the keystroke-listener drain() shape."""
	import queue
	log: list = []
	count = [0]
	q: "queue.SimpleQueue" = queue.SimpleQueue()
	ready = threading.Event()
	stop_server = threading.Event()
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
				if clients:
					websockets.asyncio.server.broadcast(clients, GRID_SMALL)
		async def main ():
			server = await websockets.asyncio.server.serve(handler, "127.0.0.1", WS_PORT)
			b = asyncio.create_task(broadcaster())
			ready.set()
			while not stop_server.is_set():
				await asyncio.sleep(0.05)
			b.cancel()
			server.close()
			await server.wait_closed()
		loop.run_until_complete(main())
		loop.close()
	st = threading.Thread(target=server_thread, daemon=True)
	st.start()
	ready.wait()
	p = spawn_sender("ws", rate, seconds)
	await asyncio.sleep(0.3)
	# clock with a per-beat drain
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
			while True:
				try:
					q.get_nowait()
					count[0] += 1
				except queue.Empty:
					break
		pulse += 1
		nxt += spp
		await asyncio.sleep(0)
	stop_server.set()
	st.join(timeout=2)
	r = summarise("ws-thread-drain", log)
	r["inbound_handled"] = count[0]
	finish_sender(p, r)
	return r


SCENARIOS = {
	"baseline": run_baseline,
	"osc-loop": run_osc_loop,
	"ws-loop": run_ws_loop,
	"ws-thread": run_ws_thread,
	"udp-thread": run_udp_thread,
	"ws-thread-cpu": run_ws_thread_cpu,
	"ws-thread-drain": run_ws_thread_drain,
}


def main () -> None:
	ap = argparse.ArgumentParser()
	ap.add_argument("--bpm", type=float, default=120)
	ap.add_argument("--seconds", type=float, default=20)
	ap.add_argument("--spin", type=float, default=0.001)
	ap.add_argument("--rate", type=float, default=50)
	ap.add_argument("--only", default=None)
	ap.add_argument("--send", default=None, help="internal: run as a sender process of this kind")
	a = ap.parse_args()
	if a.send:
		sender_main(a.send, a.rate, a.seconds)
		return
	for name, fn in SCENARIOS.items():
		if a.only and name != a.only:
			continue
		r = asyncio.run(fn(a.bpm, a.seconds, a.spin, a.rate))
		print(json.dumps(r), flush=True)
		time.sleep(0.5)


if __name__ == "__main__":
	main()
