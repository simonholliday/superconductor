"""A 16-step drum pattern for a Vermona DRM1 MkIV, played from the touchscreen.

This is the first thing Superconductor was built to do (Subroutine #2047).  Run
it beside the Superconductor service and the grid appears on the panel: tapping
a cell switches that step, and a step switched here appears on the glass.

**Everything about this particular studio lives in this file** — which MIDI
port the drum machine is on, which channel it listens to, and which of its
voices sits on which row.  The Superconductor package knows none of it, and
another rig is another copy of this file with different names at the top.

The grid itself is a plain dict on ``composition.data``: rows keyed by voice,
each holding the steps that sound.  The pattern builder reads it and the panel
writes it.  Nothing in the Subsequence package is changed to make this work.
"""

import collections.abc
import pathlib
import typing

import pymididefs.cc
import pymidiinstrumentdefs

import subsequence
import subsequence.constants.durations
import subsequence.constants.instruments.vermona_drm1_drums as drm1
import subsequence.constants.midi_notes as midi_notes

import superconductor.subsequence_adapter


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
"""The Superconductor service, running on this machine."""

PATTERN_FILE = pathlib.Path.home() / "superconductor-drm1_grid.patterns.json"
"""Where what is made on the glass is kept between starts (#2487).

**Not beside this file, which is where a composition would ordinarily keep it.**
This one sits on a network share, and on this rig's kernel a write there can wedge
the process making it (nuc14 #2438) — and the store is written every time somebody
stops tapping.  So it lives on this machine's own disk.  A composition on local
disk would say ``PatternStore.beside(__file__)`` and keep it next to itself.
"""

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
BEATS = STEPS * STEP_DURATION
"""Sixteen sixteenth-notes, which is one bar of four beats."""

NINE_STEPS = 9
NINE_BEATS = NINE_STEPS * STEP_DURATION
"""Nine sixteenths — 2.25 beats, which is the whole point (#2228).

**Polyrhythm here is independent pattern lengths**, which is how Subsequence's
own README says to do it: a second pattern on the same instrument, nine steps
long, looping against the sixteen and coinciding with it every nine bars.

It is deliberately *not* a routed grid.  A grid patched into the drums plays at
the destination's resolution, so nine steps routed into a sixteen-step pattern
would be a truncated bar rather than a cycle of its own — which is the difference
between the two mechanisms this pair exists to show side by side.

**And 2.25 is why a grid's `beats` had to stop being an integer.**  Every grid on
this rig had been sixteen sixteenths, and `int(16 * 0.25)` is 4 without
complaining; the first cycle that is not a whole number of beats is this one.
"""


# --- The Minitaur -----------------------------------------------------------

MINITAUR = pymidiinstrumentdefs.load("moog/minitaur")
"""What a Moog Minitaur *is*, read from the shared corpus rather than typed here.

**Three tiers meet in this file and only the middle one moved.**  What the
*specification* says is `pymididefs` — control change 122 is local control, on
every instrument ever built.  What this *model* does is its definition in
`pymidiinstrumentdefs` — control change 92 is glide type, and its three bands
start at 0, 43 and 85.  What *this rig* does stays here: channel 6, two octaves
from C1, and a preference for the words "Velocity to filter" over the manual's
"Filter Velocity Sensitivity".

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

MATRIARCH = pymidiinstrumentdefs.load("moog/matriarch")
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
                         MATRIARCH.controls["paraphony_voice_mode"].states))
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


CHORD_SETTINGS: list[tuple[str, str, str, typing.Any, str]] = [
	# on the glass        in the definition           on the label          opens at   section
	("voices",            "paraphony_voice_mode",     "Paraphony",           None,     "Keyboard"),
	("kb_octave",         "kb_octave",                "Octave",              "zero",   "Keyboard"),
	("multi_trig",        "multi_trig",               "Multi trigger",       None,     "Keyboard"),
	("sustain",           "sustain_pedal",            "Sustain",             None,     "Keyboard"),

	("osc_1_octave",      "osc_1_octave",             "Osc 1 octave",        None,     "Oscillators"),
	("osc_2_octave",      "osc_2_octave",             "Osc 2 octave",        None,     "Oscillators"),
	("osc_2_freq",        "osc_2_frequency",          "Osc 2 frequency",     64,       "Oscillators"),
	("osc_2_sync",        "osc_2_sync",               "Osc 2 sync",          None,     "Oscillators"),
	("osc_3_octave",      "osc_3_octave",             "Osc 3 octave",        None,     "Oscillators"),
	("osc_3_freq",        "osc_3_frequency",          "Osc 3 frequency",     64,       "Oscillators"),
	("osc_3_sync",        "osc_3_sync",               "Osc 3 sync",          None,     "Oscillators"),
	("osc_4_octave",      "osc_4_octave",             "Osc 4 octave",        None,     "Oscillators"),
	("osc_4_freq",        "osc_4_frequency",          "Osc 4 frequency",     64,       "Oscillators"),
	("osc_4_sync",        "osc_4_sync",               "Osc 4 sync",          None,     "Oscillators"),
	("hard_sync",         "hard_sync_enable",         "Hard sync",           None,     "Oscillators"),

	("glide",             "glide_on",                 "Glide",               None,     "Glide"),
	("glide_time",        "glide_time",               "Glide time",          24,       "Glide"),
	("glide_type",        "glide_type",               "Glide type",          "lcr",    "Glide"),
	("gated_glide",       "gated_glide",              "Gated glide",         None,     "Glide"),
	("legato_glide",      "legato_glide",             "Legato glide",        None,     "Glide"),

	("arp",               "arp_play",                 "Arpeggiator",         None,     "Arpeggiator"),
	("arp_latch",         "arp_latch",                "Latch",               None,     "Arpeggiator"),
	# **The band the old `0` fell in**, so a Matriarch opens exactly where it did.
	# Until `pymidiinstrumentdefs` 0.1.1 these three named no states and were drawn
	# as numbers; the manual's bands arrived there (#2203), and a choice opens at a
	# state's name.
	("arp_mode",          "arp_mode",                 "Mode",                "arp",    "Arpeggiator"),
	("arp_pattern",       "arp_pattern",              "Pattern",             "order",  "Arpeggiator"),
	("arp_rate",          "arp_rate",                 "Rate",                64,       "Arpeggiator"),
	("arp_range",         "arp_range",                "Range",               "one",    "Arpeggiator"),
	("arp_swing",         "arp_swing",                "Swing",               64,       "Arpeggiator"),
	("arp_gate",          "arp_gate_length",          "Gate length",         64,       "Arpeggiator"),

	("delay_time",        "delay_time",               "Time",                64,       "Delay"),
	("delay_spacing",     "delay_spacing",            "Spacing",             64,       "Delay"),
	("delay_sync",        "delay_sync",               "Sync",                None,     "Delay"),
	("delay_ping_pong",   "delay_ping_pong",          "Ping-pong",           None,     "Delay"),

	("mod_wheel",         "mod_wheel",                "Mod wheel",           0,        "Modulation"),
	("mod_rate",          "mod_rate",                 "Mod rate",            64,       "Modulation"),
	# **A bool, not the band's name.**  Two states make a switch, and a switch
	# holds True or False — `_cc_value` picks the far end of the definition's own
	# ascending pair, which is `bipolar`.  Naming the band here declared a switch
	# opening at a string, and `restore_state.py` is what caught it.
	("lfo_polarity",      "square_lfo_polarity",      "Square LFO",          True,     "Modulation"),
	("noise_cutoff",      "noise_filter_cutoff",      "Noise filter",        64,       "Modulation"),
]
"""All thirty-six of the Matriarch's controls, in six sections.

**Everything, on purpose, and the point is the sections rather than the
controls.**  Simon, 2026-09-07: *"It's not because I'll necessarily need all 36,
but I want to see how we handle a busy interface, and use it as an example to set
some conventions which we can use for future panels."*  So this is a stress test
that happens to be a real instrument.

Five columns where the Minitaur's table has four, and the fifth is the section on
the instrument's own front panel.  **Those words are this file's**, like every
other label here: a Matriarch has an *Arpeggiator* because Moog printed that on
it, and neither the package nor the definition knows that (#1465).

The order is the order they are drawn in, and it is the instrument's rather than
the definition's — which is by control-change number and is meaningless to a
hand.  Oscillator 2's octave, frequency and sync sit together here because that
is where they sit on the panel, three rows apart on the Matriarch and thirty CC
numbers apart in the file.

``voices`` is the exception and is **not drawn from this table**: it is an
`action` rather than a setting, because a Matriarch's voicing is a front-panel
switch as well as CC 94 and whichever moved last wins (#2177, #2172).  It is
listed here so the table is a complete account of the instrument, and skipped
where the parameters are built.
"""

CHORD_CONTROLS = {panel: MATRIARCH.controls[named] for panel, named, _, _, _ in CHORD_SETTINGS}
"""Each panel name against what the definition says that control is."""

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
composition.data["snare_lane"] = {"snare": []}
composition.data["nine"] = {row: [] for row in ROWS}
composition.data["bass"] = {}
composition.data["chords"] = {}

def _relabel (notes: dict[str, int], definition: typing.Any) -> typing.Any:
	"""What a row of *notes* is called once the pattern is transposed, for *definition*.

	**Only this file can answer it.**  The package knows a row is called ``C2``
	and nothing more; that ``C2`` is a pitch, that two semitones above it is
	``D2``, and that the instrument stops at note 72 are all facts about a studio
	(#1465).  So the grid asks and this answers, one row at a time.

	``None`` says the row cannot sound at that offset.  It is the whole reason
	the labels move at all: a Minitaur ignores a note above 72 rather than
	playing it wrong, so transposing a bassline up goes **silent**, and a row
	that says so on the glass is the difference between a design decision and a
	bug report about a synth that stopped working.
	"""

	def named (row: str, semitones: int) -> str | None:
		note = _sounding(row, semitones, notes, definition)

		return None if note is None else str(midi_notes.note_to_name(note))

	return named


def _sounding (
	row: str,
	semitones: int,
	notes: dict[str, int],
	definition: typing.Any,
) -> int | None:
	"""The note *row* actually plays at *semitones*, or None where it cannot.

	**What the glass reads, and the same arithmetic the player does.**  A row the
	label calls unreachable and the player sounds anyway would be a disagreement
	between the glass and the ears — the exact fault transposition was designed to
	avoid.  The player no longer calls this (#2454): it moves the whole pattern
	with `_transposed`, by the same number of semitones, and an instrument sounds
	nothing outside the `note_range` this checks.
	"""

	note = notes[row] + semitones
	sounds = definition.voice.note_range

	if sounds is not None and not sounds[0] <= note <= sounds[1]:
		return None

	return note


def _transposed (p: typing.Any, semitones: int) -> None:
	"""Move everything this pattern plays by *semitones*, once its stack has run.

	**The whole pattern, not the notes somebody tapped** (#2454, Simon's decision
	of 2026-09-11).  Transposition used to be applied while the tapped notes were
	placed, so every generator's notes went on sounding where they were — while
	the row labels moved for all of them (#2144), which left each generated note
	on a row naming a pitch it did not play.  Applied last, after routes and
	generators and transforms, it moves what the pattern plays as one thing, and
	every label is true again.

	**`realised` needs nothing**: the stack reports its notes inside `build`,
	before this runs, so each one is still drawn on the row it was placed on — and
	that row's label now says what it sounds.

	**A note moved past the instrument's reach is sent, and is silent.**  The
	definition's own terms: outside `note_range` an instrument sounds nothing
	(`Voice.plays_note`), and `_sounding` marks exactly those rows unreachable.
	Before this, a tapped note there was dropped rather than sent — a guarantee
	by construction where this is one by report.  Subsequence's `transpose`
	clamps to 0-127 and has no way to drop a note, so asking it for one is
	filed rather than reaching into the pattern's internals.
	"""

	if semitones:
		p.transpose(semitones)


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
	group: str | None = None,
	instrument: typing.Any = None,
) -> superconductor.subsequence_adapter.Parameter:
	"""One of the instrument's controls, as something the panel knows how to draw.

	The definition says what the control *is*; this says what it is called here.
	**A kind is derived from the bands rather than declared** — no values means a
	continuous control, two a switch, three or more a choice — so a corrected band
	table changes the drawing without this file being touched at all.

	``group`` is the section of the instrument's front panel this control sits in,
	and is a **heading rather than a structure** — the settings stay one flat list
	in the order given here.  It is optional because a panel of nine does not need
	one and a panel of thirty-six is unreadable without one, which is exactly the
	difference between the two instruments on this rig.

	The words are this file's, like every other label: a Matriarch has an
	*Arpeggiator* because Moog put that word on the panel, and neither the package
	nor the definition knows that.
	"""

	definition = instrument or MINITAUR
	control = definition.controls[named]

	# **A control the instrument only transmits is not something to send**, and a
	# definition says so in `direction` (#2469).  Offered here it would be a row on
	# the glass that moves nothing and says nothing about it — the silence the
	# range checks above exist for — so a table naming one fails at import, where
	# a person is looking, rather than on the glass, where nobody would know why.
	if not control.is_sendable:
		raise ValueError(
			f"{panel} is the {definition.model.name}'s {named}, which it transmits and "
			f"does not receive, so nothing the panel sent would reach it")

	# **A choice with nothing to choose is not a choice.**  Three of the
	# Matriarch's arpeggiator controls were declared `choice` and named no states —
	# mode, pattern and range, whose bands the definition had not recorded.  Drawn
	# as declared they came out as three empty rows: a label, and then nothing at
	# all to press.  Their bands arrived upstream in `pymidiinstrumentdefs` 0.1.1,
	# from the manual's table (#2203).
	#
	# The fallback stays, because a definition is a *report* about a particular
	# model and reports are wrong in the wild — which is the whole reason instrument
	# facts live in a file rather than in code, and one somebody writes for their
	# own synth is the likeliest to have it.  So this reads what is actually there
	# rather than what the kind claims, and draws the continuous control the range
	# describes.  It costs one branch; the alternative is a blank row nobody can
	# explain.
	#
	# **`states` and not `values`**: a stepped control is either bands (`values`)
	# or exact numbers (`choices`, #2467), and `states` names either.
	if control.kind == pymidiinstrumentdefs.CHOICE and control.states:
		return superconductor.subsequence_adapter.Parameter(
			panel, "choice", label=label, default=default, group=group,
			options=[(state, state.replace("_", " ")) for state in control.states])

	if control.kind == pymidiinstrumentdefs.SWITCH:
		return superconductor.subsequence_adapter.Parameter(
			panel, "switch", label=label, default=default, group=group)

	low, high = control.range

	return superconductor.subsequence_adapter.Parameter(
		panel, "number", label=label, default=default, group=group,
		minimum=low, maximum=high)


def _cc_value (name: str, value: typing.Any,
               controls: dict[str, typing.Any] | None = None) -> int:
	"""What number the instrument wants for a setting the panel expressed in words.

	The definition computes the **middle** of each band rather than its edge, so a
	value that drifts by one does not become a different setting.  Carried by hand
	here until #2142, and by hand they were approximate: glide type went out as 0,
	64 and 110 where the centres are 21, 63 and 106.  A control whose manual prints
	exact numbers rather than bands (#2467) is sent exactly those, and the
	definition knows which shape it holds, so this does not have to.

	``controls`` is which instrument's, defaulting to the Minitaur's because it
	was the only one when this was written.  The band arithmetic is the
	definition's and is the same for every instrument; only the table changes.
	"""

	control = (BASS_CONTROLS if controls is None else controls).get(name)

	if control is None:
		# Local control is the specification's own switch and takes 0 or 127
		# exactly — no band, so no middle to sit in (#2081).
		return 127 if value else 0

	if control.states:
		if isinstance(value, bool):
			# **A switch's two states in the order the definition gives them**,
			# which is ascending, so the second is the far end.  It is not always
			# spelled "on": legato glide is `always` and `legato_only`, and the
			# panel's own label is what says which way round that reads.
			states = control.states
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
	channel=DRUM_CHANNEL,
	steps=NINE_STEPS,
	step_duration=STEP_DURATION,
	drum_note_map=drm1.VERMONA_DRM1_DRUM_MAP,
	reschedule_lookahead=1 / 24,
)
def nine (p: typing.Any) -> None:
	"""The same instrument, a cycle of a different length (#2228).

	**Two patterns on one channel and one note map, which Subsequence allows and
	nothing here had tried.**  This one is 2.25 beats where `drums` is 4, so the
	two drift against each other and coincide every nine bars — Subsequence's own
	way of doing polyrhythm, which is by independent pattern lengths rather than
	by anything inside a bar.

	It opens empty on purpose.  The playheads part company whether or not there
	is a note under them, so the mechanism is visible before anybody has drawn
	anything — and what to put on it is a musical decision this file should not
	be making for whoever is standing at the panel.
	"""

	_play(p, composition.data["nine"])
	nine_recipe.build(p)


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

	# **As written, and moved with everything else below** (#2454).
	for row, notes in composition.data["bass"].items():
		for at, note in notes.items():
			p.note(
				BASS_NOTE_MAP[row], beat=int(at) * beats_per_position,
				velocity=note.get("velocity", BASS_VELOCITY),
				duration=note.get("length", BASS_LENGTH) * beats_per_position)

	bass_recipe.build(p)
	_transposed(p, bass_grid.transpose)


def send_voicing (name: str, value: typing.Any) -> None:
	"""Ask the Matriarch for a voicing, which is the only way it will honour one.

	Its front-panel switch and control change 94 are the same setting reached two
	ways, and **whichever moved last wins** — measured on this rig (#2177).  So
	nothing here can know which voicing is in force, and nothing tries: this only
	asserts one, and the panel draws it as a control that does something rather
	than one that shows something (#2179).

	Which is what makes it worth having on the glass at all.  A hand on that
	switch silently undoes what the composition asked for at startup, and this is
	how a person puts it back without walking to the instrument.
	"""

	voicing = MATRIARCH.controls["paraphony_voice_mode"]

	composition.trigger(
		lambda p, cc=voicing.cc, amount=voicing.value_for(value): p.cc(cc, amount),
		channel=CHORD_CHANNEL, beats=1 / 24, quantize=0)


def send_chord_setting (name: str, value: typing.Any) -> None:
	"""Send one of the Matriarch's settings, or assert its voicing.

	The same shape as `send_setting` for the bass, on the Matriarch's channel and
	against the Matriarch's table — the band arithmetic belongs to the definition
	and is the same for both, so only the table changes.

	**Voicing is the one that is not a setting** and is routed away here.  It is
	an `action` because a Matriarch's paraphony is a front-panel switch as well as
	CC 94, whichever moved last wins, and nothing can read which (#2177) — so it
	is asserted and never displayed, and it holds no value to send.
	"""

	if name == "voicing":
		send_voicing(name, value)

		return

	control = CHORD_CONTROLS[name]

	composition.trigger(
		lambda p, cc=control.cc, amount=_cc_value(name, value, CHORD_CONTROLS): p.cc(cc, amount),
		channel=CHORD_CHANNEL, beats=1 / 24, quantize=0)


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
				CHORD_NOTE_MAP[row], beat=int(at) * STEP_DURATION,
				velocity=note.get("velocity", CHORD_VELOCITY),
				duration=note.get("length", CHORD_LENGTH) * STEP_DURATION)

	chord_recipe.build(p)
	_transposed(p, chord_grid.transpose)


def _play (p: typing.Any, grid: dict[str, list[int]]) -> None:
	"""Put whatever a grid holds onto the pattern being built."""

	for row in ROWS:
		steps = grid.get(row)

		if steps:
			p.hit_steps(row, list(steps), velocity=VELOCITY)


def _play_shared (p: typing.Any) -> None:
	"""Replay the instrument-less grid, and run whatever is stacked on it.

	**The stack is built here because this grid has no pattern of its own**
	(#2147).  Every other stack is built by the pattern function that owns it;
	this grid makes no sound until something routes it, so its generators run
	where the grid runs — inside whichever pattern borrowed it.  A grid patched
	into two instruments carries its generators to both, which is what the grid
	already does with its notes.
	"""

	_play(p, composition.data["shared"])
	shared_recipe.build(p)


def _play_snare_lane (p: typing.Any) -> None:
	"""Replay the one-voice lane, and run whatever is stacked on it.

	**The join is a row name and nothing else** (#2228).  ``_play`` walks this
	rig's ten voices and puts down whatever the grid holds for each; a grid
	declaring only ``snare`` therefore holds nothing for the other nine and
	lands on the snare alone.  Routing a lane to one voice needed no mechanism
	— it is what routing has meant here since #2147, exercised for the first
	time with a grid that is not the whole kit.
	"""

	_play(p, composition.data["snare_lane"])
	snare_recipe.build(p)


SHARED: dict[str, collections.abc.Callable[[typing.Any], None]] = {
	"shared": _play_shared,
	"snare_lane": _play_snare_lane,
}
"""Annotated rather than inferred: a dict is invariant in its value type, and a
named function infers as its own signature rather than as the `Callable` the
adapter asks for.  It was a lambda before and inferred loosely enough not to
notice."""
"""Grids any pattern here may take its notes from, and how to play one.

**Turning a grid into notes is this file's business, so the function is this
file's.**  The velocity, the drum map and what a row name means are all facts
about this rig; the package routes and does not look inside (#1465, #2108).

One so far — a grid belonging to no instrument, which sounds only where it is
routed.  Simon's own case is a bassline shared by two synths, each adding notes
of its own; this is the same shape with one machine and two patterns, which is
what this rig can show today.
"""


def _places (steps: int) -> superconductor.subsequence_adapter.Positions:
	"""Every place a note may start in a pattern this long, in each unit an app
	counts in (#2412).

	**The same places twice.**  A sixteen-step bar has sixteen of them; asked for
	in `steps` they are 0 to 15 and asked for in `beats` they are 0 to 3.75, and
	which a generator wants is on its own declaration — `hit_steps` counts steps
	and `hit` counts beats.  Offering whole beats alone would throw away three
	quarters of the pattern this rig actually has.

	**The labels are here because a panel may not invent one** (#2144), and
	because counting is a musical convention rather than arithmetic: a musician
	counts from **one**, so step 0 is *1* and the second beat is *2*, and the
	places inside a beat are numbered after it.  Superconductor is handed the
	words and never works one out.

	`STEP_DURATION` is a quarter of a beat here, so every beat position lands on
	an exact binary fraction and survives the round trip through JSON that the
	service's own copy has to match.  A resolution that did not would want
	rounding rather than luck.
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
	"""A stack of contributions that build one pattern.

	``pitches`` is what this pattern's rows *are*, and it is the whole of what
	makes a stack on a bassline different from a stack on a kit: the catalogue
	knows a parameter is a pitch and cannot know which pitches exist, and only
	this file knows that one grid's rows are a DRM1's voices and another's are
	notes a Minitaur can reach (#1465, #2085).  Superconductor is handed both and
	names neither.

	``steps`` is how long the pattern this stack builds actually is, and every
	bound below that counts steps or beats is derived from it (#2228).  It was
	``STEPS`` throughout while every pattern on the rig was sixteen; a nine-step
	pattern offered a euclidean up to sixteen pulses would be offering a control
	whose top half cannot land — the same fault as a filled parameter that means
	*nothing*, arriving from the other direction.
	"""

	beats = steps * STEP_DURATION

	return superconductor.subsequence_adapter.Recipe(
		composition,
		catalogue=subsequence.generators(),

		# **What this stack may reshape with, beside what it may add** (#2246).
		# Subsequence describes both the same way and keeps them in two lists,
		# because the two are different things: a generator invents notes and a
		# transform works on everything above it in the stack. This file passes
		# both along and names neither, exactly as it does for the generators.
		transforms=subsequence.transforms(),
		pitches=list(pitches),

		# **What this stack's own rows sound**, so a patched set of notes can be
		# folded into the register this instrument actually reaches (#2374).  Only
		# this file knows it — the same reason it is the only thing that knows the
		# rows are notes at all rather than drum voices.
		pitch_notes=dict(pitch_notes or {}),
		# **Where a note may go, which is this pattern's to say** (#2412).  The
		# app says a parameter is a *position* and can say no more — how many
		# there are is a fact about the piece, exactly as which pitches exist is
		# a fact about the instrument.  Three generators that could be added and
		# could never run are drivable with this: `hit`, `hit_steps`, `sequence`.
		positions=_places(steps),
		bounds={
			"pulses": (0, steps),

			# **Named with its unit, because one word covers two meanings**
			# (#2413, fixed by #2436).  `grid` is on eight of Subsequence's
			# entries: seven mean *how many slots the pattern has* and
			# `swing.grid` means *grid size in beats*, opening at 0.25 — which
			# this range forbids.  Bounded plainly it took the swing layer out
			# of range at birth, and a stack is written whole, so every control
			# on that stack was then refused while the message named a layer
			# nobody had touched.
			#
			# The adapter dropped the bound with a warning, which was the right
			# thing to do knowing nothing; the unit is what lets it be right
			# instead.
			("grid", "steps"): (1, steps),
			"subdivisions": (1, 8),
			"duration": (0.05, float(beats)),

			# **Two bounds that are about cost rather than about music** (#2231).
			# A stack builds on the clock loop, and Subsequence contains a
			# rebuild that *raises* — the pattern loses its cycle and the clock
			# is untouched — while having no defence at all against one that is
			# merely slow. Worse, an overrunning rebuild is not a late bar: the
			# loop accumulates absolutely and then dispatches every missed pulse
			# in one pass without yielding, so it comes out as a burst.
			#
			# `reaction_diffusion` costs 3.4 ms a thousand steps, measured, and
			# is linear — so a ceiling states it honestly. Five thousand is 17 ms
			# against a two-second cycle here.
			#
			# **`de_bruijn` is deliberately not bounded here**, and it was, for
			# an hour. Its cost is k to the power of the window, where k is how
			# many pitches this stack has — so the bound had to be *computed*
			# from the pool, which meant this file holding the fact that de
			# Bruijn generates k^window notes. That is a second copy of a fact
			# about a sequencer, which is the one thing this arrangement exists
			# to prevent. Subsequence now clamps inside the generator against a
			# note budget (`d03fdb6`), which is the right place because only it
			# knows both halves.
			"steps": (100, 5000),
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
drum_recipe = _stack_for("grid", "drum_recipe", "DRM1 — stack")
"""Generators the panel can stack onto pattern 1, over the notes tapped by hand.

The catalogue is Subsequence's own description of itself, and the ten voices
are this rig's — which is the whole division: the app knows a parameter is a
pitch and cannot know which pitches exist, and only this file knows they are a
DRM1's (#1465, #2085).  Superconductor is handed both and names neither.

``builds`` names the pattern this stack contributes to.  The panel draws the
two joined and puts the stack's own "add a generator" on the grid it feeds,
because that is where a person is looking when they want another one.

Built *after* the hand grid in the pattern function, deliberately.  A generator
told to skip a step that already sounds has to see the taps before it runs, and
the order a stack plays in is the person's to arrange from the glass.
"""

bass_recipe = _stack_for("bass", "bass_recipe", "Minitaur — stack", BASS_ROWS,
                         pitch_notes=BASS_NOTE_MAP)
"""And the same for the bassline, which is #2147 and is a change to this file.

**Nothing in the package forbade it and nothing had to change there.**  The panel
offers "add generator" on a pattern exactly where some stack declares it
`builds`, and until now this composition declared one — so the DRM1 had the
button and the two Moogs did not, which read as a missing feature and was a
missing declaration.  That is the division working: an app that offers no stack
for a pattern is saying that pattern takes no contributions, and this one was
saying it by accident.

The pitches are the difference and the only one.  A euclidean rhythm on a kit
picks between ten voices; the same generator here picks between twenty-five
notes a Minitaur can reach, because that is what this grid's rows *are*.
"""

chord_recipe = _stack_for("chords", "chord_recipe", "Matriarch — stack", CHORD_ROWS,
                          pitch_notes=CHORD_NOTE_MAP)
"""And for the chords, where it is worth the most.

A grid of chords is the slowest thing on this rig to type in by hand — three
cells in a column, for every chord — and the catalogue is full of generators that
compute exactly that.  `arpeggio` in particular came fully drivable when #2155
landed upstream, so a chord written here can be arpeggiated by a generator rather
than drawn note by note.
"""

NOTES_RANGE = [midi_notes.note_to_name(note)
               for note in range(midi_notes.name_to_note("A0"), midi_notes.name_to_note("C8") + 1)]
"""A piano's eighty-eight keys to choose notes from, belonging to no instrument.

**A register of its own on purpose.**  This set is patched into a Minitaur that
reaches C1 to C3 and a Matriarch that reaches C3 to C5, and picking either of
their ranges would make the set look like it belonged to that one.  It is folded
into whichever instrument reads it (#2374), so a note chosen anywhere on it lands
in each instrument's own register and a wide pool costs nothing downstream.

**It was C3 to C5 until 2026-09-11** (#2389), and the panel drew all twenty-five
keys at once — thirty lattice cells.  Simon's decision was a whole keyboard seen
an octave at a time, so the range and the view changed together: narrowing the
range alone would have left notes already chosen outside it.
"""

NOTES_OPEN_AT = "C2"
"""Where the keyboard's octave of view begins: C2 to C3.

Between the two instruments the set feeds, which is why it is this rig's and not
the package's to say — a bass line and a lead line meet about here (Simon,
2026-09-11).
"""

notes = superconductor.subsequence_adapter.PitchSet(
	composition,
	name="notes",
	title="Notes",
	pitches={row: midi_notes.name_to_note(row) for row in NOTES_RANGE},
	about=[("feeds", "any generator that takes pitches")],
	opens_at=NOTES_OPEN_AT,
)
"""One set of notes, shared by everything patched to it.

**It plays nothing.**  It has no channel, no pattern and no note map of its own,
and the only way to hear it is to patch a generator's pitch parameter at it — at
which point that generator plays those notes, in its own instrument's register.

Two arpeggios patched here are the whole point: one set, two instruments, and no
way for them to drift apart because there is only one of it.
"""


shared_recipe = _stack_for("shared", "shared_recipe", "Shared — stack")
"""And on the grid with no instrument, which is the one that needed thought.

Every other stack is built by its own pattern function.  **This grid has none** —
it makes no sound until something routes it, and it is replayed as a *source*
inside whichever stack it is patched into (#2108).  So there is nowhere for a
`build` of its own to happen, and its generators run where the grid itself runs:
inside the pattern that borrowed it.

That is the honest place for them.  A generator on this stack contributes to
whatever this grid is currently feeding, which is exactly what the grid does, and
a grid patched into two instruments carries its generators to both.  Its pitches
are the DRM1's because that is what its rows are named after; a shared grid whose
rows meant something else would be a different declaration in this file.
"""

snare_recipe = _stack_for(
	"snare_lane", "snare_recipe", "Snare lane — stack", pitches=["snare"])
"""And on the lane that is one voice wide, where the pitches are the point.

**A stack's pitches are what make it different**, and here there is only one of
them.  Every generator offered on this lane writes snares, because that is what
the lane *is* — a euclidean added here cannot put a kick on it, and a pool that
could choose between ten voices would make the lane a kit again.

Note what this does not need: no channel, no note map, no pattern function.  The
lane is routed like any other instrument-less grid, and lands on the snare
because ``snare`` is the only row it has (#2228).
"""

nine_recipe = _stack_for(
	"nine", "nine_recipe", "Nine — stack", steps=NINE_STEPS)
"""And on the nine, where the *bounds* are the point.

Its pitches are the whole kit, exactly as pattern 1's are — the two patterns play
the same instrument and differ only in how long a cycle lasts.  What differs is
that every bound counting steps or beats is nine's rather than sixteen's, so a
euclidean here is offered up to nine pulses and a duration up to 2.25 beats.
Offering sixteen would be offering a control whose top half cannot land.
"""


def _make_grid (spec: dict[str, typing.Any]) -> typing.Any:
	"""Turn one asked-for grid into a control this rig can route (#2226).

	**Everything the package is not allowed to know is decided here** — how long
	a step lasts, what a row name means, and that a grid with no instrument
	behind it is played by being routed.  The rack holds a list and knows how
	long it is; this is where a list entry becomes a thing that can make a sound.
	"""

	key = str(spec["name"])

	composition.data.setdefault(key, {row: [] for row in spec["rows"]})

	def play (p: typing.Any) -> None:
		"""Put this grid's notes onto whatever routed it."""

		_play(p, composition.data[key])

	# Routable the moment it exists: a stack reads `sources` when it declares,
	# and the rack asks for a declaration as soon as it has made this.
	SHARED[key] = play

	return superconductor.subsequence_adapter.StepGrid(
		composition, rows=list(spec["rows"]), steps=int(spec["steps"]),
		beats=int(spec["steps"]) * STEP_DURATION,
		data_key=key, name=key,
		title=str(spec.get("title") or "Made"),
		about=[("", "no instrument")])


def _unmake_grid (name: str) -> None:
	"""Stop offering a grid that has gone, as a thing to route from.

	The notes stay in ``composition.data`` and are simply unreachable, which is
	the same thing a removed layer's parameters do; what must not stay is the
	*source*, or a stack goes on offering a cable to a grid nobody can see.
	"""

	SHARED.pop(name, None)


made_grids = superconductor.subsequence_adapter.GridRack(
	composition,
	make=_make_grid,
	unmake=_unmake_grid,
	rows=ROWS,

	# **Bounded by what a routed grid can actually play.**  A grid patched into a
	# pattern plays at the *destination's* resolution, so a twenty-step grid
	# routed into this rig's sixteen would be a truncated bar — a control that
	# looks set up and quietly drops four steps.  A cycle of a different length
	# is the other mechanism entirely, and it is a pattern rather than a grid
	# (#2228).
	steps=(1, STEPS),
	opening_steps=STEPS,
	data_key="made_grids", name="made_grids", title="Make a grid",
	about=[("", "no instrument")])
"""Grids this rig's panel can make for itself.

**Remembered with everything else a person makes**, in `PATTERN_FILE` (#2487), and
what is drawn on each comes back with it.  The list used to sit in a file of its
own beside this one, written from the clock loop onto the network share.

**What they cannot do yet is take generators.**  A stack is declared against the
pattern it builds, and nothing here declares one for a grid that did not exist
when this file was read.  A made grid is drawn on by hand and routed into a
pattern whose stack does the generating, which is enough to be useful and is
worth saying plainly rather than discovering.
"""


bass_grid = superconductor.subsequence_adapter.NoteGrid(
	composition, rows=BASS_ROWS, steps=STEPS, beats=BEATS,
	data_key="bass", name="bass", title="Minitaur — bass",
	relabel=_relabel(BASS_NOTE_MAP, MINITAUR),
	voices=_voice_count(MINITAUR),
	pattern="bass", divisions=BASS_DIVISIONS,
	about=[("ch", BASS_CHANNEL), ("", "Moog Minitaur")],
	default_length=BASS_LENGTH, default_velocity=BASS_VELOCITY,
	visible_rows=12)


chord_grid = superconductor.subsequence_adapter.NoteGrid(
	composition, rows=CHORD_ROWS, steps=STEPS, beats=BEATS,
	data_key="chords", name="chords", title="Matriarch — chords",
	relabel=_relabel(CHORD_NOTE_MAP, MATRIARCH),
	# The ceiling, through the guard that refuses to read an
	# unestablished polyphony as an unlimited one (#2172, #2142).
	voices=_voice_count(MATRIARCH, when_switchable=CHORD_VOICES),
	pattern="chords",
	about=[("ch", CHORD_CHANNEL), ("", "Moog Matriarch")],
	default_length=CHORD_LENGTH, default_velocity=CHORD_VELOCITY,
	visible_rows=12)
"""The two pitched patterns, named rather than built in place.

A pattern function has to read its grid's transposition when it builds, so the
grid has to be a thing this file can refer to (#2144).
"""


link = superconductor.subsequence_adapter.AppLink(
	composition,
	controls=[
		superconductor.subsequence_adapter.StepGrid(
			composition, rows=ROWS, steps=STEPS, beats=BEATS,
			data_key="grid", name="grid", title="DRM1 — pattern 1",
			about=[("ch", DRUM_CHANNEL), ("", "Vermona DRM1 MkIV")],
			pattern="drums"),
		# A grid with no instrument behind it: no channel, no note map, no
		# pattern function of its own. It makes no sound until something routes
		# it, and then it makes that thing's sound (#2108).
		superconductor.subsequence_adapter.StepGrid(
			composition, rows=ROWS, steps=STEPS, beats=BEATS,
			data_key="shared", name="shared", title="Shared — drums",
			about=[("", "no instrument")]),

		# The same mechanism as `shared`, one row wide. It lands on the snare
		# and nowhere else because `snare` is the only row it has, which is all
		# "route a lane to one voice" has ever meant here (#2228).
		superconductor.subsequence_adapter.StepGrid(
			composition, rows=["snare"], steps=STEPS, beats=BEATS,
			data_key="snare_lane", name="snare_lane", title="Snare lane",
			about=[("", "no instrument")]),

		# And the other mechanism, beside it: not a routed grid but a pattern of
		# its own, nine steps against the sixteen. Drawn narrower than its
		# neighbours because it *is* narrower, which is the thing that makes a
		# polyrhythm legible on a page rather than only audible in a room.
		superconductor.subsequence_adapter.StepGrid(
			composition, rows=ROWS, steps=NINE_STEPS, beats=NINE_BEATS,
			data_key="nine", name="nine", title="DRM1 — nine",
			about=[("ch", DRUM_CHANNEL), ("", "2.25 beats")],
			pattern="nine"),
		bass_grid,
		chord_grid,
		superconductor.subsequence_adapter.Params(
			composition,
			parameters=[
				superconductor.subsequence_adapter.Parameter(
					"voicing", "action", label="Set voicing", group="Keyboard",
					# Lowest first, and labelled with the count rather than the
					# band name: "1" is what is written beside the switch on the
					# instrument, and `one_voice` is not.
					options=[(band, str(count))
					         for count, band in sorted(CHORD_VOICING.items())]),

				# Every other control the definition knows, in the instrument's
				# own order and under the instrument's own section names.  The
				# voicing above is skipped here because it is an action rather
				# than a setting and is built by hand.
				*(_panel_parameter(*setting, instrument=MATRIARCH)
				  for setting in CHORD_SETTINGS if setting[0] != "voices"),
			],
			data_key="matriarch", name="matriarch", title="Matriarch — settings",
			about=[("ch", CHORD_CHANNEL), ("", "Moog Matriarch")],
			configures="chords",
			on_change=send_chord_setting),
		superconductor.subsequence_adapter.Params(
			composition,
			parameters=[
				*(_panel_parameter(*setting) for setting in BASS_SETTINGS),

				# The specification's own switch rather than the Minitaur's, so
				# it comes from `pymididefs.cc` and not from the definition.
				superconductor.subsequence_adapter.Parameter(
					LOCAL_CONTROL, "switch", label="Front panel controls", default=True),
			],
			data_key="minitaur", name="minitaur", title="Minitaur — settings",
			about=[("ch", BASS_CHANNEL), ("", "Moog Minitaur")],
			# **No sections, and that is the demonstration.** Nine controls read
			# as a list; thirty-six do not. A heading is offered where it earns
			# its place and left out where it would be ceremony.
			configures="bass",
			on_change=send_setting),
		drum_recipe,
		bass_recipe,
		chord_recipe,
		shared_recipe,
		snare_recipe,
		nine_recipe,
		notes,
		made_grids,
		superconductor.subsequence_adapter.Transport(composition),
	],
	pages=[
		# Everything that makes a sound, on one page.  The voicing button is
		# here because without it this page cannot be played: a Matriarch sounds
		# MIDI notes monophonically until its voice mode is asserted over MIDI,
		# whatever the front panel says (#2177), so a chord grid beside a bass
		# and a kit would quietly play one note at a time.
		superconductor.subsequence_adapter.Page(
			"band", parts=["grid", "bass", "chords", "matriarch"], title="Band"),
		# **One set of notes, both stacks that can read it, and both patterns
		# they write into** — which is the whole of what this page is for: patch
		# the arpeggios on either side of it at the same notes and hear two
		# instruments play them (#2374).
		#
		# **The patterns are here so both kinds of connection are on one page.**
		# Without them the page showed generators feeding nothing, and the only
		# line on it was the patch cable — so the distinction the panel is built
		# on could not be seen at all.  A generator is tied to the one pattern it
		# builds and is drawn as a taut wired line with square lugs; a note set
		# exists on its own and feeds as many inputs as it likes, and is drawn as
		# a sagging cable with a plug and a socket (#2119).  Simon, 2026-09-10:
		# *"anything which is tied is indicated by a solid routing line, anything
		# flexible and independent by a patch cable."*
		superconductor.subsequence_adapter.Page(
			"notes",
			parts=["notes", "bass", "bass_recipe", "chords", "chord_recipe"],
			title="Notes"),

		# The DRM1 with the things that write into it and the things that can be
		# patched to it: generators, cables, and a grid with no instrument behind
		# it.  All of the routing this rig can currently show is on this page.
		superconductor.subsequence_adapter.Page(
			"drums", parts=["grid", "drum_recipe", "shared", "shared_recipe",
			                "snare_lane", "snare_recipe", "nine", "nine_recipe",
			                "made_grids"],
			title="Drums"),

		superconductor.subsequence_adapter.Page(
			"bass", parts=["bass", "bass_recipe", "minitaur"], title="Bass"),
		superconductor.subsequence_adapter.Page(
			"chords", parts=["chords", "chord_recipe", "matriarch"], title="Chords"),
	],
	page_store=superconductor.subsequence_adapter.PageStore(
		pathlib.Path(__file__).with_suffix(".pages.json")),
	pattern_store=superconductor.subsequence_adapter.PatternStore(PATTERN_FILE),
	url=SERVICE_URL,
)
"""Five views over this rig, where their arrangement is kept, and where what is
made on them is.

**After the first edit on the glass this file is not the score** (#2067, #2487).
Every pattern, stack, setting and mute is put back from `PATTERN_FILE` on each
start, and `OPENING_PATTERN` and every other opening value here apply only where
the store holds nothing — which is the trade #2067 named, taken knowingly.

The arrangement file sits beside this one and is written by the adapter when a
finger lifts from a block that moved.  It is data rather than code because there
is no safe way to write a dragged block back into a Python file, and it is beside
the composition rather than inside the service because a page set belongs to the
piece that declared it (Subroutine #2075).

**One page per instrument, and one with all three on it.**  Every pattern appears
twice — once beside whatever it plays against, and once with the controls that
belong to it — which is the case worth having: see how they play together, then
take one on its own to work on it closely.  Nothing keeps two views of a pattern
in step, because nothing has to: both draw the grid the composition holds.

**There were eight, and eight was one problem rather than three extra pages.**
The client draws named page buttons up to `PAGE_BUTTONS`, which is six, and gives
way to previous-and-next above it — so the rig had been showing "‹ Pattern 1 1/8
›" and no page names at all, which is the one thing a page selector is for.  Six
of the eight were a pattern on its own beside the same pattern in company, and
the second of each is the one worth keeping.
"""


if __name__ == "__main__":
	link.start()

	# `play()` returns on Ctrl-C and on a polite kill alike, and `stop` writes down
	# whatever the store had not yet (#2487).
	try:
		composition.play()

	finally:
		link.stop()
