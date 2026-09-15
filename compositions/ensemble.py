"""Seven instruments on four pages, and nothing playing until somebody plays it.

**A rig that starts from nothing** (Simon, 2026-09-14).  Every pattern here opens
empty: no seeded steps, no generators, no routes, no cables, no note set.  What
the glass holds after the first minute is what somebody put there, which is the
whole of what this file is for — `drm1_grid.py` beside it is the demonstration
rig, and keeps the routed lane, the polyrhythm and the grid rack that show what
the panel can do.  **What a person makes here comes from racks**: a set of pitches
or of degrees to feed generators, and a line to feed instruments (#2108, #2527).

**Everything about this particular studio lives in this file**: which interface
each instrument is plugged into, which channel it listens on, and which register
its grid is drawn over.  The Superconductor package knows none of it and another
studio is another copy of this file (#1465).

**One table rather than seven copies of the same eighty lines.**  `INSTRUMENTS`
below is the whole of what this rig is; everything after it is the same loop run
over each entry.  Adding an eighth instrument is a row in that table, and taking
one out is deleting one.

**What a definition says and what this file says are kept apart.**  The
definition is a report about a model — which controls it has, which notes it can
sound, how many at once — and is read from `pymidiinstrumentdefs`.  The register a
grid is *drawn over* is a preference of this rig's, and is checked against the
instrument's limit rather than derived from it (#2121): outside its range an
instrument is silent rather than wrong-sounding, so nothing else would tell you.
"""

import collections.abc
import dataclasses
import inspect
import pathlib
import typing

import pymidiinstrumentdefs

import subsequence
import subsequence.constants.durations
import subsequence.constants.midi_notes as midi_notes
import subsequence.intervals
import subsequence.pattern_builder

import superconductor.subsequence_adapter as adapter


# --- This rig -------------------------------------------------------------

MIDI_PORT = "*U6MIDI Pro Port 1*"
"""The interface every instrument here is plugged into.

A pattern rather than the full name, because ALSA renumbers its clients when the
set of attached devices changes: a port was ``16:0`` before a reboot and ``20:0``
after one.  Subsequence matches a name with wildcards as a glob, so this survives
the renumbering.

**One port and seven channels**, confirmed by Simon on 2026-09-14.  A rig whose
instruments are spread across ports says so per instrument instead: a pattern
takes ``device=`` and Subsequence will open as many outputs as are named.
"""

SERVICE_URL = "ws://127.0.0.1:8090/ws/app"
"""The Superconductor service, running on this machine."""

PATTERN_FILE = pathlib.Path.home() / "superconductor-ensemble.patterns.json"
PAGE_FILE = pathlib.Path.home() / "superconductor-ensemble.pages.json"
"""Where what is made on the glass is kept between starts (#2487, #2075).

**On this machine's own disk and not beside this file**, which sits on a network
share where a write can wedge the process making it (nuc14 #2438) — and both of
these are written every time somebody stops tapping or lets go of a block.  A
composition on local disk would say ``PatternStore.beside(__file__)``.

**Its own pair, not the ones `drm1_grid.py` writes.**  Two compositions sharing a
store would each put back the other's patterns under its own control names, which
is how a rig comes up holding something nobody made.
"""


# --- Time, which every pattern here keeps ---------------------------------

STEPS = 16
BEATS = 4.0
STEP_DURATION = subsequence.constants.durations.SIXTEENTH
"""A bar of sixteenths, which is what every grid on this rig counts in.

One number for all of them on purpose: a pattern that steps differently from its
neighbours is worth having and is what `drm1_grid.py`'s nine-step grid is for.
This rig starts them all the same so that *changing* one is the interesting thing
rather than the starting condition.
"""

DIVISIONS = 6
"""How many places a pitched grid keeps to a step, so a note can start between two.

Six, because a sixteenth is six pulses of a 24-PPQN clock and a position finer
than a pulse is one the sequencer cannot place.  A drum grid keeps one place to a
step: a hit lands on the step or it is a different step.
"""

VELOCITY = 100
"""How hard a step is struck when it is first placed, and what two taps put it back to."""

HIT_DURATION = 1 / 24
"""A drum hit is a trigger rather than a note held, so it is one pulse long."""

NOTE_LENGTH = DIVISIONS
"""How long a pitched note is when it is first placed, in positions — one step."""

VARIANTS = ("A", "B", "C", "D")
LANDS_EVERY = 1
"""Four versions of every pattern, each landing at the next cycle (#2485, #2489).

The same four letters on every grid, which is what lets a scene be *cue B on
everything*.
"""

KEEPS_A_STEP = "steps" in inspect.signature(
	subsequence.pattern_builder.PatternBuilder.set_length).parameters
"""Whether this Subsequence can make a pattern a number of its own steps long (#2546).

**A length is offered on the glass only where it can be kept in steps** (#2548):
`set_length` in beats spreads a pattern's steps over the new length, so a grid
shortened to twelve would be squeezed into three beats rather than losing four.
"""

MIN_STEPS = 1 if KEEPS_A_STEP else None
"""The fewest steps a pattern here may play.

One: a pattern must be at least as long as its reschedule lookahead, which is one
pulse here, and a sixteenth is six.  Subsequence refuses anything shorter.
"""


def _resize (p: typing.Any, steps: int) -> None:
	"""Make the pattern being built *steps* of its own steps long (#2548)."""

	p.set_length(steps=steps)


RESIZE = _resize if KEEPS_A_STEP else None


# --- What is in the room --------------------------------------------------

@dataclasses.dataclass (frozen=True)
class Instrument:
	"""One instrument, as this rig has it.

	``key`` is what the panel addresses and what the store keys its patterns by,
	so it is chosen once and not tidied later: renaming one silently empties
	whatever it was holding.

	``low`` and ``high`` bound the register this instrument's grid is *drawn*
	over, and are this file's choice rather than the instrument's limit — a
	Matriarch reaches the whole of MIDI and is drawn over two octaves here.  A
	drum machine has no register: its rows are its voices, which the definition
	names.

	``settings`` is which of the definition's controls are worth glass, in the
	order they should read, as ``(on the panel, in the definition, label, opens
	at, section)``.  **A subset on purpose**: the TR-8S declares fifty-five
	controls and a block of fifty-five rows is a list nobody reads.  An
	instrument whose definition declares none — a Model D, a Malevolent — gets a
	pattern and no settings block, which is honest rather than a gap: they are
	all-knobs synths with nothing to send.

	``voices`` is how many notes the grid lets sound at once where the definition
	cannot say, and is refused rather than guessed (see `_voice_count`).
	"""

	key: str
	definition: str
	channel: int
	title: str
	about: str
	low: str | None = None
	high: str | None = None
	opens_at: str | None = None
	visible_rows: int | None = None
	settings: tuple[tuple[str, str, str, typing.Any, str | None], ...] = ()
	voices: int | None = None
	part: str | None = None
	asserted: tuple[str, typing.Any] | None = None
	"""One setting sent once at the start, where the instrument cannot play without it.

	**Not an opening pattern by another name.**  This rig seeds no music at all;
	this is the instrument being put into a state where the music somebody writes
	can be heard — a Matriarch sounds a chord as one note until its voice mode is
	asserted over MIDI, whatever its front panel says (#2177).

	Sent once per run rather than every cycle.  Every cycle would be three bytes a
	bar and would survive somebody moving the switch mid-session, but it would
	insist, continuously, on overriding a control the person can see and may have
	reached for on purpose.
	"""

	@property
	def drums (self) -> bool:
		"""Whether its rows are voices rather than pitches, which the definition says."""

		return not self.low


MINITAUR_SETTINGS = (
	# on the panel      in the definition               label               opens at  section
	("glide",           "glide_switch",                 "Glide",            False,    "Glide"),
	("glide_rate",      "glide_rate",                   "Glide rate",       24,       "Glide"),
	("glide_type",      "glide_type",                   "Glide type",       "lcr",    "Glide"),
	("filter_velocity", "filter_velocity_sensitivity",  "Filter velocity",  64,       "Velocity"),
	("volume_velocity", "volume_velocity_sensitivity",  "Volume velocity",  64,       "Velocity"),
)
"""Four of the Minitaur's thirty-seven, which are the ones with no knob on the front.

The rule for every table here: a control the instrument already puts under a hand
is not worth a row on the glass — what is worth glass is what the panel is the
only way to reach (#2081).
"""

MATRIARCH_SETTINGS = (
	("voicing",    "paraphony_voice_mode", "Voicing",     "four_voice", "Keyboard"),
	("glide",      "glide_on",             "Glide",       False,        "Keyboard"),
	("glide_time", "glide_time",           "Glide time",  0,            "Keyboard"),
	("arp",        "arp_play",             "Arpeggiator", False,        "Arpeggiator"),
	("arp_mode",   "arp_mode",             "Mode",        "arp",        "Arpeggiator"),
	("arp_range",  "arp_range",            "Range",       "one",        "Arpeggiator"),
	("arp_rate",   "arp_rate",             "Rate",        64,           "Arpeggiator"),
)
"""Seven of the Matriarch's thirty-six, grouped because seven reads as a list and
thirty-six does not.

**Voicing is first because without it this instrument cannot play a chord.**  A
Matriarch sounds incoming MIDI notes one at a time until its voice mode is
asserted over MIDI, whatever the front-panel switch says (#2177, measured on this
rig) — so a chord grid feeding it plays a monophonic line and nothing says why.
It is asserted once at each start as well as being on the glass, which is
`ASSERTED` below.
"""

TR8S_SETTINGS = (
	("accent",   "accent",         "Accent",   64, "Kit"),
	("shuffle",  "shuffle",        "Shuffle",  0,  "Kit"),
	("reverb",   "reverb_level",   "Reverb",   0,  "Effects"),
	("delay",    "delay_level",    "Delay",    0,  "Effects"),
	("delay_time",     "delay_time",     "Delay time",     64, "Effects"),
	("delay_feedback", "delay_feedback", "Delay feedback", 64, "Effects"),
)
"""Six of the TR-8S's fifty-five: the ones that shape the whole kit rather than one voice.

**The other forty-nine are four controls on each of eleven voices** — tune, decay,
level and ctrl per drum — and they belong beside the voice rather than in one list
of forty-nine rows.  Which is a real question for the glass and not one to answer
by dumping the lot: a block of fifty-five rows is a list nobody reads.
"""

STREICHFETT_SETTINGS = (
	("registration", "string_registration",   "Registration", "both", "Strings"),
	("octaves",      "string_octaves",        "Octaves",      64,     "Strings"),
	("ensemble",     "string_ensemble",       "Ensemble",     64,     "Strings"),
	("release",      "string_release",        "Release",      64,     "Strings"),
	("solo_tone",    "solo_tone",             "Tone",         64,     "Solo"),
	("solo_attack",  "solo_attack",           "Attack",       0,      "Solo"),
	("solo_decay",   "solo_decay",            "Decay",        64,     "Solo"),
	("solo_tremolo", "solo_tremolo",          "Tremolo",      0,      "Solo"),
	("balance",      "balance",               "Balance",      64,     None),
	("fx_type",      "fx_type",               "Effect",       "reverb", "Effect"),
	("fx_amount",    "fx_reverb_amount",      "Amount",       64,     "Effect"),
)
"""**Both sections, on the strings block, because one channel receives them all.**

The solo section is a separate part that sounds on the channel above the base one
— and it takes *notes* there and nothing else.  Every one of the Streichfett's
nineteen controls is unparted in the definition, which is that format's way of
saying *the base channel*, so the solo voice's tone and attack are set on channel
2 while its notes are played on 3.

**Measured on this rig before the definition said it** (#2544): control changes
76, 70 and 77 sent to the channel above the base moved nothing at all.  The two
agreeing is why this block sits on the strings pattern and carries both sections.
"""


INSTRUMENTS = (
	Instrument(
		key="drm1", definition="vermona/drm1_mkiv", channel=10,
		title="Vermona DRM1", about="Vermona DRM1 MkIV"),
	Instrument(
		key="tr8s", definition="roland/tr8s", channel=11,
		title="Roland TR-8S", about="Roland TR-8S", settings=TR8S_SETTINGS),
	Instrument(
		key="minitaur", definition="moog/minitaur", channel=6,
		title="Moog Minitaur", about="Moog Minitaur",
		low="C1", high="C3", settings=MINITAUR_SETTINGS),
	Instrument(
		key="model_d", definition="behringer/model_d", channel=4,
		title="Behringer Model D", about="Behringer Model D",
		low="C1", high="C4", opens_at="C2", visible_rows=12),
	Instrument(
		key="malevolent", definition="pwm/malevolent", channel=9,
		title="PWM Malevolent", about="PWM Malevolent",
		low="C2", high="C5", opens_at="C3", visible_rows=12),
	Instrument(
		key="matriarch", definition="moog/matriarch", channel=1,
		title="Moog Matriarch", about="Moog Matriarch",
		low="C3", high="C5", visible_rows=12, settings=MATRIARCH_SETTINGS,
		# **Told rather than guessed** (#2143): a Matriarch's voicing is a
		# front-panel switch with no documented power-on default, and a grid
		# handed "unknown" as "unlimited" draws a five-note chord on a four-voice
		# instrument and says nothing.
		voices=4,
		asserted=("paraphony_voice_mode", "four_voice")),
	Instrument(
		key="strings", definition="waldorf/streichfett", channel=2,
		title="Streichfett — Strings", about="Waldorf Streichfett",
		low="C2", high="C5", opens_at="C3", visible_rows=12,
		settings=STREICHFETT_SETTINGS, part="strings"),
	Instrument(
		key="solo", definition="waldorf/streichfett", channel=3,
		title="Streichfett — Solo", about="Waldorf Streichfett",
		low="C3", high="C6", opens_at="C4", visible_rows=12, part="solo"),
)
"""The room, in the order the ensemble page draws it.

**The Streichfett is two instruments here and one in the rack.**  Its definition
declares two parts — `strings` on the base channel and `solo` one above it — and
Superconductor reads no part yet, so this file places them by hand as two
patterns on channels 2 and 3.  That is where a rig fact belongs anyway: the
definition reports that the instrument has two parts, and only this file knows
which channel its base is set to.
"""


# --- Reading a definition -------------------------------------------------

DEFINITIONS = {one.key: pymidiinstrumentdefs.load(one.definition) for one in INSTRUMENTS}
"""Read once, at import, and never on the clock loop."""


def _voice_count (definition: typing.Any, *, told: int | None = None) -> int | None:
	"""How many notes a grid should let sound at once, from what a definition says.

	**Not a pass-through, and that is the whole point of it.**  A definition's
	``polyphony`` of ``None`` means *nobody has established it*; a note grid's
	``voices`` of ``None`` means *as many as you like*.  Handing one straight to
	the other turns "unknown" into "unlimited".

	So a stated count is used; an instrument that switches between counts has to
	be *told* which to assume; and only one that states neither is unlimited.
	"""

	voice = definition.voice

	if voice.polyphony is not None:
		return int(voice.polyphony)

	if voice.voicing_modes:
		if told is None:
			raise ValueError(
				f"{definition.model.name} switches between {list(voice.voicing_modes)} "
				f"voices and states no default, so a grid has to be told which to assume")

		if told not in voice.voicing_modes:
			raise ValueError(
				f"{definition.model.name} has no {told}-voice mode; "
				f"it offers {list(voice.voicing_modes)}")

		return told

	return None


def _part_polyphony (instrument: Instrument) -> int | None:
	"""What one part of a many-part instrument sounds at once, where it says.

	A part states its own polyphony and it is not the instrument's: a
	Streichfett's strings take 128 notes and its solo eight, which is a real
	difference on the glass — the solo grid refuses a ninth note in a column and
	the strings grid never has to.
	"""

	definition = DEFINITIONS[instrument.key]

	if instrument.part:
		part = definition.parts.get(instrument.part)

		if part is None:
			raise ValueError(
				f"{definition.model.name} has no part called {instrument.part!r}; "
				f"it has {list(definition.parts)}")

		if part.polyphony is not None:
			return int(part.polyphony)

	return _voice_count(definition, told=instrument.voices)


def _channel_for (instrument: Instrument) -> int:
	"""The channel this instrument's part actually listens on, checked against its own offset.

	**A part says how far above the base channel it sits**, and this file says
	where the base is — so the two can be checked against one another rather than
	one being derived from the other.  A Streichfett on base channel 2 puts its
	solo on 3, and a table saying otherwise is a table to fix.
	"""

	if not instrument.part:
		return instrument.channel

	definition = DEFINITIONS[instrument.key]
	part = definition.parts[instrument.part]
	base = next(one for one in INSTRUMENTS
	            if one.definition == instrument.definition and one.part
	            and definition.parts[one.part].channel_offset == 0)

	# **An offset of null is not an offset of zero**: a part that has not said
	# where it sits cannot be checked against anything, and a rig that assumed
	# zero would put two parts on one channel and sound like a broken instrument.
	if part.channel_offset is None:
		raise ValueError(
			f"{definition.model.name}'s {instrument.part} part does not say how far "
			f"above the base channel it sits, so {instrument.key}'s channel cannot be checked")

	wanted = base.channel + int(part.channel_offset)

	if wanted != instrument.channel:
		raise ValueError(
			f"{instrument.key} is set to channel {instrument.channel}, but "
			f"{definition.model.name}'s {instrument.part} part sits "
			f"{part.channel_offset} above its base of {base.channel}, which is {wanted}")

	return instrument.channel


def _register (instrument: Instrument) -> list[str]:
	"""The notes this instrument's grid is drawn over, checked against what it can sound.

	**A limit is the model's and a preference is this rig's** (#2121).  Outside
	its range an instrument is silent rather than wrong-sounding, so a register
	set an octave too high draws a grid that works perfectly and makes no sound —
	which is worth an exception at import, where somebody is looking.

	Skipped where the definition states no range, because an instrument nobody has
	measured is not the same as one measured as unlimited.
	"""

	assert instrument.low and instrument.high

	low = midi_notes.name_to_note(instrument.low)
	high = midi_notes.name_to_note(instrument.high)
	register = [midi_notes.note_to_name(note) for note in range(low, high + 1)]

	definition = DEFINITIONS[instrument.key]
	sounds = definition.voice.note_range

	if sounds is not None and not all(sounds[0] <= midi_notes.name_to_note(row) <= sounds[1]
	                                  for row in register):
		raise ValueError(
			f"{instrument.key} is drawn over {instrument.low} to {instrument.high}, which goes "
			f"outside what a {definition.model.name} can sound (notes {sounds[0]} to "
			f"{sounds[1]}); outside it the instrument is silent rather than wrong-sounding, "
			f"so nothing else would tell you")

	return register


def _rows (instrument: Instrument) -> list[str]:
	"""What this instrument's grid has for rows, drawn in the order they appear.

	A drum machine's are its voices, in the order the definition lists them; a
	pitched instrument's are its notes, **highest first**, so the grid reads the
	way a stave does and a rising line rises.
	"""

	if instrument.drums:
		return list(DEFINITIONS[instrument.key].voice.voices)

	return list(reversed(_register(instrument)))


def _note_map (instrument: Instrument) -> dict[str, int]:
	"""Row names to MIDI notes, which is one mechanism whether they are drums or pitches.

	Subsequence resolves a string pitch through whatever map its pattern was
	given, and nothing about that map has to be about drums.
	"""

	if instrument.drums:
		return dict(DEFINITIONS[instrument.key].voice.voices)

	return {row: midi_notes.name_to_note(row) for row in _register(instrument)}


def _panel_parameter (instrument: Instrument, panel: str, named: str, label: str,
                      default: typing.Any, group: str | None) -> adapter.Parameter:
	"""One of an instrument's controls, as something the panel knows how to draw.

	The definition says what the control *is*; this says what it is called here.
	**A kind is derived from the bands rather than declared** — no states means a
	continuous control, two a switch, three or more a choice — so a corrected band
	table changes the drawing without this file being touched.

	A control the instrument only *transmits* is not something to send, and a
	definition says so: offered here it would be a row on the glass that moves
	nothing and says nothing about it, so a table naming one fails at import.
	"""

	definition = DEFINITIONS[instrument.key]
	control = definition.controls.get(named)

	if control is None:
		raise ValueError(
			f"{definition.model.name} has no control called {named!r}, which "
			f"{instrument.key}'s settings ask for")

	if not control.is_sendable:
		raise ValueError(
			f"{panel} is the {definition.model.name}'s {named}, which it transmits and "
			f"does not receive, so nothing the panel sent would reach it")

	if control.kind == pymidiinstrumentdefs.CHOICE and control.states:
		return adapter.Parameter(
			panel, "choice", label=label, default=default, group=group,
			options=[(state, state.replace("_", " ")) for state in control.states])

	if control.kind == pymidiinstrumentdefs.SWITCH:
		return adapter.Parameter(panel, "switch", label=label, default=default, group=group)

	low, high = control.range

	return adapter.Parameter(
		panel, "number", label=label, default=default, group=group,
		minimum=low, maximum=high)


def _cc_value (instrument: Instrument, named: str, value: typing.Any) -> int:
	"""What number the instrument wants for a setting the panel expressed in words.

	The definition computes the **middle** of each band rather than its edge, so a
	value that drifts by one does not become a different setting.  A control whose
	manual prints exact numbers is sent exactly those, and the definition knows
	which shape it holds, so this does not have to.
	"""

	control = DEFINITIONS[instrument.key].controls[named]

	if control.states:
		if isinstance(value, bool):
			# **A switch's two states in the order the definition gives them**,
			# which is ascending, so the second is the far end.  It is not always
			# spelled "on": legato glide is `always` and `legato_only`, and the
			# panel's own label is what says which way round that reads.
			value = control.states[1] if value else control.states[0]

		return int(control.value_for(value))

	return int(value)


# --- The composition ------------------------------------------------------

composition = subsequence.Composition(output_device=MIDI_PORT, bpm=120)

for _one in INSTRUMENTS:
	composition.data[_one.key] = {}
	_channel_for(_one)


def _places (steps: int) -> adapter.Positions:
	"""Every place a note may start in a pattern this long, in each unit an app counts in (#2412).

	**The same places twice.**  A sixteen-step bar has sixteen of them; asked for
	in `steps` they are 0 to 15 and asked for in `beats` they are 0 to 3.75, and
	which a generator wants is on its own declaration.
	"""

	subdivisions = max(1, round(1 / STEP_DURATION))

	def counted (at: int) -> str:
		beat, inside = divmod(at, subdivisions)

		return f"{beat + 1}" if inside == 0 else f"{beat + 1}.{inside + 1}"

	return {
		"steps": [(at, str(at + 1)) for at in range(steps)],
		"beats": [(at * STEP_DURATION, counted(at)) for at in range(steps)],
	}


SOURCES: dict[str, collections.abc.Callable[[typing.Any], None]] = {}
"""What any stack here may route from, and how to play each — one map for all of them.

**Empty at the start**, which is *from nothing* holding for cables as well as notes:
a stack offers a route only where there is something to route from.  A line made on
the glass adds itself (`_make_line`) and a line taken away removes itself, and
because every stack holds this map rather than a copy of it (#2421) each of them
offers the line the moment it exists.

**Turning a grid into notes is this file's business, so the function is this
file's** (#1465, #2108); the package routes and does not look inside.  Annotated
rather than inferred, because a dict is invariant in its value type.
"""


def _stack_for (instrument: Instrument) -> typing.Any:
	"""A stack of contributions that build this instrument's pattern.

	``pitches`` is what this pattern's rows *are*, and it is the whole of what
	makes a stack on a bassline different from a stack on a kit: the catalogue
	knows a parameter is a pitch and cannot know which pitches exist, and only
	this file knows that one grid's rows are a DRM1's voices and another's are
	notes a Minitaur can reach (#1465, #2085).
	"""

	rows = _rows(instrument)

	return adapter.Recipe(
		composition,
		# **Subsequence's own description of itself**, handed along and named
		# nowhere here: this file knows which pitches exist and the catalogue
		# knows that a parameter is a pitch, and neither knows the other (#2085).
		catalogue=subsequence.generators(),
		transforms=subsequence.transforms(),
		pitches=rows,
		pitch_notes=None if instrument.drums else _note_map(instrument),
		positions=_places(STEPS),
		bounds={
			"pulses": (0, STEPS),

			# **Named with its unit, because one word covers two meanings**
			# (#2413).  `grid` is on eight of Subsequence's entries: seven mean
			# *how many slots the pattern has* and `swing.grid` means *grid size
			# in beats*, opening at 0.25 — which this range would forbid.
			("grid", "steps"): (1, STEPS),
			"subdivisions": (1, 8),
			"duration": (0.05, BEATS),

			# **Two bounds about cost rather than about music** (#2231).  A stack
			# builds on the clock loop, and an overrunning rebuild is not a late
			# bar: the loop accumulates and then dispatches every missed pulse in
			# one pass, so it comes out as a burst.
			"steps": (100, 5000),
		},
		builds=instrument.key,
		sources=SOURCES,
		pulses_per_beat=subsequence.constants.MIDI_QUARTER_NOTE,
		data_key=f"{instrument.key}_recipe",
		name=f"{instrument.key}_recipe",
		title=f"{instrument.title} — stack")


def _grid_for (instrument: Instrument) -> typing.Any:
	"""The grid this instrument is played from: voices for a drum machine, notes for the rest."""

	rows = _rows(instrument)
	shared = {
		"composition": composition, "rows": rows, "steps": STEPS, "beats": BEATS,
		"data_key": instrument.key, "name": instrument.key, "pattern": instrument.key,
		"title": instrument.title,
		"about": [("ch", instrument.channel), ("", instrument.about)],
		"variants": VARIANTS, "lands_every": LANDS_EVERY,
		"default_velocity": VELOCITY, "min_steps": MIN_STEPS, "resize": RESIZE,
	}

	if instrument.drums:
		return adapter.StepGrid(**shared)

	return adapter.NoteGrid(
		**shared, divisions=DIVISIONS, default_length=NOTE_LENGTH,
		voices=_part_polyphony(instrument),
		visible_rows=instrument.visible_rows,
		opens_at=instrument.opens_at)


GRIDS = {one.key: _grid_for(one) for one in INSTRUMENTS}
STACKS = {one.key: _stack_for(one) for one in INSTRUMENTS}


def _send (instrument: Instrument) -> collections.abc.Callable[[str, typing.Any], None]:
	"""How this instrument's settings block puts one setting on the wire.

	``trigger`` with ``quantize=0`` puts a one-shot pattern at the current pulse
	rather than at the next cycle, so a switch takes effect within a pulse — about
	21 ms at 120 BPM — instead of waiting up to a bar.  It is also the only public
	way into Subsequence's clock from another thread, and it takes the send lock
	that a direct write to the port would not.

	A setting moved before the composition is playing is kept in
	``composition.data`` and not sent, because there is no clock to send it on.
	"""

	named = {panel: definition for panel, definition, _, _, _ in instrument.settings}
	channel = instrument.channel

	def send (name: str, value: typing.Any) -> None:
		definition = named.get(name)

		if definition is None:
			return

		number = DEFINITIONS[instrument.key].controls[definition].cc
		amount = _cc_value(instrument, definition, value)

		composition.trigger(
			lambda p, control=number, level=amount: p.cc(control, level),
			channel=channel, beats=1 / 24, quantize=0)

	return send


def _settings_for (instrument: Instrument) -> typing.Any | None:
	"""This instrument's front panel, where it has one worth glass.

	**None where the definition declares no controls**, which is a Model D and a
	Malevolent: they are all-knobs synths with nothing to receive, and a block of
	no rows is worse than no block.  The panel loses a control rather than drawing
	a broken one (#2046).
	"""

	if not instrument.settings:
		return None

	return adapter.Params(
		composition,
		parameters=[_panel_parameter(instrument, *setting) for setting in instrument.settings],
		data_key=f"{instrument.key}_settings",
		name=f"{instrument.key}_settings",
		title=f"{instrument.title} — settings",
		about=[("ch", instrument.channel), ("", instrument.about)],
		configures=instrument.key,
		on_change=_send(instrument))


SETTINGS = {one.key: _settings_for(one) for one in INSTRUMENTS}


def _register_pattern (instrument: Instrument) -> None:
	"""Give this instrument a pattern that plays whatever its grid holds.

	**A drum hit is a trigger and a note is held**, which is the only difference
	between the two bodies below: a hit is one pulse long wherever it lands, and a
	note carries the length and the velocity somebody gave it.

	**The stack builds after the hand**, deliberately: a generator told to skip a
	step that already sounds has to see the taps before it runs, and the order a
	stack plays in is the person's to arrange from the glass.

	**And the whole pattern is transposed last** (#2454), after routes and
	generators alike, so every row label is true of what it plays.
	"""

	grid = GRIDS[instrument.key]
	stack = STACKS[instrument.key]
	notes = _note_map(instrument)
	drums = instrument.drums
	asserted = instrument.asserted
	said: list[bool] = []

	# **Named before it is registered**, because a pattern is addressed by the
	# name of the function that builds it and every one of these would otherwise
	# be called `play`.  The grid names the same string in `pattern=`.
	def play (p: typing.Any) -> None:
		# **Once, at the first build**, and only where an instrument cannot play
		# without it (see `Instrument.asserted`).
		if asserted is not None and not said:
			control = DEFINITIONS[instrument.key].controls[asserted[0]]
			p.cc(control.cc, _cc_value(instrument, asserted[0], asserted[1]))
			said.append(True)

		if drums:
			for row, steps in grid.now(p).items():
				for step, shape in steps.items():
					p.note(pitch=notes[row], beat=int(step) * STEP_DURATION,
					       velocity=shape.get("velocity", VELOCITY),
					       duration=HIT_DURATION)

		else:
			per_position = STEP_DURATION / DIVISIONS

			for row, placed in grid.now(p).items():
				for at, note in placed.items():
					p.note(pitch=notes[row], beat=int(at) * per_position,
					       velocity=note.get("velocity", VELOCITY),
					       duration=note.get("length", NOTE_LENGTH) * per_position)

		stack.build(p)

		# **Only a pitched grid is transposed**, because only a pitched grid has a
		# register to move within: a drum row is a voice, and moving a kick up
		# three semitones is a different drum rather than the same one higher.
		if not drums and grid.transpose:
			p.transpose(grid.transpose)

	play.__name__ = instrument.key
	play.__qualname__ = instrument.key

	composition.pattern(
		channel=instrument.channel,
		steps=STEPS,
		step_duration=STEP_DURATION,
		drum_note_map=notes,
		reschedule_lookahead=1 / 24,
	)(play)



for _one in INSTRUMENTS:
	_register_pattern(_one)


# --- Keyboards, made from the glass ---------------------------------------

KEYS = [midi_notes.note_to_name(note)
        for note in range(midi_notes.name_to_note("A0"), midi_notes.name_to_note("C8") + 1)]
"""A piano's eighty-eight keys, belonging to no instrument.

**A register of its own on purpose.**  A keyboard here is patched into whatever
wants notes — an arpeggio on the Minitaur reaching C1 to C3, another on the
Matriarch reaching C3 to C5 — and picking either instrument's register would make
the set worse for the other.  Each consumer folds a choice into its own reach
(``Recipe._folded``), so a wide pool costs nothing downstream.
"""

KEYBOARDS = "keyboards"


def _make_keyboard (spec: dict[str, typing.Any]) -> typing.Any:
	"""Turn one asked-for keyboard into a set of pitches that anything may read.

	**Everything the package is not allowed to know is decided here** (#1465):
	that a keyboard holds pitches rather than steps, which pitches exist, and what
	note each name sounds.  The rack holds a list and knows how long it is.

	**Numbered by where it sits**, because there is no text entry on this panel and
	there should not be: a control that cannot be worked with one finger on glass,
	with no keyboard attached, is a defect.  Two keyboards are told apart by their
	number and by what is chosen on them.
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

	# **Nothing to choose and no length to set**, so making one is a single press.
	# A set of pitches holds notes rather than time, and which notes it holds is
	# chosen on the keyboard itself afterwards rather than described in a form.
	steps=None,

	# **"Pitches" on the glass, and still `keyboards` where it is kept** (#2527 decision
	# 5): the pair is Pitches and Degrees, named for what each holds, and a name a store
	# keeps sets under is not a word anybody reads — so every set already made comes back.
	makes="pitch set",
	data_key=KEYBOARDS,
	name=KEYBOARDS,
	title="Pitches",
	about=[("", "patch into any generator")])
"""Keyboards a person makes from the glass, as many as the music wants (#2226).

**Simon's question of 2026-09-14, answered generally rather than for this case**:
*"For something generic like a keyboard source, which might feed any instrument,
should we have a way of creating a new instance on the interface?  Or does it
have to be defined up-front, in the composition?"*

It does not.  A rack has always been the asking, and until contract 1.41.0 the
only asking anybody had written was shaped like a grid.

**Why more than one is worth having.**  A pitch pool typed into an arpeggio layer
belongs to that layer; one held here can feed an arpeggio on the Minitaur and
another on the Matriarch, and the two cannot drift apart because there is one of
it.  Several keyboards are several such pools — a verse and a chorus — each fed
wherever it is patched.
"""


# --- The key, and degrees that follow it ---------------------------------

ROOTS = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
"""The twelve roots a key may have, spelt as Subsequence reads them."""

SCALES = ("major", "minor", "dorian", "phrygian", "lydian", "mixolydian", "locrian",
          "harmonic_minor", "melodic_minor", "major_pentatonic", "minor_pentatonic",
          "hirajoshi", "in_sen", "iwato", "yo", "egyptian")
"""Subsequence's scales, in the order a musician reaches for them.

**All of `intervals.SCALE_MODE_MAP` but the two it spells twice**: ``ionian`` is
``major`` and ``aeolian`` is ``minor``, and a list offering both is two buttons for
one scale.  The names are Subsequence's, borrowed with their meaning (#2403).
"""

KEY = "key"


def _rekey (name: str, value: typing.Any) -> None:
	"""Make the Key block's key the composition's, and tell every degree set.

	**The composition's own key** (`Composition.key`, `Composition.scale`), which
	Subsequence reads at every build, so what the glass says and what a pattern is
	built in are one fact.  Called on the clock loop for a change on the glass and on
	the link thread when a kept key is asserted at the first beat; a degree set hands
	its report to the clock loop either way.
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
"""**One key for the whole piece, in a block of its own** (Simon, 2026-09-15, #2527).

**Kept with the patterns across a restart**, as a setting is, because a key is part
of the music rather than how it is being played.  **It opens at C major** rather than
at no key: nothing on this rig reads a key but a degree set, and a set made on the
first morning should play at once.
"""

composition.key = composition.data[KEY]["root"]
composition.scale = composition.data[KEY]["scale"]


def _key_now () -> tuple[str, list[int]] | None:
	"""The key as a degree set asks for it: its words, and one octave of its scale from the tonic.

	**Read from the Key block's own values rather than from the composition**, which is
	given them on a change and at the first beat — so a key put back from the store is
	right at the first build and in the first declaration, before either has happened.
	The octave starts at the tonic's fourth, around middle C; a stack folds whatever a
	set sounds into its own instrument's reach (#2374), so where it starts is a shape.
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
"""Every degree set made here, so a key change can tell each of them."""


def _make_degrees (spec: dict[str, typing.Any]) -> adapter.DegreeSet:
	"""Turn one asked-for set of degrees into a set that follows the key (#2527).

	**Everything a key is stays in this file** (#1465): the set asks `_key_now` what the
	key is each time it is read, and `_note_name` what to call a note.  Numbered by where
	it sits, as a set of pitches is.
	"""

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
"""Sets of degrees a person makes from the glass, each patched wherever pitches are wanted (#2527).

**The chain Simon sketched on 2026-09-09** — key, then notes, then arpeggiator, then
instrument — with the notes written as degrees, so changing the key moves every part
a set feeds with nothing re-patched.
"""


# --- Lines, made from the glass -------------------------------------------

LINE_ROWS = [midi_notes.note_to_name(note) for note in range(127, -1, -1)]
"""Every note MIDI has, highest first, which is what a line belonging to no instrument holds.

**A register of its own, and the widest there is** (Simon, 2026-09-14, on the line in
`drm1_grid.py`): a line sounds as whatever it is patched into, so drawing it over one
instrument's register would make it worse for the other.  Windowed, so it is as tall
on the glass as any pitched grid.
"""

LINE_NOTES = {row: midi_notes.name_to_note(row) for row in LINE_ROWS}
"""Row names to MIDI notes, for a grid whose rows *are* notes."""

LINE_OPENS_AT = "C2"
"""Where a line's window opens: the bass register, which is what one is first made for.

A window opens at a grid's lowest rows, which for a grid over all of MIDI is C-1 —
two octaves below anything here sounds (contract 1.38.0).
"""

LINES = "lines"


def _make_line (spec: dict[str, typing.Any]) -> typing.Any:
	"""Turn one asked-for line into a pitched grid with no instrument, routable from every stack.

	**The case #2108 was raised for**: *"I have the Minitaur and Behringer Model D. I
	want to create a bass pattern which plays on both."*  A line is drawn on by hand,
	routed into both stacks, and each instrument goes on adding notes of its own.

	**A pitch means itself**, so the line places note numbers rather than row names,
	and it sounds the same notes on whatever it is patched into — each destination
	then transposed by its own grid.

	**Nothing past the end of the pattern it plays into** (#2548, `7eb4817`): a line
	drives no pattern and has no length of its own, and Subsequence sounds a note
	placed past a pattern's length at the start of its next cycle rather than dropping
	it.  `p.grid` is the borrowing pattern's count of steps, which follows its length,
	so what lies past it is left out and a note running over is cut — in the copy
	played, never on the line.

	**What it cannot do yet is take generators**, as a made grid in `drm1_grid.py`
	cannot: a stack is declared against a pattern when this file is read.  Put
	generators on the instruments it feeds.
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

	per_position = STEP_DURATION / DIVISIONS

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

				p.note(LINE_NOTES[row], beat=begins * per_position,
				       velocity=note.get("velocity", VELOCITY),
				       duration=length * per_position)

	# Routable the moment it exists: a stack reads its sources when it declares, and
	# the rack asks for a declaration as soon as it has made this.
	SOURCES[key] = play

	return line


def _unmake_line (name: str) -> None:
	"""Stop offering a line that has gone as a thing to route from.

	Its notes stay in ``composition.data``, unreachable, as a removed layer's
	parameters do; what must not stay is the source, or every stack goes on offering
	a cable to a line nobody can see.
	"""

	SOURCES.pop(name, None)


lines = adapter.Rack(
	composition,
	make=_make_line,
	unmake=_unmake_line,

	# **Nothing to choose and no length to set**: a line holds every note MIDI has,
	# and plays at the length of whatever it is routed into.
	steps=None,
	makes="line",
	data_key=LINES,
	name=LINES,
	title="Lines",
	about=[("", "route into any instrument")])
"""Lines a person makes from the glass, each one playable on as many instruments as it is routed into.

**#2108 on the rig Simon plays.**  `drm1_grid.py` declares one shared line up front;
this rig declares nothing up front, so a line is made here the way a keyboard is —
and the rig still comes up from nothing, because a rack that has made nothing is a
button rather than a control holding music.
"""


# --- The glass ------------------------------------------------------------

DRUMS = ("drm1", "tr8s")
SYNTHS = ("matriarch", "model_d", "malevolent", "strings", "solo")
BASS = ("minitaur",)
"""Which instruments each page draws, and the whole of what a page is here.

**A settings block needs no listing**: one that names the pattern it configures
is drawn wherever that pattern is, and is put away behind that pattern's own
latch.  Nor does a stack: its *add a generator* appears on the footer of the
pattern it builds, and it only takes a window of its own when that pattern is on
another page.
"""

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
		adapter.Page("ensemble", parts=[one.key for one in INSTRUMENTS] + [KEY, KEYBOARDS, DEGREES, LINES],
		             title="Ensemble"),
		adapter.Page("drums", parts=list(DRUMS), title="Drums"),
		adapter.Page("synths", parts=list(SYNTHS) + [KEY, KEYBOARDS, DEGREES, LINES], title="Synths"),
		adapter.Page("bass", parts=list(BASS) + [KEY, KEYBOARDS, DEGREES, LINES], title="Bass"),
	],
	page_store=adapter.PageStore(PAGE_FILE),
	pattern_store=adapter.PatternStore(PATTERN_FILE),
	url=SERVICE_URL,
)
"""Four views over the room, and where what is made on them is kept.

**Ensemble is everything and the other three are where the work happens.**  Eight
patterns on one page is a scrolling page rather than a glanceable one, which is
what it is for: see the whole room, then take a family of it somewhere quieter.

**After the first edit on the glass this file is not the score** (#2067, #2487).
Every pattern, stack, setting and mute is put back from `PATTERN_FILE` on each
start — and because nothing here seeds anything, a rig whose store is empty comes
up genuinely empty.  That is the point of this composition: *start again from the
file* leaves nothing behind.
"""


if __name__ == "__main__":
	link.start()

	# `play()` returns on Ctrl-C and on a polite kill alike, and `stop` writes down
	# whatever the store had not yet (#2487).
	try:
		composition.play()

	finally:
		link.stop()
