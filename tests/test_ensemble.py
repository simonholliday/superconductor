"""The ensemble composition: seven instruments, four pages, and nothing playing.

**This file's subject is a rig that starts from zero** (Simon, 2026-09-14), so the
test that matters most is that it makes no sound — asserted by rendering it
through Subsequence's own scheduler and counting the notes, because a composition
that seeds nothing is easy to write and easy to break later with one convenient
default.

**Not run by CI**, like every test here that imports `subsequence`: the sequencer
is a rig arrangement and a runner has not got it.
"""

import importlib.util
import json
import pathlib
import subprocess
import sys
import typing

import pytest

import pymidiinstrumentdefs


HERE = pathlib.Path(__file__).parent.parent
WHERE = HERE / "compositions" / "ensemble.py"


def _composition () -> typing.Any:
	"""The composition module, imported once and shared.

	Importing it does not dial the service: the link connects when it is started,
	which only ``__main__`` does.
	"""

	if "ensemble" not in sys.modules:
		spec = importlib.util.spec_from_file_location("ensemble", str(WHERE))
		assert spec is not None and spec.loader is not None
		module = importlib.util.module_from_spec(spec)
		sys.modules["ensemble"] = module
		spec.loader.exec_module(module)

	return sys.modules["ensemble"]


@pytest.fixture (scope="module")
def rig () -> typing.Any:
	"""The composition, loaded but not playing."""

	return _composition()


# --- What it comes up as -------------------------------------------------------

def test_the_rig_comes_up_with_nothing_on_it (rig: typing.Any) -> None:
	"""**The whole point of this composition** (Simon, 2026-09-14): *"I'd like to
	start from nothing with a bunch of instruments and no initial patterns,
	connections or routes between them."*

	Checked on the data rather than on the glass, because this is where a seeded
	pattern would be: every grid reads its rows out of ``composition.data`` and
	an opening pattern is a dict put there at import.

	**Four empty variants is still nothing.**  A grid that takes variants writes a
	shell for each at birth, so what is asserted is that no row anywhere holds a
	step — not that the dict is bare.
	"""

	for one in rig.INSTRUMENTS:
		held = rig.composition.data.get(one.key) or {}
		rows = {name: variant.get("rows") or {} for name, variant in held.items()}
		played = {name: content for name, content in rows.items() if content}

		assert not played, f"{one.key} came up holding something: {played}"

	for key, stack in rig.STACKS.items():
		assert not stack.declaration().get("layers"), f"{key} came up with a generator on it"


def test_no_grid_here_takes_from_another (rig: typing.Any) -> None:
	"""No routes and no cables either, which is the other half of *from nothing*.

	A stack offers a route only where there is something to route from, and nothing
	is until a person makes a line — so there is no cable to drag on the first
	morning and every one that appears later was patched by somebody.

	**One map for every stack** (#2108), held rather than copied (#2421), which is
	what lets a line made on the glass be offered to all of them the moment it
	exists.
	"""

	for key, stack in rig.STACKS.items():
		assert not stack.declaration().get("sources"), f"{key} was offered something to route from"
		assert stack.sources is rig.SOURCES, f"{key} routes from a map of its own"


def test_every_instrument_listens_on_a_channel_of_its_own (rig: typing.Any) -> None:
	"""Two instruments on one channel is the fault that sounds like a broken instrument.

	Both play, both answer every note meant for either, and nothing on the glass
	says so — so it is worth one assertion rather than an afternoon.
	"""

	channels = [one.channel for one in rig.INSTRUMENTS]

	assert len(set(channels)) == len(channels), f"two instruments share a channel: {channels}"


# --- What a definition is allowed to decide ------------------------------------

def test_a_part_sits_where_its_definition_says_above_the_base (rig: typing.Any) -> None:
	"""The Streichfett's solo section is one channel above its strings, and the
	definition is what says *one* — this file says only where the base is.

	**Measured on the hardware before it was written down** (#2544): notes sent a
	channel above the base sound the solo voice.
	"""

	_needs(rig, "strings", "solo")

	streichfett = pymidiinstrumentdefs.load("waldorf/streichfett")
	strings = next(one for one in rig.INSTRUMENTS if one.key == "strings")
	solo = next(one for one in rig.INSTRUMENTS if one.key == "solo")

	assert streichfett.parts["strings"].channel_offset == 0
	assert streichfett.parts["solo"].channel_offset == 1
	assert solo.channel == strings.channel + 1


def test_a_part_that_moved_under_the_rig_is_refused_rather_than_played_wrong (
	rig: typing.Any) -> None:
	"""The check the pair above is worth having: a table saying otherwise fails at
	import, where somebody is looking, rather than on a channel nothing answers."""

	_needs(rig, "solo")

	wrong = dataclasses_replace(rig, "solo", channel=7)

	with pytest.raises(ValueError, match="sits 1 above its base"):
		rig._channel_for(wrong)


def test_each_part_sounds_as_many_notes_as_it_says_and_not_as_many_as_the_instrument (
	rig: typing.Any) -> None:
	"""A Streichfett's strings take 128 notes and its solo eight, which is a real
	difference on the glass: the solo grid refuses a ninth note in a column."""

	_needs(rig, "strings", "solo")

	assert rig.GRIDS["strings"].declaration()["voices"] == 128
	assert rig.GRIDS["solo"].declaration()["voices"] == 8


def test_an_instrument_that_switches_voice_counts_has_to_be_told_which (rig: typing.Any) -> None:
	"""`polyphony = None` is *nobody has established it* and a grid's `voices` of
	None is *as many as you like*; handing one to the other turns unknown into
	unlimited.  A Matriarch is told four."""

	matriarch = pymidiinstrumentdefs.load("moog/matriarch")

	assert matriarch.voice.polyphony is None
	assert matriarch.voice.voicing_modes == (1, 2, 4)
	assert rig.GRIDS["matriarch"].declaration()["voices"] == 4

	with pytest.raises(ValueError, match="has to be told which to assume"):
		rig._voice_count(matriarch)


def test_a_register_outside_what_an_instrument_can_sound_is_refused (rig: typing.Any) -> None:
	"""Outside its range an instrument is **silent** rather than wrong-sounding, so
	a register set an octave too high draws a grid that works perfectly and makes
	no sound.  Nothing else would tell you (#2121)."""

	too_high = dataclasses_replace(rig, "minitaur", low="C6", high="C7")

	with pytest.raises(ValueError, match="outside what a .* can sound"):
		rig._register(too_high)


def test_a_setting_naming_a_control_the_instrument_has_not_is_refused (rig: typing.Any) -> None:
	"""A row on the glass that moves nothing and says nothing about it is the
	silence every check in this file exists for."""

	minitaur = next(one for one in rig.INSTRUMENTS if one.key == "minitaur")

	with pytest.raises(ValueError, match="has no control called 'wobble'"):
		rig._panel_parameter(minitaur, "wobble", "wobble", "Wobble", 0, None)


def test_an_instrument_with_nothing_to_receive_gets_no_settings_block (rig: typing.Any) -> None:
	"""A Model D and a Malevolent are all-knobs synths whose definitions declare no
	controls at all.  **The panel loses a control rather than drawing a broken one**
	(#2046), so they get a pattern and no block — and a block of no rows is worse
	than no block."""

	_needs(rig, "model_d", "malevolent", "strings", "solo")

	for key in ("model_d", "malevolent", "drm1", "solo"):
		assert rig.SETTINGS[key] is None, f"{key} was given a settings block with nothing in it"

	for key in ("tr8s", "minitaur", "matriarch", "strings"):
		assert rig.SETTINGS[key] is not None, f"{key} has controls and was given no block"


def test_the_streichfett_s_solo_controls_are_set_on_the_strings_channel (rig: typing.Any) -> None:
	"""**Every one of its nineteen controls is unparted**, which is the parts
	format's way of saying *the base channel* — so the solo voice's tone is set on
	channel 2 while its notes are played on 3.

	Measured on the hardware first (#2544): control changes 76, 70 and 77 sent to
	the channel above the base moved nothing at all.
	"""

	_needs(rig, "strings")

	streichfett = pymidiinstrumentdefs.load("waldorf/streichfett")
	by_part = streichfett.controls_by_part()

	assert list(by_part) == [""], f"a control moved off the base channel: {list(by_part)}"

	fields = [one["name"] for one in rig.SETTINGS["strings"].declaration()["fields"]]

	assert "solo_tone" in fields, "the solo section's controls are not on the block that can send them"
	assert rig.SETTINGS["strings"].declaration()["configures"] == "strings"


# --- Keyboards, made from the glass --------------------------------------------

def test_the_rig_offers_sets_of_pitches_and_starts_with_none (rig: typing.Any) -> None:
	"""Simon, 2026-09-14, of an arpeggiator with nothing to feed it: *"should we
	have a way of creating a new instance on the interface?  Or does it have to be
	defined up-front, in the composition?"*

	**Neither, in the end**: the composition defines the *rack* and the person makes
	the keyboards.  Which is also why this rig still comes up from nothing — a rack
	that has made nothing is a button, not a control holding music.
	"""

	declared = rig.keyboards.declaration()

	assert declared["type"] == "rack"
	# "Pitches" since #2527 decision 5; it made keyboards before that, and still draws one.
	assert declared["makes"] == "pitch set"
	assert "min_steps" not in declared, "a keyboard was offered a length"
	assert declared["rows"] == [], "a keyboard was offered rows to choose"

	assert rig.keyboards.entries() == [], "the rig came up with a keyboard already made"


def test_a_made_keyboard_is_a_set_of_pitches_anything_may_read (rig: typing.Any) -> None:
	"""**What a made thing *is* stays this file's** (#1465): the rack holds a list
	and this turns one entry into a set of pitches over the eighty-eight keys.

	A pool of its own rather than any instrument's, because it is patched into
	whatever wants notes and each consumer folds a choice into its own reach.
	"""

	made = rig._make_keyboard({"id": "abc"})

	assert made.kind == "pitch_set"
	assert made.name == "keyboards-abc"
	assert len(made.pitches) == 88
	assert made.chosen == [], "a new keyboard came up holding notes"


def test_a_keyboard_may_be_patched_into_any_generator_that_wants_pitches (
	rig: typing.Any) -> None:
	"""The point of the whole thing: one pool feeding an arpeggio on the Minitaur
	and another on the Matriarch, which cannot drift apart because there is one of
	it.

	Checked against the protocol's own table rather than by naming a kind here —
	what may be plugged into what is one policy in one place (#2403).
	"""

	import superconductor.protocol

	made = rig._make_keyboard({"id": "abc"})
	arpeggio = next(
		one for one in rig.STACKS["minitaur"].declaration()["generators"]
		if one["name"] == "arpeggio")
	notes = next(one for one in arpeggio["parameters"] if one["name"] == "notes")

	wants = superconductor.protocol.PATCH_INPUTS[(notes["kind"], notes["role"])]

	assert made.kind in wants[0], \
		f"an arpeggio wants {wants[0]} and a keyboard is a {made.kind}"


def test_the_keyboards_are_reachable_from_every_page_that_plays_notes (
	rig: typing.Any) -> None:
	"""A cable is dragged between two blocks, so both have to be on the page — a
	keyboard on a page of its own could feed nothing anybody could see."""

	pages = {page.declaration()["title"]: page.declaration()["parts"]
	         for page in rig.link.pages}

	for named in ("Ensemble", "Synths", "Bass"):
		assert rig.KEYBOARDS in pages[named], f"{named} has no keyboard to patch from"


# --- The key, and degrees that follow it ----------------------------------------

def test_the_key_block_offers_a_root_and_subsequence_s_own_scales (rig: typing.Any) -> None:
	"""**One key for the whole piece, in a block of its own** (Simon, 2026-09-15, #2527):
	a root and a scale, Subsequence's names, opening at C major so that a degree set
	made on the first morning plays at once.

	**Every scale Subsequence offers, but a second name for one already offered**:
	``ionian`` is ``major`` and ``aeolian`` is ``minor``, and a list offering both would
	be two buttons for one scale.  **Compared by their notes** rather than against a
	list of names (#3562), so a new spelling of a scale here passes by itself, and a
	new scale fails until the Key block offers it.
	"""

	import subsequence.intervals

	fields = {one["name"]: one for one in rig.key_block.declaration()["fields"]}

	assert [one["value"] for one in fields["root"]["options"]] == list(rig.ROOTS)
	assert len(rig.ROOTS) == 12

	offered = [one["value"] for one in fields["scale"]["options"]]
	notes = {one: tuple(subsequence.intervals.scale_pitch_classes(0, one))
	         for one in subsequence.intervals.SCALE_MODE_MAP}

	assert set(offered) <= set(notes)
	assert len({notes[one] for one in offered}) == len(offered), "two buttons play the same scale"

	held = {notes[one] for one in offered}
	missing = [one for one in notes if one not in offered and notes[one] not in held]

	assert not missing, f"Subsequence has scales the Key block does not offer: {missing}"
	assert "ionian" not in offered and "aeolian" not in offered, "a mode is offered by its second name"

	assert rig.composition.data[rig.KEY] == {"root": "C", "scale": "major"}
	assert rig._key_now() == ("C major", [60, 62, 64, 65, 67, 69, 71])


def test_changing_the_key_sets_the_composition_s_and_moves_every_degree_set (rig: typing.Any) -> None:
	"""The key the Key block holds is the composition's own (`Composition.key`), which
	Subsequence reads at every build, and every degree set made here is told."""

	made = rig._make_degrees({"id": "key-test"})

	class Told:
		"""A link that notes each time a set asks to say its key."""

		def __init__ (self) -> None:
			self.asked = 0

		def on_clock (self, work: typing.Any) -> None:
			self.asked += 1

	told = Told()
	made.attach(typing.cast(typing.Any, told))

	try:
		made.apply(["chosen"], [{"step": 1, "octave": 0, "chroma": 0}, {"step": 3, "octave": 0, "chroma": 0}])

		assert made.notes() == [60, 64]

		rig.key_block.apply(["root"], "D")
		rig.key_block.apply(["scale"], "dorian")

		assert told.asked == 2, "a degree set was not told the key moved, so no panel would be"
		assert (rig.composition.key, rig.composition.scale) == ("D", "dorian")
		assert made.notes() == [62, 65]
		assert made.snapshot()["key"] == "D dorian"
		assert [one["note"] for one in made.snapshot()["scale"]] == ["D", "E", "F", "G", "A", "B", "C"]

	finally:
		rig.key_block.apply(["root"], "C")
		rig.key_block.apply(["scale"], "major")
		rig._unmake_degrees(made.name)


def test_the_rig_offers_degree_sets_and_starts_with_none (rig: typing.Any) -> None:
	"""Made from the glass beside the sets of pitches, and as many as the music wants;
	three octaves, and a row as long as the longest scale on offer."""

	declared = rig.degrees.declaration()

	assert declared["type"] == "rack" and declared["makes"] == "degree set"
	assert "min_steps" not in declared and declared["rows"] == []
	assert rig.degrees.entries() == []

	made = rig._make_degrees({"id": "abc"})

	try:
		assert made.kind == "degree_set"
		assert made.name == "degrees-abc"
		assert made.declaration()["octaves"] == [-1, 0, 1]
		assert made.declaration()["steps"] == rig.MOST_STEPS == 12, \
			"a row of degrees is not as long as chromatic, the longest scale on offer (#3562)"
		assert made.title == "Degrees 1"

	finally:
		rig._unmake_degrees(made.name)


def test_a_set_of_pitches_is_called_so_on_the_glass_and_kept_where_it_always_was (
	rig: typing.Any) -> None:
	"""**"Pitches" and "Degrees"** (#2527 decision 5), a matching pair named for what
	each holds.  The words on the glass move and the names things are kept by do not,
	so every set already made comes back."""

	declared = rig.keyboards.declaration()

	assert declared["title"] == "Pitches" and declared["makes"] == "pitch set"
	assert rig.keyboards.name == "keyboards", "the name a store keeps the sets under moved"
	assert rig._make_keyboard({"id": "xyz"}).title == "Pitches 1"


def test_the_key_and_the_degrees_are_on_every_page_that_plays_notes (rig: typing.Any) -> None:
	"""A cable is dragged between two blocks, and the key is changed where the sets are."""

	pages = {page.declaration()["title"]: page.declaration()["parts"] for page in rig.link.pages}

	for named in ("Ensemble", "Synths", "Bass"):
		assert rig.KEY in pages[named] and rig.DEGREES in pages[named], f"{named} lacks the key or the degrees"


def test_a_degree_set_patched_into_an_arpeggio_follows_the_key_it_is_played_in (
	tmp_path: pathlib.Path) -> None:
	"""**Done when**, as #2527 says it: one degree set, 1 3 5, patched into the
	Minitaur's arpeggio, rendered through Subsequence in C major and then in D major —
	and the same set plays C E G, then D F# A, with nothing re-patched."""

	def classes (root: str) -> set[int]:
		played = _rendered(tmp_path / root, place=False, key=root)
		rig = _composition()
		channel = next(one.channel for one in rig.INSTRUMENTS if one.key == "minitaur") - 1

		return {note % 12 for on, note in played["notes"] if on == channel}

	assert classes("C") == {0, 4, 7}
	assert classes("D") == {2, 6, 9}


# --- Lines, made from the glass ------------------------------------------------

def test_the_rig_offers_lines_and_starts_with_none (rig: typing.Any) -> None:
	"""**#2108 on the rig Simon plays**: *"I have the Minitaur and Behringer Model D. I
	want to create a bass pattern which plays on both."*  It was built in
	`drm1_grid.py` and this composition had no way to do it.

	Made from the glass, as a keyboard is, so the rig still comes up from nothing: a
	rack that has made nothing is a button.  A line has every note MIDI has, so there
	is nothing to choose, and it plays at the length of whatever it is routed into,
	so there is no length to set either.
	"""

	declared = rig.lines.declaration()

	assert declared["type"] == "rack"
	assert declared["makes"] == "line"
	assert "min_steps" not in declared, "a line was offered a length of its own"
	assert declared["rows"] == [], "a line was offered rows to choose"

	assert rig.lines.entries() == [], "the rig came up with a line already made"
	assert rig.SOURCES == {}, "the rig came up with something to route from"


def test_a_made_line_is_every_note_with_no_instrument_and_every_stack_may_take_it (
	rig: typing.Any) -> None:
	"""**A pitched grid belonging to no pattern**, drawn over the whole of MIDI and
	opening where this rig's bass lives, because what a note sounds like belongs to
	whatever it is patched into (Simon, 2026-09-14, on `drm1_grid.py`'s line).

	Routable the moment it exists, from every stack here, and withdrawn when it goes,
	or a stack goes on offering a cable to a line nobody can see.
	"""

	made = rig._make_line({"id": "abc"})

	try:
		assert made.kind == "note_grid"
		assert made.name == "lines-abc"
		assert made.pattern is None, "a line drives a pattern of its own"
		assert len(made.rows) == 128 and made.rows[0] == "G9" and made.rows[-1] == "C-1"
		assert made.declaration()["opens_at"] == rig.LINE_OPENS_AT

		for key, stack in rig.STACKS.items():
			assert stack.declaration().get("sources") == ["lines-abc"], f"{key} was not offered the line"

	finally:
		rig._unmake_line("lines-abc")

	for key, stack in rig.STACKS.items():
		assert not stack.declaration().get("sources"), f"{key} still offers a line that has gone"


def _landed (rig: typing.Any, source: str, into: str, steps: int) -> list[tuple[int, int, int | None]]:
	"""Play one source into a pattern like *into*'s, *steps* long, and read back each note.

	Each note as its position, its pitch and how long it sounds, which is what a line
	routed into that instrument would put on the wire.
	"""

	import random

	import subsequence.pattern
	import subsequence.pattern_builder

	instrument = next(one for one in rig.INSTRUMENTS if one.key == into)
	pattern = subsequence.pattern.Pattern(channel=instrument.channel, length=rig.BEATS * steps / rig.STEPS)
	builder = subsequence.pattern_builder.PatternBuilder(
		pattern=pattern, cycle=0, rng=random.Random(1),
		drum_note_map=rig._note_map(instrument), default_grid=steps)

	rig.SOURCES[source](builder)

	return sorted((note.position, note.pitch, note.duration) for note in builder.placed())


def test_a_line_sounds_its_own_notes_in_either_synth_and_stops_where_each_ends (
	rig: typing.Any) -> None:
	"""**A pitch means itself**, so the same line is the same notes on the Minitaur and
	the Model D, each then transposed by its own grid.

	**And nothing past the end of the pattern it plays into** (#2548, `7eb4817`):
	Subsequence sounds a note placed past a pattern's length at the start of the next
	cycle rather than dropping it, so a line routed into a twelve-step pattern must
	lose its last four steps and cut a note that runs over, not play them into the bar
	after.  A note is cut in the copy played and kept whole on the line.
	"""

	_needs(rig, "model_d")

	made = rig._make_line({"id": "both"})
	per_step = rig.DIVISIONS

	try:
		made.apply(["C2", "0"], True)
		made.apply(["G2", str(10 * per_step)], True)
		made.apply(["G2", str(10 * per_step), "length"], 4 * per_step)
		made.apply(["E2", str(13 * per_step)], True)

		whole = _landed(rig, "lines-both", "minitaur", steps=16)
		short = _landed(rig, "lines-both", "model_d", steps=12)

		assert [(pitch) for _, pitch, _ in whole] == [36, 43, 40], f"the Minitaur heard {whole}"
		assert [(pitch) for _, pitch, _ in short] == [36, 43], f"the Model D heard {short}"
		cut, uncut = short[1][2], whole[1][2]

		assert cut is not None and uncut is not None and cut < uncut, \
			"a note running past a twelve-step end was not cut"
		assert made.rows_now()["G2"][str(10 * per_step)]["length"] == 4 * per_step, \
			"cutting the copy shortened the note on the line"

	finally:
		rig._unmake_line("lines-both")


def test_the_lines_are_reachable_from_every_page_that_plays_notes (rig: typing.Any) -> None:
	"""A cable is dragged between two blocks, so the rack and what it makes have to be
	on the page where the synths are."""

	pages = {page.declaration()["title"]: page.declaration()["parts"]
	         for page in rig.link.pages}

	for named in ("Ensemble", "Synths", "Bass"):
		assert rig.LINES in pages[named], f"{named} has no line to patch from"


# --- The glass -----------------------------------------------------------------

def test_every_page_names_something_this_composition_declares (rig: typing.Any) -> None:
	"""A page naming a control nobody declared draws an empty page and says nothing."""

	declared = set(rig.link.controls)

	for page in rig.link.pages:
		for part in page.declaration()["parts"]:
			assert part in declared, f"a page names {part!r}, which is not declared"


def test_the_pages_are_few_enough_to_be_named_on_the_glass (rig: typing.Any) -> None:
	"""The client draws named page buttons up to six and gives way to
	previous-and-next above that — so eight pages showed *"‹ Pattern 1 1/8 ›"* and
	no page names at all, which is the one thing a page selector is for."""

	assert len(rig.link.pages) <= 6, "there are more pages than the panel will name"


def test_every_instrument_is_on_the_ensemble_page (rig: typing.Any) -> None:
	"""*"New page 'ensemble' — we'll add everything in"* (Simon, 2026-09-14)."""

	ensemble = next(page for page in rig.link.pages
	                if page.declaration()["title"] == "Ensemble")

	assert ensemble.declaration()["parts"] == [one.key for one in rig.INSTRUMENTS] + [
		rig.KEY, rig.KEYBOARDS, rig.DEGREES, rig.LINES]


def test_a_settings_block_needs_no_page_of_its_own (rig: typing.Any) -> None:
	"""One that names the pattern it configures is drawn wherever that pattern is
	and put away behind its latch, so the pages name patterns and nothing else."""

	named = {part for page in rig.link.pages for part in page.declaration()["parts"]}
	settings = {f"{one.key}_settings" for one in rig.INSTRUMENTS}

	assert not (named & settings), f"a page named a settings block: {named & settings}"


# --- Played through Subsequence ------------------------------------------------

def test_the_rig_plays_nothing_until_somebody_plays_it (tmp_path: pathlib.Path) -> None:
	"""**The one that cannot be talked out of** — rendered through Subsequence's own
	scheduler with nothing placed, counting what reached the port.

	The only MIDI that leaves is the Matriarch's voice mode, which is the
	instrument being put where a chord can be heard rather than any music: it
	sounds incoming notes one at a time until that is asserted, whatever its front
	panel says (#2177).

	**A child process**, because a render installs signal handlers and wants the
	main thread, and MIDI is patched there or it goes looking among this rig's
	real ports (#2526).
	"""

	played = _rendered(tmp_path, place=False)

	assert played["notes"] == [], f"a rig that seeds nothing still played: {played['notes']}"
	assert played["controls"] == [[0, 94]], \
		f"something other than the Matriarch's voicing was sent: {played['controls']}"


def test_one_line_routed_into_two_synths_plays_on_both (tmp_path: pathlib.Path) -> None:
	"""**The whole of #2108, through Subsequence's own scheduler**: a line made on the
	glass with one note on it, a route to it on the Minitaur's stack and on the Model
	D's, and that note arriving on both channels and nowhere else."""

	_needs(_composition(), "model_d")

	played = _rendered(tmp_path, place=False, route=True)
	rig = _composition()
	channels = {one.key: one.channel - 1 for one in rig.INSTRUMENTS}

	assert sorted(played["notes"]) == sorted([[channels["minitaur"], 36], [channels["model_d"], 36]]), \
		f"the line did not reach exactly the two synths it was routed into: {played['notes']}"


def test_a_note_on_every_instrument_reaches_its_own_channel (tmp_path: pathlib.Path) -> None:
	"""And the other half: once somebody puts a note on each grid, each one sounds
	where its instrument is listening.  Channels are counted from zero on the wire
	and from one in this file, which is the off-by-one worth one assertion."""

	played = _rendered(tmp_path, place=True)
	wire = {channel for channel, _ in played["notes"]}
	rig = _composition()

	assert wire == {one.channel - 1 for one in rig.INSTRUMENTS}, \
		f"a note did not reach its instrument: {sorted(wire)}"


def _rendered (where: pathlib.Path, place: bool, route: bool = False, key: str | None = None) -> dict[str, typing.Any]:
	"""Play the composition in a child process and read back what reached the port.

	*route* makes a line holding one C2 and routes it into the Minitaur and the Model D.
	*key* sets that major key and patches a degree set holding 1, 3 and 5 into the
	Minitaur's arpeggio.
	"""

	where.mkdir(parents=True, exist_ok=True)

	done = subprocess.run(
		[sys.executable, str(pathlib.Path(__file__)), str(where),
		 f"key:{key}" if key else "route" if route else "place" if place else "silent"],
		capture_output=True, text=True, timeout=180, check=False, cwd=str(HERE))

	assert done.returncode == 0, done.stderr[-4000:]

	return typing.cast(dict[str, typing.Any], json.loads((where / "played.json").read_text()))


def _needs (rig: typing.Any, *keys: str) -> None:
	"""Wait, rather than fail, while an instrument a test is about is set aside.

	Simon set four aside in `ensemble.py` on 2026-09-18, to test the glass on a
	lighter page and bring them back later.  A test about one of them then says
	which it is missing, and runs again the moment it is uncommented.
	"""

	present = {one.key for one in rig.INSTRUMENTS}
	missing = [key for key in keys if key not in present]

	if missing:
		pytest.skip(f"set aside in ensemble.py: {', '.join(missing)}")


def dataclasses_replace (rig: typing.Any, key: str, **fields: typing.Any) -> typing.Any:
	"""One of the instruments with something changed, for the checks that want a wrong one."""

	import dataclasses

	return dataclasses.replace(next(one for one in rig.INSTRUMENTS if one.key == key), **fields)


# --- the child, which plays it -------------------------------------------------

if __name__ == "__main__":
	_where = pathlib.Path(sys.argv[1])
	_place = sys.argv[2] == "place"
	_route = sys.argv[2] == "route"
	_key = sys.argv[2][4:] if sys.argv[2].startswith("key:") else None

	import importlib


	class _Port:
		def send (self, message: typing.Any) -> None: pass
		def close (self) -> None: pass
		def panic (self) -> None: pass
		def reset (self) -> None: pass


	_mido = importlib.import_module("mido")
	setattr(_mido, "get_output_names", lambda: ["U6MIDI Pro Port 1"])
	setattr(_mido, "open_output", lambda *_, **__: _Port())
	setattr(_mido, "get_input_names", lambda: [])

	_rig = _composition()

	import subsequence.sequencer

	if _place:
		for _one in _rig.INSTRUMENTS:
			_row = _rig._rows(_one)[0]
			_grid = _rig.GRIDS[_one.key]
			_grid.apply(["variants", "A", "rows", _row, "0"],
			            True if _one.drums else {"length": 1, "velocity": 100})

	if _route:
		_line = _rig._make_line({"id": "shared"})
		_line.apply(["C2", "0"], True)

		for _into in ("minitaur", "model_d"):
			_rig.STACKS[_into].apply(["layers"], [{"id": "from-line", "kind": "route", "source": _line.name}])

	if _key:
		_rig.key_block.apply(["root"], _key)
		_rig.key_block.apply(["scale"], "major")

		_degrees = _rig._make_degrees({"id": "triad"})
		_degrees.apply(["chosen"], [{"step": step, "octave": 0, "chroma": 0} for step in (1, 3, 5)])

		# **Attached as a started link attaches them**, because a stack reads a patched
		# set through its link; nothing here dials the service.
		_rig.link.controls[_degrees.name] = _degrees

		for _control in list(_rig.link.controls.values()):
			_control.attach(_rig.link)

		_rig.STACKS["minitaur"].apply(["layers"], [{
			"id": "arp", "kind": "generator", "generator": "arpeggio",
			"params": {"notes": {"from": "control", "id": _degrees.name}}}])

	_notes: list[list[int]] = []
	_controls: list[list[int]] = []
	_dispatch = subsequence.sequencer.Sequencer._dispatch_with_compensation


	def _record (self: typing.Any, event: typing.Any) -> None:
		if event.message_type == "note_on":
			_notes.append([event.channel, event.note])

		elif event.message_type == "control_change":
			_controls.append([event.channel, event.control])

		_dispatch(self, event)


	setattr(subsequence.sequencer.Sequencer, "_dispatch_with_compensation", _record)
	_rig.composition.render(bars=2, filename=str(_where / "ensemble.mid"))

	(_where / "played.json").write_text(json.dumps({
		"notes": sorted({tuple(one) for one in _notes}),
		"controls": sorted({tuple(one) for one in _controls}),
	}))
