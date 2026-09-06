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


def _grid (
	mono: bool = True,
	divisions: int = 1,
) -> tuple[adapter.NoteGrid, FakeComposition, FakeLink]:
	"""A three-row, eight-step pattern with a link listening to it."""

	composition = FakeComposition()
	link = FakeLink()

	grid = adapter.NoteGrid(
		composition, rows=["C2", "C#2", "D2"], steps=8, beats=2,
		data_key="bass", name="bass", mono=mono, divisions=divisions)

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

	# `.get`, because a row emptied by the mono rule is dropped exactly as a row
	# emptied by hand is — the two paths used to disagree about that.
	assert "4" not in composition.data["bass"].get("C2", {})
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


# --- a step that divides ----------------------------------------------------

def test_a_grid_that_declares_no_divisions_is_the_grid_it_always_was () -> None:
	"""Which is the whole point of the default.

	An app that never asks for precision must not have to know the field
	exists, and must not find its own dict re-keyed underneath it.
	"""

	grid, _, _ = _grid()

	assert grid.declaration()["divisions"] == 1
	assert grid.positions == 8
	assert grid.declaration()["max_length"] == 8


def test_a_grid_that_divides_a_step_takes_a_note_between_two_of_them () -> None:
	"""The position is the address, so a finer grid is simply a longer count."""

	grid, composition, _ = _grid(divisions=6)

	assert grid.positions == 48

	grid.apply(["C2", "9"], True)

	assert set(composition.data["bass"]["C2"]) == {"9"}


def test_a_position_off_the_end_is_refused_in_the_grid_own_units () -> None:
	"""And says positions rather than steps, because that is what it counted."""

	grid, _, _ = _grid(divisions=6)

	with pytest.raises(adapter.Refused, match="48 positions long"):
		grid.apply(["C2", "48"], True)


def test_a_length_may_run_the_whole_pattern_in_positions () -> None:
	"""A note as long as the bar is 48 of them where a step holds six."""

	grid, composition, _ = _grid(divisions=6)

	grid.apply(["C2", "0"], True)
	grid.apply(["C2", "0", "length"], 48)

	assert composition.data["bass"]["C2"]["0"]["length"] == 48

	with pytest.raises(adapter.Refused, match="between 1 and 48"):
		grid.apply(["C2", "0", "length"], 49)


# --- one note at a time means one at a time ---------------------------------

def test_a_monophonic_part_clears_a_note_it_would_sound_over () -> None:
	"""#2114, and the same root cause as a long note taking only one tap.

	Clearing by starting position alone let a note beginning part-way through
	another survive in a different row — which is exactly the case a Minitaur
	would have to arbitrate by its own key priority, and exactly what ``mono``
	exists to keep off the glass. Rare while every note was a step long; the
	ordinary case once a note can be dragged about.
	"""

	grid, composition, link = _grid(mono=True)

	grid.apply(["C2", "0"], True)
	grid.apply(["C2", "0", "length"], 4)
	grid.apply(["D2", "2"], True)

	assert "0" not in composition.data["bass"].get("C2", {}), "the note it sounds over is gone"
	assert set(composition.data["bass"]["D2"]) == {"2"}
	assert ("bass/C2/0", False) in link.reported


def test_lengthening_a_note_clears_what_it_now_reaches_over () -> None:
	"""Because a note that was clear of another a moment ago is not any more."""

	grid, composition, link = _grid(mono=True)

	grid.apply(["C2", "0"], True)
	grid.apply(["D2", "3"], True)

	assert set(composition.data["bass"]["D2"]) == {"3"}

	grid.apply(["C2", "0", "length"], 6)

	assert "D2" not in composition.data["bass"], "the note it grew over is gone"
	assert ("bass/D2/3", False) in link.reported


def test_a_note_ending_where_the_next_begins_is_a_line_and_not_a_clash () -> None:
	"""Half-open on the right, which is the shape a person draws by filling
	consecutive steps."""

	grid, composition, link = _grid(mono=True)

	grid.apply(["C2", "0"], True)
	grid.apply(["C2", "0", "length"], 2)
	grid.apply(["D2", "2"], True)

	assert set(composition.data["bass"]["C2"]) == {"0"}
	assert set(composition.data["bass"]["D2"]) == {"2"}
	assert link.reported == []


def test_changing_a_velocity_disturbs_nothing () -> None:
	"""It says nothing about when a note sounds, so it clears nothing."""

	grid, composition, link = _grid(mono=True)

	grid.apply(["C2", "0"], True)
	grid.apply(["C2", "0", "length"], 4)
	grid.apply(["C2", "0", "velocity"], 40)

	assert composition.data["bass"]["C2"]["0"] == {"length": 4, "velocity": 40}
	assert link.reported == []


def test_the_service_bounds_a_note_by_the_positions_a_grid_declared () -> None:
	"""The service holds its own copy and has to agree with the app about how
	long a pattern is, or a panel rejoining reads a different grid."""

	declared = {**DECLARED, "divisions": 6}
	state: dict[str, typing.Any] = {}

	superintendent.controls.apply_change(
		state, {"bass": declared}, "bass/C2/9", True)

	assert set(state["bass"]["C2"]) == {"9"}

	with pytest.raises(superintendent.controls.ControlError, match="48 positions wide"):
		superintendent.controls.apply_change(
			state, {"bass": declared}, "bass/C2/48", True)


# --- the mute, which a step grid had and this did not ----------------------

def test_a_pitched_grid_can_be_silenced () -> None:
	"""Simon reported this three times as "the control does nothing".

	It was never the control.  ``NoteGrid.apply`` had no branch for ``enabled``,
	so the path fell through to "that does not name a note" — the panel sent the
	change, the app refused it, and the face, which always follows the app,
	never moved.  A switch that does nothing, with the reason in a ``nack``
	nobody reads.

	The step grid beside it had the branch, which is why every check I ran
	passed: I was testing the grid that worked.
	"""

	grid, _, _ = _grid()

	assert grid.apply(["enabled"], False) is True
	assert grid.enabled is False

	assert grid.apply(["enabled"], False) is False, "an absolute set applied twice is one change"

	assert grid.apply(["enabled"], True) is True
	assert grid.enabled is True


def test_a_silenced_pitched_grid_says_so_in_its_snapshot () -> None:
	"""Or a panel arriving afterwards draws a live switch over a muted part."""

	grid, composition, _ = _grid()

	grid.apply(["C2", "0"], True)
	grid.apply(["enabled"], False)

	held = grid.snapshot()

	assert held["enabled"] is False
	assert held["C2"] == {"0": {"length": 1, "velocity": 100}}


def test_silencing_a_pitched_grid_mutes_the_pattern_it_drives () -> None:
	"""A mute in the sense a mixer means it: the notes stay and stop sounding."""

	composition = FakeComposition()
	muted: list[str] = []
	composition.mute = muted.append          # type: ignore[attr-defined]
	composition.unmute = lambda name: muted.remove(name)  # type: ignore[attr-defined]

	grid = adapter.NoteGrid(
		composition, rows=["C2"], steps=8, beats=2,
		data_key="bass", name="bass", pattern="bass")

	grid.apply(["enabled"], False)
	assert muted == ["bass"]

	grid.apply(["enabled"], True)
	assert muted == []
