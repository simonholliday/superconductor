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
import typing


CONTRACT_VERSION = "1.4.0"
"""Bumped when a frame changes shape.  Both ends send it and neither guesses.

1.1.0 adds ``service``, which an older panel ignores as it ignores any frame it
does not know — so the minor number, not the major one.  1.2.0 adds ``pages`` to
``declare`` and to ``manifest``: an app that sends none, and a panel that reads
none, both behave exactly as they did.  1.3.0 adds ``arrange``, which an app
that cannot save one answers with a ``nack`` like any other refusal.  1.4.0 adds
the ``recipe`` control kind and the ``range`` parameter shape; a service too old
for either marks the control unsupported and says so on the glass, which is the
mechanism that already exists for exactly this.

The frames themselves have not changed since 1.3.0.  A stack is added to and
reordered by setting a path like any other control, which was the point of
choosing absolute sets: adding a generator from the glass needed no new frame,
only a value that happens to be a list (#2085).
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


def arrange (app: str, page: str, parts: list[Frame], client: str, seq: int) -> Frame:
	"""A panel handing back a page's arrangement for the app to keep.

	``parts`` is every part on that page as ``{name, x, y}``, in the order they
	are stacked — first drawn to last drawn, so the last entry is the one on
	top.  Positions are in lattice cells and no size is sent: a part's footprint
	follows its contents at whatever size the panel is drawn at, and a layout
	that carried pixels would be one person's screen imposed on another's
	(#2078).

	Sent when arranging is left rather than while it is going on, so a drag in
	progress is never half-saved (#2075).
	"""

	return {"t": "arrange", "app": app, "page": page, "parts": parts,
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
