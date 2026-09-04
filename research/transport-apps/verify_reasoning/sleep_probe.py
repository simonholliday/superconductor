"""VERIFIER PROTOTYPE, not house style.  Tests the finding's stated mechanism:
does a call_soon_threadsafe wake-up during the clock's asyncio.sleep make the
sleep resume past its 1 ms spin margin under epoll, and not under select?
Pure asyncio, no sockets: a thread posts a no-op callback at RATE Hz.
Records per pulse: lateness after the spin, sleep overshoot relative to the
sleep's own target (nxt - spin), and whether a callback ran during that sleep.
"""
import asyncio, json, selectors, statistics, sys, threading, time

PPQN = 24

async def run (bpm, seconds, spin, rate, mode):
	loop = asyncio.get_running_loop()
	flag = [0]
	def cb ():
		flag[0] += 1
	stop = threading.Event()
	def poster ():
		interval = 1.0 / rate
		while not stop.is_set():
			if mode == "wake":
				loop.call_soon_threadsafe(cb)
			time.sleep(interval)
	t = threading.Thread(target=poster, daemon=True)
	t.start()
	spp = 60.0 / bpm / PPQN
	nxt = time.perf_counter() + 0.05
	end = nxt + seconds
	rows = []
	while nxt < end:
		now = time.perf_counter()
		overshoot = None
		flag_before = flag[0]
		if now < nxt:
			s = nxt - now
			if s > spin:
				target = nxt - spin
				await asyncio.sleep(s - spin)
				overshoot = time.perf_counter() - target
			while time.perf_counter() < nxt:
				pass
		late = time.perf_counter() - nxt
		woke = flag[0] - flag_before
		rows.append((late, overshoot, woke))
		nxt += spp
	stop.set()
	rows = rows[PPQN:]
	late_us = sorted(r[0] * 1e6 for r in rows)
	def ov (rs):
		v = sorted(r[1] * 1e6 for r in rs if r[1] is not None)
		return {"n": len(v), "p50": round(v[len(v)//2],1), "p99": round(v[int(len(v)*0.99)],1), "max": round(v[-1],1)} if v else {}
	over = [r for r in rows if r[0] > 0.001]
	print(json.dumps({
		"selector": sys.argv[1], "mode": mode, "rate": rate,
		"pulses": len(rows),
		"late_p99_us": round(late_us[int(len(late_us)*0.99)],1), "late_max_us": round(late_us[-1],1),
		"over_1ms": len(over), "over_1ms_with_wake_in_sleep": sum(1 for r in over if r[2] > 0),
		"sleep_overshoot_us_with_wake": ov([r for r in rows if r[2] > 0]),
		"sleep_overshoot_us_no_wake": ov([r for r in rows if r[2] == 0]),
		"over_1ms_samples_us": [(round(r[0]*1e6), round(r[1]*1e6) if r[1] is not None else None, r[2]) for r in over][:8],
	}), flush=True)

def main ():
	sel, mode = sys.argv[1], sys.argv[2]
	rate = float(sys.argv[3]) if len(sys.argv) > 3 else 50.0
	if sel == "select":
		loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
	else:
		loop = asyncio.SelectorEventLoop()
	asyncio.set_event_loop(loop)
	loop.run_until_complete(run(120, 20, 0.001, rate, mode))
	loop.close()

if __name__ == "__main__":
	main()
