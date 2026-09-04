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


CONTRACT_VERSION = "1.0.0"
"""Bumped when a frame changes shape.  Both ends send it and neither guesses."""

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


def hello (client: str, page: str, versions: dict[str, int] | None = None) -> Frame:
	"""The panel introducing itself, with the version it last saw for each app.

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


def declare (app: str, controls: Frame, state: Frame, version: int) -> Frame:
	"""An app introducing itself and saying what it can be controlled by."""

	return {
		"t": "declare",
		"contract": CONTRACT_VERSION,
		"app": app,
		"controls": controls,
		"state": state,
		"ver": version,
	}


def manifest (apps: dict[str, Frame], page: Frame) -> Frame:
	"""What the panel should draw: every dialled-in app and the controls it offers.

	Sent again whenever an app arrives or goes, so a panel that was already
	open when an app started still learns what it can now reach.
	"""

	return {"t": "manifest", "contract": CONTRACT_VERSION, "apps": apps, "page": page}


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
