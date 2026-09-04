"""PROTOTYPE (research only, not house style, not for the package).

Revision runs for the state-sync design, offline via composition.render()
(simulated clock, fake MIDI backend patched as tests/conftest.py does).

  H7  a muted pattern: _rebuild() returns before the builder, so grid.apply()
      never runs, yet pattern_reschedule still fires; a stamp taken in apply()
      cannot advance, a version recorded at reschedule_pulse can.
  H8  the ordering window: a callback already in the loop's ready queue when the
      pulse handler runs (what a call_soon_threadsafe panel write arriving during
      the pulse looks like) executes after the rebuild and before the spawned
      pattern_reschedule listener, so a panel write can take a version above the
      algorithm's and be emitted first if acks leave at once and algorithm
      changes are drained in the listener.
  H9  an ephemeral algorithm: notes placed beside grid.apply(p) and a mask passed
      to apply() reach pattern.steps and the realised map without touching the
      intent or its version.
"""

import asyncio
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
	def __init__ (self): self.sent = []
	def send (self, m): self.sent.append(m)
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
	"""Stand-in for StepGrid with the revision's stamps: built_ver in apply(), an applied flag, a pre-rebuild version."""

	def __init__ (self, steps: int, cells):
		self.steps = steps
		self.cells = {r: dict(c) for r, c in cells.items()}
		self.ver = 0
		self.log: typing.List[dict] = []
		self.touched: typing.Dict[typing.Tuple[str, int], str] = {}
		self.built_ver = 0
		self.applied = False
		self.apply_calls = 0
		self.pulse_of = lambda: -1

	def set (self, row: str, step: int, on: bool, by: str) -> int:
		row_cells = self.cells.setdefault(row, {})
		before = step in row_cells
		if on:
			row_cells[step] = {"v": 100}
		else:
			row_cells.pop(step, None)
		if before != on:
			self.ver += 1
			self.log.append({"ver": self.ver, "path": f"{row}/{step}", "on": on, "by": by, "pulse": self.pulse_of()})
			self.touched[(row, step)] = by
		return self.ver

	def apply (self, p, skip: typing.Optional[typing.Set[typing.Tuple[str, int]]] = None):
		self.apply_calls += 1
		for row, cs in self.cells.items():
			idx = sorted(i for i in cs if not (skip and (row, i) in skip))
			if idx:
				p.sequence(idx, row, velocities=[cs[i]["v"] for i in idx], grid=self.steps)
		self.built_ver = self.ver
		self.applied = True
		self.touched.clear()


def realised (pattern, steps: int):
	pps = pattern.length * PPQ / steps
	out: typing.Dict[str, typing.List[int]] = {}
	off_grid = 0
	for pulse, step in pattern.steps.items():
		if pulse % pps != 0:
			off_grid += len(step.notes)
			continue
		for n in step.notes:
			out.setdefault(n.origin or REVERSE.get(n.pitch, str(n.pitch)), []).append(int(pulse // pps))
	return {k: sorted(v) for k, v in sorted(out.items())}, off_grid


def make (algorithm: str):
	comp = subsequence.Composition(output_device="Dummy MIDI", bpm=120)
	grid = MiniGrid(16, {"kick": {0: {"v": 100}, 4: {"v": 100}, 8: {"v": 100}}, "snare": {4: {"v": 100}, 12: {"v": 100}}})
	grid.pulse_of = lambda: comp.sequencer.pulse_count
	comp.data["superintendent"] = {"drums": grid}
	order: typing.List[str] = []

	@comp.pattern(channel=10, steps=16, step_duration=dur.SIXTEENTH, drum_note_map=DRUMS, reschedule_lookahead=1/PPQ)
	def drums (p):
		g: MiniGrid = p.data["superintendent"]["drums"]
		if algorithm == "persistent":
			g.set("kick", 4, False, by="algorithm")
			order.append(f"builder: algorithm set kick/4 off -> ver {g.ver} (pulse {comp.sequencer.pulse_count})")
			g.apply(p)
		elif algorithm == "ephemeral":
			g.apply(p, skip={("kick", 4)})                 # subtraction without touching intent
			p.hit_steps("hat", [2, 6, 10, 14], velocity=70)    # addition without touching intent
		else:
			g.apply(p)

	return comp, grid, order


def run (comp, grid, bars, on_pulse=None, on_reschedule_pulse=None, on_pattern_reschedule=None):
	log = []
	st = {"rp": None, "pre_ver": None}

	def _rp (pulse, patterns):
		st["rp"] = pulse
		st["pre_ver"] = grid.ver          # the version every rebuild on this pulse starts from
		grid.applied = False
		if on_reschedule_pulse: on_reschedule_pulse(pulse, patterns)

	async def _pr (pattern, cycle_start):
		real, off = realised(pattern, grid.steps)
		entry = {"cycle_start": cycle_start, "rebuild_pulse": st["rp"], "listener_pulse": comp.sequencer.pulse_count,
		         "pre_ver": st["pre_ver"], "applied": grid.applied, "built_ver_stamp": grid.built_ver,
		         "muted": pattern._muted, "steps_empty": not pattern.steps, "ver": grid.ver,
		         "intent": {r: sorted(c) for r, c in grid.cells.items() if c}, "realised": real, "off_grid": off}
		log.append(entry)
		if on_pattern_reschedule: on_pattern_reschedule(entry)

	async def on_start ():
		if on_pulse:
			await comp.sequencer.schedule_callback_repeating(on_pulse, 1 / PPQ, start_pulse=0, reschedule_lookahead=0)

	comp.on_event("reschedule_pulse", _rp)
	comp.on_event("pattern_reschedule", _pr)
	comp.on_event("start", on_start)
	comp.render(bars=bars, max_minutes=None, filename="/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad/state-sync/render_rev.mid")
	return log


def show (title, log, grid):
	print(f"\n=== {title}")
	for e in log:
		print(f"  cycle_start={e['cycle_start']:4d} rebuilt_at={e['rebuild_pulse']} listener_at={e['listener_pulse']} muted={e['muted']} applied={e['applied']} pre_ver={e['pre_ver']} built_ver_stamp={e['built_ver_stamp']} ver={e['ver']} steps_empty={e['steps_empty']} intent={e['intent']} realised={e['realised']} off_grid={e['off_grid']}")
	print("  changed frames:", [(c["ver"], c["path"], c["on"], c["by"], c["pulse"]) for c in grid.log])


# H7 --------------------------------------------------------------------------
comp, grid, _ = make("none")
done = set()
def h7 (pulse):
	if pulse == 100 and "m" not in done:
		done.add("m"); comp.mute("drums")
	if pulse == 150 and "s" not in done:
		done.add("s"); grid.set("clap", 6, True, by="panel")     # a tap while muted
	if pulse == 250 and "u" not in done:
		done.add("u"); comp.unmute("drums")
log = run(comp, grid, 4, on_pulse=h7)
show("H7 muted from 100 to 250, panel sets clap/6 at 150: apply() skipped while muted, listener still fires", log, grid)
print(f"  apply() calls over 4 rebuilds: {grid.apply_calls}")

# H8 --------------------------------------------------------------------------
comp, grid, order = make("persistent")
done = set()
def h8_rp (pulse, patterns):
	if pulse == 95 and "w" not in done:
		done.add("w")
		loop = asyncio.get_running_loop()
		def panel_write ():
			v = grid.set("kick", 4, True, by="panel")
			order.append(f"ready-queue callback: panel set kick/4 on -> ver {v} (pulse {comp.sequencer.pulse_count}); an ack sent here would carry ver {v}")
		loop.call_soon(panel_write)          # already queued when the rebuild runs, as a call_soon_threadsafe arrival during this pulse would be
		order.append(f"reschedule_pulse listener at pulse {pulse}: queued a panel write")
def h8_pr (entry):
	if entry["cycle_start"] == 96:
		order.append(f"pattern_reschedule listener (pulse {entry['listener_pulse']}): drains algorithm log here; log order = {[(c['ver'], c['by']) for c in grid.log]}")
log = run(comp, grid, 2, on_reschedule_pulse=h8_rp, on_pattern_reschedule=h8_pr)
print("\n=== H8 ordering window at the rebuild for cycle 96")
for line in order:
	print("  " + line)
print(f"  intent kick after cycle-96 rebuild: {sorted(grid.cells['kick'])} (panel's ver-2 write is the server's value); realised for cycle 96: {log[0]['realised']}")

# H9 --------------------------------------------------------------------------
comp, grid, _ = make("ephemeral")
log = run(comp, grid, 2)
show("H9 ephemeral algorithm: apply(skip=kick/4) plus hit_steps hat beside it; intent and ver untouched", log, grid)
