"""The frame vocabulary spoken over every Superintendent socket.

One JSON object per frame, in UTF-8, named by its ``t`` field.  The panel and
each app speak the same vocabulary, so a frame crossing the service is usually
forwarded rather than translated.

The full vocabulary is Subroutine document #2018.  What appears here is the
subset the first proof-of-concept (#2047) needs.  Frames that design names but
this build does not use — ``fire``, ``telemetry`` and the page frames — are
absent rather than stubbed, so nothing claims to work that has never run.
"""

import json
import math
import typing


CONTRACT_VERSION = "1.17.0"
"""Bumped when a frame changes shape.  Both ends send it and neither guesses.

1.1.0 adds ``service``, which an older panel ignores as it ignores any frame it
does not know — so the minor number, not the major one.  1.2.0 adds ``pages`` to
``declare`` and to ``manifest``: an app that sends none, and a panel that reads
none, both behave exactly as they did.  1.3.0 adds ``arrange``, which an app
that cannot save one answers with a ``nack`` like any other refusal.  1.4.0 adds
the ``recipe`` control kind and the ``range`` parameter shape; a service too old
for either marks the control unsupported and says so on the glass, which is the
mechanism that already exists for exactly this.

1.5.0 renames ``arrange`` to ``layout``.  The frame is unchanged in every
other respect; the word was the problem.  *Arrangement* is a musical term in a
package that talks to a sequencer, and it was being used here for where a block
sits on a screen — a collision worth the rename while there is one app and one
panel to keep in step.

1.6.0 gives a layer an ``index``: the number a person sees on its window, held
by that layer for the whole of its life and never handed out twice.  A panel too
old to read it draws the stack exactly as it did; an app too old to send one
leaves every layer at zero, which is what a panel shows when it has not been
told a number.

1.7.0 adds two things a panel may draw and neither end acts on.  A control may
carry ``about``: a list of ``{label, value}`` facts shown beside its name.  It
exists because the package may not hold a MIDI channel or an instrument's name
(#1465), so a composition that wants those on the glass has to be the one saying
them.  And a parameter may carry ``role``, which says what a shape was before it
became a shape — a ``choice`` with ``role: "pitch"`` is a pitch the composition
resolved into the voices it has.  A panel too old for either ignores it as it
ignores any field it does not know.

1.8.0 lets a layer of a stack be a ``pattern`` as well as a ``generator``: a grid
belonging to no instrument, routed into several so that two synths share a
bassline and each add notes of their own (#2108).  It names a ``source`` where a
generator names a ``generator``, and the stack declares the ``sources`` it may
take from.  A service too old refuses the layer rather than dropping it, which is
the right way round: the app would play a route the service was not holding.

1.9.0 adds the ``realised`` event: which cells of a grid the algorithms put
there this cycle, as ``control`` and ``cells``.  1.10.0 makes each row's cells a
map of step to velocity rather than a list of steps, because how hard a
generated note is played is the thing that tells a ghost fill from a full hit,
and a panel drawing them the same weight says the opposite of what they are.  **An event and never a change**,
which is the whole of #1965 — a change is intent and is kept, and these notes are
not intent.  Nothing applies one to any control's state, a panel draws them as
dots beside the steps somebody tapped, and a person's taps remain the only thing
anything stores.  Sent only when the answer differs from the cycle before, so a
deterministic stack is silent.

1.11.0 gives a grid an ``enabled`` flag beside its rows, set at
``control/enabled``.  A mute in the sense a mixer means it: the notes stay where
they are and stop being heard.  What "off" does is the app's business — a grid
that drives a pattern mutes that pattern, a grid that only feeds routes stops
contributing — and neither the service nor the panel interprets it.  Absent means
on, which is what every grid was before there was a switch.

1.12.0 lets a ``note_grid`` declare ``divisions``: how many addressable
positions make up one drawn cell.  Absent means one, which is what every grid
was before there was a number — a position is a step, and nothing changes.
A composition that wants to place a note between two steps says so here, and
then a note's position and its length are both counted in those finer
positions rather than in steps.

**The unit belongs to the composition, not to this package.**  ``composition
.data`` is the app's own dict, read by its own pattern builder, so a panel that
re-keyed it to a resolution of its choosing would be dictating to the app it
serves.  Instead the app names the resolution it keeps and the panel offers
what that can hold: a grid left at one division snaps to whole steps because
that is the only place it could store anything else.  A panel too old to read
the field draws a step per position, which is wrong on a grid that declares
more than one — so a service that does not know the field refuses the control
rather than drawing it, as 1.8.0 does for the same reason.

1.17.0 lets a note grid be transposed.  It declares ``transpose_range`` and its
state carries ``transpose`` in semitones, plus two fields the app alone can fill:
``labels``, what each row is called at the current offset, and ``unreachable``,
the rows that will not sound at it.

**The sound moves and the drawing does not.**  The notes stay where they were
put, so the shape a person made stays a stable thing to read and keep editing,
and the change is undone by putting the number back.  What follows the offset is
the row labels — which is what stops the glass lying about pitch, and is the only
way to mark a row pushed past an instrument's ceiling.  A Moog Minitaur ignores
anything above note 72 and goes *silent* rather than wrong, so a transposed
bassline can vanish with every cell still lit and nothing to say why.

The panel cannot compute any of it: it knows a row is called ``C2`` and nothing
else, and that ``C2`` is a pitch is a fact about a studio (#1465).  So the app
sends the words and the panel prints them.

1.16.0 adds ``action``: a parameter that **does something and holds nothing**.
It names options as a ``choice`` does and a press is checked against them, but no
value is kept anywhere — not by the app, not by the service, and not on the glass,
where no button is ever drawn as chosen.

It exists because some settings cannot honestly be displayed.  A Moog Matriarch's
voicing is a front-panel switch *as well as* control change 94, and moving that
switch changes what the instrument does with no message of any kind — measured on
the rig, where a mode set over MIDI was overridden by a hand and a mode set by
hand was overridden over MIDI, last writer winning either way (#2177).  Any state
a panel showed for it would be wrong within seconds, and a panel joining late
would be handed a confident lie.

So the service returns without writing its copy, and ``apply`` reports that
nothing changed while still telling the composition something happened: the press
is acked, and no ``changed`` frame follows it, because a ``changed`` is precisely
the service's cue to remember a value.  A panic button is the same shape — there
is no state after "all notes off" either.

1.15.0 adds ``choices`` to a parameter's kinds: several of a pool, held as a list
in the order the panel sent, where ``choice`` is one of it.  It is a kind of its
own rather than a flag on ``choice``, on the same reasoning that makes ``range``
a kind rather than a ``number`` carrying a pair — a kind settles the shape of a
value, and one meaning a string here and a list there settles nothing.

It is worth a version because of what it was costing: a pitch parameter taking
*several* pitches had nowhere to go, so the adapter dropped it and marked its
generator partial, and **twenty-two of thirty-three generators arrived that
way** — not a random two thirds but every chord and melody writer in the
catalogue (#2150).  A panel too old to draw the kind refuses the control rather
than guessing, as 1.8.0 does for the same reason.

The same version stops ``partial`` conflating two different facts.  It was set
both by an app calling its own generator partial and by this package failing to
draw a parameter, and a panel could not tell them apart; the parameters this
package could not draw are now named in ``undrawn``, and only the second is
anything anybody here can fix.

1.14.0 replaces a note grid's ``mono`` flag with ``voices``, a count of how many
notes the instrument sounds at once — ``null`` for as many as you like, ``1`` for
what ``mono`` meant.  Voicing is not a boolean and never was: of the fourteen
instruments measured in #2125 one is switchable between 1, 2 and 4 voices *from
the glass*, and another drops from 32 notes to 16 when an effect is on.  Nothing
on the panel ever read ``mono`` — the rule is the app's and is enforced there —
so this costs a panel nothing and gives one something to say when a part is full.

1.13.0 makes each realised cell an object rather than a velocity: ``{"v": 100,
"from": "l7x2"}``, where ``from`` is the id of the stack layer that put the note
there.  A routed grid's notes and a generator's arrived under the same mark and
could not be told apart, so a person looking for the generator behind a note
found none — because there was none, and the note had come from a pattern routed
in.  The panel already holds the layers, so it reads the *kind* from those and
this only has to say which one; a second copy of the kind on the wire is a second
copy that could disagree.  The adapter now reads the pattern once per layer
rather than twice per cycle, which is one list copy each on a stack four deep.

A stack is added to and reordered by setting a path like any other control,
which was the point of choosing absolute sets: adding a generator from the
glass needed no new frame, only a value that happens to be a list (#2085).
"""

Frame = dict[str, typing.Any]


class ProtocolError (Exception):
	"""A frame that could not be understood, named by what was wrong with it."""


def encode (frame: Frame) -> str:
	"""Render a frame as the compact JSON that goes on the wire."""

	return json.dumps(frame, separators=(",", ":"))


def decode (raw: str | bytes) -> Frame:
	"""Read a frame off the wire, refusing anything that is not a named object."""

	try:
		parsed = json.loads(raw)

	except json.JSONDecodeError as error:
		raise ProtocolError(f"not JSON: {error}") from error

	if not isinstance(parsed, dict):
		raise ProtocolError(f"expected an object, got {type(parsed).__name__}")

	if not isinstance(parsed.get("t"), str):
		raise ProtocolError("frame has no 't' naming its kind")

	return typing.cast(Frame, parsed)


def whole (frame: Frame, name: str, fallback: int) -> int:
	"""One field of a frame as a whole number, refusing anything that is not one.

	`decode` guarantees a frame is an object carrying a string ``t`` and says
	nothing about any other field, so everything else is whatever the sender
	chose to put there.  Three fields were coerced with a bare ``int()`` or
	``float()`` inside a ``try`` that catches only a disconnection and a
	`ProtocolError` — so ``{"t": "set", ..., "seq": "oops"}`` took the socket
	down with a traceback rather than through the careful path this module has
	for exactly "a frame that could not be read".

	A float that happens to be whole is accepted: JSON has one number type, and
	refusing ``2.0`` for a sequence number would be pedantry about an encoding
	rather than about the value.
	"""

	held = frame.get(name, fallback)

	if isinstance(held, bool) or not isinstance(held, (int, float)):
		raise ProtocolError(f"{name!r} is a whole number, and {held!r} is not one")

	if isinstance(held, float) and (not math.isfinite(held) or held != int(held)):
		raise ProtocolError(f"{name!r} is a whole number, and {held!r} is not one")

	return int(held)


def number (frame: Frame, name: str, fallback: float) -> float:
	"""One field of a frame as a number, refusing anything that is not one.

	Infinities and NaN are refused as well as strings: they survive JSON in
	some encoders, and a timestamp of NaN would come back through a pong and
	poison the panel's own clock arithmetic.
	"""

	held = frame.get(name, fallback)

	if isinstance(held, bool) or not isinstance(held, (int, float)) or not math.isfinite(held):
		raise ProtocolError(f"{name!r} is a number, and {held!r} is not one")

	return float(held)


def hello (client: str, page: str | None, versions: dict[str, int] | None = None) -> Frame:
	"""The panel introducing itself, with the version it last saw for each app.

	``page`` is the page this panel is showing, or null when it has not chosen
	one — a panel that has never been set, or whose browser cannot remember.
	Nothing is served differently for it; it is there so a service can say which
	panel is looking at what.

	``token`` is carried and ignored.  It costs nothing now and its absence
	would force a protocol change the day the panel is reached from off the
	local network.
	"""

	return {
		"t": "hello",
		"contract": CONTRACT_VERSION,
		"client": client,
		"page": page,
		"ver": versions or {},
		"token": None,
	}


def declare (app: str, controls: Frame, state: Frame, version: int,
             pages: list[Frame] | None = None) -> Frame:
	"""An app introducing itself and saying what it can be controlled by.

	``pages`` is how a composition offers several views over those controls
	(#2075).  It is optional in both directions: an app with nothing to say
	about arrangement sends none, and a panel then shows everything declared,
	which is what every panel did before pages existed.
	"""

	return {
		"t": "declare",
		"contract": CONTRACT_VERSION,
		"app": app,
		"controls": controls,
		"state": state,
		"ver": version,
		"pages": pages or [],
	}


def manifest (apps: dict[str, Frame], page: Frame, pages: list[Frame] | None = None) -> Frame:
	"""What the panel should draw: every dialled-in app and the controls it offers.

	Sent again whenever an app arrives or goes, so a panel that was already
	open when an app started still learns what it can now reach — and so a page
	set arrives on a panel that was open before its composition started.

	``pages`` is every page every connected app declared, each carrying the app
	that declared it.  The service assembles the list and owns none of it: a
	page set belongs to the composition that sent it, and is never read from
	disk here (#2075).
	"""

	return {"t": "manifest", "contract": CONTRACT_VERSION, "apps": apps,
	        "page": page, "pages": pages or []}


def layout (app: str, page: str, parts: list[Frame], client: str, seq: int) -> Frame:
	"""A panel handing back where a page's parts sit, for the app to keep.

	``parts`` is every part on that page as ``{name, x, y}``, in the order they
	are stacked — first drawn to last drawn, so the last entry is the one on
	top.  Positions are in lattice cells and no size is sent: a part's footprint
	follows its contents at whatever size the panel is drawn at, and a layout
	that carried pixels would be one person's screen imposed on another's
	(#2078).

	Sent when a drag ends rather than while it is going on, so a layout in
	motion is never half-saved (#2075).  It used to be sent on leaving a mode,
	which did the same job more coarsely and needed the mode to exist.
	"""

	return {"t": "layout", "app": app, "page": page, "parts": parts,
	        "client": client, "seq": seq}


def service (version: str | None, build: str | None) -> Frame:
	"""Which Superintendent the panel has reached, sent whenever it says hello.

	The panel compares ``build`` against the one stamped on the page it is
	actually running.  A difference means the service has newer files than the
	browser loaded, which no other signal on the glass would reveal (#2056).

	Both fields may be null.  A version that could not be derived and a client
	directory that is not there are both real states, and saying so is better
	than sending a number that means neither.
	"""

	return {"t": "service", "contract": CONTRACT_VERSION, "version": version, "build": build}


def snapshot (app: str, state: Frame, version: int) -> Frame:
	"""One app's whole state, sent on every connect rather than on a version miss.

	A grid this size is well under a kilobyte, and always sending it means there
	is no version-comparison path that can be wrong.
	"""

	return {"t": "snapshot", "app": app, "state": state, "ver": version}


def set_frame (app: str, path: str, value: typing.Any, client: str, seq: int) -> Frame:
	"""A request to make *path* hold *value*, absolutely rather than by toggling.

	An absolute value is what makes a re-send after a reconnect safe: applying
	it twice reaches the same state as applying it once.
	"""

	return {"t": "set", "app": app, "path": path, "v": value, "client": client, "seq": seq}


def changed (
	app: str,
	path: str,
	value: typing.Any,
	version: int,
	by: str,
	client: str | None = None,
	seq: int | None = None,
) -> Frame:
	"""A value that has actually been applied, sent to every panel.

	``by`` says whose hand it was — ``panel`` or ``app`` — and a panel write
	carries the client and sequence number that asked for it, which is what
	lets the asking panel clear its ring.
	"""

	frame: Frame = {"t": "changed", "app": app, "path": path, "v": value, "ver": version, "by": by}

	if client is not None:
		frame["client"] = client

	if seq is not None:
		frame["seq"] = seq

	return frame


def ack (app: str, client: str, seq: int, version: int) -> Frame:
	"""Confirmation that a named request has been applied."""

	return {"t": "ack", "app": app, "client": client, "seq": seq, "ver": version}


def nack (app: str, path: str, client: str, seq: int, reason: str) -> Frame:
	"""Refusal of a named request, saying why and naming the cell it was for.

	The path is carried so the panel can clear the mark on exactly the cell the
	finger landed on, rather than searching for it.
	"""

	return {"t": "nack", "app": app, "path": path, "client": client, "seq": seq, "reason": reason}


def event (app: str, name: str, **fields: typing.Any) -> Frame:
	"""Something the app reports that no one asked for — a beat, or a rebuild."""

	return {"t": "event", "app": app, "name": name, **fields}


def app_presence (app: str, up: bool) -> Frame:
	"""Whether an app is dialled in, so the panel can grey out what it cannot reach."""

	return {"t": "app", "app": app, "up": up}


def pong (sent_at: float) -> Frame:
	"""The panel's own timestamp echoed back.

	The round trip is what the playhead uses to place the service's clock
	against the browser's, so the highlight sits where the sound is.
	"""

	return {"t": "pong", "ts": sent_at}
