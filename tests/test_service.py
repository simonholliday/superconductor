"""The whole loop over real sockets: a tap leaves the glass and comes back."""

import pathlib
import typing

import starlette.testclient

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
