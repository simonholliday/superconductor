"""gap-2-1 copy of transport-apps/adapter_bench.py, identical but for the four
port constants, which are moved off 9111/9113/9114/9115 because another point
was running the shared bench on those ports at the same time.

Research PROTOTYPE, not house style.

Clock jitter of the real subsequence.sequencer.Sequencer (the yardstick of
benchmarks/clock_jitter.py) with one candidate adapter shape running inside
the same process.  Every scenario carries the same traffic: an external
sender process fires INBOUND_HZ command messages at the adapter for the whole
run, and the adapter pushes one small state frame per beat (24 pulses) back
to the sender/service.  The "apply" step for an inbound command is one dict
write on the clock loop, standing in for composition.data[key] = value.

Scenarios
	baseline          nothing else in the process
	osc-loop          python-osc AsyncIOOSCUDPServer on the clock loop (Subsequence's own osc.py shape); apply inline
	osc-thread        python-osc BlockingOSCUDPServer on a daemon thread; apply via loop.call_soon_threadsafe per datagram
	osc-thread-drain  same server; datagrams queued; drained on the beat event (keystroke-listener shape)
	ws-loop           websockets client link on the clock loop dialling a stand-in service; apply inline
	ws-thread         websockets client link on a daemon thread with its own loop; apply via call_soon_threadsafe
	tcp-thread        stdlib socket TCP client, newline-delimited JSON, reader on a daemon thread; apply via call_soon_threadsafe

Ports: OSC 9111/9113 (adapter/sender), WS service 9114, TCP service 9115 —
none in the apps' port map (5555, 8080, 8765, 9000-9004).

Usage: adapter_bench.py SCENARIO [--bars N] [--bpm B] [--rate HZ] [--json]
"""

import argparse
import asyncio
import json
import logging
import os
import queue
import socket
import statistics
import subprocess
import sys
import threading
import time

logging.basicConfig(level=logging.ERROR)

import pythonosc.dispatcher
import pythonosc.osc_server
import pythonosc.udp_client
import websockets
import websockets.asyncio.client
import websockets.asyncio.server

import subsequence.sequencer

PPQN = 24
OSC_ADAPTER_PORT = 9161
OSC_SENDER_PORT = 9163
WS_PORT = 9164
TCP_PORT = 9165

state = {"cells": {}, "applied": 0, "pushed": 0, "inbound": 0}
seq_ref: list = [None]


def apply (cell: int, value: bool) -> None:
	"""Runs on the clock loop: the stand-in for composition.data write."""
	state["cells"][cell] = value
	state["applied"] += 1


def frame () -> str:
	seq = seq_ref[0]
	return json.dumps({"type": "state", "pulse": seq.pulse_count if seq else 0, "cells": list(state["cells"].items())[-16:]})


# ---------------------------------------------------------------- sender side

def sender_main (kind: str, rate: float, seconds: float) -> None:
	"""Separate process: the stand-in service.  Fires commands at `rate` Hz
	and counts the frames it receives back."""
	sent = 0
	received = [0]
	interval = 1.0 / rate
	end = time.perf_counter() + seconds

	if kind == "osc":
		disp = pythonosc.dispatcher.Dispatcher()
		def h (addr, *args):
			received[0] += 1
		disp.map("/state", h)
		srv = pythonosc.osc_server.ThreadingOSCUDPServer(("127.0.0.1", OSC_SENDER_PORT), disp)
		srv.daemon_threads = True
		threading.Thread(target=srv.serve_forever, daemon=True).start()
		client = pythonosc.udp_client.SimpleUDPClient("127.0.0.1", OSC_ADAPTER_PORT)
		time.sleep(0.5)
		while time.perf_counter() < end:
			client.send_message("/grid/set", [sent % 128, 1 if sent % 2 else 0])
			sent += 1
			time.sleep(interval)
		srv.shutdown()

	elif kind == "ws":
		async def main ():
			nonlocal sent
			conns: set = set()
			async def handler (ws):
				conns.add(ws)
				try:
					async for raw in ws:
						received[0] += 1
				except websockets.exceptions.ConnectionClosed:
					pass
				finally:
					conns.discard(ws)
			async with websockets.asyncio.server.serve(handler, "127.0.0.1", WS_PORT):
				while time.perf_counter() < end:
					await asyncio.sleep(interval)
					if conns:
						payload = json.dumps({"type": "set", "cell": sent % 128, "value": bool(sent % 2)})
						websockets.broadcast(conns, payload)
						sent += 1
		asyncio.run(main())

	elif kind == "tcp":
		srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		srv.bind(("127.0.0.1", TCP_PORT))
		srv.listen(1)
		srv.settimeout(10.0)
		conn, _ = srv.accept()
		conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
		def reader ():
			buf = b""
			try:
				while True:
					chunk = conn.recv(65536)
					if not chunk:
						return
					buf += chunk
					while b"\n" in buf:
						line, buf = buf.split(b"\n", 1)
						received[0] += 1
			except OSError:
				return
		threading.Thread(target=reader, daemon=True).start()
		while time.perf_counter() < end:
			payload = json.dumps({"type": "set", "cell": sent % 128, "value": bool(sent % 2)}) + "\n"
			try:
				conn.sendall(payload.encode())
			except OSError:
				break
			sent += 1
			time.sleep(interval)
		conn.close()
		srv.close()

	print(json.dumps({"sender_sent": sent, "sender_received": received[0]}), flush=True)


def spawn_sender (kind: str, rate: float, seconds: float) -> subprocess.Popen:
	return subprocess.Popen([sys.executable, __file__, "--send", kind, "--rate", str(rate), "--seconds", str(seconds)], stdout=subprocess.PIPE, text=True)


def finish_sender (p: subprocess.Popen, r: dict) -> None:
	try:
		out, _ = p.communicate(timeout=30)
	except subprocess.TimeoutExpired:
		p.kill()
		out, _ = p.communicate()
	for line in out.splitlines():
		try:
			r.update(json.loads(line))
		except ValueError:
			pass


# ---------------------------------------------------------------- adapters

class Adapter:
	"""One adapter shape.  start() before the clock, stop() after.  on_beat()
	is called from the sequencer's beat event on the clock loop."""

	def __init__ (self, loop: asyncio.AbstractEventLoop) -> None:
		self.loop = loop

	async def start (self) -> None: ...
	async def stop (self) -> None: ...
	def on_beat (self, beat: int) -> None: ...


class OscLoop (Adapter):

	async def start (self) -> None:
		disp = pythonosc.dispatcher.Dispatcher()
		def h (addr, cell, value):
			state["inbound"] += 1
			apply(int(cell), bool(value))
		disp.map("/grid/*", h)
		self.server = pythonosc.osc_server.AsyncIOOSCUDPServer(("127.0.0.1", OSC_ADAPTER_PORT), disp, self.loop)
		self.transport, _ = await self.server.create_serve_endpoint()
		self.client = pythonosc.udp_client.SimpleUDPClient("127.0.0.1", OSC_SENDER_PORT)

	def on_beat (self, beat: int) -> None:
		self.client.send_message("/state", [frame()])
		state["pushed"] += 1

	async def stop (self) -> None:
		self.transport.close()


class OscThread (Adapter):

	def __init__ (self, loop, drain: bool) -> None:
		super().__init__(loop)
		self.drain = drain
		self.q: "queue.SimpleQueue" = queue.SimpleQueue()

	async def start (self) -> None:
		disp = pythonosc.dispatcher.Dispatcher()
		def h (addr, cell, value):
			state["inbound"] += 1
			if self.drain:
				self.q.put((int(cell), bool(value)))
			else:
				self.loop.call_soon_threadsafe(apply, int(cell), bool(value))
		disp.map("/grid/*", h)
		self.server = pythonosc.osc_server.BlockingOSCUDPServer(("127.0.0.1", OSC_ADAPTER_PORT), disp)
		self.thread = threading.Thread(target=self.server.serve_forever, daemon=True, name="osc-adapter")
		self.thread.start()
		self.client = pythonosc.udp_client.SimpleUDPClient("127.0.0.1", OSC_SENDER_PORT)

	def on_beat (self, beat: int) -> None:
		if self.drain:
			while True:
				try:
					cell, value = self.q.get_nowait()
				except queue.Empty:
					break
				apply(cell, value)
		# UDP sendto is non-blocking; sending from the loop is what osc.py does today.
		self.client.send_message("/state", [frame()])
		state["pushed"] += 1

	async def stop (self) -> None:
		self.server.shutdown()
		self.server.server_close()


class WsLink (Adapter):
	"""Outbound WebSocket link to the service (registration shape)."""

	def __init__ (self, loop, threaded: bool) -> None:
		super().__init__(loop)
		self.threaded = threaded
		self.link_loop: asyncio.AbstractEventLoop | None = None
		self.ws = None
		self.ready = threading.Event()

	async def link (self) -> None:
		for _ in range(50):
			try:
				self.ws = await websockets.asyncio.client.connect(f"ws://127.0.0.1:{WS_PORT}")
				break
			except OSError:
				await asyncio.sleep(0.1)
		self.ready.set()
		if self.ws is None:
			return
		try:
			async for raw in self.ws:
				msg = json.loads(raw)
				state["inbound"] += 1
				if self.threaded:
					self.loop.call_soon_threadsafe(apply, msg["cell"], msg["value"])
				else:
					apply(msg["cell"], msg["value"])
		except websockets.exceptions.ConnectionClosed:
			pass

	def _thread_main (self) -> None:
		self.link_loop = asyncio.new_event_loop()
		asyncio.set_event_loop(self.link_loop)
		self.link_loop.run_until_complete(self.link())

	async def start (self) -> None:
		if self.threaded:
			threading.Thread(target=self._thread_main, daemon=True, name="ws-adapter").start()
			await asyncio.get_running_loop().run_in_executor(None, self.ready.wait, 10.0)
		else:
			self.link_loop = self.loop
			self.task = asyncio.create_task(self.link())
			await asyncio.get_running_loop().run_in_executor(None, self.ready.wait, 10.0)

	def on_beat (self, beat: int) -> None:
		if self.ws is None:
			return
		payload = frame()
		state["pushed"] += 1
		if self.threaded:
			# hand the send to the link's loop; the clock loop does no socket I/O
			asyncio.run_coroutine_threadsafe(self.ws.send(payload), self.link_loop)
		else:
			asyncio.ensure_future(self.ws.send(payload))

	async def stop (self) -> None:
		if self.ws is not None:
			if self.threaded:
				asyncio.run_coroutine_threadsafe(self.ws.close(), self.link_loop)
			else:
				await self.ws.close()


class TcpThread (Adapter):
	"""Outbound TCP link, newline-delimited JSON, stdlib only, reader thread."""

	async def start (self) -> None:
		self.sock = None
		for _ in range(50):
			try:
				self.sock = socket.create_connection(("127.0.0.1", TCP_PORT), timeout=2.0)
				break
			except OSError:
				await asyncio.sleep(0.1)
		if self.sock is None:
			return
		self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
		self.sock.settimeout(None)
		self.out_q: "queue.SimpleQueue" = queue.SimpleQueue()
		threading.Thread(target=self._reader, daemon=True, name="tcp-adapter-rx").start()
		threading.Thread(target=self._writer, daemon=True, name="tcp-adapter-tx").start()

	def _reader (self) -> None:
		buf = b""
		try:
			while True:
				chunk = self.sock.recv(65536)
				if not chunk:
					return
				buf += chunk
				while b"\n" in buf:
					line, buf = buf.split(b"\n", 1)
					msg = json.loads(line)
					state["inbound"] += 1
					self.loop.call_soon_threadsafe(apply, msg["cell"], msg["value"])
		except (OSError, ValueError):
			return

	def _writer (self) -> None:
		try:
			while True:
				payload = self.out_q.get()
				if payload is None:
					return
				self.sock.sendall(payload.encode() + b"\n")
		except OSError:
			return

	def on_beat (self, beat: int) -> None:
		if self.sock is None:
			return
		self.out_q.put(frame())
		state["pushed"] += 1

	async def stop (self) -> None:
		if self.sock is not None:
			self.out_q.put(None)
			try:
				self.sock.shutdown(socket.SHUT_RDWR)
			except OSError:
				pass
			self.sock.close()


SCENARIOS = {
	"baseline": (None, None),
	"osc-loop": ("osc", lambda loop: OscLoop(loop)),
	"osc-thread": ("osc", lambda loop: OscThread(loop, drain=False)),
	"osc-thread-drain": ("osc", lambda loop: OscThread(loop, drain=True)),
	"ws-loop": ("ws", lambda loop: WsLink(loop, threaded=False)),
	"ws-thread": ("ws", lambda loop: WsLink(loop, threaded=True)),
	"tcp-thread": ("tcp", lambda loop: TcpThread(loop)),
}


async def run (scenario: str, bpm: float, bars: int, rate: float) -> dict:
	kind, factory = SCENARIOS[scenario]
	jitter: list = []
	total_seconds = (60.0 / bpm) * 4 * bars
	loop = asyncio.get_running_loop()
	sender = None
	adapter = None
	if kind is not None:
		sender = spawn_sender(kind, rate, total_seconds + 3.0)
		await asyncio.sleep(0.3)
		adapter = factory(loop)
		await adapter.start()
	seq = subsequence.sequencer.Sequencer(output_device_name="NO-SUCH-DEVICE-XYZ", initial_bpm=bpm, spin_wait=True, _jitter_log=jitter)
	seq_ref[0] = seq
	if adapter is not None:
		seq.on_event("beat", adapter.on_beat)
	await seq.start()
	try:
		await asyncio.wait_for(asyncio.shield(seq.task), timeout=total_seconds + 2.0)
	except asyncio.TimeoutError:
		pass
	seq.running = False
	try:
		await asyncio.wait_for(seq.task, timeout=2.0)
	except (asyncio.TimeoutError, asyncio.CancelledError):
		seq.task.cancel()
	if adapter is not None:
		await adapter.stop()
	j = jitter[: bars * 4 * PPQN]
	ms = sorted(x * 1000 for x in j)
	r = {
		"scenario": scenario, "bpm": bpm, "bars": bars, "rate_hz": rate if kind else 0,
		"pulses": len(ms),
		"mean_ms": round(statistics.mean(ms), 4), "median_ms": round(statistics.median(ms), 4),
		"p95_ms": round(ms[int(len(ms) * 0.95)], 4), "p99_ms": round(ms[int(len(ms) * 0.99)], 4),
		"max_ms": round(max(ms), 4), "over_1ms": sum(1 for x in ms if x > 1.0),
		"inbound": state["inbound"], "applied": state["applied"], "pushed": state["pushed"],
	}
	if sender is not None:
		finish_sender(sender, r)
	return r


def main () -> None:
	ap = argparse.ArgumentParser()
	ap.add_argument("scenario", nargs="?", default="baseline")
	ap.add_argument("--bars", type=int, default=16)
	ap.add_argument("--bpm", type=float, default=120.0)
	ap.add_argument("--rate", type=float, default=50.0)
	ap.add_argument("--send", default=None)
	ap.add_argument("--seconds", type=float, default=10.0)
	ap.add_argument("--selector", default="epoll", help="epoll (asyncio default on Linux) or select (no 1 ms timeout rounding); diagnostic only")
	a = ap.parse_args()
	if a.send:
		sender_main(a.send, a.rate, a.seconds)
		return
	if a.selector == "select":
		import selectors
		class _Policy (asyncio.DefaultEventLoopPolicy):
			def new_event_loop (self):
				return asyncio.SelectorEventLoop(selectors.SelectSelector())
		asyncio.set_event_loop_policy(_Policy())
	r = asyncio.run(run(a.scenario, a.bpm, a.bars, a.rate))
	r["selector"] = a.selector
	print(json.dumps(r), flush=True)


if __name__ == "__main__":
	main()
