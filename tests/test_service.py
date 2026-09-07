"""The whole loop over real sockets: a tap leaves the glass and comes back."""

import pathlib
import re
import tomllib
import typing

import pytest
import starlette.testclient
import starlette.websockets

import superintendent
import superintendent.config
import superintendent.protocol
import superintendent.service


CONTROLS: dict[str, typing.Any] = {
	"grid": {"type": "step_grid", "rows": ["kick", "snare"], "steps": 16, "beats": 4}}


def _read_until (socket: typing.Any, kind: str, limit: int = 12) -> superintendent.protocol.Frame:
	"""Read frames until one of *kind* arrives, so ordering is not asserted."""

	for _ in range(limit):
		frame = socket.receive_json()

		if frame["t"] == kind:
			return typing.cast(superintendent.protocol.Frame, frame)

	raise AssertionError(f"no {kind!r} frame arrived")


def test_a_tap_reaches_the_app_and_its_answer_reaches_the_glass () -> None:
	"""The full round trip, with the service holding both ends."""

	client = starlette.testclient.TestClient(superintendent.service.build(superintendent.config.Config()))

	with client.websocket_connect("/ws/app") as app:
		app.send_json(superintendent.protocol.declare(
			"subsequence", CONTROLS, {"grid": {"kick": [0, 4]}}, 1))

		with client.websocket_connect("/ws/panel") as panel:
			panel.send_json(superintendent.protocol.hello("panel-1", "grid"))

			manifest = _read_until(panel, "manifest")
			snapshot = _read_until(panel, "snapshot")

			assert manifest["apps"]["subsequence"]["grid"]["steps"] == 16
			assert snapshot["state"]["grid"]["kick"] == [0, 4]

			panel.send_json({"t": "set", "app": "subsequence", "path": "grid/snare/12", "v": True, "seq": 1})

			asked = _read_until(app, "set")

			assert asked["path"] == "grid/snare/12"
			assert asked["client"] == "panel-1"

			app.send_json(superintendent.protocol.changed(
				"subsequence", "grid/snare/12", True, 2, by="panel",
				client=asked["client"], seq=asked["seq"]))

			changed = _read_until(panel, "changed")
			ack = _read_until(panel, "ack")

			assert changed["v"] is True
			assert changed["by"] == "panel"
			assert ack["seq"] == 1


def test_a_panel_that_arrives_before_any_app_is_told_so () -> None:
	"""Starting the panel first is ordinary, and it must not look broken."""

	client = starlette.testclient.TestClient(superintendent.service.build(superintendent.config.Config()))

	with client.websocket_connect("/ws/panel") as panel:
		panel.send_json(superintendent.protocol.hello("panel-1", "grid"))

		assert _read_until(panel, "manifest")["apps"] == {}


def test_a_beat_reaches_the_glass_so_the_playhead_has_something_to_follow () -> None:
	"""The events the sequencer reports are passed on unchanged."""

	client = starlette.testclient.TestClient(superintendent.service.build(superintendent.config.Config()))

	with client.websocket_connect("/ws/app") as app:
		app.send_json(superintendent.protocol.declare("subsequence", CONTROLS, {"grid": {}}, 1))

		with client.websocket_connect("/ws/panel") as panel:
			panel.send_json(superintendent.protocol.hello("panel-1", "grid"))
			_read_until(panel, "manifest")

			app.send_json(superintendent.protocol.event("subsequence", "beat", beat=2, interval=0.5))

			event = _read_until(panel, "event")

			assert event["name"] == "beat"
			assert event["beat"] == 2


def test_the_panel_is_answered_when_it_checks_the_service_is_alive () -> None:
	"""The echoed timestamp is also how the playhead places the two clocks."""

	client = starlette.testclient.TestClient(superintendent.service.build(superintendent.config.Config()))

	with client.websocket_connect("/ws/panel") as panel:
		panel.send_json(superintendent.protocol.hello("panel-1", "grid"))
		panel.send_json({"t": "ping", "ts": 1234.5})

		assert _read_until(panel, "pong")["ts"] == 1234.5


def test_the_page_is_served () -> None:
	"""The page, its script and both sockets share one origin."""

	client = starlette.testclient.TestClient(superintendent.service.build(superintendent.config.Config()))

	assert client.get("/").status_code == 200
	assert client.get("/client/app.js").status_code == 200


def test_the_page_ships_inside_the_package () -> None:
	"""A built copy carries what is inside the package and nothing else.

	The page once sat beside the package, which worked only because the install
	was editable: a wheel held the Python and no page at all, so an installed
	service answered every request with an error. This keeps it where a build
	can find it.
	"""

	assert superintendent.service.CLIENT_DIR.parent == pathlib.Path(superintendent.__file__).resolve().parent
	assert (superintendent.service.CLIENT_DIR / "index.html").exists()
	assert (superintendent.service.CLIENT_DIR / "app.js").exists()
	assert (superintendent.service.CLIENT_DIR / "vendor").is_dir()
	assert (superintendent.service.CLIENT_DIR / "fonts").is_dir()


def _globbed (pattern: str) -> typing.Any:
	"""One setuptools package-data glob as an expression, where * stops at a /."""

	parts = []

	for piece in re.split(r"(\*\*/|\*|\?)", pattern):
		if piece == "**/":
			parts.append(r"(?:[^/]+/)*")
		elif piece == "*":
			parts.append(r"[^/]*")
		elif piece == "?":
			parts.append(r"[^/]")
		else:
			parts.append(re.escape(piece))

	return re.compile("".join(parts) + "$")


def test_everything_the_page_needs_is_named_in_the_package_data () -> None:
	"""Every file the service can serve must be matched by a glob that ships it.

	**Listing the files a test knows about is not enough**, and this is the
	second time the same fault has shipped: the client once sat outside the
	package entirely, and then the bundled face was added under `client/fonts/`
	while the globs said `client/*` and `client/vendor/*`.  A glob does not
	reach into a directory nobody named, so a wheel carried the stylesheet that
	asks for the face and not the face — and an installed panel answered that
	request with a 404 and fell silently back to whatever condensed font the
	machine happened to have.

	Invisible to everyone developing, because a source tree has the file either
	way.  So this asks the question a build asks: for each file under `client/`,
	is there a glob that would carry it?
	"""

	settings = tomllib.loads(
		(pathlib.Path(superintendent.__file__).resolve().parent.parent / "pyproject.toml")
		.read_text(encoding="utf-8"))

	globs = [_globbed(one) for one in
	         settings["tool"]["setuptools"]["package-data"]["superintendent"]]

	inside = pathlib.Path(superintendent.__file__).resolve().parent
	missed = []

	for file in sorted(superintendent.service.CLIENT_DIR.rglob("*")):
		if not file.is_file() or "__pycache__" in file.parts:
			continue

		named = file.relative_to(inside).as_posix()

		if not any(one.match(named) for one in globs):
			missed.append(named)

	assert missed == [], f"these would not be carried into a built copy: {missed}"


def test_an_app_refusing_a_request_reaches_the_panel_that_asked () -> None:
	"""A control that will not move must say why, or the person is left guessing."""

	client = starlette.testclient.TestClient(superintendent.service.build(superintendent.config.Config()))

	with client.websocket_connect("/ws/app") as app:
		app.send_json(superintendent.protocol.declare("subsequence", CONTROLS, {"grid": {}}, 1))

		with client.websocket_connect("/ws/panel") as panel:
			panel.send_json(superintendent.protocol.hello("panel-1", "grid"))
			_read_until(panel, "manifest")

			panel.send_json({"t": "set", "app": "subsequence", "path": "grid/cowbell/0", "v": True, "seq": 9})
			asked = _read_until(app, "set")

			app.send_json(superintendent.protocol.nack(
				"subsequence", asked["path"], asked["client"], asked["seq"], "this grid has no 'cowbell' row"))

			refusal = _read_until(panel, "nack")

			assert refusal["seq"] == 9
			assert refusal["path"] == "grid/cowbell/0"
			assert "cowbell" in refusal["reason"]


def test_a_refusal_for_a_panel_that_has_gone_troubles_nobody () -> None:
	"""An app may answer after the panel that asked has closed its socket."""

	client = starlette.testclient.TestClient(superintendent.service.build(superintendent.config.Config()))

	with client.websocket_connect("/ws/app") as app:
		app.send_json(superintendent.protocol.declare("subsequence", CONTROLS, {"grid": {}}, 1))
		app.send_json(superintendent.protocol.nack("subsequence", "grid/kick/0", "nobody", 1, "gone"))

		app.send_json(superintendent.protocol.event("subsequence", "beat", beat=0))


def test_a_page_set_reaches_the_panel_with_the_app_that_owns_it () -> None:
	"""A composition owns its pages (#2075). The service carries them and reads
	no file of its own, so what arrives is exactly what was declared."""

	pages = [{"id": "both", "title": "Both", "parts": ["grid"]}]

	client = starlette.testclient.TestClient(superintendent.service.build(superintendent.config.Config()))

	with client.websocket_connect("/ws/app") as app:
		app.send_json(superintendent.protocol.declare(
			"subsequence", CONTROLS, {"grid": {"kick": [0]}}, 1, pages))

		with client.websocket_connect("/ws/panel") as panel:
			panel.send_json(superintendent.protocol.hello("panel-1", "both"))

			manifest = _read_until(panel, "manifest")

	assert manifest["pages"] == [{"id": "both", "title": "Both", "parts": ["grid"], "app": "subsequence"}]


def test_an_app_that_declares_no_pages_says_so_rather_than_nothing () -> None:
	"""Which is what keeps a panel written for pages working against a
	composition that has never heard of them."""

	client = starlette.testclient.TestClient(superintendent.service.build(superintendent.config.Config()))

	with client.websocket_connect("/ws/app") as app:
		app.send_json(superintendent.protocol.declare("subsequence", CONTROLS, {}, 1))

		with client.websocket_connect("/ws/panel") as panel:
			panel.send_json(superintendent.protocol.hello("panel-1", None))

			manifest = _read_until(panel, "manifest")

	assert manifest["pages"] == []


def test_an_arrangement_is_carried_to_the_app_that_owns_the_page () -> None:
	"""The service holds no page files and writes nothing (#2075): a page set
	belongs to the composition that declared it, so the composition decides."""

	client = starlette.testclient.TestClient(superintendent.service.build(superintendent.config.Config()))

	with client.websocket_connect("/ws/app") as app:
		app.send_json(superintendent.protocol.declare(
			"subsequence", CONTROLS, {}, 1, [{"id": "both", "title": "Both", "parts": ["grid"]}]))

		with client.websocket_connect("/ws/panel") as panel:
			panel.send_json(superintendent.protocol.hello("panel-1", "both"))
			_read_until(panel, "manifest")

			panel.send_json(superintendent.protocol.layout(
				"subsequence", "both", [{"name": "grid", "x": 3, "y": 1}], "panel-1", 7))

			carried = _read_until(app, "layout")

	assert carried["page"] == "both"
	assert carried["parts"] == [{"name": "grid", "x": 3, "y": 1}]
	assert carried["seq"] == 7


def test_an_arrangement_for_an_app_that_is_gone_is_refused_with_a_reason () -> None:
	"""So the person is told their layout was not kept, rather than finding out
	at the next reload."""

	client = starlette.testclient.TestClient(superintendent.service.build(superintendent.config.Config()))

	with client.websocket_connect("/ws/panel") as panel:
		panel.send_json(superintendent.protocol.hello("panel-1", "both"))

		panel.send_json(superintendent.protocol.layout(
			"nobody", "both", [{"name": "grid", "x": 0, "y": 0}], "panel-1", 1))

		refusal = _read_until(panel, "nack")

	assert "not connected" in refusal["reason"]


def test_a_control_this_service_is_too_old_for_is_declared_as_such () -> None:
	"""Rather than passed on as though it were fine.

	This cost an evening. The service was running code from before a control
	kind existed, so it dropped every change to that control while forwarding
	the frames — the panel was told once and never again, and the button
	appeared simply not to work. The reason was in a log nobody was reading.
	"""

	controls = {"mystery": {"type": "hologram", "shimmer": 3}, **CONTROLS}

	client = starlette.testclient.TestClient(superintendent.service.build(superintendent.config.Config()))

	with client.websocket_connect("/ws/app") as app:
		app.send_json(superintendent.protocol.declare("subsequence", controls, {}, 1))

		with client.websocket_connect("/ws/panel") as panel:
			panel.send_json(superintendent.protocol.hello("panel-1", None))

			manifest = _read_until(panel, "manifest")

	offered = manifest["apps"]["subsequence"]

	assert offered["mystery"]["unsupported"] == "hologram"
	assert "unsupported" not in offered["grid"], "a kind it does know is left alone"


def test_a_panel_saying_hello_again_is_one_panel_not_two () -> None:
	"""The client re-sends `hello` on waking, and it must not join twice.

	A hidden tab's timers are throttled to about once a minute, so a panel
	coming back cannot be left to its own stale timer to notice; it says hello
	again on the socket it already has.  Every one of those built a fresh
	`PanelLink` and appended it, and nothing removed the previous one — so after
	N wakes every frame went down the one socket N+1 times.

	Silent, which is what makes it worth a test: the frames are idempotent, so
	the page stays perfectly correct while the wire and the render loop degrade,
	and it only stops when the socket finally closes.  A kiosk panel on a wall
	wakes every time the screen does.
	"""

	client = starlette.testclient.TestClient(superintendent.service.build(superintendent.config.Config()))

	with client.websocket_connect("/ws/app") as app:
		app.send_json(superintendent.protocol.declare("subsequence", CONTROLS, {"grid": {}}, 1))

		with client.websocket_connect("/ws/panel") as panel:
			for _ in range(3):
				panel.send_json(superintendent.protocol.hello("panel-1", "grid"))
				_read_until(panel, "manifest")

			app.send_json(superintendent.protocol.event("subsequence", "beat", beat=7, interval=0.5))

			# **Fenced by a pong**, because the question is *how many* beats
			# arrive and there is no other way to know when to stop reading. A
			# broadcast goes to every registration; a pong is written to the one
			# link that asked. So the pong is always last and always single, and
			# whatever beats turn up before it are all of them.
			panel.send_json({"t": "ping", "ts": 99.0})

			beats = 0

			for _ in range(12):
				frame = panel.receive_json()

				if frame["t"] == "event" and frame.get("beat") == 7:
					beats += 1

				if frame["t"] == "pong":
					break

			else:
				raise AssertionError("no pong arrived to fence the count")

			assert beats == 1, f"one beat was delivered {beats} times after three hellos"


def test_a_malformed_frame_does_not_take_the_socket_down_with_a_traceback () -> None:
	"""It goes through the refusal path this service already has for it.

	The panel is our own code and this is a LAN, so it is not a security
	finding — it is that the service has a careful, deliberate `ProtocolError`
	path for "a frame that could not be read", and three coercions bypassed it
	to die with a `ValueError` instead.
	"""

	client = starlette.testclient.TestClient(superintendent.service.build(superintendent.config.Config()))

	with client.websocket_connect("/ws/app") as app:
		app.send_json(superintendent.protocol.declare("subsequence", CONTROLS, {"grid": {}}, 1))

		with client.websocket_connect("/ws/panel") as panel:
			panel.send_json(superintendent.protocol.hello("panel-1", "grid"))
			_read_until(panel, "manifest")

			panel.send_json({"t": "set", "app": "subsequence", "path": "grid/kick/0",
			                 "v": True, "seq": "oops"})

	# Nothing is read after it: the service closes the socket on a frame it
	# cannot read, and reading a closed one blocks rather than returning. What
	# is asserted is that leaving the block raises nothing — `TestClient`
	# re-raises an exception that escaped the endpoint, and a bare `int()` on a
	# string escapes it.


@pytest.mark.parametrize(("spoken", "level", "said"), [
	("1.0.0", "WARNING", "older"),
	("99.0.0", "ERROR", "may have changed shape"),
	("banana", "ERROR", "no readable contract version"),
])
def test_a_panel_speaking_a_different_contract_is_said_out_loud (
	caplog: typing.Any, spoken: str, level: str, said: str) -> None:
	"""It is said and not acted on (#2164).

	Refusing an old panel is wrong — it is the thing a person is standing in
	front of, and a blank screen because the service moved on is worse than a
	slightly stale one.  So the service says so and carries the panel, which is
	the pattern it already uses for a control kind it does not know: marked
	`unsupported` and drawn saying so, rather than dropped.
	"""

	client = starlette.testclient.TestClient(
		superintendent.service.build(superintendent.config.Config()))

	with caplog.at_level("DEBUG", logger="superintendent.service"):
		with client.websocket_connect("/ws/panel") as panel:
			panel.send_json({**superintendent.protocol.hello("panel", None), "contract": spoken})

			# Carried rather than closed: the greeting still arrives.
			assert _read_until(panel, "service")["contract"] \
				== superintendent.protocol.CONTRACT_VERSION

	complaints = [one for one in caplog.records if one.levelname == level and said in one.getMessage()]

	assert complaints, f"nothing said {said!r} at {level}: {[one.getMessage() for one in caplog.records]}"


def test_an_app_speaking_a_different_contract_is_said_out_loud (caplog: typing.Any) -> None:
	"""And it matters at least as much as a panel, because an app has no glass.

	A panel newer than the service can say so for itself, and does.  An app
	declaring a control kind the service does not know has every change to it
	dropped while the frame is still forwarded — and on the glass that is a
	button that will not move, with the reason in a log nobody is reading.  This
	is the line that makes that log worth reading.
	"""

	client = starlette.testclient.TestClient(
		superintendent.service.build(superintendent.config.Config()))

	with caplog.at_level("DEBUG", logger="superintendent.service"):
		with client.websocket_connect("/ws/app") as app:
			app.send_json({
				**superintendent.protocol.declare("subsequence", CONTROLS, {}, 1),
				"contract": "1.0.0"})

			with client.websocket_connect("/ws/panel") as panel:
				panel.send_json(superintendent.protocol.hello("panel", None))
				_read_until(panel, "manifest")

	complaints = [one.getMessage() for one in caplog.records
	              if "subsequence" in one.getMessage() and "older" in one.getMessage()]

	assert complaints, f"the app's version went unremarked: {[one.getMessage() for one in caplog.records]}"


def test_a_matching_contract_says_nothing_at_all (caplog: typing.Any) -> None:
	"""The ordinary case is silent, or the warning stops being a warning.

	Worth its own test because the check runs on every hello — and a panel
	re-sends one every time it wakes, which on a tablet carried round a room is
	often.
	"""

	client = starlette.testclient.TestClient(
		superintendent.service.build(superintendent.config.Config()))

	with caplog.at_level("DEBUG", logger="superintendent.service"):
		with client.websocket_connect("/ws/panel") as panel:
			panel.send_json(superintendent.protocol.hello("panel", None))
			_read_until(panel, "service")

	assert [one.getMessage() for one in caplog.records if "contract" in one.getMessage()] == []
