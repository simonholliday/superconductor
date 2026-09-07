"""The rig's own composition, where an instrument definition meets the panel.

Nothing here tests the Superintendent package — it tests the join a composition
has to make, and it lives in this suite because the join has a trap in it that
would otherwise be found by a chord going silent on a Matriarch.

Importing `compositions/drm1_grid.py` is safe: a Subsequence composition resolves
its devices lazily and opens no MIDI port until `play()`, which nothing here
calls.  The file sorts before `test_page.py`, which matters — Playwright's sync
API holds the main thread's loop for the rest of the session once a page test has
run, and anything after it that wants a loop of its own fails.
"""

import importlib.util
import sys
import types
import typing

import pytest

import pymididefs.instruments


def _composition () -> typing.Any:
	"""The rig's composition, imported once and shared."""

	if "drm1_grid" not in sys.modules:
		spec = importlib.util.spec_from_file_location(
			"drm1_grid", "compositions/drm1_grid.py")
		assert spec is not None and spec.loader is not None
		module = importlib.util.module_from_spec(spec)
		sys.modules["drm1_grid"] = module
		spec.loader.exec_module(module)

	return sys.modules["drm1_grid"]


@pytest.fixture (scope="module")
def rig () -> typing.Any:
	"""The composition module, loaded but not playing."""

	return _composition()


def test_a_stated_voice_count_is_used_as_it_stands (rig: typing.Any) -> None:
	"""A Minitaur says one voice, and one voice is what the grid enforces."""

	assert rig._voice_count(rig.MINITAUR) == 1
	assert rig.MINITAUR.voice.polyphony == 1


def test_an_unknown_voice_count_is_not_quietly_read_as_unlimited () -> None:
	"""**The trap this guard exists for**, on the instrument it is aimed at.

	`pymididefs` uses ``polyphony = None`` for *nobody has established it*; a note
	grid uses ``voices = None`` for *as many as you like*.  A Matriarch's voicing
	is a front-panel switch and control change 94 with no documented power-on
	default, so its definition says null — and a pass-through would draw a
	five-note chord on a four-voice instrument and say nothing.
	"""

	rig = _composition()
	matriarch = pymididefs.instruments.load("moog_matriarch")

	assert matriarch.voice.polyphony is None
	assert matriarch.voice.voicing_modes == (1, 2, 4)

	with pytest.raises(ValueError, match="has to be told which to assume"):
		rig._voice_count(matriarch)


def test_a_switchable_instrument_may_be_told_which_mode_to_assume () -> None:
	"""Told, rather than guessed — and only a mode it actually has."""

	rig = _composition()
	matriarch = pymididefs.instruments.load("moog_matriarch")

	assert rig._voice_count(matriarch, when_switchable=4) == 4

	with pytest.raises(ValueError, match="no 3-voice mode"):
		rig._voice_count(matriarch, when_switchable=3)


def test_an_instrument_that_states_nothing_at_all_is_unlimited () -> None:
	"""The only case where None may become None: neither a count nor any modes.

	That is a different fact from "unknown", which is the whole distinction, so
	it gets its own case rather than being assumed to fall out of the others.
	"""

	rig = _composition()
	silent = types.SimpleNamespace(
		model=types.SimpleNamespace(name="Nothing In Particular"),
		voice=types.SimpleNamespace(polyphony=None, voicing_modes=()))

	assert rig._voice_count(silent) is None


def test_a_switch_sends_the_state_the_definition_names_not_the_word_on (
	rig: typing.Any) -> None:
	"""Legato glide is `always` and `legato_only`, and neither is spelled "on".

	A bool has to pick by the *order* the definition gives — ascending, so the
	second is the far end — because mapping True to a literal "on" raises a
	KeyError on the first instrument whose switch is named after what it does.
	"""

	assert list(rig.MINITAUR.controls["legato_glide"].values) == ["always", "legato_only"]

	assert rig._cc_value("legato_glide", False) == 31
	assert rig._cc_value("legato_glide", True) == 95


def test_a_bands_value_is_the_middle_of_the_band_and_not_its_edge (
	rig: typing.Any) -> None:
	"""So a value that drifts by one does not become a different setting."""

	assert rig._cc_value("glide_type", "lcr") == 21
	assert rig._cc_value("glide_type", "lct") == 63
	assert rig._cc_value("glide_type", "exp") == 106


def test_local_control_is_the_specifications_switch_and_takes_0_or_127 (
	rig: typing.Any) -> None:
	"""It is not in the Minitaur's definition, because it is not the Minitaur's.

	Control change 122 means local control on every instrument ever built, so it
	is a specification fact.  Its absence from the corpus is the three-tier split
	working rather than a gap, and it is the one switch with no band to sit in
	the middle of (#2081).
	"""

	assert "local_control" not in rig.BASS_CONTROLS
	assert rig._cc_value("local_control", True) == 127
	assert rig._cc_value("local_control", False) == 0


def test_a_controls_kind_is_derived_from_its_bands_rather_than_declared (
	rig: typing.Any) -> None:
	"""No values means continuous, two a switch, three or more a choice.

	Derived here as well as upstream, so a corrected band table changes what the
	panel draws without this composition being edited at all.
	"""

	drawn = {p.name: p.kind for p in
	         [rig._panel_parameter(*setting) for setting in rig.BASS_SETTINGS]}

	assert drawn["glide"] == "switch"
	assert drawn["glide_type"] == "choice"
	assert drawn["glide_rate"] == "number"


def test_a_range_outside_what_the_instrument_sounds_is_refused_at_import (
	rig: typing.Any) -> None:
	"""The check is at module level, so this asserts the fact it rests on.

	A Minitaur ignores a note above 72 rather than playing it wrong, so a range
	set an octave too high draws a grid that works perfectly and makes no sound.
	"""

	low, high = rig.MINITAUR.voice.note_range

	assert (low, high) == (0, 72)
	assert all(low <= rig.midi_notes.name_to_note(row) <= high for row in rig.BASS_RANGE)
