"""The web service: one page, one socket to the glass, one socket per app.

Everything reaches the panel from here and nothing else is exposed.  The page,
its scripts and both sockets share one origin, so the browser needs no
cross-origin permission and the service is the only thing on the network that
has to be reachable.

The apps dial in rather than being dialled, which is why the service can be
started and stopped without the music software noticing anything but a
reconnect.
"""

import logging
import pathlib
import typing

import starlette.applications
import starlette.requests
import starlette.responses
import starlette.routing
import starlette.staticfiles
import starlette.websockets

import superintendent.build
import superintendent.config
import superintendent.hub
import superintendent.protocol


LOG = logging.getLogger(__name__)

CLIENT_DIR = pathlib.Path(__file__).resolve().parent / "client"
"""The page and its scripts, which ship inside the package.

They live here rather than beside it so that an installed copy has a page to
serve: a wheel carries what is inside the package and nothing else, and a
service with no page is not a service.
"""


def build (config: superintendent.config.Config) -> starlette.applications.Starlette:
	"""Assemble the service: the page, the static files and the two sockets."""

	hub = superintendent.hub.Hub(page={"name": config.page})

	async def index (request: starlette.requests.Request) -> starlette.responses.Response:
		"""Serve the page itself, with its assets stamped by the build they are.

		Two decisions about caching live here, and they are deliberate (#2056).
		The page is never stored: it is a few hundred bytes whose only job is to
		name the files that matter, so caching it saves nothing and can only
		make it lie about them. Those files keep a content hash in their URL, so
		a browser holding an old copy cannot serve it in place of a new one —
		the URL it was cached under no longer exists.
		"""

		page = CLIENT_DIR / "index.html"

		if not page.exists():
			return starlette.responses.PlainTextResponse(f"No page to serve: {page} is missing.", status_code=500)

		markup = page.read_text(encoding="utf-8")
		build = superintendent.build.client_build(CLIENT_DIR)

		if build is not None:
			for asset in ("/client/style.css", "/client/app.js"):
				markup = markup.replace(f'"{asset}"', f'"{asset}?v={build}"')

		return starlette.responses.HTMLResponse(markup, headers={"Cache-Control": "no-store"})

	async def panel_socket (websocket: starlette.websockets.WebSocket) -> None:
		"""Hold one browser's socket for as long as the browser is there."""

		await websocket.accept()
		await _serve_panel(hub, websocket)

	async def app_socket (websocket: starlette.websockets.WebSocket) -> None:
		"""Hold one music app's socket for as long as the app is there."""

		await websocket.accept()
		await _serve_app(hub, websocket)

	routes: list[starlette.routing.BaseRoute] = [
		starlette.routing.Route("/", index),
		starlette.routing.WebSocketRoute("/ws/panel", panel_socket),
		starlette.routing.WebSocketRoute("/ws/app", app_socket),
	]

	if CLIENT_DIR.exists():
		routes.append(starlette.routing.Mount(
			"/client", starlette.staticfiles.StaticFiles(directory=CLIENT_DIR), name="client"))

	app = starlette.applications.Starlette(routes=routes)
	app.state.hub = hub

	return app


def _note_contract (side: str, who: str, frame: superintendent.protocol.Frame) -> None:
	"""Say so when something dials in speaking a different contract (#2164).

	**It is said and not acted on, deliberately.** Refusing an old panel is
	wrong: the panel is the thing a person is standing in front of, and a blank
	screen because the service moved on is worse than a slightly stale one. The
	service already has the better pattern for this — a control of a kind it does
	not know is marked ``unsupported`` and drawn saying so rather than dropped.

	So this is the log half, and the panel says it on the glass for itself: the
	service sends its own version in the greeting and the panel compares it. That
	split is not tidiness. A panel newer than the service is the case that costs
	a session here, and the service is by definition too old to have been taught
	to report it — so the only half that can catch it is the half that is new.

	An app has no glass of its own, which is why this is the whole of the check
	on that side. It matters at least as much: an app declaring a control kind
	the service does not know has every change to it dropped while the frame is
	still forwarded, and on the glass that is a button that will not move with
	the reason in a log nobody is reading.
	"""

	gap = superintendent.protocol.contract_gap(frame.get("contract"))

	if gap is None:
		return

	spoken = frame.get("contract")
	ours = superintendent.protocol.CONTRACT_VERSION

	if gap == "major":
		LOG.error("%s %r speaks contract %r against this service's %r; a frame either"
		          " end already knows may have changed shape", side, who, spoken, ours)
	elif gap == "unreadable":
		LOG.error("%s %r named no readable contract version (%r)", side, who, spoken)
	else:
		LOG.warning("%s %r is %s than this service: contract %r against %r",
		            side, who, gap, spoken, ours)


async def _serve_panel (hub: superintendent.hub.Hub, websocket: starlette.websockets.WebSocket) -> None:
	"""Greet one panel, then carry its frames until it goes away."""

	panel: superintendent.hub.PanelLink | None = None

	try:
		while True:
			frame = superintendent.protocol.decode(await websocket.receive_text())
			kind = frame["t"]

			if kind == "hello":
				# **A hello on a socket that has already said one is a resync,
				# not a second panel.** The client re-sends it on waking,
				# because a hidden tab's timers are throttled to once a minute
				# and it cannot be left to notice by itself. Every one of those
				# built another link and appended it, and nothing took the
				# previous one away: after N wakes every frame — every change,
				# every manifest, every beat, every realised cycle twice a
				# second — went down the one socket N+1 times, growing for the
				# life of the connection and completely silent, because the
				# frames are idempotent and the page stays correct while the
				# wire and the render loop degrade.
				if panel is not None:
					hub.panel_left(panel)

				_note_contract("panel", str(frame.get("client", "panel")), frame)

				panel = superintendent.hub.PanelLink(
					client=str(frame.get("client", "panel")), send=_sender(websocket))

				# Said before anything else, and said again on every hello, so a
				# panel that reconnects to a restarted service learns at once
				# whether the page it is still running has been left behind.
				await panel.send(superintendent.protocol.service(
					superintendent.build.version(),
					superintendent.build.client_build(CLIENT_DIR)))

				await hub.panel_joined(panel)

			elif panel is None:
				LOG.warning("panel sent %r before saying hello; closing", kind)
				break

			elif kind == "set":
				await hub.set_requested(panel, frame)

			elif kind == "layout":
				await hub.layout_requested(panel, frame)

			elif kind == "ping":
				await panel.send(superintendent.protocol.pong(
					superintendent.protocol.number(frame, "ts", 0.0)))

			else:
				LOG.debug("panel %s sent %r, which this version ignores", panel.client, kind)

	except starlette.websockets.WebSocketDisconnect:
		LOG.debug("panel socket closed")

	except superintendent.protocol.ProtocolError:
		LOG.warning("panel sent a frame that could not be read; closing", exc_info=True)

	finally:
		if panel is not None:
			hub.panel_left(panel)


async def _serve_app (hub: superintendent.hub.Hub, websocket: starlette.websockets.WebSocket) -> None:
	"""Take one app's declaration, then carry what it reports until it goes."""

	app: superintendent.hub.AppLink | None = None

	try:
		while True:
			frame = superintendent.protocol.decode(await websocket.receive_text())
			kind = frame["t"]

			if kind == "declare":
				_note_contract("app", str(frame.get("app", "app")), frame)

				app = superintendent.hub.AppLink(
					name=str(frame.get("app", "app")),
					send=_sender(websocket),
					controls=dict(frame.get("controls") or {}),
					state=dict(frame.get("state") or {}),
					version=superintendent.protocol.whole(frame, "ver", 0),
					pages=list(frame.get("pages") or []),
				)
				await hub.app_declared(app)

			elif app is None:
				LOG.warning("app sent %r before declaring itself; closing", kind)
				break

			elif kind == "changed":
				await hub.change_reported(app, frame)

			elif kind == "event":
				await hub.event_reported(app, frame)

			elif kind == "nack":
				await hub.refusal_reported(app, frame)

			else:
				LOG.debug("app %r sent %r, which this version ignores", app.name, kind)

	except starlette.websockets.WebSocketDisconnect:
		LOG.debug("app socket closed")

	except superintendent.protocol.ProtocolError:
		LOG.warning("app sent a frame that could not be read; closing", exc_info=True)

	finally:
		if app is not None:
			await hub.app_left(app)


def _sender (websocket: starlette.websockets.WebSocket) -> superintendent.hub.Sender:
	"""Give the hub one way to write to this socket, knowing nothing else about it."""

	async def send (frame: superintendent.protocol.Frame) -> None:
		"""Write one frame."""

		await websocket.send_text(superintendent.protocol.encode(frame))

	return typing.cast(superintendent.hub.Sender, send)
