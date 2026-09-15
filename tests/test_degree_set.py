"""A set of scale degrees, which follows the key and feeds whatever wants pitches (#2527).

**Simon's design of 2026-09-15.**  A second kind of set beside the fixed-pitch
one: *the 1st, 3rd and 5th* rather than *C, E and G*, resolved against the piece's
key each time a pattern is built, so changing the key moves every part a degree
set feeds with nothing re-patched.  Three octaves and a flat or sharp on any
degree; one key for the whole piece, in a block of its own.

**Nothing here knows a key.**  The composition hands the set a way to ask what the
key is now, as the notes of one octave of its scale and the words to say it in,
and a way to name a note (#1465, #2144).
"""

import typing

import pytest

import superconductor.controls as controls
import superconductor.protocol as protocol
import superconductor.subsequence_adapter as adapter

import test_pitch_set
import test_recipe


NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


class Key:
	"""The composition's key as the set is told it: settable, as the Key block sets it."""

	def __init__ (self, root: str | None = "C", steps: typing.Sequence[int] = (0, 2, 4, 5, 7, 9, 11),
	              words: str = "C major") -> None:
		"""A key in one octave from middle C, or none at all."""

		self.root = root
		self.steps = list(steps)
		self.words = words

	def __call__ (self) -> tuple[str, list[int]] | None:
		"""What the key is now: its words and the notes of its steps, tonic first."""

		if self.root is None:
			return None

		tonic = 60 + NAMES.index(self.root)

		return self.words, [tonic + step for step in self.steps]


def _named (note: int) -> str:
	"""A note's name without its octave, as the composition says it."""

	return NAMES[note % 12]


def _degree (step: int, octave: int = 0, chroma: int = 0) -> dict[str, int]:
	"""One degree as it crosses the wire."""

	return {"step": step, "octave": octave, "chroma": chroma}


def _set (key: Key | None = None, chosen: typing.Sequence[dict[str, int]] = ()) -> adapter.DegreeSet:
	"""A degree set following *key*, holding *chosen*."""

	held = adapter.DegreeSet(
		test_pitch_set.Composition(), name="degrees", title="Degrees 1",
		key=key or Key(), named=_named)

	if chosen:
		held.apply(["chosen"], list(chosen))

	return held


# --- What it declares and holds ------------------------------------------------

def test_a_degree_set_declares_its_octaves_and_the_most_steps_a_row_may_hold () -> None:
	"""Three octaves by default, and seven steps, which is the longest scale the
	composition offers; both are what a degree is checked against, on both halves."""

	declared = _set().declaration()

	assert declared["type"] == "degree_set"
	assert declared["octaves"] == [-1, 0, 1]
	assert declared["steps"] == 7
	assert declared["title"] == "Degrees 1"


def test_the_state_says_the_key_and_what_each_step_makes_in_it () -> None:
	"""**The labels come from the app** (#2144): the panel knows a button is degree 3
	and nothing else, so what degree 3 is — and what it is flattened or sharpened —
	travels in the state, where a key change can move it."""

	held = _set(Key("D", (0, 2, 3, 5, 7, 9, 10), "D dorian"), [_degree(3), _degree(7, 1, -1)])
	state = held.snapshot()

	assert state["chosen"] == [_degree(3), _degree(7, 1, -1)]
	assert state["enabled"] is True
	assert state["key"] == "D dorian"
	assert state["scale"][0] == {"note": "D", "flat": "C#", "sharp": "D#"}
	assert [one["note"] for one in state["scale"]] == ["D", "E", "F", "G", "A", "B", "C"]


def test_with_no_key_the_state_says_so_and_names_no_step () -> None:
	"""A degree means nothing until there is a key, and the glass has to say that
	rather than draw seven buttons that would play nothing."""

	state = _set(Key(None)).snapshot()

	assert state["key"] is None
	assert state["scale"] == []


def test_what_is_kept_is_what_was_chosen_and_not_what_the_key_made_of_it () -> None:
	"""The key is kept by the Key block; a set keeps its degrees, which is the point."""

	kept = _set(chosen=[_degree(1), _degree(5)]).kept()

	assert kept == {"chosen": [_degree(1), _degree(5)], "enabled": True}


# --- What it takes -------------------------------------------------------------

def test_a_set_keeps_the_order_its_degrees_were_chosen_in () -> None:
	"""A root chosen first stays first, as a fixed set's does."""

	held = _set(chosen=[_degree(5), _degree(1), _degree(3)])

	assert held.chosen == [_degree(5), _degree(1), _degree(3)]


@pytest.mark.parametrize(("chosen", "says"), [
	([_degree(0)], "step"),
	([_degree(8)], "step"),
	([_degree(3, 2)], "octave"),
	([_degree(3, 0, 2)], "flat or sharp"),
	([{"step": 3, "octave": 0}], "step, octave and chroma"),
	([{"step": True, "octave": 0, "chroma": 0}], "step"),
	([_degree(3), _degree(3, 0, -1)], "once in an octave"),
	("3", "a list"),
])
def test_a_degree_the_set_could_not_mean_is_refused (chosen: typing.Any, says: str) -> None:
	"""Checked by the one rule both halves read (`protocol.degrees_refusal`), so the
	app and the service cannot come to disagree about what a degree is."""

	with pytest.raises(adapter.Refused, match=says):
		_set().apply(["chosen"], chosen)


def test_a_set_switched_off_resolves_to_nothing_and_forgets_nothing () -> None:
	"""An empty pitch list is a thing every consumer already handles: an arpeggio rests."""

	held = _set(chosen=[_degree(1)])
	held.apply(["enabled"], False)

	assert held.notes() == []
	assert held.chosen == [_degree(1)]


def test_a_set_put_back_keeps_every_degree_it_still_can () -> None:
	"""One degree a narrower set no longer takes costs that degree, not the set."""

	held = _set()
	refused = held.restore({"chosen": [_degree(1), _degree(3, 5), _degree(5)], "enabled": False})

	assert held.chosen == [_degree(1), _degree(5)]
	assert held.enabled is False
	assert len(refused) == 1 and "octave" in refused[0]


# --- What it sounds ------------------------------------------------------------

def test_a_degree_is_the_note_its_step_makes_in_the_key_moved_by_octave_and_sign () -> None:
	"""**1, 3 and 5 are C, E and G in C major**; ♭7 an octave up is B♭5."""

	held = _set(chosen=[_degree(1), _degree(3), _degree(5), _degree(7, 1, -1), _degree(2, -1, 1)])

	assert held.notes() == [60, 64, 67, 82, 51]


def test_changing_the_key_changes_what_the_same_degrees_sound () -> None:
	"""The whole of #2527: nothing re-patched, and the part moves."""

	key = Key()
	held = _set(key, [_degree(1), _degree(3), _degree(5)])

	assert held.notes() == [60, 64, 67]

	key.root, key.steps, key.words = "D", [0, 2, 3, 5, 7, 9, 10], "D dorian"

	assert held.notes() == [62, 65, 69]


def test_a_step_the_scale_has_not_got_is_kept_and_not_played () -> None:
	"""**Kept and not played**, as a step past a pattern's end is (#2548): a seventh
	chosen in a major key goes quiet in a pentatonic one, and comes back when the
	scale is long enough again.  It is not carried into the next octave, which
	would sound a note nobody chose."""

	key = Key()
	held = _set(key, [_degree(1), _degree(7)])

	key.steps, key.words = [0, 2, 4, 7, 9], "C major pentatonic"

	assert held.notes() == [60]
	assert held.chosen == [_degree(1), _degree(7)]


def test_with_no_key_a_set_refuses_to_resolve_and_says_why () -> None:
	"""Not an empty list, which would be silence with nothing to say why."""

	with pytest.raises(adapter.Unresolved, match="no key is set"):
		_set(Key(None), [_degree(1)]).notes()


# --- Saying a key change -------------------------------------------------------

class Link:
	"""A link that hands work to the clock loop only when asked to run it."""

	def __init__ (self) -> None:
		"""Nothing queued and nothing said."""

		self.queued: list[typing.Callable[[], None]] = []
		self.reported: list[tuple[str, typing.Any]] = []
		self.controls: dict[str, typing.Any] = {}

	def on_clock (self, work: typing.Callable[[], None]) -> None:
		"""Queue *work* for the clock loop."""

		self.queued.append(work)

	def report (self, path: str, value: typing.Any) -> None:
		"""Keep what was said."""

		self.reported.append((path, value))

	def run (self) -> None:
		"""Be the clock loop for a moment."""

		while self.queued:
			self.queued.pop(0)()


def test_a_key_change_is_said_on_the_clock_loop_and_only_when_it_changed_something () -> None:
	"""**Handed to the clock loop**, because a key moved from the glass arrives there and
	one put back from the store is settled on the link thread, and a frame is numbered
	on the clock loop alone.  Said once: a second rekey to the same key says nothing."""

	key = Key()
	link = Link()
	held = _set(key)
	held.attach(typing.cast(typing.Any, link))
	held.declared()

	key.root, key.steps, key.words = "E", [0, 2, 3, 5, 7, 8, 10], "E minor"
	held.rekeyed()

	assert link.reported == [], "the key was said off the clock loop"

	link.run()
	held.rekeyed()
	link.run()

	assert [path for path, _ in link.reported] == ["degrees/key", "degrees/scale"]
	assert link.reported[0][1] == "E minor"
	assert [one["note"] for one in link.reported[1][1]] == ["E", "F#", "G", "A", "B", "C", "D"]


# --- Patched into a stack ------------------------------------------------------

def _stack (held: adapter.DegreeSet, pitches: dict[str, int] = test_pitch_set.BASS) -> adapter.Recipe:
	"""A stack over one instrument's rows, able to see one degree set."""

	recipe = adapter.Recipe(
		test_pitch_set.Composition(), catalogue=test_recipe.CATALOGUE,
		pitches=list(pitches), pitch_notes=pitches)
	recipe.link = typing.cast(typing.Any, test_recipe.Speaker({"degrees": held}))

	return recipe


def test_a_patched_parameter_arrives_folded_into_the_instrument_and_follows_the_key () -> None:
	"""Resolved at every build and folded exactly as fixed pitches are (#2374)."""

	key = Key()
	held = _set(key, [_degree(1), _degree(3), _degree(5)])
	recipe = _stack(held)
	patch = {"pitches": {"from": "control", "id": "degrees"}}

	assert recipe._arguments("evolve", patch)["pitches"] == ["C2", "E2", "G2"]

	key.root, key.steps, key.words = "D", [0, 2, 4, 5, 7, 9, 11], "D major"

	assert recipe._arguments("evolve", patch)["pitches"] == ["D2", "F#2", "A2"]


def test_a_layer_fed_by_a_set_with_no_key_rests_and_says_why_on_the_glass () -> None:
	"""**One layer, not the bar**: the other layers play, and the resting one is named
	in the report a panel draws beside it (#2368)."""

	held = _set(Key(None), [_degree(1)])
	grid = adapter.NoteGrid(test_pitch_set.Composition(), rows=list(test_pitch_set.BASS), name="bass")
	speaker = test_recipe.Speaker({"degrees": held, "bass": grid})
	recipe = adapter.Recipe(
		test_pitch_set.Composition(), catalogue=test_recipe.CATALOGUE,
		pitches=list(test_pitch_set.BASS), pitch_notes=test_pitch_set.BASS,
		builds="bass", pulses_per_beat=24)
	recipe.attach(typing.cast(typing.Any, speaker))

	builder = test_recipe.Builder()
	recipe.apply(["layers"], [
		{"id": "fed", "generator": "evolve", "params": {"pitches": {"from": "control", "id": "degrees"}}},
		{"id": "own", "generator": "euclidean", "params": {"pitch": "C2", "pulses": 3}},
	])
	recipe.build(builder)

	assert [name for name, _ in builder.calls] == ["euclidean"], "the resting layer played, or took the other with it"

	stalled = [fields for name, fields in speaker.events if name == "stalled"]

	assert stalled and list(stalled[-1]["layers"]) == ["fed"]
	assert "no key is set" in stalled[-1]["layers"]["fed"]


# --- The rule both halves read, and the service's copy -------------------------

def test_a_pitch_socket_takes_a_degree_set_as_well_as_a_pitch_set () -> None:
	"""One row in the patch table, naming both (#2419); anything else is still refused."""

	offered = adapter.Parameter("notes", "choices", options=[("C2", "C2")], role="pitch")
	patch = {"from": "control", "id": "degrees"}

	assert adapter.checked_value(offered, patch, {"degrees": "degree_set"}) == patch

	with pytest.raises(adapter.Refused, match="a set of pitches or degrees"):
		adapter.checked_value(offered, {"from": "control", "id": "clock"}, {"clock": "transport"})


DECLARED: dict[str, typing.Any] = {"degrees": _set().declaration()}


def test_the_service_keeps_a_degree_set_as_the_app_holds_it () -> None:
	"""**The seam** (#2517): every path the app reports, crossed, and the two copies equal."""

	key = Key()
	link = Link()
	held = _set(key)
	held.attach(typing.cast(typing.Any, link))
	held.declared()

	state = {"degrees": held.snapshot()}

	for rest, value in ((["chosen"], [_degree(3), _degree(7, 1, -1)]), (["enabled"], False)):
		held.apply(rest, value)
		controls.apply_change(state, DECLARED, "/".join(["degrees", *rest]), held.applied(rest, value))

	key.root, key.words = "G", "G major"
	held.rekeyed()
	link.run()

	for path, value in link.reported:
		controls.apply_change(state, DECLARED, path, value)

	assert state["degrees"] == held.snapshot()


def test_the_service_refuses_what_the_app_would_not_hold () -> None:
	"""The same sentence on both halves, from the one rule."""

	with pytest.raises(controls.ControlError, match="once in an octave"):
		controls.apply_change({}, DECLARED, "degrees/chosen", [_degree(2), _degree(2, 0, 1)])

	with pytest.raises(controls.ControlError):
		controls.apply_change({}, DECLARED, "degrees/notes", [])


def test_the_service_takes_a_cable_from_a_degree_set () -> None:
	"""And keeps it as a reference, never resolving it."""

	declarations = {
		**DECLARED,
		"stack": {"type": "recipe", "generators": [{
			"name": "arpeggio", "partial": False,
			"parameters": [{"name": "notes", "kind": "choices", "role": "pitch",
			                "required": True, "options": [{"value": "C2"}]}]}]},
	}
	state: dict[str, typing.Any] = {}

	controls.apply_change(state, declarations, "stack/layers",
	                      [{"id": "a", "kind": "generator", "generator": "arpeggio", "params": {}}])
	controls.apply_change(state, declarations, "stack/a/notes", {"from": "control", "id": "degrees"})

	assert state["stack"]["layers"][0]["params"]["notes"] == {"from": "control", "id": "degrees"}


def test_the_rule_about_a_degree_lives_in_the_protocol () -> None:
	"""A fact both halves must agree about lives in `protocol.py` (#2519)."""

	assert protocol.degrees_refusal([_degree(1), _degree(1, 1)], 7, [-1, 0, 1]) is None
	assert "degree_set" in protocol.CONTROL_KINDS
