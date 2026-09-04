"""Research prototype (transport-ui): size and encode/decode cost of JSON vs MessagePack vs CBOR
for the Superintendent message shapes. Not house style; measurement only."""
import json, time, statistics, random
import msgpack, cbor2

random.seed(1)

def grid(rows, cols):
	return [[random.random() < 0.3 for _ in range(cols)] for _ in range(rows)]

def snapshot(rows, cols):
	return {
		"t": "snapshot", "seq": 12345, "ts": 1756800000.123,
		"controls": {
			"drums.grid": {
				"rows": [f"voice{r}" for r in range(rows)],
				"steps": cols,
				"cells": grid(rows, cols),
			},
			"drums.length": 16,
			"bpm": 124.0,
		},
	}

def delta_toggle():
	return {"t": "set", "seq": 12346, "id": "drums.grid", "cell": [3, 7], "v": True}

def playhead():
	return {"t": "beat", "seq": 12347, "pulse": 4104, "bar": 42, "beat": 3, "ts": 1756800000.123}

def bench(name, obj):
	encs = {
		"json": (lambda o: json.dumps(o, separators=(",", ":")).encode(), lambda b: json.loads(b)),
		"msgpack": (lambda o: msgpack.packb(o), lambda b: msgpack.unpackb(b)),
		"cbor2": (lambda o: cbor2.dumps(o), lambda b: cbor2.loads(b)),
	}
	print(f"\n{name}")
	for k, (enc, dec) in encs.items():
		b = enc(obj)
		n = 2000
		t0 = time.perf_counter()
		for _ in range(n): enc(obj)
		te = (time.perf_counter() - t0) / n * 1e6
		t0 = time.perf_counter()
		for _ in range(n): dec(b)
		td = (time.perf_counter() - t0) / n * 1e6
		print(f"  {k:8s} {len(b):6d} bytes  encode {te:7.1f} us  decode {td:7.1f} us")

bench("snapshot 16x8 (128 cells)", snapshot(8, 16))
bench("snapshot 64x16 (1024 cells)", snapshot(16, 64))
bench("toggle delta", delta_toggle())
bench("beat/playhead", playhead())
# packed-bit alternative for the cells array only, for comparison
cells = grid(8, 16)
bits = bytes(sum((1 << i) for i, v in enumerate(row) if v) & 0xFFFF for row in cells for _ in ())  # placeholder
import struct
packed = b"".join(struct.pack("<H", sum(1 << i for i, v in enumerate(row) if v)) for row in cells)
print(f"\n16x8 cells as packed bits: {len(packed)} bytes; as JSON bool array: {len(json.dumps(cells, separators=(',', ':')))} bytes; as JSON 0/1 flat string: {len(json.dumps(''.join('1' if v else '0' for row in cells for v in row)))} bytes")
