"""A cell's address, and what writing to one does to an app's state."""

import typing

import pytest

import superintendent.controls


GRID: dict[str, typing.Any] = {
	"grid": {"type": "step_grid", "rows": ["kick", "snare"], "steps": 16},
	"transport": {"type": "transport", "fields": ["silenced", "bpm"]},
}


def test_an_address_names_a_control_and_the_way_into_it () -> None:
	"""How many parts follow depends on the kind of control, so both shapes parse."""

	assert superintendent.controls.parse_path("grid/kick/4") == ("grid", ["kick", "4"])
	assert superintendent.controls.parse_path("transport/bpm") == ("transport", ["bpm"])


@pytest.mark.parametrize("path", ["", "grid", "grid/", "/kick/4"])
def test_an_address_naming_no_control_or_nothing_within_it_is_refused (path: str) -> None:
	"""A path has to say both what it addresses and what part of it."""

	with pytest.raises(superintendent.controls.ControlError):
		superintendent.controls.parse_path(path)


@pytest.mark.parametrize("path", ["grid/kick", "grid/kick/4/5", "grid/kick/last"])
def test_an_address_of_the_wrong_shape_for_a_grid_is_refused (path: str) -> None:
	"""A grid cell is a row and a step; the check belongs where the kind is known."""

	with pytest.raises(superintendent.controls.ControlError):
		superintendent.controls.apply_change({}, GRID, path, True)


def test_a_transport_field_is_written_by_name () -> None:
	"""A transport carries named fields rather than cells."""

	state: dict[str, typing.Any] = {}

	superintendent.controls.apply_change(state, GRID, "transport/silenced", True)
	superintendent.controls.apply_change(state, GRID, "transport/bpm", 137.5)

	assert state["transport"] == {"silenced": True, "bpm": 137.5}


@pytest.mark.parametrize("path", ["transport/tempo", "transport/bpm/2", "transport"])
def test_a_transport_field_that_was_not_declared_is_refused (path: str) -> None:
	"""The declaration is the boundary here too."""

	with pytest.raises(superintendent.controls.ControlError):
		superintendent.controls.apply_change({}, GRID, path, 1)


def test_switching_a_cell_on_adds_its_step_in_order () -> None:
	"""A row holds the steps that sound, lowest first."""

	state: dict[str, typing.Any] = {}

	superintendent.controls.apply_change(state, GRID, "grid/kick/8", True)
	superintendent.controls.apply_change(state, GRID, "grid/kick/0", True)

	assert state["grid"]["kick"] == [0, 8]


def test_switching_a_cell_off_removes_it () -> None:
	"""And leaves the rest of the row alone."""

	state: dict[str, typing.Any] = {"grid": {"kick": [0, 4, 8]}}

	superintendent.controls.apply_change(state, GRID, "grid/kick/4", False)

	assert state["grid"]["kick"] == [0, 8]


def test_writing_the_same_value_twice_changes_nothing () -> None:
	"""Absolute values are what make a re-send after a reconnect safe."""

	state: dict[str, typing.Any] = {}

	superintendent.controls.apply_change(state, GRID, "grid/kick/4", True)
	superintendent.controls.apply_change(state, GRID, "grid/kick/4", True)

	assert state["grid"]["kick"] == [4]


@pytest.mark.parametrize("path", ["mixer/kick/4", "grid/cowbell/4", "grid/kick/16", "grid/kick/99"])
def test_a_cell_outside_what_the_app_declared_is_refused (path: str) -> None:
	"""The declaration is the boundary; nothing outside it is written."""

	with pytest.raises(superintendent.controls.ControlError):
		superintendent.controls.apply_change({}, GRID, path, True)


RANGED: dict[str, typing.Any] = {
	"recipe": {"type": "params", "fields": [
		{"name": "velocity", "kind": "range", "min": 1, "max": 127},
	]},
}


def test_a_range_takes_two_numbers_in_order () -> None:
	"""Which is what a generator means by ``velocity=(30, 50)``."""

	state: dict[str, typing.Any] = {}

	superintendent.controls.apply_change(state, RANGED, "recipe/velocity", [30, 50])

	assert state == {"recipe": {"velocity": [30, 50]}}


def test_a_range_may_have_both_ends_together () -> None:
	"""One fixed velocity is a range that has not been opened, not a refusal.

	A generator declaring ``velocity=100`` opens here, so a range that could not
	hold a pair of equals could not carry its own author's default.
	"""

	state: dict[str, typing.Any] = {}

	superintendent.controls.apply_change(state, RANGED, "recipe/velocity", [100, 100])

	assert state["recipe"]["velocity"] == [100, 100]


def test_a_range_arriving_as_a_tuple_is_kept_as_a_list () -> None:
	"""So the service's copy compares equal to the same value off the wire.

	JSON has no tuple.  Keeping one here would make the app's copy and the
	service's differ by type while reading identically in a log.
	"""

	state: dict[str, typing.Any] = {}

	superintendent.controls.apply_change(state, RANGED, "recipe/velocity", (30, 50))

	assert state["recipe"]["velocity"] == [30, 50]
	assert isinstance(state["recipe"]["velocity"], list)


SEVERAL: dict[str, typing.Any] = {
	"recipe": {"type": "params", "fields": [
		{"name": "pitches", "kind": "choices", "role": "pitch", "options": [
			{"value": "kick", "label": "kick"},
			{"value": "snare", "label": "snare"},
			{"value": "clap", "label": "clap"},
		]},
	]},
}


def test_choices_takes_several_of_the_pool_and_keeps_the_order () -> None:
	"""Which is what a chord generator means by three pitches.

	The order is kept rather than sorted, because the pitches of a chord are not
	a set: a generator handed a root first is entitled to use that.
	"""

	state: dict[str, typing.Any] = {}

	superintendent.controls.apply_change(state, SEVERAL, "recipe/pitches", ["snare", "kick"])

	assert state == {"recipe": {"pitches": ["snare", "kick"]}}


def test_choices_may_be_empty () -> None:
	"""Nothing chosen is a state a person passes through on the way to choosing.

	Whether a generator with no pitches is worth running is the app's business;
	this validates the shape of a value and not the wisdom of it.
	"""

	state: dict[str, typing.Any] = {}

	superintendent.controls.apply_change(state, SEVERAL, "recipe/pitches", [])

	assert state["recipe"]["pitches"] == []


def test_choices_keeps_its_own_list_rather_than_the_caller_s () -> None:
	"""For the reason a range is copied: the service's copy is the service's.

	Holding the list that arrived would let a later edit of it change the
	service's idea of what the app reported, without anything on the wire.
	"""

	state: dict[str, typing.Any] = {}
	sent = ["kick", "snare"]

	superintendent.controls.apply_change(state, SEVERAL, "recipe/pitches", sent)
	sent.append("clap")

	assert state["recipe"]["pitches"] == ["kick", "snare"]


@pytest.mark.parametrize("value", [
	"kick",                     # one of them is not several of them
	["kick", "cowbell"],        # not in the pool
	["kick", "kick"],           # twice says nothing once does not
	[["kick"]],                 # a value a set could not even hold
	None,
])
def test_choices_that_are_not_several_of_the_pool_are_refused (value: typing.Any) -> None:
	"""The service keeps the app's state, so a value the app could not have
	reported has to be refused rather than stored."""

	with pytest.raises(superintendent.controls.ControlError):
		superintendent.controls.apply_change({}, SEVERAL, "recipe/pitches", value)


@pytest.mark.parametrize("value", [
	[50, 30],       # out of order
	[0, 50],        # below the floor
	[30, 200],      # above the ceiling
	[30],           # not two
	[30, 40, 50],   # not two
	30,             # not a pair at all
	[True, False],  # booleans are not numbers here
])
def test_a_range_that_is_not_two_numbers_in_bounds_is_refused (value: typing.Any) -> None:
	"""The service keeps the app's state, so a value the app could not have
	reported has to be refused rather than stored."""

	with pytest.raises(superintendent.controls.ControlError):
		superintendent.controls.apply_change({}, RANGED, "recipe/velocity", value)


STACK: dict[str, typing.Any] = {
	"recipe": {"type": "recipe", "generators": [
		{"name": "euclidean", "parameters": [
			{"name": "pulses", "kind": "number", "min": 0, "max": 16},
			{"name": "velocity", "kind": "range", "min": 1, "max": 127},
		]},
		{"name": "thin", "parameters": [
			{"name": "amount", "kind": "number", "min": 0.0, "max": 1.0},
		]},
	], "sources": ["shared"]},
}


def _one_layer () -> list[dict[str, typing.Any]]:
	"""A stack of one, which is what a part has the moment a generator is added."""

	return [{"id": "a", "generator": "euclidean", "params": {"pulses": 7}}]


def test_a_stack_is_set_whole_because_its_order_is_part_of_its_value () -> None:
	"""Adding, removing, bypassing and reordering all change the list itself."""

	state: dict[str, typing.Any] = {}

	superintendent.controls.apply_change(state, STACK, "recipe/layers", _one_layer())

	assert state["recipe"]["layers"] == [
		{"id": "a", "kind": "generator", "generator": "euclidean",
		 "bypassed": False, "params": {"pulses": 7}}]


def test_a_layer_may_take_from_a_pattern_instead_of_a_generator () -> None:
	"""One mechanism, not two.  A generator contributes notes to a pattern and a
	grid contributes notes to a pattern, and Simon settled that this is the same
	thing in effect (#2108) — so a layer says which kind it is and carries the
	one fact that says what it plays.
	"""

	state: dict[str, typing.Any] = {}

	superintendent.controls.apply_change(state, STACK, "recipe/layers", [
		{"id": "a", "kind": "pattern", "source": "shared"}])

	assert state["recipe"]["layers"] == [
		{"id": "a", "kind": "pattern", "bypassed": False,
		 "source": "shared", "params": {}}]


def test_a_layer_may_not_take_from_a_pattern_the_app_does_not_offer () -> None:
	"""Which grids a stack may take from is the app's to say, for the same
	reason the generators are: this package does not know that a grid exists,
	let alone which of them belongs to an instrument."""

	state: dict[str, typing.Any] = {}

	with pytest.raises(superintendent.controls.ControlError):
		superintendent.controls.apply_change(state, STACK, "recipe/layers", [
			{"id": "a", "kind": "pattern", "source": "nowhere"}])


def test_a_layers_number_survives_the_service () -> None:
	"""The number a person reads on a window, which the app hands out.

	This list is a whitelist, and a field it does not name is dropped — which
	does not show until a panel reloads, because until then the panel is reading
	the ``changed`` frame and that carries what the app actually said.  So the
	numbers appeared on the glass, and came back without them.  Anything added
	to a layer has to be added there too, and this is what says so.
	"""

	state: dict[str, typing.Any] = {}

	superintendent.controls.apply_change(state, STACK, "recipe/layers", [
		{"id": "a", "generator": "euclidean", "index": 3, "params": {}}])

	assert state["recipe"]["layers"][0]["index"] == 3


def test_a_layer_with_no_number_is_not_given_one_here () -> None:
	"""It is the app's to hand out.  Inventing one would put a number on the
	glass that the app has never heard of and would not keep."""

	state: dict[str, typing.Any] = {}

	superintendent.controls.apply_change(state, STACK, "recipe/layers", [
		{"id": "a", "generator": "euclidean", "params": {}},
		{"id": "b", "generator": "euclidean", "index": 0, "params": {}},
		{"id": "c", "generator": "euclidean", "index": "two", "params": {}},
	])

	assert all("index" not in layer for layer in state["recipe"]["layers"])


def test_the_order_a_stack_is_given_in_is_the_order_it_is_kept_in () -> None:
	"""A fill that skips where a note already sits depends on what ran before it."""

	state: dict[str, typing.Any] = {}
	stack = [
		{"id": "a", "generator": "euclidean", "params": {}},
		{"id": "b", "generator": "thin", "params": {}},
	]

	superintendent.controls.apply_change(state, STACK, "recipe/layers", stack)
	superintendent.controls.apply_change(state, STACK, "recipe/layers", list(reversed(stack)))

	assert [layer["id"] for layer in state["recipe"]["layers"]] == ["b", "a"]


def test_one_knob_of_one_layer_moves_without_sending_the_stack () -> None:
	"""Which is what turning a knob does, and it must not overwrite a neighbour."""

	state: dict[str, typing.Any] = {}

	superintendent.controls.apply_change(state, STACK, "recipe/layers", _one_layer())
	superintendent.controls.apply_change(state, STACK, "recipe/a/velocity", [30, 50])

	assert state["recipe"]["layers"][0]["params"] == {"pulses": 7, "velocity": [30, 50]}


def test_a_layer_naming_a_generator_the_app_does_not_offer_is_refused () -> None:
	"""The catalogue comes from the app, so this can only be a fault in the panel."""

	with pytest.raises(superintendent.controls.ControlError):
		superintendent.controls.apply_change(
			{}, STACK, "recipe/layers", [{"id": "a", "generator": "invented", "params": {}}])


def test_a_parameter_no_generator_has_is_refused () -> None:
	"""Validated through the same path an instrument's settings take, so a
	range or a bound behaves identically wherever it appears."""

	with pytest.raises(superintendent.controls.ControlError):
		superintendent.controls.apply_change(
			{}, STACK, "recipe/layers",
			[{"id": "a", "generator": "thin", "params": {"pulses": 7}}])


def test_a_parameter_out_of_its_declared_bounds_is_refused () -> None:
	"""The service keeps the app's copy; a value the app could not hold is a lie."""

	with pytest.raises(superintendent.controls.ControlError):
		superintendent.controls.apply_change(
			{}, STACK, "recipe/layers",
			[{"id": "a", "generator": "thin", "params": {"amount": 4.0}}])


def test_two_layers_may_not_share_an_id () -> None:
	"""A parameter is addressed by its layer's id, so a repeat makes one of the
	two unreachable — and which one would depend on the order of a search."""

	with pytest.raises(superintendent.controls.ControlError):
		superintendent.controls.apply_change({}, STACK, "recipe/layers", [
			{"id": "a", "generator": "euclidean", "params": {}},
			{"id": "a", "generator": "thin", "params": {}},
		])


def test_a_bad_layer_leaves_the_stack_that_was_there_alone () -> None:
	"""Checked entire before any of it is kept, so a stack is never half-new."""

	state: dict[str, typing.Any] = {}

	superintendent.controls.apply_change(state, STACK, "recipe/layers", _one_layer())

	with pytest.raises(superintendent.controls.ControlError):
		superintendent.controls.apply_change(state, STACK, "recipe/layers", [
			{"id": "a", "generator": "euclidean", "params": {}},
			{"id": "b", "generator": "invented", "params": {}},
		])

	assert [layer["id"] for layer in state["recipe"]["layers"]] == ["a"]


def test_a_parameter_of_a_layer_that_is_not_there_is_refused () -> None:
	"""A stale panel asking after a layer somebody else removed."""

	state: dict[str, typing.Any] = {}

	superintendent.controls.apply_change(state, STACK, "recipe/layers", _one_layer())

	with pytest.raises(superintendent.controls.ControlError):
		superintendent.controls.apply_change(state, STACK, "recipe/gone/pulses", 3)


def test_a_layer_says_what_kind_of_contribution_it_is () -> None:
	"""One kind so far. A pattern is the other — a grid belonging to no
	instrument, routed into several so two synths can share a bassline and each
	add notes of its own — and Simon settled that it is the same mechanism
	rather than a second one.

	The field is here now so that the second kind is an addition rather than a
	rewrite, and it defaults, so a stack written before it existed still reads.
	"""

	state: dict[str, typing.Any] = {}

	superintendent.controls.apply_change(
		state, STACK, "recipe/layers", [{"id": "a", "generator": "euclidean"}])

	assert state["recipe"]["layers"][0]["kind"] == "generator"


def test_a_kind_of_contribution_this_version_does_not_know_is_refused () -> None:
	"""Rather than kept as a layer nothing will ever play."""

	with pytest.raises(superintendent.controls.ControlError):
		superintendent.controls.apply_change(
			{}, STACK, "recipe/layers",
			[{"id": "a", "kind": "invented", "generator": "euclidean"}])
