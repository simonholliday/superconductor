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

	def alter (self, change: typing.Callable[[], None]) -> None:
		"""Make a change to what is offered, and count the declaration it causes.

		The real link hands this to its own loop, because that is where a
		declaration is built and where the dict must not be resized under one
		(#2341).  A link with no loop yet does it where it stands, which is what
		this stands in for.
		"""

		change()
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


def _rack () -> tuple[adapter.Rack, Link]:
	"""A rack over three voices, attached to a link."""

	rack = adapter.Rack(
		Composition(), make=_made, rows=ROWS, steps=(1, 32),
		data_key="rack", name="rack")

	link = Link()
	rack.attach(typing.cast(typing.Any, link))

	return rack, link


def _grid (one: str = "a", rows: list[str] | None = None,
           steps: int = 16) -> dict[str, typing.Any]:
	"""One specification, as a panel would send it."""

	return {"id": one, "rows": rows or ["kick"], "steps": steps}


def _kept () -> tuple[adapter.Rack, Link]:
	"""A rack that makes something with no length and nothing to choose.

	Which is what a set of pitches is: it holds notes rather than time, and which
	notes it holds is chosen on the thing itself rather than described in a form.
	"""

	rack = adapter.Rack(
		Composition(), make=_a_set, steps=None, makes="keyboard",
		data_key="keys", name="keys")

	link = Link()
	rack.attach(typing.cast(typing.Any, link))

	return rack, link


def _a_set (spec: dict[str, typing.Any]) -> typing.Any:
	"""What this composition makes of one specification, which is a set of pitches."""

	return adapter.PitchSet(
		Composition(), name=f"keys-{spec['id']}", title="Keyboard",
		pitches={"C4": 60, "E4": 64, "G4": 67})


def test_a_rack_says_what_it_makes_in_the_app_s_own_word () -> None:
	"""**The panel cannot write *make a keyboard*** because it does not know that a
	keyboard is one (#1465), so the word travels with the declaration.

	Simon, 2026-09-14, of an arpeggiator with nothing to feed it: *"For something
	generic like a keyboard source, which might feed any instrument, should we have
	a way of creating a new instance on the interface?"*
	"""

	assert _rack()[0].declaration()["makes"] == "grid"
	assert _kept()[0].declaration()["makes"] == "keyboard"


def test_a_rack_that_makes_something_with_no_length_declares_none () -> None:
	"""**Absent rather than sent as a floor**, the way a bound nobody declared is:
	a sheet drawing a length for a thing that has none is a row that does nothing,
	which is the silence this package refuses everywhere else."""

	declared = _kept()[0].declaration()

	assert "min_steps" not in declared, declared
	assert "max_steps" not in declared
	assert "opening_steps" not in declared
	assert declared["rows"] == [], "a rack with nothing to choose from offered a choice"


def test_making_one_of_those_needs_nothing_but_an_id () -> None:
	"""One press, because there is nothing to describe: no rows to pick and no
	length to set.  What it holds is chosen on the keyboard itself afterwards."""

	rack, link = _kept()

	assert rack.apply(["made"], [{"id": "a"}]) is True
	assert rack.entries() == [{"id": "a", "title": None}], rack.entries()
	assert sorted(link.controls) == ["keys-a"]


def test_a_specification_never_carries_a_field_that_means_nothing_to_it () -> None:
	"""A rack keeps what it asks for and drops the rest, so a length sent to a rack
	that has none does not come back as one — which would be a stored fact nothing
	reads and everything has to keep agreeing about."""

	rack, _ = _kept()
	rack.apply(["made"], [{"id": "a", "steps": 16, "rows": ["kick"]}])

	assert rack.entries() == [{"id": "a", "title": None}], rack.entries()


def test_a_rack_refuses_in_the_words_of_what_it_makes () -> None:
	"""A refusal is read on the glass by somebody who has just pressed *add
	keyboard*, so it has to say *keyboard* (#2403)."""

	rack, _ = _kept()

	with pytest.raises(adapter.Refused, match="a keyboard needs an id of its own"):
		rack.apply(["made"], [{}])

	with pytest.raises(adapter.Refused, match="two keyboards both call themselves"):
		rack.apply(["made"], [{"id": "a"}, {"id": "a"}])


def test_what_a_rack_made_comes_back_across_a_restart () -> None:
	"""Without this a restart would discard the thing's *existence*, which is a
	person losing something they made rather than something they played (#2067)."""

	rack, _ = _kept()
	rack.apply(["made"], [{"id": "a"}, {"id": "b"}])

	again, link = _kept()
	refused = again.restore(rack.kept())

	assert refused == []
	assert [one["id"] for one in again.entries()] == ["a", "b"]
	assert sorted(link.controls) == ["keys-a", "keys-b"]


def test_a_rack_reads_a_store_written_before_it_was_a_rack_of_things () -> None:
	"""A store from before contract 1.41.0 calls the list `grids`.

	**Read rather than refused**, because the alternative is a rig coming up saying
	STORE · TROUBLE about a rack that is perfectly fine — and a warning that is not
	true is worse than none.  Found by replaying this rig's own store against the
	renamed rack on 2026-09-14, where it would have cried wolf over an empty one.
	"""

	rack, link = _rack()
	refused = rack.restore({"grids": [_grid("a", ["snare"], 9)]})

	assert refused == [], refused
	assert [one["id"] for one in rack.entries()] == ["a"]
	assert sorted(link.controls) == ["rack-a"]


def test_a_rack_kept_as_neither_word_is_still_refused () -> None:
	"""The migration reads one other word and not anything at all: a rack kept as
	something that is not a list is a store to say something about."""

	rack, _ = _rack()

	assert rack.restore({"made": "a grid"}) == [
		"rack was kept as something other than a list of what it made"]
	assert rack.restore("nothing like a rack") == [
		"rack was kept as something other than a list of what it made"]


def test_a_rack_offers_the_rows_a_grid_may_be_made_from () -> None:
	"""Which rows exist is a fact about a studio, so the composition says it and
	this repeats it — the same join a stack's pitches make (#1465, #2085)."""

	rack, _ = _rack()
	declared = rack.declaration()

	assert declared["type"] == "rack"
	assert declared["rows"] == ROWS
	assert (declared["min_steps"], declared["max_steps"]) == (1, 32)


def test_asking_for_a_grid_puts_a_control_on_the_link () -> None:
	"""**The whole of #2226.**  There is no frame meaning *make me a control* and
	there does not need to be: the grid arrives as an ordinary declared control,
	and the app says its controls changed by declaring again."""

	rack, link = _rack()

	assert rack.apply(["made"], [_grid("a", ["snare"], 9)]) is True

	made = [name for name in link.controls if name.startswith("rack-")]

	assert made == ["rack-a"]
	assert link.controls["rack-a"].rows == ["snare"]
	assert link.controls["rack-a"].steps == 9
	assert link.said == 1, "the link was not told the controls had changed"


def test_a_grid_that_leaves_the_list_leaves_the_link () -> None:
	"""Or a control nobody can see goes on being declared for ever, and a panel
	draws a block for a grid that is not in the rack."""

	rack, link = _rack()
	rack.apply(["made"], [_grid("a"), _grid("b")])

	assert sorted(name for name in link.controls if name.startswith("rack-")) == [
		"rack-a", "rack-b"]

	rack.apply(["made"], [_grid("b")])

	assert [name for name in link.controls if name.startswith("rack-")] == ["rack-b"]


def test_a_grid_that_stays_is_not_rebuilt () -> None:
	"""It holds the notes somebody has drawn on it, so remaking it on every
	change to the list would empty a grid because its neighbour was removed."""

	rack, link = _rack()
	rack.apply(["made"], [_grid("a"), _grid("b")])

	was = link.controls["rack-a"]

	rack.apply(["made"], [_grid("a"), _grid("b"), _grid("c")])

	assert link.controls["rack-a"] is was


def test_a_row_this_rack_never_offered_is_refused () -> None:
	"""The pool is the composition's statement about what exists here, and a grid
	holding a row outside it would be a grid whose notes nothing can play."""

	rack, _ = _rack()

	with pytest.raises(adapter.Refused, match="tom"):
		rack.apply(["made"], [_grid("a", ["tom"])])


def test_a_grid_of_no_rows_is_refused_rather_than_made_empty () -> None:
	"""Unlike a height, there is no gesture that gets it back: an empty grid
	draws nothing to aim at, so it would be a block a person is stuck with."""

	rack, _ = _rack()

	with pytest.raises(adapter.Refused):
		rack.apply(["made"], [{"id": "a", "rows": [], "steps": 16}])


def test_a_length_outside_the_bounds_is_refused () -> None:
	"""The bounds are the composition's, for the same reason a stack's are: how
	long a pattern may usefully be is a fact about this rig and not about grids."""

	rack, _ = _rack()

	with pytest.raises(adapter.Refused, match="1 to 32"):
		rack.apply(["made"], [_grid("a", steps=64)])


def test_two_grids_of_one_name_are_refused_entire () -> None:
	"""Checked before anything is kept, so a bad list leaves the rack as it was
	rather than half-applied."""

	rack, link = _rack()
	rack.apply(["made"], [_grid("a")])

	with pytest.raises(adapter.Refused, match="both call themselves"):
		rack.apply(["made"], [_grid("b"), _grid("b")])

	assert [one["id"] for one in rack.entries()] == ["a"]


def test_the_same_list_again_changes_nothing () -> None:
	"""So a panel replaying what it holds does not cost a re-declaration, which
	every open panel would have to read."""

	rack, link = _rack()
	rack.apply(["made"], [_grid("a")])
	before = link.said

	assert rack.apply(["made"], [_grid("a")]) is False
	assert link.said == before


def test_what_somebody_made_comes_back_after_a_restart () -> None:
	"""**The cost this feature actually has** (#2226).  Without it a restart would
	lose the grid itself, which is somebody losing what they made rather than
	what they played.

	The link's pattern store keeps the list with everything else a person made
	(#2487), and `tests/test_pattern_store.py` restarts a whole piece; this is the
	rack's own half — what it keeps, and making it all again from that.
	"""

	rack, _ = _rack()
	rack.apply(["made"], [_grid("a", ["snare"], 9)])

	again, link = _rack()

	assert again.restore(rack.kept()) == []
	assert [one["id"] for one in again.entries()] == ["a"]
	assert link.controls["rack-a"].steps == 9


def test_a_kept_grid_the_rack_no_longer_offers_costs_that_grid_alone () -> None:
	"""Each grid stands alone, so a row dropped from the rack between two starts
	costs the grid that used it and not every grid a person made."""

	rack, _ = _rack()
	rack.apply(["made"], [_grid("a", ["snare"]), _grid("b", ["kick"])])

	kept = rack.kept()
	kept["made"][0]["rows"] = ["cowbell"]

	again, link = _rack()
	refused = again.restore(kept)

	assert len(refused) == 1 and "cowbell" in refused[0]
	assert [one["id"] for one in again.entries()] == ["b"]
	assert "rack-b" in link.controls


def test_a_grid_that_goes_is_unmade_as_well_as_undeclared () -> None:
	"""**Taking the control off the link is not the whole of removing a grid.**

	Making one may have done more than build it — on the rig it also registers a
	play function, so the grid can be routed.  Left behind, that is a source a
	stack still offers for a grid nobody can see, which plays notes from a block
	that is not on the glass.
	"""

	undone: list[str] = []

	rack = adapter.Rack(
		Composition(), make=_made, unmake=undone.append, rows=ROWS,
		data_key="rack", name="rack")

	rack.attach(typing.cast(typing.Any, Link()))
	rack.apply(["made"], [_grid("a"), _grid("b")])

	assert undone == [], "nothing has gone yet"

	rack.apply(["made"], [_grid("b")])

	assert undone == ["rack-a"]


def test_a_rack_with_nothing_to_undo_needs_no_undoing () -> None:
	"""What making does is the composition's business, and it may do nothing that
	needs reversing — so the second half is optional and its absence is not a
	special case anywhere."""

	rack, link = _rack()
	rack.apply(["made"], [_grid("a")])
	rack.apply(["made"], [])

	assert [name for name in link.controls if name.startswith("rack-")] == []


def test_a_grid_is_put_on_the_link_by_the_link_and_not_by_the_clock () -> None:
	"""**The dict the declare walks is resized where the declare runs** (#2341).

	`AppLink._declare` walks `self.controls` four times on the link loop, and a
	rack made and unmade grids in it from the clock loop — so a press on *make*
	while another panel's declare was in flight could resize it mid-iteration and
	kill that declare with *dictionary changed size during iteration*.  It needs a
	second declare already running, which two panels make ordinary: the rig has
	run with two more than once.

	The deterministic sibling of this fault took the app down on start and is
	fixed (`a4b7e74`).  Here the rack hands the change over instead of making it,
	so this link keeps it rather than running it, and nothing has moved until it
	does.
	"""

	class Deferring (Link):
		"""A link that holds what it was handed until somebody runs it."""

		def __init__ (self) -> None:
			"""Nothing offered, nothing said, nothing waiting."""

			super().__init__()

			self.waiting: list[typing.Callable[[], None]] = []

		def alter (self, change: typing.Callable[[], None]) -> None:
			"""Keep the change, as a loop with work ahead of it would."""

			self.waiting.append(change)

	rack = adapter.Rack(
		Composition(), make=_made, rows=ROWS, steps=(1, 32), data_key="rack", name="rack")
	link = Deferring()

	rack.attach(typing.cast(typing.Any, link))

	assert rack.apply(["made"], [_grid("a")]) is True
	assert link.controls == {}, "the clock loop resized the dict the link loop walks"
	assert rack.names() == [], "and said it had made one before the link agreed"

	for change in link.waiting:
		change()

	assert "rack-a" in link.controls, "the grid never reached the link"
	assert rack.names() == ["rack-a"], "the rack does not know what it put there"
