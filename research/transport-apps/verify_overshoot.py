"""VERIFIER PROTOTYPE, not house style. Tests the claimed cause of the late pulses:
does an early wake-up of the clock loop (message during the sleep) make the
asyncio.sleep resume later than the 1 ms spin margin, and does the effect vanish
when the selector does not round timeouts to whole milliseconds (SelectSelector)?
Runs osc-loop at 50 msg/s with an instrumented clock. Port 9111 as jitter_probe.py.
"""
import asyncio, json, selectors, statistics, subprocess, sys, time
import pythonosc.dispatcher, pythonosc.osc_server

PPQN = 24
OSC_PORT = 9111
PROBE = __file__.replace("verify_overshoot.py", "jitter_probe.py")

async def run (bpm, seconds, spin, rate, selector_name):
	count = [0]
	disp = pythonosc.dispatcher.Dispatcher()
	def h (addr, *args):
		count[0] += 1
	disp.map("/grid/*", h)
	server = pythonosc.osc_server.AsyncIOOSCUDPServer(("127.0.0.1", OSC_PORT), disp, asyncio.get_running_loop())
	transport, _ = await server.create_serve_endpoint()
	p = subprocess.Popen([sys.executable, PROBE, "--send", "osc", "--rate", str(rate), "--seconds", str(seconds)], stdout=subprocess.PIPE, text=True)
	spp = 60.0 / bpm / PPQN
	start = time.perf_counter() + 0.05
	nxt = start
	end = start + seconds
	rows = []
	last_count = 0
	while nxt < end:
		now = time.perf_counter()
		overshoot = None
		if now < nxt:
			s = nxt - now
			if s > spin:
				target = nxt - spin
				await asyncio.sleep(s - spin)
				overshoot = time.perf_counter() - target
			while time.perf_counter() < nxt:
				pass
		late = time.perf_counter() - nxt
		msgs = count[0] - last_count
		last_count = count[0]
		rows.append((late, overshoot, msgs))
		nxt += spp
		await asyncio.sleep(0)
	transport.close()
	p.communicate(timeout=30)
	rows = rows[PPQN:]
	late_us = [r[0] * 1e6 for r in rows]
	with_msg = [r for r in rows if r[2] > 0 and r[1] is not None]
	no_msg = [r for r in rows if r[2] == 0 and r[1] is not None]
	def ov (rs):
		v = sorted(r[1] * 1e6 for r in rs)
		return {"n": len(v), "p50": round(v[len(v)//2],1), "p99": round(v[int(len(v)*0.99)],1), "max": round(v[-1],1)} if v else {}
	over = [r for r in rows if r[0] > 0.001]
	print(json.dumps({
		"selector": selector_name, "rate": rate, "spin_ms": spin*1e3,
		"pulses": len(rows), "mean_us": round(statistics.fmean(late_us),1),
		"p99_us": round(sorted(late_us)[int(len(late_us)*0.99)],1), "max_us": round(max(late_us),1),
		"over_1ms": len(over), "over_1ms_with_msg_in_sleep": sum(1 for r in over if r[2] > 0),
		"sleep_overshoot_us_with_msg": ov(with_msg), "sleep_overshoot_us_no_msg": ov(no_msg),
		"handled": count[0],
	}), flush=True)

def main ():
	sel = sys.argv[1]
	rate = float(sys.argv[2]) if len(sys.argv) > 2 else 50.0
	spin = float(sys.argv[3]) if len(sys.argv) > 3 else 0.001
	if sel == "select":
		loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
	else:
		loop = asyncio.SelectorEventLoop()
	asyncio.set_event_loop(loop)
	loop.run_until_complete(run(120, 20, spin, rate, sel))
	loop.close()

if __name__ == "__main__":
	main()
