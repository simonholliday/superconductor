"""PROTOTYPE (revision, 2026-09-03, not house style, not for the package).

Measures what benchmarks/clock_jitter.py's _jitter_log cannot see: how late a
pulse's own MIDI dispatch is relative to that pulse's ideal instant, when the
rebuild for that pulse runs inline ahead of it (sequencer.py:1484-1485).

Adds to the verification prototype: the count and message types of the events
dispatched on each rebuild pulse, so "which pulse pays" can be stated in notes
rather than inferred.
"""

import argparse, asyncio, collections, json, logging, statistics, sys, time, typing

logging.basicConfig(level=logging.ERROR)
sys.path.insert(0, "/mnt/dev/Apps/2026-02 Sequencer")

import subsequence
import subsequence.constants.durations as dur
import subsequence.sequencer

PPQN = 24
NO_DEVICE = "NO-SUCH-DEVICE-XYZ-REV"


def make_cells(steps, voices, fill):
	stride = int(round(1.0 / fill))
	out = {}
	for i in range(voices):
		row = {}
		for s in range(steps):
			if (s + i) % stride == 0:
				row[s] = {"v": 90 + (s % 30)}
		out[f"v{i}"] = row
	return out


def build_composition(steps, voices, fill, lookahead, bpm):
	comp = subsequence.Composition(output_device=NO_DEVICE, bpm=bpm)
	drum_map = {f"v{i}": 36 + i for i in range(voices)}
	comp.data["grid"] = {"steps": steps, "cells": make_cells(steps, voices, fill)}

	def grid(p):
		g = p.data["grid"]
		n = int(g["steps"])
		p.set_length(n * dur.SIXTEENTH)
		for voice, row in g["cells"].items():
			if not row:
				continue
			idx = sorted(row)
			vels = [row[i].get("v", 100) for i in idx]
			p.sequence(idx, voice, velocities=vels, grid=n)

	comp.pattern(channel=10, steps=steps, step_duration=dur.SIXTEENTH,
	             drum_note_map=drum_map, reschedule_lookahead=lookahead)(grid)
	return comp


async def run(args):
	jitter: typing.List[float] = []
	total_seconds = (60.0 / args.bpm) * 4 * args.bars

	comp = build_composition(args.steps, args.voices, args.fill, args.lookahead, args.bpm)
	seq = comp._sequencer
	seq._jitter_log = jitter
	pattern = comp._build_pattern_from_pending(comp._pending_patterns[0])

	dispatch: typing.Dict[int, float] = {}
	kinds: typing.Dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
	rebuild_pulses: typing.List[int] = []
	block_us: typing.List[float] = []
	t_block = [0.0]

	orig_dispatch = seq._dispatch_with_compensation

	def wrapped(event):
		now = time.perf_counter()
		ideal = seq.start_time + seq.pulse_count * seq.seconds_per_pulse
		dispatch.setdefault(seq.pulse_count, (now - ideal) * 1000.0)
		kinds[seq.pulse_count][event.message_type] += 1
		orig_dispatch(event)

	seq._dispatch_with_compensation = wrapped  # type: ignore[method-assign]

	orig_schedule = seq.schedule_pattern

	async def timed_schedule(pat, start_pulse):
		r = await orig_schedule(pat, start_pulse)
		if t_block[0]:
			block_us.append((time.perf_counter() - t_block[0]) * 1e6)
		return r

	seq.schedule_pattern = timed_schedule  # type: ignore[method-assign]

	def on_reschedule_pulse(pulse, patterns):
		t_block[0] = time.perf_counter()
		rebuild_pulses.append(pulse)

	seq.on_event("reschedule_pulse", on_reschedule_pulse)

	await seq.start()
	await seq.schedule_pattern_repeating(pattern, 0)

	try:
		await asyncio.wait_for(asyncio.shield(seq.task), timeout=total_seconds + 2.0)
	except asyncio.TimeoutError:
		pass

	seq.running = False
	if seq.task and not seq.task.done():
		try:
			await asyncio.wait_for(seq.task, timeout=2.0)
		except (asyncio.TimeoutError, asyncio.CancelledError):
			seq.task.cancel()
	if seq.midi_out:
		seq.midi_out.close(); seq.midi_out = None

	rebuilt = set(rebuild_pulses)
	on_rebuild = [v for k, v in dispatch.items() if k in rebuilt]
	other = [v for k, v in dispatch.items() if k not in rebuilt]
	ms = sorted(x * 1000.0 for x in jitter)
	ev_on_rebuild = collections.Counter()
	for p in rebuilt:
		ev_on_rebuild.update(kinds.get(p, {}))

	def stat(vals):
		if not vals: return {}
		s = sorted(vals)
		return {"n": len(s), "median": round(statistics.median(s), 3),
		        "p95": round(s[min(int(len(s) * 0.95), len(s) - 1)], 3),
		        "max": round(s[-1], 3)}

	return {
		"steps": args.steps, "voices": args.voices, "fill": args.fill,
		"lookahead": args.lookahead, "bpm": args.bpm, "bars": args.bars,
		"notes_per_cycle": sum(len(s.notes) for s in pattern.steps.values()),
		"rebuilds": len(rebuild_pulses),
		"rebuild_pulses_first4": rebuild_pulses[:4],
		"events_on_rebuild_pulses": dict(ev_on_rebuild),
		"pulses_carrying_events": len(dispatch),
		"jitter_log_median_ms": round(statistics.median(ms), 4),
		"jitter_log_p95_ms": round(ms[min(int(len(ms)*0.95), len(ms)-1)], 4),
		"jitter_log_p99_ms": round(ms[min(int(len(ms) * 0.99), len(ms) - 1)], 4),
		"jitter_log_max_ms": round(ms[-1], 4),
		"jitter_log_over_1ms": sum(1 for x in ms if x > 1.0),
		"block_ms": {k: round(v / 1000.0, 3) for k, v in stat(block_us).items()} if block_us else {},
		"dispatch_on_rebuild_pulses_ms": stat(on_rebuild),
		"dispatch_other_pulses_ms": stat(other),
		"raw_on_rebuild_ms": [round(x, 3) for x in on_rebuild],
		"load_at_start": round(__import__("os").getloadavg()[0], 2),
		"label": args.label,
	}


def _fraction(text):
	if "/" in text:
		n, d = text.split("/", 1); return float(n) / float(d)
	return float(text)


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("--steps", type=int, default=16)
	ap.add_argument("--voices", type=int, default=8)
	ap.add_argument("--fill", type=float, default=0.5)
	ap.add_argument("--lookahead", type=_fraction, default=1.0)
	ap.add_argument("--bars", type=int, default=16)
	ap.add_argument("--bpm", type=float, default=120.0)
	ap.add_argument("--label", default="")
	print(json.dumps(asyncio.run(run(ap.parse_args()))), flush=True)


if __name__ == "__main__":
	main()
