"""An instrument's own settings: a switch, a number, a choice of names.

The three shapes that between them cover every control change a Minitaur
answers to, and the first controls here that are not about notes at all.
"""

import typing

import pytest

import superconductor.controls
import superconductor.subsequence_adapter as adapter


def _params () -> tuple[adapter.Params, typing.Any, list[tuple[str, typing.Any]]]:
	"""A small instrument with one of each kind, and a record of what moved."""

	class Composition:
		def __init__ (self) -> None:
			self.data: dict[str, typing.Any] = {}

	composition = Composition()
	moved: list[tuple[str, typing.Any]] = []

	settings = adapter.Params(
		composition,
		parameters=[
			adapter.Parameter("glide", "switch", label="Glide"),
			adapter.Parameter("rate", "number", label="Rate", default=24),
			adapter.Parameter("shape", "choice", label="Shape", default="lcr",
			                  options=[("lcr", "LCR"), ("exp", "EXP")]),
			adapter.Parameter("voicing", "action", label="Set voicing",
			                  options=[("one", "1"), ("two", "2")]),
		],
		data_key="moog", name="moog",
		on_change=lambda name, value: moved.append((name, value)))

	return settings, composition, moved


def test_a_setting_opens_where_the_composition_said () -> None:
	"""So a panel and the instrument agree before anybody has touched anything."""

	settings, composition, _ = _params()

	# The action is absent on purpose: it holds nothing, so there is nothing to
	# open it at and nowhere for a panel to read a state back from (#2179).
	assert composition.data["moog"] == {"glide": False, "rate": 24, "shape": "lcr"}
	assert settings.snapshot() == composition.data["moog"]


def test_the_declaration_carries_no_midi_at_all () -> None:
	"""A panel draws a switch. What that switch is wired to is the composition's
	business, which is the rule the rows of a grid follow (#1465)."""

	settings, _, _ = _params()

	declared = settings.declaration()

	assert declared["type"] == "params"
	assert [field["kind"] for field in declared["fields"]] == [
		"switch", "number", "choice", "action"]
	assert "cc" not in repr(declared), "no control-change number reaches the panel"
	assert declared["fields"][2]["options"] == [
		{"value": "lcr", "label": "LCR"}, {"value": "exp", "label": "EXP"}]


def test_a_parameter_says_what_it_is_measured_in_and_never_what_that_means () -> None:
	"""#2436, from Simon's decision #2435: *we cannot assume units in any interface.*

	A unit is a **free string in the app's own words**, carried beside `min` and
	`max` and drawn as it was given.  Nothing here enumerates units, converts
	between them, or has an opinion about any of them — a table of units would be
	this package knowing what a hertz is, which is the same mistake as knowing
	what a drum voice is (#1465).

	**Absent rather than null where there is none**, because most numbers are not
	measured in anything: a probability is a fraction of one and a count is a
	count, and inventing a word for either would be worse than the silence.
	"""

	said = superconductor.subsequence_adapter.Parameter(
		"cutoff", "number", minimum=0, maximum=127, unit="MIDI").declaration()

	assert said["unit"] == "MIDI"

	bare = superconductor.subsequence_adapter.Parameter(
		"amount", "number", minimum=0, maximum=1).declaration()

	assert "unit" not in bare, "a parameter with no unit was given an empty one"


def test_a_units_word_survives_the_round_trip_through_the_catalogue () -> None:
	"""The half a declaration test cannot see: a unit reaches a `Parameter` from an
	app's own catalogue entry and comes back out unchanged.

	`_as_parameter` is the reading in that direction and it had to be told about
	the field — a value refused by the wrong code is the fault `tests/test_seam.py`
	exists for, and a unit dropped on the way in is the same shape one layer down.
	"""

	held = superconductor.subsequence_adapter._as_parameter({
		"name": "duration", "kind": "number", "min": 0.05, "max": 4.0,
		"unit": "beats"})

	assert held.unit == "beats"
	assert held.declaration()["unit"] == "beats"

	assert superconductor.subsequence_adapter._as_parameter(
		{"name": "probability", "kind": "number"}).unit is None


def test_moving_a_setting_tells_the_composition_once () -> None:
	"""Which is where a control change gets sent, if that is what it stands for."""

	settings, composition, moved = _params()

	assert settings.apply(["glide"], True) is True
	assert settings.apply(["glide"], True) is False, "asking twice is the same as asking once"

	assert composition.data["moog"]["glide"] is True
	assert moved == [("glide", True)]


def test_a_setting_refuses_what_it_could_not_hold () -> None:
	"""With a reason, so the panel can say why rather than springing back."""

	settings, _, _ = _params()

	for rest, value in ((["glide"], 5), (["rate"], 500), (["shape"], "wobble"), (["nothing"], 1)):
		with pytest.raises(adapter.Refused):
			settings.apply(rest, value)


def test_the_service_checks_a_setting_against_what_was_declared () -> None:
	"""Its copy of the app's state has to be one the app could have reported."""

	declared = {
		"type": "params",
		"fields": [
			{"name": "glide", "kind": "switch"},
			{"name": "rate", "kind": "number", "min": 0, "max": 127},
			{"name": "shape", "kind": "choice",
			 "options": [{"value": "lcr"}, {"value": "exp"}]},
		]}

	state: dict[str, typing.Any] = {}
	controls = {"moog": declared}

	superconductor.controls.apply_change(state, controls, "moog/glide", True)
	superconductor.controls.apply_change(state, controls, "moog/rate", 100)
	superconductor.controls.apply_change(state, controls, "moog/shape", "exp")

	assert state["moog"] == {"glide": True, "rate": 100, "shape": "exp"}

	for path, value in (("moog/rate", 200), ("moog/shape", "wobble"), ("moog/glide", 1)):
		with pytest.raises(superconductor.controls.ControlError):
			superconductor.controls.apply_change(state, controls, path, value)


def test_every_setting_is_asserted_to_the_instrument_after_declaring () -> None:
	"""Nothing here can read an instrument's mind.

	A synthesiser holds its own settings, remembers them through a power cycle
	and says nothing about them — so a panel showing defaults is showing a
	guess. And because a value that has not changed sends no message, pressing
	the control cannot correct it either: the panel says off, the instrument is
	on, and tapping off does nothing at all. Asserting them makes the glass
	true rather than hopeful.
	"""

	settings, _, moved = _params()

	assert settings.owed() == [], "nothing is owed until the app declares itself"
	assert moved == []

	settings.declared()

	owed = settings.owed()

	assert sorted(owed) == [("glide", False), ("rate", 24), ("shape", "lcr")]

	# **Asking does not pay**, which is the whole point of the split: the
	# question is asked on the clock loop and the answer is acted on elsewhere.
	assert moved == [], "asking what is owed told the instrument on the clock loop"
	assert settings.poll() == [], "and nothing is reported to a panel by it either"

	settings.settle(owed)
	settings.settled()

	assert sorted(moved) == [("glide", False), ("rate", 24), ("shape", "lcr")]

	moved.clear()

	assert settings.owed() == [], "paid once, not every beat"


def test_a_reconnection_asserts_them_again () -> None:
	"""An app that has been away may have been restarted; the instrument was not."""

	settings, _, moved = _params()

	def pay () -> None:
		"""What the link does on a beat: ask, hand over, mark it settled."""

		owed = settings.owed()

		if owed:
			settings.settle(owed)
			settings.settled()

	settings.declared()
	pay()
	moved.clear()

	settings.declared()
	pay()

	assert len(moved) == 3


# --- a control that does something and holds nothing (#2179) ----------------

def test_an_action_tells_the_composition_and_stores_nothing () -> None:
	"""The whole of the kind, in one assertion pair.

	Something happened — the composition heard about it and can send a control
	change. Nothing changed — so no value is kept, here or anywhere, because the
	setting it moves cannot be read back and a remembered value would be a claim
	nobody can stand behind.
	"""

	settings, composition, moved = _params()

	changed = settings.apply(["voicing"], "two")

	assert moved == [("voicing", "two")]
	assert changed is False, "an action must report that nothing changed"
	assert "voicing" not in composition.data["moog"]
	assert "voicing" not in settings.snapshot()


def test_an_action_fires_every_time_rather_than_only_on_a_difference () -> None:
	"""A choice set to what it already holds does nothing; an action always acts.

	Pressing "all notes off" twice has to send twice, and pressing a voicing the
	instrument is already in is exactly how somebody recovers after moving the
	switch by hand — which is the case this kind was built for (#2177).
	"""

	settings, _, moved = _params()

	settings.apply(["voicing"], "two")
	settings.apply(["voicing"], "two")

	assert moved == [("voicing", "two"), ("voicing", "two")]


def test_an_action_refuses_an_option_the_app_never_offered () -> None:
	"""Holding nothing is not the same as accepting anything."""

	settings, _, moved = _params()

	with pytest.raises(adapter.Refused, match="no option called"):
		settings.apply(["voicing"], "sixteen")

	assert moved == []


def test_an_action_declares_its_options_so_a_panel_can_draw_them () -> None:
	"""It names them exactly as a choice does; only the state differs."""

	settings, _, _ = _params()

	field = next(f for f in settings.declaration()["fields"] if f["name"] == "voicing")

	assert field["kind"] == "action"
	assert [one["value"] for one in field["options"]] == ["one", "two"]
