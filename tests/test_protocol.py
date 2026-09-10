"""Frames survive the round trip, and unreadable ones are refused by name."""

import pytest

import superconductor.protocol


def test_a_frame_survives_the_round_trip () -> None:
	"""What is encoded is what comes back."""

	frame = superconductor.protocol.set_frame("subsequence", "grid/kick/4", True, "panel-1", 7)

	assert superconductor.protocol.decode(superconductor.protocol.encode(frame)) == frame


def test_a_changed_frame_names_the_hand_that_moved_it () -> None:
	"""A panel's own write carries the client and sequence that asked for it."""

	frame = superconductor.protocol.changed(
		"subsequence", "grid/kick/4", True, 12, by="panel", client="panel-1", seq=7)

	assert frame["by"] == "panel"
	assert frame["client"] == "panel-1"
	assert frame["seq"] == 7


def test_a_change_the_app_made_itself_names_no_client () -> None:
	"""Nothing pretends a composition's own edit came from a finger."""

	frame = superconductor.protocol.changed("subsequence", "grid/kick/4", True, 12, by="app")

	assert "client" not in frame
	assert "seq" not in frame


def test_hello_carries_a_token_field_that_is_not_used_yet () -> None:
	"""Its absence would force a protocol change the day the panel is remote."""

	assert "token" in superconductor.protocol.hello("panel-1", "grid")


@pytest.mark.parametrize("raw", ["not json", "[1, 2, 3]", '"a string"', '{"no": "kind"}', '{"t": 3}'])
def test_a_frame_that_is_not_a_named_object_is_refused (raw: str) -> None:
	"""Anything without a kind is refused rather than half-understood."""

	with pytest.raises(superconductor.protocol.ProtocolError):
		superconductor.protocol.decode(raw)


def test_a_number_off_the_wire_is_read_rather_than_assumed () -> None:
	"""`decode` promises an object with a string `t` and nothing else.

	Every other field is whatever the sender put there, and three of them were
	coerced with a bare `int()` or `float()` inside a `try` that catches only a
	disconnection and a `ProtocolError`.  So `{"t": "set", ..., "seq": "oops"}`
	took its own socket down with a traceback instead of going through the path
	this module has for exactly "a frame that could not be read".
	"""

	assert superconductor.protocol.whole({"t": "set", "seq": 4}, "seq", -1) == 4
	assert superconductor.protocol.whole({"t": "set"}, "seq", -1) == -1

	# JSON has one number type, so a whole float is a whole number.
	assert superconductor.protocol.whole({"t": "set", "seq": 4.0}, "seq", -1) == 4

	for bad in ("oops", None, 4.5, True, [4], {"n": 4}, float("nan"), float("inf")):
		with pytest.raises(superconductor.protocol.ProtocolError):
			superconductor.protocol.whole({"t": "set", "seq": bad}, "seq", -1)

	assert superconductor.protocol.number({"t": "ping", "ts": 1.5}, "ts", 0.0) == 1.5
	assert superconductor.protocol.number({"t": "ping"}, "ts", 0.0) == 0.0

	for bad in ("later", None, True, float("nan"), float("inf")):
		with pytest.raises(superconductor.protocol.ProtocolError):
			superconductor.protocol.number({"t": "ping", "ts": bad}, "ts", 0.0)


@pytest.mark.parametrize(("spoken", "gap"), [
	(superconductor.protocol.CONTRACT_VERSION, None),
	# The same major, so it is behind rather than incompatible — which is the
	# distinction the whole thing turns on.
	("1.0.0", "older"),
	("9.0.0", "major"),
	("0.0.0", "major"),
	("", "unreadable"),
	("banana", "unreadable"),
	(None, "unreadable"),
	(5, "unreadable"),
	("1.17", "unreadable"),
	("1.17.0.1", "unreadable"),
	("1.-1.0", "unreadable"),
])
def test_a_version_on_the_wire_is_compared_rather_than_carried (
	spoken: object, gap: str | None) -> None:
	"""Both ends have always sent a contract version and neither ever read one
	(#2164).  It went 1.13.0 to 1.17.0 in two days with a panel open throughout
	and nothing anywhere said a word.

	The cases that are not a version at all are reported rather than ignored,
	because something is speaking and it is not this protocol — and a missing
	field reads as `None`, which is what an end too old to send it looks like.
	"""

	assert superconductor.protocol.contract_gap(spoken) == gap


def test_which_side_is_behind_is_named_and_not_left_to_the_caller () -> None:
	"""So a log line says what was found rather than working out whose fault it
	is.  The direction is always the *other* side's.

	Built from this version rather than written down, so the test does not need
	editing every time the contract moves — which is how a table of literals
	comes to assert nothing.
	"""

	major, minor, patch = (int(one) for one in superconductor.protocol.CONTRACT_VERSION.split("."))

	assert superconductor.protocol.contract_gap(f"{major}.{minor + 1}.0") == "newer"
	assert superconductor.protocol.contract_gap(f"{major}.{minor}.{patch + 1}") == "newer"
	assert superconductor.protocol.contract_gap(f"{major + 1}.0.0") == "major"

	if minor:
		assert superconductor.protocol.contract_gap(f"{major}.{minor - 1}.99") == "older"

	if patch:
		assert superconductor.protocol.contract_gap(f"{major}.{minor}.{patch - 1}") == "older"


def test_a_parameter_may_be_unset_only_when_it_opened_unset () -> None:
	"""The permission is #2249's sentence read backwards, and its edge is the
	*presence* of the key rather than the value read out of it.

	An instrument's settings declare no ``default`` at all — `Parameter.
	declaration` never emits one — so a test written as
	``field.get("default") is None`` is true of every switch and every dial on a
	Matriarch, and would offer a CC an unset it has no way to be.  A catalogue
	says ``"default": null`` on purpose.  That difference is the whole check, and
	it is the one thing about this that is easy to get wrong from either end.
	"""

	may = superconductor.protocol.may_be_unset

	assert may({"name": "grid", "required": False, "default": None}) is True
	assert may({"name": "grid", "default": None}) is True, "unsaid is not required"

	assert may({"name": "root", "required": True, "default": None}) is False
	assert may({"name": "beat", "required": False, "default": 0.0}) is False
	assert may({"name": "beat", "required": False, "default": 0}) is False, \
		"zero is a value somebody chose"
	assert may({"name": "on", "required": False, "default": False}) is False, \
		"and so is false"

	assert may({"name": "cutoff", "kind": "number"}) is False, \
		"a settings field declares no default and has no unset to go back to"
