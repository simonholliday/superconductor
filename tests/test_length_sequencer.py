"""A pattern's length played by Subsequence's own scheduler, rather than a stand-in (#2526, #2546).

`test_length.py` builds with a stand-in for the pattern builder, and the one thing
it cannot check is the grid's count of where each cycle starts — worked out from
the lengths it gave, never read (#2548).  That count is a model of how Subsequence
schedules a pattern: a cycle starts where the one before it ended, a length holds
until it is set again, a muted pattern goes on counting, and a build that raises
leaves the length it had.  Only the sequencer can say the model is right, so these
render with it and compare every note with pulses worked out by hand from #2548's
rules: a sixteenth is 6 pulses and a bar of 4/4 is 96.

**Each render runs in a child process.**  A render starts its event loop in the
main thread, and a page test that has run on the same worker leaves Playwright's
loop running there (checked on 2026-09-13), so a render in this process would pass
or fail by the order `-n` happened to choose.  **And MIDI is patched in the child**,
because a render otherwise goes looking for its device among the rig's real ports.

Importing Subsequence here is a rig arrangement, as it is for `test_composition.py`
and `test_generators.py`, and CI leaves this file out with them.
"""

import importlib
import json
import pathlib
import subprocess
import sys
import typing

import subsequence
import subsequence.constants.durations
import subsequence.sequencer

import superconductor.subsequence_adapter as adapter


KICK, HAT, SNARE = 36, 42, 38

SEED = {"kick": [0], "hat": [4, 11], "snare": [15]}
"""The drum pattern each render starts from: its first step, two inside it, and its last."""


def _render (scenario: str, where: pathlib.Path) -> dict[str, typing.Any]:
	"""Play *scenario* through Subsequence in a child process, and read back what it sent."""

	done = subprocess.run(
		[sys.executable, __file__, scenario, str(where)],
		capture_output=True, text=True, timeout=120, check=False)

	assert done.returncode == 0, done.stderr[-4000:]

	# A file rather than the child's output, which a sequencer is free to print to.
	return typing.cast(dict[str, typing.Any], json.loads((where / f"{scenario}.json").read_text()))


def _onsets (played: dict[str, typing.Any], below: int) -> list[tuple[int, int]]:
	"""Every note on before *below*, as (pulse, note)."""

	return sorted((pulse, note) for pulse, note, on in played["notes"] if on and pulse < below)


# --- the tests, which read what a child sent ------------------------------------------

def test_a_shortened_pattern_and_two_resyncs_play_where_the_grid_counts_them (
	tmp_path: pathlib.Path) -> None:
	"""Ten steps, a re-sync from a gap longer than the pattern, sixteen again off the bar, and a re-sync back."""

	played = _render("shorten", tmp_path)

	assert _onsets(played, 960) == sorted([
		(0, KICK), (24, HAT), (66, HAT), (90, SNARE),        # cycle 0 at 0, the whole window
		(96, KICK), (120, HAT), (162, HAT), (186, SNARE),    # 1 at 96
		(192, KICK), (216, HAT),                             # 2 at 192, ten steps: 11 and 15 are past the end
		(252, KICK), (276, HAT),                             # 3 at 252
		(324, KICK), (348, HAT),                             # 4 at 312, re-sync: twelve steps from step 8, round at 10
		(384, KICK), (408, HAT),                             # 5 at 384, on bar 4
		(444, KICK), (468, HAT),                             # 6 at 444
		(504, KICK), (528, HAT), (570, HAT), (594, SNARE),   # 7 at 504, sixteen again and a quarter off the bar
		(600, KICK), (624, HAT), (666, HAT), (690, SNARE),   # 8 at 600
		(696, HAT), (738, HAT), (762, SNARE),                # 9 at 696, re-sync: twelve steps from step 4
		(768, KICK), (792, HAT), (834, HAT), (858, SNARE),   # 10 at 768, on bar 8
		(864, KICK), (888, HAT), (930, HAT), (954, SNARE),   # 11 at 864
	])
	assert [start for start in played["starts"] if start < 960] == \
		[96, 192, 252, 312, 384, 444, 504, 600, 696, 768, 864], "the grid's count is not the sequencer's"

	# **Where the page is told each cycle starts, in beats**: every cycle the page's
	# own count would draw wrongly, and the first back in step.
	assert played["cycles"] == [
		[8.0, 0, 10], [10.5, 0, 10], [13.0, 8, 10], [16.0, 0, 10], [18.5, 0, 10],
		[21.0, 0, 16], [25.0, 0, 16], [29.0, 4, 16], [32.0, 0, 16]]
	assert played["reports"] == [["grid/resync", False], ["grid/resync", False]]
	assert played["length"] == [4.0, 16], "the pattern was not given its whole window back"


def test_a_muted_pattern_goes_on_counting_and_still_comes_back_onto_the_bar (
	tmp_path: pathlib.Path) -> None:
	"""Seven steps, four cycles muted, then a re-sync: the builds a mute skips are counted at the length it had."""

	played = _render("mute", tmp_path)
	onsets = _onsets(played, 768)

	assert [one for one in onsets if 222 <= one[0] < 390] == [], "a muted cycle sounded"
	assert [one for one in onsets if not 180 <= one[0] < 390] == sorted([
		(0, KICK), (24, HAT), (66, HAT), (90, SNARE),        # cycle 0 at 0
		(96, KICK), (120, HAT),                              # 1 at 96, seven steps
		(138, KICK), (162, HAT),                             # 2 at 138
		(390, KICK), (414, HAT),                             # 8 at 390, the first build after four muted ones
		(432, KICK), (456, HAT),                             # 9
		(474, KICK), (498, HAT),                             # 10
		(516, HAT), (534, KICK), (558, HAT),                 # 11 at 516, re-sync: ten steps from step 4, round at 7
		(576, KICK), (600, HAT),                             # 12 at 576, on bar 6
		(618, KICK), (642, HAT),                             # 13
		(660, KICK), (684, HAT),                             # 14
		(702, KICK), (726, HAT),                             # 15
		(744, KICK),                                         # 16 at 744
	])
	assert [start for start in played["starts"] if start < 768] == \
		[96, 138, 180, 222, 264, 306, 348, 390, 432, 474, 516, 576, 618, 660, 702, 744]


def test_a_pitched_note_is_cut_at_the_end_and_moved_into_a_resync_s_gap (
	tmp_path: pathlib.Path) -> None:
	"""A note grid in pulses: a five-step note cut to two at a twelve-step end, and played in the gap."""

	played = _render("notes", tmp_path)

	assert sorted((pulse, on) for pulse, _, on in played["notes"] if pulse < 288) == sorted([
		(0, 1), (6, 0), (60, 1), (90, 0),        # cycle 0 at 0, whole
		(96, 1), (102, 0), (156, 1), (168, 0),   # 1 at 96, twelve steps: the long note cut at its end
		(180, 1), (192, 0),                      # 2 at 168, re-sync: four steps from step 8
		(192, 1), (198, 0), (252, 1), (264, 0),  # 3 at 192, on bar 2
		(264, 1), (270, 0),                      # 4 at 264
	])


def test_a_length_the_sequencer_refuses_costs_its_cycles_and_not_the_count (
	tmp_path: pathlib.Path) -> None:
	"""Two steps under a one-beat lookahead are refused twice; sixteen again, a re-sync on the bar changes nothing.

	**Found by this file before it was fixed**: the grid had counted the refused cycles
	as two steps each, so the page drew the pattern off the bar, and the re-sync made a
	short cycle and took a pattern that was on the bar off it.
	"""

	played = _render("refused", tmp_path)

	assert _onsets(played, 672) == sorted([
		(0, KICK), (24, HAT), (66, HAT), (90, SNARE),        # cycle 0 at 0
		(96, KICK), (120, HAT), (162, HAT), (186, SNARE),    # 1 at 96
		                                                     # 2 at 192 and 3 at 288: refused, silent, sixteen long
		(384, KICK), (408, HAT), (450, HAT), (474, SNARE),   # 4 at 384, sixteen asked for and taken
		(480, KICK), (504, HAT), (546, HAT), (570, SNARE),   # 5 at 480, re-sync asked on the bar
		(576, KICK), (600, HAT), (642, HAT), (666, SNARE),   # 6 at 576
	])
	assert played["cycles"] == [], "the page was told the pattern had left the bar"
	assert played["reports"] == [["grid/resync", False]]


# --- the child, which plays each scenario ---------------------------------------------

class _Port:
	"""A MIDI port that takes every message and sends none."""

	def send (self, message: typing.Any) -> None:
		"""Take one message."""

	def close (self) -> None:
		"""Nothing to close."""

	def panic (self) -> None:
		"""Nothing to silence."""

	def reset (self) -> None:
		"""Nothing to reset."""


class _Link:
	"""A link that writes down what a grid tells it."""

	def __init__ (self) -> None:
		"""Nothing said yet."""

		self.cycles: list[list[typing.Any]] = []
		self.reports: list[list[typing.Any]] = []

	def report (self, path: str, value: typing.Any) -> None:
		"""Write down one thing the app did of its own accord."""

		self.reports.append([path, value])

	def happened (self, name: str, **fields: typing.Any) -> None:
		"""Write down a cycle event as its start in beats, its first step and its end."""

		if name == "cycle":
			self.cycles.append([fields["at"], fields["from"], fields["end"]])

	def kept_changed (self) -> None:
		"""Nothing is kept here."""


Script = dict[int, typing.Callable[[typing.Any], typing.Any]]
"""What to do to a grid at the build of each cycle named, before it is asked what to play."""


def _resize (p: typing.Any, steps: int) -> None:
	"""What a composition on this Subsequence hands a grid (#2546)."""

	p.set_length(steps=steps)


def _drums (lookahead: float, script: Script, conductor: Script | None = None) -> dict[str, typing.Any]:
	"""A sixteen-step drum grid whose length changes, played with *script* acted at its builds.

	*conductor* is acted at the builds of a bar-long pattern beside it, which is how a
	grid is muted and brought back while its own builds are skipped.
	"""

	composition = subsequence.Composition(output_device="Dummy MIDI", bpm=120)
	composition.data["grid"] = {row: list(steps) for row, steps in SEED.items()}
	grid = adapter.StepGrid(composition, rows=list(SEED), steps=16, beats=4, pattern="drums",
	                        min_steps=1, resize=_resize)
	link = _Link()
	grid.attach(typing.cast(typing.Any, link))
	notes = {"kick": KICK, "hat": HAT, "snare": SNARE}
	sixteenth = subsequence.constants.durations.SIXTEENTH

	@composition.pattern(channel=10, steps=16, step_duration=sixteenth, reschedule_lookahead=lookahead)
	def drums (p: typing.Any) -> None:
		if p.cycle in script:
			script[p.cycle](grid)

		for row, steps in grid.now(p).items():
			for step in steps:
				p.note(pitch=notes[row], beat=int(step) * sixteenth, velocity=100, duration=1 / 24)

	if conductor is not None:
		@composition.pattern(channel=11, beats=4, reschedule_lookahead=1 / 24)
		def conduct (p: typing.Any) -> None:
			if p.cycle in conductor:
				conductor[p.cycle](grid)

	return {"composition": composition, "link": link, "pattern": "drums"}


def _notes () -> dict[str, typing.Any]:
	"""A note grid a pulse to a position, with a five-step note from step 10, cut and moved by a re-sync."""

	composition = subsequence.Composition(output_device="Dummy MIDI", bpm=120)
	composition.data["bass"] = {"C2": {"0": {"length": 6, "velocity": 100}, "60": {"length": 30, "velocity": 100}}}
	grid = adapter.NoteGrid(composition, rows=["C2"], steps=16, beats=4, data_key="bass", name="bass",
	                        pattern="bass", divisions=6, min_steps=1, resize=_resize)
	link = _Link()
	grid.attach(typing.cast(typing.Any, link))
	script: Script = {1: lambda one: one.apply(["end"], 12), 2: lambda one: one.apply(["resync"], True)}

	@composition.pattern(channel=3, steps=16, step_duration=subsequence.constants.durations.SIXTEENTH,
	                     reschedule_lookahead=1 / 24)
	def bass (p: typing.Any) -> None:
		if p.cycle in script:
			script[p.cycle](grid)

		for placed in grid.now(p).values():
			for at, note in placed.items():
				p.note(36, beat=int(at) / 24, velocity=note["velocity"], duration=note["length"] / 24)

	return {"composition": composition, "link": link, "pattern": "bass"}


SCENARIOS: dict[str, typing.Callable[[], dict[str, typing.Any]]] = {
	"shorten": lambda: _drums(1 / 24, {
		2: lambda grid: grid.apply(["end"], 10),
		4: lambda grid: grid.apply(["resync"], True),
		7: lambda grid: grid.apply(["end"], 16),
		9: lambda grid: grid.apply(["resync"], True)}),
	"mute": lambda: _drums(1 / 24, {1: lambda grid: grid.apply(["end"], 7)}, conductor={
		2: lambda grid: grid.apply(["enabled"], False),
		4: lambda grid: grid.apply(["enabled"], True),
		5: lambda grid: grid.apply(["resync"], True)}),
	"notes": _notes,
	"refused": lambda: _drums(1, {
		2: lambda grid: grid.apply(["end"], 2),
		4: lambda grid: grid.apply(["end"], 16),
		5: lambda grid: grid.apply(["resync"], True)}),
}

BARS = {"shorten": 10, "mute": 8, "notes": 3, "refused": 7}


def _play (scenario: str, where: pathlib.Path) -> dict[str, typing.Any]:
	"""Render one scenario and say what it sent, where each cycle started, and what the grid said."""

	mido = importlib.import_module("mido")
	setattr(mido, "get_output_names", lambda: ["Dummy MIDI"])
	setattr(mido, "open_output", lambda *_, **__: _Port())
	setattr(mido, "get_input_names", lambda: [])

	made = SCENARIOS[scenario]()
	composition = made["composition"]
	notes: list[list[int]] = []
	starts: list[int] = []
	dispatch = subsequence.sequencer.Sequencer._dispatch_with_compensation

	def record (self: typing.Any, event: typing.Any) -> None:
		if event.message_type in ("note_on", "note_off"):
			notes.append([event.pulse, event.note, int(event.message_type == "note_on")])

		dispatch(self, event)

	def rescheduled (pattern: typing.Any, start: int) -> None:
		if pattern is composition._running_patterns.get(made["pattern"]):
			starts.append(start)

	setattr(subsequence.sequencer.Sequencer, "_dispatch_with_compensation", record)
	composition.on_event("pattern_reschedule", rescheduled)
	composition.render(bars=BARS[scenario], filename=str(where / f"{scenario}.mid"))

	running = composition._running_patterns[made["pattern"]]

	return {
		"notes": notes, "starts": starts, "cycles": made["link"].cycles, "reports": made["link"].reports,
		"length": [running.length, running._default_grid]}


if __name__ == "__main__":
	written = pathlib.Path(sys.argv[2])
	(written / f"{sys.argv[1]}.json").write_text(json.dumps(_play(sys.argv[1], written)))
