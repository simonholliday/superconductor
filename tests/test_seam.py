"""What the adapter puts on the wire, and what the service will accept from it.

**This file exists because both halves of that join were correct by their own
tests and wrong together.**  Clearing a grid sent the adapter's whole snapshot —
rows *and* the mute — down a path named ``control/rows``; the service refused the
frame because ``enabled`` is not a declared row, logged it as a warning and left
its copy of the pattern exactly as it was.  The music went quiet and every panel
went on showing a full grid.

The Python unit tests stopped at the adapter, the page tests stopped at the
outgoing frame, and nothing ran a value the adapter actually produces through the
service the adapter actually talks to.  So the rule here is one assertion, made
for every path a panel can send:

    after a change, the service's copy of a control equals the app's own.

If those two ever disagree, a panel that reloads sees something different from
one that stayed connected — which is this project's most persistent class of
defect, reported three times and found by hand each time.
"""

import typing

import pytest

import superintendent.controls
import superintendent.subsequence_adapter as adapter


class Composition:
	"""The little of a composition a grid uses, and nothing more."""

	def __init__ (self) -> None:
		"""An empty data store and nowhere to send events."""

		self.data: dict[str, typing.Any] = {}
		self.listeners: dict[str, typing.Any] = {}

	def on_event (self, name: str, callback: typing.Any) -> None:
		"""Register a callback the way the real composition does."""

		self.listeners[name] = callback


def _agree (control: typing.Any, rest: list[str], value: typing.Any) -> None:
	"""Cross the join once: apply, report, accept, compare.

	The service's copy starts where a real one does — from the declaration — so
	this is the whole round trip a panel depends on, with nothing in it that the
	running system does not do.
	"""

	name = control.name
	declared = {name: control.declaration()}
	held = {name: control.snapshot()}

	control.apply(rest, value)

	# What the app tells every panel and the service, which for a whole-grid
	# write is not what was asked for.
	wire = control.applied(rest, value)

	superintendent.controls.apply_change(held, declared, "/".join([name, *rest]), wire)

	assert held[name] == control.snapshot(), (
		f"after {rest!r} the service holds {held[name]!r} "
		f"and the app holds {control.snapshot()!r}")


def _steps () -> typing.Any:
	"""A two-row step grid with a pattern already in it."""

	composition = Composition()
	grid = adapter.StepGrid(
		composition, rows=["kick", "snare"], steps=8, beats=2,
		data_key="grid", name="grid")

	composition.data["grid"] = {"kick": [0, 4], "snare": [2]}

	return grid


def _notes () -> typing.Any:
	"""A three-row note grid with one note in it."""

	composition = Composition()
	grid = adapter.NoteGrid(
		composition, rows=["C2", "C#2", "D2"], steps=8, beats=2,
		data_key="bass", name="bass", voices=None)

	composition.data["bass"] = {"C2": {"0": {"length": 1, "velocity": 100}}}

	return grid


@pytest.mark.parametrize(("rest", "value"), [
	(["rows"], {}),
	(["rows"], {"kick": [1, 3, 5]}),
	(["rows"], {"kick": [4, 0, 4], "snare": []}),
	(["kick", "2"], True),
	(["kick", "0"], False),
	(["enabled"], False),
])
def test_a_step_grid_and_the_service_agree_after_every_write (
	rest: list[str], value: typing.Any) -> None:
	"""Every path the panel can send to a step grid, crossed.

	``rows`` with ``{}`` is the clear button, and it is the one that was broken:
	the wire carried the mute inside the rows, the service threw the whole frame
	away, and its copy stayed lit.
	"""

	_agree(_steps(), rest, value)


@pytest.mark.parametrize(("rest", "value"), [
	(["rows"], {}),
	(["rows"], {"C2": {"3": {"length": 2, "velocity": 90}}}),
	(["C#2", "5"], True),
	(["C2", "0"], False),
	(["enabled"], False),
])
def test_a_note_grid_and_the_service_agree_after_every_write (
	rest: list[str], value: typing.Any) -> None:
	"""The same crossing for a pitched pattern, whose cells carry a shape."""

	_agree(_notes(), rest, value)


def test_clearing_a_grid_leaves_the_mute_where_it_was () -> None:
	"""The mute is not one of the rows, so replacing the rows must not take it.

	Both sides had to be told: the service clears the whole state object to make
	a replacement a replacement, and the panel builds a fresh one from the frame.
	Either one dropping `enabled` would silence the switch on a reload only —
	the worst shape of disagreement, because the panel that asked still looks
	right.
	"""

	grid = _steps()

	grid.apply(["enabled"], False)
	assert grid.snapshot()["enabled"] is False

	_agree(grid, ["rows"], {})

	assert grid.snapshot()["enabled"] is False, "clearing the rows turned the grid back on"


def test_a_whole_grid_write_is_answered_with_rows_and_not_the_snapshot () -> None:
	"""The fault itself, named.

	`applied` answers the path that was written.  `control/rows` names the rows,
	so the mute must not ride along inside them — the service validates every key
	of that value against the declared row names and refuses the frame entire if
	one is not a row.
	"""

	for grid in (_steps(), _notes()):
		wire = grid.applied(["rows"], {})

		assert "enabled" not in wire, (
			f"{grid.name}'s whole-grid write carries the mute among its rows: {wire!r}")

		# And the service agrees, rather than this being true only by inspection.
		superintendent.controls.apply_change(
			{grid.name: grid.snapshot()}, {grid.name: grid.declaration()},
			f"{grid.name}/rows", wire)
