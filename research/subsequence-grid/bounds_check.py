"""PROTOTYPE: what hit_steps does with out-of-range step indices and velocities."""
import sys
sys.path.insert(0, "/mnt/dev/Apps/2026-02 Sequencer")
import subsequence.pattern, subsequence.pattern_builder
pat = subsequence.pattern.Pattern(channel=9, length=4)
b = subsequence.pattern_builder.PatternBuilder(pattern=pat, cycle=0, default_grid=16, drum_note_map={"kick": 36})
b.hit_steps("kick", [0, 15, 16, 20, -1], grid=16, velocity=100)
print("pulses placed for steps [0,15,16,20,-1] on a 4-beat/16 grid (cycle = 96 pulses):", sorted(pat.steps))
pat2 = subsequence.pattern.Pattern(channel=9, length=4)
b2 = subsequence.pattern_builder.PatternBuilder(pattern=pat2, cycle=0, default_grid=16, drum_note_map={"kick": 36})
for v in (0, 127, 128, 300, -5):
	try:
		b2.hit_steps("kick", [0], velocity=v)
		print(f"velocity {v} -> stored {pat2.steps[0].notes[-1].velocity}")
	except Exception as e:
		print(f"velocity {v} -> raised {type(e).__name__}: {e}")
# 1.5 is not a valid step index type
try:
	b2.hit_steps("kick", [1.5], velocity=100)
	print("float step 1.5 ->", sorted(pat2.steps))
except Exception as e:
	print("float step 1.5 -> raised", type(e).__name__, e)
# dict mutated during iteration -> RuntimeError (the containment case for a concurrent writer)
d = {"kick": [0], "snare": [4]}
try:
	for k, v in d.items():
		d["hat"] = [2]
except RuntimeError as e:
	print("dict grown during iteration ->", type(e).__name__, e)
