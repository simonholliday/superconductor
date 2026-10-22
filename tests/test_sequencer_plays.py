"""A sequencer control played through Subsequence's own sequencers plugin, rather than a stand-in (#5210).

`test_sequencer.py` drives the control with a hand-written state.  What only the plugin
can say is that the two agree: that the first build hands over what the control needs
to declare, that a stage set from the glass is heard from the pattern's next build,
and that handing it back puts the code's value back.  So this renders a Moog 960 into
a notes-out, with the control watching, and compares what was played cycle by cycle.

**The render runs in a child process, with MIDI patched there**, for the reasons
`test_length_sequencer.py` gives: a render starts its event loop in the main thread,
and a page test leaves Playwright's running there.

Importing Subsequence here is a rig arrangement, as it is for the other files that
measure this package against the sequencer an app runs.
"""

import importlib
import json
import pathlib
import subprocess
import sys
import typing

import pytest

import subsequence
import subsequence.constants.durations
import subsequence.plugins.sequencers as sequencers
import subsequence.sequencer

import superconductor.subsequence_adapter as adapter


LOWEST = 48
"""The notes-out's lowest note, which a lane value of 0 plays."""

LANE_A = [0, 2, 4, 5, 7, 9, 11, 12]
"""The 960's first lane, in semitones above the lowest note: a major scale over an octave."""

OCTAVE = 12 / 60
"""A lane value an octave up: the notes-out spans sixty semitones over a lane's 0 to 1."""

PULSES = 96
"""One cycle: a bar of sixteen sixteenths, at the sequencer's 24 pulses a beat."""

CYCLES = 5


@pytest.fixture(scope="module")
def played (tmp_path_factory: pytest.TempPathFactory) -> dict[str, typing.Any]:
	"""The scenario, played once for every test here, in a child process."""

	where = tmp_path_factory.mktemp("sequencer")
	done = subprocess.run(
		[sys.executable, __file__, str(where)], capture_output=True, text=True, timeout=120, check=False)

	assert done.returncode == 0, done.stderr[-4000:]

	return typing.cast(dict[str, typing.Any], json.loads((where / "overlay.json").read_text()))


def _onsets (played: dict[str, typing.Any], cycle: int) -> list[tuple[int, int]]:
	"""Each note begun in *cycle*, as (step, note)."""

	return sorted(((pulse - cycle * PULSES) // 6, note) for pulse, note, on in played["notes"]
	              if on and cycle * PULSES <= pulse < (cycle + 1) * PULSES)


def _where_stage_0_played (played: dict[str, typing.Any], cycle: int) -> set[int]:
	"""The steps of *cycle* the 960 spent on its first stage, as the plugin reported them."""

	return {step for step, stage in enumerate(played["positions"][cycle]) if stage == 0}


# --- the tests, which read what the child sent ------------------------------------------

def test_the_first_build_declares_the_sequencer_it_found (played: dict[str, typing.Any]) -> None:
	"""Only a build says what the sequencer is, so the first one asks for a declaration carrying it."""

	assert played["declared"] >= 1
	assert sorted(played["models"]) == ["clock", "midi_out", "moog_960"]
	assert played["modules"] == ["clock", "midi", "960"]


def test_where_each_stage_played_comes_once_a_cycle (played: dict[str, typing.Any]) -> None:
	"""One event a cycle, a stage for each of the cycle's sixteen steps."""

	assert len(played["positions"]) == CYCLES
	assert all(len(one) == 16 for one in played["positions"])
	assert _where_stage_0_played(played, 0), "the 960 never reached its first stage, so this proves nothing"


def test_a_stage_set_on_the_glass_is_heard_from_the_next_build (played: dict[str, typing.Any]) -> None:
	"""Set during cycle 1's build, so cycle 2 plays it: stage 0 an octave up, and nothing else moved."""

	before, after = dict(_onsets(played, 1)), dict(_onsets(played, 2))
	moved = _where_stage_0_played(played, 2)

	assert moved
	assert {step: after[step] - before[step] for step in after if after[step] != before[step]} == {
		step: 12 for step in moved}


def test_handing_it_back_puts_the_code_s_note_back (played: dict[str, typing.Any]) -> None:
	"""Handed back during cycle 3's build, so cycle 4 plays what the code says, as cycle 0 did."""

	assert _onsets(played, 4) == _onsets(played, 0)


def test_what_the_glass_held_was_reported_as_it_moved (played: dict[str, typing.Any]) -> None:
	"""The plugin's own account of what the glass held, reported whole, ending with nothing held."""

	helds = [value for path, value in played["reports"] if path == "lead/held"]

	assert {"modules": {"960": {"settings": {"lane_a": {"0": OCTAVE}}}}} in helds
	assert helds[-1] == {}


# --- the child: the scenario, and what it sent ------------------------------------------

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
	"""A link that writes down what the control tells it."""

	def __init__ (self) -> None:
		"""Nothing said yet."""

		self.reports: list[list[typing.Any]] = []
		self.positions: list[list[typing.Any]] = []
		self.declared = 0

	def report (self, path: str, value: typing.Any) -> None:
		"""Write down one thing the app did of its own accord."""

		self.reports.append([path, value])

	def happened (self, name: str, **fields: typing.Any) -> None:
		"""Write down where the 960 was at each step of a cycle."""

		if name == "playing":
			self.positions.append(fields["modules"]["960"]["positions"]["stage"])

	def redeclare (self) -> None:
		"""Count one declaration asked for."""

		self.declared += 1


def _play (where: pathlib.Path) -> dict[str, typing.Any]:
	"""Render the 960 with a stage set from the glass during cycle 1's build and handed back during cycle 3's."""

	mido = importlib.import_module("mido")
	setattr(mido, "get_output_names", lambda: ["Dummy MIDI"])
	setattr(mido, "open_output", lambda *_, **__: _Port())
	setattr(mido, "get_input_names", lambda: [])

	composition = subsequence.Composition(output_device="Dummy MIDI", bpm=120)

	@sequencers.pattern(composition, channel=1, steps=16,
	                    step_duration=subsequence.constants.durations.SIXTEENTH, reschedule_lookahead=1 / 24)
	def lead (seq: typing.Any) -> None:
		seq.add(sequencers.moog_960, "960", lane_a=[one / 60 for one in LANE_A])
		seq.add(sequencers.midi_out, "midi", lowest=LOWEST)
		seq.patch("clock.out", "960.shift")
		seq.patch("clock.out", "midi.trigger")
		seq.patch("960.lane_a", "midi.pitch")

	control = adapter.Sequencer(composition, "lead", watch=sequencers.on_build)
	link = _Link()
	control.attach(typing.cast(typing.Any, link))

	# **Registered after the control, so the plugin calls it second**: at each build's
	# end, with the control already holding that build's state, as a hand on the glass
	# would find it between two builds.  **From the second build**, because the pattern
	# joins the running ones only once its first has finished, and a change made during
	# that one waits a build more (`test_sequencer.py` holds that case).
	builds = []

	def script (pattern_name: str, state: typing.Any, playing: typing.Any) -> None:
		builds.append(pattern_name)

		if len(builds) == 2:
			control.apply(["settings", "960", "lane_a", "0"], OCTAVE)

		elif len(builds) == 4:
			control.apply(["settings", "960", "lane_a", "0"], None)

	sequencers.on_build(composition, script)

	notes: list[list[int]] = []
	dispatch = subsequence.sequencer.Sequencer._dispatch_with_compensation

	def record (self: typing.Any, event: typing.Any) -> None:
		if event.message_type in ("note_on", "note_off"):
			notes.append([event.pulse, event.note, int(event.message_type == "note_on")])

		dispatch(self, event)

	setattr(subsequence.sequencer.Sequencer, "_dispatch_with_compensation", record)
	composition.render(bars=CYCLES, filename=str(where / "overlay.mid"))

	return {
		"notes": notes, "positions": link.positions[:CYCLES], "reports": link.reports,
		"declared": link.declared, "models": sorted(control.declaration()["models"]),
		"modules": [one["name"] for one in control.snapshot()["modules"]]}


if __name__ == "__main__":
	written = pathlib.Path(sys.argv[1])
	(written / "overlay.json").write_text(json.dumps(_play(written)))
