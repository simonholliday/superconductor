"""A rack of grids a person made, and what happens on the link when they do.

`test_recipe.py` covers the other list-shaped control and the two are parallel on
purpose (#2226).  What is different here is that a rack's entries become
*controls*: the list is the panel's, and what each entry turns into is entirely
the composition's, handed in as a function.
"""

import pathlib
import typing

import pytest

import superconductor.subsequence_adapter as adapter


ROWS = ["kick", "snare", "hihat_1_closed"]


class Composition:
	"""Just the dict a control touches, as the rest of the suite uses."""

	def __init__ (self) -> None:
		"""Start with nothing in it."""

		self.data: dict[str, typing.Any] = {}


class Link:
	"""A link that keeps its controls and counts how often it was told to speak."""

	def __init__ (self) -> None:
		"""Start with nothing offered and nothing said."""

		self.controls: dict[str, typing.Any] = {}
		self.said = 0

	def redeclare (self) -> None:
		"""Write down that the controls changed, instead of sending anything."""

		self.said += 1


def _made (spec: dict[str, typing.Any]) -> typing.Any:
	"""What this composition turns one specification into.

	A `StepGrid` with no instrument behind it, which is what makes a grid the
	panel invented routable rather than audible.  Everything the package is not
	allowed to know — the step duration, the note map, the channel — is decided
	here, which is the whole point of the rack being handed a function.
	"""

	return adapter.StepGrid(
		Composition(), rows=spec["rows"], steps=spec["steps"],
		beats=spec["steps"] * 0.25,
		data_key=spec["name"], name=spec["name"],
		title=spec.get("title") or "Grid")


def _rack (store: typing.Any = None) -> tuple[adapter.GridRack, Link]:
	"""A rack over three voices, attached to a link."""

	rack = adapter.GridRack(
		Composition(), make=_made, rows=ROWS, steps=(1, 32),
		data_key="rack", name="rack", store=store)

	link = Link()
	rack.attach(typing.cast(typing.Any, link))

	return rack, link


def _grid (one: str = "a", rows: list[str] | None = None,
           steps: int = 16) -> dict[str, typing.Any]:
	"""One specification, as a panel would send it."""

	return {"id": one, "rows": rows or ["kick"], "steps": steps}


def test_a_rack_offers_the_rows_a_grid_may_be_made_from () -> None:
	"""Which rows exist is a fact about a studio, so the composition says it and
	this repeats it — the same join a stack's pitches make (#1465, #2085)."""

	rack, _ = _rack()
	declared = rack.declaration()

	assert declared["type"] == "grids"
	assert declared["rows"] == ROWS
	assert (declared["min_steps"], declared["max_steps"]) == (1, 32)


def test_asking_for_a_grid_puts_a_control_on_the_link () -> None:
	"""**The whole of #2226.**  There is no frame meaning *make me a control* and
	there does not need to be: the grid arrives as an ordinary declared control,
	and the app says its controls changed by declaring again."""

	rack, link = _rack()

	assert rack.apply(["grids"], [_grid("a", ["snare"], 9)]) is True

	made = [name for name in link.controls if name.startswith("rack-")]

	assert made == ["rack-a"]
	assert link.controls["rack-a"].rows == ["snare"]
	assert link.controls["rack-a"].steps == 9
	assert link.said == 1, "the link was not told the controls had changed"


def test_a_grid_that_leaves_the_list_leaves_the_link () -> None:
	"""Or a control nobody can see goes on being declared for ever, and a panel
	draws a block for a grid that is not in the rack."""

	rack, link = _rack()
	rack.apply(["grids"], [_grid("a"), _grid("b")])

	assert sorted(name for name in link.controls if name.startswith("rack-")) == [
		"rack-a", "rack-b"]

	rack.apply(["grids"], [_grid("b")])

	assert [name for name in link.controls if name.startswith("rack-")] == ["rack-b"]


def test_a_grid_that_stays_is_not_rebuilt () -> None:
	"""It holds the notes somebody has drawn on it, so remaking it on every
	change to the list would empty a grid because its neighbour was removed."""

	rack, link = _rack()
	rack.apply(["grids"], [_grid("a"), _grid("b")])

	was = link.controls["rack-a"]

	rack.apply(["grids"], [_grid("a"), _grid("b"), _grid("c")])

	assert link.controls["rack-a"] is was


def test_a_row_this_rack_never_offered_is_refused () -> None:
	"""The pool is the composition's statement about what exists here, and a grid
	holding a row outside it would be a grid whose notes nothing can play."""

	rack, _ = _rack()

	with pytest.raises(adapter.Refused, match="tom"):
		rack.apply(["grids"], [_grid("a", ["tom"])])


def test_a_grid_of_no_rows_is_refused_rather_than_made_empty () -> None:
	"""Unlike a height, there is no gesture that gets it back: an empty grid
	draws nothing to aim at, so it would be a block a person is stuck with."""

	rack, _ = _rack()

	with pytest.raises(adapter.Refused):
		rack.apply(["grids"], [{"id": "a", "rows": [], "steps": 16}])


def test_a_length_outside_the_bounds_is_refused () -> None:
	"""The bounds are the composition's, for the same reason a stack's are: how
	long a pattern may usefully be is a fact about this rig and not about grids."""

	rack, _ = _rack()

	with pytest.raises(adapter.Refused, match="1 to 32"):
		rack.apply(["grids"], [_grid("a", steps=64)])


def test_two_grids_of_one_name_are_refused_entire () -> None:
	"""Checked before anything is kept, so a bad list leaves the rack as it was
	rather than half-applied."""

	rack, link = _rack()
	rack.apply(["grids"], [_grid("a")])

	with pytest.raises(adapter.Refused, match="both call themselves"):
		rack.apply(["grids"], [_grid("b"), _grid("b")])

	assert [one["id"] for one in rack.grids()] == ["a"]


def test_the_same_list_again_changes_nothing () -> None:
	"""So a panel replaying what it holds does not cost a re-declaration, which
	every open panel would have to read."""

	rack, link = _rack()
	rack.apply(["grids"], [_grid("a")])
	before = link.said

	assert rack.apply(["grids"], [_grid("a")]) is False
	assert link.said == before


def test_what_somebody_made_comes_back_after_a_restart (
	tmp_path: pathlib.Path) -> None:
	"""**The cost this feature actually has** (#2226).  A restart already loses
	the notes on a grid (#2067); without this it would lose the grid itself,
	which is somebody losing what they made rather than what they played.

	What comes back is the grids, empty.  That is honest and it is better than
	nothing coming back at all.
	"""

	store = adapter.PageStore(tmp_path / "made.grids.json")

	rack, _ = _rack(store)
	rack.apply(["grids"], [_grid("a", ["snare"], 9)])

	again, link = _rack(adapter.PageStore(tmp_path / "made.grids.json"))

	assert [one["id"] for one in again.grids()] == ["a"]
	assert link.controls["rack-a"].steps == 9


def test_a_grid_that_goes_is_unmade_as_well_as_undeclared () -> None:
	"""**Taking the control off the link is not the whole of removing a grid.**

	Making one may have done more than build it — on the rig it also registers a
	play function, so the grid can be routed.  Left behind, that is a source a
	stack still offers for a grid nobody can see, which plays notes from a block
	that is not on the glass.
	"""

	undone: list[str] = []

	rack = adapter.GridRack(
		Composition(), make=_made, unmake=undone.append, rows=ROWS,
		data_key="rack", name="rack")

	rack.attach(typing.cast(typing.Any, Link()))
	rack.apply(["grids"], [_grid("a"), _grid("b")])

	assert undone == [], "nothing has gone yet"

	rack.apply(["grids"], [_grid("b")])

	assert undone == ["rack-a"]


def test_a_rack_with_nothing_to_undo_needs_no_undoing () -> None:
	"""What making does is the composition's business, and it may do nothing that
	needs reversing — so the second half is optional and its absence is not a
	special case anywhere."""

	rack, link = _rack()
	rack.apply(["grids"], [_grid("a")])
	rack.apply(["grids"], [])

	assert [name for name in link.controls if name.startswith("rack-")] == []
