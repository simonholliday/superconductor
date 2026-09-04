"""Reviser prototype for the latency point of Superintendent. Not house style.

Recomputes the finding's tables from the saved runs so every cell is machine
checked, and adds three things the first pass lacked: a stated panel touch-down
allowance inside the pad budget, the off-host sampler variants, and the run 1
versus run 2 comparison the measured table brackets.
"""

import json
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "results")

KEYS = ["input_to_handler", "handler_to_class", "class_to_send", "handler_to_raf",
        "raf_to_commit", "input_to_commit", "send_to_service", "service_to_adapter",
        "send_to_adapter"]


def pct(xs, p):
	s = sorted(xs)
	k = (len(s) - 1) * p
	f = int(k)
	c = min(f + 1, len(s) - 1)
	return s[f] if f == c else s[f] + (s[c] - s[f]) * (k - f)


def load(name):
	return json.load(open(os.path.join(RES, name)))


def stats(d, k):
	xs = [r[k] for r in d["rows"] if r.get(k) is not None]
	return min(xs), statistics.median(xs), pct(xs, 0.95), pct(xs, 0.99), max(xs)


def rng(d, k):
	xs = [r[k] for r in d["rows"] if r.get(k) is not None]
	return min(xs), statistics.median(xs), max(xs)


def add(*t):
	return tuple(sum(x[i] for x in t) for i in range(3))


def fmt(t):
	return f"{t[0]:.1f} / {t[1]:.1f} / {t[2]:.1f}"


CASES = [("chromium/touch", "pad_chain_chromium_touch.json", "run1_pad_chain_chromium_touch.json"),
         ("chromium/mouse", "pad_chain_chromium_mouse.json", "run1_pad_chain_chromium_mouse.json"),
         ("firefox/touch", "pad_chain_firefox_touch.json", "run1_pad_chain_firefox_touch.json"),
         ("firefox/mouse", "pad_chain_firefox_mouse.json", "run1_pad_chain_firefox_mouse.json")]

print("== measured table, run 2 (run 1) : min / median / p95 / p99 / max")
for label, f2, f1 in CASES:
	d2, d1 = load(f2), load(f1)
	print(f"-- {label}  offset run2 {d2['offset_estimate']['off']:+.4f} ms, run1 {d1['offset_estimate']['off']:+.4f} ms;"
	      f" rAF {d2['raf_interval_median']:.2f} median {d2['raf_interval_max']:.2f} max")
	for k in KEYS:
		a, b = stats(d2, k), stats(d1, k)
		print(f"   {k:<18} run2 " + " ".join(f"{v:6.2f}" for v in a) + "  | run1 " + " ".join(f"{v:6.2f}" for v in b))

VSYNC = (16.7, 16.7, 16.7)
GTG = (5.0, 5.0, 5.0)
PANEL_35 = (0.0, 0.0, 35.0)
PANEL_15 = (15.0, 15.0, 15.0)
LAN = (0.5, 1.0, 1.8)
MIDI_HOP = (0.04, 0.235, 0.917)
DISPATCH = (0.0, 0.5, 1.0)
HANDLING = (0.0, 0.5, 1.0)
OUT = {"128": (2.7, 2.9, 8.7), "256": (5.3, 5.8, 17.4), "512": (10.7, 11.6, 34.8), "1024": (21.3, 23.2, 69.6)}

print("\n== tap to glass (browser event -> lit pixel); panel display input lag NOT carried")
for label, f2, _ in CASES[:3]:
	d = load(f2)
	sw = rng(d, "input_to_commit")
	glass = add(sw, VSYNC, GTG)
	print(f"  {label}: commit {fmt(sw)} | glass {fmt(glass)} | + panel touch-down 0..35 {fmt(add(glass, PANEL_35))}"
	      f" | + panel touch-down 15 {fmt(add(glass, PANEL_15))}")

print("\n== pad hit: browser event -> DAC, and finger -> sound with a stated panel allowance")
for label, f2, _ in CASES[:3]:
	d = load(f2)
	to_send = add(rng(d, "input_to_handler"), rng(d, "handler_to_class"), rng(d, "class_to_send"))
	base = add(to_send, rng(d, "send_to_adapter"), MIDI_HOP, DISPATCH, HANDLING)
	print(f"  {label}: event -> send {fmt(to_send)}; software to mixer, one host {fmt(base)}")
	for frames in ("128", "256", "512"):
		one = add(base, OUT[frames])
		lan = add(one, LAN)
		print(f"     {frames:>4} frames: one host {fmt(one)} | + browser LAN hop {fmt(lan)}"
		      f" | + sampler off-host, second hop {fmt(add(lan, LAN))}"
		      f" | finger to sound at panel 15 {fmt(add(lan, PANEL_15))}"
		      f" | at panel 0..35 {fmt(add(lan, PANEL_35))}")
