"""Frames survive the round trip, and unreadable ones are refused by name."""

import pytest

import superintendent.protocol


def test_a_frame_survives_the_round_trip () -> None:
	"""What is encoded is what comes back."""

	frame = superintendent.protocol.set_frame("subsequence", "grid/kick/4", True, "panel-1", 7)

	assert superintendent.protocol.decode(superintendent.protocol.encode(frame)) == frame


def test_a_changed_frame_names_the_hand_that_moved_it () -> None:
	"""A panel's own write carries the client and sequence that asked for it."""

	frame = superintendent.protocol.changed(
		"subsequence", "grid/kick/4", True, 12, by="panel", client="panel-1", seq=7)

	assert frame["by"] == "panel"
	assert frame["client"] == "panel-1"
	assert frame["seq"] == 7


def test_a_change_the_app_made_itself_names_no_client () -> None:
	"""Nothing pretends a composition's own edit came from a finger."""

	frame = superintendent.protocol.changed("subsequence", "grid/kick/4", True, 12, by="app")

	assert "client" not in frame
	assert "seq" not in frame


def test_hello_carries_a_token_field_that_is_not_used_yet () -> None:
	"""Its absence would force a protocol change the day the panel is remote."""

	assert "token" in superintendent.protocol.hello("panel-1", "grid")


@pytest.mark.parametrize("raw", ["not json", "[1, 2, 3]", '"a string"', '{"no": "kind"}', '{"t": 3}'])
def test_a_frame_that_is_not_a_named_object_is_refused (raw: str) -> None:
	"""Anything without a kind is refused rather than half-understood."""

	with pytest.raises(superintendent.protocol.ProtocolError):
		superintendent.protocol.decode(raw)


def test_a_number_off_the_wire_is_read_rather_than_assumed () -> None:
	"""`decode` promises an object with a string `t` and nothing else.

	Every other field is whatever the sender put there, and three of them were
	coerced with a bare `int()` or `float()` inside a `try` that catches only a
	disconnection and a `ProtocolError`.  So `{"t": "set", ..., "seq": "oops"}`
	took its own socket down with a traceback instead of going through the path
	this module has for exactly "a frame that could not be read".
	"""

	assert superintendent.protocol.whole({"t": "set", "seq": 4}, "seq", -1) == 4
	assert superintendent.protocol.whole({"t": "set"}, "seq", -1) == -1

	# JSON has one number type, so a whole float is a whole number.
	assert superintendent.protocol.whole({"t": "set", "seq": 4.0}, "seq", -1) == 4

	for bad in ("oops", None, 4.5, True, [4], {"n": 4}, float("nan"), float("inf")):
		with pytest.raises(superintendent.protocol.ProtocolError):
			superintendent.protocol.whole({"t": "set", "seq": bad}, "seq", -1)

	assert superintendent.protocol.number({"t": "ping", "ts": 1.5}, "ts", 0.0) == 1.5
	assert superintendent.protocol.number({"t": "ping"}, "ts", 0.0) == 0.0

	for bad in ("later", None, True, float("nan"), float("inf")):
		with pytest.raises(superintendent.protocol.ProtocolError):
			superintendent.protocol.number({"t": "ping", "ts": bad}, "ts", 0.0)
