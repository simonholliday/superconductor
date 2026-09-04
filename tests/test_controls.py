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
