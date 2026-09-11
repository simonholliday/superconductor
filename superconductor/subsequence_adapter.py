"""The Subsequence side of the link: what a composition adds to be playable.

A composition builds an :class:`AppLink`, gives it the controls it wants to
offer — a :class:`StepGrid` over a dict it keeps, a :class:`Transport` over its
own playback — and starts it.  From then on a tap on the glass reaches the
composition, and what the composition does reaches the glass.

**No part of the Subsequence package is changed**, and none of it needs to be.
The link reaches the composition's clock loop through ``composition.on_event``,
which is public: a callback registered there runs *on* that loop, so the first
beat is where the link learns which loop to hand later taps to.  Subroutine
#2046 fixes the no-package-change rule and #1963 carries what a future version
might expose instead.

What a control is *for* is never known here.  A grid's rows are names whoever
built it chose, which is the rule in this project's CLAUDE.md.

Where this module finally lives — here, or shared between the three apps — is
Subroutine #1972 and is still open.
"""

import asyncio
import collections
import collections.abc
import inspect
import json
import logging
import pathlib
import random
import threading
import time
import typing
import zlib

import websockets.asyncio.client
import websockets.exceptions

import superconductor.build
import superconductor.protocol


LOG = logging.getLogger(__name__)

LOADED_BUILD = superconductor.build.package_build()
"""The package this app is running, hashed **as this module is imported** (#2220).

Taken here and never again, because the question it answers is *what did this
process load* — and a process that re-read the files would answer *what is on
disk*, which is the service's question and the other half of the comparison.
An app importing this at start-up therefore carries its own age with it for the
whole of its life, which is the one thing nothing could see before: a page knows
when it is behind and a service is caught by the contract, but a fix inside an
adapter moves no frame, so the contract agrees while a composition plays code
from before lunch.

Module level rather than per link, so two links in one process cannot disagree
about the age of the code they share.
"""

OUTBOUND_CAP = 256
"""How many frames may wait for the socket before the oldest is dropped (#2242).

Large enough that ordinary play never reaches it — a cycle emits a handful — and
small enough that a burst cannot outrun the link thread.  A number rather than a
measurement, because the thing it bounds is a fault: what matters is that some
bound exists, not that this one is exactly right."""

DEFAULT_URL = "ws://127.0.0.1:8090/ws/app"
"""The service on this machine.  A different one is a constructor argument."""

RECONNECT_FLOOR = 0.25
RECONNECT_CEILING = 5.0
"""Seconds between attempts to dial the service, backing off to the ceiling."""


class Refused (Exception):
	"""A request the app will not carry out, carrying why so a panel can say so.

	Distinct from a request that changes nothing: refusing means the panel
	asked for something this app cannot do, and the person who tapped should
	be told rather than left watching a control that never moves.
	"""



class Control:
	"""One thing a panel can see and work, offered under a name."""

	name: str

	kind: str = ""
	"""What sort of control this is, in the word the wire uses.

	**A class attribute rather than a literal inside `declaration`**, because
	something other than the declaration needs to ask (#2419): a cable landing on
	a parameter is refused unless what it comes from is the right sort of thing,
	and the check runs on the clock loop, where building a `Recipe`'s whole
	declaration to read one word off it would be absurd.

	Empty on the base and set by every subclass.  A control that leaves it empty
	is one nothing can be patched from, which is the safe way round.
	"""

	title: str | None = None
	"""What to call this on the glass, if not the name it is addressed by.

	The app names its own parts and the panel repeats them (#2071).  Nothing in
	Superconductor knows that a row called ``kick`` is a drum or that a grid is
	a pattern for one, so a title is the composition's to give: it is the same
	rule as the row names, and the same reason.
	"""

	about: collections.abc.Sequence[tuple[str, typing.Any]] = ()
	"""Facts about this control, to be shown beside its name and nothing more.

	A pair per fact: ``[("ch", 10), ("instrument", "Vermona DRM1 MkIV")]``.

	**This exists because the package may not know any of them.**  A MIDI
	channel and an instrument's name are facts about a studio, and nothing here
	is allowed to hold one (#1465).  A panel that worked them out would be a
	panel that knew what a rig looked like; a panel that is *told* them is a
	panel repeating what the composition said, which is the same rule as the
	title and the row names.

	Shown, never read.  Nothing in the protocol or the client does anything with
	these but draw them, so a composition may say whatever is worth knowing at a
	glance without teaching anything a new word.
	"""

	composition: typing.Any
	"""The composition this control reads and writes.  Declared here because the
	mute below needs it and every control has one."""

	pattern: str | None = None
	"""Which of the composition's patterns this control drives, if any.  A grid
	belonging to no instrument drives none and is silenced by contributing
	nothing (#2108)."""

	enabled: bool = True
	"""Whether this control is contributing anything at all.

	A mute, in the sense a mixer means it: the notes stay where they are and stop
	being heard.  Simon asked for one on every item, and the panel had none —
	silencing one instrument for eight bars was not a thing a person could do at
	all.

	What "off" means is the control's own business.  A grid that drives a pattern
	mutes that pattern; a grid that drives nothing but is routed elsewhere simply
	stops contributing.  Both are "this makes no sound anywhere", said in the
	terms each has available.
	"""

	def said (self) -> dict[str, typing.Any]:
		"""What this control says about itself, over and above what it does.

		Gathered here rather than repeated in every declaration, so a control
		added later cannot quietly offer one and not the other.
		"""

		said: dict[str, typing.Any] = {}

		if self.title is not None:
			said["title"] = self.title

		if self.about:
			said["about"] = [{"label": str(label), "value": str(value)}
			                 for label, value in self.about]

		return said

	def declaration (self) -> dict[str, typing.Any]:
		"""What a panel needs in order to draw this."""

		raise NotImplementedError

	def snapshot (self) -> typing.Any:
		"""What this control holds at the moment."""

		raise NotImplementedError

	def apply (self, rest: list[str], value: typing.Any) -> bool:
		"""Take a request, on the clock loop, and say whether anything changed."""

		raise NotImplementedError

	def applied (self, rest: list[str], value: typing.Any) -> typing.Any:
		"""What this control now holds where a request has just landed.

		Nearly always the value that was asked for, because a control stores
		what it is given.  A stack does not: adding a layer fills in every
		parameter the generator has a default for, so that the glass shows what
		is playing rather than only what somebody typed.  The panel has to be
		told what was actually kept or it draws a layer with nothing in it, and
		the service's copy drifts from the app's on the first tap.
		"""

		return value

	def poll (self) -> list[tuple[str, typing.Any]]:
		"""Anything that changed without the panel asking, as path and value.

		Called on the clock loop once a beat.  It is how a control follows the
		composition's own hand — a tempo ramp, say — rather than only the
		panel's.
		"""

		return []

	def owed (self) -> list[tuple[str, typing.Any]]:
		"""What this control still has to say to the instrument, and has not.

		**Returned rather than done, because the caller is the clock.**  Asked
		on the clock loop and paid on the link thread, which is the discipline
		`_emit` already follows for a socket — "never blocking there, so a slow
		socket cannot delay a pulse".  Telling an instrument is the same kind of
		work and was the one place doing it inline.

		Asking does not clear the debt; `settled` does, once the work has been
		handed to a thread that will do it.  So a beat that finds no link yet
		simply asks again on the next one.
		"""

		return []

	def settled (self) -> None:
		"""The debt above has been handed over and need not be offered again."""

	def settle (self, owed: list[tuple[str, typing.Any]]) -> None:
		"""Say those things to the instrument.  Called on the link thread."""

	def attach (self, link: "AppLink") -> None:
		"""Take the link, so a control that must report between beats can.

		Polling once a beat is enough for anything that moves while the music
		plays.  It is not enough for a transport, because a paused composition
		emits no beats at all.
		"""

	def declared (self) -> None:
		"""Called each time the app introduces itself, reconnections included.

		A control whose value lives somewhere this package cannot read — inside
		an instrument, say — uses this to put its own idea of that value back,
		because otherwise the panel is showing a guess that pressing it cannot
		correct.
		"""


	def _keep_enabled (self, value: typing.Any) -> bool:
		"""Silence this control, or bring it back.

		A pattern is muted through the composition's own mute rather than by
		emptying anything: the notes stay where they are and stop being heard,
		which is what a mute is and what makes it reversible without loss.

		A composition too old to have one is not an error.  The flag is still
		kept and still honoured everywhere this package does the playing — a
		routed grid stops contributing — so what is lost is only the half that
		was never this package's to do.
		"""

		wanted = bool(value)

		if wanted == self.enabled:
			return False

		self.enabled = wanted

		if self.pattern is not None:
			switch = getattr(self.composition, "unmute" if wanted else "mute", None)

			if callable(switch):
				switch(self.pattern)

			else:
				LOG.warning("this composition cannot mute %r", self.pattern)

		return True


class StepGrid (Control):
	"""A grid of rows against steps, kept as a plain dict on ``composition.data``.

	The dict is the composition's: the pattern builder reads it and this writes
	to it.  Nothing wraps it, which is what #2046 decided and what #1914
	anticipated a helper would later replace.

	**``beats`` is a float, and a whole number of them is a coincidence.**  A
	cycle is however long its steps make it, and nine sixteenths is 2.25 —
	which is the whole point of a nine-step pattern running against a sixteen
	(#2228).  It was an ``int`` because every grid on the rig had happened to be
	sixteen steps of a sixteenth, and `int(16 * 0.25)` is 4 without complaint.
	"""

	kind = "step_grid"

	def __init__ (
		self,
		composition: typing.Any,
		rows: collections.abc.Sequence[str],
		steps: int = 16,
		beats: float = 4,
		data_key: str = "grid",
		name: str = "grid",
		title: str | None = None,
		about: collections.abc.Sequence[tuple[str, typing.Any]] = (),
		visible_rows: int | None = None,
		pattern: str | None = None,
	) -> None:
		"""Describe the grid to offer over a dict the composition already keeps."""

		self.composition = composition
		self.rows = list(rows)
		self.steps = steps
		self.beats = beats
		self.data_key = data_key
		self.name = name
		self.title = title
		self.about = list(about)

		self.pattern = pattern
		"""Which of the composition's patterns this grid drives, if it drives one.

		Given, switching this control off mutes that pattern — everything it
		plays, its stack of contributions included, because "off" means this
		instrument is silent rather than "off except for the algorithms".

		A grid that drives nothing has none, and that is not a lesser thing: a
		grid with no instrument is the whole of #2108.  Switching *that* off
		stops it contributing wherever it is routed, which is the same sentence
		in the only terms it has.
		"""
		self.visible_rows = visible_rows
		"""How many rows to show at once, if fewer than there are.

		The same window a pitched pattern has, offered here for the same reason
		rather than a different one: a drum machine with forty voices is as tall
		a block as two octaves, and one mechanism serving both is one place for
		it to behave a certain way.
		"""

	def declaration (self) -> dict[str, typing.Any]:
		"""Rows, width, how long one time round takes, and what to call it."""

		declared: dict[str, typing.Any] = {
			"type": self.kind, "rows": self.rows, "steps": self.steps, "beats": self.beats,

			# **What a weight means, said by the app rather than assumed by the
			# panel.** A step grid's own cells carry no velocity (#2046), but the
			# cells a generator realises on it do — and the panel draws each one
			# at the weight it was played. It was dividing by a hard-coded 127,
			# which is a MIDI number in a package that carries no MIDI; a note
			# grid already declared this and a step grid did not, so the one that
			# said nothing was the one being guessed at.
			"velocity_range": list(VELOCITY_RANGE)}

		if self.visible_rows is not None:
			declared["visible_rows"] = self.visible_rows

		declared.update(self.said())

		return declared

	def _keep_rows (self, value: typing.Any) -> bool:
		"""Replace the whole grid, which is how it is cleared.

		A cell at a time would be a hundred and sixty requests to empty a drum
		pattern, and a clear that stops half way through is worse than one that
		never started.  Checked entire before a single row is touched.
		"""

		if not isinstance(value, dict):
			raise Refused("a grid is a set of rows")

		wanted: dict[str, list[int]] = {}

		for row, held in value.items():
			if row not in self.rows:
				raise Refused(f"this grid has no {row!r} row")

			if not isinstance(held, list):
				raise Refused(f"the {row!r} row takes a list of steps")

			for step in held:
				if isinstance(step, bool) or not isinstance(step, int):
					raise Refused("a step is a whole number")

				if not 0 <= step < self.steps:
					raise Refused(f"step {step} is outside a grid {self.steps} steps wide")

			if held:
				wanted[row] = sorted(set(held))

		grid = self.composition.data.setdefault(self.data_key, {})

		if {row: steps for row, steps in grid.items() if steps} == wanted:
			return False

		grid.clear()
		grid.update(wanted)

		return True

	def applied (self, rest: list[str], value: typing.Any) -> typing.Any:
		"""What the grid now holds, which for a whole-grid write is not the ask.

		A row given the same step twice, or out of order, is kept once and in
		order — so the request and the result differ, and the panel has to be
		told the second.
		"""

		return self.rows_now() if rest == ["rows"] else value

	def rows_now (self) -> dict[str, list[int]]:
		"""The grid as it stands, one row at a time, empty rows included.

		Read from the link thread rather than the clock loop, deliberately: the
		only hazard is a row being sorted at this instant, and copying a list is
		a single step under the interpreter's lock.  Crossing onto the loop for
		a read would put socket work on the path that generates MIDI timing.

		**Rows and nothing else**, which is why this is not `snapshot`.  A write
		to ``control/rows`` is answered with what that path names; the mute is a
		different path and does not belong in the answer to this one.  Sending
		the snapshot here made the service refuse the whole frame — `enabled` is
		not a declared row — so a cleared grid stayed lit on every panel while
		the music went quiet.
		"""

		grid = self.composition.data.get(self.data_key) or {}

		return {row: sorted(grid.get(row, [])) for row in self.rows}

	def snapshot (self) -> dict[str, typing.Any]:
		"""Everything a panel needs to draw this grid, mute included."""

		# Beside the rows rather than under a key of its own, because a control's
		# state is one object and a panel reads it as one. `rows` is already
		# reserved here for the whole-grid write, so a row cannot be called that
		# either; this is the second word spent and it buys a mute.
		return {**self.rows_now(), "enabled": self.enabled}

	def apply (self, rest: list[str], value: typing.Any) -> bool:
		"""Switch one cell, absolutely rather than by toggling.

		Absolute is what makes a re-send after a reconnect safe: applying it
		twice reaches the same grid as applying it once.
		"""

		if rest == ["enabled"]:
			return self._keep_enabled(value)

		if rest == ["rows"]:
			return self._keep_rows(value)

		if len(rest) != 2 or not rest[1].isdigit():
			raise Refused(f"{'/'.join(rest)!r} does not name a cell of this grid")

		row, step = rest[0], int(rest[1])

		if row not in self.rows:
			raise Refused(f"this grid has no {row!r} row")

		if not 0 <= step < self.steps:
			raise Refused(f"step {step} is outside a grid {self.steps} steps wide")

		steps = self.composition.data.setdefault(self.data_key, {}).setdefault(row, [])

		if value and step not in steps:
			steps.append(step)
			steps.sort()
			return True

		if not value and step in steps:
			steps.remove(step)
			return True

		return False


def _overlaps (at: int, span: int, other_at: int, other: dict[str, typing.Any]) -> bool:
	"""Whether two notes sound at the same time.

	Half-open on the right, so a note ending exactly where the next begins does
	not count as overlapping it — that is a legato line, not a clash, and it is
	the shape a person draws by filling consecutive steps.
	"""

	other_span = max(1, int(other.get("length", 1)))

	return at < other_at + other_span and other_at < at + span


class NoteGrid (Control):
	"""A pitched pattern: one row per note, and a cell that is a note.

	The same plain dict on ``composition.data`` that a step grid uses, one level
	deeper — row, then step, then the note's length in steps and its velocity.
	The pattern builder reads it and this writes to it, and nothing here knows
	that a row called ``C2`` is a pitch: the composition maps row names to notes
	exactly as it maps drum voices to them.

	``voices`` is how many notes the instrument sounds at once, and it is the
	composition's to state because only the composition knows what is plugged in.
	``None`` — the default — means as many as you like.  ``1`` is a monophonic
	synth, ``4`` a Matriarch in its four-voice mode, ``10`` a drum machine with a
	voice to a part.  Voicing is not a boolean and never was: of the fourteen
	instruments measured in #2125, one is switchable between 1, 2 and 4 *from the
	glass*, and another drops from 32 notes to 16 when an effect is on.

	It is enforced here rather than left to the instrument, because an instrument
	choosing between simultaneous notes by its own key-priority setting would
	leave the glass showing notes that never sound.  Enforced by **extent** and
	not by starting position: a note beginning part-way through another is
	exactly the case the instrument would have to arbitrate (#2114).

	``mono=True`` is kept as a spelling of ``voices=1``, so a composition written
	before there was a count does not have to change.

	**Do not pass an instrument definition's ``polyphony`` straight in.**  In
	``pymididefs.instruments`` a ``polyphony`` of ``None`` means *nobody has
	established it*; here ``voices=None`` means *as many as you like*.  They are
	the same value with opposite meanings, and the Moog Matriarch is exactly the
	case: its voicing is a front-panel switch and CC 94 with no documented
	power-on default, so its definition says ``polyphony: null`` and offers
	``voicing_modes: [1, 2, 4]`` instead.  Read straight through, that gives an
	unlimited grid on a four-voice instrument — a chord drawn on the glass that
	cannot sound, failing silently, on the first polyphonic synth this project
	takes on.  Translating one into the other is #2142's job, and which number a
	mode-switched instrument opens at is #2143's.

	``divisions`` is how many addressable positions make up one drawn cell, and
	the composition is the one that says.  One — the default — means a position
	is a step and this is the grid it always was.  More than one means the
	composition keeps a finer dict and reads it with ``PatternBuilder.note``
	rather than ``hit_steps``, because placing a note between two steps is
	precisely what ``hit_steps`` cannot express.  **The unit is the
	composition's**, since ``composition.data`` is its dict and its own builder
	reads it (#1465).
	"""

	kind = "note_grid"

	def __init__ (
		self,
		composition: typing.Any,
		rows: collections.abc.Sequence[str],
		steps: int = 16,
		beats: float = 4,
		data_key: str = "notes",
		name: str = "notes",
		title: str | None = None,
		about: collections.abc.Sequence[tuple[str, typing.Any]] = (),
		pattern: str | None = None,
		mono: bool = False,
		voices: int | None = None,
		transpose_range: tuple[int, int] = (-24, 24),
		relabel: collections.abc.Callable[[str, int], str | None] | None = None,
		divisions: int = 1,
		default_length: int = 1,
		default_velocity: int = 100,
		visible_rows: int | None = None,
	) -> None:
		"""Describe the pattern to offer over a dict the composition keeps."""

		self.composition = composition
		self.rows = list(rows)
		self.steps = steps
		self.beats = beats
		self.data_key = data_key
		self.name = name
		self.title = title
		self.about = list(about)
		self.pattern = pattern
		if mono:
			if voices is not None and voices != 1:
				raise ValueError(
					"mono=True is a spelling of voices=1 and cannot be given "
					f"beside voices={voices}")

			voices = 1

		if voices is not None and voices < 1:
			raise ValueError("an instrument sounds at least one note at a time")

		self.voices = voices
		"""How many notes may sound at once, or None for as many as you like."""

		self.transpose = 0
		"""How many semitones the pattern is sounding away from how it is drawn.

		**The sound moves and the drawing does not** (#2152).  The notes stay
		where they were put, so the shape a person made stays a stable thing to
		read and to keep editing, and the change is undone by putting the number
		back.  What follows the offset is the row *labels*, which is what stops
		the glass lying about pitch.
		"""

		self.transpose_range = transpose_range
		"""How far it may be moved, in semitones.

		Two octaves each way by default, which is what pitch bend offers and
		about as far as a bassline stays a bassline.  The composition may say
		otherwise; the panel draws whatever it is told.
		"""

		self.relabel = relabel
		"""What a row is called once the pattern is transposed, asked of the composition.

		**This package cannot answer it**, and that is the point: nothing here
		knows that a row called ``C2`` is a pitch, or that two semitones above it
		is ``D2``.  The composition maps rows to notes and so the composition is
		asked, one row at a time (#1465).

		Returning ``None`` says the row cannot sound at this offset — which a
		Minitaur does above note 72, silently, and is the failure this whole
		design exists to make visible.
		"""

		self.divisions = divisions
		self.default_length = default_length
		"""How long a note is when it is placed, in this grid's own positions.

		In positions rather than steps so that one number means one thing: a
		composition dividing a step into six and wanting a note a step long
		says six, and never has to know which unit a given field is counted in.
		"""
		self.default_velocity = default_velocity
		self.visible_rows = visible_rows
		"""How many rows to show at once, if fewer than there are.

		A pitched pattern is tall — two octaves is twenty-five rows against a
		drum machine's ten — and a block tall enough to hold all of it crowds
		everything else off the page.  Showing a window onto it, which scrolls
		within the block, keeps the block small on the lattice without shortening
		the instrument.
		"""

		self.link: "AppLink | None" = None

	def attach (self, link: "AppLink") -> None:
		"""Keep the link, so clearing a note the panel did not name can be said."""

		self.link = link

	@property
	def positions (self) -> int:
		"""Every place a note may start, which is a step only where there is one
		division to a step."""

		return self.steps * self.divisions

	def declaration (self) -> dict[str, typing.Any]:
		"""Rows, width, and what a note may be."""

		declared: dict[str, typing.Any] = {
			"type": self.kind, "rows": self.rows, "steps": self.steps, "beats": self.beats,
			"voices": self.voices, "divisions": self.divisions,
			"transpose_range": list(self.transpose_range),
			"default_length": self.default_length, "default_velocity": self.default_velocity,
			"max_length": self.positions, "velocity_range": list(VELOCITY_RANGE)}

		if self.visible_rows is not None:
			declared["visible_rows"] = self.visible_rows

		declared.update(self.said())

		return declared

	def rows_now (self) -> dict[str, typing.Any]:
		"""Every note as it stands, copied so nothing shares a dict with the loop.

		**Rows and nothing else**, for the reason a step grid's says: the answer
		to a write names what the path named.
		"""

		grid = self.composition.data.get(self.data_key) or {}

		return {
			row: {step: dict(note) for step, note in (grid.get(row) or {}).items()}
			for row in self.rows if grid.get(row)}

	def snapshot (self) -> dict[str, typing.Any]:
		"""Every note, and the mute that travels with them.

		The mute travels with the rows, as a step grid's does: a panel arriving
		after one was silenced has no other way to learn it, and would draw the
		switch live over a pattern that is not.
		"""

		labels, unreachable = self._relabelled()

		return {**self.rows_now(), "enabled": self.enabled,
		        "transpose": self.transpose,
		        "labels": labels, "unreachable": unreachable}

	def apply (self, rest: list[str], value: typing.Any) -> bool:
		"""Place, remove or reshape one note, absolutely rather than by toggling."""

		# **The mute, and it was missing here while a step grid had it.** A note
		# grid fell straight through to "that does not name a note", so the panel
		# sent the change, the app refused it, and the face — which always
		# follows the app — never moved. On the glass that is a switch that does
		# nothing, with the reason in a `nack` nobody was reading. Simon reported
		# it three times before he happened to say which grid it was on, and the
		# one I kept testing was the step grid, where it worked.
		if rest == ["enabled"]:
			return self._keep_enabled(value)

		if rest == ["transpose"]:
			return self._keep_transpose(value)

		if rest == ["rows"]:
			return self._keep_rows(value)

		if len(rest) not in (2, 3) or not rest[1].isdigit():
			raise Refused("that does not name a note")

		row, step = rest[0], rest[1]

		if row not in self.rows:
			raise Refused(f"this pattern has no row called {row}")

		if not 0 <= int(step) < self.positions:
			raise Refused(f"{step} is outside a pattern {self.positions} positions long")

		grid = self.composition.data.setdefault(self.data_key, {})
		notes = grid.setdefault(row, {})

		if len(rest) == 3:
			return self._shape(grid, row, notes, step, rest[2], value)

		if value:
			if step in notes:
				return False

			notes[step] = {"length": self.default_length, "velocity": self.default_velocity}

			self._keep_voices(grid, row, int(step), self.default_length)

			return True

		if step not in notes:
			return False

		del notes[step]

		# Dropped once its last note goes, which is what the service's copy of
		# the same structure does. Nothing on the wire differs either way — the
		# snapshot filters empty rows — but two copies of one thing drifting is
		# how a future reader loses an afternoon.
		if not notes:
			grid.pop(row, None)

		return True

	def _shape (
		self,
		grid: dict[str, typing.Any],
		row: str,
		notes: dict[str, typing.Any],
		step: str,
		field: str,
		value: typing.Any,
	) -> bool:
		"""Change a note's length or velocity, refusing what would not sound."""

		if step not in notes:
			raise Refused("there is no note there to shape")

		wanted = self._checked_field(field, value)

		if notes[step][field] == wanted:
			return False

		notes[step][field] = wanted

		# Lengthening reaches over notes that were clear of it a moment ago, so
		# a counted part has to be re-checked here and not only where a note is
		# placed. Velocity changes nothing about when a note sounds, so this
		# asks about the extent it now has either way and finds nothing to do.
		if field == "length":
			self._keep_voices(grid, row, int(step), wanted)

		return True

	def _checked_field (self, field: str, value: typing.Any) -> int:
		"""One of a note's two numbers, refused if it would not sound.

		Shared between shaping a note and writing a whole grid, so a length that
		is legal one way cannot be illegal the other.
		"""

		wanted = int(value)

		if field == "length":
			if not 1 <= wanted <= self.positions:
				raise Refused(f"a note is between 1 and {self.positions} positions long")

		elif field == "velocity":
			# **The pair this grid declared, rather than the same two numbers
			# written out again** (#2436).  A check that disagreed with the
			# declaration would draw a lane a finger cannot reach the end of, and
			# nothing would say which of the two was wrong.
			low, high = VELOCITY_RANGE

			if not low <= wanted <= high:
				raise Refused(f"velocity is between {low} and {high}")

		else:
			raise Refused(f"a note has no {field}")

		return wanted

	def _keep_transpose (self, value: typing.Any) -> bool:
		"""Move the sound without moving the drawing, and say what the rows are now.

		**Landing.**  Nothing here waits for a boundary and nothing has to: the
		pattern is rebuilt once a cycle and reads this when it is, so a number set
		mid-bar is heard from the next one.  What that costs is a window of up to
		one cycle in which the labels have moved and the ears have not — small,
		self-correcting, and worth knowing about.  A change that has to be *shown*
		as queued is #2146's, and it is the harder half of the same idea.

		The labels are said in their own right because the panel cannot work them
		out.  It knows a row is called ``C2`` and nothing else; only the
		composition knows that is a pitch.
		"""

		low, high = self.transpose_range
		wanted_semitones = int(value)

		if not low <= wanted_semitones <= high:
			raise Refused(f"transposition is between {low} and {high} semitones")

		if wanted_semitones == self.transpose:
			return False

		self.transpose = wanted_semitones

		# Reported separately rather than folded into the value, because they are
		# a consequence of it rather than part of it — the same reason a note the
		# voice count cleared is reported in its own right.
		if self.link is not None:
			labels, unreachable = self._relabelled()
			self.link.report(f"{self.name}/labels", labels)
			self.link.report(f"{self.name}/unreachable", unreachable)

		return True

	def _relabelled (self) -> tuple[dict[str, str], list[str]]:
		"""What each row is called at the current offset, and which cannot sound.

		Empty when the composition offered no way to ask, which is not an error:
		a grid whose rows are not pitches has nothing to relabel, and a panel goes
		on drawing the row names it already has.
		"""

		if self.relabel is None:
			return {}, []

		labels: dict[str, str] = {}
		unreachable: list[str] = []

		for row in self.rows:
			said = self.relabel(row, self.transpose)

			if said is None:
				unreachable.append(row)
			else:
				labels[row] = said

		return labels, unreachable

	def _keep_rows (self, value: typing.Any) -> bool:
		"""Replace the whole grid, which is how it is cleared."""

		if not isinstance(value, dict):
			raise Refused("a grid is a set of rows")

		wanted: dict[str, dict[str, typing.Any]] = {}

		for row, held in value.items():
			if row not in self.rows:
				raise Refused(f"this grid has no {row!r} row")

			if not isinstance(held, dict):
				raise Refused(f"the {row!r} row takes notes by step")

			placed: dict[str, typing.Any] = {}

			for step, note in held.items():
				if not str(step).isdigit() or not 0 <= int(step) < self.positions:
					raise Refused(f"{step} is outside a grid {self.positions} positions wide")

				if not isinstance(note, dict):
					raise Refused("a note is an object")

				placed[str(step)] = {
					"length": self._checked_field(
						"length", note.get("length", self.default_length)),
					"velocity": self._checked_field(
						"velocity", note.get("velocity", self.default_velocity)),
				}

			if placed:
				wanted[row] = placed

		grid = self.composition.data.setdefault(self.data_key, {})

		if {row: notes for row, notes in grid.items() if notes} == wanted:
			return False

		grid.clear()
		grid.update(wanted)

		return True

	def applied (self, rest: list[str], value: typing.Any) -> typing.Any:
		"""What the grid now holds, which for a whole-grid write is not the ask:
		a note arrives without its shape and is kept with one."""

		return self.rows_now() if rest == ["rows"] else value

	def _keep_voices (self, grid: dict[str, typing.Any], keep: str, at: int, span: int) -> None:
		"""Take notes away until no more than the instrument's voices sound, and say so.

		**By extent, not by starting position** (#2114).  A note beginning
		part-way through another is exactly the case the instrument would have to
		arbitrate by its own key priority, which is what a voice count exists to
		keep off the glass — and once a note can be dragged around, overlapping
		without sharing a start is the ordinary case rather than a corner of one.

		**The note just placed always survives.**  It is the one the panel asked
		for, and last-note priority is what a monophonic synth does with the same
		situation.  Among the rest the earliest-starting goes first, because it is
		the one the player has most likely moved on from.

		The panel asked for one thing and several changed, so each of the others
		is reported in its own right — otherwise a cell would go dark on the glass
		with nothing on the wire to explain it.
		"""

		if self.voices is None:
			return

		# One at a time, re-asking after each: taking a note away can leave the
		# part inside its count everywhere, and guessing how many to remove up
		# front is how a grid loses a note it could have kept.
		while True:
			crowded = self._crowded(grid, keep, at, span)

			if crowded is None:
				return

			row, step = crowded

			del grid[row][step]

			if self.link is not None:
				self.link.report(f"{self.name}/{row}/{step}", False)

			# Dropped once its last note goes, as removing one by hand already
			# does. Nothing on the wire differs either way — the snapshot filters
			# empty rows — but this is the second copy of that rule, and a test
			# found them disagreeing the moment there was a second way in.
			if not grid[row]:
				grid.pop(row, None)

	def _crowded (
		self,
		grid: dict[str, typing.Any],
		keep: str,
		at: int,
		span: int,
	) -> tuple[str, str] | None:
		"""The note to take away first, or ``None`` when nothing sounds too thickly.

		**Asked position by position rather than by counting what overlaps the new
		note**, because two notes can each overlap it without overlapping one
		another: a long note laid across two short ones in different rows is three
		notes and never three at once.  Counting the overlaps would take one away
		for nothing, and on a four-voice part that is a chord quietly losing a
		finger.

		Notes in the row being kept are not counted, which is what the monophonic
		rule did before there was a count — a row is one pitch, and a pitch does
		not compete with itself.  Two overlapping notes in one row are a retrigger
		rather than two voices, and an instrument that disagrees is a question for
		#2143 rather than a silent change here.
		"""

		if self.voices is None:
			return None

		sounding: list[tuple[int, int, str, str, int]] = []

		for order, row in enumerate(self.rows):
			if row == keep:
				continue

			for step, note in (grid.get(row) or {}).items():
				if _overlaps(at, span, int(step), note):
					sounding.append(
						(int(step), order, row, step, max(1, int(note.get("length", 1)))))

		# The note being kept holds a voice for the whole of its own extent, so
		# whatever else sounds there shares what is left.
		room = self.voices - 1

		# Nothing can be over the count at a single position if the whole extent
		# is within it, and this is the answer almost every time.
		if len(sounding) <= room:
			return None

		for position in range(at, at + span):
			here = [entry for entry in sounding if entry[0] <= position < entry[0] + entry[4]]

			if len(here) > room:
				# Earliest first, and the row order breaks a tie so that the same
				# grid always loses the same note.
				chosen = min(here)

				return chosen[2], chosen[3]

		return None

class Parameter:
	"""One setting of an instrument, in one of the shapes a panel can draw.

	Which shapes those are is `protocol.PARAMETER_KINDS`, and saying the number
	here is how it goes stale: this said *three* while the tuple held six.

	Carries no MIDI.  What a switch is wired to is the composition's business,
	which is the same rule the rows of a grid follow (#1465).
	"""

	def __init__ (
		self,
		name: str,
		kind: str,
		label: str | None = None,
		minimum: float | None = 0,
		maximum: float | None = 127,
		step: float = 1,
		options: collections.abc.Sequence[tuple[str, str]] | None = None,
		default: typing.Any = None,
		group: str | None = None,
		role: str | None = None,
		unit: str | None = None,
		may_be_unset: bool = False,
	) -> None:
		"""Describe one setting: what it is called, what shape it is, what it may be.

		``group`` is the section of the instrument this belongs to — *Oscillators*,
		*Arpeggiator*, *Delay*.  It is a **heading, not a structure**: the fields
		stay one flat list in the order the composition gave them, and a panel is
		free to draw the headings or ignore them.  A settings panel of six controls
		does not need them and a panel of thirty-six is unreadable without them,
		and neither of those is this package's business to decide.

		The words are the composition's, like every other label here.  A Matriarch
		has an *Arpeggiator* because Moog put that word on the panel, and nothing
		in this package knows that (#1465).
		"""

		self.name = name
		self.kind = kind

		self.role = role
		"""What the values of this parameter *are*, where the kind cannot say.

		A ``choices`` of pitch names and a ``choices`` of waveform names are the
		same kind and are not the same thing, and only the first may be fed from a
		set of notes (#2374).  Held here so that the check reading it is the same
		one every other value passes through.
		"""
		self.unit = unit
		"""What this parameter's values are measured in, in the app's own words.

		`beats`, `steps`, `MIDI velocity` — a free string, drawn beside the
		number and never converted (`protocol.UNIT`).  Absent where a parameter
		has no natural unit, which is most of the ones that are counts and all of
		the ones that are constants: inventing one for `lorenz.sigma` would be
		worse than the silence.

		**Read only by the half that faces the app that said it.**  A unit is
		what lets `offerable` tell one `grid` from another and turn a position
		into the choices a pattern actually has; by the time anything downstream
		sees a control, that is already a bound or an option list.
		"""

		self.label = label
		self.minimum = minimum
		self.maximum = maximum
		self.step = step
		self.options = list(options or [])
		self.default = default
		self.group = group

		self.may_be_unset = may_be_unset
		"""Whether this can be put back to holding nothing at all.

		**A parameter that opens unset can be returned to unset** — the rule and
		why it is not inferred here are `protocol.may_be_unset`.  It is off by
		default because a *composition* builds these for an instrument's front
		panel, where there is no such state: a CC always holds a number, and a
		switch is on or off.  Only a catalogue's own entry says otherwise, and
		only `_as_parameter` reads one.
		"""

	def declaration (self) -> dict[str, typing.Any]:
		"""What a panel needs in order to draw this and to know what it may ask."""

		declared: dict[str, typing.Any] = {
			"name": self.name, "kind": self.kind, "label": self.label or self.name}

		if self.group is not None:
			declared["group"] = self.group

		# **Whatever the kind**, because a position that has become a `choices`
		# is still counted in steps and the glass still wants to say so.  Left
		# out rather than sent as null where there is none: a panel drawing an
		# empty unit would put a gap after every number that has no name for
		# what it is.
		if self.unit is not None:
			declared[superconductor.protocol.UNIT] = self.unit

		if self.kind in ("number", "range"):
			declared["step"] = self.step

			# A bound that was never declared is left out rather than sent as
			# null: a panel drawing a slider needs two ends, and one that has
			# none should be shown as something a finger can still work — a
			# stepper — rather than as a slider with invented limits.
			if self.minimum is not None:
				declared["min"] = self.minimum

			if self.maximum is not None:
				declared["max"] = self.maximum

		elif self.kind in ("choice", "choices", "action"):
			declared["options"] = [{"value": value, "label": label} for value, label in self.options]

		return declared

	def opening (self) -> typing.Any:
		"""What it holds before anybody has touched it."""

		if self.kind == "range":
			return self._opening_range()

		if self.default is not None:
			return self.default

		if self.kind == "switch":
			return False

		if self.kind == "choice":
			return self.options[0][0] if self.options else None

		if self.kind == "choices":
			# **The first option, as a list of one** — the same answer a choice
			# gives, wearing the shape a choices holds.  A required parameter has
			# to open at something usable, and opening at nothing would place a
			# chord generator on the stack that sounds nothing while its picker
			# says "choose"; opening at everything would be a decision the person
			# has not made.  One is the smallest thing that plays.
			return [self.options[0][0]] if self.options else []

		return self.minimum if self.minimum is not None else 0

	def _opening_range (self) -> list[float]:
		"""Two numbers, widening a single one rather than refusing it.

		A generator that takes ``int | (int, int)`` declares a scalar default —
		``euclidean`` opens at velocity 100, not at a pair — so a range control
		has to be able to start from one number.  Both ends at the same value
		says *exactly this*, and dragging them apart is how a person asks for
		variation.  Refusing the scalar would mean no generator could be offered
		with the velocity its own author chose.
		"""

		if isinstance(self.default, (list, tuple)) and len(self.default) == 2:
			return [self.default[0], self.default[1]]

		if isinstance(self.default, bool) or not isinstance(self.default, (int, float)):
			floor = self.minimum if self.minimum is not None else 0

			return [floor, floor]

		return [self.default, self.default]


def checked_value (
	parameter: Parameter,
	value: typing.Any,
	sources: dict[str, str] | None = None,
) -> typing.Any:
	"""Refuse anything a parameter could not hold, saying which and why.

	Shared between an instrument's settings and a generator's, because they are
	the same six shapes and two copies of this would drift.  A refusal here is
	a message a person reads on the glass, so each one names the parameter.

	``sources`` maps every control this app has declared to its kind, and is what
	a patch is checked against.  **Left out, every patch is refused** — which is
	the safe way round and is what an instrument's settings want: only `Recipe`
	resolves an envelope, so a cable landing in a `Params` field would be stored,
	reported to every panel, and worth nothing for ever.

	**Every kind offered has to appear here as well as in the declaration.**  The
	panel is answered by this and a panel that reloads is answered by the
	service's own copy, so a kind that is declared but not accepted here is one
	the service takes and the app refuses — which was exactly what happened when
	``choices`` was added, and what `tests/test_seam.py` caught.
	"""

	# **A reference is checked before a kind is, because it is not one** (#2374).
	# `{"from": ...}` says take this from somewhere every cycle, and it would fail
	# every check below — reporting that a pitch pool is not a list, which is true
	# and useless.
	#
	# **The policy is `protocol.PATCH_INPUTS`, and what the source *is* is checked
	# here rather than by the caller** (#2419).  A comment here used to say the
	# caller did it, and no caller ever had: measured on 2026-09-10, this half
	# accepted a cable from a transport and from a control that did not exist,
	# while the service refused both — and a refusal on that side is logged and
	# the frame forwarded, so the cable appeared on a connected panel and not on
	# one that reloaded.  That is the shape `tests/test_seam.py` exists for.
	if superconductor.protocol.is_patch(value):
		why = superconductor.protocol.patch_refusal(
			parameter.name, value,
			(sources or {}).get(str(value.get("id"))),
			parameter.kind, parameter.role)

		if why is not None:
			raise Refused(why)

		return {superconductor.protocol.PATCHED: "control", "id": value["id"]}

	# **`null` is not a value, it is the absence of one** (#2381), and it is
	# checked here for the reason a reference is: it would fail every kind below
	# and be refused as *not a number*, which is true and tells nobody anything.
	#
	# Only a parameter that opened unset may go back, and the caller is what
	# acts on it — this says the value is allowed and `_keep_parameter` takes
	# the key off the layer.  Anything else is refused by name, so a panel that
	# sends `null` at a parameter which must hold something is told so on the
	# glass rather than silently handing a generator a `None` it never asked for.
	if value is None:
		if not parameter.may_be_unset:
			raise Refused(f"{parameter.name} has to hold something")

		return None

	if parameter.kind == "switch":
		if not isinstance(value, bool):
			raise Refused(f"{parameter.name} is a switch")

		return value

	if parameter.kind == "choice":
		if value not in [option for option, _ in parameter.options]:
			raise Refused(f"{parameter.name} has no option called {value}")

		return value

	if parameter.kind == "range":
		if (not isinstance(value, (list, tuple)) or len(value) != 2
				or any(isinstance(one, bool) or not isinstance(one, (int, float)) for one in value)):
			raise Refused(f"{parameter.name} is a range, and takes two numbers")

		if value[0] > value[1]:
			raise Refused(f"{parameter.name} is two numbers in order")

		_in_bounds(parameter, value[0])
		_in_bounds(parameter, value[1])

		return [value[0], value[1]]

	if parameter.kind == "action":
		# Checked exactly as a choice is: a press names one of the things the app
		# offered, and anything else is refused.  What differs is downstream —
		# nothing stores the answer, because there is nothing to store.
		if value not in [option for option, _ in parameter.options]:
			raise Refused(f"{parameter.name} has no option called {value}")

		return value

	if parameter.kind == "choices":
		if not isinstance(value, list):
			raise Refused(f"{parameter.name} takes several options as a list")

		allowed = [option for option, _ in parameter.options]
		taken: list[typing.Any] = []

		for one in value:
			# Membership before the duplicate check, so a value JSON can carry
			# but a set cannot hold is refused by name rather than raising an
			# unhashable TypeError from underneath.
			if one not in allowed:
				raise Refused(f"{parameter.name} has no option called {one}")

			if one in taken:
				raise Refused(f"{parameter.name} was given {one} twice")

			taken.append(one)

		return taken

	if isinstance(value, bool) or not isinstance(value, (int, float)):
		raise Refused(f"{parameter.name} is a number")

	_in_bounds(parameter, value)

	return value


def _in_bounds (parameter: Parameter, value: float) -> None:
	"""Refuse a number outside whatever bounds this parameter declared, if any.

	Most of a generator's numbers have no bound to declare — a duration in
	beats, a spacing, the time step of a chaotic system — so an unbounded one
	is the ordinary case here rather than an oversight, and inventing a range
	for it would be a guess with a MIDI accent.
	"""

	if parameter.minimum is not None and value < parameter.minimum:
		raise Refused(f"{parameter.name} is not below {parameter.minimum}")

	if parameter.maximum is not None and value > parameter.maximum:
		raise Refused(f"{parameter.name} is not above {parameter.maximum}")


class Params (Control):
	"""The settings of one instrument, held in a dict the composition keeps.

	Every other control here writes into ``composition.data`` and lets the
	composition decide what that means.  This does the same, and then calls a
	function the composition supplied — which is where a MIDI control change
	gets sent, if that is what the setting is.  Nothing in this package learns
	a control-change number, and nothing in it has to.
	"""

	kind = "params"

	def __init__ (
		self,
		composition: typing.Any,
		parameters: collections.abc.Sequence[Parameter],
		data_key: str = "settings",
		name: str = "settings",
		title: str | None = None,
		about: collections.abc.Sequence[tuple[str, typing.Any]] = (),
		on_change: collections.abc.Callable[[str, typing.Any], None] | None = None,
		configures: str | None = None,
	) -> None:
		"""Describe the settings to offer, and how the composition hears about one.

		``configures`` names the control these settings belong to — the pattern
		that plays the instrument they set.  It is what lets a panel keep them out
		of the way until they are asked for, behind a control on that pattern's
		own block, rather than standing a settings panel beside every pattern for
		ever (#2201).

		**It is a claim about this rig and not a structure.**  Nothing here checks
		that the named control exists: an app is the authority on its own
		declaration, and a panel that cannot find the named pattern simply draws
		these settings as a block of their own, which is what every settings
		control did before the field existed.
		"""

		self.composition = composition
		self.parameters = {parameter.name: parameter for parameter in parameters}
		self.data_key = data_key
		self.name = name
		self.title = title
		self.configures = configures
		self.about = list(about)
		self.on_change = on_change

		self._to_assert = False
		"""Whether every setting is owed to the instrument.

		Set when the app declares itself and acted on at the next beat rather
		than at once, because the clock may not be running yet when a
		composition first dials in — and a setting sent before there is a clock
		to carry it is simply dropped.
		"""

		held = composition.data.setdefault(data_key, {})

		for parameter in self.parameters.values():
			# An action holds nothing, so there is nothing to open it at. Leaving
			# it out of the dict is what keeps it out of `snapshot`, out of the
			# settings burst, and out of the service's copy — each of which would
			# otherwise be a place the panel could read a state back from and
			# draw it as though somebody knew it (#2179).
			if parameter.kind != "action":
				held.setdefault(parameter.name, parameter.opening())

	def declaration (self) -> dict[str, typing.Any]:
		"""Every setting, in the order the composition offered them."""

		declared: dict[str, typing.Any] = {
			"type": self.kind,
			"fields": [parameter.declaration() for parameter in self.parameters.values()]}

		if self.configures is not None:
			declared["configures"] = self.configures

		declared.update(self.said())

		return declared

	def snapshot (self) -> dict[str, typing.Any]:
		"""What every setting holds at the moment."""

		return dict(self.composition.data.get(self.data_key) or {})

	def declared (self) -> None:
		"""Owe the instrument every setting, to be paid at the next beat."""

		self._to_assert = True

	def poll (self) -> list[tuple[str, typing.Any]]:
		"""On the first beat after declaring, tell the instrument everything.

		Nothing here can read an instrument's mind.  A synthesiser holds its own
		settings, remembers them through a power cycle and says nothing about
		them, so a panel that merely showed defaults would be showing a guess —
		and because a value that has not changed sends no message, pressing the
		control could not correct it either.  Asserting them makes the glass
		true rather than hopeful.

		Reported to nobody: this is the app telling the instrument, not telling
		a panel, and the panel already holds what the snapshot gave it.
		"""

		return []

	def owed (self) -> list[tuple[str, typing.Any]]:
		"""Every setting this instrument has not been told yet, once.

		**Measured, and moved off the clock for it.**  The adapter's own cost
		here is 0.012 ms and free; the cost is one `composition.trigger()` per
		setting, and there is one per setting — ten for the Minitaur as
		`compositions/drm1_grid.py` declares it, thirty-six for a Matriarch.
		That is linear in a number the project is deliberately increasing, on a
		callback with about 20 ms of headroom before it delays the next pulse,
		and it had no measurement behind it while every other path on the timing
		loop did (#1926, #2025, #2033, #2043).

		Simon's rule of 2026-09-06 decides it: timing is paramount and the clock
		must remain solid at all costs, so an unmeasured cost on the timing path
		is one to remove rather than to assume away.  It is still *asked for* on
		the first beat, because a beat is how this knows the clock is running —
		a setting sent before playback starts is silently dropped — but it is
		paid on the link thread, where `composition.trigger()` is documented as
		the thread-safe way in.
		"""

		if not self._to_assert or self.on_change is None:
			return []

		return [(name, value)
		        for name, value in (self.composition.data.get(self.data_key) or {}).items()
		        if name in self.parameters]

	def settled (self) -> None:
		"""Owed once and no more, now that somebody has taken the work."""

		self._to_assert = False

	def settle (self, owed: list[tuple[str, typing.Any]]) -> None:
		"""Tell the instrument, on the link thread rather than on the clock."""

		if self.on_change is None:
			return

		for name, value in owed:
			try:
				self.on_change(name, value)

			except Exception:
				LOG.warning("asserting %r of %r failed", name, self.name, exc_info=True)

		LOG.info("asserted %d setting(s) of %r to the instrument", len(owed), self.name)

	def apply (self, rest: list[str], value: typing.Any) -> bool:
		"""Write one setting, and tell the composition it moved."""

		if len(rest) != 1:
			raise Refused("that does not name a setting")

		parameter = self.parameters.get(rest[0])

		if parameter is None:
			raise Refused(f"this instrument has no setting called {rest[0]}")

		wanted = self._checked(parameter, value)

		if parameter.kind == "action":
			# **Nothing changed, and something happened.**  The composition is
			# told so it can act; the panel is acked by the service either way,
			# which is what clears its ring.  What it must not get is a
			# `changed` frame, because that is the service's cue to remember a
			# value — and remembering one here is the whole thing #2179 exists
			# to prevent.
			if self.on_change is not None:
				self.on_change(parameter.name, wanted)

			return False

		held = self.composition.data.setdefault(self.data_key, {})

		if held.get(parameter.name) == wanted:
			return False

		held[parameter.name] = wanted

		if self.on_change is not None:
			self.on_change(parameter.name, wanted)

		return True

	def _checked (self, parameter: Parameter, value: typing.Any) -> typing.Any:
		"""Refuse anything this setting could not hold, with a reason.

		**No sources are offered, so a cable is refused here** (#2419).  Only
		`Recipe` resolves a patch envelope when it builds; a reference stored in
		an instrument's settings would be handed to the composition's own
		`on_change` — which is where a control change gets sent — and would be
		worth nothing for ever, reported to every panel as though it were fine.
		"""

		return checked_value(parameter, value)


VELOCITY_RANGE = (1, 127)
"""How hard a note on a grid this adapter declares may be struck.

**Three copies of this pair used to be written out** — a step grid's
declaration, a note grid's, and the check that refuses a velocity — and two
halves of one number is how they come to disagree (#2436).  The check is the one
that mattered: a declaration saying 1 to 127 beside a check reading anything else
is a panel drawing a lane a person cannot reach the end of.

**It lives in the adapter and may not move to `controls.py` or the client**,
which is the whole of #2435's rule and the reason this is not simply a constant.
MIDI is *Subsequence's* domain and this file is the half that faces it; the
service carries no MIDI at all and says so twice in its own docstrings, and the
panel draws a mark in proportion to whatever range it was told rather than to
one it knows.  An adapter for a sampler will declare something else here and
nothing downstream will need changing.

**No unit beside it, and that is #2049 rather than an oversight.**  A unit is
drawn beside a *number*, and no number is drawn for a velocity anywhere on this
panel — a grid's weights are a lane of bars.  The field can be added the day
something reads it.
"""

DRAWABLE = superconductor.protocol.PARAMETER_KINDS + ("pitch", "position")
"""Every parameter kind `offerable` will pass to a panel, and nothing else.

``pitch`` and ``position`` are here and neither is a kind a panel ever sees:
this function turns each into a ``choice`` or a ``choices`` of what a
composition actually has — the pitches on this instrument, the places in this
pattern — which is the join the whole arrangement rests on (#1465).  They have
to be let through to be converted.

**They are the same join twice.**  The app says *this is a pitch* or *this is a
position* and can say no more, because which pitches exist and how long a
pattern is are both facts about a studio; the composition says they are these
ten drum voices, or these sixteen places.  Neither knows the other's half and
this package knows neither.

The rest is the shared vocabulary rather than a list of its own, because the
service checks incoming values against the same six and a copy here would be the
half that goes stale.
"""


def _as_parameter (field: dict[str, typing.Any]) -> Parameter:
	"""One entry of a catalogue read back as the thing that checks a value.

	The catalogue an app hands in is already in the shape a panel draws, so
	this is a reading rather than a translation: it exists so that a
	generator's parameter is refused by exactly the code an instrument's
	setting is refused by.
	"""

	return Parameter(
		name=str(field.get("name", "")),
		kind=str(field.get("kind", "number")),
		label=field.get("label"),
		minimum=field.get("min"),
		maximum=field.get("max"),
		step=field.get("step", 1),
		options=[(one.get("value"), one.get("label", one.get("value")))
		         for one in field.get("options", [])],
		default=field.get("default"),
		role=field.get("role"),
		unit=field.get(superconductor.protocol.UNIT),
		may_be_unset=superconductor.protocol.may_be_unset(field),
	)


def _outside (default: typing.Any, low: float, high: float) -> bool:
	"""Whether a parameter's own opening value falls outside a proposed bound.

	**Only a default that would actually be sent counts.**  `None` means the
	parameter opens unset and nothing is handed to the generator (#2249), so no
	bound can exclude it; a bool is not a number whatever Python thinks.  A
	`range` may declare a scalar default that widens into a pair (`euclidean`
	opens at velocity 100), and either end landing outside is enough.
	"""

	if isinstance(default, (list, tuple)):
		return any(_outside(one, low, high) for one in default)

	if isinstance(default, bool) or not isinstance(default, (int, float)):
		return False

	return not low <= default <= high


Positions = collections.abc.Mapping[
	str, collections.abc.Sequence[tuple[typing.Any, str]]]
"""Where a note may be placed in this pattern, by the unit the app counts in.

A value and the word for it, exactly as an ``options`` list is everywhere else,
because **a panel may not invent a label** (#2144) and what "step 3" is called
is the composition's to say — it is the one that knows a step is a sixteenth
here and that a musician counts from one.

**Keyed by unit because the app counts in more than one** (#2411): `hit_steps`
asks for positions in `steps` and `hit` asks for the same places in `beats`.
Which of them a parameter wants is on its own declaration; how many there are,
and what each is called, is the composition's.  A unit nobody supplied leaves
the parameter `undrawn` rather than guessed at, the same as a pitch with no
pitches to offer.
"""

Bounds = collections.abc.Mapping[
	"str | tuple[str, str]", tuple[float, float]]
"""What a composition says a parameter's range is, keyed by name or by name and unit.

A bare name bounds that parameter wherever it appears, and **a name with a unit
bounds only the meaning measured in that unit** — most specific winning, which
is the shape a page's `parts` and a composition's own overrides already have.

**One name really does cover two meanings, and it has already cost a session**
(#2413).  `grid` is on eight of Subsequence's entries: seven mean *how many
slots the pattern has* and `swing.grid` means *grid size in beats*, opening at
0.25, which a bound of 1 to 16 forbids — so Simon added a swing layer and could
then toggle nothing on that stack at all, because a stack is written whole and
one impossible value refuses every layer on it.

Until an app declared its units there was nothing on the wire that told the two
apart, and the defence was `_outside` below: notice that a bound excludes the
parameter's own default, and drop the bound with a warning.  That stays, because
a composition may still key a name plainly and a *future* collision has no unit
to separate it either — but it is the backstop now rather than the answer.
"""


def _bound_for (
	field: dict[str, typing.Any],
	narrowed: Bounds,
) -> tuple[float, float] | None:
	"""The bound this composition set for this parameter, if it set one.

	Most specific wins: a `(name, unit)` key is preferred to a bare name, so a
	composition can bound *how many slots* without touching the one entry where
	the same word means beats.
	"""

	name = str(field.get("name", ""))
	unit = field.get(superconductor.protocol.UNIT)

	if isinstance(unit, str) and (name, unit) in narrowed:
		return narrowed[(name, unit)]

	return narrowed.get(name)


def offerable (
	catalogue: collections.abc.Sequence[dict[str, typing.Any]],
	pitches: collections.abc.Sequence[str],
	bounds: Bounds | None = None,
	positions: Positions | None = None,
) -> list[dict[str, typing.Any]]:
	"""An app's catalogue, with the pitches this composition actually has.

	This is the join the whole arrangement rests on.  The app describing itself
	says *this parameter is a pitch* and can say no more, because which pitches
	exist is a fact about a studio; the composition says they are these ten
	drum voices.  Neither knows the other's half, and this package knows
	neither — it is handed both (#1465).

	A parameter this panel cannot draw is left out, its name recorded in
	``undrawn`` and its generator marked partial — the same courtesy the app pays
	upstream: better to say a generator is not fully drivable than to offer a
	control that cannot be completed.  **The two reasons are kept apart**, because
	``partial`` alone conflates "this generator is inherently partial" with "this
	panel could not draw one of its parameters", and only the second is anything
	anybody here can fix.

	A pitch parameter taking *several* pitches becomes a ``choices``.  It used to
	be dropped, and it was not a rare shape: twenty-two of thirty-three generators
	arrived partial for want of it, and they were not a random two thirds but
	every chord and melody writer in the catalogue (#2150).  Nothing had noticed
	because the only stack on the rig builds a drum pattern, where one voice is
	all you want.

	``bounds`` is the same division applied to numbers.  An app cannot know
	what a sensible range for ``pulses`` is, because that depends on how many
	steps the pattern has and the pattern is the composition's; where the
	composition does know, it says so here and the panel can draw a slider
	instead of a stepper.
	"""

	narrowed: Bounds = bounds or {}
	places: Positions = positions or {}
	offered: list[dict[str, typing.Any]] = []

	for generator in catalogue:
		fields: list[dict[str, typing.Any]] = []
		undrawn: list[str] = []

		for field in generator.get("parameters", []):
			# **A kind this package cannot draw is said out loud, not guessed at**
			# (#2379).  Everything that was not a pitch used to pass straight
			# through, and the fall-through at both ends of this file is *it is a
			# number* — so the first kind Subsequence invented that was not in the
			# vocabulary arrived on the glass as an unbounded dial opening at
			# zero, on a parameter that wanted a chord, and would have handed that
			# zero back to the generator.  Nothing was audible, because it landed
			# on a layer that could not run for another reason; that is luck and
			# it runs out.
			#
			# `undrawn` already means exactly this and has only ever fired on a
			# pitch with no pitches to offer.  Saying it here covers every kind
			# yet to be invented rather than this one.
			if field.get("kind") not in DRAWABLE:
				undrawn.append(str(field.get("name")))
				continue

			bound = _bound_for(field, narrowed) if field.get("kind") in ("number", "range") else None

			if bound is not None:
				low, high = bound

				# **A bound that excludes the parameter's own default is not
				# applied**, because a control born outside its own range is one
				# whose every write is refused — and refused naming a parameter
				# nobody touched.
				#
				# `bounds` is keyed by parameter *name* and applied across both
				# catalogues, so one word covering two meanings mis-bounds the
				# odd one out.  Measured 2026-09-10: `grid` is on eight entries,
				# seven meaning *how many slots the pattern has* and `swing`
				# meaning *grid size in beats* — and swing is the only one of the
				# eight carrying a default, 0.25, which a bound of 1 to 16
				# forbids.  Simon added a swing layer and could then toggle
				# nothing on that stack at all: bypass, reorder, add and remove
				# all write the whole stack, so one impossible value freezes every
				# control on it, and the refusal names a layer he had not touched.
				#
				# Skipped rather than clamped: clamping would give swing a grid of
				# one whole beat, which is a wrong answer somebody can hear.
				# Skipped rather than refused: the bound is right for the other
				# seven, and a composition should not fail to start over it.
				if _outside(field.get("default"), low, high):
					LOG.warning(
						"not bounding %s.%s to %s–%s: the app's own default is %r,"
						" which that range excludes — one name, two meanings",
						generator.get("name"), field.get("name"), low, high,
						field.get("default"))

					fields.append(field)
					continue

				fields.append({**field, "min": low, "max": high})
				continue

			if field.get("kind") == "position":
				# **A place in the pattern, offered as the places this pattern
				# has** (#2411 upstream, #2412 here).  Three of the ten
				# generators that could be added and could never run were
				# waiting on exactly this: the parameter they cannot do without
				# was not *described* in the catalogue at all, so there was
				# nothing to draw and nothing saying why.
				#
				# **The unit chooses the list**, which is the one place a unit is
				# read rather than drawn (#2435).  `hit_steps` asks in `steps`
				# and `hit` asks for the same places in `beats`, and no other
				# field separates them.
				held = places.get(str(field.get(superconductor.protocol.UNIT)))

				if not held:
					undrawn.append(str(field.get("name")))
					continue

				fields.append({
					**{key: kept for key, kept in field.items() if key != "multiple"},
					"kind": "choices" if field.get("multiple") else "choice",

					# What it was stays with it, for the reason a pitch's does:
					# a choices of places and a choices of waveforms are the same
					# kind and are not the same thing.
					"role": "position",
					"options": [{"value": at, "label": said} for at, said in held],
				})
				continue

			if field.get("kind") != "pitch":
				fields.append(field)
				continue

			if not pitches:
				undrawn.append(str(field.get("name")))
				continue

			# **What it was stays with it.**  A pitch becomes a choice here and
			# every trace of what made it one would otherwise be lost — which
			# matters on the glass, where a line from a generator arrives level
			# with the row it writes rather than at the middle of a pattern that
			# has ten (#2109).  A panel guessing that from the option list alone
			# has to guess, and a composition may offer a wider pool of voices
			# than any one pattern has rows.  Saying it costs a word.
			fields.append({
				**{key: held for key, held in field.items() if key != "multiple"},
				"kind": "choices" if field.get("multiple") else "choice",
				"role": "pitch",
				"options": [{"value": pitch, "label": pitch} for pitch in pitches],
			})

		one = {
			**generator,
			"parameters": fields,
			"partial": bool(generator.get("partial")) or bool(undrawn),
		}

		# Only when there is something to say. An empty list on every generator
		# is a field a reader has to check before believing, and thirty-three of
		# them is noise around the one that matters.
		if undrawn:
			one["undrawn"] = undrawn

		offered.append(one)

	return offered


class PitchSet (Control):
	"""A set of pitches somebody chose, which sounds nothing and feeds things that do.

	**A note set is a value rather than a placement** (#2374).  Every other
	control here either makes a sound or arranges one; this one exists only to be
	*read*, by a generator's pitch parameter that has been patched to it.

	The point is sharing.  A pitch pool typed into one arpeggio layer belongs to
	that layer; the same pool held here can feed an arpeggio on the Minitaur and
	another on the Matriarch, and the two cannot drift apart because there is one
	of it.  Reading is not consuming, so fanning out costs nothing and needs no
	topology — which is the whole reason a value graph is cheaper than the motif
	graph #2225 designed.

	**Order is kept as it was chosen**, never sorted.  The pitches of a chord are
	not a set, and a generator handed a root first is entitled to use that.

	**Each pitch travels with the note it sounds.**  A panel needs it to draw a
	keyboard at all, and a consumer needs it to fold a choice into its own
	register — see ``Recipe._folded``.  Which note a row name sounds is the
	composition's to say (#1465); this holds what it was told.
	"""

	kind = "pitch_set"

	def __init__ (
		self,
		composition: typing.Any,
		name: str = "notes",
		title: str | None = None,
		pitches: collections.abc.Mapping[str, int] | None = None,
		chosen: collections.abc.Sequence[str] = (),
		about: collections.abc.Sequence[tuple[str, typing.Any]] = (),
	) -> None:
		"""Hold a set of pitches, from the pool the composition says exists."""

		self.composition = composition
		self.name = name
		self.title = title
		self.about = about

		self.pitches: dict[str, int] = dict(pitches or {})
		"""Every pitch this set may hold, and the note each one sounds."""

		self.chosen: list[str] = [one for one in chosen if one in self.pitches]
		"""What is in the set now, in the order it was chosen."""

	def declaration (self) -> dict[str, typing.Any]:
		"""The pool, with the note behind each name."""

		return {
			"type": self.kind,
			"pitches": [{"value": named, "label": named, "midi": note}
			            for named, note in self.pitches.items()],
			**self.said(),
		}

	def snapshot (self) -> dict[str, typing.Any]:
		"""What is in the set, and whether it is contributing at all."""

		return {"chosen": list(self.chosen), "enabled": self.enabled}

	def apply (self, rest: list[str], value: typing.Any) -> bool:
		"""Replace the set entire, or switch it off."""

		if rest == ["enabled"]:
			# Through the helper every other control uses, rather than setting the
			# flag here: it short-circuits a no-op, so switching a set off twice
			# stops emitting a `changed` frame that says nothing (#2429).  The
			# mute branch inside it is skipped for a set, which drives no pattern.
			return self._keep_enabled(value)

		if rest != ["chosen"]:
			raise Refused("a pitch set is addressed as control/chosen")

		if not isinstance(value, list):
			raise Refused("a pitch set takes a list of pitches")

		taken: list[str] = []

		for one in value:
			if one not in self.pitches:
				raise Refused(f"this set offers no pitch called {one}")

			if one in taken:
				raise Refused(f"{one} is named twice, and a pitch is either in the set or not")

			taken.append(str(one))

		self.chosen = taken

		return True

	def notes (self) -> list[int]:
		"""What is in the set, as the notes they sound, in the order chosen.

		A set that is switched off is empty rather than absent, because an empty
		pitch list is a thing every consumer already handles: ``arpeggio`` rests
		on one and says so in its own docstring.  A mute is therefore silence
		wherever this is patched, with nothing to special-case at the far end.
		"""

		if not self.enabled:
			return []

		return [self.pitches[one] for one in self.chosen]


class Recipe (Control):
	"""An ordered stack of generators that build one pattern.

	A person adds a generator from the glass, tunes it, bypasses it, and moves
	it up or down the stack; the pattern is rebuilt from the stack every cycle.
	The order is the musical content as much as the parameters are, because a
	fill told to skip where a note already sits depends on what ran before it.

	**The stack is the only thing kept.**  What a generator produces is made
	afresh each cycle and never written down (#1965), so a person's own taps
	remain the only notes anything stores and no algorithm can erase one.

	This knows the name of no generator.  The catalogue is handed in by the
	composition, which got it from the app that owns those generators, and the
	pitches are handed in beside it because only a composition knows what a
	studio has.
	"""

	kind = "recipe"

	def __init__ (
		self,
		composition: typing.Any,
		catalogue: collections.abc.Sequence[dict[str, typing.Any]],
		pitches: collections.abc.Sequence[str] = (),
		pitch_notes: collections.abc.Mapping[str, int] | None = None,
		bounds: Bounds | None = None,
		positions: Positions | None = None,
		transforms: collections.abc.Sequence[dict[str, typing.Any]] = (),
		builds: str | None = None,
		sources: dict[str, collections.abc.Callable[[typing.Any], None]] | None = None,
		pulses_per_beat: int | None = None,
		data_key: str = "recipe",
		name: str = "recipe",
		title: str | None = None,
		about: collections.abc.Sequence[tuple[str, typing.Any]] = (),
	) -> None:
		"""Offer a stack over a list the composition keeps."""

		self.pitch_notes: dict[str, int] = dict(pitch_notes or {})
		"""What note each of this stack's own pitches sounds, where the composition said.

		Only needed to *fold* a patched pitch set into this stack's register, and
		empty is a perfectly good answer: a stack whose rows are drum voices has
		no register to fold into, and one that is never patched never asks.

		**Without it two instruments cannot share a set of notes.**  The Minitaur
		here reaches C1 to C3 and the Matriarch C3 to C5, so a literal pitch
		played through both is silent on one of them — a person patches one set
		to two arpeggios, hears one instrument, and has nothing to look at.  What
		they mean by *the same notes* is the same pitch classes, each in its own
		instrument's register, and that is what folding does.
		"""

		self.builds = builds
		"""Which control this stack contributes to, by name.

		The panel draws the two joined by a line and puts this stack's own
		buttons on the pattern it feeds, so a person can see what makes what.
		Nothing here reads it; it is a fact about the composition that the
		composition states, like the rows of a grid.
		"""

		self.pulses_per_beat = pulses_per_beat
		"""How many pulses a beat is, or None to report nothing.

		**An app's number, not this package's**, which is why it is handed in
		rather than known: nothing in this module imports the sequencer it talks
		to, and that is deliberate — the adapter is duck-typed on whatever a
		composition hands it.

		Given, this stack works out which cells its generators realised each
		cycle and says so, and a panel can draw them beside the steps a person
		tapped (#1925).  Withheld, it says nothing and behaves exactly as it did.
		"""

		self.sources = sources if sources is not None else {}
		"""Which other grids this stack may take notes from, and how to play one.

		A name the composition also declared as a control, against a function
		that writes that grid onto a pattern being built.  **The function is the
		composition's because turning a grid into notes is** — a velocity, a
		note map, a length, whether a row is a drum voice or a pitch.  This
		routes; it does not know what it is routing (#1465).

		**The composition's own mapping is held rather than copied** (#2421), so a
		source added after this stack was built is offered the next time it
		declares.  A rack makes a grid at run time (#2226) and every stack here is
		constructed at import, so a copy taken now is a stack that can never route
		what the panel makes: the grid is registered, drawn, played on, and refused
		by both halves as a source that was never declared.  What the copy guarded
		against was a composition mutating a stack's sources — which is exactly the
		mechanism that feature needs, so the guard was pointed at the feature.

		Nothing here writes to it, and a stack offering a grid it should not is a
		composition's mistake to make: which stacks may take from what is the
		composition's to say, like the rows (#1465).

		Empty by default, which is a stack that offers generators only.  That is
		what every stack was before #2108 and what a composition with nothing
		worth sharing still wants.
		"""

		self.composition = composition
		self.pitches = list(pitches)
		self.catalogue = offerable(catalogue, self.pitches, bounds, positions)

		self.transforms = offerable(transforms or [], self.pitches, bounds, positions)
		"""What this stack may *reshape* with, as against what it may add.

		A second catalogue rather than a longer one, because the two are
		different things and a panel has to draw them differently (#2119,
		#2246): a generator invents notes and a transform works on everything
		above it.  Drawn alike, the order of a stack stops meaning anything —
		and order is the whole of what a rack is.
		"""

		self._building = False
		"""Whether this stack is inside a build, so a route leading back here is
		refused rather than recursed (#2230)."""

		self._playing_route: str | None = None
		"""Which route is in flight, so the refusal can name the cable."""
		self.data_key = data_key
		self.name = name
		self.title = title
		self.about = list(about)

		self._offered = {
			generator.get("name"): {
				str(field.get("name")): _as_parameter(field)
				for field in generator.get("parameters", [])
			}
			for generator in self.catalogue
		}

		# **A parameter says whether it must be supplied, and nothing here infers
		# it.**  The two cases look identical without the flag — a parameter with
		# no default at all and one defaulting to ``None`` — and they want
		# opposite treatment: fill the first or the call fails, leave the second
		# alone or the generator is handed a zero where it asked to be told
		# nothing.  This used to be inferred from parameter *order*, which was a
		# stand-in that said so in its own docstring, and which shipped `rotate`
		# inert along with eight others.  An app that does not mark a parameter
		# is taken at its word: nothing is required, and whatever then fails to
		# run says so once in the log rather than guessing again.
		self._must_have = {
			generator.get("name"): {
				str(field.get("name"))
				for field in generator.get("parameters", [])
				if field.get("required")
			}
			for generator in self.catalogue
		}

		# **Both catalogues share one map of shapes, and a collision must not be
		# silent.**  No name appears in both today.  If one ever does the two are
		# indistinguishable by name, and a layer would run whichever won the
		# dictionary — the exact shape of fault this package has been bitten by
		# three times.  So the generator keeps the name, the transform is not
		# offered, and it is said out loud rather than found later.
		for shape in self.transforms:
			named = str(shape.get("name"))

			if named in self._offered:
				LOG.error(
					"%r is offered as both a generator and a transform; keeping "
					"the generator, because a layer names what it runs and these "
					"two cannot be told apart by name", named)
				continue

			self._offered[named] = {
				str(field.get("name")): _as_parameter(field)
				for field in shape.get("parameters", [])
			}
			self._must_have[named] = {
				str(field.get("name"))
				for field in shape.get("parameters", [])
				if field.get("required")
			}

		self.link: "AppLink | None" = None
		"""How a stack says what it realised, and where it finds the grid it feeds."""

		self._seeds: dict[str, bool] = {}
		"""Which layers will take a stream of their own, asked once each.

		Read off the live method rather than the catalogue, because the
		catalogue deliberately leaves ``seed`` out — it is a machine's parameter
		and not a person's, so it is never *offered* (#2233).  Supplying one is
		a different act from offering it.  Cached because ``inspect.signature``
		is far too slow to run once a layer once a bar on the clock's thread.
		"""

		self._complained: set[str] = set()

		self._failing: dict[str, str] = {}
		"""Which layers did not run this cycle, and the app's own words for why.

		Rebuilt from nothing on every build, so a layer that starts working stops
		being in it without anything having to remember that it once was."""

		self._reported_failing: dict[str, str] = {}
		"""What the glass was last told, so the frame that clears it is sent once
		rather than a frame a cycle saying nothing is wrong."""
		"""Generators that have already failed once, so a bar does not flood a log.

		A pattern is rebuilt every cycle, so anything said here is said twice a
		second until it is fixed.  Subsequence took the same decision about its
		own bounds and for the same reason.
		"""

	def attach (self, link: "AppLink") -> None:
		"""Take the link, which is also the register of what else this app offers."""

		self.link = link

	def declaration (self) -> dict[str, typing.Any]:
		"""Every generator that can be offered, and what each of them takes."""

		declared: dict[str, typing.Any] = {"type": self.kind, "generators": self.catalogue}

		if self.transforms:
			declared["transforms"] = self.transforms

		if self.builds is not None:
			declared["builds"] = self.builds

		if self.sources:
			# Names only. What each is called on the glass is the control's own
			# title, which a panel already has — saying it twice would be two
			# places for it to be wrong.
			declared["sources"] = sorted(self.sources)

		declared.update(self.said())

		return declared

	def snapshot (self) -> dict[str, typing.Any]:
		"""The stack as it stands, in order."""

		return {"layers": self.layers()}

	def layers (self) -> list[dict[str, typing.Any]]:
		"""A copy of the stack, so a caller cannot edit it by accident."""

		held = self.composition.data.get(self.data_key) or {}

		kept = []

		for layer in held.get("layers") or []:
			one: dict[str, typing.Any] = {
				"id": str(layer.get("id", "")),
				"kind": str(layer.get("kind", "generator")),
				"index": int(layer.get("index", 0)),
				"bypassed": bool(layer.get("bypassed", False)),
				"params": dict(layer.get("params") or {}),
			}

			# Each kind carries the one thing that says what it plays, and
			# neither carries the other's — a routed grid has no generator and a
			# generator has no source.
			if one["kind"] == "route":
				one["source"] = layer.get("source")

			elif one["kind"] == "transform":
				one["transform"] = layer.get("transform")

			else:
				one["generator"] = layer.get("generator")

			kept.append(one)

		return kept

	def apply (self, rest: list[str], value: typing.Any) -> bool:
		"""Rewrite the stack, or move one parameter of one layer."""

		if rest == ["layers"]:
			return self._keep_stack(value)

		if len(rest) != 2:
			raise Refused("that names neither the stack nor one of its parameters")

		return self._keep_parameter(rest[0], rest[1], value)

	def applied (self, rest: list[str], value: typing.Any) -> typing.Any:
		"""The stack as it now stands, or one parameter as it was actually kept.

		A layer is stored with every parameter its generator has, filled from
		that generator's own defaults, so what was asked for and what is held
		are different things here in a way they are nowhere else.
		"""

		if rest == ["layers"]:
			return self.layers()

		layer = next((one for one in self.layers() if one["id"] == rest[0]), None)

		return layer["params"].get(rest[1]) if layer is not None else value

	@staticmethod
	def _runs (layer: dict[str, typing.Any]) -> typing.Any:
		"""What this layer calls, whichever field its kind keeps it in.

		Said once here rather than at each of the three places that ask, which
		is how `generator` and `source` came to be checked in two different
		ways in the first place.
		"""

		return (layer.get("transform") if layer.get("kind") == "transform"
		        else layer.get("generator"))

	def _keep_stack (self, value: typing.Any) -> bool:
		"""Take a whole stack, checked entire before any of it is kept."""

		if not isinstance(value, list):
			raise Refused("a stack is a list of layers")

		wanted: list[dict[str, typing.Any]] = []
		seen: set[str] = set()
		kinds = self._declared_kinds()
		standing = {one["id"]: one for one in self.layers()}
		counting = self._counted()

		for entry in value:
			if not isinstance(entry, dict):
				raise Refused("a layer is an object")

			name = entry.get("id")

			if not isinstance(name, str) or not name:
				raise Refused("a layer needs an id of its own")

			if name in seen:
				raise Refused(f"two layers both call themselves {name}")

			seen.add(name)

			kind = str(entry.get("kind", "generator"))

			# The kind's old spelling, read for the same reason the service reads
			# it: a capture written before 1.24.0 holds `pattern`, and losing
			# somebody's routing to a rename would be this project doing to
			# itself what it refuses to do to anybody else.  `wanted` is built
			# from `kind` below, so converting it here is the whole of it.
			if kind == "pattern":
				kind = "route"

			if kind not in superconductor.protocol.LAYER_KINDS:
				raise Refused(f"a layer cannot be a {kind}")

			if kind == "route":
				source = entry.get("source")

				if source not in self.sources:
					raise Refused(f"this stack cannot take from a pattern called {source}")

				wanted.append({
					"id": name,
					"kind": kind,
					"source": source,
					"index": self._numbered(str(source), name, entry, standing, counting),
					"bypassed": bool(entry.get("bypassed", False)),

					# Nothing to tune: a routed grid plays what is drawn on it.
					"params": {},
				})
				continue

			# **The two name their function in different fields**, so a stack
			# read back says what each layer *is* without a lookup, and a panel
			# too old to know about transforms finds no `generator` on one and
			# draws nothing rather than drawing it as something it is not.
			running = "transform" if kind == "transform" else "generator"
			generator = entry.get(running)
			offered = self._offered.get(generator)
			known = ({shape.get("name") for shape in self.transforms}
			         if kind == "transform"
			         else {shape.get("name") for shape in self.catalogue})

			if offered is None or generator not in known:
				raise Refused(f"there is no {running} called {generator}")

			held = entry.get("params")
			kept: dict[str, typing.Any] = {}

			for parameter, setting in (held if isinstance(held, dict) else {}).items():
				if parameter not in offered:
					raise Refused(f"{generator} has no parameter called {parameter}")

				checked = checked_value(offered[parameter], setting, kinds)

				# A stack arriving with an explicit null carries the same meaning
				# one parameter at a time does, and has to reach the same place:
				# not in `kept`, so the merge below leaves it out.  `_opening`
				# already omits every parameter that opens unset, so absent here
				# is absent in the layer.
				if checked is None:
					continue

				kept[parameter] = checked

			wanted.append({
				"id": name,
				"kind": kind,
				running: generator,
				"index": self._numbered(str(generator), name, entry, standing, counting),
				"bypassed": bool(entry.get("bypassed", False)),
				"params": {**self._opening(str(generator)), **kept},
			})

		if self.layers() == wanted:
			return False

		held = self.composition.data.setdefault(self.data_key, {})
		held["layers"] = wanted
		held["counts"] = counting

		return True

	def _counted (self) -> dict[str, int]:
		"""The highest number handed out to each generator so far.

		Seeded from the stack itself as well as from what was written down, so
		a composition that predates the counter does not start again at one and
		hand a fresh window a number that is already on the glass.
		"""

		held = self.composition.data.get(self.data_key) or {}
		counted = {str(one): int(mark) for one, mark in (held.get("counts") or {}).items()}

		for layer in self.layers():
			named = str(layer.get("source") if layer["kind"] == "route" else self._runs(layer))
			counted[named] = max(counted.get(named, 0), layer["index"])

		return counted

	def _declared_kinds (self) -> dict[str, str]:
		"""Every control this app declared, against the sort of thing it is.

		What a patch is checked against (#2419).  Read from the link rather than
		held, because a rack can make a control after this stack was built and a
		copy taken here would be the same staleness #2421 is about.
		"""

		if self.link is None:
			return {}

		return {name: one.kind for name, one in self.link.controls.items()}

	def _numbered (
		self,
		generator: str,
		layer_id: str,
		entry: dict[str, typing.Any],
		standing: dict[str, dict[str, typing.Any]],
		counting: dict[str, int],
	) -> int:
		"""The number this layer is known by on the glass, for the whole of its life.

		A person reads "Euclidean 2" on a window and reaches for that window, so
		the number has to be a name and not a position.  A layer already in the
		stack keeps the number it has whatever a panel sends: renumbering under
		somebody's hand because a neighbour was removed is the exact surprise
		this exists to prevent.

		A number is never handed out twice, so a stack may read 1, 3, 4 after a
		removal.  That is stranger to look at and much safer to work with, which
		is the right way round.  The high-water mark is written down beside the
		stack, so it survives a restart of the composition as well.
		"""

		held = standing.get(layer_id, {}).get("index")

		if isinstance(held, int) and held > 0:
			return held

		# A panel replaying a stack it captured earlier sends the numbers back
		# with it, and those are the ones the person already knows.
		asked = entry.get("index")

		if isinstance(asked, int) and asked > 0:
			counting[generator] = max(counting.get(generator, 0), asked)

			return asked

		counting[generator] = counting.get(generator, 0) + 1

		return counting[generator]

	def _keep_parameter (self, layer_id: str, parameter: str, value: typing.Any) -> bool:
		"""Move one parameter of one layer, which is what turning a knob does."""

		held = self.composition.data.setdefault(self.data_key, {}).setdefault("layers", [])
		layer = next((one for one in held if one.get("id") == layer_id), None)

		if layer is None:
			raise Refused(f"there is no layer called {layer_id}")

		running = self._runs(layer)
		offered = self._offered.get(running, {})

		if parameter not in offered:
			raise Refused(f"{running} has no parameter called {parameter}")

		wanted = checked_value(offered[parameter], value, self._declared_kinds())
		params = dict(layer.get("params") or {})

		# **Unset is an absent key, not a stored `None`** (#2381).  A generator
		# reads its parameters as keyword arguments, so what tells it to decide
		# for itself is the argument not being passed — `ghost_fill(grid=None)`
		# and `ghost_fill()` happen to agree, and `arpeggio(pool, count=None)`
		# and `arpeggio(pool)` do too, but only because the default is `None`.
		# Storing the null would also make this the one parameter whose held
		# value a capture writes down and a restore cannot replay.
		if wanted is None:
			if parameter not in params:
				return False

			del params[parameter]

		elif params.get(parameter) == wanted:
			return False

		else:
			params[parameter] = wanted

		# **The dict is replaced rather than edited in place**, because this runs
		# on the link thread and `build` reads the same layer on the clock.  A
		# key appearing or disappearing under a reader is the shape of
		# `a4b7e74`, which killed this composition on start, and of #2341 —
		# and giving a parameter a way back to unset is what makes a key
		# *disappear* here for the first time.
		#
		# **Measured, and it does not reproduce**: 20,000 set/unset pairs against
		# a thread calling `layers()` in a loop raised nothing, because the copy
		# there is `dict(d)`, which CPython does at C level without releasing the
		# GIL.  `a4b7e74` was a Python-level `for` over a live collection, which
		# is a different thing and does yield.  So this is not a fix for a fault
		# anybody has met; it is one store instead of two on the path the clock
		# reads, and it costs a dict copy of at most a dozen keys on a gesture a
		# finger makes.  The atomicity it would otherwise lean on is an
		# implementation detail of one interpreter, and the clock is paramount.
		layer["params"] = params

		return True

	def _opening (self, generator: str) -> dict[str, typing.Any]:
		"""What a freshly added layer holds before anybody has touched it.

		A parameter with a default of its own starts there, so the glass shows
		what is playing rather than only what somebody has typed.  A parameter
		with **no** default is filled only when the generator cannot be called
		without it — and is otherwise left out entirely, because leaving it out
		is what tells the generator to decide for itself.

		That distinction is not decoration.  ``ghost_fill(grid=None)`` means
		*use the pattern's own grid*; ``ghost_fill(grid=0)`` means a grid of no
		steps, and a layer given the second places nothing at all while looking
		perfectly well set up on the glass.  Filling every absent default with a
		number did exactly that.
		"""

		offered = self._offered.get(generator, {})
		must = self._must_have.get(generator, set())

		return {
			name: parameter.opening()
			for name, parameter in offered.items()
			if parameter.default is not None or name in must
		}

	def build (self, pattern: typing.Any) -> None:
		"""Play the whole stack onto a pattern being built, in order.

		Called from the composition's pattern function, so this runs on the
		clock loop once a cycle.  It does no I/O and holds no lock; the cost is
		the generators' own, which is what it would be if they were written out
		by hand in the same order.

		A layer that will not run is skipped rather than allowed to raise.
		Subsequence survives a failing rebuild by design — it costs that
		pattern its cycle, never the clock — but for an instrument that is the
		wrong failure: one bad layer would silence the part every bar with the
		reason in a log nobody is reading.  Skipping keeps the rest playing,
		which is what a person can actually hear and correct.

		**What the stack put there is read back and reported**, so the panel can
		draw it beside the steps somebody tapped (#1925).  Read once either side
		of the whole stack rather than around each layer: a person is shown what
		the algorithms did, not which of them did it, and the read-back cannot
		say the second anyway (#2102's accepted limit).  Two walks of a couple
		of dozen notes, against generators that have just run — this is not the
		expensive thing on this path.
		"""

		# **A stack builds at most once a cycle** (#2230). A stack is drawn
		# wherever its pattern is drawn (#2211), so a grid and the stack feeding
		# it share a page and a cable has two plausible ends; dragged to the
		# wrong one, the source's play function builds this very stack.
		#
		# The recursion is not the damage. `RecursionError` is an `Exception`,
		# so the route below catches it and everything unwinds for a millisecond
		# of work — but **every level reports what it landed**, which put 482
		# `realised` frames on the link thread in one cycle and took the rig
		# down. Refusing the nested *build* rather than the nested route matters:
		# refusing the route alone still lets the re-entered stack replay its
		# generators, so the part doubles quietly.
		#
		# It catches an indirect loop for the same reason — whichever stack is
		# re-entered is the one holding the flag.
		if self._building:
			self._complain(
				self.name,
				f"the {self._playing_route!r} route leads back to this stack, "
				f"which is already building; nothing can be routed in a circle")

			return

		self._building = True

		try:
			self._play_once(pattern)

		finally:
			# In a `finally` so one generator raising inside a routed stack
			# cannot leave the flag set and silence this block for ever, with
			# nothing on the glass to say why.
			self._building = False

	def _play_once (self, pattern: typing.Any) -> None:
		"""The body of one build, called only when this stack is not already in one."""

		# **Emptied here rather than added to**, so a layer that starts working
		# again stops being reported without anything having to notice that it
		# once failed. The verdict is about this cycle and no other, which is the
		# same discipline `realised` follows (#1965) and for the same reason.
		self._failing = {}

		before = self._reads(pattern) if self.pulses_per_beat else None

		# **One draw, before any layer runs, and every layer keys off it**
		# (#2233).  A pattern has one random stream and every layer used to draw
		# from it in call order, so a layer's notes depended on its neighbours:
		# measured, turning `pulses` from 7 to 3 on the layer *above* moved the
		# one below from [0, 18, 36, 54] to [0, 18, 36, 72].  Reorder, bypass and
		# knob are the whole gesture set of a rack, and all three did this.
		#
		# Taking the base here rather than per layer is what makes it a fix: the
		# shared stream is drawn from exactly once whatever the stack holds, so
		# adding, moving or silencing a layer cannot move the base.
		#
		# **And it is one draw rather than a constant so a layer still evolves.**
		# Seeding each layer from its id alone — which is what #2233 proposed —
		# freezes it: `seed=` builds a fresh `Random(seed)` for that call, so the
		# layer would place the same bar for ever.  Measured over three cycles,
		# identical.  The stream advances a cycle at a time, so a base drawn from
		# it moves with the music and holds still exactly when Subsequence says
		# it should: `lock()` re-deals the stream from a fixed seed each cycle,
		# so a locked pattern draws the same base and every layer under it lands
		# in the same place.  A freeze gesture of our own (#2232) is then a
		# question of what goes in the key, not of a second mechanism.
		base = self._base(pattern)

		# **Read between the layers, not only around them.** A dot could say
		# that *something* put a note there and not what — so Simon went looking
		# for a generator behind a note the routed grid had contributed, and
		# there was none to find. Reading after each layer costs one list copy
		# per layer instead of two per cycle, on a stack that is four deep.
		landed: list[tuple[str, list[typing.Any]]] = []

		for layer in self.layers():
			if layer["bypassed"]:
				continue

			if layer["kind"] == "route":
				source = str(layer.get("source"))
				play = self.sources.get(source)

				if play is None:
					self._complain(source, "this composition offers no such pattern",
					               layer=str(layer["id"]))
					continue

				# A grid switched off contributes nothing, wherever it is routed.
				# The route is still there and still drawn; it just carries
				# nothing, which is the difference between a mute and a delete.
				held = self.link.controls.get(source) if self.link is not None else None

				if held is not None and not held.enabled:
					continue

				# **A route may not lead back to the stack playing it** (#2230).
				# A stack is drawn wherever its pattern is drawn (#2211), so a
				# grid and the stack feeding it share a page and a cable has two
				# plausible ends. Dragged to the wrong one, the source's play
				# function builds this very stack — and the recursion is not the
				# damage. `RecursionError` is an `Exception`, so the line below
				# catches it and everything unwinds for a millisecond of work;
				# what costs is that *every level reports what it landed*, which
				# put 482 `realised` frames on the link thread in one cycle and
				# took the rig down.
				#
				# Guarding the call rather than the whole of `build` is what lets
				# the complaint name the cable: the flag is set only while a
				# route is in flight, so an ordinary first route passes and a
				# re-entrant one does not. It catches an indirect loop for the
				# same reason — whichever stack is re-entered still has its own
				# route in flight.
				# Remembered only so the refusal above can name the cable. A
				# nested build knows it is nested and cannot know what led there.
				self._playing_route = source

				try:
					play(pattern)

				except Exception as error:
					self._complain(source, str(error), layer=str(layer["id"]))

				if before is not None:
					landed.append((str(layer["id"]), self._reads(pattern) or []))

				continue

			# **A transform is called exactly as a generator is**, and the
			# difference is what it does rather than how it is reached: one
			# invents notes and the other reshapes whatever is above it in the
			# stack. Which is why the order of a stack is the whole of what it
			# means, and why the two must not be drawn alike (#2246).
			#
			# **And a transform acts on the entire pattern, hand taps included.**
			# There is no scratch builder yet, so a `rotate` here rolls the notes
			# somebody tapped as well as the ones a generator made. That is right
			# for the eight of thirteen that are *feel* — swing, randomize,
			# legato — and is the thing a block has to say plainly for the five
			# that are not. It stops being true the day a node builds into its
			# own scratch (#2225), and this layer kind does not change then.
			generator = str(self._runs(layer))
			method = getattr(pattern, generator, None)

			if method is None:
				self._complain(
					generator,
					f"this Subsequence has no such {layer['kind']}",
					layer=str(layer["id"]))
				continue

			arguments = self._arguments(generator, layer["params"])
			seed = self._seed_for(method, generator, str(layer["id"]), base)

			if seed is not None:
				arguments["seed"] = seed

			try:
				method(**arguments)

			except Exception as error:
				self._complain(generator, str(error), layer=str(layer["id"]))

			if before is not None:
				landed.append((str(layer["id"]), self._reads(pattern) or []))

		if before is not None:
			self._say_what_landed(before, landed)

		# **Outside that guard on purpose.** `_say_what_landed` needs a grid it
		# can address cells on and gives up without one; a stack that will not
		# run has to say so whether or not anybody can draw its notes, and a
		# stack whose grid this panel cannot read is exactly where a silent
		# failure is hardest to spot.
		self._say_what_failed()

	def _reads (self, pattern: typing.Any) -> list[typing.Any] | None:
		"""What is on the pattern now, or None if it cannot be read at all.

		The two are different answers and were briefly the same one: a pattern
		holding nothing reports nothing realised, and a pattern that cannot be
		asked reports *nothing at all*.  A composition older than the read-back,
		or one whose pattern object is something else entirely, is not an error —
		it is a panel that draws no dots, and everything else works exactly as
		before.
		"""

		reader = getattr(pattern, "placed", None)

		return list(reader()) if callable(reader) else None

	def _say_what_landed (
		self,
		before: list[typing.Any],
		landed: list[tuple[str, list[typing.Any]]],
	) -> None:
		"""Report the cells this stack realised, as rows and step numbers, and
		**which layer put each one there**.

		Ephemeral and stored nowhere: an event rather than a change, because
		these notes are not intent and must never be applied as if they were
		(#1965).  A person's taps remain the only thing anything keeps.

		Carrying the layer is what lets a panel tell a note a routed grid
		contributed from one an algorithm invented — which are different things
		wearing the same mark until now, and Simon read the first as the second.
		"""

		grid = self._target()

		if grid is None or self.link is None or self.pulses_per_beat is None:
			return

		# **In the unit the grid is addressed in**, which is not always a step.
		# A note grid divides a step into `divisions` places a note may start,
		# and a panel addresses it in those (#2115) — so a dot reported in steps
		# would land at a sixth of its position on the Minitaur's bassline, which
		# declares six. A step grid has one place per step and is unchanged.
		#
		# **`positions` is a property, and reading it as a method was #2219.**
		# `callable()` on an int is False, so the fallback took `steps` and the
		# whole bar was reported six times too coarse — the panel divides what
		# arrives by `divisions`, so eleven notes spread across sixteen cells
		# were drawn in the first three. It sounded right throughout, which is
		# why it read as a generator that stopped rather than a dot in the wrong
		# place. A default rather than a `callable` guard: a `StepGrid` has no
		# `positions` at all and a step is its place.
		bound = int(getattr(grid, "positions", grid.steps))

		per_place = self.pulses_per_beat * grid.beats / bound

		if per_place <= 0:
			return

		known = set(grid.rows)
		cells: dict[str, dict[str, typing.Any]] = {}
		seen = set(before)

		for layer, after in landed:
			fresh = set(after) - seen
			seen = set(after)

			self._gather(cells, fresh, layer, known, per_place, bound)

		self._report_cells(cells)

	def _gather (
		self,
		cells: dict[str, dict[str, typing.Any]],
		fresh: set[typing.Any],
		layer: str,
		known: set[str],
		per_place: float,
		places: int,
	) -> None:
		"""Fold one layer's new notes into the cells being reported."""

		# **A row for a note that arrived without one**, built from the map this
		# stack was handed rather than from anything this package knows about
		# pitch (#1465).  Only where a map is unambiguous: a pitched grid's rows
		# *are* its notes, so the answer is exact, while a drum map may name two
		# voices on one note and there is no answer at all.
		by_note: dict[int, str] = {}

		for named, note_number in (self.pitch_notes or {}).items():
			if named in known:
				by_note[note_number] = named if note_number not in by_note else ""

		for note in fresh:
			row = getattr(note, "origin", None)

			# **A generator may place a note without saying which row it was**,
			# and three of them do: `arpeggio`, `chord` and `strum` resolve their
			# pitches to numbers before placing, so the name never reaches the
			# note — where `de_bruijn`, handed the same list of names, keeps it.
			# Measured 2026-09-10 and reported upstream; it is not this package's
			# to fix and this is not a workaround for it, because **the panel
			# should not need a generator's cooperation to draw what it played.**
			#
			# The pitch is the fact and the name was only ever a way of saying
			# it, so a note with no name is matched by what it sounds. Nothing is
			# invented: the map is the composition's own.
			if not isinstance(row, str) or row not in known:
				row = by_note.get(int(getattr(note, "pitch", -1) or -1), "")

			# A note that still cannot be matched to a row must not be drawn, and
			# neither must one the primary device will not sound — a hit on the
			# glass that makes no sound is a lie.
			if not row or row not in known:
				continue

			if getattr(note, "primary_unmapped", False):
				continue

			step = int(getattr(note, "position", 0) // per_place)

			if not 0 <= step < places:
				continue

			# **How hard, not only whether.** A ghost fill is quiet by its whole
			# nature and drawing it at the weight of a full hit says the opposite
			# of what it is (Simon, 2026-09-05).
			#
			# The loudest wins where two contributions land on one step, because
			# that is what a person hears: two notes on one drum voice are one
			# sound at the weight of the louder.
			loud = int(getattr(note, "velocity", 0) or 0)
			held = cells.setdefault(row, {})
			standing = held.get(str(step))

			if standing is None or loud > int(standing.get("v", 0)):
				held[str(step)] = {"v": loud, "from": layer}

	def _report_cells (self, cells: dict[str, dict[str, typing.Any]]) -> None:
		"""Send what the stack realised, once a cycle and unconditionally."""

		grid = self._target()

		if grid is None or self.link is None:
			return

		# **Every cycle, including one that says the same as the last.**
		#
		# Comparing with the previous answer and staying quiet is the obvious
		# saving and it is wrong: a euclidean layer realises the same cells for
		# ever, so a panel that opened after the first cycle would wait for a
		# change that never comes and draw nothing at all. Found on the rig,
		# with four generators playing and a fresh socket seeing silence.
		#
		# Nothing keeps this, by design (#1965), so there is nowhere for a late
		# panel to read it from — which means saying it again is not repetition,
		# it is the only way anybody who was not listening can hear it. One small
		# frame a cycle, two seconds apart at this tempo.
		self.link.happened("realised", control=grid.name, cells=cells)

	def _target (self) -> typing.Any:
		"""The grid this stack builds, if it is one this panel can draw cells on.

		**A note grid counts too, and did not until #2218.**  This read
		``isinstance(grid, StepGrid)`` from when a stack could only be built onto
		the drum machine — so the moment every pattern took generators (#2147), a
		melodic one played what its generators wrote and showed nothing at all.
		Simon heard the notes and saw an empty grid.

		Nothing else here needed to know the difference: a realised cell is
		matched to a row by the name the generator was given, and a note grid's
		rows are note names for exactly the same reason a drum grid's are voice
		names — the composition said so (#1465).
		"""

		if self.link is None or self.builds is None:
			return None

		grid = self.link.controls.get(self.builds)

		return grid if isinstance(grid, (StepGrid, NoteGrid)) else None

	@staticmethod
	def _base (pattern: typing.Any) -> int | None:
		"""Today's number, drawn once from the pattern's own stream.

		None when this pattern has no stream to draw from, which is a
		composition older than the read-back or an object that is something else
		entirely — the same courtesy :meth:`_reads` pays, and with the same
		result: everything works exactly as it did before, and one improvement
		is quietly absent rather than an app being broken by this package.
		"""

		stream = getattr(pattern, "rng", None)

		return stream.getrandbits(32) if isinstance(stream, random.Random) else None

	def _seed_for (
		self,
		method: typing.Any,
		generator: str,
		layer_id: str,
		base: int | None,
	) -> int | None:
		"""The stream this layer draws from, or None to leave it on the pattern's.

		Derived the way Subsequence derives a named stream from a composition
		seed and a scratch builder derives a child from its parent — ``crc32`` of
		the two joined by a colon, because it is stable across processes where
		``hash()`` is not.  Deriving it a second way here would be a second
		answer to a question that already has one.

		The name is the layer's **id**, which is minted when somebody adds the
		layer and kept for the whole of its life.  So a layer's notes follow the
		layer: drag it, bypass what is above it, turn a neighbour's knob, and it
		lands where it landed.  Its position is not in the key, which is the
		whole point.

		**Measured on the clock's thread, because that is where it runs**: 4.5 us
		a layer, so a build of eight goes from 0.067 ms to 0.103 ms against a
		pulse budget of 20.  Of that, 3.6 us is Subsequence building a ``Random``
		from the seed and 0.14 us is the line below — so there is nothing here
		worth trading the shared derivation for, and the obvious saving
		(``crc32(name, base)``, which takes an initial value) buys 0.08 us of the
		4.5 and a second answer to a settled question.
		"""

		if base is None or not self._takes_seed(method, generator):
			return None

		return zlib.crc32(f"{base}:{layer_id}".encode())

	def _takes_seed (self, method: typing.Any, generator: str) -> bool:
		"""Whether this layer will accept a stream of its own, asked once each.

		Twenty of the forty-six offered here will not, and there is nothing to
		fix in that: fourteen of them draw no random numbers at all, so no
		neighbour can disturb them.  The remaining six cannot be called from a
		panel at all today — a separate defect of the same family as #2248, with
		its own evidence and its own fix.
		"""

		held = self._seeds.get(generator)

		if held is None:
			try:
				held = "seed" in inspect.signature(method).parameters

			# A builtin, or anything else without a readable signature. Not an
			# error: it means this layer keeps the pattern's stream, which is
			# where every layer was before this.
			except (TypeError, ValueError):
				held = False

			self._seeds[generator] = held

		return held

	def _arguments (self, generator: str, params: dict[str, typing.Any]) -> dict[str, typing.Any]:
		"""A layer's parameters as the generator's own call expects them.

		A range crosses the wire as a two-item list because JSON has no tuple,
		and a generator that offers ``int | (int, int)`` reads a list as
		neither.  So it goes back to a tuple on the way in.

		**A parameter may hold a source rather than a value** (#2374), and this is
		where one becomes the other.  It is resolved on every build because that
		is the point of it: a set of notes somebody is editing on the glass, or a
		signal that moves, has to be read at the moment the bar is made and not
		when the layer was added.

		Measured at 0.28 to 2.25 us a source against a 20 ms pulse, which is less
		than the 4.5 us a layer already spends deriving its own stream (#2233).
		"""

		offered = self._offered.get(generator, {})
		wanted: dict[str, typing.Any] = {}

		for name, value in params.items():
			parameter = offered.get(name)

			if isinstance(value, dict) and "from" in value:
				wanted[name] = self._sourced(value)
				continue

			if parameter is not None and parameter.kind == "range" and isinstance(value, list):
				wanted[name] = tuple(value)
				continue

			wanted[name] = value

		return wanted

	def _sourced (self, patch: dict[str, typing.Any]) -> typing.Any:
		"""What a patched parameter is worth this cycle.

		**A source that has gone is an empty answer, not a failure.**  A stack
		whose set of notes was removed should fall silent on that layer and keep
		playing everything else — the same reasoning as the skip in ``build``,
		where one bad layer must not cost the part its bar.
		"""

		named = patch.get("id")
		held = self.link.controls.get(str(named)) if self.link is not None else None

		if not isinstance(held, PitchSet):
			return []

		return self._folded(held.notes())

	def _folded (self, notes: collections.abc.Sequence[int]) -> list[str]:
		"""Somebody's notes, moved into the register this stack can actually play.

		**The same notes means the same shape, not the same numbers.**  One set
		patched to a bass and to a lead is a person saying *both of these play
		this*, and taking it literally silences whichever instrument does not
		reach — on this rig always one of them, because the Minitaur stops at C3
		and the Matriarch starts there.

		**The whole set moves together, by octaves.**  Folding each note to its own
		nearest octave was tried first and is wrong: C4 E4 G4 came out of a bass as
		C3 E2 G2, which is the right three pitch classes and not a chord anybody
		played.  A triad has a shape and the shape is most of what it is, so one
		octave shift is chosen for the set and every note takes it.

		A note still outside the range after the shift is folded by octaves until
		it is inside — a set wider than the instrument cannot keep its shape, and
		sounding is better than silence.  A pitch class this stack has no row for
		is dropped, which is honest: there is nowhere for it to sound.
		"""

		if not self.pitch_notes or not notes:
			return []

		reach = sorted(self.pitch_notes.values())
		lowest, highest = reach[0], reach[-1]

		# **The nearest register that holds the whole set, not the middle of the
		# instrument** (Simon, 2026-09-10).  Octaves only: anything else would
		# change the notes rather than move them.
		#
		# Centring on the instrument's range was the first rule and moves a set
		# further than it needs to go.  C3 E3 G3 C4 patched to a Minitaur came
		# out as **C1 E1 G1 C2** when C2 E2 G2 C3 fits perfectly — two octaves
		# where one would do, and two octaves away from the Matriarch playing the
		# same set unmoved, when a person patching one set to two instruments is
		# saying *both of these play this*.
		#
		# It was worse than a bad rule: at that exact set the arithmetic is
		# `round(-1.5)`, and Python rounds a half to **even**, so the tie broke
		# away from the octave a musician would have picked rather than towards
		# it.  A tie decided by the parity of the answer is not a decision.
		#
		# So: every whole-octave shift that fits, nearest to where the notes were
		# actually chosen.  A tie — a narrow set in a wide instrument, which can
		# sit an octave either way — goes to whichever leaves the set nearer the
		# middle of what the instrument reaches, because at that point there is
		# nothing else to prefer.
		middle = (min(notes) + max(notes)) / 2
		centre = (lowest + highest) / 2

		fits = [shift for shift in range(-120, 121, 12)
		        if all(lowest <= note + shift <= highest for note in notes)]

		if fits:
			shift = min(fits, key=lambda by: (abs(by), abs(middle + by - centre)))
		else:
			# **A set wider than the instrument cannot keep its shape**, so there
			# is no register that holds it and the old rule is the right one:
			# centre it, and fold the stragglers below.  Sounding beats silence.
			shift = round((centre - middle) / 12) * 12

		by_note = {note: named for named, note in self.pitch_notes.items()}
		folded: list[str] = []

		for note in notes:
			moved = note + shift

			while moved < lowest:
				moved += 12

			while moved > highest:
				moved -= 12

			named = by_note.get(moved)

			if named is None:
				# A row list that is not chromatic — a scale, or one voice. Take
				# the nearest row of the same pitch class, or nothing.
				matching = [(other, mine) for other, mine in self.pitch_notes.items()
				            if mine % 12 == moved % 12]

				if not matching:
					continue

				named = min(matching, key=lambda pair: abs(pair[1] - moved))[0]

			# A set may name two notes that fold onto one row. Kept once: a
			# generator handed the same pitch twice plays it twice, which is not
			# what somebody who chose two different notes meant.
			if named not in folded:
				folded.append(named)

		return folded

	def _complain (self, generator: str, why: str, layer: str | None = None) -> None:
		"""Say once in the log that a layer will not run, and every cycle on the glass.

		**Two audiences, and they want opposite things** (#2368).  A log wants
		saying once — a failing layer fails every cycle, and #2230 is what a
		flooded link does to a rig.  The glass wants saying *every* cycle, for
		the reason `_report_cells` gives: nothing keeps an event, so a panel that
		joined after the first one has nowhere to read it from, and staying quiet
		is indistinguishable from nothing being wrong.

		**Keyed by layer for the glass and by generator for the log.**  A person
		looks at a block, and two layers of one generator are two blocks that can
		disagree — one arpeggio patched at a pitch list and one at a chord.  The
		log's dedupe stays per generator, because that is what stops a rebuilt bar
		writing the same line twice a second.
		"""

		if layer is not None:
			self._failing[layer] = why

		if generator in self._complained:
			return

		self._complained.add(generator)

		LOG.warning(
			"the %r layer of %r will not run and is being skipped: %s. "
			"Further failures of this generator are not logged.",
			generator, self.name, why)

	def _say_what_failed (self) -> None:
		"""Tell the glass which layers did not run, so a block can say so.

		**Sent when there is something to say, and once more when there is not.**
		`_report_cells` sends every cycle unconditionally and is right to: a
		euclidean realises the same cells for ever, so a panel comparing with
		the last answer would wait for a change that never comes.  This is the
		other case — the answer is *nothing is wrong* almost always, which is
		what a panel draws with no information at all, so saying it every cycle
		would be a frame per stack per cycle carrying no news.  The clearing
		frame is what a panel needs and it is sent, once.
		"""

		if self.link is None:
			return

		if not self._failing and not self._reported_failing:
			return

		self._reported_failing = dict(self._failing)

		self.link.happened("stalled", control=self.name, layers=dict(self._failing))


class GridRack (Control):
	"""Grids a person makes from the glass, the way a stack makes layers (#2226).

	Simon asked whether a grid could be created from nothing, with a size chosen
	at the time.  **It can, and less was missing than it looked.**  There is no
	frame meaning *make me a control* and there does not need to be: an app
	re-declaring on the socket it already holds is how it says its controls have
	changed, and that has worked since the first day.  Only the asking was
	missing, and this is the asking.

	**The shape is a rack, deliberately parallel to a stack.**  Its value is an
	ordered list of specifications, each with an id that lives as long as the
	grid does; the panel adds, removes and reorders exactly as it does layers.
	Nothing new crosses the wire but a control kind.

	**What a grid *is* stays the composition's** (#1465).  This holds a list and
	knows how long it is; it is handed a ``make`` that turns one specification
	into a control, and that function is where the step duration, the note map,
	the channel and whether the thing is routable are decided — none of which
	this package is allowed to know.  A rack that built its own `StepGrid` would
	be a rack that had opinions about a studio.

	**Persistence is the real cost and it is worse than a lost pattern** (#2067).
	A restart already discards the notes on a grid; without a store it would
	discard the grid's *existence*, which is a person losing something they made
	rather than something they played.  So a rack takes a :class:`PageStore` —
	the same mechanism a page arrangement already uses, pointed at a file of its
	own — and what comes back is the grids they made, empty.  Honest, and better
	than nothing coming back at all.
	"""

	kind = "grids"

	def __init__ (
		self,
		composition: typing.Any,
		make: collections.abc.Callable[[dict[str, typing.Any]], Control],
		rows: collections.abc.Sequence[str],
		unmake: collections.abc.Callable[[str], None] | None = None,
		steps: tuple[int, int] = (1, 32),
		opening_steps: int = 16,
		store: "PageStore | None" = None,
		data_key: str = "rack",
		name: str = "rack",
		title: str | None = None,
		about: collections.abc.Sequence[tuple[str, typing.Any]] = (),
	) -> None:
		"""Offer a rack over a list the composition keeps."""

		self.composition = composition
		self.make = make

		self.unmake = unmake
		"""What to undo when a grid leaves, given the control's name.

		**Taking the control off the link is not the whole of removing a grid**,
		because making one may have done more than build it: on this rig it also
		registers a play function, so the grid can be routed.  Left behind, that
		is a source a stack still offers for a grid nobody can see any more — a
		control that looks connected and plays something invisible, which is the
		exact fault this project ranks worst.

		Optional, because what making does is the composition's business and it
		may do nothing that needs undoing.
		"""

		self.rows = list(rows)
		self.steps = steps
		self.opening_steps = opening_steps
		self.store = store
		self.data_key = data_key
		self.name = name
		self.title = title
		self.about = list(about)

		self.link: "AppLink | None" = None

		self._made: dict[str, str] = {}
		"""Which control each specification is currently materialised as, by id.

		Kept so a grid that leaves the list can be taken off the link again.  A
		second copy of the list would be a second copy that can disagree; this
		is a map from id to *name*, which is the one thing the list does not
		itself carry.
		"""

		if store is not None:
			kept = store.load().get(name)

			if kept:
				self.composition.data.setdefault(data_key, {})["grids"] = kept

	def declaration (self) -> dict[str, typing.Any]:
		"""What a panel needs in order to offer a new grid and draw the rack."""

		return {
			"type": self.kind,
			"rows": self.rows,
			"min_steps": self.steps[0],
			"max_steps": self.steps[1],
			"opening_steps": self.opening_steps,
			**self.said(),
		}

	def snapshot (self) -> typing.Any:
		"""Every grid this rack has been asked for, in the order it holds them."""

		return {"grids": self.grids()}

	def grids (self) -> list[dict[str, typing.Any]]:
		"""The specifications as they stand."""

		held = self.composition.data.get(self.data_key) or {}

		return list(held.get("grids") or [])

	def made (self) -> list[str]:
		"""What this rack has put on the link, by control name and in its order.

		Read by the link when it declares its pages: a grid is drawn wherever
		the rack that made it is drawn, so a page carrying the rack carries its
		grids too.
		"""

		return [self._made[one["id"]] for one in self.grids() if one["id"] in self._made]

	def attach (self, link: "AppLink") -> None:
		"""Take the link, and put back whatever was made before this started."""

		self.link = link
		self._materialise()

	def apply (self, rest: list[str], value: typing.Any) -> bool:
		"""Take a whole rack, checked entire before any of it is kept."""

		if rest != ["grids"]:
			raise Refused(f"a rack has no {'/'.join(rest)}")

		if not isinstance(value, list):
			raise Refused("a rack is a list of grids")

		wanted: list[dict[str, typing.Any]] = []
		seen: set[str] = set()

		for entry in value:
			if not isinstance(entry, dict):
				raise Refused("a grid is an object")

			one = str(entry.get("id") or "")

			if not one:
				raise Refused("a grid needs an id of its own")

			if one in seen:
				raise Refused(f"two grids both call themselves {one}")

			seen.add(one)
			wanted.append({
				"id": one,
				"rows": self._checked_rows(entry.get("rows")),
				"steps": self._checked_steps(entry.get("steps")),
				"title": str(entry["title"]) if entry.get("title") else None,
			})

		if self.grids() == wanted:
			return False

		self.composition.data.setdefault(self.data_key, {})["grids"] = wanted
		self._materialise()

		if self.store is not None:
			self.store.save(self.name, wanted)

		return True

	def applied (self, rest: list[str], value: typing.Any) -> typing.Any:
		"""What the rack now holds, which is the whole list."""

		return self.grids()

	def _checked_rows (self, rows: typing.Any) -> list[str]:
		"""The rows asked for, which must all be ones this rack was offered.

		A grid of no rows is refused rather than floored, because unlike a
		height there is no gesture that gets it back: an empty grid draws
		nothing to aim at.
		"""

		if not isinstance(rows, list) or not rows:
			raise Refused("a grid needs at least one row")

		named = [str(row) for row in rows]
		strange = [row for row in named if row not in self.rows]

		if strange:
			raise Refused(f"this rack offers no row called {strange[0]}")

		return named

	def _checked_steps (self, steps: typing.Any) -> int:
		"""How many steps, inside the bounds the composition set."""

		try:
			wanted = int(steps)

		except (TypeError, ValueError):
			raise Refused("a grid's steps must be a whole number") from None

		low, high = self.steps

		if not low <= wanted <= high:
			raise Refused(f"a grid may be {low} to {high} steps, not {wanted}")

		return wanted

	def _materialise (self) -> None:
		"""Put every specification on the link as a control, and take off the rest.

		**Called on the clock loop, and it touches no socket.**  The re-declaration
		that tells a panel any of this happened is scheduled on the link loop by
		the link itself, for the same reason every other frame is.
		"""

		if self.link is None:
			return

		wanted = {one["id"]: one for one in self.grids()}
		moved = False

		for gone in [one for one in self._made if one not in wanted]:
			name = self._made.pop(gone)

			self.link.controls.pop(name, None)

			if self.unmake is not None:
				self.unmake(name)

			moved = True

		for one, spec in wanted.items():
			# **A grid that stays is not rebuilt.**  It holds whatever has been
			# drawn on it, so remaking it because a neighbour was removed would
			# empty a pattern for a reason nobody could see.
			if one in self._made:
				continue

			made = self.make({**spec, "name": f"{self.name}-{one}"})

			made.attach(self.link)
			self.link.controls[made.name] = made
			self._made[one] = made.name
			moved = True

		# Only when the set of controls actually moved. Re-declaring is every
		# open panel re-reading everything this app offers, and a rack that
		# asked for it on a list it had already materialised would do that for
		# nothing — on the first attach, most often, when the list came back
		# from a store and the controls were about to be declared anyway.
		if moved:
			self.link.redeclare()


class Transport (Control):
	"""Whether the composition is playing, and at what tempo.

	Pause holds the clock where it is: the position is kept, sounding notes are
	released, and MIDI Stop goes out to anything following.  Resume continues
	from the same pulse rather than restarting.

	**The face follows the composition, never the button.**  A tap asks; the
	composition answers with its own ``pause`` or ``resume`` event once the
	clock has really stopped or started, and that is what moves the face.

	**A refusal has to be caught by reading back, not by waiting.**  Subsequence
	ignores ``pause()`` when the pulse is not its to hold — under an external
	clock, an Ableton Link session, or in render mode — and says so only in its
	log: no exception, and no event will ever arrive.  So the request is read
	back at once, and a refusal is passed to the panel rather than left as a
	button that waits forever.

	A Subsequence too old to pause does not have the field declared at all, and
	a panel draws what is declared, so nothing breaks.
	"""

	kind = "transport"

	def __init__ (
		self,
		composition: typing.Any,
		name: str = "transport",
		tempo_range: tuple[float, float] = (40.0, 240.0),
	) -> None:
		"""Offer tempo, and pause where the composition can hold its clock."""

		self.composition = composition
		self.name = name
		self.tempo_range = tempo_range

		self._link: "AppLink | None" = None
		self._last_bpm: float | None = None
		self._can_pause = (
			callable(getattr(composition, "pause", None))
			and callable(getattr(composition, "resume", None))
		)

		if not self._can_pause:
			LOG.info("this Subsequence cannot hold its clock; offering tempo alone")

	def attach (self, link: "AppLink") -> None:
		"""Follow the transport the composition reports, not the button tapped."""

		self._link = link

		if not self._can_pause:
			return

		self.composition.on_event("pause", lambda *_: self._report_paused(True))
		self.composition.on_event("resume", lambda *_: self._report_paused(False))

	def declaration (self) -> dict[str, typing.Any]:
		"""The fields this offers, and the tempo a panel may ask for."""

		fields = ["bpm"]

		if self._can_pause:
			fields.insert(0, "paused")

		return {"type": self.kind, "fields": fields, "tempo_range": list(self.tempo_range)}

	def snapshot (self) -> dict[str, typing.Any]:
		"""Whether it is held, and the tempo the sequencer actually holds."""

		state: dict[str, typing.Any] = {"bpm": self._bpm()}

		if self._can_pause:
			state["paused"] = self._paused()

		return state

	def apply (self, rest: list[str], value: typing.Any) -> bool:
		"""Hold the transport, let it go, or set the tempo.

		**Refused rather than ignored.**  `False` means "nothing changed", which
		is a true and useful answer for a pause that was already paused — and
		the wrong one for a field this transport does not have.  Returning it
		emitted nothing at all, so the panel's request sat pending for the full
		five seconds and then flashed as a failure with no reason given, while
		every other control raises.  This is the first review's finding about
		`StepGrid.apply`, fixed there and still true here.
		"""

		if len(rest) != 1:
			raise Refused(f"{'/'.join(rest)!r} does not name a transport field")

		if rest[0] == "paused":
			if not self._can_pause:
				raise Refused("this composition cannot hold its clock")

			return self._set_paused(bool(value))

		if rest[0] == "bpm":
			return self._set_bpm(value)

		raise Refused(f"a transport has no field named {rest[0]!r}")

	def poll (self) -> list[tuple[str, typing.Any]]:
		"""Report a tempo the composition changed itself, so the panel follows it."""

		bpm = self._bpm()

		if bpm is not None and bpm != self._last_bpm:
			self._last_bpm = bpm
			return [(f"{self.name}/bpm", bpm)]

		return []

	def _paused (self) -> bool:
		"""Whether the composition says it is holding."""

		return bool(getattr(self.composition, "is_paused", False))

	def _bpm (self) -> float | None:
		"""The tempo the sequencer is running at, or nothing before it starts."""

		bpm = getattr(self.composition.sequencer, "current_bpm", 0.0)

		return round(float(bpm), 2) if bpm else None

	def _set_paused (self, paused: bool) -> bool:
		"""Ask the composition to hold or continue, and check it took.

		Nothing is reported from here on success: the composition's own event
		moves the face a few milliseconds later, once the clock has actually
		stopped.  Returning False says only that this call has changed nothing
		a panel should be told about *yet*.
		"""

		if paused == self._paused():
			return False

		if paused:
			self.composition.pause()

		else:
			self.composition.resume()

		if self._paused() != paused:
			raise Refused("the transport follows an external clock or a Link session")

		return False

	def _report_paused (self, paused: bool) -> None:
		"""Tell every panel what the transport actually did."""

		if self._link is not None:
			self._link.report(f"{self.name}/paused", paused)

	def _set_bpm (self, value: typing.Any) -> bool:
		"""Set the tempo, refusing anything outside what was declared."""

		try:
			bpm = float(value)

		except (TypeError, ValueError):
			raise Refused(f"{value!r} is not a tempo")

		low, high = self.tempo_range

		if not low <= bpm <= high:
			raise Refused(f"{bpm:g} is outside the {low:g} to {high:g} this offers")

		self.composition.set_bpm(bpm)
		self._last_bpm = self._bpm()

		return True


def _readable_arrangement (parts: typing.Any) -> list[dict[str, typing.Any]] | None:
	"""An arrangement reduced to what a panel could draw, or None if it could not.

	This is the one thing a panel sends that is written to disk, and it comes
	back to every panel on the next declaration — so a shape nobody can draw
	would survive a restart and go on being handed out.  Everything else a panel
	sends is checked by the control that owns the path; this has no control to
	own it, so it is checked here.

	Coordinates are floored at zero and coerced to whole cells: a lattice
	position is a count, and a fractional one would put a block between two
	squares for ever.

	``rows`` is how tall somebody has pulled the block, and it is **optional in
	both directions** (#2227).  A part that carries none is a block nobody has
	resized, and it opens at the height its control declares — which is what
	every block did before a height could be arranged.  So a panel too old to
	send one loses nothing, and a block that has never been touched is not
	recorded as having a height, which would freeze it at whatever the app
	happened to declare on the day it was first drawn.

	**Floored at one, because zero is unrecoverable.**  A block of no rows would
	be a block nobody can take hold of to make taller again, and it would come
	back that way after a restart, which is the exact class of thing this
	function exists to stop.  There is no ceiling here: how many rows a control
	*has* is the panel's to know, and clamping to a number this end cannot see
	would be a guess written to disk.
	"""

	if not isinstance(parts, list):
		return None

	kept: list[dict[str, typing.Any]] = []

	for part in parts:
		if not isinstance(part, dict) or not isinstance(part.get("name"), str):
			return None

		try:
			x, y = int(part["x"]), int(part["y"])

		except (KeyError, TypeError, ValueError):
			return None

		placed: dict[str, typing.Any] = {"name": part["name"], "x": max(0, x), "y": max(0, y)}

		if part.get("rows") is not None:
			try:
				placed["rows"] = max(1, int(part["rows"]))

			except (TypeError, ValueError):
				return None

		kept.append(placed)

	return kept


class PageStore:
	"""Where a composition keeps what a panel arranged or made.

	**Two things use this and they are the same mechanism.**  A page's
	arrangement is where somebody put the blocks; a rack's list is what grids
	somebody made (#2226).  Both are a key against a list of objects, both are
	the panel's doing rather than the composition author's, and both have to
	come back after a restart or the person has lost what they did.  A second
	class would have been the same file format written twice.

	Pointed at a file of its own per use — the keys are a page id in one case
	and a control name in the other, and they share no namespace.

	A data file beside the composition, not inside it (#2075).  The composition
	is Python and there is no safe round trip from a dragged block back into
	source; a file next to it still travels with the piece in git, which is the
	point of the composition owning its pages, while keeping what changes at
	runtime apart from what a person edits by hand.

	The service never sees this path.  An arrangement arrives over the socket
	and is written here by the app that declared the page, which is what lets a
	composition on another machine work without this package learning anything
	about anybody's disk.
	"""

	def __init__ (self, path: pathlib.Path) -> None:
		"""Keep arrangements in this file, creating it when one is first made."""

		self.path = pathlib.Path(path)

	def load (self) -> dict[str, list[dict[str, typing.Any]]]:
		"""Every arrangement kept so far, by page.

		A missing file is an empty answer rather than an error: a piece nobody
		has arranged yet is the ordinary case.  A file that cannot be read is
		reported and then treated the same way, because losing the arrangement
		is better than refusing to start the music.
		"""

		if not self.path.exists():
			return {}

		try:
			held = json.loads(self.path.read_text(encoding="utf-8"))

		except (OSError, ValueError):
			LOG.warning("could not read %s; starting with no arrangement", self.path, exc_info=True)

			return {}

		return held if isinstance(held, dict) else {}

	def save (self, page_id: str, parts: list[dict[str, typing.Any]]) -> None:
		"""Keep one page's arrangement, leaving every other page as it was.

		Written to a neighbouring file and moved into place, so an interruption
		mid-write leaves the previous arrangement intact rather than half of a
		new one.
		"""

		held = self.load()
		held[page_id] = parts

		spare = self.path.with_suffix(self.path.suffix + ".part")

		spare.write_text(json.dumps(held, indent="\t") + "\n", encoding="utf-8")
		spare.replace(self.path)


class Page:
	"""One view over some of an app's controls, offered as part of a set.

	A composition owns its page set (#2075): several pages served at one URL,
	each naming the parts it carries, navigated from the panel's header. A part
	may appear on more than one page and needs no synchronising to do it —
	every widget draws the app's own state, so two views of one control cannot
	disagree.

	Offering no pages at all is a complete answer: a panel then shows every
	control declared, which is what it did before pages existed.
	"""

	def __init__ (self, page_id: str, parts: collections.abc.Sequence[str],
	              title: str | None = None) -> None:
		"""Name a view and say which declared controls appear on it.

		Where the parts sit is not said here.  They are placed on the panel's
		lattice, left to right and then down, until somebody moves them — and
		then it is the arrangement that is remembered, not a count of columns
		(#2078).
		"""

		self.page_id = page_id
		self.parts = list(parts)
		self.title = title

	def declaration (
		self,
		layout: list[dict[str, typing.Any]] | None = None,
		made: dict[str, list[str]] | None = None,
	) -> dict[str, typing.Any]:
		"""What a panel needs in order to offer this page and draw it.

		``layout`` is the arrangement somebody has already made, if there is
		one.  Absent, the panel places the parts itself, left to right and then
		down, until somebody moves them (#2078).

		``made`` says which parts were created by a control that is on this page
		— a rack's grids — and each is drawn after the thing that made it
		(#2226).  **A grid is drawn wherever the rack that made it is drawn**,
		which is the same rule a stack and a settings block already follow
		(#2211): a part nobody named on a page is drawn nowhere, with nothing
		saying so, and a grid a person just asked for vanishing is the worst
		version of that.
		"""

		parts: list[str] = []

		for part in self.parts:
			parts.append(part)
			parts.extend((made or {}).get(part, []))

		declared: dict[str, typing.Any] = {
			"id": self.page_id, "title": self.title or self.page_id, "parts": parts}

		if layout:
			declared["layout"] = layout

		return declared


class AppLink:
	"""One app's socket to the service, and the controls it offers over it."""

	def __init__ (
		self,
		composition: typing.Any,
		controls: collections.abc.Sequence[Control],
		app_name: str = "subsequence",
		url: str = DEFAULT_URL,
		pages: collections.abc.Sequence[Page] | None = None,
		page_store: PageStore | None = None,
	) -> None:
		"""Describe what to offer, without connecting anything yet."""

		self.composition = composition
		self.controls = {control.name: control for control in controls}
		self.app_name = app_name
		self.url = url
		self.pages = list(pages or [])
		self.page_store = page_store

		self.version = 0

		self._clock_loop: asyncio.AbstractEventLoop | None = None
		self._link_loop: asyncio.AbstractEventLoop | None = None
		self._socket: typing.Any = None

		self._outbound: collections.OrderedDict[
			typing.Any, superconductor.protocol.Frame] = collections.OrderedDict()
		"""Frames waiting for the socket, newest last (#2242).  Ordered because
		the oldest is what goes when it is full, and keyed because an event about
		a control supersedes a waiting one for the same control."""

		self._dropped = 0
		"""How many have gone that way since the link last caught up."""

		self._minted = 0
		"""Keys for frames that supersede nothing, so each queues in its turn."""
		self._thread: threading.Thread | None = None
		self._stopping = threading.Event()
		self._last_beat_at: float | None = None

	def start (self) -> None:
		"""Begin listening to the clock and dialling the service.

		Safe to call before the composition plays: the link simply waits, and
		the panel shows the app as absent until it answers.
		"""

		self.composition.on_event("beat", self._on_beat)

		# **A snapshot, because attaching a control can register more of them.**
		# A rack puts back the grids somebody made before this started (#2226),
		# and each one becomes a control on this link — so the dict grows while
		# it is being walked, and Python raises rather than quietly skipping
		# one. It cannot fire until a grid has been made *and* the app started
		# again, which is why it outlived the rack landing and appeared on the
		# first restart afterwards. The rack attaches every grid it
		# materialises, so a snapshot loses nothing.
		for control in list(self.controls.values()):
			control.attach(self)

		self._thread = threading.Thread(target=self._run_link, name="superconductor-link", daemon=True)
		self._thread.start()

		LOG.info("Superconductor link started; dialling %s", self.url)

	def stop (self) -> None:
		"""Stop dialling and let the link thread finish."""

		self._stopping.set()

		if self._link_loop is not None:
			self._link_loop.call_soon_threadsafe(self._link_loop.stop)

	# ------------------------------------------------------------------
	# On the composition's clock loop
	# ------------------------------------------------------------------

	def _on_beat (self, beat: int) -> None:
		"""Note the beat, pass it on, and report anything the composition changed.

		This runs on the clock loop, which is the point: the first call is how
		the link learns which loop to hand taps to, without reaching for any
		private name.
		"""

		if self._clock_loop is None:
			self._clock_loop = asyncio.get_running_loop()
			LOG.debug("clock loop captured from the first beat")

		now = time.monotonic()
		interval = None if self._last_beat_at is None else now - self._last_beat_at
		self._last_beat_at = now

		# **Any grid, not the first step grid.** A composition offering pitched
		# patterns and no step grid sent `steps=None, beats=None`, and the
		# transport counter drew nothing at all with nothing to say why.
		grid = next(
			(c for c in self.controls.values() if isinstance(c, (StepGrid, NoteGrid))), None)

		self._emit(superconductor.protocol.event(
			self.app_name, "beat", beat=beat, ts=now, interval=interval,
			steps=grid.steps if grid else None, beats=grid.beats if grid else None))

		for control in self.controls.values():
			for path, value in control.poll():
				self.version += 1
				self._emit(superconductor.protocol.changed(
					self.app_name, path, value, self.version, by="app"))

			# Asked here because a beat is how we know the clock is running, and
			# paid on the link thread because this is the clock.
			owed = control.owed()

			if owed:
				self._settle(control, owed)

	def _apply (self, path: str, value: typing.Any, client: str, seq: int) -> None:
		"""Hand one request to the control that owns it, on the clock loop."""

		name, _, rest = path.partition("/")
		control = self.controls.get(name)

		if control is None or not rest:
			LOG.warning("panel asked for %r, which names no control here", path)
			return

		try:
			changed = control.apply(rest.split("/"), value)

		except Refused as refusal:
			LOG.info("refused %r: %s", path, refusal)
			self._emit(superconductor.protocol.nack(self.app_name, path, client, seq, str(refusal)))
			return

		except Exception:
			LOG.warning("applying %r failed", path, exc_info=True)
			self._emit(superconductor.protocol.nack(self.app_name, path, client, seq, "the app could not do that"))
			return

		if not changed:
			return

		self.version += 1

		self._emit(superconductor.protocol.changed(
			self.app_name, path, control.applied(rest.split("/"), value), self.version,
			by="panel", client=client, seq=seq))

	def redeclare (self) -> None:
		"""Say what this app offers again, because it has changed (#2226).

		**An app re-declaring on the socket it already holds is how it says its
		controls changed**, and that has worked since the first day — it is the
		same path #2133 had to learn to tell apart from a second app arriving.
		A rack that made a grid therefore needs no frame of its own: it puts the
		control on the link and asks for this.

		Scheduled on the link loop rather than run here, exactly as `_emit` is
		and for the same reason: this is called on the clock loop, and building
		every control's declaration and snapshot is not work a pulse should wait
		for.
		"""

		loop = self._link_loop

		if loop is None or self._socket is None:
			return

		asyncio.run_coroutine_threadsafe(self._declare(), loop)

	def happened (self, name: str, **fields: typing.Any) -> None:
		"""Announce something that is true for one cycle and stored nowhere.

		An event rather than a change, and the distinction is the whole of
		#1965: a change is intent and is kept, an event is what the music did
		this time round.  Nothing applies one to any control's state.
		"""

		self._emit(superconductor.protocol.event(self.app_name, name, **fields))

	def report (self, path: str, value: typing.Any) -> None:
		"""Announce something the app did of its own accord, on the clock loop.

		A control polled once a beat cannot report a pause, because a paused
		composition has no beats.
		"""

		self.version += 1

		self._emit(superconductor.protocol.changed(
			self.app_name, path, value, self.version, by="app"))

	def _settle (self, control: Control, owed: list[tuple[str, typing.Any]]) -> None:
		"""Tell an instrument what it is owed, on the link thread.

		The same shape as `_emit` and for the same reason: the clock loop hands
		the work over and returns, so a slow instrument cannot delay a pulse.
		"""

		loop = self._link_loop

		# No link thread yet happens only before the socket is first dialled.
		# The debt is left unsettled, so the next beat offers it again — paying
		# it inline here is the one thing this exists to avoid.
		if loop is None:
			return

		asyncio.run_coroutine_threadsafe(self._tell(control, owed), loop)
		control.settled()

	async def _tell (self, control: Control, owed: list[tuple[str, typing.Any]]) -> None:
		"""Hand the work to the control, on the link thread."""

		control.settle(owed)

	def _emit (self, frame: superconductor.protocol.Frame) -> None:
		"""Hand a frame to the link thread, in the order it was produced.

		Called on the clock loop and never blocking there: the send itself
		happens on the link thread, so a slow socket cannot delay a pulse.

		**Queued rather than scheduled one coroutine per frame** (#2242).  A
		looping route once put 482 frames on this path in a single cycle and the
		link loop drowned in work handed to it faster than it could drain — which
		is what left the process spinning and deaf to `SIGTERM`, and was read at
		the time as a busy builder.  A cable made that particular burst and it is
		fixed (#2230); anything else that produces one arrives here.
		"""

		loop = self._link_loop

		if loop is None or self._socket is None:
			return

		self._queue(frame)

		asyncio.run_coroutine_threadsafe(self._drain(), loop)

	def _queue (self, frame: superconductor.protocol.Frame) -> None:
		"""Put one frame in line, superseding what it makes untrue.

		Separate from `_emit` so it can be tested without a link thread, and
		because it is the only part with a decision in it.

		**An event about a control supersedes a waiting one for the same
		control.**  An event is what the music did this cycle and nothing keeps
		it (#1965) — two of them waiting together is not two facts, it is one
		fact and a stale copy, and drawing the stale one is worse than drawing
		neither.  It keeps the older one's *place* in the queue rather than
		jumping ahead, so a superseded frame occupies the slot it would have had.

		**Everything else is somebody's fact and may not be merged.**  A change
		is intent and is kept; an `ack` and a `nack` are what a hand on the glass
		is waiting for.  Those get a fresh key each and queue in order.

		Over the cap the *oldest* goes, because these are frames a socket has not
		taken yet and the newest is the one still true.
		"""

		waiting = self._outbound
		key = self._supersedes(frame)
		standing = key in waiting

		waiting[key] = frame

		if standing or len(waiting) <= OUTBOUND_CAP:
			return

		waiting.popitem(last=False)
		self._dropped += 1

		# Once an episode, not once a frame: the whole failure being described
		# here is a path that says something per frame under a burst.
		if self._dropped == 1:
			LOG.warning(
				"the link is behind: frames are being dropped after %d waiting. "
				"Nothing further is logged until it catches up.", OUTBOUND_CAP)

	def _supersedes (self, frame: superconductor.protocol.Frame) -> typing.Any:
		"""What a frame replaces while it waits, or a key of its own if nothing."""

		if frame.get("t") == "event":
			return ("event", frame.get("name"), frame.get("control"))

		self._minted += 1

		return self._minted

	async def _drain (self) -> None:
		"""Send whatever is waiting, on the link thread.

		Every `_emit` schedules one of these and most find the queue already
		empty, which is the point: the work is bounded by the queue rather than
		by how many times it was asked for.
		"""

		while self._outbound:
			_, frame = self._outbound.popitem(last=False)

			await self._send(frame)

		if self._dropped:
			LOG.info("the link caught up, having dropped %d frame(s)", self._dropped)
			self._dropped = 0

	# ------------------------------------------------------------------
	# On the link thread
	# ------------------------------------------------------------------

	def _run_link (self) -> None:
		"""Own an event loop on this thread and keep the service dialled."""

		self._link_loop = asyncio.new_event_loop()
		asyncio.set_event_loop(self._link_loop)

		try:
			self._link_loop.run_until_complete(self._dial_forever())

		finally:
			self._link_loop.close()

	async def _dial_forever (self) -> None:
		"""Connect, serve, and reconnect for as long as the composition runs."""

		delay = RECONNECT_FLOOR

		while not self._stopping.is_set():
			try:
				async with websockets.asyncio.client.connect(self.url, ping_interval=5, ping_timeout=5) as socket:
					self._socket = socket
					delay = RECONNECT_FLOOR

					LOG.info("connected to Superconductor at %s", self.url)

					await self._declare()
					await self._serve(socket)

			except (OSError, websockets.exceptions.WebSocketException) as error:
				LOG.debug("Superconductor not reachable (%s); retrying in %.2fs", error, delay)

			finally:
				self._socket = None

			await asyncio.sleep(delay)
			delay = min(delay * 2, RECONNECT_CEILING)

	async def _declare (self) -> None:
		"""Say what this app offers and what it currently holds."""

		kept = self.page_store.load() if self.page_store is not None else {}

		# What each rack has made, so a page carrying the rack carries its grids.
		made = {control.name: control.made()
		        for control in self.controls.values() if isinstance(control, GridRack)}

		for control in self.controls.values():
			control.declared()

		await self._send(superconductor.protocol.declare(
			self.app_name,
			{name: control.declaration() for name, control in self.controls.items()},
			{name: control.snapshot() for name, control in self.controls.items()},
			self.version,
			[page.declaration(kept.get(page.page_id), made) for page in self.pages],
			LOADED_BUILD,
		))

	async def _serve (self, socket: typing.Any) -> None:
		"""Carry what the service sends until the socket closes."""

		async for raw in socket:
			try:
				frame = superconductor.protocol.decode(raw)

			except superconductor.protocol.ProtocolError:
				LOG.warning("service sent a frame that could not be read", exc_info=True)
				continue

			if frame["t"] == "set":
				self._cross(frame)

			elif frame["t"] == "layout":
				await self._keep_layout(frame)

	async def _keep_layout (self, frame: superconductor.protocol.Frame) -> None:
		"""Write a page's layout down, and tell every panel it landed.

		Handled on the link thread and never crossed onto the clock loop: this
		writes a file, and a file write has no business on the path that
		generates MIDI timing.  It touches nothing the composition is playing.

		A composition that keeps no page file refuses rather than pretending.
		The panel then says so and the person knows their arrangement is only in
		front of them, which is better than finding out at the next reload.
		"""

		page_id = str(frame.get("page", ""))
		parts = _readable_arrangement(frame.get("parts"))

		if parts is None:
			await self._send(superconductor.protocol.nack(
				self.app_name, page_id, str(frame.get("client", "")),
				int(frame.get("seq", 0)), "that arrangement could not be read"))
			return

		if self.page_store is None:
			await self._send(superconductor.protocol.nack(
				self.app_name, page_id, str(frame.get("client", "")),
				int(frame.get("seq", 0)), "this composition keeps no page file to save into"))
			return

		try:
			self.page_store.save(page_id, parts)

		except OSError as error:
			LOG.warning("could not save the arrangement of %r", page_id, exc_info=True)

			await self._send(superconductor.protocol.nack(
				self.app_name, page_id, str(frame.get("client", "")),
				int(frame.get("seq", 0)), f"the arrangement could not be written: {error.strerror}"))
			return

		LOG.info("kept the arrangement of page %r", page_id)

		# Declaring again is how every panel learns: a page set is shared, so
		# an arrangement made on one panel belongs on the others too.
		await self._declare()

	def _cross (self, frame: superconductor.protocol.Frame) -> None:
		"""Hand one request to the clock loop, the only place it may land.

		This is the crossing Subroutine #2046 chose: one per message, no
		batching, measured at about a millisecond at p99 (#1926, #2043).
		"""

		loop = self._clock_loop

		if loop is None:
			LOG.warning("a request arrived before the first beat; nothing to apply it to yet")
			return

		loop.call_soon_threadsafe(
			self._apply,
			str(frame.get("path", "")),
			frame.get("v"),
			str(frame.get("client", "")),
			int(frame.get("seq", -1)),
		)

	async def _send (self, frame: superconductor.protocol.Frame) -> None:
		"""Write one frame, forgiving a socket that has closed underneath it."""

		socket = self._socket

		if socket is None:
			return

		try:
			await socket.send(superconductor.protocol.encode(frame))

		except websockets.exceptions.WebSocketException:
			LOG.debug("frame dropped: the service went away mid-send")

		# **Anything else, and this was not always here** (#2242). A socket that
		# breaks under load raises things this library does not wrap — the
		# incident log holds 2,819 `socket.send() raised exception.` beside a
		# `coroutine 'AppLink._send' was never awaited`, which is what an escaped
		# exception in a future nobody reads looks like from the outside.
		# Dropping a frame is a redrawn dot; an unread future is a leak.
		except Exception:
			LOG.warning("frame dropped: the socket would not take it", exc_info=True)
