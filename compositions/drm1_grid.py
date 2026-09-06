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

MINITAUR_CC = {
	"glide": 65,
	"glide_rate": 5,
	"glide_type": 92,
	"legato_glide": 83,
	"note_sync": 81,
	"filter_velocity": 89,
	"volume_velocity": 90,
	"key_priority": 91,
	"volume": 7,
	"local_control": 122,
}
"""Which control change each panel setting is wired to.

Taken from the Minitaur's own manual and written up as Subroutine #2081.  It
lives here rather than in the Superintendent package because it is a fact about
an instrument, and that package is not allowed to know one — a panel draws a
switch and this file decides what the switch does.

Every one of these except ``glide`` and ``glide_rate`` is a parameter the
Minitaur has no knob for at all, which is what makes them worth a panel: they
are otherwise reachable only through the editor software.
"""

MINITAUR_BANDS = {
	"glide_type": {"lcr": 0, "lct": 64, "exp": 110},
	"key_priority": {"low": 0, "high": 64, "last": 110},
}
"""Where in each band to sit for a choice, since the Minitaur reads ranges.

The middle of the band rather than its edge, so a value that drifts by one does
not become a different setting.
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

def _cc_value (name: str, value: typing.Any) -> int:
	"""What number the Minitaur wants for a setting the panel expressed in words."""

	if name in MINITAUR_BANDS:
		return MINITAUR_BANDS[name][value]

	if isinstance(value, bool):
		return 127 if value else 0

	# Local control is the MIDI specification's own switch and takes only 0 or
	# 127 — no band, no midpoint (#2081).

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

	control = MINITAUR_CC[name]
	amount = _cc_value(name, value)

	composition.trigger(
		lambda p, control=control, amount=amount: p.cc(control, amount),
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
			data_key="bass", name="bass", title="Minitaur — bass", voices=1,
			pattern="bass", divisions=BASS_DIVISIONS,
			about=[("ch", BASS_CHANNEL), ("", "Moog Minitaur")],
			default_length=BASS_LENGTH, default_velocity=BASS_VELOCITY,
			visible_rows=12),
		superintendent.subsequence_adapter.Params(
			composition,
			parameters=[
				superintendent.subsequence_adapter.Parameter(
					"glide", "switch", label="Glide"),
				superintendent.subsequence_adapter.Parameter(
					"glide_rate", "number", label="Glide rate", default=24),
				superintendent.subsequence_adapter.Parameter(
					"glide_type", "choice", label="Glide type", default="lcr",
					options=[("lcr", "LCR"), ("lct", "LCT"), ("exp", "EXP")]),
				superintendent.subsequence_adapter.Parameter(
					"legato_glide", "switch", label="Legato glide only"),
				superintendent.subsequence_adapter.Parameter(
					"note_sync", "switch", label="Note sync"),
				superintendent.subsequence_adapter.Parameter(
					"filter_velocity", "number", label="Velocity to filter", default=64),
				superintendent.subsequence_adapter.Parameter(
					"volume_velocity", "number", label="Velocity to volume", default=64),
				superintendent.subsequence_adapter.Parameter(
					"key_priority", "choice", label="Note priority", default="last",
					options=[("low", "Low"), ("high", "High"), ("last", "Last")]),
				superintendent.subsequence_adapter.Parameter(
					"volume", "number", label="Output level", default=127),
				superintendent.subsequence_adapter.Parameter(
					"local_control", "switch", label="Front panel controls", default=True),
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
