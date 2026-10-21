"""The demo example: what the panel can do, through a composition that uses it.

Importing `examples/demo.py` is safe: a Subsequence composition resolves its MIDI
port only when it plays, and the link dials the service only when it is started,
which only ``__main__`` does.  So every test here reads the example as it is
declared, and plays its patterns onto Subsequence's own builder.

**Run by CI against the Subsequence release named in its workflow**, as every
test here that imports `subsequence` is.
"""

import importlib.util
import inspect
import logging
import pathlib
import random
import re
import sys
import typing

import pytest

import subsequence.pattern
import subsequence.pattern_builder

import superconductor.service
import superconductor.subsequence_adapter


WHERE = pathlib.Path(__file__).parent.parent / "examples" / "demo.py"


def _composition () -> typing.Any:
	"""The example, imported once and shared."""

	if "demo" not in sys.modules:
		spec = importlib.util.spec_from_file_location("demo", str(WHERE))
		assert spec is not None and spec.loader is not None
		module = importlib.util.module_from_spec(spec)
		sys.modules["demo"] = module
		spec.loader.exec_module(module)

	return sys.modules["demo"]


@pytest.fixture (scope="module")
def rig () -> typing.Any:
	"""The example, loaded but not playing."""

	return _composition()


def _built (rig: typing.Any, play: typing.Any, steps: int) -> list[typing.Any]:
	"""Run one play function onto a real pattern on the kit, and hand back what landed."""

	pattern = subsequence.pattern.Pattern(
		channel=rig.DRUM_CHANNEL, length=steps * rig.STEP_DURATION)

	builder = subsequence.pattern_builder.PatternBuilder(
		pattern=pattern, cycle=0, rng=random.Random(1), drum_note_map=rig.DRUM_NOTES)

	play(builder)

	return list(builder.placed())


# --- The instruments -----------------------------------------------------------

def test_the_kit_plays_general_midi_s_notes_on_its_drum_channel (rig: typing.Any) -> None:
	"""A neutral kit: General MIDI's names and notes on channel 10."""

	assert rig.DRUM_CHANNEL == 10
	assert rig.DRUM_NOTES["kick"] == 36 and rig.DRUM_NOTES["snare"] == 38
	assert rig.drum_grid.declaration()["rows"] == list(rig.DRUM_NOTES)


def test_the_bass_is_a_monosynth_and_the_poly_plays_chords (rig: typing.Any) -> None:
	"""The bass's grid refuses a second note at once, and the poly's lets four sound."""

	assert rig.link.controls["bass"].declaration()["voices"] == 1
	assert rig.link.controls["poly"].declaration()["voices"] == rig.POLY_VOICES == 4


def test_a_poly_note_is_placed_in_steps_rather_than_in_sub_steps (rig: typing.Any) -> None:
	"""The bass divides a step six ways, and the poly does not: a chord wants to land
	on a step.  Asserted because `default_length` is counted in the grid's own
	places, so the two numbers mean the same thing only while divisions is 1."""

	declared = rig.link.controls["poly"].declaration()

	assert declared["divisions"] == 1
	assert declared["default_length"] == rig.POLY_LENGTH == 2
	assert rig.link.controls["bass"].declaration()["divisions"] == 6


# --- Settings ------------------------------------------------------------------

def test_a_setting_opening_at_true_or_false_is_a_switch_and_the_rest_are_numbers (
	rig: typing.Any) -> None:
	"""The demo's two shapes of setting, told apart by what each opens at."""

	fields = {one["name"]: one for one in rig.link.controls["bass_settings"].declaration()["fields"]}

	assert fields["glide"]["kind"] == "switch" and fields["glide"]["default"] is False
	assert fields["glide_time"]["kind"] == "number"
	assert (fields["glide_time"]["min"], fields["glide_time"]["max"]) == (0, 127)


def test_the_poly_s_settings_are_in_sections_and_the_bass_s_are_not (rig: typing.Any) -> None:
	"""A section is a heading above its settings, and a short list reads without one."""

	poly = rig.link.controls["poly_settings"].declaration()["fields"]
	bass = rig.link.controls["bass_settings"].declaration()["fields"]

	assert [one.get("group") for one in poly] == [
		"Filter", "Filter", "Envelope", "Envelope", "Effects", "Effects"]
	assert all(one.get("group") is None for one in bass)


def test_a_switch_is_sent_as_127_or_0_on_its_instrument_s_channel (
	rig: typing.Any, monkeypatch: pytest.MonkeyPatch) -> None:
	"""A setting is a control change on its instrument's channel, at the next pulse."""

	sent: list[tuple[int, int, dict[str, typing.Any]]] = []

	class Played:
		"""A builder that keeps the control changes it is asked for."""

		def __init__ (self, asked: dict[str, typing.Any]) -> None:
			self.asked = asked

		def cc (self, control: int, amount: int) -> None:
			sent.append((control, amount, self.asked))

	def kept (play: typing.Any, **asked: typing.Any) -> None:
		play(Played(asked))

	monkeypatch.setattr(rig.composition, "trigger", kept)

	send = rig._sender(rig.BASS_CHANNEL, rig.BASS_SETTINGS)
	send("glide", True)
	send("glide", False)
	send("cutoff", 90)

	asked = {"channel": rig.BASS_CHANNEL, "beats": 1 / 24, "quantize": 0}

	assert sent == [(65, 127, asked), (65, 0, asked), (74, 90, asked)]


# --- Transposition -------------------------------------------------------------

def test_the_label_and_the_player_agree_about_what_can_sound (rig: typing.Any) -> None:
	"""**One function decides, so they cannot differ**: a row the label calls
	unreachable and the player sounds anyway would be the glass and the ears
	disagreeing."""

	named = rig._relabel(rig.BASS_NOTE_MAP)

	for semitones in (-24, -7, 0, 5, 24):
		for row in rig.BASS_RANGE:
			sounds = rig._sounding(row, semitones, rig.BASS_NOTE_MAP)

			assert (named(row, semitones) is None) == (sounds is None), (
				f"{row} at {semitones}: the label and the player disagree")


def test_a_row_moved_past_the_top_of_midi_is_marked_rather_than_played (rig: typing.Any) -> None:
	"""A transposition that takes a row past note 127 leaves it nothing to play, and
	its label says so rather than the row going quietly silent."""

	named = rig._relabel(rig.POLY_NOTE_MAP)
	top = rig.POLY_RANGE[-1]

	assert rig.POLY_NOTE_MAP[top] == 72
	assert named(top, 24) == "C7"
	assert named(top, 56) is None
	assert rig._sounding(top, 56, rig.POLY_NOTE_MAP) is None


def test_both_synths_offer_a_transposition_and_the_kit_does_not (rig: typing.Any) -> None:
	"""Transposing a drum map is a different drum, not the same one higher."""

	for name in ("bass", "poly"):
		assert "transpose_range" in rig.link.controls[name].declaration()

	assert "transpose_range" not in rig.link.controls["drums"].declaration()


def _pitched (rig: typing.Any, play: typing.Any, note_map: dict[str, int]) -> list[typing.Any]:
	"""Run a synth pattern's play function onto a real builder and hand back what landed."""

	pattern = subsequence.pattern.Pattern(
		channel=rig.BASS_CHANNEL, length=rig.STEPS * rig.STEP_DURATION)

	builder = subsequence.pattern_builder.PatternBuilder(
		pattern=pattern, cycle=0, rng=random.Random(1), drum_note_map=note_map)

	play(builder)

	return list(builder.placed())


def test_a_generated_note_moves_with_the_pattern_s_transposition (
	rig: typing.Any, monkeypatch: pytest.MonkeyPatch) -> None:
	"""Transposing a pattern moves the notes its generators place as well as the ones
	tapped in, and a generated note is still reported on the row it was placed on,
	whose label then names what it sounds."""

	# A stack is handed its link when the link starts, which nothing here does, so
	# it is handed one for the length of the test, with the send caught.
	reported: list[dict[str, typing.Any]] = []
	monkeypatch.setattr(rig.bass_recipe, "link", rig.link)
	monkeypatch.setattr(rig.link, "happened", lambda name, **fields: reported.append(
		{"name": name, **fields}))

	playing = rig.bass_grid.playing
	held = rig.bass_grid.rows_now(playing)
	rig.bass_grid.apply(["variants", playing, "rows"], {"E2": {"0": {"length": 6, "velocity": 100}}})
	rig.bass_recipe.apply(["layers"], [
		{"id": "made", "generator": "hit_steps", "bypassed": False,
		 "params": {"pitch": "C2", "steps": [4]}}])

	try:
		rig.bass_grid.transpose = 2
		landed = _pitched(rig, rig.bass, rig.BASS_NOTE_MAP)

	finally:
		rig.bass_grid.transpose = 0
		rig.bass_recipe.apply(["layers"], [])
		rig.bass_grid.apply(["variants", playing, "rows"], held)

	assert sorted(note.pitch for note in landed) == [38, 42], (
		"the tapped E2 and the generated C2 should both sound two semitones up")

	cells = [one["cells"] for one in reported if one["name"] == "realised"][-1]

	assert set(cells) == {"C2"}, f"the generated note left its row: {cells}"
	assert rig._relabel(rig.BASS_NOTE_MAP)("C2", 2) == "D2"


# --- Pages and stores ----------------------------------------------------------

def test_every_control_this_composition_declares_reaches_a_page (rig: typing.Any) -> None:
	"""A control declared and put on no page is invisible, and nothing says so.

	The transport and the store are not parts: they are drawn on the bar whatever
	page is open, which is why this asks for them by type rather than by name.
	"""

	drawn = {name for name, control in rig.link.controls.items()
	         if not isinstance(control, (superconductor.subsequence_adapter.Transport,
	                                     superconductor.subsequence_adapter.StoreStatus))}
	placed = {part for page in rig.link.pages for part in page.parts}

	assert drawn - placed == set(), f"declared and on no page: {sorted(drawn - placed)}"
	assert placed - drawn == set(), f"on a page and never declared: {sorted(placed - drawn)}"


def test_what_is_made_is_kept_beside_the_example (rig: typing.Any) -> None:
	"""A copy of the example keeps its own store next to itself, so two copies never
	put back each other's patterns."""

	store = rig.link.pattern_store

	assert store is not None, "nothing made on the glass would survive a restart"
	assert store.path == WHERE.with_suffix(".patterns.json")


def test_the_page_set_still_fits_the_row_of_named_buttons (rig: typing.Any) -> None:
	"""Past `PAGE_BUTTONS` the client stops drawing page names and offers previous
	and next with a counter instead.  The number is read out of the client rather
	than written here, so the two cannot disagree."""

	source = (superconductor.service.CLIENT_DIR / "app.js").read_text(encoding="utf-8")
	limit = re.search(r"^const PAGE_BUTTONS = (\d+);$", source, re.MULTILINE)

	assert limit, "the client no longer names a page-button limit"
	assert len(rig.link.pages) <= int(limit.group(1)), (
		f"{len(rig.link.pages)} pages is past {limit.group(1)}, so the panel will"
		f" draw a counter instead of their names")


def test_the_shared_line_is_drawn_where_both_the_synths_it_feeds_are (rig: typing.Any) -> None:
	"""A cable has two ends, and a page that shows one of them shows half a connection."""

	notes_page = next(page for page in rig.link.pages if page.page_id == "notes")

	for part in ("notes", "shared_notes", "shared_notes_recipe", "bass", "poly"):
		assert part in notes_page.parts, part


# --- Stacks --------------------------------------------------------------------

def test_every_pattern_can_be_given_a_generator (rig: typing.Any) -> None:
	"""The panel offers *add generator* on a pattern exactly where a stack declares
	it `builds`.  Asserted against the grids rather than a list of names, so a grid
	added later fails here rather than arriving without one."""

	grids = {name for name, control in rig.link.controls.items()
	         if isinstance(control, (superconductor.subsequence_adapter.StepGrid,
	                                 superconductor.subsequence_adapter.NoteGrid))}

	built = {control.declaration()["builds"] for control in rig.link.controls.values()
	         if control.declaration().get("type") == "recipe"}

	assert grids, "no grids at all, so this proves nothing"
	assert grids - built == set(), f"these patterns take no contributions: {sorted(grids - built)}"


def test_a_stack_offers_the_pitches_of_the_pattern_it_builds (rig: typing.Any) -> None:
	"""A euclidean on the kit picks between its sounds, and the same generator on
	the bass picks between the notes its rows are.  A bass stack handed the kit's
	rows would offer `kick` as a pitch, and every value it sent would be refused."""

	assert rig.drum_recipe.pitches == rig.ROWS
	assert rig.bass_recipe.pitches == rig.BASS_ROWS
	assert rig.poly_recipe.pitches == rig.POLY_ROWS

	assert "kick" in rig.drum_recipe.pitches
	assert "kick" not in rig.bass_recipe.pitches


def test_the_slot_count_is_bounded_and_the_one_measured_in_beats_is_not (
	rig: typing.Any, caplog: pytest.LogCaptureFixture) -> None:
	"""`grid` means *how many slots* on most of Subsequence's generators and *a grid
	size in beats* on `swing`, which opens at 0.25.  Bounded as slots, swing would be
	born outside its own range and every write to its stack refused.  The example
	names the unit, so the bound reaches only what it was written for, and a stack
	built here says nothing about a bound it had to drop."""

	with caplog.at_level(logging.WARNING, logger="superconductor.subsequence_adapter"):
		rig._stack_for("drums", "probe_recipe", "Probe")

	dropped = [one.getMessage() for one in caplog.records if "not bounding" in one.getMessage()]

	assert dropped == [], f"a bound still had to be dropped: {dropped}"

	said = rig.drum_recipe.declaration()
	grids = {one["name"]: p
	         for one in said["generators"] + said.get("transforms", [])
	         for p in one["parameters"] if p["name"] == "grid"}

	counted = {name: p for name, p in grids.items() if p.get("unit") == "steps"}
	beaten = {name: p for name, p in grids.items() if p.get("unit") == "beats"}

	assert counted and beaten, f"the collision has gone from the catalogue: {grids}"

	for name, p in counted.items():
		assert p.get("max") == rig.STEPS, f"{name}.grid was not bounded to the pattern"

	for name, p in beaten.items():
		assert "max" not in p, f"{name}.grid was bounded as though it counted slots"


def test_a_stack_is_bounded_by_the_pattern_it_builds (rig: typing.Any) -> None:
	"""Sixteen pulses on a nine-step pattern would be a control whose top half cannot land."""

	def ceiling (recipe: typing.Any, generator: str, parameter: str) -> typing.Any:
		"""The top of one parameter's range, as the panel is offered it."""

		shape = next(one for one in recipe.declaration()["generators"] if one["name"] == generator)

		return next(one for one in shape["parameters"] if one["name"] == parameter)["max"]

	assert ceiling(rig.nine_recipe, "euclidean", "pulses") == 9
	assert ceiling(rig.drum_recipe, "euclidean", "pulses") == 16


# --- Variants ------------------------------------------------------------------

def test_the_kit_the_bass_and_the_poly_take_the_same_four_variants (rig: typing.Any) -> None:
	"""The same letters on all three is what makes a scene *cue B on every grid*;
	every other grid declares none."""

	declared = {name: control.declaration() for name, control in rig.link.controls.items()
	            if isinstance(control, (superconductor.subsequence_adapter.StepGrid,
	                                    superconductor.subsequence_adapter.NoteGrid))}

	with_variants = {name: one["variants"] for name, one in declared.items() if one.get("variants")}

	assert with_variants == {name: list(rig.VARIANTS) for name in ("drums", "bass", "poly")}


def test_the_opening_pattern_is_variant_a_s (rig: typing.Any) -> None:
	"""A person starts B from A with a tap; the file seeds the first alone."""

	assert rig.drum_grid.rows_now("A")["kick"] == {
		str(step): {"velocity": rig.VELOCITY} for step in rig.OPENING_PATTERN["kick"]}
	assert all(not any(rig.drum_grid.rows_now(one).values()) for one in ("B", "C", "D"))


def test_a_build_plays_the_variant_the_grid_says_and_lands_a_cue (rig: typing.Any) -> None:
	"""**The whole mechanism, through the example's own play function**: a cued variant
	becomes the live one at the build, and its steps are what the build places."""

	rig.drum_grid.apply(["variants", "B", "rows"], {"hand_clap": {"2": {"velocity": 90}}})

	try:
		rig.drum_grid.apply(["cue"], "B")
		landed = _built(rig, rig.drums, rig.STEPS)

		assert rig.drum_grid.playing == "B"
		assert {note.origin for note in landed} == {"hand_clap"}, "the build played A"

	finally:
		rig.drum_grid.apply(["cue"], "A")
		rig.drum_grid.now()
		rig.drum_grid.apply(["variants", "B", "rows"], {})

	assert rig.drum_grid.playing == "A"


# --- Two mechanisms side by side: a lane routed, and a pattern of its own --------

def test_a_lane_of_one_row_lands_on_that_sound_and_nowhere_else (rig: typing.Any) -> None:
	"""A grid declaring only `snare` holds nothing for the other rows, so routing a
	lane to one sound needs no mechanism of its own."""

	landed = _built(rig, lambda p: rig._play(
		p, {"snare": {str(step): {"velocity": 100} for step in (0, 4, 8, 12)}}), rig.STEPS)

	assert landed, "the lane placed nothing at all"
	assert {note.pitch for note in landed} == {rig.DRUM_NOTES["snare"]}


def test_a_step_is_played_as_hard_as_it_was_struck (rig: typing.Any) -> None:
	"""An accent and a ghost note on one row, each leaving at its own velocity, in
	the sixteenth it was placed on."""

	landed = _built(rig, lambda p: rig._play(
		p, {"snare": {"4": {"velocity": 127}, "6": {"velocity": 22}}}), rig.STEPS)

	pulses = 24 * rig.STEP_DURATION

	assert sorted((round(note.position / pulses), note.velocity) for note in landed) == [(4, 127), (6, 22)]


def test_the_snare_lane_is_one_row_wide_and_its_stack_offers_only_the_snare (
	rig: typing.Any) -> None:
	"""It has no instrument of its own, and a euclidean added to it can only write
	snares: a pool that could choose any sound would make the lane a kit again."""

	declared = rig.link.controls["snare_lane"].declaration()

	assert declared["rows"] == ["snare"]
	assert declared.get("pattern") is None

	euclidean = next(one for one in rig.snare_recipe.declaration()["generators"]
	                 if one["name"] == "euclidean")
	pitch = next(one for one in euclidean["parameters"] if one["name"] == "pitch")

	assert [one["value"] for one in pitch["options"]] == ["snare"]


def test_the_nine_runs_against_the_sixteen_rather_than_inside_it (rig: typing.Any) -> None:
	"""A pattern of its own, nine steps against sixteen on the same kit, coming round
	together every nine bars.  2.25 beats, which survives being declared as itself
	rather than as 2."""

	nine = rig.link.controls["nine"].declaration()
	drums = rig.link.controls["drums"].declaration()

	assert nine["steps"] == 9
	assert nine["beats"] == 2.25 and isinstance(nine["beats"], float)
	assert drums["beats"] == 4
	assert nine["rows"] == drums["rows"]


def test_the_nine_asks_its_grid_what_to_play (rig: typing.Any) -> None:
	"""Rather than reading its rows directly, so it plays only as many steps as its grid says."""

	assert rig.link.controls["nine"] is rig.nine_grid
	assert "nine_grid.now(p)" in inspect.getsource(rig.nine)


def test_a_routed_grid_places_nothing_past_the_end_of_the_pattern_it_plays_into (
	rig: typing.Any) -> None:
	"""Subsequence plays a note placed past a pattern's length inside the next cycle
	rather than dropping it, so a sixteen-step grid routed into the nine stops at
	nine."""

	pattern = subsequence.pattern.Pattern(channel=rig.DRUM_CHANNEL, length=rig.NINE_BEATS)
	builder = subsequence.pattern_builder.PatternBuilder(
		pattern=pattern, cycle=0, rng=random.Random(1),
		drum_note_map=rig.DRUM_NOTES, default_grid=rig.NINE_STEPS)

	rig._play(builder, {"kick": {str(step): {"velocity": 100} for step in range(rig.STEPS)}})

	pulses = 24 * rig.STEP_DURATION

	assert sorted(round(note.position / pulses) for note in builder.placed()) == list(range(rig.NINE_STEPS))


def test_a_length_is_offered_on_every_pattern_and_on_no_routed_grid (rig: typing.Any) -> None:
	"""A grid driving no pattern plays at the length of whatever routed it, so only
	the grids that drive a pattern offer one."""

	for name in ("drums", "nine", "bass", "poly"):
		assert "min_steps" in rig.link.controls[name].declaration(), name

	for name in ("shared", "snare_lane", "shared_notes"):
		assert "min_steps" not in rig.link.controls[name].declaration(), name


# --- Grids made from the glass -------------------------------------------------

def test_a_grid_the_panel_makes_can_be_routed_the_moment_it_exists (rig: typing.Any) -> None:
	"""A made grid makes no sound until something routes it, so one that was not a
	source would be a block that can never do anything.  A stack holds the shared
	map rather than a copy of it, which is what lets it offer a grid made after it."""

	before = set(rig.SHARED)
	made = rig._make_grid({"name": "made_grids-x", "rows": ["snare"], "steps": 8})

	assert made.name == "made_grids-x"
	assert set(rig.SHARED) - before == {"made_grids-x"}
	assert "made_grids-x" in rig.drum_recipe.declaration()["sources"], (
		"a stack built at import does not offer a grid the rack made after it")

	assert _built(rig, lambda p: rig.SHARED["made_grids-x"](p), 8) == [], \
		"an untouched grid placed something"

	made.apply(["snare", "0"], True)
	made.apply(["snare", "4"], {"velocity": 60})
	landed = _built(rig, lambda p: rig.SHARED["made_grids-x"](p), 8)

	assert {note.pitch for note in landed} == {rig.DRUM_NOTES["snare"]}

	rig._unmake_grid("made_grids-x")

	assert "made_grids-x" not in rig.SHARED
	assert "made_grids-x" not in rig.drum_recipe.declaration()["sources"], (
		"a stack goes on offering a cable to a grid nobody can see")


def test_the_rack_cannot_make_a_grid_longer_than_a_route_can_carry (rig: typing.Any) -> None:
	"""A grid routed into a pattern plays at that pattern's length, so a twenty-step
	grid routed into sixteen would quietly lose four steps."""

	declared = rig.link.controls["made_grids"].declaration()

	assert declared["type"] == "rack"
	assert declared["max_steps"] == rig.STEPS
	assert declared["rows"] == rig.ROWS


# --- The shared line of notes ----------------------------------------------------

def _routed (rig: typing.Any, source: str, note_map: dict[str, int],
             steps: int | None = None) -> list[tuple[int, int]]:
	"""Play one of the example's sources into a pattern carrying *note_map*, and read back what landed.

	*steps* is how long the borrowing pattern plays, which is what `p.grid` says.
	"""

	playing = rig.STEPS if steps is None else steps
	pattern = subsequence.pattern.Pattern(channel=1, length=rig.BEATS * playing / rig.STEPS)
	builder = subsequence.pattern_builder.PatternBuilder(
		pattern=pattern, cycle=0, rng=random.Random(1),
		drum_note_map=note_map, default_grid=playing)

	rig.SHARED[source](builder)

	return sorted((note.position, note.pitch) for note in builder.placed())


def _lengths (rig: typing.Any, source: str, note_map: dict[str, int], steps: int) -> list[tuple[int, int | None]]:
	"""The same, read back as each note's position and how long it sounds."""

	pattern = subsequence.pattern.Pattern(channel=1, length=rig.BEATS * steps / rig.STEPS)
	builder = subsequence.pattern_builder.PatternBuilder(
		pattern=pattern, cycle=0, rng=random.Random(1),
		drum_note_map=note_map, default_grid=steps)

	rig.SHARED[source](builder)

	return sorted((note.position, note.duration) for note in builder.placed())


@pytest.fixture
def line (rig: typing.Any) -> typing.Iterator[dict[str, typing.Any]]:
	"""The shared line's notes, to write a test's own into and put back afterwards."""

	held = rig.composition.data.get("shared_notes")

	yield rig.composition.data

	if held is None:
		rig.composition.data.pop("shared_notes", None)

	else:
		rig.composition.data["shared_notes"] = held


def test_a_shared_line_stops_at_the_end_of_the_pattern_it_is_played_into (
	rig: typing.Any, line: dict[str, typing.Any]) -> None:
	"""A sixteen-step line routed into a twelve-step pattern must not play its last
	four steps into the start of the next bar."""

	line["shared_notes"] = {
		"C2": {str(rig.BASS_DIVISIONS * 11): {"velocity": 90, "length": 1},
		       str(rig.BASS_DIVISIONS * 13): {"velocity": 90, "length": 1}}}

	landed = _routed(rig, "shared_notes", rig.BASS_NOTE_MAP, steps=12)
	pulses = int(24 * rig.STEP_DURATION)

	assert landed == [(pulses * 11, rig.BASS_NOTE_MAP["C2"])], \
		f"a routed line played past the end of the pattern it was played into: {landed}"


def test_a_shared_note_is_cut_at_the_end_rather_than_ringing_past_it (
	rig: typing.Any, line: dict[str, typing.Any]) -> None:
	"""**Cut, never shortened**: the line keeps the length it was given, and only the
	copy played stops where the pattern does."""

	line["shared_notes"] = {
		"C2": {str(rig.BASS_DIVISIONS * 10): {"velocity": 90, "length": rig.BASS_DIVISIONS * 4}}}

	landed = _lengths(rig, "shared_notes", rig.BASS_NOTE_MAP, steps=12)
	pulses = int(24 * rig.STEP_DURATION)

	assert landed == [(pulses * 10, pulses * 2)], \
		f"a routed note rang past the end of the pattern it was played into: {landed}"

	kept = rig.composition.data["shared_notes"]["C2"][str(rig.BASS_DIVISIONS * 10)]

	assert kept["length"] == rig.BASS_DIVISIONS * 4, "cutting the copy shortened the line itself"


def test_a_shared_line_of_notes_sounds_the_same_on_either_synth (
	rig: typing.Any, line: dict[str, typing.Any]) -> None:
	"""One line, two synths, each keeping a grid of its own.  A pitch means itself,
	so the line places the number and sounds the same on whatever borrowed it, even
	a note neither synth's grid has a row for."""

	line["shared_notes"] = {
		"C2": {"0": {"velocity": 90, "length": rig.BASS_LENGTH}},
		"G2": {str(rig.BASS_DIVISIONS * 4): {"velocity": 90, "length": rig.BASS_LENGTH}}}

	on_the_bass = _routed(rig, "shared_notes", rig.BASS_NOTE_MAP)
	on_the_poly = _routed(rig, "shared_notes", rig.POLY_NOTE_MAP)

	assert on_the_bass == on_the_poly, \
		"the same line did not reach both, so a row name was resolved somewhere"

	pulses = int(24 * rig.STEP_DURATION)

	assert on_the_bass == [(0, rig.BASS_NOTE_MAP["C2"]), (pulses * 4, rig.BASS_NOTE_MAP["G2"])]
	assert "C2" not in rig.POLY_NOTE_MAP


def test_the_shared_line_is_offered_to_every_stack_and_drives_nothing (rig: typing.Any) -> None:
	"""It is a source like the drum grids, and like them it has no pattern of its own."""

	for stack in ("bass_recipe", "poly_recipe", "drums_recipe"):
		assert "shared_notes" in rig.link.controls[stack].declaration()["sources"], stack

	declared = rig.link.controls["shared_notes"].declaration()

	assert declared["type"] == "note_grid"
	assert rig.shared_notes.pattern is None


def test_the_shared_line_holds_every_note_and_opens_where_the_bass_register_starts (
	rig: typing.Any) -> None:
	"""A grid with no instrument has no register of its own, so it holds every note
	MIDI has, and says where its window opens, or it would open on C-1."""

	declared = rig.link.controls["shared_notes"].declaration()

	assert len(declared["rows"]) == 128
	assert declared["rows"][0] == "G9" and declared["rows"][-1] == "C-1", "drawn highest first"
	assert declared["opens_at"] == "C1"

	for row in rig.BASS_ROWS + rig.POLY_ROWS:
		assert row in declared["rows"], row

	assert rig.shared_notes_recipe.pitches == declared["rows"], \
		"the stack on it may write anything the grid can hold"


def test_the_set_of_pitches_is_a_whole_keyboard_seen_from_c2 (rig: typing.Any) -> None:
	"""Eighty-eight keys, opening on the octave between the bass and the poly."""

	declared = rig.notes.declaration()
	midi = [one["midi"] for one in declared["pitches"]]

	assert midi == list(range(21, 109)), "A0 to C8, every key of a piano and nothing else"
	assert declared["opens_at"] == "C2"
