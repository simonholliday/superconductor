"""A pitched pattern: a cell that is a note, with a length and a weight.

The first control kind that is not a grid of booleans, and the first whose cells
carry anything of their own.
"""

import typing

import pytest

import superintendent.controls
import superintendent.subsequence_adapter as adapter


DECLARED: dict[str, typing.Any] = {
	"type": "note_grid", "rows": ["C2", "C#2", "D2"], "steps": 8, "beats": 2,
	"mono": True, "default_length": 1, "default_velocity": 100}


class FakeComposition:
	"""Just the data dict an adapter writes through."""

	def __init__ (self) -> None:
		"""Start with nothing placed."""

		self.data: dict[str, typing.Any] = {}


class FakeLink:
	"""Records what the adapter said happened without being asked."""

	def __init__ (self) -> None:
		"""Start with nothing reported."""

		self.reported: list[tuple[str, typing.Any]] = []

	def report (self, path: str, value: typing.Any) -> None:
		"""Keep it."""

		self.reported.append((path, value))


def _grid (mono: bool = True) -> tuple[adapter.NoteGrid, FakeComposition, FakeLink]:
	"""A three-row, eight-step pattern with a link listening to it."""

	composition = FakeComposition()
	link = FakeLink()

	grid = adapter.NoteGrid(
		composition, rows=["C2", "C#2", "D2"], steps=8, beats=2,
		data_key="bass", name="bass", mono=mono)

	grid.attach(typing.cast(typing.Any, link))

	return grid, composition, link


# --- what the service understands ------------------------------------------

def test_a_note_is_placed_with_the_shape_the_app_declared () -> None:
	"""So a panel and the service agree about a note nobody has shaped yet."""

	state: dict[str, typing.Any] = {}

	superintendent.controls.apply_change(state, {"bass": DECLARED}, "bass/C2/4", True)

	assert state["bass"]["C2"]["4"] == {"length": 1, "velocity": 100}


def test_a_note_can_be_lengthened_and_weighted () -> None:
	"""The two things a note carries beyond being there at all."""

	state: dict[str, typing.Any] = {}
	controls = {"bass": DECLARED}

	superintendent.controls.apply_change(state, controls, "bass/C2/4", True)
	superintendent.controls.apply_change(state, controls, "bass/C2/4/length", 3)
	superintendent.controls.apply_change(state, controls, "bass/C2/4/velocity", 64)

	assert state["bass"]["C2"]["4"] == {"length": 3, "velocity": 64}


def test_shaping_a_note_that_is_not_there_is_refused () -> None:
	"""A length without a note is not a state the app could have reported."""

	with pytest.raises(superintendent.controls.ControlError):
		superintendent.controls.apply_change({}, {"bass": DECLARED}, "bass/C2/4/length", 3)


def test_a_row_with_no_notes_left_is_forgotten () -> None:
	"""So a snapshot carries what is there rather than where notes have been."""

	state: dict[str, typing.Any] = {}
	controls = {"bass": DECLARED}

	superintendent.controls.apply_change(state, controls, "bass/C2/4", True)
	superintendent.controls.apply_change(state, controls, "bass/C2/4", False)

	assert state["bass"] == {}


# --- what the app does ------------------------------------------------------

def test_placing_a_note_writes_it_where_the_pattern_builder_reads () -> None:
	"""The dict is the composition's; nothing wraps it (#2046)."""

	grid, composition, _ = _grid()

	assert grid.apply(["C2", "4"], True) is True
	assert composition.data["bass"]["C2"]["4"] == {"length": 1, "velocity": 100}


def test_placing_the_same_note_twice_changes_nothing () -> None:
	"""Absolute, never a toggle: asking twice reaches the same pattern as once."""

	grid, _, _ = _grid()

	grid.apply(["C2", "4"], True)

	assert grid.apply(["C2", "4"], True) is False


def test_a_monophonic_part_keeps_one_note_to_a_step_and_says_which_it_took () -> None:
	"""Enforced here rather than left to the instrument.

	A Minitaur handed two notes at once picks one by its own key-priority
	setting, which the panel cannot see — so the glass would show two notes
	while one sounded. The cleared note is reported in its own right, or a cell
	would go dark with nothing on the wire to explain it.
	"""

	grid, composition, link = _grid(mono=True)

	grid.apply(["C2", "4"], True)
	grid.apply(["D2", "4"], True)

	assert "4" not in composition.data["bass"]["C2"]
	assert composition.data["bass"]["D2"]["4"]["length"] == 1
	assert link.reported == [("bass/C2/4", False)]


def test_a_polyphonic_part_keeps_both () -> None:
	"""The same grid without the constraint, which is a chord."""

	grid, composition, link = _grid(mono=False)

	grid.apply(["C2", "4"], True)
	grid.apply(["D2", "4"], True)

	assert set(composition.data["bass"]["C2"]) == {"4"}
	assert set(composition.data["bass"]["D2"]) == {"4"}
	assert link.reported == []


def test_a_length_outside_the_pattern_is_refused_with_a_reason () -> None:
	"""The panel says why rather than showing a note that could not sound."""

	grid, _, _ = _grid()

	grid.apply(["C2", "4"], True)

	with pytest.raises(adapter.Refused):
		grid.apply(["C2", "4", "length"], 0)

	with pytest.raises(adapter.Refused):
		grid.apply(["C2", "4", "velocity"], 200)


def test_a_row_the_pattern_does_not_have_is_refused () -> None:
	"""Row names are the composition's, so a panel asking for another is wrong."""

	grid, _, _ = _grid()

	with pytest.raises(adapter.Refused):
		grid.apply(["G9", "0"], True)


def test_the_snapshot_shares_no_dict_with_the_clock_loop () -> None:
	"""It is read off the link thread while the loop may be building a bar."""

	grid, composition, _ = _grid()

	grid.apply(["C2", "4"], True)

	taken = grid.snapshot()
	taken["C2"]["4"]["velocity"] = 1

	assert composition.data["bass"]["C2"]["4"]["velocity"] == 100


def test_the_declaration_says_what_a_note_may_be () -> None:
	"""A panel cannot draw a control it has to guess the shape of."""

	grid, _, _ = _grid()

	declared = grid.declaration()

	assert declared["type"] == "note_grid"
	assert declared["mono"] is True
	assert declared["max_length"] == 8
	assert declared["velocity_range"] == [1, 127]
