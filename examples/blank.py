"""A drum kit, a bass synth and a polysynth, with nothing playing until you play it.

**Start here.**  Copy this file somewhere of your own, change the names under
*Your instruments* to match what you have, and run it beside the Superconductor
service::

	python blank.py

Every pattern opens empty: no notes, no generators, no routes and no cables.
What the glass holds after the first minute is what you put there.  What you
make comes from racks on the glass: sets of pitches or of degrees to feed
generators, and lines to feed instruments.  `demo.py` beside this one shows
more of what the panel can do, with a pattern already playing.

**Everything about your studio lives in a file like this one**: which MIDI port
your instruments are on, which channel each listens on, and which notes each
grid is drawn over.  Superconductor itself knows none of it.

**One table, and the same loop run over each entry.**  `INSTRUMENTS` is the
whole of what this file plays.  Adding an instrument is a row in it, and taking
one out is deleting one.
"""

import collections.abc
import dataclasses
import pathlib
import typing

import pymididefs.cc

import subsequence
import subsequence.constants
import subsequence.constants.durations
import subsequence.constants.instruments.gm_drums
import subsequence.constants.midi_notes as midi_notes
import subsequence.intervals

import superconductor.subsequence_adapter as adapter


# --- Your instruments -----------------------------------------------------

MIDI_PORT: str | None = None
"""The MIDI output your instruments are on, or None to let Subsequence find it.

With None, Subsequence uses the only output there is, and asks which you meant
when there are several.  A name is matched as a pattern, with ``*`` for any run
of characters, so ``"*Scarlett*"`` finds a port without the rest of its name.
To list the names your system has::

	python -c "import mido; print(mido.get_output_names())"

An instrument on a port of its own says so on its pattern instead, with
``device=``.
"""

SERVICE_URL = "ws://127.0.0.1:8090/ws/app"
"""The Superconductor service, on this machine and its default port."""

DRUM_CHANNEL = 10
BASS_CHANNEL = 1
POLY_CHANNEL = 2
"""The channel each instrument listens on, counted from 1.

Ten is General MIDI's drum channel.  Set each to whatever your instrument
receives on: two instruments on one channel both answer every note.
"""

DRUM_NOTES = {
	name: subsequence.constants.instruments.gm_drums.GM_DRUM_MAP[name]
	for name in ("kick", "snare", "side_stick", "hand_clap", "hi_hat_closed",
	             "hi_hat_pedal", "hi_hat_open", "low_tom", "high_tom", "crash", "ride")
}
"""The kit's rows, top to bottom, and the note each one plays.

From General MIDI's percussion map, so a GM kit or sound module plays each sound
on the note it expects.  A drum machine with notes of its own is a dict of your
own here, ``{"kick": 36, "snare": 40}`` and so on.  A row's name is what the
glass shows beside it.
"""

SYNTH_SETTINGS = (
	# name         control change                    label        opens at
	("cutoff",     pymididefs.cc.FILTER_CUTOFF,     "Cutoff",     64),
	("resonance",  pymididefs.cc.FILTER_RESONANCE,  "Resonance",  64),
	("attack",     pymididefs.cc.ATTACK_TIME,       "Attack",     64),
	("release",    pymididefs.cc.RELEASE_TIME,      "Release",    64),
)
"""Four of General MIDI's sound controllers, which many synths answer.

Control changes 74, 71, 73 and 72, each from 0 to 127 and opening at the middle.
Your synth's manual lists what it answers: change a number here, or add a row,
and the glass draws it.  A synth that answers none of them wants an empty tuple,
and then it has no settings block at all.
"""


@dataclasses.dataclass (frozen=True)
class Instrument:
	"""One instrument: what the glass calls it, where it listens, and what its grid holds.

	``key`` is what the glass addresses and what the store keeps the instrument's
	patterns under, so choose it once: renaming one leaves whatever it held behind.

	``low`` and ``high`` are the notes a synth's grid is drawn over, both included.
	A drum kit has neither: its rows are ``DRUM_NOTES``.

	``voices`` is how many notes the grid lets sound at once: one for a monosynth,
	your polysynth's count for a polysynth, and None for as many as you like.

	``settings`` are the controls in the instrument's settings block, as ``(name,
	control change, label, opens at)``.
	"""

	key: str
	title: str
	channel: int
	low: str | None = None
	high: str | None = None
	voices: int | None = None
	settings: tuple[tuple[str, int, str, int], ...] = ()

	@property
	def drums (self) -> bool:
		"""Whether its rows are drum sounds rather than notes."""

		return self.low is None


INSTRUMENTS = (
	Instrument(key="drums", title="Drums", channel=DRUM_CHANNEL),
	Instrument(key="bass", title="Bass", channel=BASS_CHANNEL,
	           low="C1", high="C3", voices=1, settings=SYNTH_SETTINGS),
	Instrument(key="poly", title="Poly", channel=POLY_CHANNEL,
	           low="C3", high="C5", voices=4, settings=SYNTH_SETTINGS),
)
"""What this file plays, in the order the first page draws it.

The bass is a monosynth, so its grid lets one note sound at a time and refuses
a second, rather than leaving the synth to choose between two notes the glass
shows.  The poly lets four: set ``voices`` to the number yours plays.
"""


# --- Time, which every pattern here keeps ---------------------------------

STEPS = 16
BEATS = 4.0
STEP_DURATION = subsequence.constants.durations.SIXTEENTH
"""A bar of sixteenths, which is what every grid here counts in."""

DIVISIONS = 6
"""How many places a synth's grid keeps in a step, so a note can start between two.

Six, because a sixteenth is six pulses of the sequencer's 24-a-beat clock, and
a place finer than a pulse is one it cannot play.  A drum grid keeps one place
to a step: a hit lands on the step or it is on a different one.
"""

VELOCITY = 100
"""How hard a step is struck when it is first placed, and what a double tap puts it back to."""

HIT_DURATION = 1 / 24
"""A drum hit is a trigger rather than a held note, so it is one pulse long."""

NOTE_LENGTH = DIVISIONS
"""How long a synth's note is when it is first placed, in places: one step."""

VARIANTS = ("A", "B", "C", "D")
LANDS_EVERY = 1
"""Four versions of every pattern, a cued one starting at the end of the cycle playing.

The same four letters on every grid, which is what lets a scene be *cue B on
everything*.
"""

MIN_STEPS = 1
"""The fewest steps a pattern here may be made to play.

One, because a pattern must be at least as long as the time it is built ahead
of playing, which is one pulse here, and a step is six of them.
"""


def _resize (p: typing.Any, steps: int) -> None:
	"""Make the pattern being built *steps* of its own steps long."""

	p.set_length(steps=steps)


PATTERN_STORE = adapter.PatternStore.beside(__file__)
PAGE_STORE = adapter.PageStore(pathlib.Path(__file__).with_suffix(".pages.json"))
"""Where what you make on the glass is kept between starts: beside this file.

``blank.patterns.json`` holds every pattern, stack, setting and mute, and
``blank.pages.json`` where each block sits on each page.  Delete them, with this
stopped, to start again from nothing.  Give paths of your own to keep them
anywhere else.
"""


# --- The instruments' patterns --------------------------------------------

composition = subsequence.Composition(output_device=MIDI_PORT, bpm=120)

for _one in INSTRUMENTS:
	composition.data[_one.key] = {}


def _register (instrument: Instrument) -> list[str]:
	"""The notes a synth's grid is drawn over, lowest first."""

	assert instrument.low and instrument.high

	low = midi_notes.name_to_note(instrument.low)
	high = midi_notes.name_to_note(instrument.high)

	return [midi_notes.note_to_name(note) for note in range(low, high + 1)]


def _rows (instrument: Instrument) -> list[str]:
	"""What an instrument's grid has for rows, in the order they are drawn.

	A kit's are its sounds.  A synth's are its notes, **highest first**, so the
	grid reads the way a stave does and a rising line rises.
	"""

	if instrument.drums:
		return list(DRUM_NOTES)

	return list(reversed(_register(instrument)))


def _note_map (instrument: Instrument) -> dict[str, int]:
	"""Each row's name against the note it plays, for drums and synths alike.

	Subsequence plays a row's name through whatever map its pattern is given, and
	nothing about that map has to be about drums.
	"""

	if instrument.drums:
		return dict(DRUM_NOTES)

	return {row: midi_notes.name_to_note(row) for row in _register(instrument)}


def _places (steps: int) -> adapter.Positions:
	"""Every place a note may start in a pattern this long, and what each is called.

	**The same places twice**, because a generator asks for a place either in
	steps (0 to 15) or in beats (0 to 3.75), and says which.  The words are a
	musician's: counted from one, with the places inside a beat after it, so the
	second sixteenth is *1.2*.
	"""

	subdivisions = max(1, round(1 / STEP_DURATION))

	def counted (at: int) -> str:
		"""Which beat, and where inside it."""

		beat, inside = divmod(at, subdivisions)

		return f"{beat + 1}" if inside == 0 else f"{beat + 1}.{inside + 1}"

	return {
		"steps": [(at, str(at + 1)) for at in range(steps)],
		"beats": [(at * STEP_DURATION, counted(at)) for at in range(steps)],
	}


SOURCES: dict[str, collections.abc.Callable[[typing.Any], None]] = {}
"""What any stack here may route from, and how to play each: one map shared by all of them.

**Empty at the start**, so no stack offers a route until there is something to
route from.  A line made on the glass adds itself (`_make_line`) and a line
taken away removes itself, and because every stack holds this map rather than
a copy of it, each offers a new line the moment it exists.
"""


def _stack_for (instrument: Instrument) -> typing.Any:
	"""The stack of generators and transforms that builds an instrument's pattern.

	Subsequence describes its generators and transforms, and this file says which
	pitches the pattern has: a kit's sounds or a synth's notes.  The bounds keep
	each generator's numbers to what this pattern can play.
	"""

	return adapter.Recipe(
		composition,
		catalogue=subsequence.generators(),
		transforms=subsequence.transforms(),
		pitches=_rows(instrument),
		pitch_notes=None if instrument.drums else _note_map(instrument),
		positions=_places(STEPS),
		bounds={
			"pulses": (0, STEPS),

			# **Named with its unit**, because `grid` means *how many slots* on
			# most generators and *a grid size in beats* on `swing`.
			("grid", "steps"): (1, STEPS),
			"subdivisions": (1, 8),
			"duration": (0.05, BEATS),

			# A ceiling on cost rather than on music: a stack builds on the
			# sequencer's clock, and a slow build makes a late bar.
			"steps": (100, 5000),
		},
		builds=instrument.key,
		sources=SOURCES,
		pulses_per_beat=subsequence.constants.MIDI_QUARTER_NOTE,
		data_key=f"{instrument.key}_recipe",
		name=f"{instrument.key}_recipe",
		title=f"{instrument.title} — stack")


def _grid_for (instrument: Instrument) -> typing.Any:
	"""The grid an instrument is played from: sounds for a kit, notes for a synth."""

	shared: dict[str, typing.Any] = {
		"composition": composition, "rows": _rows(instrument), "steps": STEPS, "beats": BEATS,
		"data_key": instrument.key, "name": instrument.key, "pattern": instrument.key,
		"title": instrument.title, "about": [("ch", instrument.channel)],
		"variants": VARIANTS, "lands_every": LANDS_EVERY,
		"default_velocity": VELOCITY, "min_steps": MIN_STEPS, "resize": _resize,
	}

	if instrument.drums:
		return adapter.StepGrid(**shared)

	return adapter.NoteGrid(
		**shared, divisions=DIVISIONS, default_length=NOTE_LENGTH, voices=instrument.voices)


GRIDS = {one.key: _grid_for(one) for one in INSTRUMENTS}
STACKS = {one.key: _stack_for(one) for one in INSTRUMENTS}


def _send (instrument: Instrument) -> collections.abc.Callable[[str, typing.Any], None]:
	"""How an instrument's settings block sends one setting.

	Sent at the next pulse rather than at the next bar, so a change is heard at
	once.  ``trigger`` is also the safe way into the sequencer's clock from
	another thread.  A setting moved before the composition is playing is kept,
	and sent once it is.
	"""

	numbers = {name: number for name, number, _, _ in instrument.settings}

	def send (name: str, value: typing.Any) -> None:
		number = numbers.get(name)

		if number is None:
			return

		composition.trigger(
			lambda p, control=number, level=int(value): p.cc(control, level),
			channel=instrument.channel, beats=1 / 24, quantize=0)

	return send


def _settings_for (instrument: Instrument) -> typing.Any | None:
	"""An instrument's settings block, or None where it has no settings.

	A block of no rows is worse than no block, so an instrument given no settings
	gets a pattern and nothing else.
	"""

	if not instrument.settings:
		return None

	return adapter.Params(
		composition,
		parameters=[
			adapter.Parameter(name, "number", label=label, default=opens_at,
			                  minimum=0, maximum=127)
			for name, _, label, opens_at in instrument.settings],
		data_key=f"{instrument.key}_settings",
		name=f"{instrument.key}_settings",
		title=f"{instrument.title} — settings",
		about=[("ch", instrument.channel)],
		configures=instrument.key,
		on_change=_send(instrument))


SETTINGS = {one.key: _settings_for(one) for one in INSTRUMENTS}


def _register_pattern (instrument: Instrument) -> None:
	"""Give an instrument a pattern that plays whatever its grid and its stack hold.

	**A drum hit is a trigger and a note is held**, which is the only difference
	between the two halves below: a hit is one pulse long, and a note has the
	length and velocity it was given.

	**The stack builds after the grid**, so a generator told to skip a step that
	already sounds can see what was tapped.  **The pattern is transposed last**,
	after everything has been placed, so every row's label says what it plays.
	"""

	grid = GRIDS[instrument.key]
	stack = STACKS[instrument.key]
	notes = _note_map(instrument)
	drums = instrument.drums

	def play (p: typing.Any) -> None:
		"""Play what the grid holds this cycle, then the stack, then the transposition."""

		if drums:
			for row, steps in grid.now(p).items():
				for step, hit in steps.items():
					p.note(pitch=notes[row], beat=int(step) * STEP_DURATION,
					       velocity=hit.get("velocity", VELOCITY), duration=HIT_DURATION)

		else:
			per_place = STEP_DURATION / DIVISIONS

			for row, placed in grid.now(p).items():
				for at, note in placed.items():
					p.note(pitch=notes[row], beat=int(at) * per_place,
					       velocity=note.get("velocity", VELOCITY),
					       duration=note.get("length", NOTE_LENGTH) * per_place)

		stack.build(p)

		# Only a synth is transposed: a drum row is a sound, and moving a kick up
		# three semitones would be a different drum.
		if not drums and grid.transpose:
			p.transpose(grid.transpose)

	# A pattern is known by the name of the function that builds it, and the grid
	# names the same one as its `pattern`.
	play.__name__ = instrument.key
	play.__qualname__ = instrument.key

	# Built one pulse before each cycle rather than a beat before it, so a tap is
	# heard at most a pulse later.
	composition.pattern(
		channel=instrument.channel,
		steps=STEPS,
		step_duration=STEP_DURATION,
		drum_note_map=notes,
		reschedule_lookahead=1 / 24,
	)(play)


for _one in INSTRUMENTS:
	_register_pattern(_one)


# --- Sets of pitches, made from the glass ---------------------------------

KEYS = [midi_notes.note_to_name(note)
        for note in range(midi_notes.name_to_note("A0"), midi_notes.name_to_note("C8") + 1)]
"""A piano's eighty-eight keys, belonging to no instrument.

A set of pitches is patched into whatever generator wants notes, on any
instrument, and each folds what it is given into its own register.  So the set
can be as wide as a piano and cost nothing downstream.
"""

KEYBOARDS = "keyboards"


def _make_keyboard (spec: dict[str, typing.Any]) -> typing.Any:
	"""Turn one set of pitches asked for on the glass into a set anything may read.

	Numbered by where it sits, because nothing on the glass asks you to type: two
	sets are told apart by their number and by what is chosen on them.
	"""

	key = str(spec["id"])
	held = (composition.data.get(KEYBOARDS) or {}).get("made") or []
	at = next((n for n, one in enumerate(held) if one["id"] == key), len(held))

	return adapter.PitchSet(
		composition,
		name=f"{KEYBOARDS}-{key}",
		title=f"Pitches {at + 1}",
		pitches={row: midi_notes.name_to_note(row) for row in KEYS},
		about=[("", "no instrument")],
		opens_at="C3")


keyboards = adapter.Rack(
	composition,
	make=_make_keyboard,

	# Nothing to choose and no length to set, so making one is a single press:
	# which notes a set holds is chosen on its keyboard afterwards.
	steps=None,
	makes="pitch set",
	data_key=KEYBOARDS,
	name=KEYBOARDS,
	title="Pitches",
	about=[("", "patch into any generator")])
"""Sets of pitches made from the glass, as many as the music wants.

One set can feed an arpeggio on the bass and another on the poly, and the two
cannot drift apart because there is only one of it.
"""


# --- The key, and sets of degrees that follow it --------------------------

ROOTS = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
"""The twelve roots a key may have, spelt as Subsequence reads them."""

SCALES = ("major", "minor", "dorian", "phrygian", "lydian", "mixolydian", "locrian",
          "harmonic_minor", "melodic_minor", "major_pentatonic", "minor_pentatonic",
          "blues_scale", "hirajoshi", "in_sen", "iwato", "yo", "egyptian",
          "lydian_dominant", "superlocrian", "whole_tone", "augmented",
          "phrygian_dominant", "hungarian_minor", "double_harmonic", "neapolitan_major",
          "enigmatic", "chromatic")
"""Subsequence's scales, in the order a musician reaches for them, each named once."""

KEY = "key"


def _rekey (name: str, value: typing.Any) -> None:
	"""Make the Key block's key the composition's, and tell every set of degrees.

	The composition's own key is what Subsequence builds every pattern in, so what
	the glass says and what plays are one fact.
	"""

	held = composition.data.get(KEY) or {}
	composition.key = held.get("root")
	composition.scale = held.get("scale")

	for one in list(DEGREE_SETS.values()):
		one.rekeyed()


key_block = adapter.Params(
	composition,
	parameters=[
		adapter.Parameter("root", "choice", label="root", default="C",
		                  options=[(root, root) for root in ROOTS]),
		adapter.Parameter("scale", "choice", label="scale", default="major",
		                  options=[(scale, scale.replace("_", " ")) for scale in SCALES]),
	],
	data_key=KEY,
	name=KEY,
	title="Key",
	about=[("", "every set of degrees follows it")],
	on_change=_rekey)
"""One key for the whole piece, kept with the patterns, and opening at C major."""

composition.key = composition.data[KEY]["root"]
composition.scale = composition.data[KEY]["scale"]


def _key_now () -> tuple[str, list[int]] | None:
	"""The key as a set of degrees asks for it: its name, and one octave of its scale.

	Read from the Key block's own values, so a key kept from the last run is right
	from the first cycle.  The octave starts at the tonic's fourth octave, around
	middle C; a stack folds whatever it is given into its own instrument's register.
	"""

	held = composition.data.get(KEY) or {}
	root, scale = held.get("root"), held.get("scale")

	if root not in ROOTS or scale not in SCALES:
		return None

	classes = subsequence.intervals.scale_pitch_classes(0, str(scale))
	tonic = midi_notes.name_to_note(f"{root}4")

	return f"{root} {str(scale).replace('_', ' ')}", [tonic + (one - classes[0]) % 12 for one in classes]


def _note_name (note: int) -> str:
	"""A note's name without its octave, which is what a degree's button says."""

	return str(midi_notes.note_to_name(note)).rstrip("-0123456789")


MOST_STEPS = max(len(subsequence.intervals.scale_pitch_classes(0, scale)) for scale in SCALES)
"""The longest scale on offer, which is how long a row of degrees may be."""

DEGREES = "degrees"

DEGREE_SETS: dict[str, adapter.DegreeSet] = {}
"""Every set of degrees made here, so a change of key can tell each of them."""


def _make_degrees (spec: dict[str, typing.Any]) -> adapter.DegreeSet:
	"""Turn one set of degrees asked for on the glass into a set that follows the key."""

	number = str(spec["id"])
	key = f"{DEGREES}-{number}"
	held = (composition.data.get(DEGREES) or {}).get("made") or []
	at = next((n for n, one in enumerate(held) if one["id"] == number), len(held))

	made = adapter.DegreeSet(
		composition, key=_key_now, named=_note_name, name=key, title=f"Degrees {at + 1}",
		about=[("", "follows the key")], octaves=(-1, 0, 1), steps=MOST_STEPS)

	DEGREE_SETS[key] = made

	return made


def _unmake_degrees (name: str) -> None:
	"""Stop telling a set that has gone about the key."""

	DEGREE_SETS.pop(name, None)


degrees = adapter.Rack(
	composition,
	make=_make_degrees,
	unmake=_unmake_degrees,
	steps=None,
	makes="degree set",
	data_key=DEGREES,
	name=DEGREES,
	title="Degrees",
	about=[("", "patch into any generator; follows the key")])
"""Sets of degrees made from the glass, patched wherever pitches are wanted.

Written as degrees of the key rather than as notes, so changing the key moves
every part a set feeds, with nothing patched again.
"""


# --- Lines, made from the glass -------------------------------------------

LINE_ROWS = [midi_notes.note_to_name(note) for note in range(127, -1, -1)]
"""Every note MIDI has, highest first, because a line belongs to no instrument.

A line sounds as whatever it is routed into, so it is drawn over all of MIDI
rather than one instrument's register, a window of it at a time.
"""

LINE_NOTES = {row: midi_notes.name_to_note(row) for row in LINE_ROWS}
"""Each row's name against the note it plays."""

LINE_OPENS_AT = "C2"
"""Where a line's window opens: low, because a line is often a bassline."""

LINES = "lines"


def _make_line (spec: dict[str, typing.Any]) -> typing.Any:
	"""Turn one line asked for on the glass into a grid of notes any stack may route from.

	**A pitch means itself**, so the same line plays the same notes on every
	instrument it is routed into, and each instrument's own grid then transposes
	what it plays.

	**Nothing past the end of the pattern it plays into.**  A line has no length
	of its own and plays at the length of whatever routed it, so a note past that
	end is left out and a note running over is cut short, in what is played and
	never on the line.
	"""

	number = str(spec["id"])
	key = f"{LINES}-{number}"
	held = (composition.data.get(LINES) or {}).get("made") or []
	at = next((n for n, one in enumerate(held) if one["id"] == number), len(held))

	line = adapter.NoteGrid(
		composition, rows=LINE_ROWS, steps=STEPS, beats=BEATS,
		data_key=key, name=key, title=f"Line {at + 1}",
		divisions=DIVISIONS, default_length=NOTE_LENGTH, default_velocity=VELOCITY,
		visible_rows=12, opens_at=LINE_OPENS_AT,
		about=[("", "no instrument")])

	per_place = STEP_DURATION / DIVISIONS

	def play (p: typing.Any) -> None:
		"""Put this line's notes onto whatever routed it, and nothing past that pattern's end."""

		ends = getattr(p, "grid", None)
		last = None if ends is None else ends * DIVISIONS

		for row, notes in line.now(p).items():
			for placed, note in notes.items():
				begins = int(placed)

				if last is not None and begins >= last:
					continue

				length = note.get("length", NOTE_LENGTH)

				if last is not None:
					length = min(length, last - begins)

				p.note(LINE_NOTES[row], beat=begins * per_place,
				       velocity=note.get("velocity", VELOCITY), duration=length * per_place)

	# Routable the moment it exists: every stack reads `SOURCES` when it declares,
	# and the rack asks for a declaration as soon as it has made this.
	SOURCES[key] = play

	return line


def _unmake_line (name: str) -> None:
	"""Stop offering a line that has gone as something to route from."""

	SOURCES.pop(name, None)


lines = adapter.Rack(
	composition,
	make=_make_line,
	unmake=_unmake_line,

	# Nothing to choose and no length to set: a line holds every note MIDI has, and
	# plays at the length of whatever it is routed into.
	steps=None,
	makes="line",
	data_key=LINES,
	name=LINES,
	title="Lines",
	about=[("", "route into any instrument")])
"""Lines made from the glass, each one playing on every instrument it is routed into.

Route one line into the bass and the poly, and each goes on adding notes of its own.
"""


# --- The glass ------------------------------------------------------------

link = adapter.AppLink(
	composition,
	controls=[
		*GRIDS.values(),
		*STACKS.values(),
		*(one for one in SETTINGS.values() if one is not None),
		key_block,
		keyboards,
		degrees,
		lines,
		adapter.Transport(composition),
	],
	pages=[
		adapter.Page("band", parts=[one.key for one in INSTRUMENTS] + [KEY, KEYBOARDS, DEGREES, LINES],
		             title="Band"),
		adapter.Page("drums", parts=["drums"], title="Drums"),
		adapter.Page("bass", parts=["bass", KEY, KEYBOARDS, DEGREES, LINES], title="Bass"),
		adapter.Page("poly", parts=["poly", KEY, KEYBOARDS, DEGREES, LINES], title="Poly"),
	],
	page_store=PAGE_STORE,
	pattern_store=PATTERN_STORE,
	url=SERVICE_URL,
)
"""Four pages, and where what is made on them is kept.

**Band is everything, and the other three are where the work happens**: see the
whole of it, then take one instrument somewhere quieter.  A settings block and a
stack need no place on a page: each is drawn wherever the pattern it belongs to
is.

**After your first edit on the glass, this file is not the score.**  Every
pattern, stack, setting and mute is put back from the store each time this
starts, and because nothing here is seeded, an empty store comes up empty.
"""


if __name__ == "__main__":
	link.start()

	# `play()` returns on Ctrl-C and on a polite kill alike, and `stop` writes down
	# whatever the store had not yet.
	try:
		composition.play()

	finally:
		link.stop()
