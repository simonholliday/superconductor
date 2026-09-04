"""PROTOTYPE: a cell with velocity 300 and a step beyond the grid, rendered offline — what is contained where."""
import sys, logging
sys.path.insert(0, "/mnt/dev/Apps/2026-02 Sequencer")
import mido
logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(name)s: %(message)s")
sent = []
class Spy:
	def send (self, m): sent.append((comp.sequencer.pulse_count, m))
	def close (self): pass
	def panic (self): pass
	def reset (self): pass
mido.get_output_names = lambda: ["Dummy MIDI"]
mido.open_output = lambda name: Spy()
import subsequence, subsequence.constants.durations as dur
comp = subsequence.Composition(output_device="Dummy MIDI", bpm=120)
@comp.pattern(channel=10, steps=16, step_duration=dur.SIXTEENTH, drum_note_map={"kick": 36, "snare": 38})
def drums (p):
	p.hit_steps("kick", [0, 8], velocity=100)
	p.hit_steps("snare", [4], velocity=300)      # bad velocity
	p.hit_steps("kick", [20], velocity=90)       # beyond the 16-step grid
comp.render(bars=2, max_minutes=None, filename="/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad/subsequence-grid/v.mid")
ons = [(pulse, m.note, m.velocity) for pulse, m in sent if m.type == "note_on"]
print("note_ons (pulse, note, vel):", ons)
