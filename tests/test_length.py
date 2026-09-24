"""A pattern playing fewer of its grid's steps, changed while it plays (#2526, design #2548).

A grid whose composition allows it declares ``min_steps``; its ``steps`` stays its
window and the longest it may be.  ``end`` is how many steps play, kept at once and
heard from the pattern's next cycle, and the build asks the grid what to play with
`now`, which hands back only what the cycle plays.  ``resync`` is the performer
asking for the pattern to come back onto the bar.  A grid declaring none of it is
the grid it always was.
"""

import collections.abc
import fractions
import importlib.util
import types
import typing

import pytest

import superconductor.controls as controls
import superconductor.subsequence_adapter as adapter


ROWS = ["kick", "snare", "hat"]
PITCHES = ["E2", "D2", "C2"]


class Link:
	"""A link that writes down what it was told instead of saying it."""

	def __init__ (self, grids: dict[str, typing.Any] | None = None) -> None:
		"""Nothing said, nothing noted, and the controls a stack may look its grid up in."""

		self.controls: dict[str, typing.Any] = dict(grids or {})
		self.reports: list[tuple[str, typing.Any]] = []
		self.events: list[tuple[str, dict[str, typing.Any]]] = []
		self.noted = 0

	def report (self, path: str, value: typing.Any) -> None:
		"""Write down one thing the app did of its own accord."""

		self.reports.append((path, value))

	def happened (self, name: str, **fields: typing.Any) -> None:
		"""Write down one event."""

		self.events.append((name, fields))

	def kept_changed (self) -> None:
		"""Count one change worth keeping."""

		self.noted += 1


class Builder:
	"""The little of a pattern builder `now` reads, and the lengths it is given."""

	def __init__ (self, cycle: int, time_signature: tuple[int, int] = (4, 4),
	              bar_beats: float | None = None) -> None:
		"""A build of this cycle, in this time.

		*bar_beats* is how many quarter notes a bar lasts, which Subsequence's builder
		says from 0.7.0 on: three for 6/8.  Left out, this builder says nothing, as
		0.6.6's did not.
		"""

		self.cycle = cycle
		self.time_signature = time_signature

		if bar_beats is not None:
			self.bar_beats = bar_beats
		self.lengths: list[int] = []
		self.calls: list[tuple[str, dict[str, typing.Any]]] = []

	def hit_steps (self, **arguments: typing.Any) -> None:
		"""Write down a generator's call."""

		self.calls.append(("hit_steps", arguments))

	def sequence (self, **arguments: typing.Any) -> None:
		"""Write down a generator's call."""

		self.calls.append(("sequence", arguments))

	def once (self, **arguments: typing.Any) -> None:
		"""Write down a generator's call."""

		self.calls.append(("once", arguments))


def _resize (pattern: typing.Any, steps: int) -> None:
	"""The composition's resize, which here writes the length down on the builder."""

	pattern.lengths.append(steps)


def _steps (*numbers: int, velocity: int = 100) -> dict[str, typing.Any]:
	"""A row as a step grid holds it."""

	return {str(one): {"velocity": velocity} for one in sorted(numbers)}


def _drums (seed: dict[str, typing.Any] | None = None, end: int | None = None,
            variants: typing.Sequence[str] = ()) -> tuple[adapter.StepGrid, Link]:
	"""A three-voice, sixteen-step grid whose length changes, and a link."""

	composition = types.SimpleNamespace(data={})

	if seed is not None:
		composition.data["grid"] = seed

	grid = adapter.StepGrid(
		composition, rows=ROWS, steps=16, beats=4, data_key="grid", name="grid",
		pattern="drums", variants=variants, min_steps=1, end=end, resize=_resize)
	link = Link({"grid": grid})
	grid.attach(typing.cast(typing.Any, link))

	return grid, link


def _cycles (link: Link) -> list[dict[str, typing.Any]]:
	"""Every cycle event the grid sent, in order."""

	return [fields for name, fields in link.events if name == "cycle"]


# --- a grid declaring no length is unchanged ------------------------------------

def test_a_grid_declaring_no_length_is_the_grid_it_always_was () -> None:
	"""The same declaration, the same state, the same build, and no event."""

	composition = types.SimpleNamespace(data={"grid": {"kick": [0, 12]}})
	grid = adapter.StepGrid(composition, rows=ROWS, steps=16, pattern="drums")
	link = Link()
	grid.attach(typing.cast(typing.Any, link))

	assert "min_steps" not in grid.declaration()
	assert grid.snapshot() == {"kick": _steps(0, 12), "enabled": True}
	assert grid.kept() == {"rows": {"kick": _steps(0, 12)}, "enabled": True}

	builder = Builder(cycle=3)

	assert grid.now(builder) == {"kick": _steps(0, 12)}
	assert builder.lengths == [] and link.events == [], "a length was set on a grid that has none"

	for path in (["end"], ["resync"]):
		with pytest.raises(adapter.Refused):
			grid.apply(path, 12 if path == ["end"] else True)


@pytest.mark.parametrize("given, why", [
	({"min_steps": 0}, "no pattern plays no steps"),
	({"min_steps": 17}, "the window is the longest a pattern may be"),
	({"min_steps": 4, "end": 3}, "an opening below the shortest"),
	({"min_steps": 4, "end": 17}, "an opening past the window"),
	({"min_steps": True}, "a flag is not a count"),
	({"end": 12}, "a length with no bound"),
	({"min_steps": 1, "resize": None}, "a length nothing can make"),
	({"min_steps": 1, "pattern": None}, "a grid driving no pattern has no length of its own"),
	({"min_steps": 1, "rows": ["kick", "end"]}, "a row called what sits beside the rows"),
])
def test_a_length_the_composition_cannot_mean_is_refused_when_the_grid_is_made (
	given: dict[str, typing.Any], why: str,
) -> None:
	"""Loudly, at start, rather than as a control that offers what it cannot do."""

	arguments: dict[str, typing.Any] = {"rows": ROWS, "steps": 16, "pattern": "drums", "resize": _resize}
	arguments.update(given)

	with pytest.raises(ValueError):
		adapter.StepGrid(types.SimpleNamespace(data={}), **arguments)


# --- the declaration, the state and the store -----------------------------------

def test_a_grid_whose_length_changes_declares_its_bounds_and_holds_its_end () -> None:
	"""``steps`` stays the window; ``end`` opens at it unless the composition says."""

	grid, _ = _drums()

	assert grid.declaration()["steps"] == 16
	assert grid.declaration()["min_steps"] == 1
	assert grid.snapshot()["end"] == 16 and grid.snapshot()["resync"] is False

	opened, _ = _drums(end=12)

	assert opened.snapshot()["end"] == 12


def test_an_end_is_kept_at_once_and_refused_outside_its_bounds () -> None:
	"""Kept the moment it is set, as a transposition is, and answered with itself."""

	grid, _ = _drums()

	assert grid.apply(["end"], 12)
	assert grid.snapshot()["end"] == 12
	assert grid.applied(["end"], 12) == 12
	assert not grid.apply(["end"], 12), "setting what is already there changed something"

	for wrong in (0, 17, 12.0, True, "12", None):
		with pytest.raises(adapter.Refused):
			grid.apply(["end"], wrong)


def test_the_store_keeps_the_end_and_never_a_resync () -> None:
	"""How many steps play is something somebody made; a re-sync is a request in flight."""

	grid, _ = _drums(seed={"kick": [0, 14]})

	grid.apply(["end"], 12)
	grid.apply(["resync"], True)

	kept = grid.kept()

	assert kept["end"] == 12
	assert "resync" not in kept
	assert kept["rows"] == {"kick": _steps(0, 14)}, "a step past the end was not kept"

	again, _ = _drums()

	assert again.restore(kept) == []
	assert again.snapshot()["end"] == 12
	assert again.snapshot()["resync"] is False


def test_a_kept_end_outside_the_bounds_is_said_and_the_rest_comes_back () -> None:
	"""A composition can narrow its window between two starts; the rows still come back."""

	grid, _ = _drums()

	refused = grid.restore({"rows": {"kick": _steps(3)}, "enabled": True, "end": 40})

	assert refused and "16" in refused[0]
	assert grid.snapshot()["end"] == 16
	assert grid.snapshot()["kick"] == _steps(3)


# --- what a build plays -----------------------------------------------------------

def test_a_build_hands_over_only_the_steps_before_the_end_and_keeps_the_rest () -> None:
	"""Steps past the end are not played and not touched, so lengthening brings them back."""

	grid, link = _drums(seed={"kick": [0, 11, 12, 15], "snare": [13]})

	grid.apply(["end"], 12)

	builder = Builder(cycle=1)

	assert grid.now(builder) == {"kick": _steps(0, 11)}, "a step past the end was handed to the build"
	assert builder.lengths == [12], "the pattern was not made as long as it plays"
	assert grid.rows_now() == {"kick": _steps(0, 11, 12, 15), "snare": _steps(13)}

	grid.apply(["end"], 16)

	again = Builder(cycle=2)

	assert grid.now(again) == {"kick": _steps(0, 11, 12, 15), "snare": _steps(13)}
	assert again.lengths == [16]
	assert [(one["from"], one["end"]) for one in _cycles(link)] == [(0, 12), (0, 16)]


def test_a_cycle_starts_where_the_ones_before_it_ended () -> None:
	"""Summed from the lengths each build set, including the builds a mute skipped."""

	grid, link = _drums()

	grid.now(Builder(cycle=0))
	grid.apply(["end"], 12)
	grid.now(Builder(cycle=1))
	grid.now(Builder(cycle=2))

	# Cycles 3 and 4 were never built — the pattern was muted — and ran at twelve.
	grid.now(Builder(cycle=5))

	# Cycle 0 is where the page's own beat count draws it, so nothing is said of it.
	assert [one["at"] for one in _cycles(link)] == [4.0, 7.0, 16.0]


def test_a_cycle_is_said_only_while_the_page_would_draw_it_wrongly () -> None:
	"""A pattern at its whole window, on a start the window divides, costs the clock nothing.

	The page's count is exact for every pattern that never changed length, so a frame a
	cycle for each would be a cost on the clock loop that nobody reads.  Once a pattern
	is back where that count puts it, one more is said, so a panel holding the last
	cycle it was told of is corrected, and then nothing again.
	"""

	grid, link = _drums()

	for cycle in range(4):
		grid.now(Builder(cycle=cycle))

	assert _cycles(link) == [], "an unchanged pattern reported its cycles"

	grid.apply(["end"], 8)
	grid.now(Builder(cycle=4))
	grid.now(Builder(cycle=5))

	assert len(_cycles(link)) == 2, "a shortened pattern did not say where each cycle began"

	grid.apply(["end"], 16)
	grid.now(Builder(cycle=6))
	grid.now(Builder(cycle=7))
	grid.now(Builder(cycle=8))

	assert [(one["at"], one["end"]) for one in _cycles(link)][2:] == [(20.0, 16)], \
		"coming back to the bar was said more or less than once"


def test_the_variants_share_one_length () -> None:
	"""The pattern's, like the transposition and the mute (#2548 decision 3)."""

	grid, _ = _drums(seed={"A": {"rows": {"kick": [0, 13]}}, "B": {"rows": {"snare": [2, 14]}}},
	                 variants=("A", "B"))

	grid.apply(["end"], 12)
	grid.apply(["cue"], "B")

	assert grid.now(Builder(cycle=1)) == {"snare": _steps(2)}
	assert grid.snapshot()["end"] == 12 and grid.playing == "B"


# --- re-sync ------------------------------------------------------------------------

def test_a_resync_plays_the_end_of_the_pattern_into_the_next_bar_line () -> None:
	"""Twelve steps for two cycles leaves the pattern two beats off the bar (#2548 decision 4)."""

	grid, link = _drums(seed={"kick": [0, 8], "hat": [12, 15]})

	grid.now(Builder(cycle=0))
	grid.apply(["end"], 12)
	grid.now(Builder(cycle=1))
	grid.now(Builder(cycle=2))
	grid.apply(["end"], 16)
	grid.apply(["resync"], True)

	# Cycle 3 starts on beat 10: eight steps short of the bar line at 12.
	short = Builder(cycle=3)

	assert grid.now(short) == {"kick": _steps(0), "hat": _steps(4, 7)}, \
		"the gap did not play the last eight steps, each in its place"
	assert short.lengths == [8]
	assert grid.snapshot()["resync"] is True, "it said it had landed before the bar line"

	landed = Builder(cycle=4)

	assert grid.now(landed) == {"kick": _steps(0, 8), "hat": _steps(12, 15)}
	assert landed.lengths == [16]
	assert grid.snapshot()["resync"] is False
	assert ("grid/resync", False) in link.reports

	assert [(one["at"], one["from"]) for one in _cycles(link)][-2:] == [(10.0, 8), (12.0, 0)]


def test_the_short_cycle_a_resync_makes_plays_nothing_past_the_end () -> None:
	"""A step kept past a shortened end stays out of the gap too, however the gap wraps."""

	grid, _ = _drums(seed={"kick": [3], "snare": [14]}, end=4)

	grid.now(Builder(cycle=0))
	grid.apply(["end"], 2)
	grid.now(Builder(cycle=1))
	grid.apply(["end"], 12)
	grid.apply(["resync"], True)

	# Cycle 2 starts on beat 1.5: ten steps to the bar, from step 2 of twelve.
	short = Builder(cycle=2)

	assert grid.now(short) == {"kick": _steps(1)}, "a step past the end played in the gap"
	assert short.lengths == [10]

	composition = types.SimpleNamespace(data={})
	notes = adapter.NoteGrid(composition, rows=PITCHES, steps=16, beats=4, divisions=2, data_key="n",
	                         name="n", pattern="n", min_steps=1, end=4, resize=_resize)
	notes.attach(typing.cast(typing.Any, Link()))
	notes.apply(["C2", "6"], True)
	notes.apply(["E2", "28"], True)

	notes.now(Builder(cycle=0))
	notes.apply(["end"], 2)
	notes.now(Builder(cycle=1))
	notes.apply(["end"], 12)
	notes.apply(["resync"], True)

	assert notes.now(Builder(cycle=2)) == {"C2": {"2": {"length": 1, "velocity": 100}}}


def test_a_resync_on_a_pattern_already_on_the_bar_changes_nothing_and_lands () -> None:
	"""Asked of a pattern in step, it is answered at once and nothing moves."""

	grid, link = _drums(seed={"kick": [0]})

	grid.now(Builder(cycle=0))
	grid.apply(["resync"], True)

	builder = Builder(cycle=1)

	assert grid.now(builder) == {"kick": _steps(0)}
	assert builder.lengths == [16]
	assert grid.snapshot()["resync"] is False
	assert link.reports == [("grid/resync", False)]


def test_a_gap_longer_than_the_pattern_plays_it_round_again () -> None:
	"""Four steps and ten to fill: the end of the pattern, wrapping, into the downbeat."""

	grid, _ = _drums(seed={"kick": [0], "hat": [3]}, end=4)

	grid.now(Builder(cycle=0))
	grid.apply(["end"], 2)
	grid.now(Builder(cycle=1))
	grid.apply(["end"], 4)
	grid.apply(["resync"], True)

	# Cycle 2 starts on beat 1.5, ten steps before the bar line at 4.
	short = Builder(cycle=2)

	assert grid.now(short) == {"kick": _steps(2, 6), "hat": _steps(1, 5, 9)}
	assert short.lengths == [10]


def test_a_resync_can_be_taken_back_until_its_short_cycle_is_built () -> None:
	"""After that the sequencer has it queued, and a panel told otherwise would be misled."""

	grid, _ = _drums()

	grid.now(Builder(cycle=0))
	grid.apply(["end"], 12)
	grid.now(Builder(cycle=1))

	assert grid.apply(["resync"], True)
	assert grid.apply(["resync"], False)
	assert grid.apply(["resync"], True)

	grid.now(Builder(cycle=2))

	with pytest.raises(adapter.Refused):
		grid.apply(["resync"], False)

	for wrong in (1, "true", None):
		with pytest.raises(adapter.Refused):
			grid.apply(["resync"], wrong)


def test_a_bar_line_that_falls_between_two_steps_is_said_rather_than_guessed () -> None:
	"""Ten steps to three beats, a bar of four: the gap is three and a third steps."""

	composition = types.SimpleNamespace(data={"odd": {"kick": [0, 9]}})
	grid = adapter.StepGrid(composition, rows=ROWS, steps=10, beats=3, data_key="odd", name="odd",
	                        pattern="odd", min_steps=1, resize=_resize)
	link = Link()
	grid.attach(typing.cast(typing.Any, link))

	grid.now(Builder(cycle=0))
	grid.apply(["resync"], True)

	builder = Builder(cycle=1)

	assert grid.now(builder) == {"kick": _steps(0, 9)}, "a cycle of part of a step was guessed at"
	assert builder.lengths == [10]
	assert grid.snapshot()["resync"] is False
	assert link.reports == [("odd/resync", False)]


def test_a_bar_counts_the_beats_its_time_signature_says () -> None:
	"""A builder that says no ``bar_beats`` is taken at its time signature's word.

	Seven quarter notes to a bar of 7/8, as 0.6.6 counted them: a pattern starting on
	beat four is three beats, twelve steps, short of it.
	"""

	grid, _ = _drums()

	grid.now(Builder(cycle=0))
	grid.apply(["resync"], True)

	builder = Builder(cycle=1, time_signature=(7, 8))
	grid.now(builder)

	assert builder.lengths == [12]


def test_a_bar_is_as_many_quarter_notes_as_the_builder_says () -> None:
	"""Six eighths to a bar are three quarter notes, as Subsequence counts them from 0.7.0.

	A pattern starting on beat eight is one beat, four steps, short of the bar line at
	nine.  Taking the time signature's six as quarter notes would put the line at twelve,
	sixteen steps away (#3562).
	"""

	grid, _ = _drums()

	grid.now(Builder(cycle=0))
	grid.now(Builder(cycle=1))
	grid.apply(["resync"], True)

	builder = Builder(cycle=2, time_signature=(6, 8), bar_beats=3.0)
	grid.now(builder)

	assert builder.lengths == [4]


# --- a length the sequencer refuses ----------------------------------------------------

def _refusing (shortest: int) -> collections.abc.Callable[[typing.Any, int], None]:
	"""A resize that refuses too short a length by raising, as Subsequence does under a lookahead (#2546)."""

	def resize (pattern: typing.Any, steps: int) -> None:
		if steps < shortest:
			raise ValueError(f"{steps} steps is shorter than this pattern's reschedule lookahead")

		pattern.lengths.append(steps)

	return resize


def test_a_refused_length_leaves_the_count_where_the_music_is () -> None:
	"""Refused, the build is silent and the pattern plays on at the length it had, so nothing is kept.

	**Kept, two refused cycles of two steps put the count twenty-eight steps behind the
	music**: the page drew the pattern off the bar, and a re-sync asked of a pattern on
	it made a short cycle and took it off (`test_length_sequencer.py`, #2546).
	"""

	grid, link = _drums(seed={"kick": [0]})
	grid.resize = _refusing(4)

	grid.now(Builder(cycle=0))
	grid.apply(["end"], 2)

	for cycle in (1, 2):
		with pytest.raises(ValueError):
			grid.now(Builder(cycle=cycle))

	grid.apply(["end"], 16)
	grid.now(Builder(cycle=3))
	grid.apply(["resync"], True)

	on_the_bar = Builder(cycle=4)

	assert grid.now(on_the_bar) == {"kick": _steps(0)}
	assert on_the_bar.lengths == [16], "a re-sync asked on the bar made a short cycle"
	assert grid.snapshot()["resync"] is False
	assert _cycles(link) == [], "the page was told the pattern had left the bar"


def test_a_resync_whose_short_cycle_is_refused_can_still_be_taken_back () -> None:
	"""Nothing was queued, so a panel is not told it is already coming back onto the bar."""

	grid, _ = _drums()
	grid.resize = _refusing(4)

	grid.now(Builder(cycle=0))
	grid.apply(["end"], 14)
	grid.now(Builder(cycle=1))
	grid.apply(["resync"], True)

	# Cycle 2 starts on beat 7.5: two steps to the bar, which is too short to take.
	with pytest.raises(ValueError):
		grid.now(Builder(cycle=2))

	assert grid.apply(["resync"], False), "a short cycle that never played could not be taken back"


# --- a note grid ----------------------------------------------------------------------

def test_a_note_past_the_end_is_cut_where_it_plays_and_kept_whole () -> None:
	"""The step grid's rule in positions: cut, never shortened."""

	composition = types.SimpleNamespace(data={})
	grid = adapter.NoteGrid(
		composition, rows=PITCHES, steps=16, beats=4, divisions=6, data_key="bass", name="bass",
		pattern="bass", min_steps=1, resize=_resize)
	link = Link()
	grid.attach(typing.cast(typing.Any, link))

	grid.apply(["E2", "0"], True)
	grid.apply(["E2", "0", "length"], 6)
	grid.apply(["D2", "66"], True)
	grid.apply(["D2", "66", "length"], 12)
	grid.apply(["C2", "72"], True)
	grid.apply(["end"], 12)

	builder = Builder(cycle=1)

	assert grid.now(builder) == {
		"E2": {"0": {"length": 6, "velocity": 100}},
		"D2": {"66": {"length": 6, "velocity": 100}},
	}
	assert builder.lengths == [12]
	assert grid.rows_now()["D2"]["66"]["length"] == 12, "the kept note was shortened"
	assert "72" in grid.rows_now()["C2"], "a note past the end was not kept"
	assert grid.declaration()["max_length"] == 96, "a note's room is still the window"


# --- the stack ------------------------------------------------------------------------

CATALOGUE: list[dict[str, typing.Any]] = [
	{"name": "hit_steps", "parameters": [
		{"name": "pitch", "kind": "pitch", "required": True},
		{"name": "steps", "kind": "position", "unit": "steps", "multiple": True, "required": True}]},
	{"name": "sequence", "parameters": [
		{"name": "steps", "kind": "position", "unit": "steps", "multiple": True, "required": True},
		{"name": "pitches", "kind": "pitch", "multiple": True, "required": True}]},
	{"name": "once", "parameters": [
		{"name": "pitch", "kind": "pitch", "required": True},
		{"name": "at", "kind": "position", "unit": "steps", "required": True}]},
]

PLACES = {"steps": [(at, str(at + 1)) for at in range(16)]}


def _stacked (layers: list[dict[str, typing.Any]]) -> tuple[adapter.StepGrid, adapter.Recipe, Link]:
	"""A grid whose length changes, and a stack building onto its pattern."""

	grid, link = _drums()
	recipe = adapter.Recipe(types.SimpleNamespace(data={}), catalogue=CATALOGUE, pitches=ROWS,
	                        positions=PLACES, builds="grid")
	recipe.attach(typing.cast(typing.Any, link))
	recipe.apply(["layers"], layers)

	return grid, recipe, link


def test_a_generator_s_places_past_the_end_are_kept_on_the_layer_and_not_placed () -> None:
	"""A place a generator was given moves as a tapped step does (#2548)."""

	grid, recipe, _ = _stacked([
		{"id": "a", "generator": "hit_steps", "params": {"pitch": "kick", "steps": [0, 4, 8, 12]}}])

	grid.apply(["end"], 10)

	builder = Builder(cycle=1)
	grid.now(builder)
	recipe.build(builder)

	assert builder.calls == [("hit_steps", {"pitch": "kick", "steps": [0, 4, 8]})]
	assert recipe.layers()[0]["params"]["steps"] == [0, 4, 8, 12], "the layer lost a place"


def test_what_goes_with_each_place_goes_with_it () -> None:
	"""``sequence`` pairs its pitches with its steps one to one, so a dropped step takes its pitch."""

	grid, recipe, _ = _stacked([
		{"id": "a", "generator": "sequence",
		 "params": {"steps": [0, 12, 4], "pitches": ["kick", "snare", "hat"]}}])

	grid.apply(["end"], 8)

	builder = Builder(cycle=1)
	grid.now(builder)
	recipe.build(builder)

	assert builder.calls == [("sequence", {"steps": [0, 4], "pitches": ["kick", "hat"]})]


def test_a_layer_given_one_place_this_cycle_does_not_play_places_nothing () -> None:
	"""It cannot be called with none, and is not failing: it is kept, as a step is."""

	grid, recipe, link = _stacked([
		{"id": "a", "generator": "once", "params": {"pitch": "kick", "at": 14}}])

	grid.apply(["end"], 12)

	builder = Builder(cycle=1)
	grid.now(builder)
	recipe.build(builder)

	assert builder.calls == []
	assert not [fields for name, fields in link.events if name == "stalled"], \
		"a layer resting past the end was reported as failing"


def test_a_stack_on_a_pattern_playing_its_window_is_left_exactly_alone () -> None:
	"""No moves where the length is the window, and none from a build that asked nothing."""

	grid, recipe, _ = _stacked([
		{"id": "a", "generator": "hit_steps", "params": {"pitch": "kick", "steps": [0, 15]}}])

	whole = Builder(cycle=1)
	grid.now(whole)
	recipe.build(whole)

	grid.apply(["end"], 12)

	unasked = Builder(cycle=2)
	recipe.build(unasked)

	assert [call[1]["steps"] for call in whole.calls + unasked.calls] == [[0, 15], [0, 15]]


def test_the_moves_count_beats_as_well_as_steps () -> None:
	"""A place counted in beats moves by the same amount as one counted in steps."""

	moves = adapter._Moves(first=12, played=8, end=16, step=fractions.Fraction(1, 4))
	offered = {"beats": adapter.Parameter("beats", "choices", role="position", unit="beats")}

	assert moves.arguments(offered, {"beats": [3.0, 3.75, 0.0, 1.25]}) == {"beats": [0.0, 0.75, 1.0]}


# --- the service, and both halves together ------------------------------------------

def _agree (grid: typing.Any, rest: list[str], value: typing.Any) -> None:
	"""Apply on the app, carry what it answers to the service, and compare the two copies."""

	declared = {grid.name: grid.declaration()}
	held = {grid.name: grid.snapshot()}

	grid.apply(rest, value)
	controls.apply_change(held, declared, "/".join([grid.name, *rest]), grid.applied(rest, value))

	assert held[grid.name] == grid.snapshot()


@pytest.mark.parametrize("rest, value", [(["end"], 9), (["resync"], True)])
def test_a_length_and_a_resync_cross_the_join_as_the_app_holds_them (rest: list[str], value: typing.Any) -> None:
	"""On a step grid, a note grid, and a grid with variants."""

	grid, _ = _drums(seed={"kick": [0, 12]})
	_agree(grid, rest, value)

	varied, _ = _drums(seed={"A": {"rows": {"kick": [1]}}}, variants=("A", "B"))
	_agree(varied, rest, value)

	notes = adapter.NoteGrid(types.SimpleNamespace(data={}), rows=PITCHES, steps=16, name="bass",
	                         data_key="bass", pattern="bass", min_steps=4, resize=_resize)
	_agree(notes, rest, value)


def test_the_app_clearing_a_resync_reaches_the_service () -> None:
	"""What the app reports at the bar line is kept, so a panel arriving then is not told to blink."""

	grid, link = _drums()
	declared = {"grid": grid.declaration()}
	held = {"grid": grid.snapshot()}

	grid.now(Builder(cycle=0))
	grid.apply(["resync"], True)
	controls.apply_change(held, declared, "grid/resync", True)
	grid.now(Builder(cycle=1))

	for path, value in link.reports:
		controls.apply_change(held, declared, path, value)

	assert held["grid"] == grid.snapshot()
	assert held["grid"]["resync"] is False


@pytest.mark.parametrize("path, value", [
	("grid/end", 0), ("grid/end", 17), ("grid/end", "12"), ("grid/end", True), ("grid/resync", 1)])
def test_the_service_refuses_a_length_the_grid_could_not_have_reported (path: str, value: typing.Any) -> None:
	"""A copy outside the declared bounds could not have come from the app."""

	grid, _ = _drums()
	held = {"grid": grid.snapshot()}

	with pytest.raises(controls.ControlError):
		controls.apply_change(held, {"grid": grid.declaration()}, path, value)


def test_the_service_refuses_a_length_on_a_grid_that_declared_none () -> None:
	"""As a transposition is refused on a grid that declared no range."""

	grid = adapter.StepGrid(types.SimpleNamespace(data={}), rows=ROWS, steps=16, name="grid")

	with pytest.raises(controls.ControlError):
		controls.apply_change({"grid": grid.snapshot()}, {"grid": grid.declaration()}, "grid/end", 12)


# --- a capture put back ---------------------------------------------------------------

def _restore_tool () -> typing.Any:
	"""The restore tool, imported as a module, as its own tests import it."""

	spec = importlib.util.spec_from_file_location("restore_state", "tools/restore_state.py")
	assert spec is not None and spec.loader is not None

	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)

	return module


def test_a_restore_puts_the_length_back_and_never_a_resync () -> None:
	"""Replaying a re-sync would move a pattern nobody at the panel asked to move."""

	restore_state = _restore_tool()
	grid, _ = _drums(seed={"kick": [0]})
	grid.apply(["end"], 12)
	grid.apply(["resync"], True)

	varied, _ = _drums(seed={"A": {"rows": {"kick": [1]}}}, variants=("A", "B"))
	varied.apply(["end"], 5)
	varied.apply(["resync"], True)

	asks = restore_state._sets(
		"app", {"grid": grid.snapshot(), "varied": varied.snapshot()},
		{"grid": grid.declaration(), "varied": varied.declaration()})

	assert ("app", "grid/end", 12) in asks
	assert ("app", "varied/end", 5) in asks
	assert not [path for _, path, _ in asks if path.endswith("/resync")]
	assert ("app", "grid/rows", {"kick": _steps(0)}) in asks, "end or resync was sent as a row"
