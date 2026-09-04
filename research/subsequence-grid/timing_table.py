"""PROTOTYPE: analytic tap-to-sound table from the measured mechanics (lookahead la, cycle L)."""
PPQ = 24
rows = []
print("tempo | cycle | lookahead | tap->cycle start best/worst | tap-under-playhead heard after (cells before / inside lookahead window) | confirmation (pattern_reschedule) best/worst")
for bpm in (60, 90, 120, 140, 180):
	beat_ms = 60000 / bpm
	for L in (4, 8, 16):
		for la_name, la in (("1 beat", 1.0), ("1 pulse", 1 / PPQ)):
			best = la * beat_ms
			worst = (L + la) * beat_ms
			same_step = L * beat_ms
			same_step_late = 2 * L * beat_ms
			steps_16th = L * 4
			late_cells = int(round(la / 0.25)) if la >= 0.25 else 0
			print(f"{bpm:3d} | {L:2d} beats ({L/4:.0f} bar) | {la_name:7s} | {best:7.0f} / {worst:7.0f} ms | {same_step:6.0f} ms / {same_step_late:6.0f} ms (last {late_cells} of {steps_16th} cells) | 0 / {L*beat_ms:6.0f} ms")
