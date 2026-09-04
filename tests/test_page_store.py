"""Keeping a page's arrangement beside the composition that owns the page."""

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
