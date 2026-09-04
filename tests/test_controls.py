"""A cell's address, and what writing to one does to an app's state."""

import typing

import pytest

import superintendent.controls


GRID: dict[str, typing.Any] = {"grid": {"type": "step_grid", "rows": ["kick", "snare"], "steps": 16}}


def test_an_address_names_a_control_a_row_and_a_step () -> None:
	"""``grid/kick/4`` is the fourth step of the kick row."""

	assert superintendent.controls.parse_path("grid/kick/4") == ("grid", "kick", 4)


@pytest.mark.parametrize("path", ["grid/kick", "grid/kick/4/5", "grid/kick/last", ""])
def test_an_address_of_the_wrong_shape_is_refused (path: str) -> None:
	"""Nothing is guessed from an address that does not name a cell."""

	with pytest.raises(superintendent.controls.ControlError):
		superintendent.controls.parse_path(path)


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
