"""A drum kit, a bass synth and a polysynth, with a pattern already playing.

**What the panel can do, shown working.**  Run it beside the Superconductor
service and open the page::

	python demo.py

A General MIDI kit plays a bar of sixteenths from the first beat, and a tap on
the glass changes it.  Around it are the things the glass offers beyond a grid
of steps:

- **variants**: four versions of each of the kit, the bass and the poly, a
  cued one starting at the end of the bar;
- **a polyrhythm**: a nine-step pattern on the same kit, running against the
  sixteen;
- **grids with no instrument**: a drum grid and a one-row snare lane that play
  on whatever they are routed into, and a line of notes either synth can take;
- **generators**: a stack on every pattern, adding notes to what was tapped;
- **a set of pitches**, patched into any generator that wants notes;
- **instruments**: the kit and each synth on the glass, a cable from every
  pattern that plays it, and its settings on it, sent as control changes.

`blank.py` beside this one is the same three instruments with nothing playing,
and is the better file to start your own from.  **Everything about your studio
lives in a file like this**: change the names under *Your instruments* to match
what you have.
"""

import collections.abc
import pathlib
import typing

import pymididefs.cc

import subsequence
import subsequence.constants
import subsequence.constants.durations
import subsequence.constants.instruments.gm_drums
import subsequence.constants.midi_notes as midi_notes

import superconductor.subsequence_adapter as adapter


# --- Your instruments -----------------------------------------------------

MIDI_PORT: str | None = None
"""The MIDI output your instruments are on, or None to let Subsequence find it.

With None, Subsequence uses the only output there is, and asks which you meant
when there are several.  A name is matched as a pattern, with ``*`` for any run
of characters, so ``"*Scarlett*"`` finds a port without the rest of its name.
"""

SERVICE_URL = "ws://127.0.0.1:8090/ws/app"
"""The Superconductor service, on this machine and its default port."""

DRUM_CHANNEL = 10
BASS_CHANNEL = 1
POLY_CHANNEL = 2
"""The channel each instrument listens on, counted from 1.  Ten is General MIDI's drums."""

DRUM_NOTES = {
	name: subsequence.constants.instruments.gm_drums.GM_DRUM_MAP[name]
	for name in ("kick", "snare", "side_stick", "hand_clap", "hi_hat_closed",
	             "hi_hat_pedal", "hi_hat_open", "low_tom", "high_tom", "crash", "ride")
}
"""The kit's rows, top to bottom, and the note each one plays.

From General MIDI's percussion map, so a GM kit plays each sound on the note it
expects.  A drum machine with notes of its own is a dict of your own here.
"""

ROWS = list(DRUM_NOTES)
"""The kit's rows, which every drum grid here shares: the kit, the nine and the lanes."""

BASS_RANGE = [midi_notes.note_to_name(note)
              for note in range(midi_notes.name_to_note("C1"), midi_notes.name_to_note("C3") + 1)]
"""The notes the bass grid is drawn over: two chromatic octaves, C1 to C3.

One row a note, so a line is read as a shape and an octave leap looks like one.
A different range, or only the notes of a scale, is an edit here and nowhere else.
"""

BASS_VOICES = 1
"""A monosynth: the grid lets one note sound at a time, and refuses a second.

A monosynth handed two notes at once chooses between them by its own note
priority, which the glass cannot see, so the glass would show two notes while
one sounded.
"""

POLY_RANGE = [midi_notes.note_to_name(note)
              for note in range(midi_notes.name_to_note("C3"), midi_notes.name_to_note("C5") + 1)]
"""The notes the poly grid is drawn over: C3 to C5, above the bass rather than across it."""

POLY_VOICES = 4
"""How many notes your polysynth plays at once, which is as many as its grid lets sound."""

BASS_SETTINGS: list[tuple[str, int, str, typing.Any, str | None]] = [
	# name          control change                       label          opens at  section
	("glide",       pymididefs.cc.PORTAMENTO_ON_OFF,     "Glide",       False,    None),
	("glide_time",  pymididefs.cc.PORTAMENTO_TIME,       "Glide time",  24,       None),
	("cutoff",      pymididefs.cc.FILTER_CUTOFF,         "Cutoff",      64,       None),
	("resonance",   pymididefs.cc.FILTER_RESONANCE,      "Resonance",   64,       None),
]
"""The bass's settings: a switch and three numbers, as a short list with no headings.

**A kind is told by what a setting opens at**: True or False is a switch, sent
as 127 or 0, and a number is dragged between 0 and 127.  Glide is MIDI's
portamento switch and time, which many monosynths answer.  Change a number to
whatever your synth's manual says it answers.
"""

POLY_SETTINGS: list[tuple[str, int, str, typing.Any, str | None]] = [
	("cutoff",      pymididefs.cc.FILTER_CUTOFF,         "Cutoff",      64,       "Filter"),
	("resonance",   pymididefs.cc.FILTER_RESONANCE,      "Resonance",   64,       "Filter"),
	("attack",      pymididefs.cc.ATTACK_TIME,           "Attack",      64,       "Envelope"),
	("release",     pymididefs.cc.RELEASE_TIME,          "Release",     64,       "Envelope"),
	("chorus",      pymididefs.cc.CHORUS_DEPTH,          "Chorus",      0,        "Effects"),
	("reverb",      pymididefs.cc.REVERB_DEPTH,          "Reverb",      40,       "Effects"),
]
"""The poly's settings, in sections, as an instrument's front panel groups them.

A section is a heading drawn above its settings, in the order given here.  A
short list reads without one; a long one is unreadable without.
"""


# --- Time ------------------------------------------------------------------

STEPS = 16
STEP_DURATION = subsequence.constants.durations.SIXTEENTH
BEATS = STEPS * STEP_DURATION
"""Sixteen sixteenths, which is one bar of four beats."""

NINE_STEPS = 9
NINE_BEATS = NINE_STEPS * STEP_DURATION
"""Nine sixteenths, which is 2.25 beats: the nine-step pattern's whole cycle.

**A polyrhythm is two patterns of different lengths** on one instrument, which
is how Subsequence does it: nine steps looping against sixteen, coming round
together every nine bars.  Not a grid routed into the kit, which would play at
the kit's length and be a bar cut short.
"""

VELOCITY = 100
"""How hard a drum step is struck when it is first placed, and what a double tap puts it back to."""

HIT_DURATION = 1 / 24
"""A drum hit is a trigger rather than a held note, so it is one pulse long."""

BASS_DIVISIONS = int(subsequence.constants.MIDI_QUARTER_NOTE * STEP_DURATION)
"""How many places a bass note may start at within one step: six, one a pulse.

The sequencer's clock runs at 24 pulses a beat and a step is a sixteenth, so a
step holds six of them, and a finer place is one no note could be played at.
"""

BASS_LENGTH = BASS_DIVISIONS
"""How long a bass note is when it is first placed, counted in those places: one step."""

BASS_VELOCITY = 100
POLY_VELOCITY = 100
"""How hard a synth's note is played when it is first placed."""

POLY_LENGTH = 2
"""How long a poly note is when it is first placed, in steps.

**The poly keeps one place a step**, where the bass keeps six: a chord wants to
land on a step rather than between two.  Two steps long, because a chord held
for a sixteenth is a stab.
"""

VARIANTS = ("A", "B", "C", "D")
"""The versions of a pattern you can switch between while it plays.

**The same four on the kit, the bass and the poly**, which is what lets a scene
be *cue B on every grid*.  A grid given none, like the lanes and the nine, is a
single pattern.
"""

LANDS_EVERY = 1
"""How many cycles a cued variant waits for: here, to the end of the one playing."""

MIN_STEPS = 1
"""The fewest steps a pattern here may be made to play.

One, because a pattern must be at least as long as the time it is built ahead
of playing, which is one pulse here, and a step is six of them.
"""


def _resize (p: typing.Any, steps: int) -> None:
	"""Make the pattern being built *steps* of its own steps long."""

	p.set_length(steps=steps)


# --- Notes and their names -------------------------------------------------

BASS_ROWS = list(reversed(BASS_RANGE))
POLY_ROWS = list(reversed(POLY_RANGE))
"""The same notes in the order they are drawn: highest first, the way a stave reads."""

BASS_NOTE_MAP = {row: midi_notes.name_to_note(row) for row in BASS_RANGE}
POLY_NOTE_MAP = {row: midi_notes.name_to_note(row) for row in POLY_RANGE}
"""Each row's name against the note it plays.

Subsequence plays a row's name through whatever map its pattern is given, the
same way a drum map works, and nothing about that map has to be about drums.
"""

SHARED_RANGE = [midi_notes.note_to_name(note) for note in range(0, 128)]
SHARED_ROWS = list(reversed(SHARED_RANGE))
SHARED_NOTE_MAP = {row: midi_notes.name_to_note(row) for row in SHARED_RANGE}
"""Every note MIDI has, for the line of notes that belongs to no instrument.

**An instrument's grid is drawn over the notes it is played in.**  A line with no
instrument sounds as whatever it is routed into, so it holds every note and
lets the routing decide.
"""

SHARED_OPENS_AT = "C1"
"""Where the shared line's window opens: at the bass's register, rather than at C-1."""

NOTES_RANGE = [midi_notes.note_to_name(note)
               for note in range(midi_notes.name_to_note("A0"), midi_notes.name_to_note("C8") + 1)]
"""A piano's eighty-eight keys, for the set of pitches, which belongs to no instrument.

Each generator it feeds folds what it is given into its own instrument's register,
so the set can be as wide as a piano.
"""

NOTES_OPEN_AT = "C2"
"""Where the set's keyboard opens: an octave between the bass and the poly."""


def _sounding (row: str, semitones: int, notes: dict[str, int]) -> int | None:
	"""The note *row* plays when its pattern is transposed by *semitones*, or None past MIDI's ends."""

	note = notes[row] + semitones

	if not 0 <= note <= 127:
		return None

	return note


def _relabel (notes: dict[str, int]) -> collections.abc.Callable[[str, int], str | None]:
	"""What each row of a transposed grid says, so its label names what it plays.

	**Only this file can answer it**: that a row called ``C2`` is a note, and that
	two semitones up is ``D2``.  None says the row cannot sound at all, past the
	ends of MIDI.  A synth whose manual gives a narrower range could say so here,
	and a row past it would say so on the glass rather than going quietly silent.
	"""

	def named (row: str, semitones: int) -> str | None:
		"""The name of the note *row* plays at *semitones*."""

		note = _sounding(row, semitones, notes)

		return None if note is None else str(midi_notes.note_to_name(note))

	return named


# --- The opening pattern ---------------------------------------------------

OPENING_PATTERN = {
	"kick": [0, 6, 8, 14],
	"snare": [4, 12],
	"hi_hat_closed": [0, 2, 4, 6, 8, 10, 12, 14],
	"hi_hat_open": [7, 15],
	"hand_clap": [12],
}
"""Something to hear on the first bar, and something to see on the glass.

It is variant A's.  The other three open empty, and a tap starts one from A.
Every row not named here starts empty.
"""


composition = subsequence.Composition(output_device=MIDI_PORT, bpm=120)

composition.data["drums"] = {"A": {"rows": {
	row: {str(step): {"velocity": VELOCITY} for step in OPENING_PATTERN.get(row, [])}
	for row in ROWS}}}


# --- The instruments, and their settings ------------------------------------

def _parameter (name: str, number: int, label: str, opens_at: typing.Any,
                group: str | None) -> adapter.Parameter:
	"""One setting as the glass draws it: a switch where it opens at True or False, else a number."""

	if isinstance(opens_at, bool):
		return adapter.Parameter(name, "switch", label=label, default=opens_at, group=group)

	return adapter.Parameter(name, "number", label=label, default=opens_at, group=group,
	                         minimum=0, maximum=127)


def _sender (channel: int, table: list[tuple[str, int, str, typing.Any, str | None]],
             ) -> collections.abc.Callable[[str, typing.Any], None]:
	"""How one instrument sends one of its settings, on its own channel.

	Sent at the next pulse rather than at the next bar, so a change is heard at
	once.  ``trigger`` is also the safe way into the sequencer's clock from another
	thread.  A setting moved before the composition is playing is kept, and sent
	once it is.
	"""

	numbers = {name: number for name, number, _, _, _ in table}

	def send (name: str, value: typing.Any) -> None:
		"""Send one setting, a switch as 127 or 0 and a number as itself."""

		number = numbers.get(name)

		if number is None:
			return

		level = (127 if value else 0) if isinstance(value, bool) else int(value)

		composition.trigger(
			lambda p, control=number, amount=level: p.cc(control, amount),
			channel=channel, beats=1 / 24, quantize=0)

	return send


def _instrument (key: str, title: str, channel: int,
                 table: list[tuple[str, int, str, typing.Any, str | None]]) -> adapter.Instrument:
	"""An instrument on the glass, drawn wherever a pattern playing it is, with its settings on it.

	Its settings were a block of their own called ``…_settings``, so it takes back what
	was kept under that name.
	"""

	return adapter.Instrument(
		composition,
		name=f"{key}_instrument",
		parameters=[_parameter(*setting) for setting in table],
		data_key=f"{key}_settings", title=title,
		about=[("ch", channel)],
		on_change=_sender(channel, table) if table else None,
		formerly=[f"{key}_settings"])


kit = _instrument("kit", "General MIDI kit", DRUM_CHANNEL, [])
bass_synth = _instrument("bass", "Monosynth", BASS_CHANNEL, BASS_SETTINGS)
poly_synth = _instrument("poly", "Polysynth", POLY_CHANNEL, POLY_SETTINGS)
"""What the patterns play.  The kit has nothing to set, and is still what two of them play."""


# --- The patterns ------------------------------------------------------------

@composition.pattern(
	channel=DRUM_CHANNEL,
	steps=STEPS,
	step_duration=STEP_DURATION,
	drum_note_map=DRUM_NOTES,
	reschedule_lookahead=1 / 24,
)
def drums (p: typing.Any) -> None:
	"""Play whatever the kit's grid holds when this bar is built, then its stack.

	Built one pulse before each cycle rather than a beat before it, so a tap is
	heard at most a pulse later, about 20 ms at 120 BPM.
	"""

	# Asked of the grid at the build, because the build is when a cued variant
	# starts to play.
	_play(p, drum_grid.now(p))
	drum_recipe.build(p)


@composition.pattern(
	channel=DRUM_CHANNEL,
	steps=NINE_STEPS,
	step_duration=STEP_DURATION,
	drum_note_map=DRUM_NOTES,
	reschedule_lookahead=1 / 24,
)
def nine (p: typing.Any) -> None:
	"""The same kit, in a cycle nine steps long, drifting against the sixteen.

	It opens empty on purpose: the two playheads part company whether or not there
	is a note under them, so the polyrhythm is visible before anything is drawn.
	"""

	_play(p, nine_grid.now(p))
	nine_recipe.build(p)


@composition.pattern(
	channel=BASS_CHANNEL,
	steps=STEPS,
	step_duration=STEP_DURATION,
	drum_note_map=BASS_NOTE_MAP,
	reschedule_lookahead=1 / 24,
)
def bass (p: typing.Any) -> None:
	"""Play the bass grid's notes, each at its own place, length and velocity.

	**Placed by beat rather than by step**, because this grid divides a step six
	ways.  The whole pattern is transposed last, after the stack, so what a
	generator adds moves with what was tapped and every row's label stays true.
	"""

	per_place = STEP_DURATION / BASS_DIVISIONS

	for row, notes in bass_grid.now(p).items():
		for at, note in notes.items():
			p.note(
				BASS_NOTE_MAP[row], beat=int(at) * per_place,
				velocity=note.get("velocity", BASS_VELOCITY),
				duration=note.get("length", BASS_LENGTH) * per_place)

	bass_recipe.build(p)

	if bass_grid.transpose:
		p.transpose(bass_grid.transpose)


@composition.pattern(
	channel=POLY_CHANNEL,
	steps=STEPS,
	step_duration=STEP_DURATION,
	drum_note_map=POLY_NOTE_MAP,
	reschedule_lookahead=1 / 24,
)
def poly (p: typing.Any) -> None:
	"""Play the poly grid's notes, a step to a place, then its stack, then its transposition."""

	for row, notes in poly_grid.now(p).items():
		for at, note in notes.items():
			p.note(
				POLY_NOTE_MAP[row], beat=int(at) * STEP_DURATION,
				velocity=note.get("velocity", POLY_VELOCITY),
				duration=note.get("length", POLY_LENGTH) * STEP_DURATION)

	poly_recipe.build(p)

	if poly_grid.transpose:
		p.transpose(poly_grid.transpose)


def _play (p: typing.Any, grid: dict[str, dict[str, dict[str, int]]]) -> None:
	"""Put whatever a drum grid holds onto the pattern being built, each step as hard as it was struck.

	**A row is a name**, played through the pattern's own drum map, so a grid
	routed into the kit lands on whichever sounds it has rows for.  **Nothing past
	the end of the pattern it plays into**: Subsequence sounds a note placed past
	a pattern's length at the start of its next cycle, so a sixteen-step grid
	routed into the nine stops at nine.
	"""

	ends = getattr(p, "grid", None)

	for row in ROWS:
		steps = grid.get(row)

		if not steps:
			continue

		for step, shape in steps.items():
			at = int(step)

			if ends is not None and at >= ends:
				continue

			p.note(pitch=row, beat=at * STEP_DURATION,
			       velocity=shape.get("velocity", VELOCITY), duration=HIT_DURATION)


# --- Grids with no instrument, played by being routed -------------------------

def _play_shared (p: typing.Any) -> None:
	"""Play the shared drum grid and its stack, inside whichever pattern routed it.

	It has no pattern of its own, so its generators run where it runs: a grid
	routed into two patterns carries its generators to both.
	"""

	_play(p, shared_grid.rows_now())
	shared_recipe.build(p)


def _play_snare_lane (p: typing.Any) -> None:
	"""Play the one-row lane and its stack.  It has only a snare row, so it lands on the snare."""

	_play(p, snare_lane.rows_now())
	snare_recipe.build(p)


def _play_shared_notes (p: typing.Any) -> None:
	"""Play the shared line of notes and its stack, inside whichever pattern routed it.

	**A pitch means itself**: a drum row is a name the borrowing pattern looks up,
	and a note is a number, so the line plays the same notes on either synth, each
	then transposed by its own grid.  A note past the end of the borrowing pattern
	is left out, and one running over is cut short, in what is played and never on
	the line.
	"""

	per_place = STEP_DURATION / BASS_DIVISIONS
	ends = getattr(p, "grid", None)
	last = None if ends is None else ends * BASS_DIVISIONS

	for row, notes in shared_notes.now(p).items():
		for at, note in notes.items():
			begins = int(at)

			if last is not None and begins >= last:
				continue

			length = note.get("length", BASS_LENGTH)

			if last is not None:
				length = min(length, last - begins)

			p.note(
				SHARED_NOTE_MAP[row], beat=begins * per_place,
				velocity=note.get("velocity", BASS_VELOCITY), duration=length * per_place)

	shared_notes_recipe.build(p)


SHARED: dict[str, collections.abc.Callable[[typing.Any], None]] = {
	"shared": _play_shared,
	"shared_notes": _play_shared_notes,
	"snare_lane": _play_snare_lane,
}
"""Grids any pattern here may route from, and how to play each.

**Turning a grid into notes is this file's business**, so the function is this
file's: Superconductor routes, and does not look inside.  A grid the rack makes
on the glass adds itself (`_make_grid`), and because every stack holds this map
rather than a copy, each offers the new grid the moment it exists.
"""


def _places (steps: int) -> adapter.Positions:
	"""Every place a note may start in a pattern this long, and what each is called.

	**The same places twice**, because a generator asks for a place either in steps
	or in beats, and says which.  The words are a musician's: counted from one, with
	the places inside a beat after it, so the second sixteenth is *1.2*.
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


def _stack_for (pattern: str, name: str, title: str,
                pitches: collections.abc.Sequence[str] = ROWS,
                steps: int = STEPS,
                pitch_notes: collections.abc.Mapping[str, int] | None = None) -> typing.Any:
	"""A stack of generators and transforms that builds one pattern.

	``pitches`` is what the pattern's rows are: the kit's sounds for a drum grid,
	notes for a synth.  It is the whole difference between a stack on a kit and one
	on a bassline.  ``steps`` is how long the pattern is, and every bound counting
	steps or beats comes from it, so a generator on the nine is offered at most
	nine pulses.
	"""

	beats = steps * STEP_DURATION

	return adapter.Recipe(
		composition,
		catalogue=subsequence.generators(),
		transforms=subsequence.transforms(),
		pitches=list(pitches),
		pitch_notes=dict(pitch_notes or {}),
		positions=_places(steps),
		bounds={
			"pulses": (0, steps),

			# **Named with its unit**, because `grid` means *how many slots* on
			# most generators and *a grid size in beats* on `swing`.
			("grid", "steps"): (1, steps),
			"subdivisions": (1, 8),
			"duration": (0.05, float(beats)),

			# A ceiling on cost rather than on music: a stack builds on the
			# sequencer's clock, and a slow build makes a late bar.
			"steps": (100, 5000),
		},
		builds=pattern,
		sources=SHARED,
		pulses_per_beat=subsequence.constants.MIDI_QUARTER_NOTE,
		data_key=name,
		name=name,
		title=title)


drum_recipe = _stack_for("drums", "drums_recipe", "Drums — stack")
bass_recipe = _stack_for("bass", "bass_recipe", "Bass — stack", BASS_ROWS, pitch_notes=BASS_NOTE_MAP)
poly_recipe = _stack_for("poly", "poly_recipe", "Poly — stack", POLY_ROWS, pitch_notes=POLY_NOTE_MAP)
nine_recipe = _stack_for("nine", "nine_recipe", "Nine — stack", steps=NINE_STEPS)
shared_recipe = _stack_for("shared", "shared_recipe", "Shared — stack")
snare_recipe = _stack_for("snare_lane", "snare_recipe", "Snare lane — stack", pitches=["snare"])
shared_notes_recipe = _stack_for("shared_notes", "shared_notes_recipe", "Shared — notes stack",
                                 SHARED_ROWS, pitch_notes=SHARED_NOTE_MAP)
"""A stack on every pattern and on every routed grid.

**Each builds after the notes tapped by hand**, so a generator told to skip a step
that already sounds can see it.  The snare lane's offers only the snare: a pool
that could choose any sound would make the lane a kit again.
"""


# --- The grids -----------------------------------------------------------------

drum_grid = adapter.StepGrid(
	composition, rows=ROWS, steps=STEPS, beats=BEATS,
	data_key="drums", name="drums", title="Drums",
	pattern="drums", variants=VARIANTS, lands_every=LANDS_EVERY,
	default_velocity=VELOCITY, min_steps=MIN_STEPS, resize=_resize)

nine_grid = adapter.StepGrid(
	composition, rows=ROWS, steps=NINE_STEPS, beats=NINE_BEATS,
	data_key="nine", name="nine", title="Drums — nine",
	about=[("", "2.25 beats")],
	pattern="nine", default_velocity=VELOCITY, min_steps=MIN_STEPS, resize=_resize)
"""The nine-step pattern, drawn narrower than its neighbours because its cycle is."""

bass_grid = adapter.NoteGrid(
	composition, rows=BASS_ROWS, steps=STEPS, beats=BEATS,
	data_key="bass", name="bass", title="Bass",
	pattern="bass", relabel=_relabel(BASS_NOTE_MAP), voices=BASS_VOICES,
	divisions=BASS_DIVISIONS, default_length=BASS_LENGTH, default_velocity=BASS_VELOCITY,
	visible_rows=12, variants=VARIANTS, lands_every=LANDS_EVERY,
	min_steps=MIN_STEPS, resize=_resize)

poly_grid = adapter.NoteGrid(
	composition, rows=POLY_ROWS, steps=STEPS, beats=BEATS,
	data_key="poly", name="poly", title="Poly",
	pattern="poly", relabel=_relabel(POLY_NOTE_MAP), voices=POLY_VOICES,
	default_length=POLY_LENGTH, default_velocity=POLY_VELOCITY,
	visible_rows=12, variants=VARIANTS, lands_every=LANDS_EVERY,
	min_steps=MIN_STEPS, resize=_resize)

shared_grid = adapter.StepGrid(
	composition, rows=ROWS, steps=STEPS, beats=BEATS,
	data_key="shared", name="shared", title="Shared — drums",
	about=[("", "no instrument")], default_velocity=VELOCITY)
"""A drum grid with no instrument: no channel and no pattern of its own.

It makes no sound until something routes it, and then it makes that thing's
sound.  It plays at the length of whatever routed it, so it offers no length.
"""

snare_lane = adapter.StepGrid(
	composition, rows=["snare"], steps=STEPS, beats=BEATS,
	data_key="snare_lane", name="snare_lane", title="Snare lane",
	about=[("", "no instrument")], default_velocity=VELOCITY)
"""The same, one row wide: it lands on the snare and nowhere else, because that is its only row."""

shared_notes = adapter.NoteGrid(
	composition, rows=SHARED_ROWS, steps=STEPS, beats=BEATS,
	data_key="shared_notes", name="shared_notes", title="Shared — notes",
	divisions=BASS_DIVISIONS, about=[("", "no instrument")],
	default_length=BASS_LENGTH, default_velocity=BASS_VELOCITY,
	visible_rows=12, opens_at=SHARED_OPENS_AT)
"""A line of notes with no instrument, which the bass and the poly can both take."""


notes = adapter.PitchSet(
	composition,
	name="notes",
	title="Pitches",
	pitches={row: midi_notes.name_to_note(row) for row in NOTES_RANGE},
	about=[("feeds", "any generator that takes pitches")],
	opens_at=NOTES_OPEN_AT,
)
"""One set of notes, shared by every generator patched to it.

**It plays nothing on its own.**  Patch an arpeggio on the bass and another on the
poly to it, and both play its notes, each in its own register.
"""


# --- What each pattern plays ------------------------------------------------------

PATTERNS = [
	adapter.Pattern(composition, "drums", plays=[kit], title="Drums"),
	adapter.Pattern(composition, "nine", plays=[kit], title="Drums — nine"),
	adapter.Pattern(composition, "bass", plays=[bass_synth], title="Bass"),
	adapter.Pattern(composition, "poly", plays=[poly_synth], title="Poly"),
]
"""Each pattern above, and the instrument it plays, so the glass can draw a cable to it.

**Two patterns play the kit**, as two Subsequence patterns may share a channel.  The
grids with no instrument play no pattern of their own, and are in none of these.
"""


# --- Grids made from the glass -------------------------------------------------

def _make_grid (spec: dict[str, typing.Any]) -> typing.Any:
	"""Turn one grid asked for on the glass into a drum grid any stack may route from.

	The rack holds a list and knows how long each grid is; this decides what a grid
	is: the kit's rows chosen, played by being routed.
	"""

	key = str(spec["name"])

	made = adapter.StepGrid(
		composition, rows=list(spec["rows"]), steps=int(spec["steps"]),
		beats=int(spec["steps"]) * STEP_DURATION,
		data_key=key, name=key,
		title=str(spec.get("title") or "Made"),
		about=[("", "no instrument")], default_velocity=VELOCITY)

	def play (p: typing.Any) -> None:
		"""Put this grid's notes onto whatever routed it."""

		_play(p, made.rows_now())

	# Routable the moment it exists: a stack reads `SHARED` when it declares, and
	# the rack asks for a declaration as soon as it has made this.
	SHARED[key] = play

	return made


def _unmake_grid (name: str) -> None:
	"""Stop offering a grid that has gone, as something to route from."""

	SHARED.pop(name, None)


made_grids = adapter.Rack(
	composition,
	make=_make_grid,
	unmake=_unmake_grid,
	rows=ROWS,

	# No longer than the patterns it can be routed into, which play it at their own
	# length: a twenty-step grid routed into sixteen would lose four steps quietly.
	steps=(1, STEPS),
	opening_steps=STEPS,
	data_key="made_grids", name="made_grids", title="Make a grid",
	about=[("", "no instrument")])
"""Drum grids made from the glass, each routed into a pattern whose stack does the generating."""


# --- The glass ------------------------------------------------------------------

PATTERN_STORE = adapter.PatternStore.beside(__file__)
PAGE_STORE = adapter.PageStore(pathlib.Path(__file__).with_suffix(".pages.json"))
"""Where what you make on the glass is kept between starts: beside this file.

``demo.patterns.json`` holds every pattern, stack, setting and mute, and
``demo.pages.json`` where each block sits on each page.  **After your first edit,
this file is not the score**: what is kept is put back on each start, and the
opening pattern applies only where the store holds nothing.
"""

link = adapter.AppLink(
	composition,
	controls=[
		drum_grid,
		shared_grid,
		snare_lane,
		shared_notes,
		nine_grid,
		bass_grid,
		poly_grid,
		kit,
		bass_synth,
		poly_synth,
		*PATTERNS,
		drum_recipe,
		bass_recipe,
		poly_recipe,
		shared_recipe,
		shared_notes_recipe,
		snare_recipe,
		nine_recipe,
		notes,
		made_grids,
		adapter.Transport(composition),
	],
	pages=[
		# Everything that makes a sound, on one page.
		adapter.Page("band", parts=["drums", "bass", "poly"], title="Band"),

		# One set of notes, the shared line, and both synths with the stacks that
		# can read them: patch an arpeggio on each to the same notes, and hear two
		# instruments play them.
		adapter.Page(
			"notes",
			parts=["notes", "shared_notes", "shared_notes_recipe",
			       "bass", "bass_recipe", "poly", "poly_recipe"],
			title="Notes"),

		# The kit with everything that writes into it or can be routed to it.
		adapter.Page(
			"drums", parts=["drums", "drums_recipe", "shared", "shared_recipe",
			                "snare_lane", "snare_recipe", "nine", "nine_recipe",
			                "made_grids"],
			title="Drums"),

		adapter.Page("bass", parts=["bass", "bass_recipe"], title="Bass"),
		adapter.Page("poly", parts=["poly", "poly_recipe"], title="Poly"),
	],
	page_store=PAGE_STORE,
	pattern_store=PATTERN_STORE,
	url=SERVICE_URL,
)
"""Five pages, and where what is made on them is kept.

**Every pattern appears on more than one page**: once beside what it plays
against, and once with the controls that belong to it.  Nothing keeps two views
in step, because nothing has to: both draw the grid the composition holds.
"""


if __name__ == "__main__":
	link.start()

	# `play()` returns on Ctrl-C and on a polite kill alike, and `stop` writes down
	# whatever the store had not yet.
	try:
		composition.play()

	finally:
		link.stop()
