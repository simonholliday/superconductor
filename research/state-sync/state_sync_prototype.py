"""PROTOTYPE (research only, not house style, not for the package).

Checks the ordering and confirmation semantics of bidirectional grid sync
inside Subsequence's rebuild-every-cycle model, offline via composition.render()
(simulated clock, fake MIDI backend patched as tests/conftest.py does).

A tiny stand-in for the StepGrid helper of #1914 keeps a version counter and a
change log with `by`, so the frames a service would emit can be reconstructed.

Experiments:
  H1  same cell, same cycle: panel sets kick/4 on before the rebuild, the algorithm
      clears kick/4 inside the builder -> who is last writer, every cycle?
  H2  the same, with an algorithm that leaves cells the human touched this cycle alone
  H3  two panels write one cell in one cycle -> loop order decides, one confirmation
  H4  pending duration: a set applied at offset x into a cycle, how many pulses until
      the pattern_reschedule that confirms it (lookahead 1 pulse and 1 beat)
  H5  snapshot taken between rebuild and cycle start: intent and realised differ
  H6  duplicate set (same client, same seq) replayed -> version unchanged
"""

import logging
import sys
import typing

import mido

sys.path.insert(0, "/mnt/dev/Apps/2026-02 Sequencer")

import subsequence
import subsequence.constants.durations as dur

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
PPQ = 24


class SpyOut:
	def __init__ (self): self.sent = []; self.seq = None
	def send (self, m): self.sent.append((self.seq.pulse_count if self.seq else -1, m))
	def close (self): pass
	def panic (self): pass
	def reset (self): pass

_spy = SpyOut()
mido.get_output_names = lambda: ["Dummy MIDI"]
mido.open_output = lambda name: _spy
mido.get_input_names = lambda: ["Dummy MIDI"]
mido.open_input = lambda name, callback=None: None

DRUMS = {"kick": 36, "snare": 38, "hat": 42, "clap": 39}
REVERSE = {v: k for k, v in DRUMS.items()}


class MiniGrid:
	"""Stand-in for StepGrid: sparse cells, version counter, change log, dedup by (client, seq)."""

	def __init__ (self, steps: int, cells: typing.Dict[str, typing.Dict[int, dict]]):
		self.steps = steps
		self.cells: typing.Dict[str, typing.Dict[int, dict]] = {r: dict(c) for r, c in cells.items()}
		self.ver = 0
		self.log: typing.List[dict] = []          # what the service would send as `changed`
		self.touched: typing.Dict[typing.Tuple[str, int], str] = {}   # (row, step) -> by, since last rebuild
		self.seen: typing.Dict[typing.Tuple[str, int], int] = {}      # (client, seq) -> ver of the ack
		self.pulse_of = lambda: -1

	def set (self, row: str, step: int, on: bool, by: str, client: str = "", seq: int = 0, velocity: int = 100) -> int:
		key = (client, seq)
		if client and key in self.seen:
			return self.seen[key]                    # replay: repeat the old ack, no new version
		if not (0 <= step < self.steps) or not isinstance(step, int):
			raise ValueError("bad step")
		row_cells = self.cells.setdefault(row, {})
		before = step in row_cells
		if on:
			row_cells[step] = {"v": velocity}
		else:
			row_cells.pop(step, None)
		if before == on and not (on and before):
			pass
		if before != on:
			self.ver += 1
			self.log.append({"ver": self.ver, "path": f"{row}/{step}", "on": on, "by": by, "pulse": self.pulse_of()})
			self.touched[(row, step)] = by
		if client:
			self.seen[key] = self.ver
		return self.ver

	def apply (self, p):
		for row, cs in self.cells.items():
			if cs:
				idx = sorted(cs)
				p.sequence(idx, row, velocities=[cs[i]["v"] for i in idx], grid=self.steps)


def realised (pattern, steps: int) -> typing.Dict[str, typing.List[int]]:
	pps = pattern.length * PPQ / steps
	out: typing.Dict[str, typing.List[int]] = {}
	for pulse, step in pattern.steps.items():
		for n in step.notes:
			out.setdefault(n.origin or REVERSE.get(n.pitch, str(n.pitch)), []).append(int(round(pulse / pps)))
	return {k: sorted(v) for k, v in sorted(out.items())}


def make (lookahead: float, algorithm: str = "none"):
	comp = subsequence.Composition(output_device="Dummy MIDI", bpm=120)
	_spy.seq = comp.sequencer
	_spy.sent.clear()
	grid = MiniGrid(16, {"kick": {0: {"v": 100}, 8: {"v": 100}}, "snare": {4: {"v": 100}, 12: {"v": 100}}})
	grid.pulse_of = lambda: comp.sequencer.pulse_count
	comp.data["superintendent"] = {"drums": grid}

	@comp.pattern(channel=10, steps=16, step_duration=dur.SIXTEENTH, drum_note_map=DRUMS, reschedule_lookahead=lookahead)
	def drums (p):
		g: MiniGrid = p.data["superintendent"]["drums"]
		if algorithm == "insist":
			g.set("kick", 4, False, by="algorithm")           # clears kick/4 every cycle, whatever the human did
		elif algorithm == "polite":
			if g.touched.get(("kick", 4)) != "panel":
				g.set("kick", 4, False, by="algorithm")
		g.apply(p)

	return comp, grid


def run (comp, grid, bars, before_rebuild=None, after_rebuild=None, on_beat=None):
	log = []
	st = {"rp": None}

	def on_reschedule_pulse (pulse, patterns):
		st["rp"] = pulse
		if before_rebuild: before_rebuild(pulse)

	async def on_pattern_reschedule (pattern, cycle_start):
		log.append({"cycle_start": cycle_start, "rebuild_pulse": st["rp"], "confirm_pulse": comp.sequencer.pulse_count,
		            "ver": grid.ver, "realised": realised(pattern, grid.steps), "intent": {r: sorted(c) for r, c in grid.cells.items() if c}})
		grid.touched.clear()      # a rebuild consumed the touches
		if after_rebuild: after_rebuild(cycle_start, pattern)

	async def on_start ():
		# A repeating callback at one-pulse interval fires inside
		# _maybe_reschedule_patterns before that pulse's pattern rebuilds
		# (sequencer.py:1690-1716 pops and fires callbacks; pattern rebuilds follow at 1776-1829),
		# so a write made here at pulse P is what a panel write applied on the
		# loop just before pulse P's rebuild looks like.
		if on_beat:
			await comp.sequencer.schedule_callback_repeating(on_beat, 1 / PPQ, start_pulse=0, reschedule_lookahead=0)

	comp.on_event("reschedule_pulse", on_reschedule_pulse)
	comp.on_event("pattern_reschedule", on_pattern_reschedule)
	comp.on_event("start", on_start)
	comp.render(bars=bars, max_minutes=None, filename="/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad/state-sync/render.mid")
	return log


def show (title, log, grid):
	print(f"\n=== {title}")
	for e in log:
		print(f"  cycle_start={e['cycle_start']:4d} rebuilt_at={e['rebuild_pulse']} confirmed_at={e['confirm_pulse']} ver={e['ver']} intent={e['intent']} realised={e['realised']}")
	print("  changed frames:", [(c["ver"], c["path"], c["on"], c["by"], c["pulse"]) for c in grid.log])


# H1 --------------------------------------------------------------------------
comp, grid = make(1/PPQ, algorithm="insist")
done = set()
def h1_tap (pulse):
	if pulse == 95 and "a" not in done:          # rebuild for cycle 96 fires at pulse 95 (lookahead 1 pulse)
		done.add("a"); grid.set("kick", 4, True, by="panel", client="A", seq=1)
log = run(comp, grid, 4, before_rebuild=h1_tap)
show("H1 same cell, same cycle: panel on at 95 (before rebuild), algorithm clears inside the builder", log, grid)

# H2 --------------------------------------------------------------------------
comp, grid = make(1/PPQ, algorithm="polite")
done = set()
log = run(comp, grid, 4, before_rebuild=h1_tap)
show("H2 same, algorithm leaves a cell the panel touched this cycle alone", log, grid)

# H3 --------------------------------------------------------------------------
comp, grid = make(1/PPQ)
done = set()
def h3 (pulse):
	if pulse == 120 and "a" not in done:   # inside cycle 96..191, well before its rebuild at 191
		done.add("a"); grid.set("clap", 2, True, by="panel:A", client="A", seq=1)
	if pulse == 144 and "b" not in done:
		done.add("b"); grid.set("clap", 2, False, by="panel:B", client="B", seq=1)
log = run(comp, grid, 4, on_beat=h3)
show("H3 two panels, one cell, one cycle: A on at 120, B off at 144", log, grid)

# H4 --------------------------------------------------------------------------
for la, name in ((1/PPQ, "1 pulse"), (1.0, "1 beat")):
	comp, grid = make(la)
	pending = {}
	offsets = list(range(0, 96, 8)) + [94, 95]
	def h4_tap (pulse):
		x = pulse - 192
		if 0 <= x < 96 and x in offsets and x not in pending:
			grid.set("clap", 1 + (x % 15), True, by="panel", client="A", seq=x + 1)
			pending[x] = {"at": pulse, "seen": None}
	def h4_confirm (cycle_start, pattern):
		r = realised(pattern, grid.steps).get("clap", [])
		for x, rec in pending.items():
			if rec["seen"] is None and (1 + (x % 15)) in r:
				rec["seen"] = comp.sequencer.pulse_count
	log = run(comp, grid, 6, on_beat=h4_tap, after_rebuild=h4_confirm)
	print(f"\n=== H4 pending duration, lookahead {name}, 4-beat cycle (96 pulses), set applied at offset x of cycle 192")
	print("  x(pulses)  set_at  confirmed_at  pending_pulses  pending_beats  ms@120")
	for x in sorted(pending):
		rec = pending[x]
		if rec["seen"] is None: print(f"  {x:3d}  {rec['at']}  never"); continue
		d = rec["seen"] - rec["at"]
		print(f"  {x:3d}  {rec['at']:5d}  {rec['seen']:5d}  {d:4d}  {d/PPQ:5.2f}  {d/PPQ*500:6.0f}")

# H5 --------------------------------------------------------------------------
comp, grid = make(1.0)
done = set()
snap = {}
def h5_tap (pulse):
	if pulse == 172 and "a" not in done:     # after the rebuild at 168, before the cycle start at 192
		done.add("a"); grid.set("clap", 3, True, by="panel", client="A", seq=1)
def h5_snapshot (pulse):
	if pulse == 180:
		pat = comp2.running_patterns["drums"]
		snap["intent"] = {r: sorted(c) for r, c in grid.cells.items() if c}
		snap["realised_next_cycle"] = realised(pat, grid.steps)
		snap["ver"] = grid.ver
log = run(comp, grid, 5, on_beat=h5_tap, before_rebuild=None)
comp2, grid2 = make(1.0)
done = set()
grid = grid2
log2 = run(comp2, grid2, 5, on_beat=lambda pulse: (h5_tap(pulse), h5_snapshot(pulse)))
print("\n=== H5 snapshot at pulse 180 (rebuild for cycle 192 fired at 168; set applied at 172)")
print("  snapshot:", snap)
show("H5 run log", log2, grid2)

# H6 --------------------------------------------------------------------------
comp, grid = make(1/PPQ)
v1 = grid.set("clap", 5, True, by="panel", client="A", seq=7)
v2 = grid.set("clap", 5, True, by="panel", client="A", seq=7)   # replay after a reconnect
v3 = grid.set("clap", 5, True, by="panel", client="B", seq=1)   # another client, same value: no-op set
print(f"\n=== H6 idempotency: first ack ver={v1}, replayed same (client, seq) ack ver={v2}, other client same value ver={v3}, frames={len(grid.log)}")
