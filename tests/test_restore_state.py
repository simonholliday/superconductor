"""Putting a capture back through the panel's own socket, exactly (#2465).

`tools/restore_state.py` replays a capture as the sets a finger would send.  It
used to send a grid a cell at a time, which can only add, so every step a
composition seeds on start and somebody had taken out came back — twice on
2026-09-11, each time with a clean summary.  A grid goes back as one whole-grid
write now, which is how a grid is cleared.
"""

import importlib.util
import types
import typing

import superconductor.subsequence_adapter as adapter


def _tool () -> typing.Any:
	"""The restore tool, imported as a module — which runs nothing since #2465."""

	spec = importlib.util.spec_from_file_location("restore_state", "tools/restore_state.py")
	assert spec is not None and spec.loader is not None

	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)

	return module


DECLARED: dict[str, typing.Any] = {
	"grid": {"type": "step_grid"},
	"bass": {"type": "note_grid"},
	"rack": {"type": "grids"},
	"synth": {"type": "params"},
	"stack": {"type": "recipe"},
}
"""What an app declares, reduced to the one word the tool reads off each."""


def test_a_grid_goes_back_as_one_write_of_every_row_and_then_its_mute () -> None:
	"""One write replaces what the grid holds — the empty rows as much as the full
	ones, which is what takes a seeded step out."""

	asks = _tool()._sets("app", {"grid": {"kick": [0, 8], "snare": [], "enabled": False}}, DECLARED)

	assert asks == [("app", "grid/rows", {"kick": [0, 8], "snare": []}),
	                ("app", "grid/enabled", False)]


def test_a_note_grid_goes_back_whole_with_its_offset_and_nothing_it_works_out () -> None:
	"""Notes with their shapes in the one write, the offset and the mute beside
	it, and the labels the offset implies left for the app to work out again."""

	held = {"C2": {"0": {"length": 6, "velocity": 90}}, "enabled": True, "transpose": 3,
	        "labels": {"C2": "D#2"}, "unreachable": []}

	asks = _tool()._sets("app", {"bass": held}, DECLARED)

	assert asks == [("app", "bass/rows", {"C2": {"0": {"length": 6, "velocity": 90}}}),
	                ("app", "bass/enabled", True),
	                ("app", "bass/transpose", 3)]


def test_a_rack_goes_back_before_anything_that_could_route_from_its_grids () -> None:
	"""The grids a rack made exist only once it has made them, and a stack
	refuses a route to a grid that does not exist."""

	state = {
		"stack": {"layers": [{"id": "one", "kind": "route", "source": "rack-a"}]},
		"rack": {"grids": [{"id": "a", "rows": ["kick"], "steps": 16, "title": None}]},
	}

	asks = _tool()._sets("app", state, DECLARED)

	assert [path for _, path, _ in asks] == ["rack/grids", "stack/layers"]


def test_what_the_manifest_does_not_describe_is_walked_a_value_at_a_time () -> None:
	"""A grid a rack is about to make is in no manifest yet.  Walked a value at a
	time it still comes back exactly, because it starts empty."""

	asks = _tool()._sets("app", {"rack-a": {"snare": [3], "enabled": True}}, DECLARED)

	assert asks == [("app", "rack-a/snare/3", True), ("app", "rack-a/enabled", True)]


def test_a_restore_takes_out_what_the_composition_seeded () -> None:
	"""**The whole of #2465**, through a real grid rather than a list of paths:
	the composition seeded a kick on 8 and a clap on 12, the capture holds
	neither, and after the restore's writes neither is there."""

	composition = types.SimpleNamespace(data={"grid": {"kick": [0, 8], "clap": [12]}})
	grid = adapter.StepGrid(composition, rows=["kick", "clap", "snare"], steps=16,
	                        data_key="grid", name="grid")

	captured = {"grid": {"kick": [0, 4], "clap": [], "snare": [], "enabled": True}}

	for _, path, value in _tool()._sets("app", captured, {"grid": grid.declaration()}):
		grid.apply(path.split("/")[1:], value)

	assert grid.rows_now() == {"kick": [0, 4], "clap": [], "snare": []}


def test_what_a_restore_takes_out_is_said_and_only_for_grids_the_capture_holds () -> None:
	"""Said, so a person knows it happened; and only where the capture speaks for
	the grid — one made since is left alone rather than emptied (#2465)."""

	gone = _tool()._taken_out(
		{"grid": {"kick": [0, 4], "clap": [], "enabled": True}},
		{"grid": {"kick": [0, 8], "clap": [12], "enabled": True}, "made": {"kick": [1]}},
		{"grid": {"type": "step_grid"}, "made": {"type": "step_grid"}})

	assert gone == ["grid/kick/8", "grid/clap/12"]


VARIANTS_DECLARED: dict[str, typing.Any] = {
	"grid": {"type": "step_grid", "variants": ["A", "B", "C"]},
}
"""A grid with variants, as the manifest describes one (#2485)."""


def test_a_grid_with_variants_goes_back_a_variant_at_a_time_and_what_played_as_a_cue () -> None:
	"""Each variant whole; **what played goes back as a cue**, because only the app
	writes which variant plays, and at a build (#2488)."""

	held = {"variants": {"A": {"rows": {"kick": [0]}}, "B": {"rows": {"snare": [4]}},
	                     "C": {"rows": {}}},
	        "playing": "B", "cue": "C", "enabled": True}

	asks = _tool()._sets("app", {"grid": held}, VARIANTS_DECLARED)

	assert asks == [("app", "grid/variants/A/rows", {"kick": [0]}),
	                ("app", "grid/variants/B/rows", {"snare": [4]}),
	                ("app", "grid/variants/C/rows", {}),
	                ("app", "grid/cue", "B"),
	                ("app", "grid/enabled", True)]


def test_a_capture_from_before_a_grid_had_variants_goes_into_its_first () -> None:
	"""The conversion #2485 asks for: bare rows are what the first variant was."""

	asks = _tool()._sets("app", {"grid": {"kick": [0, 8], "snare": [], "enabled": False}},
	                     VARIANTS_DECLARED)

	assert asks == [("app", "grid/variants/A/rows", {"kick": [0, 8], "snare": []}),
	                ("app", "grid/enabled", False)]


def test_a_restore_puts_every_variant_back_exactly_and_cues_what_played () -> None:
	"""**End to end through a real grid with variants**, seeded as the rig's is:
	each variant exactly — the seed in A taken out — and the one that played
	cued, so it lands at the next build rather than mid-bar."""

	composition = types.SimpleNamespace(data={"grid": {"A": {"rows": {"kick": [0, 8], "clap": [12]}}}})
	grid = adapter.StepGrid(composition, rows=["kick", "clap", "snare"], steps=16,
	                        data_key="grid", name="grid", variants=("A", "B", "C"))

	captured = {"grid": {"variants": {"A": {"rows": {"kick": [0, 4]}}, "B": {"rows": {"snare": [2]}},
	                                  "C": {"rows": {}}},
	                     "playing": "B", "enabled": True}}

	for _, path, value in _tool()._sets("app", captured, {"grid": grid.declaration()}):
		grid.apply(path.split("/")[1:], value)

	assert grid.rows_now("A") == {"kick": [0, 4], "clap": [], "snare": []}
	assert grid.rows_now("B")["snare"] == [2]
	assert (grid.playing, grid.cue) == ("A", "B"), "what played went back as a cue"

	grid.now()

	assert grid.playing == "B"


def test_what_a_restore_takes_out_is_said_by_the_variant_it_comes_from () -> None:
	"""At each cell's own address; and a variant the capture holds nothing about is
	left alone, as a grid made since the capture is (#2465)."""

	gone = _tool()._taken_out(
		{"grid": {"variants": {"A": {"rows": {"kick": [0]}}, "B": {"rows": {}}}, "playing": "A"}},
		{"grid": {"variants": {"A": {"rows": {"kick": [0, 8]}}, "B": {"rows": {"snare": [3]}},
		                       "C": {"rows": {"kick": [1]}}}}},
		VARIANTS_DECLARED)

	assert gone == ["grid/variants/A/rows/kick/8", "grid/variants/B/rows/snare/3"]


def test_what_a_note_grid_loses_is_said_by_the_note () -> None:
	"""A note grid's rows are notes keyed by position, not lists of steps."""

	gone = _tool()._taken_out(
		{"bass": {"C2": {"0": {"length": 6, "velocity": 90}}}},
		{"bass": {"C2": {"0": {"length": 6, "velocity": 90}, "12": {"length": 6, "velocity": 90}},
		          "transpose": 0, "labels": {}, "unreachable": []}},
		{"bass": {"type": "note_grid"}})

	assert gone == ["bass/C2/12"]
