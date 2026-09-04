"""PROTOTYPE (revision, 2026-09-04, not house style, not for the package).

Measures the quantity benchmarks/clock_jitter.py's _jitter_log cannot see: how
late a pulse's own MIDI dispatch is, relative to that pulse's ideal instant,
when a grid pattern's rebuild runs inline ahead of it (sequencer.py:1484-1485).

Also records, per pulse, how late the loop is when it goes to sleep, so the
wake lateness recorded in the jitter log can be checked against the epoll
rounding model (selectors.py rounds an epoll timeout up to a whole millisecond)
rather than guessed at.

Same harness shape as scratchpad/subsequence-grid/gap11/grid_jitter_bench.py:
a real Composition, a real decorator pattern whose builder reads a
StepGrid-shaped sparse cell map out of composition.data, no MIDI port opened.
"""

import argparse, asyncio, collections, json, logging, math, os, statistics, sys, time, typing

logging.basicConfig(level = logging.ERROR)
sys.path.insert(0, "/mnt/dev/Apps/2026-02 Sequencer")

import subsequence
import subsequence.constants.durations as dur
import subsequence.sequencer

PPQN       = 24
NO_DEVICE  = "NO-SUCH-DEVICE-XYZ-SUPERINTENDENT-REV2"


def make_cells (steps, voices, fill):
	stride = int(round(1.0 / fill))
	out = {}
	for i in range(voices):
		row = {}
		for s in range(steps):
			if (s + i) % stride == 0:
				row[s] = {"v": 90 + (s % 30)}
		out[f"v{i}"] = row
	return out


def build_composition (steps, voices, fill, lookahead, bpm, length_beats):
	comp = subsequence.Composition(output_device = NO_DEVICE, bpm = bpm)
	drum_map = {f"v{i}": 36 + i for i in range(voices)}
	comp.data["grid"] = {"steps": steps, "cells": make_cells(steps, voices, fill),
	                     "length": length_beats}

	def grid (p):
		g = p.data["grid"]
		n = int(g["steps"])
		p.set_length(g["length"] if g["length"] else n * dur.SIXTEENTH)
		for voice, row in g["cells"].items():
			if not row:
				continue
			idx  = sorted(row)
			vels = [row[i].get("v", 100) for i in idx]
			p.sequence(idx, voice, velocities = vels, grid = n)

	comp.pattern(channel = 10, steps = steps, step_duration = dur.SIXTEENTH,
	             drum_note_map = drum_map, reschedule_lookahead = lookahead)(grid)
	return comp


def current_mhz ():
	try:
		cpu = int(open("/proc/self/stat").read().rsplit(") ", 1)[1].split()[36])
		return int(open(f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_cur_freq").read()) / 1000.0
	except Exception:
		return 0.0


async def run (args):

	jitter: typing.List[float] = []
	total_seconds = (60.0 / args.bpm) * 4 * args.bars

	if args.scenario == "baseline":
		seq = subsequence.sequencer.Sequencer(output_device_name = NO_DEVICE,
		                                      initial_bpm = args.bpm, spin_wait = True,
		                                      _jitter_log = jitter)
		patterns = []
	else:
		comp = build_composition(args.steps, args.voices, args.fill, args.lookahead,
		                         args.bpm, args.length_beats)
		seq  = comp._sequencer
		seq._jitter_log = jitter
		patterns = [comp._build_pattern_from_pending(pp) for pp in comp._pending_patterns]

	dispatch: typing.Dict[int, float] = {}
	kinds:    typing.Dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
	tail:     typing.Dict[int, float] = {}          # pulse -> ms late when the loop went to sleep
	rebuild_pulses: typing.List[int] = []
	block_us: typing.List[float] = []
	freq_mhz: typing.List[float] = []
	t_block = [0.0]

	orig_dispatch = seq._dispatch_with_compensation

	def wrapped_dispatch (event):
		now   = time.perf_counter()
		ideal = seq.start_time + seq.pulse_count * seq.seconds_per_pulse
		dispatch.setdefault(seq.pulse_count, (now - ideal) * 1000.0)
		kinds[seq.pulse_count][event.message_type] += 1
		orig_dispatch(event)

	seq._dispatch_with_compensation = wrapped_dispatch		# type: ignore[method-assign]

	orig_advance = seq._advance_pulse

	async def wrapped_advance ():
		pulse = seq.pulse_count
		await orig_advance()
		ideal = seq.start_time + pulse * seq.seconds_per_pulse
		tail[pulse] = (time.perf_counter() - ideal) * 1000.0

	seq._advance_pulse = wrapped_advance				# type: ignore[method-assign]

	if patterns:
		orig_schedule = seq.schedule_pattern

		async def timed_schedule (pat, start_pulse):
			t0 = time.perf_counter()
			r  = await orig_schedule(pat, start_pulse)
			if t_block[0]:
				block_us.append((time.perf_counter() - t_block[0]) * 1e6)
				freq_mhz.append(current_mhz())
			return r

		seq.schedule_pattern = timed_schedule			# type: ignore[method-assign]

		def on_reschedule_pulse (pulse, pats):
			t_block[0] = time.perf_counter()
			rebuild_pulses.append(pulse)

		seq.on_event("reschedule_pulse", on_reschedule_pulse)

	await seq.start()
	for pat in patterns:
		await seq.schedule_pattern_repeating(pat, 0)

	try:
		await asyncio.wait_for(asyncio.shield(seq.task), timeout = total_seconds + 2.0)
	except asyncio.TimeoutError:
		pass

	seq.running = False
	if seq.task and not seq.task.done():
		try:
			await asyncio.wait_for(seq.task, timeout = 2.0)
		except (asyncio.TimeoutError, asyncio.CancelledError):
			seq.task.cancel()
	if seq.midi_out:
		seq.midi_out.close()
		seq.midi_out = None

	spp_ms  = seq.seconds_per_pulse * 1000.0
	rebuilt = set(rebuild_pulses)
	on_reb  = [v for k, v in dispatch.items() if k in rebuilt]
	other   = [v for k, v in dispatch.items() if k not in rebuilt]
	ms      = sorted(x * 1000.0 for x in jitter)

	# jitter[i] is the wake lateness at pulse i+1 (it is appended after pulse i
	# has been dispatched and the loop has slept to pulse i+1's instant).
	def wake_at (pulse):
		i = pulse - 1
		return jitter[i] * 1000.0 if 0 <= i < len(jitter) else None

	# Epoll model: the loop sleeps for (remaining - 1 ms) and spins the last
	# millisecond; CPython rounds an epoll timeout UP to a whole millisecond.
	model = []
	for pulse, late_at_tail in sorted(tail.items()):
		w = wake_at(pulse + 1)
		if w is None:
			continue
		remaining = spp_ms - late_at_tail
		if remaining <= 0:
			predicted = -remaining
		else:
			requested = remaining - 1.0
			if requested <= 0:
				predicted = max(0.0, math.ceil(remaining * 1e3) / 1e3 - remaining)
			else:
				predicted = max(0.0, late_at_tail + math.ceil(requested) - spp_ms)
		model.append((pulse, round(late_at_tail, 3), round(predicted, 3), round(w, 3),
		              pulse in rebuilt))

	def stat (vals):
		if not vals:
			return {}
		s = sorted(vals)
		return {"n": len(s), "median": round(statistics.median(s), 3),
		        "p95": round(s[min(int(len(s) * 0.95), len(s) - 1)], 3),
		        "max": round(s[-1], 3)}

	ev = collections.Counter()
	for p in rebuilt:
		ev.update(kinds.get(p, {}))

	reb_model = [m for m in model if m[4]]

	return {
		"label": args.label, "scenario": args.scenario,
		"steps": args.steps, "voices": args.voices, "fill": args.fill,
		"lookahead": args.lookahead, "length_beats": args.length_beats,
		"bpm": args.bpm, "bars": args.bars,
		"notes_per_cycle": sum(len(s.notes) for s in patterns[0].steps.values()) if patterns else 0,
		"rebuilds": len(rebuild_pulses),
		"rebuild_pulses_first4": rebuild_pulses[:4],
		"events_on_rebuild_pulses": dict(ev),
		"pulses_carrying_events": len(dispatch),
		"jitter_median_ms": round(statistics.median(ms), 4),
		"jitter_p95_ms": round(ms[min(int(len(ms) * 0.95), len(ms) - 1)], 4),
		"jitter_p99_ms": round(ms[min(int(len(ms) * 0.99), len(ms) - 1)], 4),
		"jitter_max_ms": round(ms[-1], 4),
		"jitter_over_1ms": sum(1 for x in ms if x > 1.0),
		"pulses_logged": len(ms),
		"block_ms": stat([x / 1000.0 for x in block_us]),
		"dispatch_on_rebuild_pulses_ms": stat(on_reb),
		"dispatch_other_pulses_ms": stat(other),
		"wake_after_rebuild_ms": stat([m[3] for m in reb_model]),
		"wake_after_rebuild_predicted_ms": stat([m[2] for m in reb_model]),
		"raw_on_rebuild_ms": [round(x, 3) for x in on_reb],
		"raw_block_ms": [round(x / 1000.0, 3) for x in block_us],
		"raw_freq_mhz": [round(x) for x in freq_mhz],
		"raw_model_rebuild": reb_model,
		"load_at_start": args.load_at_start,
	}


def _fraction (text):
	if "/" in text:
		n, d = text.split("/", 1)
		return float(n) / float(d)
	return float(text)


def main ():
	ap = argparse.ArgumentParser()
	ap.add_argument("--scenario", default = "grid")
	ap.add_argument("--steps", type = int, default = 16)
	ap.add_argument("--voices", type = int, default = 8)
	ap.add_argument("--fill", type = float, default = 0.5)
	ap.add_argument("--lookahead", type = _fraction, default = 1.0)
	ap.add_argument("--length-beats", type = float, default = None)
	ap.add_argument("--bars", type = int, default = 16)
	ap.add_argument("--bpm", type = float, default = 120.0)
	ap.add_argument("--label", default = "")
	args = ap.parse_args()
	args.load_at_start = round(os.getloadavg()[0], 2)
	print(json.dumps(asyncio.run(run(args))), flush = True)


if __name__ == "__main__":
	main()
