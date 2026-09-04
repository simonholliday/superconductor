"""Research prototype for the latency point of Superintendent. Not house style.

Assembles the per-hop budgets from the measured terms (results/pad_chain_*.json,
sibling findings) and the cited terms, and prints the totals used in the
finding. Every number here is either measured in this scratchpad, quoted from a
sibling Subroutine document, or cited in the finding beside its source.
"""

import json
import statistics
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
	rows = json.load(open(os.path.join(HERE, "results", name)))["rows"]
	def rng(k):
		xs = [r[k] for r in rows if r[k] is not None]
		return min(xs), statistics.median(xs), max(xs)
	return rng


def fmt(t):
	return f"{t[0]:.1f} / {t[1]:.1f} / {t[2]:.1f}"


def add(*terms):
	return tuple(sum(t[i] for t in terms) for i in range(3))


# Measured here (run 2 unless stated), min / median / max in ms.
ct = load("pad_chain_chromium_touch.json")
cm = load("pad_chain_chromium_mouse.json")
ft = load("pad_chain_firefox_touch.json")

# Cited or sibling-measured terms, min / median / max.
FRAME = (0.0, 8.35, 16.7)          # wait for the next rAF at 60 Hz, uniform (measured cadence 16.7)
VSYNC = (16.7, 16.7, 16.7)         # one vsync from commit to glass (web.dev, #1924)
GTG = (5.0, 5.0, 5.0)              # panel pixel response, 5 ms GTG (#1917)
PANEL_IN = (0.0, 0.0, 35.0)        # touch-down latency: unmeasured; Windows 10 guideline <= 35 ms active (Microsoft)
LAN_WIRE = (0.5, 1.0, 1.8)         # one LAN hop, ICMP on this LAN (#1920)
WIFI_TAIL = (0.0, 0.0, 80.0)       # Wi-Fi queueing tail (#1920, Shen and Meng)
MIDI_HOP = (0.04, 0.235, 0.917)    # mido output into the virtual port, same process (#1937)
DISPATCH = (0.0, 0.5, 1.0)         # Subsample MIDI dispatch, under 1 ms (README)
HANDLING = (0.0, 0.5, 1.0)         # Subsample per-note handling, well under 1 ms (README)
OUT_128 = (2.7, 2.9, 2.9 * 3)      # PortAudio period at 128 frames; total is a small multiple (README)
OUT_256 = (5.3, 5.8, 5.8 * 3)
OUT_512 = (10.7, 11.6, 11.6 * 3)
OUT_1024 = (21.3, 23.2, 23.2 * 3)
WAN_NEAR = (13.6 / 2, 15.3 / 2, 24.4 / 2)   # one way, half the measured RTT to a nearby WAN echo (#1920)
WAN_FAR = (96.8 / 2, 98.6 / 2, 111.2 / 2)

print("== Case 1: visual acknowledgement of a step tap (software terms measured in headless browsers on the workstation)")
for name, r in [("Chromium 151, synthetic touch", ct), ("Chromium 151, mouse", cm), ("Firefox 153, synthetic touch", ft)]:
	sw = r("input_to_commit")
	print(f"  {name}: input timestamp -> commit {fmt(sw)}")
	glass = add(sw, VSYNC, GTG)
	print(f"     + one vsync + 5 ms GTG = finger event -> glass, panel input excluded: {fmt(glass)}")
	print(f"     + panel touch-down latency 0..35 ms (guideline bound, unmeasured): {fmt(add(glass, PANEL_IN))}")
print("  Thresholds: direct-touch tapping JND 69 ms (Deber 2015), 64 ms mean and 20..40 ms window (Jota 2013)")

print("\n== Case 2: pad hit, tap to sound")
for name, r in [("Chromium 151, synthetic touch", ct), ("Chromium 151, mouse", cm), ("Firefox 153, synthetic touch", ft)]:
	to_send = add(r("input_to_handler"), r("handler_to_class"), r("class_to_send"))
	to_adapter = r("send_to_adapter")
	print(f"  {name}:")
	print(f"     input -> WebSocket send: {fmt(to_send)}")
	print(f"     send -> service -> adapter (loopback): {fmt(to_adapter)}")
	base = add(to_send, to_adapter, MIDI_HOP, DISPATCH, HANDLING)
	print(f"     software to Subsample's mixer, all on one host: {fmt(base)}")
	for label, out in [("128", OUT_128), ("256", OUT_256), ("512", OUT_512), ("1024", OUT_1024)]:
		print(f"        + output latency at buffer_frames={label} (period..3 periods): {fmt(add(base, out))}"
		      f"   | + wired LAN hop {fmt(add(base, out, LAN_WIRE))}   | + panel input 0..35 {fmt(add(base, out, LAN_WIRE, PANEL_IN))}")
	print(f"     Wi-Fi tail adds up to {WIFI_TAIL[2]:.0f} ms; WAN one way adds {fmt(WAN_NEAR)} nearby, {fmt(WAN_FAR)} distant")
print("  Thresholds: 10 ms and 1 ms jitter (Wessel and Wright 2002); 0 and 10 ms rated alike, 10+-3 and 20 ms worse (Jack et al. 2016 via Schmid 2024);"
      " drums good <= 8..9 ms, fair <= 24.5..25 ms (Lester and Boley 2007, 85 percent confidence); JND 20..30 ms theremin (Maki-Patola 2004)")
