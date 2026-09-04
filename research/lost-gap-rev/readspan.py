"""Verification probe: how much of ws-batch-read's crossing is the _recv_now
read pattern rather than the batching device?  Measures the span from the
first frame of a burst being taken off the connection to the last, under the
two read patterns the block uses.  Server on 9271, nothing else touched."""
import asyncio, json, statistics, sys, time
import websockets, websockets.asyncio.client, websockets.asyncio.server

PORT = 9271  # private to this probe; not one of the reserved ports
BURST = 1024
NBURST = 8

async def server():
    conns = set()
    async def handler(ws):
        conns.add(ws)
        try:
            async for _ in ws: pass
        except Exception: pass
        finally: conns.discard(ws)
    async with websockets.asyncio.server.serve(handler, "127.0.0.1", PORT):
        for _ in range(NBURST):
            await asyncio.sleep(1.0)
            if not conns: continue
            for i in range(BURST):
                websockets.broadcast(conns, json.dumps({"type":"set","cell":i%128,"value":bool(i%2)}))
        await asyncio.sleep(1.0)

class Reader:
    def __init__(self, ws): self.ws = ws; self._pending=None
    MODE = "sleep"
    async def _recv_now(self):
        if self._pending is None:
            self._pending = asyncio.ensure_future(self.ws.recv())
        if Reader.MODE == "sleep":
            for _ in range(3):
                if self._pending.done(): break
                await asyncio.sleep(0)
        else:
            await asyncio.wait({self._pending}, timeout=0)
        if not self._pending.done(): return None
        t = self._pending; self._pending=None
        return t.result()

async def client(mode):
    ws = None
    for _ in range(50):
        try:
            ws = await websockets.asyncio.client.connect(f"ws://127.0.0.1:{PORT}")
            break
        except OSError: await asyncio.sleep(0.1)
    spans = []
    stamps = []
    if mode == "asyncfor":
        n = 0; first = None
        async for raw in ws:
            json.loads(raw)
            t = time.perf_counter()
            if n % BURST == 0: first = t
            stamps.append(t)
            n += 1
            if n % BURST == 0:
                spans.append(t - first)
        return spans, stamps
    else:
        r = Reader(ws)
        while True:
            try:
                raw = await r._pending if r._pending is not None else await ws.recv()
            except Exception: break
            r._pending = None
            batch = [time.perf_counter()]
            json.loads(raw)
            while True:
                nxt = await r._recv_now()
                if nxt is None: break
                json.loads(nxt)
                batch.append(time.perf_counter())
            if len(batch) > 1:
                spans.append(batch[-1] - batch[0])
                stamps.extend(batch)
            if len(spans) >= NBURST: break
        return spans, stamps

async def main():
    mode = sys.argv[1]
    Reader.MODE = "wait" if mode == "batchwait" else "sleep"
    srv = asyncio.ensure_future(server())
    await asyncio.sleep(0.3)
    spans, stamps = await asyncio.wait_for(client(mode), timeout=40)
    srv.cancel()
    print(mode, "bursts", len(spans), "span_ms", [round(s*1000,2) for s in spans])
    if spans:
        print("  median span ms", round(statistics.median(spans)*1000,3),
              " implied cross median (half span)", round(statistics.median(spans)*1000/2,3))

asyncio.run(main())
