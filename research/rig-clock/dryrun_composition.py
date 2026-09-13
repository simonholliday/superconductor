"""A throwaway composition for proving the measurement launcher. Not the rig's."""

import subsequence
import subsequence.constants.durations as dur

composition = subsequence.Composition(output_device="unused", bpm=0)

DRUMS = {f"v{i}": 36 + i for i in range(4)}


def grid (p):  # type: ignore[no-untyped-def]
	for i, voice in enumerate(DRUMS):
		p.sequence([s for s in range(16) if (s + i) % 4 == 0], voice, velocities=[100] * 4, grid=16)


composition.pattern(channel=10, steps=16, step_duration=dur.SIXTEENTH,
                    drum_note_map=DRUMS, reschedule_lookahead=1 / 24)(grid)

if __name__ == "__main__":
	composition.play()
