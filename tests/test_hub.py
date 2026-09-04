"""Routing: a tap reaches the app, and what the app applied reaches every panel."""

import typing

import superintendent.hub
import superintendent.protocol


class Recorder:
	"""Stands in for one socket, keeping what was written to it."""

	def __init__ (self) -> None:
		"""Start with nothing written."""

		self.frames: list[superintendent.protocol.Frame] = []

	async def send (self, frame: superintendent.protocol.Frame) -> None:
		"""Keep a frame instead of putting it on a wire."""

		self.frames.append(frame)

	def of_kind (self, kind: str) -> list[superintendent.protocol.Frame]:
		"""Every frame of one kind, in the order it was sent."""

		return [frame for frame in self.frames if frame["t"] == kind]


CONTROLS: dict[str, typing.Any] = {"grid": {"type": "step_grid", "rows": ["kick"], "steps": 16}}


async def _hub_with_app () -> tuple[superintendent.hub.Hub, superintendent.hub.AppLink, Recorder]:
	"""A hub with one app dialled in and nothing on the glass yet."""

	hub = superintendent.hub.Hub(page={"name": "grid"})
	recorder = Recorder()

	app = superintendent.hub.AppLink(
		name="subsequence", send=recorder.send, controls=CONTROLS, state={"grid": {"kick": [0, 4]}})
	await hub.app_declared(app)

	return hub, app, recorder


async def test_a_panel_is_told_what_to_draw_the_moment_it_arrives () -> None:
	"""The manifest carries the declaration and the snapshot the grid itself."""

	hub, _, _ = await _hub_with_app()
	glass = Recorder()

	await hub.panel_joined(superintendent.hub.PanelLink(client="panel-1", send=glass.send))

	manifest = glass.of_kind("manifest")[0]
	snapshot = glass.of_kind("snapshot")[0]

	assert manifest["apps"]["subsequence"]["grid"]["rows"] == ["kick"]
	assert snapshot["state"] == {"grid": {"kick": [0, 4]}}


async def test_a_panel_already_open_learns_when_an_app_arrives () -> None:
	"""Starting the composition second is the ordinary case, not an error."""

	hub = superintendent.hub.Hub(page={"name": "grid"})
	glass = Recorder()

	await hub.panel_joined(superintendent.hub.PanelLink(client="panel-1", send=glass.send))
	await hub.app_declared(superintendent.hub.AppLink(
		name="subsequence", send=Recorder().send, controls=CONTROLS, state={"grid": {}}))

	assert glass.of_kind("manifest")[-1]["apps"]["subsequence"] == CONTROLS
	assert glass.of_kind("app")[-1]["up"] is True


async def test_a_tap_is_passed_to_the_app_and_not_applied_here () -> None:
	"""The app is the authority; the service never guesses on its behalf."""

	hub, _, app_socket = await _hub_with_app()
	glass = Recorder()
	panel = superintendent.hub.PanelLink(client="panel-1", send=glass.send)

	await hub.panel_joined(panel)
	await hub.set_requested(panel, {"t": "set", "app": "subsequence", "path": "grid/kick/8", "v": True, "seq": 3})

	forwarded = app_socket.of_kind("set")[0]

	assert forwarded["path"] == "grid/kick/8"
	assert forwarded["client"] == "panel-1"
	assert forwarded["seq"] == 3
	assert glass.of_kind("changed") == []


async def test_a_tap_for_an_app_that_is_not_there_is_refused_by_name () -> None:
	"""A ring that would never clear is worse than being told at once."""

	hub = superintendent.hub.Hub(page={"name": "grid"})
	glass = Recorder()
	panel = superintendent.hub.PanelLink(client="panel-1", send=glass.send)

	await hub.panel_joined(panel)
	await hub.set_requested(panel, {"t": "set", "app": "subsequence", "path": "grid/kick/8", "v": True, "seq": 3})

	refusal = glass.of_kind("nack")[0]

	assert refusal["seq"] == 3
	assert refusal["path"] == "grid/kick/8"


async def test_what_the_app_applied_reaches_every_panel_and_confirms_to_the_asker () -> None:
	"""One panel taps; both see the face move, and only the asker is acked."""

	hub, app, _ = await _hub_with_app()
	first, second = Recorder(), Recorder()

	await hub.panel_joined(superintendent.hub.PanelLink(client="panel-1", send=first.send))
	await hub.panel_joined(superintendent.hub.PanelLink(client="panel-2", send=second.send))

	await hub.change_reported(app, superintendent.protocol.changed(
		"subsequence", "grid/kick/8", True, 5, by="panel", client="panel-1", seq=3))

	assert first.of_kind("changed")[0]["v"] is True
	assert second.of_kind("changed")[0]["v"] is True
	assert first.of_kind("ack")[0]["seq"] == 3
	assert second.of_kind("ack") == []


async def test_the_service_keeps_its_own_copy_so_a_late_panel_sees_the_grid () -> None:
	"""A panel arriving after the change is not made to wake the app for it."""

	hub, app, _ = await _hub_with_app()

	await hub.change_reported(app, superintendent.protocol.changed(
		"subsequence", "grid/kick/8", True, 5, by="app"))

	late = Recorder()
	await hub.panel_joined(superintendent.hub.PanelLink(client="panel-2", send=late.send))

	assert late.of_kind("snapshot")[0]["state"]["grid"]["kick"] == [0, 4, 8]


async def test_an_app_going_away_is_shown_on_the_glass () -> None:
	"""A control nobody can reach must not look reachable."""

	hub, _, _ = await _hub_with_app()
	glass = Recorder()

	await hub.panel_joined(superintendent.hub.PanelLink(client="panel-1", send=glass.send))
	await hub.app_left("subsequence")

	assert glass.of_kind("app")[-1] == {"t": "app", "app": "subsequence", "up": False}
	assert glass.of_kind("manifest")[-1]["apps"] == {}
