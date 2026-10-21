"""The blank example: a GM kit, a bass and a poly, four pages, and nothing playing.

**Its subject is a composition that starts from nothing**, so the test that
matters most is that it makes no sound — asserted by rendering it through
Subsequence's own scheduler and counting the notes, because a composition that
seeds nothing is easy to write and easy to break later with one convenient
default.

**Run by CI against the Subsequence release named in its workflow**, as every
test here that imports `subsequence` is: the sequencer is a rig arrangement, and a
runner installs that release instead.
"""

import importlib.util
import json
import pathlib
import subprocess
import sys
import typing

import pytest

import pymididefs.cc
import pymididefs.drums


HERE = pathlib.Path(__file__).parent.parent
WHERE = HERE / "examples" / "blank.py"


def _composition () -> typing.Any:
	"""The example, imported once and shared.

	Importing it does not dial the service: the link connects when it is started,
	which only ``__main__`` does.
	"""

	if "blank" not in sys.modules:
		spec = importlib.util.spec_from_file_location("blank", str(WHERE))
		assert spec is not None and spec.loader is not None
		module = importlib.util.module_from_spec(spec)
		sys.modules["blank"] = module
		spec.loader.exec_module(module)

	return sys.modules["blank"]


@pytest.fixture (scope="module")
def rig () -> typing.Any:
	"""The example, loaded but not playing."""

	return _composition()


# --- What it comes up as -------------------------------------------------------

def test_it_comes_up_with_nothing_on_it (rig: typing.Any) -> None:
	"""**The whole point of this example**: three instruments and no opening
	patterns, connections or routes between them.

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

	**One map for every stack**, held rather than copied, which is what lets a line
	made on the glass be offered to all of them the moment it exists.
	"""

	for key, stack in rig.STACKS.items():
		assert not stack.declaration().get("sources"), f"{key} was offered something to route from"
		assert stack.sources is rig.SOURCES, f"{key} routes from a map of its own"


def test_every_instrument_listens_on_a_channel_of_its_own (rig: typing.Any) -> None:
	"""Two instruments on one channel both answer every note meant for either, and
	nothing on the glass says so."""

	channels = [one.channel for one in rig.INSTRUMENTS]

	assert len(set(channels)) == len(channels), f"two instruments share a channel: {channels}"


def test_the_kit_plays_general_midi_s_drum_notes_on_its_drum_channel (rig: typing.Any) -> None:
	"""A neutral kit: every row is named and played as General MIDI's percussion map
	has it, on channel 10, so any GM kit plays each sound on the note it expects."""

	drums = next(one for one in rig.INSTRUMENTS if one.drums)

	assert drums.channel == 10
	assert rig.GRIDS[drums.key].declaration()["rows"] == list(rig.DRUM_NOTES)

	for row, note in rig._note_map(drums).items():
		named = row if row in pymididefs.drums.GM_DRUM_MAP else f"{row}_1"

		assert pymididefs.drums.GM_DRUM_MAP[named] == note, f"{row} is not GM's note {note}"


def test_the_bass_is_a_monosynth_and_the_poly_plays_chords (rig: typing.Any) -> None:
	"""A monosynth handed two notes at once chooses between them by its own note
	priority, which the glass cannot see, so the bass's grid refuses a second note
	rather than showing two while one sounds."""

	assert rig.GRIDS["bass"].declaration()["voices"] == 1
	assert rig.GRIDS["poly"].declaration()["voices"] == 4


def test_a_synth_s_rows_are_its_register_highest_first (rig: typing.Any) -> None:
	"""Drawn the way a stave is, so a rising line rises, and played through a note
	map built from the same names, so a row and the note it plays cannot drift
	apart."""

	bass = next(one for one in rig.INSTRUMENTS if one.key == "bass")
	rows = rig._rows(bass)

	assert rows[0] == "C3" and rows[-1] == "C1" and len(rows) == 25
	assert rig._note_map(bass) == {row: note for row, note in zip(reversed(rows), range(24, 49))}


def test_the_settings_are_general_midi_s_sound_controllers (rig: typing.Any) -> None:
	"""Cutoff, resonance, attack and release on control changes 74, 71, 73 and 72,
	which many synths answer, each a number from 0 to 127 opening at the middle."""

	assert [(name, number) for name, number, _, _ in rig.SYNTH_SETTINGS] == [
		("cutoff", pymididefs.cc.FILTER_CUTOFF), ("resonance", pymididefs.cc.FILTER_RESONANCE),
		("attack", pymididefs.cc.ATTACK_TIME), ("release", pymididefs.cc.RELEASE_TIME)]

	fields = rig.SETTINGS["bass"].declaration()["fields"]

	assert [one["name"] for one in fields] == ["cutoff", "resonance", "attack", "release"]
	assert all(one["kind"] == "number" and one["min"] == 0 and one["max"] == 127
	           and one["default"] == 64 for one in fields), fields


def test_a_setting_is_sent_on_its_instrument_s_channel_at_once (rig: typing.Any) -> None:
	"""A setting is a control change on the instrument's channel, sent at the next
	pulse rather than at the next bar."""

	sent: list[dict[str, typing.Any]] = []
	trigger = rig.composition.trigger

	def kept (play: typing.Any, **asked: typing.Any) -> None:
		sent.append(asked)

	rig.composition.trigger = kept

	try:
		rig._send(next(one for one in rig.INSTRUMENTS if one.key == "poly"))("cutoff", 90)

	finally:
		rig.composition.trigger = trigger

	assert sent == [{"channel": rig.POLY_CHANNEL, "beats": 1 / 24, "quantize": 0}]


def test_an_instrument_with_no_settings_gets_no_settings_block (rig: typing.Any) -> None:
	"""**The panel loses a control rather than drawing a broken one**, so the kit
	gets a pattern and no block, and a block of no rows is worse than no block."""

	assert rig.SETTINGS["drums"] is None, "the kit was given a settings block with nothing in it"

	for key in ("bass", "poly"):
		assert rig.SETTINGS[key] is not None, f"{key} has settings and was given no block"


# --- Sets of pitches, made from the glass --------------------------------------

def test_it_offers_sets_of_pitches_and_starts_with_none (rig: typing.Any) -> None:
	"""The composition defines the *rack* and the person makes the sets, which is
	why it still comes up from nothing: a rack that has made nothing is a button,
	not a control holding music."""

	declared = rig.keyboards.declaration()

	assert declared["type"] == "rack"
	assert declared["makes"] == "pitch set"
	assert "min_steps" not in declared, "a set of pitches was offered a length"
	assert declared["rows"] == [], "a set of pitches was offered rows to choose"

	assert rig.keyboards.entries() == [], "it came up with a set already made"


def test_a_made_set_of_pitches_is_one_anything_may_read (rig: typing.Any) -> None:
	"""The rack holds a list, and the example turns one entry into a set of pitches
	over the eighty-eight keys, belonging to no instrument."""

	made = rig._make_keyboard({"id": "abc"})

	assert made.kind == "pitch_set"
	assert made.name == "keyboards-abc"
	assert len(made.pitches) == 88
	assert made.chosen == [], "a new set came up holding notes"


def test_a_set_of_pitches_may_be_patched_into_any_generator_that_wants_pitches (
	rig: typing.Any) -> None:
	"""One set feeding an arpeggio on the bass and another on the poly.  Checked
	against the protocol's own table, which is the one place what may be plugged
	into what is decided."""

	import superconductor.protocol

	made = rig._make_keyboard({"id": "abc"})
	arpeggio = next(
		one for one in rig.STACKS["bass"].declaration()["generators"]
		if one["name"] == "arpeggio")
	notes = next(one for one in arpeggio["parameters"] if one["name"] == "notes")

	wants = superconductor.protocol.PATCH_INPUTS[(notes["kind"], notes["role"])]

	assert made.kind in wants[0], \
		f"an arpeggio wants {wants[0]} and a set of pitches is a {made.kind}"


def test_a_set_of_pitches_is_called_so_on_the_glass_and_kept_as_keyboards (
	rig: typing.Any) -> None:
	"""**"Pitches" and "Degrees"**, a pair named for what each holds.  The store
	keeps sets under `keyboards`, the name both examples' stores share."""

	declared = rig.keyboards.declaration()

	assert declared["title"] == "Pitches" and declared["makes"] == "pitch set"
	assert rig.keyboards.name == "keyboards"
	assert rig._make_keyboard({"id": "xyz"}).title == "Pitches 1"


# --- The key, and degrees that follow it ----------------------------------------

def test_the_key_block_offers_a_root_and_subsequence_s_own_scales (rig: typing.Any) -> None:
	"""**One key for the whole piece**: a root and a scale, Subsequence's names,
	opening at C major so that a set of degrees made at once plays at once.

	**Every scale Subsequence offers, and none twice**: ``ionian`` is ``major`` and
	``aeolian`` is ``minor``.  **Compared by their notes** rather than by name, so a
	new spelling of a scale here passes by itself, and a new scale fails until the
	Key block offers it.
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
	"""The key the Key block holds is the composition's own, which Subsequence reads
	at every build, and every set of degrees made here is told."""

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

		assert told.asked == 2, "a set of degrees was not told the key moved, so no panel would be"
		assert (rig.composition.key, rig.composition.scale) == ("D", "dorian")
		assert made.notes() == [62, 65]
		assert made.snapshot()["key"] == "D dorian"
		assert [one["note"] for one in made.snapshot()["scale"]] == ["D", "E", "F", "G", "A", "B", "C"]

	finally:
		rig.key_block.apply(["root"], "C")
		rig.key_block.apply(["scale"], "major")
		rig._unmake_degrees(made.name)


def test_it_offers_degree_sets_and_starts_with_none (rig: typing.Any) -> None:
	"""Made from the glass beside the sets of pitches; three octaves, and a row as
	long as the longest scale on offer."""

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
			"a row of degrees is not as long as chromatic, the longest scale on offer"
		assert made.title == "Degrees 1"

	finally:
		rig._unmake_degrees(made.name)


def test_a_degree_set_patched_into_an_arpeggio_follows_the_key_it_is_played_in (
	tmp_path: pathlib.Path) -> None:
	"""One set of degrees, 1 3 5, patched into the bass's arpeggio and rendered
	through Subsequence in C major and then in D major: the same set plays C E G,
	then D F# A, with nothing patched again."""

	def classes (root: str) -> set[int]:
		played = _rendered(tmp_path / root, place=False, key=root)
		rig = _composition()
		channel = next(one.channel for one in rig.INSTRUMENTS if one.key == "bass") - 1

		return {note % 12 for on, note in played["notes"] if on == channel}

	assert classes("C") == {0, 4, 7}
	assert classes("D") == {2, 6, 9}


# --- Lines, made from the glass ------------------------------------------------

def test_it_offers_lines_and_starts_with_none (rig: typing.Any) -> None:
	"""A line made on the glass plays on every instrument it is routed into.  A rack
	that has made nothing is a button, and a line has every note MIDI has and plays
	at the length of whatever routed it, so there is nothing to choose and no length
	to set."""

	declared = rig.lines.declaration()

	assert declared["type"] == "rack"
	assert declared["makes"] == "line"
	assert "min_steps" not in declared, "a line was offered a length of its own"
	assert declared["rows"] == [], "a line was offered rows to choose"

	assert rig.lines.entries() == [], "it came up with a line already made"
	assert rig.SOURCES == {}, "it came up with something to route from"


def test_a_made_line_is_every_note_with_no_instrument_and_every_stack_may_take_it (
	rig: typing.Any) -> None:
	"""**A grid of notes belonging to no pattern**, drawn over the whole of MIDI and
	opening low.  Routable the moment it exists, from every stack, and withdrawn
	when it goes, or a stack goes on offering a cable to a line nobody can see."""

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


def _landed (rig: typing.Any, source: str, into: str, steps: int) -> list[tuple[float, int, float | None]]:
	"""What a routed source puts on a pattern of *steps* steps on instrument *into*."""

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
	"""**A pitch means itself**, so the same line is the same notes on the bass and
	the poly, each then transposed by its own grid.

	**And nothing past the end of the pattern it plays into**: Subsequence sounds a
	note placed past a pattern's length at the start of the next cycle rather than
	dropping it, so a line routed into a twelve-step pattern must lose its last four
	steps and cut a note that runs over, not play them into the bar after.  A note
	is cut in the copy played and kept whole on the line.
	"""

	made = rig._make_line({"id": "both"})
	per_step = rig.DIVISIONS

	try:
		made.apply(["C2", "0"], True)
		made.apply(["G2", str(10 * per_step)], True)
		made.apply(["G2", str(10 * per_step), "length"], 4 * per_step)
		made.apply(["E2", str(13 * per_step)], True)

		whole = _landed(rig, "lines-both", "bass", steps=16)
		short = _landed(rig, "lines-both", "poly", steps=12)

		assert [pitch for _, pitch, _ in whole] == [36, 43, 40], f"the bass heard {whole}"
		assert [pitch for _, pitch, _ in short] == [36, 43], f"the poly heard {short}"
		cut, uncut = short[1][2], whole[1][2]

		assert cut is not None and uncut is not None and cut < uncut, \
			"a note running past a twelve-step end was not cut"
		assert made.rows_now()["G2"][str(10 * per_step)]["length"] == 4 * per_step, \
			"cutting the copy shortened the note on the line"

	finally:
		rig._unmake_line("lines-both")


def test_the_racks_and_the_key_are_on_every_page_that_plays_notes (rig: typing.Any) -> None:
	"""A cable is dragged between two blocks, so a set or a line has to be on the
	page where the synth it feeds is, and the key is changed where the sets are."""

	pages = {page.declaration()["title"]: page.declaration()["parts"] for page in rig.link.pages}

	for named in ("Band", "Bass", "Poly"):
		for part in (rig.KEY, rig.KEYBOARDS, rig.DEGREES, rig.LINES):
			assert part in pages[named], f"{named} has no {part}"


# --- The glass -----------------------------------------------------------------

def test_every_page_names_something_this_composition_declares (rig: typing.Any) -> None:
	"""A page naming a control nobody declared draws an empty page and says nothing."""

	declared = set(rig.link.controls)

	for page in rig.link.pages:
		for part in page.declaration()["parts"]:
			assert part in declared, f"a page names {part!r}, which is not declared"


def test_the_pages_are_few_enough_to_be_named_on_the_glass (rig: typing.Any) -> None:
	"""The client draws named page buttons up to six and gives way to previous and
	next above that, which shows no page names at all."""

	assert len(rig.link.pages) <= 6, "there are more pages than the panel will name"


def test_every_instrument_is_on_the_first_page (rig: typing.Any) -> None:
	"""Band is everything, and the other pages take one instrument somewhere quieter."""

	band = next(page for page in rig.link.pages if page.declaration()["title"] == "Band")

	assert band.declaration()["parts"] == [one.key for one in rig.INSTRUMENTS] + [
		rig.KEY, rig.KEYBOARDS, rig.DEGREES, rig.LINES]


def test_a_settings_block_needs_no_page_of_its_own (rig: typing.Any) -> None:
	"""One that names the pattern it configures is drawn wherever that pattern is
	and put away behind its latch, so the pages name patterns and nothing else."""

	named = {part for page in rig.link.pages for part in page.declaration()["parts"]}
	settings = {f"{one.key}_settings" for one in rig.INSTRUMENTS}

	assert not (named & settings), f"a page named a settings block: {named & settings}"


def test_what_is_made_is_kept_beside_the_example (rig: typing.Any) -> None:
	"""A copy of this file keeps its own store next to itself, so two copies never
	put back each other's patterns."""

	assert rig.PATTERN_STORE.path == WHERE.with_suffix(".patterns.json")


# --- Played through Subsequence ------------------------------------------------

def test_it_plays_nothing_until_somebody_plays_it (tmp_path: pathlib.Path) -> None:
	"""**The one that cannot be talked out of**: rendered through Subsequence's own
	scheduler with nothing placed, counting what reached the port.

	**A child process**, because a render installs signal handlers and wants the
	main thread, and MIDI is patched there or it goes looking among real ports.
	"""

	played = _rendered(tmp_path, place=False)

	assert played["notes"] == [], f"an example that seeds nothing still played: {played['notes']}"
	assert played["controls"] == [], f"an example that seeds nothing still sent: {played['controls']}"


def test_one_line_routed_into_two_synths_plays_on_both (tmp_path: pathlib.Path) -> None:
	"""A line made on the glass with one note on it, a route to it on the bass's
	stack and on the poly's, and that note arriving on both channels and nowhere
	else."""

	played = _rendered(tmp_path, place=False, route=True)
	rig = _composition()
	channels = {one.key: one.channel - 1 for one in rig.INSTRUMENTS}

	assert sorted(played["notes"]) == sorted([[channels["bass"], 36], [channels["poly"], 36]]), \
		f"the line did not reach exactly the two synths it was routed into: {played['notes']}"


def test_a_note_on_every_instrument_reaches_its_own_channel (tmp_path: pathlib.Path) -> None:
	"""Once somebody puts a note on each grid, each one sounds where its instrument
	is listening.  Channels are counted from zero on the wire and from one in the
	example, which is the off-by-one worth one assertion."""

	played = _rendered(tmp_path, place=True)
	wire = {channel for channel, _ in played["notes"]}
	rig = _composition()

	assert wire == {one.channel - 1 for one in rig.INSTRUMENTS}, \
		f"a note did not reach its instrument: {sorted(wire)}"


def _rendered (where: pathlib.Path, place: bool, route: bool = False, key: str | None = None) -> dict[str, typing.Any]:
	"""Play the example in a child process and read back what reached the port.

	*route* makes a line holding one C2 and routes it into the bass and the poly.
	*key* sets that major key and patches a set of degrees holding 1, 3 and 5 into
	the bass's arpeggio.
	"""

	where.mkdir(parents=True, exist_ok=True)

	done = subprocess.run(
		[sys.executable, str(pathlib.Path(__file__)), str(where),
		 f"key:{key}" if key else "route" if route else "place" if place else "silent"],
		capture_output=True, text=True, timeout=180, check=False, cwd=str(HERE))

	assert done.returncode == 0, done.stderr[-4000:]

	return typing.cast(dict[str, typing.Any], json.loads((where / "played.json").read_text()))


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
	setattr(_mido, "get_output_names", lambda: ["A MIDI interface"])
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

		for _into in ("bass", "poly"):
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

		_rig.STACKS["bass"].apply(["layers"], [{
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
	_rig.composition.render(bars=2, filename=str(_where / "blank.mid"))

	(_where / "played.json").write_text(json.dumps({
		"notes": sorted({tuple(one) for one in _notes}),
		"controls": sorted({tuple(one) for one in _controls}),
	}))
