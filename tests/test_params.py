"""An instrument's own settings: a switch, a number, a choice of names.

The three shapes that between them cover every control change a Minitaur
answers to, and the first controls here that are not about notes at all.
"""

import typing

import pytest

import superintendent.controls
import superintendent.subsequence_adapter as adapter


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
		],
		data_key="moog", name="moog",
		on_change=lambda name, value: moved.append((name, value)))

	return settings, composition, moved


def test_a_setting_opens_where_the_composition_said () -> None:
	"""So a panel and the instrument agree before anybody has touched anything."""

	settings, composition, _ = _params()

	assert composition.data["moog"] == {"glide": False, "rate": 24, "shape": "lcr"}
	assert settings.snapshot() == composition.data["moog"]


def test_the_declaration_carries_no_midi_at_all () -> None:
	"""A panel draws a switch. What that switch is wired to is the composition's
	business, which is the rule the rows of a grid follow (#1465)."""

	settings, _, _ = _params()

	declared = settings.declaration()

	assert declared["type"] == "params"
	assert [field["kind"] for field in declared["fields"]] == ["switch", "number", "choice"]
	assert "cc" not in repr(declared), "no control-change number reaches the panel"
	assert declared["fields"][2]["options"] == [
		{"value": "lcr", "label": "LCR"}, {"value": "exp", "label": "EXP"}]


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

	superintendent.controls.apply_change(state, controls, "moog/glide", True)
	superintendent.controls.apply_change(state, controls, "moog/rate", 100)
	superintendent.controls.apply_change(state, controls, "moog/shape", "exp")

	assert state["moog"] == {"glide": True, "rate": 100, "shape": "exp"}

	for path, value in (("moog/rate", 200), ("moog/shape", "wobble"), ("moog/glide", 1)):
		with pytest.raises(superintendent.controls.ControlError):
			superintendent.controls.apply_change(state, controls, path, value)


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
