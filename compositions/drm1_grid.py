"""A 16-step drum pattern for a Vermona DRM1 MkIV, played from the touchscreen.

This is the first thing Superintendent was built to do (Subroutine #2047).  Run
it beside the Superintendent service and the grid appears on the panel: tapping
a cell switches that step, and a step switched here appears on the glass.

**Everything about this particular studio lives in this file** — which MIDI
port the drum machine is on, which channel it listens to, and which of its
voices sits on which row.  The Superintendent package knows none of it, and
another rig is another copy of this file with different names at the top.

The grid itself is a plain dict on ``composition.data``: rows keyed by voice,
each holding the steps that sound.  The pattern builder reads it and the panel
writes it.  Nothing in the Subsequence package is changed to make this work.
"""

import pathlib
import typing

import pymididefs.cc
import pymididefs.instruments

import subsequence
import subsequence.constants.durations
import subsequence.constants.instruments.vermona_drm1_drums as drm1
import subsequence.constants.midi_notes as midi_notes

import superintendent.subsequence_adapter


# --- This rig -------------------------------------------------------------

MIDI_PORT = "*U6MIDI Pro Port 1*"
"""The interface the DRM1 is plugged into.

A pattern rather than the full name, because ALSA renumbers its clients when
the set of attached devices changes: this port was ``16:0`` before a reboot and
``20:0`` after one, and the exact name stopped matching.  Subsequence matches a
name with wildcards as a glob, so this survives the renumbering.
"""

DRUM_CHANNEL = 10
"""The channel the DRM1 is set to receive on."""

SERVICE_URL = "ws://127.0.0.1:8090/ws/app"
"""The Superintendent service, running on this machine."""

VELOCITY = 100
"""One fixed velocity per hit: a cell is on or off, with no accent (#2046)."""

ROWS = [
	"kick",
	"drum_1",
	"drum_2",
	"multi",
	"snare",
	"clap",
	"hihat_1_closed",
	"hihat_1_open",
	"hihat_2_closed",
	"hihat_2_open",
]
"""Every voice the DRM1 has, one to a row.

Ten rows rather than the machine's eight parts, because each hi-hat has a
separate closed and open note and a cell has no room to carry that choice
while it holds presence alone.  The names are the drum map's own, so nothing
new is invented for the wire.
"""

STEPS = 16
STEP_DURATION = subsequence.constants.durations.SIXTEENTH
BEATS = int(STEPS * STEP_DURATION)
"""Sixteen sixteenth-notes, which is one bar of four beats."""


# --- The Minitaur -----------------------------------------------------------

MINITAUR = pymididefs.instruments.load("moog_minitaur")
"""What a Moog Minitaur *is*, read from the shared corpus rather than typed here.

**Three tiers meet in this file and only the middle one moved.**  What the
*specification* says is `pymididefs` — control change 122 is local control, on
every instrument ever built.  What this *model* does is the definition — control
change 92 is glide type, and its three bands start at 0, 43 and 85.  What *this
rig* does stays here: channel 6, two octaves from C1, and a preference for the
words "Velocity to filter" over the manual's "Filter Velocity Sensitivity".

The middle tier used to be sixty lines of this file, so every other Minitaur
owner typed them again and a correction lived only here.
"""

BASS_CHANNEL = 6
"""The channel the Moog Minitaur is set to receive on."""

BASS_RANGE = [midi_notes.note_to_name(note)
              for note in range(midi_notes.name_to_note("C1"), midi_notes.name_to_note("C3") + 1)]
"""Two chromatic octaves, C1 to C3, in the order music is written in.

Chromatic rather than a scale because no key is being imposed on the instrument
by this file, and one row per pitch rather than twelve pitch classes because
position is then pitch: the line is read as a shape, and an octave leap looks
like one.  Low, because this is a bass — and well inside the Minitaur's range,
which stops at note 72 (#2081).

This list is the whole of the decision.  A different range, or only the notes of
a scale, is an edit here and nothing else anywhere.
"""

_sounds = MINITAUR.voice.note_range

if _sounds is not None and not all(
		_sounds[0] <= midi_notes.name_to_note(row) <= _sounds[1] for row in BASS_RANGE):
	raise ValueError(
		f"BASS_RANGE goes outside what a {MINITAUR.model.name} can sound "
		f"(notes {_sounds[0]} to {_sounds[1]}); outside it the instrument is silent "
		f"rather than wrong-sounding, so nothing else would tell you")
"""A limit is the model's and a preference is the rig's, so this checks one against
the other (#2121).

Skipped when the definition states no range, because an instrument nobody has
measured is not the same as one measured as unlimited — the same distinction
`_voice_count` turns on.

Worth an exception rather than a comment because the failure is **silent**: a
Minitaur ignores a note above 72 rather than playing it wrong, so a range set an
octave too high draws a grid that works perfectly and makes no sound.  Checked
once at import, where it costs nothing and cannot be missed.
"""

BASS_ROWS = list(reversed(BASS_RANGE))
"""The same notes in the order they are drawn, which is top to bottom.

A declared row list is drawn in the order it is given — the drum grid's kick is
first because it is meant to be at the top.  For pitches that means the highest
note first, so the grid reads the way a stave does and a rising line rises.
"""

BASS_NOTE_MAP = {row: midi_notes.name_to_note(row) for row in BASS_RANGE}
"""Row names to MIDI notes, which is the same mechanism the drum map is.

Subsequence resolves a string pitch through whatever map the pattern was given,
and nothing about that map has to be about drums.
"""

BASS_SETTINGS: list[tuple[str, str, str, typing.Any]] = [
	# on the glass         in the definition                on the label        opens at
	("glide",              "glide_switch",                  "Glide",             None),
	("glide_rate",         "glide_rate",                    "Glide rate",        24),
	("glide_type",         "glide_type",                    "Glide type",        "lcr"),
	("legato_glide",       "legato_glide",                  "Legato glide only", None),
	("note_sync",          "note_sync",                     "Note sync",         None),
	("filter_velocity",    "filter_velocity_sensitivity",   "Velocity to filter", 64),
	("volume_velocity",    "volume_velocity_sensitivity",   "Velocity to volume", 64),
	("key_priority",       "key_priority",                  "Note priority",     "last"),
	("volume",             "vca_output_level",              "Output level",      127),
]
"""Which of the Minitaur's thirty-seven controls this rig puts on the glass.

Four columns and every one of them is genuinely this file's to decide.  **What
each control *is*** — its control change, whether it is a switch or a choice,
and where its bands fall — comes from the definition and is not repeated here.

The names are kept short rather than adopted from the definition, for two
reasons.  A panel row is narrow and the manual is not: "Velocity to filter" fits
where "Filter Velocity Sensitivity" does not.  And a captured pattern names its
settings by these, so renaming them would strand a restore (#2067).

Eight of the nine have no knob on the Minitaur at all, which is what earns them
a place: the definition marks them `panel_only`, and that is the strongest
ranking signal a panel ever gets for free.
"""

BASS_CONTROLS = {panel: MINITAUR.controls[named] for panel, named, _, _ in BASS_SETTINGS}
"""Each panel name against what the definition says that control is."""

LOCAL_CONTROL = "local_control"
"""The one setting that is not the Minitaur's, and so is not in its definition.

Its absence from the corpus is the specification tier working rather than a gap:
control change 122 means local control on every instrument, so it belongs in
`pymididefs.cc`.  It is also the one switch taking 0 and 127 exactly, with no
band to sit in the middle of (#2081), which is why it skips the table above.
"""

BASS_VELOCITY = 100
"""What a note is when it is first placed: at a middling weight.

Velocity reaches the Minitaur only through its two sensitivity parameters, which
default to half — CC 89 for the filter and CC 90 for the amplifier (#2081).  A
velocity lane that appears to do nothing is that, not this.
"""

BASS_DIVISIONS = int(subsequence.constants.MIDI_QUARTER_NOTE * STEP_DURATION)
"""How many places a note may start within one step of the bass pattern.

As many as the clock has, which is the finest this rig can play: the sequencer
runs at 24 pulses to a beat and a step here is a sixteenth, so a step holds six
of them.  Asking for more would offer a precision on the glass that no note
could actually be played at.

**This is the composition's number, not the package's** (#1465).  A grid that
says nothing gets one position to a step and is the grid it always was; this
one says six, and in exchange keeps its notes in sixths of a step and reads
them with ``PatternBuilder.note`` rather than ``hit_steps``.
"""

BASS_LENGTH = BASS_DIVISIONS
"""One step, counted in the positions above rather than in steps."""


# --- The Matriarch ----------------------------------------------------------

MATRIARCH = pymididefs.instruments.load("moog_matriarch")
"""The rig's polyphonic instrument, and the first one on this panel (#2143)."""

CHORD_CHANNEL = 1
"""The channel the Matriarch is set to receive on.

Same interface and same port as the other two — a DIN output carries sixteen
channels and this rig uses three of them.
"""

CHORD_RANGE = [midi_notes.note_to_name(note)
               for note in range(midi_notes.name_to_note("C3"), midi_notes.name_to_note("C5") + 1)]
"""Two chromatic octaves, C3 to C5, sitting above the bass rather than across it.

Chosen for chords rather than for a line: high enough that the Minitaur's C1-C3
has room underneath, and two octaves because a chord wants vertical space where
a bassline wants horizontal.  As with BASS_RANGE, this list is the whole of the
decision and a different one is an edit here and nowhere else.
"""

CHORD_ROWS = list(reversed(CHORD_RANGE))
"""Highest note first, so the grid reads the way a stave does."""

CHORD_NOTE_MAP = {row: midi_notes.name_to_note(row) for row in CHORD_RANGE}
"""Row names to MIDI notes, exactly as the bass does it."""

CHORD_VELOCITY = 100
"""What a note is when it is first placed.

The Matriarch receives note-on velocity and does not gate it behind a
sensitivity parameter the way the Minitaur does, so this one is heard.
"""

CHORD_LENGTH = 2
"""How long a chord note is when placed, in steps.

Two rather than one because a chord held for a sixteenth is a stab, and the
first thing anybody will want to hear from a paraphonic synth is something that
rings.
"""

CHORD_VOICES = max(MATRIARCH.voice.voicing_modes)
"""How many notes the grid lets sound at once: the ceiling, not a claim (#2172).

A Matriarch's voicing is a front-panel switch *and* control change 94, and a
person can move that switch at any moment with nothing on the wire to say so.
So the grid enforces the most the instrument can do — never refusing a note it
could have played — and the panel never displays a count it cannot verify.
"""

CHORD_VOICING = dict(zip(MATRIARCH.voice.voicing_modes,
                         MATRIARCH.controls["paraphony_voice_mode"].values))
"""Which band of control change 94 selects which voice count.

**Inferred by pairing two ascending lists**, because the definition states the
counts in `voicing_modes` and names the bands in the control, and does not say
which names which.  Both are ordered lowest-first, so pairing them is sound —
but it is an inference this file is making rather than a fact it was given, and
the assertion below is what stops it selecting the wrong voicing in silence if
either list ever changes shape.  Worth carrying in the definition itself one
day (#2151).
"""

assert len(CHORD_VOICING) == len(MATRIARCH.voice.voicing_modes), (
	"the Matriarch's voice counts and its CC 94 bands no longer pair up")

_chord_range = MATRIARCH.voice.note_range

if _chord_range is not None and not all(
		_chord_range[0] <= midi_notes.name_to_note(row) <= _chord_range[1] for row in CHORD_RANGE):
	raise ValueError(
		f"CHORD_RANGE goes outside what a {MATRIARCH.model.name} can sound "
		f"(notes {_chord_range[0]} to {_chord_range[1]})")
"""The same check the bass gets, for the same reason (#2121)."""


# --- The pattern the composition starts with ------------------------------

OPENING_PATTERN = {
	"kick": [0, 6, 8, 14],
	"snare": [4, 12],
	"hihat_1_closed": [0, 2, 4, 6, 8, 10, 12, 14],
	"hihat_1_open": [7, 15],
	"clap": [12],
}
"""Something to hear on the first bar, and something to see on the glass.

Every row not named here starts empty.  This is here to be changed from the
panel, which is the whole point of the exercise.
"""


composition = subsequence.Composition(output_device=MIDI_PORT, bpm=120)

composition.data["grid"] = {row: sorted(OPENING_PATTERN.get(row, [])) for row in ROWS}
composition.data["shared"] = {row: [] for row in ROWS}
composition.data["bass"] = {}
composition.data["chords"] = {}

def _voice_count (definition: typing.Any, *, when_switchable: int | None = None) -> int | None:
	"""How many notes a grid should let sound at once, from what a definition says.

	**Not a pass-through, and that is the whole point of it.**  A definition's
	``polyphony`` of ``None`` means *nobody has established it*; a note grid's
	``voices`` of ``None`` means *as many as you like*.  Handing one straight to
	the other turns "unknown" into "unlimited" — which on a Moog Matriarch, whose
	voicing is a front-panel switch *and* control change 94 with no documented
	power-on default, draws a five-note chord on a four-voice instrument and says
	nothing at all about it.

	So a stated count is used; an instrument that switches between counts has to
	be *told* which to assume; and only one that states neither is unlimited.
	Which number a switchable instrument should open at is a real question and
	not this function's to answer (#2143) — refusing to guess is.
	"""

	voice = definition.voice

	if voice.polyphony is not None:
		return int(voice.polyphony)

	if voice.voicing_modes:
		if when_switchable is None:
			raise ValueError(
				f"{definition.model.name} switches between {list(voice.voicing_modes)} "
				f"voices and states no default, so a grid has to be told which to assume")

		if when_switchable not in voice.voicing_modes:
			raise ValueError(
				f"{definition.model.name} has no {when_switchable}-voice mode; "
				f"it offers {list(voice.voicing_modes)}")

		return when_switchable

	return None


def _panel_parameter (
	panel: str,
	named: str,
	label: str,
	default: typing.Any,
) -> superintendent.subsequence_adapter.Parameter:
	"""One of the instrument's controls, as something the panel knows how to draw.

	The definition says what the control *is*; this says what it is called here.
	**A kind is derived from the bands rather than declared** — no values means a
	continuous control, two a switch, three or more a choice — so a corrected band
	table changes the drawing without this file being touched at all.
	"""

	control = MINITAUR.controls[named]

	if control.kind == pymididefs.instruments.CHOICE:
		return superintendent.subsequence_adapter.Parameter(
			panel, "choice", label=label, default=default,
			options=[(state, state.replace("_", " ")) for state in control.values])

	if control.kind == pymididefs.instruments.SWITCH:
		return superintendent.subsequence_adapter.Parameter(
			panel, "switch", label=label, default=default)

	low, high = control.range

	return superintendent.subsequence_adapter.Parameter(
		panel, "number", label=label, default=default, minimum=low, maximum=high)


def _cc_value (name: str, value: typing.Any) -> int:
	"""What number the Minitaur wants for a setting the panel expressed in words.

	The definition computes the **middle** of each band rather than its edge, so a
	value that drifts by one does not become a different setting.  Carried by hand
	here until #2142, and by hand they were approximate: glide type went out as 0,
	64 and 110 where the centres are 21, 63 and 106.
	"""

	control = BASS_CONTROLS.get(name)

	if control is None:
		# Local control is the specification's own switch and takes 0 or 127
		# exactly — no band, so no middle to sit in (#2081).
		return 127 if value else 0

	if control.values:
		if isinstance(value, bool):
			# **A switch's two states in the order the definition gives them**,
			# which is ascending, so the second is the far end.  It is not always
			# spelled "on": legato glide is `always` and `legato_only`, and the
			# panel's own label is what says which way round that reads.
			states = list(control.values)
			value = states[1] if value else states[0]

		return control.value_for(value)

	return int(value)


def send_setting (name: str, value: typing.Any) -> None:
	"""Send one setting to the instrument as soon as the clock will carry it.

	``trigger`` with ``quantize=0`` puts a one-shot pattern at the current pulse
	rather than at the next cycle, so a switch takes effect within a pulse —
	about 21 ms at 120 BPM — instead of waiting up to a bar for the pattern to
	be rebuilt.  It is also the only public way into Subsequence's clock from
	another thread, and it takes the send lock that a direct write to the port
	would not.

	A setting moved before the composition is playing is kept in
	``composition.data`` but not sent, because there is no clock yet to send it
	on.
	"""

	control = BASS_CONTROLS.get(name)
	number = control.cc if control is not None else pymididefs.cc.LOCAL_CONTROL_ON_OFF
	amount = _cc_value(name, value)

	composition.trigger(
		lambda p, control=number, amount=amount: p.cc(control, amount),
		channel=BASS_CHANNEL, beats=1 / 24, quantize=0)
@composition.pattern(
	channel=DRUM_CHANNEL,
	steps=STEPS,
	step_duration=STEP_DURATION,
	drum_note_map=drm1.VERMONA_DRM1_DRUM_MAP,
	reschedule_lookahead=1 / 24,
)
def drums (p: typing.Any) -> None:
	"""Play whatever the grid holds when this bar is built.

	Rebuilt one pulse before each cycle rather than a beat before it, so the
	rebuild lands on a pulse that carries no note of its own and delays
	nothing (Subroutine #2041).  It also means a tap waits at most one pulse —
	about 20 ms at 120 BPM — before it can be heard, rather than a whole beat.
	"""

	_play(p, composition.data["grid"])
	drum_recipe.build(p)


@composition.pattern(
	channel=BASS_CHANNEL,
	steps=STEPS,
	step_duration=STEP_DURATION,
	drum_note_map=BASS_NOTE_MAP,
	reschedule_lookahead=1 / 24,
)
def bass (p: typing.Any) -> None:
	"""Play the pitched pattern the panel holds.

	Unlike the drums, every note carries its own length and velocity, so each is
	placed on its own rather than a row at a time.

	**Placed by beat rather than by step**, because this grid divides a step and
	a step is the smallest thing ``hit_steps`` can address.  Both numbers a note
	carries are counted in this pattern's own positions, and one position is
	``STEP_DURATION / BASS_DIVISIONS`` beats — a twenty-fourth of a beat, which
	is one pulse of the clock.
	"""

	beats_per_position = STEP_DURATION / BASS_DIVISIONS

	for row, notes in composition.data["bass"].items():
		for at, note in notes.items():
			p.note(
				row, beat=int(at) * beats_per_position,
				velocity=note.get("velocity", BASS_VELOCITY),
				duration=note.get("length", BASS_LENGTH) * beats_per_position)


_voicing_sent = False
"""Whether this run has told the Matriarch which voicing to use yet."""


@composition.pattern(
	channel=CHORD_CHANNEL,
	steps=STEPS,
	step_duration=STEP_DURATION,
	drum_note_map=CHORD_NOTE_MAP,
	reschedule_lookahead=1 / 24,
)
def chords (p: typing.Any) -> None:
	"""Play the chord pattern the panel holds, on an instrument told how to voice it.

	**The voicing has to be asserted over MIDI or every chord arrives as one
	note** (#2177), measured on this rig: with the front-panel switch on
	two-voice and untouched, notes sent together sounded singly until control
	change 94 was written, and sounded together immediately afterwards.  The
	switch governs the keyboard; it does not govern how incoming MIDI notes are
	allocated.

	Sent once per run rather than every cycle.  Every cycle would be three bytes
	a bar and would also survive somebody moving the switch mid-session — but it
	would insist, continuously, on overriding a control the person can see and
	may have reached for on purpose.  Whether the switch overrides a mode set
	this way is not yet known and is #2177's open question; if it does, this is
	the line that changes.
	"""

	global _voicing_sent

	if not _voicing_sent:
		voicing = MATRIARCH.controls["paraphony_voice_mode"]
		p.cc(voicing.cc, voicing.value_for(CHORD_VOICING[CHORD_VOICES]))
		_voicing_sent = True

	# One position is one step here, unlike the bass: a chord wants to land on
	# the beat rather than between two of them, and nothing yet asks otherwise.
	for row, notes in composition.data["chords"].items():
		for at, note in notes.items():
			p.note(
				row, beat=int(at) * STEP_DURATION,
				velocity=note.get("velocity", CHORD_VELOCITY),
				duration=note.get("length", CHORD_LENGTH) * STEP_DURATION)


def _play (p: typing.Any, grid: dict[str, list[int]]) -> None:
	"""Put whatever a grid holds onto the pattern being built."""

	for row in ROWS:
		steps = grid.get(row)

		if steps:
			p.hit_steps(row, list(steps), velocity=VELOCITY)


SHARED = {"shared": lambda p: _play(p, composition.data["shared"])}
"""Grids any pattern here may take its notes from, and how to play one.

**Turning a grid into notes is this file's business, so the function is this
file's.**  The velocity, the drum map and what a row name means are all facts
about this rig; the package routes and does not look inside (#1465, #2108).

One so far — a grid belonging to no instrument, which sounds only where it is
routed.  Simon's own case is a bassline shared by two synths, each adding notes
of its own; this is the same shape with one machine and two patterns, which is
what this rig can show today.
"""


def _stack_for (pattern: str, name: str, title: str) -> typing.Any:
	"""A stack of contributions that build one pattern."""

	return superintendent.subsequence_adapter.Recipe(
		composition,
		catalogue=subsequence.generators(),
		pitches=ROWS,
		bounds={
			"pulses": (0, STEPS),
			"grid": (1, STEPS),
			"subdivisions": (1, 8),
			"duration": (0.05, float(BEATS)),
		},
		builds=pattern,
		sources=SHARED,

		# So the stack can say which cells it realised, and the panel can draw
		# them (#1925). The sequencer's number, handed in because the adapter
		# imports no sequencer — it is duck-typed on whatever this file gives it.
		pulses_per_beat=subsequence.constants.MIDI_QUARTER_NOTE,
		data_key=name,
		name=name,
		title=title)


# The names are what the panel addresses and what a saved arrangement is keyed
# by, so `drum_recipe` keeps the name it was born with rather than taking a
# tidier one: renaming a control silently empties whatever it was holding.
drum_recipe = _stack_for("grid", "drum_recipe", "DRM1 — generators")
"""Generators the panel can stack onto pattern 1, over the notes tapped by hand.

The catalogue is Subsequence's own description of itself, and the ten voices
are this rig's — which is the whole division: the app knows a parameter is a
pitch and cannot know which pitches exist, and only this file knows they are a
DRM1's (#1465, #2085).  Superintendent is handed both and names neither.

``builds`` names the pattern this stack contributes to.  The panel draws the
two joined and puts the stack's own "add a generator" on the grid it feeds,
because that is where a person is looking when they want another one.

Built *after* the hand grid in the pattern function, deliberately.  A generator
told to skip a step that already sounds has to see the taps before it runs, and
the order a stack plays in is the person's to arrange from the glass.
"""


link = superintendent.subsequence_adapter.AppLink(
	composition,
	controls=[
		superintendent.subsequence_adapter.StepGrid(
			composition, rows=ROWS, steps=STEPS, beats=BEATS,
			data_key="grid", name="grid", title="DRM1 — pattern 1",
			about=[("ch", DRUM_CHANNEL), ("", "Vermona DRM1 MkIV")],
			pattern="drums"),
		# A grid with no instrument behind it: no channel, no note map, no
		# pattern function of its own. It makes no sound until something routes
		# it, and then it makes that thing's sound (#2108).
		superintendent.subsequence_adapter.StepGrid(
			composition, rows=ROWS, steps=STEPS, beats=BEATS,
			data_key="shared", name="shared", title="Shared — drums",
			about=[("", "no instrument")]),
		superintendent.subsequence_adapter.NoteGrid(
			composition, rows=BASS_ROWS, steps=STEPS, beats=BEATS,
			data_key="bass", name="bass", title="Minitaur — bass",
			voices=_voice_count(MINITAUR),
			pattern="bass", divisions=BASS_DIVISIONS,
			about=[("ch", BASS_CHANNEL), ("", "Moog Minitaur")],
			default_length=BASS_LENGTH, default_velocity=BASS_VELOCITY,
			visible_rows=12),
		superintendent.subsequence_adapter.NoteGrid(
			composition, rows=CHORD_ROWS, steps=STEPS, beats=BEATS,
			data_key="chords", name="chords", title="Matriarch — chords",
			# The ceiling, through the guard that refuses to read an
			# unestablished polyphony as an unlimited one (#2172, #2142).
			voices=_voice_count(MATRIARCH, when_switchable=CHORD_VOICES),
			pattern="chords",
			about=[("ch", CHORD_CHANNEL), ("", "Moog Matriarch")],
			default_length=CHORD_LENGTH, default_velocity=CHORD_VELOCITY,
			visible_rows=12),
		superintendent.subsequence_adapter.Params(
			composition,
			parameters=[
				*(_panel_parameter(*setting) for setting in BASS_SETTINGS),

				# The specification's own switch rather than the Minitaur's, so
				# it comes from `pymididefs.cc` and not from the definition.
				superintendent.subsequence_adapter.Parameter(
					LOCAL_CONTROL, "switch", label="Front panel controls", default=True),
			],
			data_key="minitaur", name="minitaur", title="Minitaur — settings",
			about=[("ch", BASS_CHANNEL), ("", "Moog Minitaur")],
			on_change=send_setting),
		drum_recipe,
		superintendent.subsequence_adapter.Transport(composition),
	],
	pages=[
		superintendent.subsequence_adapter.Page(
			"pattern_1", parts=["grid"], title="Pattern 1"),
		superintendent.subsequence_adapter.Page(
			"bass", parts=["bass"], title="Bass"),
		superintendent.subsequence_adapter.Page(
			"kit", parts=["grid", "bass"], title="Drums + bass"),
		superintendent.subsequence_adapter.Page(
			"minitaur", parts=["bass", "minitaur"], title="Minitaur"),
		superintendent.subsequence_adapter.Page(
			"chords", parts=["chords"], title="Chords"),
		superintendent.subsequence_adapter.Page(
			"band", parts=["chords", "bass", "grid"], title="Band"),
		superintendent.subsequence_adapter.Page(
			"generators", parts=["grid", "drum_recipe"], title="Generators"),
		superintendent.subsequence_adapter.Page(
			"shared", parts=["shared", "grid", "drum_recipe"], title="Shared"),
	],
	page_store=superintendent.subsequence_adapter.PageStore(
		pathlib.Path(__file__).with_suffix(".pages.json")),
	url=SERVICE_URL,
)
"""Six views over this rig, and where their arrangement is kept.

The arrangement file sits beside this one and is written by the adapter when a
finger lifts from a block that moved.  It is data rather than code because there
is no safe way to write a dragged block back into a Python file, and it is beside
the composition rather than inside the service because a page set belongs to the
piece that declared it (Subroutine #2075).

Every pattern appears on more than one of them — once with the whole glass to
itself and once beside whatever it plays against — which is the case worth
having: see how they play together, then take one on its own to work on it
closely.  Nothing keeps two views of a pattern in step, because nothing has to:
both draw the grid the composition holds.
"""


if __name__ == "__main__":
	link.start()
	composition.play()
