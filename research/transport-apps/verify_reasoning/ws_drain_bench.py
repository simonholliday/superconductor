"""VERIFIER PROTOTYPE, not house style.  Adds the recommended shape that the
researcher's adapter_bench.py never ran: a WebSocket client link on a daemon
thread with its own loop, inbound messages queued and drained at the beat
event (C-ws with the drain).  Reuses adapter_bench.py unchanged.
"""
import asyncio, json, queue, sys
sys.path.insert(0, sys.argv[2])
import adapter_bench as ab
import websockets, websockets.asyncio.client

class WsDrain (ab.WsLink):
	def __init__ (self, loop):
		super().__init__(loop, threaded=True)
		self.q = queue.SimpleQueue()

	async def link (self):
		for _ in range(50):
			try:
				self.ws = await websockets.asyncio.client.connect(f"ws://127.0.0.1:{ab.WS_PORT}")
				break
			except OSError:
				await asyncio.sleep(0.1)
		self.ready.set()
		if self.ws is None:
			return
		try:
			async for raw in self.ws:
				msg = json.loads(raw)
				ab.state["inbound"] += 1
				self.q.put((msg["cell"], msg["value"]))
		except websockets.exceptions.ConnectionClosed:
			pass

	def on_beat (self, beat):
		while True:
			try:
				cell, value = self.q.get_nowait()
			except queue.Empty:
				break
			ab.apply(cell, value)
		super().on_beat(beat)

ab.SCENARIOS["ws-thread-drain"] = ("ws", lambda loop: WsDrain(loop))
scenario = sys.argv[1]
r = asyncio.run(ab.run(scenario, 120.0, 16, 50.0))
r["selector"] = "epoll"
print(json.dumps(r), flush=True)
