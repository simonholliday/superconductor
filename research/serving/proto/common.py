"""Prototype (not house style): shared state generator for the three candidate servers."""
import json, time, random
CELLS = 128
def snapshot(step):
	return json.dumps({"type": "state", "seq": step, "playhead": step % 16, "grid": [random.random() < 0.3 for _ in range(CELLS)], "t": time.time()})
