"""Research prototype (not house style): measure when Subsequence's beat, bar and
pattern_reschedule listeners run relative to the ideal pulse time and to the MIDI
send of that pulse, on the wall clock, with a fake MIDI port.  Optionally emulate a
per-pulse event to see what it costs the clock (jitter log).

usage: server_events.py BPM BARS [--pulse-event] [--no-spin]
"""
import asyncio, json, statistics, sys, time
sys.path.insert(0, "/mnt/dev/Apps/2026-02 Sequencer")
import mido

class FakeOut:
	def send (self, m): return None
	def close (self): return None
	def panic (self): return None
	def reset (self): return None

mido.get_output_names = lambda: ["Dummy MIDI"]
mido.open_output = lambda name: FakeOut()
import logging; logging.basicConfig(level=logging.ERROR)
import subsequence.sequencer, subsequence.pattern

BPM = float(sys.argv[1]); BARS = int(sys.argv[2])
PULSE_EVENT = "--pulse-event" in sys.argv
SPIN = "--no-spin" not in sys.argv

def pct (xs, p):
	xs = sorted(xs); return xs[min(len(xs)-1, int(p*len(xs)))]

def summ (xs):
	xs_ms = [x*1000 for x in xs]
	return {"n": len(xs), "median_ms": round(statistics.median(xs_ms),4), "p95_ms": round(pct(xs_ms,0.95),4), "p99_ms": round(pct(xs_ms,0.99),4), "max_ms": round(max(xs_ms),4), "min_ms": round(min(xs_ms),4)}

async def main ():
	jitter = []
	seq = subsequence.sequencer.Sequencer(output_device_name="Dummy MIDI", initial_bpm=BPM, spin_wait=SPIN, _jitter_log=jitter)
	pattern = subsequence.pattern.Pattern(channel=9, length=4, reschedule_lookahead=1/24)
	for row in range(8):
		for step in range(16):
			if (step + row) % 2 == 0:
				pattern.add_note(step*6, 36+row, 100, 3)
	sends = {}
	orig_send = seq._send_midi
	def send (event):
		if event.message_type == 'note_on' and event.pulse not in sends:
			sends[event.pulse] = time.perf_counter()
		orig_send(event)
	seq._send_midi = send
	beats, bars, resched, pulses = [], [], [], []
	seq.on_event("beat", lambda b: beats.append((time.perf_counter(), seq.pulse_count, b)))
	seq.on_event("bar", lambda b: bars.append((time.perf_counter(), seq.pulse_count, b)))
	seq.on_event("pattern_reschedule", lambda p, s: resched.append((time.perf_counter(), seq.pulse_count, s)))
	if PULSE_EVENT:
		seq.on_event("pulse", lambda p: pulses.append((time.perf_counter(), p)))
		orig_adv = seq._advance_pulse
		async def adv ():
			seq._spawn(seq.events.emit_async("pulse", seq.pulse_count))
			await orig_adv()
		seq._advance_pulse = adv
	await seq.schedule_pattern_repeating(pattern, 0)
	await seq.start()
	await asyncio.sleep((60/BPM)*4*BARS)
	seq.running = False
	await seq.task
	spp = seq.seconds_per_pulse
	t0 = seq.start_time
	ideal = lambda pulse: t0 + pulse*spp
	# beat listener: pulse of the beat is the last multiple of 24 at or below pulse_count-1
	beat_late, beat_after_send = [], []
	for t, pc, b in beats:
		bp = ((pc-1)//24)*24
		beat_late.append(t - ideal(bp))
		if bp in sends: beat_after_send.append(t - sends[bp])
	res_late, res_lead = [], []
	for t, pc, start in resched:
		res_late.append(t - ideal(pc-1))
		res_lead.append(ideal(start) - t)
	send_late = [sends[p] - ideal(p) for p in sends]
	out = {"bpm": BPM, "bars": BARS, "spin_wait": SPIN, "pulse_event": PULSE_EVENT, "pulse_ms": round(spp*1000,3),
		"clock_jitter_wake": summ(jitter),
		"note_on_send_vs_ideal": summ(send_late),
		"beat_listener_vs_ideal_pulse": summ(beat_late),
		"beat_listener_after_note_on_send": summ(beat_after_send),
		"pattern_reschedule_listener_vs_ideal_pulse": summ(res_late),
		"pattern_reschedule_lead_before_cycle_start": summ(res_lead),
		"beats": len(beats), "bars_seen": len(bars), "reschedules": len(resched)}
	if PULSE_EVENT:
		out["pulse_listener_vs_ideal_pulse"] = summ([t - ideal(p) for t, p in pulses])
	print(json.dumps(out, indent=1))

asyncio.run(main())
