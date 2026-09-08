"""Keeping a page's arrangement beside the composition that owns the page.

An arrangement is where the blocks sit and how tall they have been pulled — the
same kind of fact, travelling the same path, checked at the same door (#2227).
"""

import json
import pathlib

import superintendent.subsequence_adapter as adapter


def test_a_piece_nobody_has_arranged_yet_has_no_arrangement (tmp_path: pathlib.Path) -> None:
	"""Which is the ordinary case, not an error."""

	assert adapter.PageStore(tmp_path / "absent.pages.json").load() == {}


def test_an_arrangement_is_kept_and_read_back (tmp_path: pathlib.Path) -> None:
	"""Positions in cells and no sizes: a layout carrying pixels would be one
	person's screen imposed on another's (#2078)."""

	store = adapter.PageStore(tmp_path / "piece.pages.json")

	store.save("both", [{"name": "grid", "x": 0, "y": 0}, {"name": "layer", "x": 19, "y": 0}])

	assert store.load() == {"both": [{"name": "grid", "x": 0, "y": 0},
	                                 {"name": "layer", "x": 19, "y": 0}]}


def test_saving_one_page_leaves_the_others_alone (tmp_path: pathlib.Path) -> None:
	"""A person arranging one view must not lose the others."""

	store = adapter.PageStore(tmp_path / "piece.pages.json")

	store.save("both", [{"name": "grid", "x": 0, "y": 0}])
	store.save("solo", [{"name": "layer", "x": 4, "y": 2}])

	assert set(store.load()) == {"both", "solo"}


def test_a_file_that_cannot_be_read_costs_the_arrangement_and_not_the_music (
	tmp_path: pathlib.Path) -> None:
	"""Losing a layout is better than refusing to start the composition."""

	broken = tmp_path / "piece.pages.json"
	broken.write_text("{ this is not json")

	assert adapter.PageStore(broken).load() == {}


def test_an_interrupted_save_leaves_the_previous_arrangement_intact (
	tmp_path: pathlib.Path) -> None:
	"""Written next door and moved into place, so there is no moment at which
	the file holds half of a new layout."""

	path = tmp_path / "piece.pages.json"
	store = adapter.PageStore(path)

	store.save("both", [{"name": "grid", "x": 1, "y": 1}])

	assert json.loads(path.read_text())["both"][0]["x"] == 1
	assert not list(tmp_path.glob("*.part")), "nothing is left behind"


def test_a_page_declares_the_arrangement_it_has_been_given () -> None:
	"""And says nothing when it has none, so the panel places the parts itself."""

	page = adapter.Page("both", parts=["grid", "layer"], title="Both")

	assert "layout" not in page.declaration()
	assert page.declaration([{"name": "grid", "x": 2, "y": 0}])["layout"] == [
		{"name": "grid", "x": 2, "y": 0}]


# --- a height is part of an arrangement (#2227) ------------------------------

def test_a_part_may_say_how_tall_it_has_been_pulled () -> None:
	"""How many rows a grid *has* is the app's fact and does not move; how many
	of them somebody wants in front of them is theirs, and changes with what
	they are working on."""

	kept = adapter._readable_arrangement([{"name": "bass", "x": 0, "y": 0, "rows": 18}])

	assert kept == [{"name": "bass", "x": 0, "y": 0, "rows": 18}]


def test_a_part_nobody_has_resized_is_not_recorded_as_having_a_height () -> None:
	"""Rather than being written down at whatever the app happened to declare on
	the day it was first drawn — which would freeze it there, and would mean a
	panel too old to send a height silently pinned every block it touched."""

	kept = adapter._readable_arrangement([{"name": "bass", "x": 1, "y": 2}])

	assert kept == [{"name": "bass", "x": 1, "y": 2}]
	assert "rows" not in (kept or [{}])[0]


def test_a_height_of_nothing_is_refused_by_being_floored () -> None:
	"""A block of no rows is a block nobody can take hold of to make taller
	again, and it would come back that way after a restart.  This is the door
	that exists to stop an undrawable shape surviving one."""

	assert adapter._readable_arrangement(
		[{"name": "bass", "x": 0, "y": 0, "rows": 0}]) == [
		{"name": "bass", "x": 0, "y": 0, "rows": 1}]

	assert adapter._readable_arrangement(
		[{"name": "bass", "x": 0, "y": 0, "rows": -5}]) == [
		{"name": "bass", "x": 0, "y": 0, "rows": 1}]


def test_a_height_that_is_not_a_number_costs_the_whole_arrangement () -> None:
	"""The same answer this gives a position that cannot be read, and for the
	same reason: an arrangement is written to disk and handed back to every
	panel, so half of one is worse than none."""

	assert adapter._readable_arrangement(
		[{"name": "bass", "x": 0, "y": 0, "rows": "tall"}]) is None


def test_a_page_hands_back_the_height_with_the_position () -> None:
	"""Both halves or neither: a panel that got the position and not the height
	would draw an arrangement nobody made."""

	page = adapter.Page("bass", parts=["bass"], title="Bass")
	placed = [{"name": "bass", "x": 2, "y": 0, "rows": 18}]

	assert page.declaration(placed)["layout"] == placed


def test_a_grid_a_rack_made_is_drawn_where_the_rack_is () -> None:
	"""**A part nobody named on a page is drawn nowhere, with nothing saying so**
	— and a grid somebody has just asked for vanishing is the worst version of
	that (#2226).

	A page names its parts by hand and a grid made at run time was on none of
	them.  It is drawn immediately after the rack that made it, which is the
	rule a stack and a settings block already follow (#2211): a thing belonging
	to another thing is drawn wherever that thing is.
	"""

	page = adapter.Page("drums", parts=["grid", "rack"], title="Drums")

	assert page.declaration()["parts"] == ["grid", "rack"], "nothing made, nothing added"

	assert page.declaration(None, {"rack": ["rack-a", "rack-b"]})["parts"] == [
		"grid", "rack", "rack-a", "rack-b"]


def test_a_rack_on_no_page_puts_its_grids_on_none_either () -> None:
	"""Which is the same answer the rack itself gets, and the only consistent
	one: a page that drew grids from a rack it does not carry would be showing
	the output of something the person cannot see or reach."""

	page = adapter.Page("bass", parts=["bass"], title="Bass")

	assert page.declaration(None, {"rack": ["rack-a"]})["parts"] == ["bass"]
