"""Versions of a pattern's notes, switched between while it plays (#2485, #2488).

A grid that declares variants keeps a set of rows for each and plays one.  A
panel edits any of them and asks for one to play next with `cue`; the play
function asks the grid what to play with `now`, which is the one moment a cue may
land, and the grid says so.  A grid declaring none is the grid it always was.
"""

import pathlib
import types
import typing

import pytest

import superconductor.controls as controls
import superconductor.subsequence_adapter as adapter


ROWS = ["kick", "snare", "hat"]
PITCHES = ["E2", "D2", "C2"]
LETTERS = ("A", "B", "C", "D")


class Link:
	"""A link that writes down what it was told instead of saying it."""

	def __init__ (self) -> None:
		"""Nothing said, nothing noted."""

		self.reports: list[tuple[str, typing.Any]] = []
		self.noted = 0

	def report (self, path: str, value: typing.Any) -> None:
		"""Write down one thing the app did of its own accord."""

		self.reports.append((path, value))

	def kept_changed (self) -> None:
		"""Count one change worth keeping."""

		self.noted += 1


def _drums (seed: dict[str, list[int]] | None = None, lands_every: int = 1,
            variants: typing.Sequence[str] = LETTERS) -> tuple[adapter.StepGrid, Link]:
	"""A three-voice step grid with four variants, the first seeded, and a link."""

	composition = types.SimpleNamespace(data={})

	if seed is not None:
		composition.data["grid"] = {"A": {"rows": seed}}

	grid = adapter.StepGrid(composition, rows=ROWS, steps=16, data_key="grid", name="grid",
	                        pattern="drums", variants=variants, lands_every=lands_every)
	link = Link()
	grid.attach(typing.cast(typing.Any, link))

	return grid, link


def _bass (voices: int | None = None) -> tuple[adapter.NoteGrid, Link]:
	"""A three-pitch note grid with four variants, and a link."""

	composition = types.SimpleNamespace(data={})
	grid = adapter.NoteGrid(composition, rows=PITCHES, steps=16, data_key="bass", name="bass",
	                        voices=voices, variants=LETTERS,
	                        relabel=lambda row, semitones: row)
	link = Link()
	grid.attach(typing.cast(typing.Any, link))

	return grid, link


class Builder:
	"""The one thing `now` reads off a pattern builder."""

	def __init__ (self, cycle: int) -> None:
		"""A build of this cycle."""

		self.cycle = cycle


# --- a grid without variants is unchanged ------------------------------------

def test_a_grid_declaring_no_variants_is_the_grid_it_always_was () -> None:
	"""The same declaration, the same state, the same paths (#2485 Q6)."""

	composition = types.SimpleNamespace(data={"grid": {"kick": [0]}})
	grid = adapter.StepGrid(composition, rows=ROWS, steps=16)

	assert "variants" not in grid.declaration()
	assert "lands_every" not in grid.declaration()
	assert grid.snapshot() == {"kick": [0], "snare": [], "hat": [], "enabled": True}

	assert grid.apply(["snare", "4"], True)
	assert grid.now() == {"kick": [0], "snare": [4]}

	with pytest.raises(adapter.Refused):
		grid.apply(["cue"], "B")


# --- the address of a cell ----------------------------------------------------

def test_variants_are_declared_with_how_often_a_cue_may_land () -> None:
	"""The composition's to declare; A–D is what this rig says (#2485 Q6)."""

	grid, _ = _drums(lands_every=2)

	assert grid.declaration()["variants"] == ["A", "B", "C", "D"]
	assert grid.declaration()["lands_every"] == 2


def test_a_cell_lands_in_the_variant_its_path_names_and_nowhere_else () -> None:
	"""Editing B while A plays is the whole of Q1."""

	grid, _ = _drums(seed={"kick": [0]})

	assert grid.apply(["variants", "B", "rows", "snare", "4"], True)

	assert grid.rows_now("B")["snare"] == [4]
	assert grid.rows_now("A") == {"kick": [0], "snare": [], "hat": []}


def test_the_old_spelling_is_refused_on_a_grid_with_variants () -> None:
	"""**One address per cell.**  `grid/kick/3` read as "the one playing" would be
	a second spelling of a cell, and two spellings is how two ends disagree."""

	grid, _ = _drums()

	for rest in (["kick", "3"], ["rows"], ["variants", "A", "kick", "3"], ["variants", "Z", "rows"]):
		with pytest.raises(adapter.Refused):
			grid.apply(rest, True if len(rest) != 2 else {})

	with pytest.raises(adapter.Refused, match="ask for one with cue"):
		grid.apply(["playing"], "B")


def test_a_whole_variant_is_written_at_once_and_only_that_one () -> None:
	"""Clear works on the variant shown, and *start from A* is a copy of A's rows
	written into another — both one write, both leaving the rest alone."""

	grid, _ = _drums(seed={"kick": [0, 8]})

	assert grid.apply(["variants", "B", "rows"], grid.rows_now("A"))
	assert grid.rows_now("B")["kick"] == [0, 8]

	assert grid.apply(["variants", "A", "rows"], {})
	assert grid.rows_now("A")["kick"] == []
	assert grid.rows_now("B")["kick"] == [0, 8], "clearing A emptied B"

	assert grid.applied(["variants", "B", "rows"], {"kick": [8, 0, 8]}) == grid.rows_now("B")


# --- what plays, and when it changes ------------------------------------------

def test_editing_one_variant_while_another_plays_changes_nothing_heard () -> None:
	"""What a build is handed is the variant playing, whatever is being edited."""

	grid, _ = _drums(seed={"kick": [0]})

	grid.apply(["variants", "B", "rows", "snare", "4"], True)

	assert grid.now(Builder(3)) == {"kick": [0]}


def test_a_cue_lands_at_the_next_build_and_the_app_says_so () -> None:
	"""**The panel's blinking stops when the app says, not when a panel guesses**,
	so the switch is reported from the build — and noted for the store, which
	would otherwise go on saying the old one plays."""

	grid, link = _drums(seed={"kick": [0]})
	grid.apply(["variants", "B", "rows", "snare", "4"], True)

	assert grid.apply(["cue"], "B")
	assert grid.cue == "B" and grid.playing == "A", "nothing lands before a build"

	played = grid.now(Builder(7))

	assert played["snare"] == [4]
	assert (grid.playing, grid.cue) == ("B", None)
	assert link.reports == [("grid/playing", "B"), ("grid/cue", None)]
	assert link.noted == 1


def test_a_cue_waits_for_a_cycle_it_may_land_on () -> None:
	"""`lands_every: 2` is a two-bar phrase over a one-bar pattern (#2485 Q3)."""

	grid, link = _drums(lands_every=2)
	grid.apply(["cue"], "C")

	grid.now(Builder(3))

	assert grid.playing == "A", "landed on an odd cycle"
	assert link.reports == []

	grid.now(Builder(4))

	assert grid.playing == "C"


def test_cueing_the_one_playing_takes_a_cue_back_and_another_replaces_it () -> None:
	"""Pressing the lit ▶ means *stay here*; pressing a third replaces the second."""

	grid, _ = _drums()

	grid.apply(["cue"], "B")
	grid.apply(["cue"], "C")

	assert grid.cue == "C"

	assert grid.apply(["cue"], "A")
	assert grid.cue is None
	assert grid.applied(["cue"], "A") is None, "the panel is told the cue went, not that A was cued"

	assert not grid.apply(["cue"], None), "taking back nothing changes nothing"


def test_an_unknown_variant_is_refused_by_name () -> None:
	"""Refused rather than dropped, so the ▶ that sent it springs back with a reason."""

	grid, _ = _drums()

	with pytest.raises(adapter.Refused, match="no variant called 'E'"):
		grid.apply(["cue"], "E")


def test_a_grid_seeded_with_plain_rows_is_refused_when_it_declares_variants () -> None:
	"""The rows would sit beside the variants as though they were one, and a
	person would find their seed nowhere on the glass — so it is refused where it
	is written, at import, with the one line that would do."""

	composition = types.SimpleNamespace(data={"grid": {"kick": [0, 8]}})

	with pytest.raises(ValueError, match="seed a variant instead"):
		adapter.StepGrid(composition, rows=ROWS, variants=LETTERS)


# --- what a panel is told ------------------------------------------------------

def test_the_state_of_a_variant_grid_is_every_variant_which_plays_and_which_is_cued () -> None:
	"""The shape #2485 gives the wire, with the mute beside it as ever."""

	grid, _ = _drums(seed={"kick": [0]})
	grid.apply(["cue"], "B")

	held = grid.snapshot()

	assert set(held) == {"variants", "playing", "cue", "enabled"}
	assert list(held["variants"]) == list(LETTERS)
	assert held["variants"]["A"] == {"rows": {"kick": [0], "snare": [], "hat": []}}
	assert (held["playing"], held["cue"], held["enabled"]) == ("A", "B", True)


# --- what is kept across a restart --------------------------------------------

def test_every_variant_and_which_one_plays_is_kept_and_put_back () -> None:
	"""The pattern store's round trip (#2487), with the cue left out — a request in
	flight is not something anybody made."""

	grid, _ = _drums(seed={"kick": [0]})
	grid.apply(["variants", "C", "rows", "hat", "2"], True)
	grid.apply(["cue"], "C")
	grid.now()
	grid.apply(["cue"], "B")

	kept = grid.kept()

	assert "cue" not in kept
	assert kept["playing"] == "C"

	again, _ = _drums(seed={"kick": [5]})

	assert again.restore(kept) == []
	assert again.kept() == kept
	assert again.cue is None


def test_rows_kept_before_a_grid_had_variants_become_its_first () -> None:
	"""The conversion #2485 asks for: a store written before this grid had
	variants holds bare rows, and they are what A was."""

	grid, _ = _drums(seed={"kick": [5]})

	# B playing, so "the first" and "the one playing" are not the same answer.
	grid.apply(["cue"], "B")
	grid.now()

	assert grid.restore({"rows": {"kick": [0, 4]}, "enabled": True}) == []
	assert grid.rows_now("A")["kick"] == [0, 4]
	assert grid.rows_now("B")["kick"] == [], "the old rows went to whichever was playing"


def test_a_kept_variant_the_composition_no_longer_declares_is_said () -> None:
	"""Said rather than dropped: the store as it was is kept aside by whoever asked."""

	grid, _ = _drums(variants=("A", "B"))

	refused = grid.restore({"variants": {"A": {"rows": {"kick": [1]}}, "E": {"rows": {}}},
	                        "playing": "E", "enabled": True})

	assert any("no variant called E any more" in one for one in refused)
	assert any("to play any more" in one for one in refused)
	assert grid.rows_now("A")["kick"] == [1], "the rest came back"
	assert grid.playing == "A"


def test_variants_kept_for_a_grid_that_no_longer_has_them_put_back_the_one_playing () -> None:
	"""The one that was sounding is what the grid was, to anybody listening."""

	composition = types.SimpleNamespace(data={})
	grid = adapter.StepGrid(composition, rows=ROWS, steps=16)

	refused = grid.restore({"variants": {"A": {"rows": {"kick": [1]}}, "B": {"rows": {"kick": [9]}}},
	                        "playing": "B", "enabled": True})

	assert grid.rows_now()["kick"] == [9]
	assert refused == ["grid has no variants any more, so A was not put back"]


def test_the_store_keeps_the_variant_a_build_landed (
	tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
	"""Through a real link: a cue landing at the build is a change the store has
	to hear about, or it would put the old variant back after a restart."""

	monkeypatch.setattr(adapter.AppLink, "_run_link", lambda self: None)

	composition = types.SimpleNamespace(data={}, on_event=lambda name, callback: None)
	grid = adapter.StepGrid(composition, rows=ROWS, steps=16, variants=LETTERS)
	link = adapter.AppLink(composition, controls=[grid],
	                       pattern_store=adapter.PatternStore(tmp_path / "piece.patterns.json"),
	                       url="ws://127.0.0.1:1/ws/app")
	link.start()

	link._apply("grid/cue", "B", "panel-1", 1)
	link._keep_now()
	grid.now()
	link._keep_now()

	again = adapter.StepGrid(types.SimpleNamespace(data={}), rows=ROWS, steps=16, variants=LETTERS)
	kept = adapter.PatternStore(tmp_path / "piece.patterns.json").load()

	assert kept is not None
	assert again.restore(kept["grid"]) == []
	assert again.playing == "B"


# --- a note grid --------------------------------------------------------------

def test_a_note_placed_in_one_variant_leaves_the_others_alone () -> None:
	"""The same address, one level further down, and a note's shape with it."""

	grid, _ = _bass()

	assert grid.apply(["variants", "B", "rows", "C2", "4"], True)
	assert grid.apply(["variants", "B", "rows", "C2", "4", "length"], 3)

	assert grid.rows_now("B") == {"C2": {"4": {"length": 3, "velocity": 100}}}
	assert grid.rows_now("A") == {}


def test_the_voice_count_is_kept_within_the_variant_being_edited () -> None:
	"""**And said at that variant's address**, which is not the playing one — a
	note taken away from B reported as a cell of A would go dark on the wrong
	tab."""

	grid, link = _bass(voices=1)

	grid.apply(["variants", "A", "rows", "D2", "4"], True)
	grid.apply(["variants", "B", "rows", "D2", "4"], True)
	grid.apply(["variants", "B", "rows", "C2", "4"], True)

	assert grid.rows_now("B") == {"C2": {"4": {"length": 1, "velocity": 100}}}
	assert "D2" in grid.rows_now("A"), "a note in another variant was taken away"
	assert link.reports == [("bass/variants/B/rows/D2/4", False)]


def test_transposition_and_the_mute_stay_the_pattern_s_whichever_variant_plays () -> None:
	"""Switching variant should not change the key you are in (#2485 Q4)."""

	grid, _ = _bass()

	grid.apply(["transpose"], 3)
	grid.apply(["cue"], "B")
	grid.now()

	assert grid.transpose == 3
	assert grid.snapshot()["transpose"] == 3
	assert grid.kept()["transpose"] == 3


# --- the service keeps what the app holds -------------------------------------

def _mirrored (grid: typing.Any) -> tuple[dict[str, typing.Any], dict[str, typing.Any]]:
	"""The service's copy of a grid, starting where a real one does."""

	return {grid.name: grid.declaration()}, {grid.name: grid.snapshot()}


def test_the_service_keeps_each_variant_where_the_app_does () -> None:
	"""`tests/test_seam.py`'s one assertion, for every path a variant grid has."""

	grid, _ = _drums(seed={"kick": [0]})
	declared, held = _mirrored(grid)

	for rest, value in ((["variants", "B", "rows", "snare", "4"], True),
	                    (["variants", "B", "rows", "snare", "4"], False),
	                    (["variants", "C", "rows"], {"hat": [2, 2, 1]}),
	                    (["cue"], "D"),
	                    (["enabled"], False)):
		grid.apply(rest, value)
		controls.apply_change(held, declared, "/".join(["grid", *rest]), grid.applied(rest, value))

	grid.now()

	# What the app reports of its own accord when a cue lands at the build.
	for path, said in (("grid/playing", grid.playing), ("grid/cue", grid.cue)):
		controls.apply_change(held, declared, path, said)

	assert held["grid"] == grid.snapshot()


def test_the_service_keeps_a_variant_note_grid_where_the_app_does () -> None:
	"""The same for notes, their shapes, and the offset that stays the pattern's."""

	grid, _ = _bass()
	declared, held = _mirrored(grid)

	for rest, value in ((["variants", "B", "rows", "C2", "4"], True),
	                    (["variants", "B", "rows", "C2", "4", "velocity"], 60),
	                    (["variants", "A", "rows"], {"D2": {"0": {"length": 2}}}),
	                    (["transpose"], 2)):
		grid.apply(rest, value)
		controls.apply_change(held, declared, "/".join(["bass", *rest]), grid.applied(rest, value))

	held["bass"]["labels"], held["bass"]["unreachable"] = grid.snapshot()["labels"], []

	assert held["bass"] == grid.snapshot()


def test_the_service_refuses_the_old_spelling_on_a_grid_with_variants_too () -> None:
	"""Both ends, the same way — a disagreement here would be a cell one of them
	kept and the other never saw."""

	grid, _ = _drums()
	declared, held = _mirrored(grid)

	for path, value in (("grid/kick/3", True), ("grid/rows", {}), ("grid/variants/E/rows", {}),
	                    ("grid/cue", "E")):
		with pytest.raises(controls.ControlError):
			controls.apply_change(held, declared, path, value)
