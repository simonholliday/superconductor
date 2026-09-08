"""Routing: a tap reaches the app, and what the app applied reaches every panel."""

import asyncio
import collections.abc
import concurrent.futures
import functools
import pathlib
import typing

import superintendent.hub
import superintendent.protocol


def _on_a_loop_of_its_own (
	test: collections.abc.Callable[[], collections.abc.Coroutine[typing.Any, typing.Any, None]],
) -> collections.abc.Callable[[], None]:
	"""Run one async test on a loop it owns, in a thread it owns.

	`pytest-asyncio` runs a bare ``async def test_`` with ``Runner.run()`` on the
	**main thread**, and that raises the moment something else is already running
	a loop there.  Playwright's sync API is exactly that something: it takes the
	main thread's loop and keeps it for the rest of the session, from the first
	page test onwards.

	**Serially this never bit, and only because of the alphabet.**  `test_hub`
	sorts before `test_page`, so these always ran first.  Under `pytest-xdist` a
	worker takes whatever it is handed and that accident stops holding — measured
	on 2026-09-08, naming the two files the other way round on one command line
	failed all twelve of these with *Runner.run() cannot be called from a running
	event loop*.  A suite that is 5x faster and occasionally wrong for a reason
	nobody can see is not a bargain.

	A thread of its own has no ambient loop to collide with, so the order stops
	mattering.  The wrapper being a plain ``def`` is the other half of it: that is
	what stops `pytest-asyncio` claiming the test back and running it on the main
	thread after all.
	"""

	@functools.wraps(test)
	def run () -> None:
		"""Drive one coroutine to completion, somewhere with room for it."""

		with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
			pool.submit(asyncio.run, test()).result()

	# `functools.wraps` leaves a `__wrapped__` behind, and anything that unwraps
	# to decide what it is looking at would find the coroutine function again —
	# which is the whole thing being hidden.
	del run.__wrapped__

	return run


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


@_on_a_loop_of_its_own
async def test_a_panel_is_told_what_to_draw_the_moment_it_arrives () -> None:
	"""The manifest carries the declaration and the snapshot the grid itself."""

	hub, _, _ = await _hub_with_app()
	glass = Recorder()

	await hub.panel_joined(superintendent.hub.PanelLink(client="panel-1", send=glass.send))

	manifest = glass.of_kind("manifest")[0]
	snapshot = glass.of_kind("snapshot")[0]

	assert manifest["apps"]["subsequence"]["grid"]["rows"] == ["kick"]
	assert snapshot["state"] == {"grid": {"kick": [0, 4]}}


@_on_a_loop_of_its_own
async def test_a_panel_already_open_learns_when_an_app_arrives () -> None:
	"""Starting the composition second is the ordinary case, not an error."""

	hub = superintendent.hub.Hub(page={"name": "grid"})
	glass = Recorder()

	await hub.panel_joined(superintendent.hub.PanelLink(client="panel-1", send=glass.send))
	await hub.app_declared(superintendent.hub.AppLink(
		name="subsequence", send=Recorder().send, controls=CONTROLS, state={"grid": {}}))

	assert glass.of_kind("manifest")[-1]["apps"]["subsequence"] == CONTROLS
	assert glass.of_kind("app")[-1]["up"] is True


@_on_a_loop_of_its_own
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


@_on_a_loop_of_its_own
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


@_on_a_loop_of_its_own
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


@_on_a_loop_of_its_own
async def test_the_service_keeps_its_own_copy_so_a_late_panel_sees_the_grid () -> None:
	"""A panel arriving after the change is not made to wake the app for it."""

	hub, app, _ = await _hub_with_app()

	await hub.change_reported(app, superintendent.protocol.changed(
		"subsequence", "grid/kick/8", True, 5, by="app"))

	late = Recorder()
	await hub.panel_joined(superintendent.hub.PanelLink(client="panel-2", send=late.send))

	assert late.of_kind("snapshot")[0]["state"]["grid"]["kick"] == [0, 4, 8]


@_on_a_loop_of_its_own
async def test_an_app_going_away_is_shown_on_the_glass () -> None:
	"""A control nobody can reach must not look reachable."""

	hub, app, _ = await _hub_with_app()
	glass = Recorder()

	await hub.panel_joined(superintendent.hub.PanelLink(client="panel-1", send=glass.send))
	await hub.app_left(app)

	assert glass.of_kind("app")[-1] == {"t": "app", "app": "subsequence", "up": False}
	assert glass.of_kind("manifest")[-1]["apps"] == {}


@_on_a_loop_of_its_own
async def test_a_control_that_appears_after_the_app_declared_reaches_an_open_panel () -> None:
	"""Adding a generator on the glass changes what an app offers while it runs.

	The app re-declares on the socket it already has, and every panel is sent a
	fresh manifest.  Nothing about this is new — an arrangement being kept
	re-declares for the same reason — but #2085 makes it load-bearing rather
	than incidental, so it is worth a test that says so.
	"""

	hub, _, _ = await _hub_with_app()
	glass = Recorder()

	await hub.panel_joined(superintendent.hub.PanelLink(client="panel-1", send=glass.send))

	grown = dict(CONTROLS, recipe={"type": "params", "settings": []})

	await hub.app_declared(superintendent.hub.AppLink(
		name="subsequence", send=Recorder().send, controls=grown, state={"grid": {}, "recipe": {}}))

	assert set(glass.of_kind("manifest")[-1]["apps"]["subsequence"]) == {"grid", "recipe"}


@_on_a_loop_of_its_own
async def test_a_control_that_has_gone_stops_being_offered () -> None:
	"""Removing a layer has to take its block with it.

	A re-declaration is the whole truth about what an app offers, not an
	addition to what it offered before.  Without this a generator could be
	taken off a part and go on being drawn.
	"""

	hub, _, _ = await _hub_with_app()
	glass = Recorder()

	await hub.panel_joined(superintendent.hub.PanelLink(client="panel-1", send=glass.send))

	await hub.app_declared(superintendent.hub.AppLink(
		name="subsequence", send=Recorder().send, controls={}, state={}))

	assert glass.of_kind("manifest")[-1]["apps"]["subsequence"] == {}


@_on_a_loop_of_its_own
async def test_a_reconnecting_app_is_not_erased_by_its_own_old_socket () -> None:
	"""The window every restart of a composition opens.

	An app that reconnects declares on its new socket, and the old socket's
	close arrives afterwards — the adapter's client gives up after about ten
	seconds while the service can take minutes of TCP keepalive to notice a
	corpse, so this ordering is the ordinary one rather than a corner.  Removing
	by name took the *live* app away with the dead one, every control greyed out,
	and nothing recovered: the app believes it is connected and will not declare
	again.

	Nothing covered a reconnection at all.  Re-declaring under one name was
	tested; closing the first link afterwards was not, and that is the whole
	defect.
	"""

	hub, first, _ = await _hub_with_app()
	glass = Recorder()

	await hub.panel_joined(superintendent.hub.PanelLink(client="panel-1", send=glass.send))

	# The composition comes back on a socket of its own.
	second = superintendent.hub.AppLink(
		name="subsequence", send=Recorder().send,
		controls=CONTROLS, state={"grid": {"kick": [2]}})

	await hub.app_declared(second)

	# And only now does the service notice the socket that died.
	await hub.app_left(first)

	assert hub.apps.get("subsequence") is second, \
		"the old socket closing took the live app away with it"

	assert glass.of_kind("manifest")[-1]["apps"] != {}, \
		"every control was greyed out while the app was connected"

	assert not [one for one in glass.of_kind("app") if one["up"] is False], \
		"the glass was told the app had gone while it was here"


@_on_a_loop_of_its_own
async def test_an_app_that_really_goes_away_still_goes_away () -> None:
	"""The other half, so the guard above cannot be satisfied by never removing."""

	hub, app, _ = await _hub_with_app()
	glass = Recorder()

	await hub.panel_joined(superintendent.hub.PanelLink(client="panel-1", send=glass.send))
	await hub.app_left(app)

	assert "subsequence" not in hub.apps
	assert glass.of_kind("app")[-1]["up"] is False


@_on_a_loop_of_its_own
async def test_two_panels_reporting_one_name_are_two_registrations () -> None:
	"""A panel is its socket, not its name.

	`PanelLink` compares by identity for this reason: what a socket closing has
	to remove is its own registration, and two browsers may perfectly well
	report the same client string.
	"""

	hub = superintendent.hub.Hub(page={"name": "grid"})

	one = superintendent.hub.PanelLink(client="panel", send=Recorder().send)
	two = superintendent.hub.PanelLink(client="panel", send=Recorder().send)

	await hub.panel_joined(one)
	await hub.panel_joined(two)

	assert len(hub.panels) == 2

	hub.panel_left(one)

	assert hub.panels == [two], "closing one socket removed the wrong registration"


def test_no_test_borrows_the_main_threads_event_loop () -> None:
	"""The rule above, enforced rather than remembered.

	A bare ``async def test_`` passes today and fails under `pytest-xdist` the
	moment a worker happens to run a page test first — which is a failure that
	depends on how work was shared out, so it would arrive looking like flakiness
	rather than like a rule that was broken.

	Checked as text rather than by importing every module, because importing them
	is what a test run does and this has to hold for the ones that have not been
	collected yet.
	"""

	borrowed = []

	for path in sorted(pathlib.Path(__file__).parent.glob("test_*.py")):
		lines = path.read_text(encoding="utf-8").splitlines()

		for number, line in enumerate(lines):
			if not line.startswith("async def test_"):
				continue

			above = lines[number - 1].strip() if number else ""

			if above != "@_on_a_loop_of_its_own":
				borrowed.append(f"{path.name}:{number + 1} {line.split('(')[0]}")

	assert not borrowed, (
		"these run on whatever loop the main thread already has, which is "
		f"Playwright's once a page test has run: {borrowed}. Decorate them with "
		"@_on_a_loop_of_its_own, as the rest of this file does.")
