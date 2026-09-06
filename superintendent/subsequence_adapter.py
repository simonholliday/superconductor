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
import collections.abc
import json
import logging
import pathlib
import threading
import time
import typing

import websockets.asyncio.client
import websockets.exceptions

import superintendent.protocol


LOG = logging.getLogger(__name__)

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

	title: str | None = None
	"""What to call this on the glass, if not the name it is addressed by.

	The app names its own parts and the panel repeats them (#2071).  Nothing in
	Superintendent knows that a row called ``kick`` is a drum or that a grid is
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
	"""

	def __init__ (
		self,
		composition: typing.Any,
		rows: collections.abc.Sequence[str],
		steps: int = 16,
		beats: int = 4,
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
			"type": "step_grid", "rows": self.rows, "steps": self.steps, "beats": self.beats}

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

		return self.snapshot() if rest == ["rows"] else value

	def snapshot (self) -> dict[str, list[int]]:
		"""The grid as it stands, one row at a time, empty rows included.

		Read from the link thread rather than the clock loop, deliberately: the
		only hazard is a row being sorted at this instant, and copying a list is
		a single step under the interpreter's lock.  Crossing onto the loop for
		a read would put socket work on the path that generates MIDI timing.
		"""

		grid = self.composition.data.get(self.data_key) or {}
		held: dict[str, typing.Any] = {row: sorted(grid.get(row, [])) for row in self.rows}

		# Beside the rows rather than under a key of its own, because a control's
		# state is one object and a panel reads it as one. `rows` is already
		# reserved here for the whole-grid write, so a row cannot be called that
		# either; this is the second word spent and it buys a mute.
		held["enabled"] = self.enabled

		return held

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

	``mono`` is the composition's statement that the instrument sounds one note
	at a time.  It is enforced here rather than left to the instrument, because
	an instrument choosing between simultaneous notes by its own key-priority
	setting would leave the glass showing notes that never sound.  Enforced by
	**extent** and not by starting position: a note beginning part-way through
	another is exactly the case the instrument would have to arbitrate (#2114).

	``divisions`` is how many addressable positions make up one drawn cell, and
	the composition is the one that says.  One — the default — means a position
	is a step and this is the grid it always was.  More than one means the
	composition keeps a finer dict and reads it with ``PatternBuilder.note``
	rather than ``hit_steps``, because placing a note between two steps is
	precisely what ``hit_steps`` cannot express.  **The unit is the
	composition's**, since ``composition.data`` is its dict and its own builder
	reads it (#1465).
	"""

	def __init__ (
		self,
		composition: typing.Any,
		rows: collections.abc.Sequence[str],
		steps: int = 16,
		beats: int = 4,
		data_key: str = "notes",
		name: str = "notes",
		title: str | None = None,
		about: collections.abc.Sequence[tuple[str, typing.Any]] = (),
		pattern: str | None = None,
		mono: bool = False,
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
		self.mono = mono
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
			"type": "note_grid", "rows": self.rows, "steps": self.steps, "beats": self.beats,
			"mono": self.mono, "divisions": self.divisions,
			"default_length": self.default_length, "default_velocity": self.default_velocity,
			"max_length": self.positions, "velocity_range": [1, 127]}

		if self.visible_rows is not None:
			declared["visible_rows"] = self.visible_rows

		declared.update(self.said())

		return declared

	def snapshot (self) -> dict[str, typing.Any]:
		"""Every note as it stands, copied so nothing shares a dict with the loop.

		The mute travels with the rows, as a step grid's does: a panel arriving
		after one was silenced has no other way to learn it, and would draw the
		switch live over a pattern that is not.
		"""

		grid = self.composition.data.get(self.data_key) or {}

		held: dict[str, typing.Any] = {
			row: {step: dict(note) for step, note in (grid.get(row) or {}).items()}
			for row in self.rows if grid.get(row)}

		held["enabled"] = self.enabled

		return held

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

			self._keep_mono(grid, row, int(step), self.default_length)

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
		# a monophonic part has to be re-checked here and not only where a note
		# is placed. Velocity changes nothing about when a note sounds, so this
		# asks about the extent it now has either way and finds nothing to do.
		if field == "length":
			self._keep_mono(grid, row, int(step), wanted)

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
			if not 1 <= wanted <= 127:
				raise Refused("velocity is between 1 and 127")

		else:
			raise Refused(f"a note has no {field}")

		return wanted

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

		return self.snapshot() if rest == ["rows"] else value

	def _keep_mono (self, grid: dict[str, typing.Any], keep: str, at: int, span: int) -> None:
		"""Take away any note this one would sound over, and say so.

		**By extent, not by starting position** (#2114). A note beginning
		part-way through another is exactly the case a monophonic instrument
		would have to arbitrate by its own key priority, which is what ``mono``
		exists to keep off the glass — and once a note can be dragged around,
		overlapping without sharing a start is the ordinary case rather than a
		corner of one.

		The panel asked for one thing and two changed, so the second is reported
		in its own right — otherwise a cell would go dark on the glass with
		nothing on the wire to explain it.
		"""

		if not self.mono:
			return

		for row in self.rows:
			if row == keep:
				continue

			notes = grid.get(row) or {}

			for step in [held for held in notes if _overlaps(at, span, int(held), notes[held])]:
				del notes[step]

				if self.link is not None:
					self.link.report(f"{self.name}/{row}/{step}", False)

			# Dropped once its last note goes, as removing one by hand already
			# does. Nothing on the wire differs either way — the snapshot filters
			# empty rows — but this is the second copy of that rule, and a test
			# found them disagreeing the moment there was a second way in.
			if not notes:
				grid.pop(row, None)


class Parameter:
	"""One setting of an instrument, in one of the three shapes a panel can draw.

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
	) -> None:
		"""Describe one setting: what it is called, what shape it is, what it may be."""

		self.name = name
		self.kind = kind
		self.label = label
		self.minimum = minimum
		self.maximum = maximum
		self.step = step
		self.options = list(options or [])
		self.default = default

	def declaration (self) -> dict[str, typing.Any]:
		"""What a panel needs in order to draw this and to know what it may ask."""

		declared: dict[str, typing.Any] = {
			"name": self.name, "kind": self.kind, "label": self.label or self.name}

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

		elif self.kind == "choice":
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


def checked_value (parameter: Parameter, value: typing.Any) -> typing.Any:
	"""Refuse anything a parameter could not hold, saying which and why.

	Shared between an instrument's settings and a generator's, because they are
	the same four shapes and two copies of this would drift.  A refusal here is
	a message a person reads on the glass, so each one names the parameter.
	"""

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

	def __init__ (
		self,
		composition: typing.Any,
		parameters: collections.abc.Sequence[Parameter],
		data_key: str = "settings",
		name: str = "settings",
		title: str | None = None,
		about: collections.abc.Sequence[tuple[str, typing.Any]] = (),
		on_change: collections.abc.Callable[[str, typing.Any], None] | None = None,
	) -> None:
		"""Describe the settings to offer, and how the composition hears about one."""

		self.composition = composition
		self.parameters = {parameter.name: parameter for parameter in parameters}
		self.data_key = data_key
		self.name = name
		self.title = title
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
			held.setdefault(parameter.name, parameter.opening())

	def declaration (self) -> dict[str, typing.Any]:
		"""Every setting, in the order the composition offered them."""

		declared: dict[str, typing.Any] = {
			"type": "params",
			"fields": [parameter.declaration() for parameter in self.parameters.values()]}

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

		if not self._to_assert or self.on_change is None:
			return []

		self._to_assert = False

		for name, value in (self.composition.data.get(self.data_key) or {}).items():
			if name in self.parameters:
				self.on_change(name, value)

		LOG.info("asserted %d setting(s) of %r to the instrument", len(self.parameters), self.name)

		return []

	def apply (self, rest: list[str], value: typing.Any) -> bool:
		"""Write one setting, and tell the composition it moved."""

		if len(rest) != 1:
			raise Refused("that does not name a setting")

		parameter = self.parameters.get(rest[0])

		if parameter is None:
			raise Refused(f"this instrument has no setting called {rest[0]}")

		wanted = self._checked(parameter, value)
		held = self.composition.data.setdefault(self.data_key, {})

		if held.get(parameter.name) == wanted:
			return False

		held[parameter.name] = wanted

		if self.on_change is not None:
			self.on_change(parameter.name, wanted)

		return True

	def _checked (self, parameter: Parameter, value: typing.Any) -> typing.Any:
		"""Refuse anything this setting could not hold, with a reason."""

		return checked_value(parameter, value)


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
	)


def offerable (
	catalogue: collections.abc.Sequence[dict[str, typing.Any]],
	pitches: collections.abc.Sequence[str],
	bounds: dict[str, tuple[float, float]] | None = None,
) -> list[dict[str, typing.Any]]:
	"""An app's catalogue, with the pitches this composition actually has.

	This is the join the whole arrangement rests on.  The app describing itself
	says *this parameter is a pitch* and can say no more, because which pitches
	exist is a fact about a studio; the composition says they are these ten
	drum voices.  Neither knows the other's half, and this package knows
	neither — it is handed both (#1465).

	A parameter this panel cannot draw is left out and its generator marked
	partial, which is the same courtesy the app pays upstream: better to say a
	generator is not fully drivable than to offer a control that cannot be
	completed.  A pool of pitches is the common case — one day a multiple
	choice, today not drawn.

	``bounds`` is the same division applied to numbers.  An app cannot know
	what a sensible range for ``pulses`` is, because that depends on how many
	steps the pattern has and the pattern is the composition's; where the
	composition does know, it says so here and the panel can draw a slider
	instead of a stepper.
	"""

	narrowed = bounds or {}
	offered: list[dict[str, typing.Any]] = []

	for generator in catalogue:
		fields: list[dict[str, typing.Any]] = []
		dropped = False

		for field in generator.get("parameters", []):
			if field.get("kind") in ("number", "range") and field.get("name") in narrowed:
				low, high = narrowed[str(field.get("name"))]
				fields.append({**field, "min": low, "max": high})
				continue

			if field.get("kind") != "pitch":
				fields.append(field)
				continue

			if field.get("multiple") or not pitches:
				dropped = True
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
				"kind": "choice",
				"role": "pitch",
				"options": [{"value": pitch, "label": pitch} for pitch in pitches],
			})

		offered.append({
			**generator,
			"parameters": fields,
			"partial": bool(generator.get("partial")) or dropped,
		})

	return offered


def _required (parameters: collections.abc.Sequence[dict[str, typing.Any]]) -> set[str]:
	"""Which of a generator's parameters have to be given a value.

	Inferred from their order, because the catalogue does not say.  A parameter
	with no default at all and one whose default is ``None`` both arrive with no
	``default`` key, and the two want opposite treatment: the first has to be
	filled in or the call fails, the second has to be left out or the generator
	is handed a zero where it expected to be told nothing.

	Python requires parameters without defaults to come first, so everything
	ahead of the first defaulted one is required.  That holds for every
	generator in the catalogue as it stands.  It would not hold for a
	keyword-only parameter declared after a defaulted one, which is legal and
	which nothing here uses — so this is an assumption with a shelf life, and an
	explicit flag from the app would retire it.
	"""

	must: set[str] = set()

	for field in parameters:
		if "default" in field:
			break

		must.add(str(field.get("name")))

	return must


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

	def __init__ (
		self,
		composition: typing.Any,
		catalogue: collections.abc.Sequence[dict[str, typing.Any]],
		pitches: collections.abc.Sequence[str] = (),
		bounds: dict[str, tuple[float, float]] | None = None,
		builds: str | None = None,
		sources: dict[str, collections.abc.Callable[[typing.Any], None]] | None = None,
		pulses_per_beat: int | None = None,
		data_key: str = "recipe",
		name: str = "recipe",
		title: str | None = None,
		about: collections.abc.Sequence[tuple[str, typing.Any]] = (),
	) -> None:
		"""Offer a stack over a list the composition keeps."""

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

		self.sources = dict(sources or {})
		"""Which other grids this stack may take notes from, and how to play one.

		A name the composition also declared as a control, against a function
		that writes that grid onto a pattern being built.  **The function is the
		composition's because turning a grid into notes is** — a velocity, a
		note map, a length, whether a row is a drum voice or a pitch.  This
		routes; it does not know what it is routing (#1465).

		Empty by default, which is a stack that offers generators only.  That is
		what every stack was before #2108 and what a composition with nothing
		worth sharing still wants.
		"""

		self.composition = composition
		self.pitches = list(pitches)
		self.catalogue = offerable(catalogue, self.pitches, bounds)
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

		self._must_have = {
			generator.get("name"): _required(generator.get("parameters", []))
			for generator in self.catalogue
		}

		self.link: "AppLink | None" = None
		"""How a stack says what it realised, and where it finds the grid it feeds."""

		self._complained: set[str] = set()
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

		declared: dict[str, typing.Any] = {"type": "recipe", "generators": self.catalogue}

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
			if one["kind"] == "pattern":
				one["source"] = layer.get("source")

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

	def _keep_stack (self, value: typing.Any) -> bool:
		"""Take a whole stack, checked entire before any of it is kept."""

		if not isinstance(value, list):
			raise Refused("a stack is a list of layers")

		wanted: list[dict[str, typing.Any]] = []
		seen: set[str] = set()
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

			if kind not in ("generator", "pattern"):
				raise Refused(f"a layer cannot be a {kind}")

			if kind == "pattern":
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

			generator = entry.get("generator")
			offered = self._offered.get(generator)

			if offered is None:
				raise Refused(f"there is no generator called {generator}")

			held = entry.get("params")
			kept: dict[str, typing.Any] = {}

			for parameter, setting in (held if isinstance(held, dict) else {}).items():
				if parameter not in offered:
					raise Refused(f"{generator} has no parameter called {parameter}")

				kept[parameter] = checked_value(offered[parameter], setting)

			wanted.append({
				"id": name,
				"kind": kind,
				"generator": generator,
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
			named = str(layer.get("source") if layer["kind"] == "pattern" else layer["generator"])
			counted[named] = max(counted.get(named, 0), layer["index"])

		return counted

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

		offered = self._offered.get(layer.get("generator"), {})

		if parameter not in offered:
			raise Refused(f"{layer.get('generator')} has no parameter called {parameter}")

		wanted = checked_value(offered[parameter], value)
		params = layer.setdefault("params", {})

		if params.get(parameter) == wanted:
			return False

		params[parameter] = wanted

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

		before = self._reads(pattern) if self.pulses_per_beat else None

		for layer in self.layers():
			if layer["bypassed"]:
				continue

			if layer["kind"] == "pattern":
				source = str(layer.get("source"))
				play = self.sources.get(source)

				if play is None:
					self._complain(source, "this composition offers no such pattern")
					continue

				# A grid switched off contributes nothing, wherever it is routed.
				# The route is still there and still drawn; it just carries
				# nothing, which is the difference between a mute and a delete.
				held = self.link.controls.get(source) if self.link is not None else None

				if held is not None and not held.enabled:
					continue

				try:
					play(pattern)

				except Exception as error:
					self._complain(source, str(error))

				continue

			generator = str(layer["generator"])
			method = getattr(pattern, generator, None)

			if method is None:
				self._complain(generator, "this Subsequence has no such generator")
				continue

			try:
				method(**self._arguments(generator, layer["params"]))

			except Exception as error:
				self._complain(generator, str(error))

		after = self._reads(pattern) if before is not None else None

		if before is not None and after is not None:
			self._say_what_landed(before, after)

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

	def _say_what_landed (self, before: list[typing.Any], after: list[typing.Any]) -> None:
		"""Report the cells this stack realised, as rows and step numbers.

		Ephemeral and stored nowhere: an event rather than a change, because
		these notes are not intent and must never be applied as if they were
		(#1965).  A person's taps remain the only thing anything keeps.
		"""

		grid = self._target()

		if grid is None or self.link is None or self.pulses_per_beat is None:
			return

		per_step = self.pulses_per_beat * grid.beats / grid.steps

		if per_step <= 0:
			return

		known = set(grid.rows)
		cells: dict[str, dict[str, int]] = {}

		for note in set(after) - set(before):
			row = getattr(note, "origin", None)

			# A note with no named voice cannot be matched to a row, and one the
			# primary device will not sound must not be drawn as though it will
			# — a hit on the glass that makes no sound is a lie.
			if not isinstance(row, str) or row not in known:
				continue

			if getattr(note, "primary_unmapped", False):
				continue

			step = int(getattr(note, "position", 0) // per_step)

			if not 0 <= step < grid.steps:
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
			held[str(step)] = max(held.get(str(step), 0), loud)

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
		"""The grid this stack builds, if it is one this panel can draw cells on."""

		if self.link is None or self.builds is None:
			return None

		grid = self.link.controls.get(self.builds)

		return grid if isinstance(grid, StepGrid) else None

	def _arguments (self, generator: str, params: dict[str, typing.Any]) -> dict[str, typing.Any]:
		"""A layer's parameters as the generator's own call expects them.

		A range crosses the wire as a two-item list because JSON has no tuple,
		and a generator that offers ``int | (int, int)`` reads a list as
		neither.  So it goes back to a tuple on the way in.
		"""

		offered = self._offered.get(generator, {})

		return {
			name: tuple(value) if offered.get(name) is not None
			and offered[name].kind == "range" and isinstance(value, list)
			else value
			for name, value in params.items()
		}

	def _complain (self, generator: str, why: str) -> None:
		"""Say once that a layer will not run, not once a bar."""

		if generator in self._complained:
			return

		self._complained.add(generator)

		LOG.warning(
			"the %r layer of %r will not run and is being skipped: %s. "
			"Further failures of this generator are not logged.",
			generator, self.name, why)


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

		return {"type": "transport", "fields": fields, "tempo_range": list(self.tempo_range)}

	def snapshot (self) -> dict[str, typing.Any]:
		"""Whether it is held, and the tempo the sequencer actually holds."""

		state: dict[str, typing.Any] = {"bpm": self._bpm()}

		if self._can_pause:
			state["paused"] = self._paused()

		return state

	def apply (self, rest: list[str], value: typing.Any) -> bool:
		"""Hold the transport, let it go, or set the tempo."""

		if len(rest) != 1:
			return False

		if rest[0] == "paused" and self._can_pause:
			return self._set_paused(bool(value))

		if rest[0] == "bpm":
			return self._set_bpm(value)

		return False

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

		kept.append({"name": part["name"], "x": max(0, x), "y": max(0, y)})

	return kept


class PageStore:
	"""Where a composition keeps the arrangements made on its pages.

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

	def declaration (self, layout: list[dict[str, typing.Any]] | None = None) -> dict[str, typing.Any]:
		"""What a panel needs in order to offer this page and draw it.

		``layout`` is the arrangement somebody has already made, if there is
		one.  Absent, the panel places the parts itself, left to right and then
		down, until somebody moves them (#2078).
		"""

		declared: dict[str, typing.Any] = {
			"id": self.page_id, "title": self.title or self.page_id, "parts": self.parts}

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
		self._thread: threading.Thread | None = None
		self._stopping = threading.Event()
		self._last_beat_at: float | None = None

	def start (self) -> None:
		"""Begin listening to the clock and dialling the service.

		Safe to call before the composition plays: the link simply waits, and
		the panel shows the app as absent until it answers.
		"""

		self.composition.on_event("beat", self._on_beat)

		for control in self.controls.values():
			control.attach(self)

		self._thread = threading.Thread(target=self._run_link, name="superintendent-link", daemon=True)
		self._thread.start()

		LOG.info("Superintendent link started; dialling %s", self.url)

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

		grid = next((c for c in self.controls.values() if isinstance(c, StepGrid)), None)

		self._emit(superintendent.protocol.event(
			self.app_name, "beat", beat=beat, ts=now, interval=interval,
			steps=grid.steps if grid else None, beats=grid.beats if grid else None))

		for control in self.controls.values():
			for path, value in control.poll():
				self.version += 1
				self._emit(superintendent.protocol.changed(
					self.app_name, path, value, self.version, by="app"))

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
			self._emit(superintendent.protocol.nack(self.app_name, path, client, seq, str(refusal)))
			return

		except Exception:
			LOG.warning("applying %r failed", path, exc_info=True)
			self._emit(superintendent.protocol.nack(self.app_name, path, client, seq, "the app could not do that"))
			return

		if not changed:
			return

		self.version += 1

		self._emit(superintendent.protocol.changed(
			self.app_name, path, control.applied(rest.split("/"), value), self.version,
			by="panel", client=client, seq=seq))

	def happened (self, name: str, **fields: typing.Any) -> None:
		"""Announce something that is true for one cycle and stored nowhere.

		An event rather than a change, and the distinction is the whole of
		#1965: a change is intent and is kept, an event is what the music did
		this time round.  Nothing applies one to any control's state.
		"""

		self._emit(superintendent.protocol.event(self.app_name, name, **fields))

	def report (self, path: str, value: typing.Any) -> None:
		"""Announce something the app did of its own accord, on the clock loop.

		A control polled once a beat cannot report a pause, because a paused
		composition has no beats.
		"""

		self.version += 1

		self._emit(superintendent.protocol.changed(
			self.app_name, path, value, self.version, by="app"))

	def _emit (self, frame: superintendent.protocol.Frame) -> None:
		"""Hand a frame to the link thread, in the order it was produced.

		Called on the clock loop and never blocking there: the send itself
		happens on the link thread, so a slow socket cannot delay a pulse.
		"""

		loop = self._link_loop

		if loop is None or self._socket is None:
			return

		asyncio.run_coroutine_threadsafe(self._send(frame), loop)

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

					LOG.info("connected to Superintendent at %s", self.url)

					await self._declare()
					await self._serve(socket)

			except (OSError, websockets.exceptions.WebSocketException) as error:
				LOG.debug("Superintendent not reachable (%s); retrying in %.2fs", error, delay)

			finally:
				self._socket = None

			await asyncio.sleep(delay)
			delay = min(delay * 2, RECONNECT_CEILING)

	async def _declare (self) -> None:
		"""Say what this app offers and what it currently holds."""

		kept = self.page_store.load() if self.page_store is not None else {}

		for control in self.controls.values():
			control.declared()

		await self._send(superintendent.protocol.declare(
			self.app_name,
			{name: control.declaration() for name, control in self.controls.items()},
			{name: control.snapshot() for name, control in self.controls.items()},
			self.version,
			[page.declaration(kept.get(page.page_id)) for page in self.pages],
		))

	async def _serve (self, socket: typing.Any) -> None:
		"""Carry what the service sends until the socket closes."""

		async for raw in socket:
			try:
				frame = superintendent.protocol.decode(raw)

			except superintendent.protocol.ProtocolError:
				LOG.warning("service sent a frame that could not be read", exc_info=True)
				continue

			if frame["t"] == "set":
				self._cross(frame)

			elif frame["t"] == "layout":
				await self._keep_layout(frame)

	async def _keep_layout (self, frame: superintendent.protocol.Frame) -> None:
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
			await self._send(superintendent.protocol.nack(
				self.app_name, page_id, str(frame.get("client", "")),
				int(frame.get("seq", 0)), "that arrangement could not be read"))
			return

		if self.page_store is None:
			await self._send(superintendent.protocol.nack(
				self.app_name, page_id, str(frame.get("client", "")),
				int(frame.get("seq", 0)), "this composition keeps no page file to save into"))
			return

		try:
			self.page_store.save(page_id, parts)

		except OSError as error:
			LOG.warning("could not save the arrangement of %r", page_id, exc_info=True)

			await self._send(superintendent.protocol.nack(
				self.app_name, page_id, str(frame.get("client", "")),
				int(frame.get("seq", 0)), f"the arrangement could not be written: {error.strerror}"))
			return

		LOG.info("kept the arrangement of page %r", page_id)

		# Declaring again is how every panel learns: a page set is shared, so
		# an arrangement made on one panel belongs on the others too.
		await self._declare()

	def _cross (self, frame: superintendent.protocol.Frame) -> None:
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

	async def _send (self, frame: superintendent.protocol.Frame) -> None:
		"""Write one frame, forgiving a socket that has closed underneath it."""

		socket = self._socket

		if socket is None:
			return

		try:
			await socket.send(superintendent.protocol.encode(frame))

		except websockets.exceptions.WebSocketException:
			LOG.debug("frame dropped: the service went away mid-send")
