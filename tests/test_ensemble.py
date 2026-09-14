"""The ensemble composition: seven instruments, four pages, and nothing playing.

**This file's subject is a rig that starts from zero** (Simon, 2026-09-14), so the
test that matters most is that it makes no sound — asserted by rendering it
through Subsequence's own scheduler and counting the notes, because a composition
that seeds nothing is easy to write and easy to break later with one convenient
default.

**Not run by CI**, like every test here that imports `subsequence`: the sequencer
is a rig arrangement and a runner has not got it.
"""

import importlib.util
import json
import pathlib
import subprocess
import sys
import typing

import pytest

import pymidiinstrumentdefs


HERE = pathlib.Path(__file__).parent.parent
WHERE = HERE / "compositions" / "ensemble.py"


def _composition () -> typing.Any:
	"""The composition module, imported once and shared.

	Importing it does not dial the service: the link connects when it is started,
	which only ``__main__`` does.
	"""

	if "ensemble" not in sys.modules:
		spec = importlib.util.spec_from_file_location("ensemble", str(WHERE))
		assert spec is not None and spec.loader is not None
		module = importlib.util.module_from_spec(spec)
		sys.modules["ensemble"] = module
		spec.loader.exec_module(module)

	return sys.modules["ensemble"]


@pytest.fixture (scope="module")
def rig () -> typing.Any:
	"""The composition, loaded but not playing."""

	return _composition()


# --- What it comes up as -------------------------------------------------------

def test_the_rig_comes_up_with_nothing_on_it (rig: typing.Any) -> None:
	"""**The whole point of this composition** (Simon, 2026-09-14): *"I'd like to
	start from nothing with a bunch of instruments and no initial patterns,
	connections or routes between them."*

	Checked on the data rather than on the glass, because this is where a seeded
	pattern would be: every grid reads its rows out of ``composition.data`` and
	an opening pattern is a dict put there at import.

	**Four empty variants is still nothing.**  A grid that takes variants writes a
	shell for each at birth, so what is asserted is that no row anywhere holds a
	step — not that the dict is bare.
	"""

	for one in rig.INSTRUMENTS:
		held = rig.composition.data.get(one.key) or {}
		rows = {name: variant.get("rows") or {} for name, variant in held.items()}
		played = {name: content for name, content in rows.items() if content}

		assert not played, f"{one.key} came up holding something: {played}"

	for key, stack in rig.STACKS.items():
		assert not stack.declaration().get("layers"), f"{key} came up with a generator on it"


def test_no_grid_here_takes_from_another (rig: typing.Any) -> None:
	"""No routes and no cables either, which is the other half of *from nothing*.

	A stack offers a route only where the composition hands it sources; these are
	handed none, so there is no cable to drag on the first morning and every one
	that appears later was patched by somebody.
	"""

	for key, stack in rig.STACKS.items():
		assert not stack.declaration().get("sources"), f"{key} was offered something to route from"


def test_every_instrument_listens_on_a_channel_of_its_own (rig: typing.Any) -> None:
	"""Two instruments on one channel is the fault that sounds like a broken instrument.

	Both play, both answer every note meant for either, and nothing on the glass
	says so — so it is worth one assertion rather than an afternoon.
	"""

	channels = [one.channel for one in rig.INSTRUMENTS]

	assert len(set(channels)) == len(channels), f"two instruments share a channel: {channels}"


# --- What a definition is allowed to decide ------------------------------------

def test_a_part_sits_where_its_definition_says_above_the_base (rig: typing.Any) -> None:
	"""The Streichfett's solo section is one channel above its strings, and the
	definition is what says *one* — this file says only where the base is.

	**Measured on the hardware before it was written down** (#2544): notes sent a
	channel above the base sound the solo voice.
	"""

	streichfett = pymidiinstrumentdefs.load("waldorf/streichfett")
	strings = next(one for one in rig.INSTRUMENTS if one.key == "strings")
	solo = next(one for one in rig.INSTRUMENTS if one.key == "solo")

	assert streichfett.parts["strings"].channel_offset == 0
	assert streichfett.parts["solo"].channel_offset == 1
	assert solo.channel == strings.channel + 1


def test_a_part_that_moved_under_the_rig_is_refused_rather_than_played_wrong (
	rig: typing.Any) -> None:
	"""The check the pair above is worth having: a table saying otherwise fails at
	import, where somebody is looking, rather than on a channel nothing answers."""

	wrong = dataclasses_replace(rig, "solo", channel=7)

	with pytest.raises(ValueError, match="sits 1 above its base"):
		rig._channel_for(wrong)


def test_each_part_sounds_as_many_notes_as_it_says_and_not_as_many_as_the_instrument (
	rig: typing.Any) -> None:
	"""A Streichfett's strings take 128 notes and its solo eight, which is a real
	difference on the glass: the solo grid refuses a ninth note in a column."""

	assert rig.GRIDS["strings"].declaration()["voices"] == 128
	assert rig.GRIDS["solo"].declaration()["voices"] == 8


def test_an_instrument_that_switches_voice_counts_has_to_be_told_which (rig: typing.Any) -> None:
	"""`polyphony = None` is *nobody has established it* and a grid's `voices` of
	None is *as many as you like*; handing one to the other turns unknown into
	unlimited.  A Matriarch is told four."""

	matriarch = pymidiinstrumentdefs.load("moog/matriarch")

	assert matriarch.voice.polyphony is None
	assert matriarch.voice.voicing_modes == (1, 2, 4)
	assert rig.GRIDS["matriarch"].declaration()["voices"] == 4

	with pytest.raises(ValueError, match="has to be told which to assume"):
		rig._voice_count(matriarch)


def test_a_register_outside_what_an_instrument_can_sound_is_refused (rig: typing.Any) -> None:
	"""Outside its range an instrument is **silent** rather than wrong-sounding, so
	a register set an octave too high draws a grid that works perfectly and makes
	no sound.  Nothing else would tell you (#2121)."""

	too_high = dataclasses_replace(rig, "minitaur", low="C6", high="C7")

	with pytest.raises(ValueError, match="outside what a .* can sound"):
		rig._register(too_high)


def test_a_setting_naming_a_control_the_instrument_has_not_is_refused (rig: typing.Any) -> None:
	"""A row on the glass that moves nothing and says nothing about it is the
	silence every check in this file exists for."""

	minitaur = next(one for one in rig.INSTRUMENTS if one.key == "minitaur")

	with pytest.raises(ValueError, match="has no control called 'wobble'"):
		rig._panel_parameter(minitaur, "wobble", "wobble", "Wobble", 0, None)


def test_an_instrument_with_nothing_to_receive_gets_no_settings_block (rig: typing.Any) -> None:
	"""A Model D and a Malevolent are all-knobs synths whose definitions declare no
	controls at all.  **The panel loses a control rather than drawing a broken one**
	(#2046), so they get a pattern and no block — and a block of no rows is worse
	than no block."""

	for key in ("model_d", "malevolent", "drm1", "solo"):
		assert rig.SETTINGS[key] is None, f"{key} was given a settings block with nothing in it"

	for key in ("tr8s", "minitaur", "matriarch", "strings"):
		assert rig.SETTINGS[key] is not None, f"{key} has controls and was given no block"


def test_the_streichfett_s_solo_controls_are_set_on_the_strings_channel (rig: typing.Any) -> None:
	"""**Every one of its nineteen controls is unparted**, which is the parts
	format's way of saying *the base channel* — so the solo voice's tone is set on
	channel 2 while its notes are played on 3.

	Measured on the hardware first (#2544): control changes 76, 70 and 77 sent to
	the channel above the base moved nothing at all.
	"""

	streichfett = pymidiinstrumentdefs.load("waldorf/streichfett")
	by_part = streichfett.controls_by_part()

	assert list(by_part) == [""], f"a control moved off the base channel: {list(by_part)}"

	fields = [one["name"] for one in rig.SETTINGS["strings"].declaration()["fields"]]

	assert "solo_tone" in fields, "the solo section's controls are not on the block that can send them"
	assert rig.SETTINGS["strings"].declaration()["configures"] == "strings"


# --- The glass -----------------------------------------------------------------

def test_every_page_names_something_this_composition_declares (rig: typing.Any) -> None:
	"""A page naming a control nobody declared draws an empty page and says nothing."""

	declared = set(rig.link.controls)

	for page in rig.link.pages:
		for part in page.declaration()["parts"]:
			assert part in declared, f"a page names {part!r}, which is not declared"


def test_the_pages_are_few_enough_to_be_named_on_the_glass (rig: typing.Any) -> None:
	"""The client draws named page buttons up to six and gives way to
	previous-and-next above that — so eight pages showed *"‹ Pattern 1 1/8 ›"* and
	no page names at all, which is the one thing a page selector is for."""

	assert len(rig.link.pages) <= 6, "there are more pages than the panel will name"


def test_every_instrument_is_on_the_ensemble_page (rig: typing.Any) -> None:
	"""*"New page 'ensemble' — we'll add everything in"* (Simon, 2026-09-14)."""

	ensemble = next(page for page in rig.link.pages
	                if page.declaration()["title"] == "Ensemble")

	assert ensemble.declaration()["parts"] == [one.key for one in rig.INSTRUMENTS]


def test_a_settings_block_needs_no_page_of_its_own (rig: typing.Any) -> None:
	"""One that names the pattern it configures is drawn wherever that pattern is
	and put away behind its latch, so the pages name patterns and nothing else."""

	named = {part for page in rig.link.pages for part in page.declaration()["parts"]}
	settings = {f"{one.key}_settings" for one in rig.INSTRUMENTS}

	assert not (named & settings), f"a page named a settings block: {named & settings}"


# --- Played through Subsequence ------------------------------------------------

def test_the_rig_plays_nothing_until_somebody_plays_it (tmp_path: pathlib.Path) -> None:
	"""**The one that cannot be talked out of** — rendered through Subsequence's own
	scheduler with nothing placed, counting what reached the port.

	The only MIDI that leaves is the Matriarch's voice mode, which is the
	instrument being put where a chord can be heard rather than any music: it
	sounds incoming notes one at a time until that is asserted, whatever its front
	panel says (#2177).

	**A child process**, because a render installs signal handlers and wants the
	main thread, and MIDI is patched there or it goes looking among this rig's
	real ports (#2526).
	"""

	played = _rendered(tmp_path, place=False)

	assert played["notes"] == [], f"a rig that seeds nothing still played: {played['notes']}"
	assert played["controls"] == [[0, 94]], \
		f"something other than the Matriarch's voicing was sent: {played['controls']}"


def test_a_note_on_every_instrument_reaches_its_own_channel (tmp_path: pathlib.Path) -> None:
	"""And the other half: once somebody puts a note on each grid, each one sounds
	where its instrument is listening.  Channels are counted from zero on the wire
	and from one in this file, which is the off-by-one worth one assertion."""

	played = _rendered(tmp_path, place=True)
	wire = {channel for channel, _ in played["notes"]}
	rig = _composition()

	assert wire == {one.channel - 1 for one in rig.INSTRUMENTS}, \
		f"a note did not reach its instrument: {sorted(wire)}"


def _rendered (where: pathlib.Path, place: bool) -> dict[str, typing.Any]:
	"""Play the composition in a child process and read back what reached the port."""

	done = subprocess.run(
		[sys.executable, str(pathlib.Path(__file__)), str(where), "place" if place else "silent"],
		capture_output=True, text=True, timeout=180, check=False, cwd=str(HERE))

	assert done.returncode == 0, done.stderr[-4000:]

	return typing.cast(dict[str, typing.Any], json.loads((where / "played.json").read_text()))


def dataclasses_replace (rig: typing.Any, key: str, **fields: typing.Any) -> typing.Any:
	"""One of the instruments with something changed, for the checks that want a wrong one."""

	import dataclasses

	return dataclasses.replace(next(one for one in rig.INSTRUMENTS if one.key == key), **fields)


# --- the child, which plays it -------------------------------------------------

if __name__ == "__main__":
	_where = pathlib.Path(sys.argv[1])
	_place = sys.argv[2] == "place"

	import importlib


	class _Port:
		def send (self, message: typing.Any) -> None: pass
		def close (self) -> None: pass
		def panic (self) -> None: pass
		def reset (self) -> None: pass


	_mido = importlib.import_module("mido")
	setattr(_mido, "get_output_names", lambda: ["U6MIDI Pro Port 1"])
	setattr(_mido, "open_output", lambda *_, **__: _Port())
	setattr(_mido, "get_input_names", lambda: [])

	_rig = _composition()

	import subsequence.sequencer

	if _place:
		for _one in _rig.INSTRUMENTS:
			_row = _rig._rows(_one)[0]
			_grid = _rig.GRIDS[_one.key]
			_grid.apply(["variants", "A", "rows", _row, "0"],
			            True if _one.drums else {"length": 1, "velocity": 100})

	_notes: list[list[int]] = []
	_controls: list[list[int]] = []
	_dispatch = subsequence.sequencer.Sequencer._dispatch_with_compensation


	def _record (self: typing.Any, event: typing.Any) -> None:
		if event.message_type == "note_on":
			_notes.append([event.channel, event.note])

		elif event.message_type == "control_change":
			_controls.append([event.channel, event.control])

		_dispatch(self, event)


	setattr(subsequence.sequencer.Sequencer, "_dispatch_with_compensation", _record)
	_rig.composition.render(bars=2, filename=str(_where / "ensemble.mid"))

	(_where / "played.json").write_text(json.dumps({
		"notes": sorted({tuple(one) for one in _notes}),
		"controls": sorted({tuple(one) for one in _controls}),
	}))
