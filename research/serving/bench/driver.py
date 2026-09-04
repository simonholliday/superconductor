"""Run the Subsequence clock-jitter benchmark against each serving stack under load. Prototype.

usage: driver.py OUT.json [bars]
"""

import json
import os
import re
import subprocess
import sys
import threading
import time

import psutil

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(HERE, "..", ".venv", "bin", "python")
SEQ = "/mnt/dev/Apps/2026-02 Sequencer"
BENCH = os.path.join(SEQ, "benchmarks", "clock_jitter.py")
OUT = sys.argv[1]
BARS = int(sys.argv[2]) if len(sys.argv) > 2 else 32
ENV = dict(os.environ, PYTHONPATH=SEQ, PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1")

STACKS = {
	"websockets": ("srv_websockets.py", 18801, []),
	"starlette+uvicorn": ("srv_starlette.py", 18802, []),
	"aiohttp": ("srv_aiohttp.py", 18803, []),
	"quart+hypercorn": ("srv_quart.py", 18804, []),
	"fastapi+uvicorn": ("srv_starlette.py", 18805, ["fastapi"]),
}

# (name, clients, toggle_hz, http_rps, broadcast_hz)
LOADS = [
	("idle-1client", 1, 0, 0, 20),
	("panel-4clients", 4, 10, 20, 20),
	("stress-8clients", 8, 20, 50, 100),
]


def sample(proc: psutil.Process, out: dict, stop: threading.Event) -> None:
	cpu = []
	rss = []
	proc.cpu_percent(None)
	while not stop.is_set():
		time.sleep(0.5)
		try:
			cpu.append(proc.cpu_percent(None))
			rss.append(proc.memory_info().rss)
		except psutil.Error:
			break
	out["cpu_mean_pct"] = round(sum(cpu) / len(cpu), 2) if cpu else None
	out["cpu_max_pct"] = round(max(cpu), 2) if cpu else None
	out["rss_max_mb"] = round(max(rss) / 1e6, 1) if rss else None


def parse(text: str) -> dict:
	res = {}
	for key, label in [("mean_ms", "Mean jitter"), ("median_ms", "Median jitter"), ("stdev_ms", "Std deviation"), ("p95_ms", "P95 jitter"), ("p99_ms", "P99 jitter"), ("max_ms", "Max jitter")]:
		m = re.search(label + r"\s*:\s*([-+0-9.]+) ms", text)
		res[key] = float(m.group(1)) if m else None
	m = re.search(r"Pulses measured\s*:\s*(\d+)", text)
	res["pulses"] = int(m.group(1)) if m else None
	return res


def run_jitter() -> dict:
	t0 = time.time()
	cp = subprocess.run([PY, BENCH, "--bars", str(BARS), "--device", "__superintendent_no_such_device__"], env=ENV, capture_output=True, text=True, timeout=BARS * 3 + 30)
	res = parse(cp.stdout)
	res["wall_s"] = round(time.time() - t0, 1)
	return res


def scenario(name: str, server: list | None, load: tuple | None) -> dict:
	print(f"=== {name}", flush=True)
	result: dict = {"scenario": name}
	srv = None
	ld = None
	stop = threading.Event()
	threads = []
	try:
		if server:
			script, port, extra, bhz = server
			env = dict(ENV, BROADCAST_HZ=str(bhz))
			srv = subprocess.Popen([PY, os.path.join(HERE, script), str(port)] + extra, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
			deadline = time.time() + 20
			while time.time() < deadline:
				line = srv.stdout.readline()
				if "ready" in line:
					break
			time.sleep(0.5)
			result["server"] = {}
			threads.append(threading.Thread(target=sample, args=(psutil.Process(srv.pid), result["server"], stop), daemon=True))
		if load:
			_, clients, thz, rps, _ = load
			ld = subprocess.Popen([PY, os.path.join(HERE, "load.py"), str(server[1]), str(clients), str(thz), str(rps)], env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
			time.sleep(2.0)
			result["load"] = {}
			threads.append(threading.Thread(target=sample, args=(psutil.Process(ld.pid), result["load"], stop), daemon=True))
		for t in threads:
			t.start()
		result["jitter"] = run_jitter()
	finally:
		stop.set()
		for t in threads:
			t.join(timeout=3)
		if ld:
			ld.terminate()
			try:
				out, _ = ld.communicate(timeout=5)
			except subprocess.TimeoutExpired:
				ld.kill()
				out, _ = ld.communicate()
			lines = [l for l in out.splitlines() if l.startswith("{")]
			result["load_stats"] = json.loads(lines[-1]) if lines else {"raw": out[-500:]}
		if srv:
			srv.terminate()
			try:
				out, _ = srv.communicate(timeout=5)
			except subprocess.TimeoutExpired:
				srv.kill()
				out, _ = srv.communicate()
			if out.strip() and out.strip() != "ready":
				result["server_log_tail"] = out[-800:]
	print(json.dumps(result), flush=True)
	return result


def main() -> None:
	results = []
	results.append(scenario("baseline", None, None))
	for sname, (script, port, extra) in STACKS.items():
		if sname == "fastapi+uvicorn":
			loads = LOADS[1:2]
		else:
			loads = LOADS
		for lname, clients, thz, rps, bhz in loads:
			results.append(scenario(f"{sname}/{lname}", (script, port, extra, bhz), (lname, clients, thz, rps, bhz)))
			with open(OUT, "w") as fh:
				json.dump(results, fh, indent=1)
	# hostile: saturate every core with a busy loop
	burn = [subprocess.Popen([PY, "-c", "while True: pass"]) for _ in range(psutil.cpu_count())]
	try:
		results.append(scenario("hostile-all-cores-busy", None, None))
	finally:
		for b in burn:
			b.kill()
	results.append(scenario("baseline-repeat", None, None))
	with open(OUT, "w") as fh:
		json.dump(results, fh, indent=1)
	print("DONE", flush=True)


main()
