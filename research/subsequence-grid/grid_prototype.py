"""PROTOTYPE (research only, not house-style, not for the package).

Measures how a composition.data-driven step grid behaves inside Subsequence's
rebuild-every-cycle model, using composition.render() (offline, simulated
clock, fake MIDI backend patched exactly as tests/conftest.py does).

Experiments:
  A  best-case tap  : written in the reschedule_pulse listener (just before the rebuild)
  B  worst-case tap : written in the pattern_reschedule listener (just after the rebuild)
  C  step-count change 16 -> 12 from the grid, mid-run; what the event heap holds
  D  step count below the lookahead (2 steps = 0.5 beat, lookahead 1 beat) -> containment
  E  garbage grid message -> containment
  F  reschedule_lookahead=0: rebuild on the cycle's first pulse, dispatch same pulse
  G  rebuild cost for 16x8, 32x8, 64x16 grids (offline, perf_counter)
"""

import heapq
import logging
import statistics
import sys
import time
import typing

import mido

sys.path.insert(0, "/mnt/dev/Apps/2026-02 Sequencer")

import subsequence
import subsequence.constants.durations as dur
import subsequence.pattern
import subsequence.pattern_builder

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

PPQ = 24


class SpyOut:
	def __init__ (self):
		self.sent = []
		self.seq = None
	def send (self, m):
		self.sent.append((self.seq.pulse_count if self.seq else -1, m))
	def close (self): pass
	def panic (self): pass
	def reset (self): pass


_spy = SpyOut()
mido.get_output_names = lambda: ["Dummy MIDI"]
mido.open_output = lambda name: _spy
mido.get_input_names = lambda: ["Dummy MIDI"]
mido.open_input = lambda name, callback=None: None

DRUMS = {"kick": 36, "snare": 38, "hat": 42, "ohat": 46, "clap": 39, "tom": 45, "ride": 51, "rim": 37}
REVERSE = {v: k for k, v in DRUMS.items()}


def realised_grid (pattern, steps: int) -> typing.Dict[str, typing.List[int]]:
	"""Derive the realised grid from pattern.steps (what display.py/web_ui.py do)."""
	pulses_per_step = pattern.length * PPQ / steps
	out: typing.Dict[str, typing.List[int]] = {}
	for pulse, step in pattern.steps.items():
		for note in step.notes:
			name = note.origin or REVERSE.get(note.pitch, str(note.pitch))
			out.setdefault(name, []).append(int(round(pulse / pulses_per_step)))
	return {k: sorted(v) for k, v in sorted(out.items())}


def make_composition (lookahead: float = 1.0, bpm: float = 120):
	comp = subsequence.Composition(output_device="Dummy MIDI", bpm=bpm)
	_spy.seq = comp.sequencer
	_spy.sent.clear()
	comp.data["superintendent"] = {
		"drums": {"steps": 16, "cells": {"kick": [0, 8], "snare": [4, 12]}},
	}

	@comp.pattern(channel=10, steps=16, step_duration=dur.SIXTEENTH, drum_note_map=DRUMS, reschedule_lookahead=lookahead)
	def drums (p):
		grid = p.data["superintendent"]["drums"]
		steps = int(grid["steps"])
		p.set_length(steps * dur.SIXTEENTH)
		# the algorithm's hand: every odd cycle it writes a hat line INTO the grid,
		# so the panel sees it as intent, not just as realised notes.
		if p.cycle % 2 == 1:
			grid["cells"]["hat"] = [i for i in range(steps) if i % 2 == 0]
		for voice, cells in grid["cells"].items():
			p.hit_steps(voice, cells, grid=steps, velocity=100)

	return comp


def run (comp, bars: int, before_rebuild=None, after_rebuild=None):
	"""Render `bars` bars; return the list of (cycle_start_pulse, rebuild_pulse, realised, length, heap_max, heap_len)."""
	log = []
	state = {"last_reschedule_pulse": None}

	def on_reschedule_pulse (pulse, patterns):
		state["last_reschedule_pulse"] = pulse
		if before_rebuild:
			before_rebuild(pulse, comp)

	async def on_pattern_reschedule (pattern, cycle_start_pulse):
		q = comp.sequencer.event_queue
		heap_max = max((e.pulse for e in q), default=-1)
		steps = int(comp.data["superintendent"]["drums"]["steps"]) if isinstance(comp.data["superintendent"]["drums"], dict) else 16
		log.append({
			"cycle_start": cycle_start_pulse,
			"rebuild_pulse": state["last_reschedule_pulse"],
			"realised": realised_grid(pattern, steps),
			"length_beats": pattern.length,
			"heap_max": heap_max,
			"heap_len": len(q),
			"now": comp.sequencer.pulse_count,
		})
		if after_rebuild:
			after_rebuild(cycle_start_pulse, comp)

	comp.on_event("reschedule_pulse", on_reschedule_pulse)
	comp.on_event("pattern_reschedule", on_pattern_reschedule)
	comp.render(bars=bars, max_minutes=None, filename="/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad/subsequence-grid/render.mid")
	return log


def show (title, log):
	print(f"\n=== {title}")
	for e in log:
		print(f"  cycle_start={e['cycle_start']:5d}  rebuilt_at={e['rebuild_pulse']}  len={e['length_beats']:.2f}b  heap_max={e['heap_max']}  heap_len={e['heap_len']}  realised={e['realised']}")


# ---------------------------------------------------------------- A: best case
comp = make_composition()
done = {"a": False}
def tap_before (pulse, comp):
	# tap just BEFORE the rebuild that fires at pulse 168 (cycle 2 -> cycle starting 192)
	if pulse == 168 and not done["a"]:
		done["a"] = True
		comp.data["superintendent"]["drums"]["cells"]["clap"] = [2]
		print(f"  [A] tap written at pulse {pulse} (just before rebuild)")
log = run(comp, 4, before_rebuild=tap_before)
show("A best case: tap lands in the cycle whose rebuild is happening now", log)
first = next(e for e in log if "clap" in e["realised"])
print(f"  -> clap first realised in cycle starting {first['cycle_start']}: tap->cycle start = {first['cycle_start']-168} pulses = {(first['cycle_start']-168)/PPQ} beats")

# ---------------------------------------------------------------- B: worst case
comp = make_composition()
done = {"b": False}
def tap_after (cycle_start, comp):
	# tap just AFTER the rebuild for the cycle starting at 192 (rebuild pulse 168)
	if cycle_start == 192 and not done["b"]:
		done["b"] = True
		comp.data["superintendent"]["drums"]["cells"]["clap"] = [6]
		print(f"  [B] tap written at pulse {comp.sequencer.pulse_count} (just after rebuild for cycle 192)")
log = run(comp, 5, after_rebuild=tap_after)
show("B worst case: tap lands just after a rebuild", log)
first = next(e for e in log if "clap" in e["realised"])
print(f"  -> clap first realised in cycle starting {first['cycle_start']}: tap->cycle start = {first['cycle_start']-168} pulses = {(first['cycle_start']-168)/PPQ} beats")

# ---------------------------------------------------------------- C: step count change
comp = make_composition()
done = {"c": False}
def change_steps (pulse, comp):
	if pulse == 168 and not done["c"]:
		done["c"] = True
		comp.data["superintendent"]["drums"]["steps"] = 12
		comp.data["superintendent"]["drums"]["cells"] = {"kick": [0, 6], "snare": [3, 9]}
		print(f"  [C] steps 16->12 written at pulse {pulse}")
log = run(comp, 6, before_rebuild=change_steps)
show("C step count 16 -> 12 (set_length + grid=) mid-run", log)
starts = [e["cycle_start"] for e in log]
print(f"  cycle start deltas: {[b-a for a,b in zip(starts, starts[1:])]}  (96 = 4 beats, 72 = 3 beats)")

# ---------------------------------------------------------------- D: below lookahead
comp = make_composition()
done = {"d": False}
def shrink_below (pulse, comp):
	if pulse == 168 and not done["d"]:
		done["d"] = True
		comp.data["superintendent"]["drums"]["steps"] = 2
		comp.data["superintendent"]["drums"]["cells"] = {"kick": [0]}
		print(f"  [D] steps -> 2 (0.5 beat < 1 beat lookahead) written at pulse {pulse}")
	if pulse == 264 and done["d"]:
		comp.data["superintendent"]["drums"]["steps"] = 16
		comp.data["superintendent"]["drums"]["cells"] = {"kick": [0, 8]}
		print(f"  [D] steps -> 16 restored at pulse {pulse}")
log = run(comp, 6, before_rebuild=shrink_below)
show("D step count below lookahead: sequencer containment (sequencer.py:1810-1827)", log)

# ---------------------------------------------------------------- E: garbage message
comp = make_composition()
done = {"e": False}
def garbage (pulse, comp):
	if pulse == 168 and not done["e"]:
		done["e"] = True
		comp.data["superintendent"]["drums"] = "garbage"
		print(f"  [E] grid replaced by a string at pulse {pulse}")
	if pulse == 264 and done["e"]:
		comp.data["superintendent"]["drums"] = {"steps": 16, "cells": {"kick": [0, 8]}}
		print(f"  [E] grid restored at pulse {pulse}")
log = run(comp, 6, before_rebuild=garbage)
show("E garbage grid: builder raises, _rebuild containment (composition.py:6093-6100)", log)

# ---------------------------------------------------------------- F: lookahead 0
comp = make_composition(lookahead=0)
log = run(comp, 3)
show("F reschedule_lookahead=0", log)
ons = [(pulse, m) for pulse, m in _spy.sent if m.type == "note_on" and m.note == 36]
print(f"  kick note_on dispatched at pulses: {[p for p,_ in ons][:8]}  (cycle starts: {[e['cycle_start'] for e in log]})")
print(f"  rebuild pulses: {[e['rebuild_pulse'] for e in log]}")

# ---------------------------------------------------------------- F2: lookahead 1 pulse
comp = make_composition(lookahead=1/PPQ)
log = run(comp, 3)
show("F2 reschedule_lookahead=1/24 beat (one pulse)", log)
print(f"  rebuild pulses: {[e['rebuild_pulse'] for e in log]}")

# ---------------------------------------------------------------- G: rebuild cost
def rebuild_cost (steps: int, voices: int, fill: float, iterations: int = 500):
	comp = subsequence.Composition(output_device="Dummy MIDI", bpm=120)
	drum_map = {f"v{i}": 36 + i for i in range(voices)}
	cells = {f"v{i}": [s for s in range(steps) if (s * 7 + i) % int(1/fill) == 0] for i in range(voices)}
	comp.data["g"] = {"steps": steps, "cells": cells}

	@comp.pattern(channel=10, steps=steps, step_duration=dur.SIXTEENTH, drum_note_map=drum_map)
	def grid (p):
		g = p.data["g"]
		p.set_length(g["steps"] * dur.SIXTEENTH)
		for voice, cs in g["cells"].items():
			p.hit_steps(voice, cs, grid=g["steps"], velocity=100)

	pending = comp._pending_patterns[0]
	pattern = comp._build_pattern_from_pending(pending)
	n_notes = sum(len(s.notes) for s in pattern.steps.values())
	times = []
	for _ in range(iterations):
		t0 = time.perf_counter()
		pattern.on_reschedule()
		times.append((time.perf_counter() - t0) * 1e6)
	times.sort()
	return n_notes, statistics.median(times), times[int(len(times)*0.95)], times[-1]

print("\n=== G rebuild cost (this workstation, Python %s, offline, microseconds per full _rebuild)" % sys.version.split()[0])
for steps, voices, fill in [(16, 8, 0.5), (16, 8, 1.0), (32, 8, 0.5), (64, 16, 0.5)]:
	n, med, p95, mx = rebuild_cost(steps, voices, fill)
	print(f"  {steps:3d} x {voices:2d} grid, {n:4d} notes placed: median {med:7.1f} us  p95 {p95:7.1f} us  max {mx:8.1f} us")

# pulse interval reference
for bpm in (60, 120, 180):
	print(f"  pulse interval at {bpm} BPM: {60/bpm/PPQ*1000:.2f} ms")
