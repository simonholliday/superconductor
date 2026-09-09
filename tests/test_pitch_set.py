"""A set of notes that sounds nothing, and the two instruments that play it.

One set patched to two arpeggios is the case this exists for (#2374).  It is
also the case that shows why folding has to move the whole set: the rig's
Minitaur reaches C1 to C3 and its Matriarch C3 to C5, so a literal pitch played
through both is silent on one of them.
"""

import typing

import pytest

import superconductor.controls as controls
import superconductor.subsequence_adapter as adapter


def _named (low: int, high: int) -> dict[str, int]:
	"""Chromatic note names against their MIDI numbers, the way a composition does."""

	steps = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

	return {f"{steps[note % 12]}{note // 12 - 1}": note for note in range(low, high + 1)}


BASS = _named(24, 48)
"""C1 to C3, which is what the Minitaur on the rig reaches."""

LEAD = _named(48, 72)
"""C3 to C5, which is what the Matriarch reaches.  They meet at exactly one note."""


class Composition:
	"""Just the dict the real one carries, which is all a control touches."""

	def __init__ (self) -> None:
		"""Start with nothing in it."""

		self.data: dict[str, typing.Any] = {}


def _set (chosen: typing.Sequence[str] = ()) -> adapter.PitchSet:
	"""A set of notes over the lead's range, holding whatever is asked for."""

	held = adapter.PitchSet(Composition(), name="notes", pitches=LEAD)

	if chosen:
		held.apply(["chosen"], list(chosen))

	return held


def _stack (pitches: dict[str, int], held: adapter.PitchSet) -> adapter.Recipe:
	"""A stack over one instrument's rows, able to see one set of notes."""

	recipe = adapter.Recipe(
		Composition(), catalogue=[], pitches=list(pitches), pitch_notes=pitches)

	class Link:
		controls = {"notes": held}

	recipe.link = typing.cast(typing.Any, Link())

	return recipe


def test_a_set_keeps_the_order_it_was_chosen_in () -> None:
	"""The pitches of a chord are not a set, and a root chosen first stays first."""

	held = _set(["G4", "C4", "E4"])

	assert held.chosen == ["G4", "C4", "E4"]
	assert held.notes() == [67, 60, 64]


def test_a_set_refuses_a_pitch_it_does_not_have () -> None:
	"""Strict rather than forgiving, as every other value on this path is."""

	with pytest.raises(adapter.Refused):
		_set().apply(["chosen"], ["C0"])


def test_a_set_refuses_the_same_pitch_twice () -> None:
	"""A pitch is in the set or it is not, and twice is a panel fault."""

	with pytest.raises(adapter.Refused):
		_set().apply(["chosen"], ["C4", "C4"])


def test_a_set_switched_off_is_empty_rather_than_absent () -> None:
	"""An empty pitch list is a thing every consumer already handles: arpeggio rests."""

	held = _set(["C4", "E4"])
	held.apply(["enabled"], False)

	assert held.notes() == []
	assert held.chosen == ["C4", "E4"], "a mute is not a delete"


def test_one_set_reaches_two_instruments_that_share_almost_no_range () -> None:
	"""The case this was built for, and the reason folding exists at all."""

	held = _set(["C4", "E4", "G4"])

	assert _stack(LEAD, held)._folded(held.notes()) == ["C4", "E4", "G4"]
	assert _stack(BASS, held)._folded(held.notes()) == ["C2", "E2", "G2"]


def test_folding_moves_the_whole_set_rather_than_each_note () -> None:
	"""**A triad has a shape and the shape is most of what it is.**

	Folding each note to its own nearest octave was tried first and is wrong: it
	took C4 E4 G4 through a bass as C3 E2 G2 — the right three pitch classes, and
	not a chord anybody played.  This asserts the intervals survive.
	"""

	folded = _stack(BASS, _set())._folded([60, 64, 67])
	notes = [BASS[one] for one in folded]

	assert [note - notes[0] for note in notes] == [0, 4, 7], "a major triad, still"


def test_a_note_the_shift_leaves_out_of_range_is_folded_in_rather_than_dropped () -> None:
	"""A set wider than the instrument cannot keep its shape, and sounding beats silence."""

	wide = _stack(BASS, _set())._folded([36, 96])

	assert len(wide) == 2, "both notes sound"
	assert all(24 <= BASS[one] <= 48 for one in wide)


def test_a_stack_with_no_notes_of_its_own_folds_nothing () -> None:
	"""A stack whose rows are drum voices has no register to fold into."""

	recipe = adapter.Recipe(Composition(), catalogue=[], pitches=["kick", "snare"])

	assert recipe._folded([60, 64]) == []


def test_a_patched_parameter_arrives_as_this_stack_s_own_pitch_names () -> None:
	"""What the generator is handed, which is the whole point of the mechanism."""

	held = _set(["C4", "E4", "G4"])
	recipe = _stack(BASS, held)

	wanted = recipe._arguments("arpeggio", {"notes": {"from": "control", "id": "notes"}})

	assert wanted["notes"] == ["C2", "E2", "G2"]


def test_a_patch_to_a_source_that_has_gone_rests_rather_than_raises () -> None:
	"""One dead reference must not cost the part its bar, as a bad layer does not."""

	recipe = _stack(BASS, _set(["C4"]))

	assert recipe._arguments("arpeggio", {"notes": {"from": "control", "id": "nope"}})["notes"] == []


def test_the_service_keeps_a_patch_as_a_reference_and_never_resolves_it () -> None:
	"""**The seam.**  What the service holds has to equal what the app holds.

	The service is the copy a panel arriving late is answered from, so a value it
	stored differently from the app is one that comes back wrong on a reload with
	nothing saying why — the fault `tests/test_seam.py` exists for, asked here of
	the new shape.
	"""

	declarations = {
		"notes": {"type": "pitch_set", "pitches": [{"value": "C4", "midi": 60}]},
		"stack": {
			"type": "recipe",
			"generators": [{
				"name": "arpeggio", "partial": False,
				"parameters": [{"name": "notes", "kind": "choices", "role": "pitch",
				                "required": True, "options": [{"value": "C2"}]}],
			}],
		},
	}

	state: dict[str, typing.Any] = {}

	controls.apply_change(state, declarations, "stack/layers",
	                      [{"id": "a", "kind": "generator", "generator": "arpeggio", "params": {}}])
	controls.apply_change(state, declarations, "stack/a/notes",
	                      {"from": "control", "id": "notes"})

	kept = state["stack"]["layers"][0]["params"]["notes"]

	assert kept == {"from": "control", "id": "notes"}, "the reference is kept whole"

	offered = adapter.Parameter("notes", "choices", options=[("C2", "C2")], role="pitch")

	assert adapter.checked_value(offered, {"from": "control", "id": "notes"}) == kept, (
		"the app and the service keep the same thing, or a reload disagrees")


def test_the_service_refuses_a_patch_to_something_that_is_not_a_set_of_notes () -> None:
	"""A dangling or wrong-typed cable is a panel fault and is said so, not stored."""

	declarations = {
		"transport": {"type": "transport", "fields": ["bpm"]},
		"stack": {
			"type": "recipe",
			"generators": [{
				"name": "arpeggio", "partial": False,
				"parameters": [{"name": "notes", "kind": "choices", "role": "pitch",
				                "required": True, "options": []}],
			}],
		},
	}

	state: dict[str, typing.Any] = {}

	controls.apply_change(state, declarations, "stack/layers",
	                      [{"id": "a", "kind": "generator", "generator": "arpeggio", "params": {}}])

	with pytest.raises(controls.ControlError):
		controls.apply_change(state, declarations, "stack/a/notes",
		                      {"from": "control", "id": "transport"})

	with pytest.raises(controls.ControlError):
		controls.apply_change(state, declarations, "stack/a/notes",
		                      {"from": "control", "id": "nothing_declared"})


def test_nothing_but_a_pitch_pool_takes_a_cable () -> None:
	"""A `choices` of waveform names is the same kind and is not the same thing."""

	waveforms = adapter.Parameter("shape", "choices", options=[("saw", "saw")])

	with pytest.raises(adapter.Refused):
		adapter.checked_value(waveforms, {"from": "control", "id": "notes"})
