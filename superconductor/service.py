"""The web service: one page, one socket to the glass, one socket per app.

Everything reaches the panel from here and nothing else is exposed.  The page,
its scripts and both sockets share one origin, so the browser needs no
cross-origin permission and the service is the only thing on the network that
has to be reachable.

The apps dial in rather than being dialled, which is why the service can be
started and stopped without the music software noticing anything but a
reconnect.
"""

import asyncio
import logging
import pathlib
import typing

import starlette.applications
import starlette.requests
import starlette.responses
import starlette.routing
import starlette.staticfiles
import starlette.websockets

import superconductor.build
import superconductor.config
import superconductor.hub
import superconductor.protocol


LOG = logging.getLogger(__name__)

LOADED_BUILD = superconductor.build.package_build()
"""The package this service is running, hashed as this module is imported.

The counterpart to the adapter's constant of the same name, and it answers the
same question about this half: *what did this process load*.  Taken here, once,
on the main thread at start-up — which is the only place this package may read a
disk it does not have to, because every other place is a socket handler on the
event loop and this working tree is a CIFS mount that hangs.
"""

LOADED_VERSION = superconductor.build.version()
"""Which release this process is, read as this module is imported.

Constant for the life of an interpreter by the question's own definition — a
version describes what was *installed*, not what is on disk — so asking again
per hello buys nothing and puts a second blocking read on the event loop beside
the one #2422 was filed about.
"""

CLIENT_DIR = pathlib.Path(__file__).resolve().parent / "client"
"""The page and its scripts, which ship inside the package.

They live here rather than beside it so that an installed copy has a page to
serve: a wheel carries what is inside the package and nothing else, and a
service with no page is not a service.
"""


class _ClientBuild:
	"""What serving the page last stamped the client's assets with (#2422).

	**A panel's socket reports this and reads no disk to do it.**  Hashing the
	client is `read_bytes` over every file the page is made of — 6 ms warm,
	measured — and the `hello` branch used to do it on the event loop that serves
	the glass.  On 2026-09-10 that happened: a stalled CIFS read left the
	service's main thread in `netfs_start_io_read`, the control surface went off
	the air — no panel, no taps — and the composition went on playing, which is
	the worst shape available: the rig sounds alive and the glass is dead.  **A
	read that can stop the thing it is serving is not a cost, it is a hazard**,
	which is the sentence `package_build` was weakened under, applied to the half
	it was not applied to.

	**Nothing here is read that was not read anyway.**  Serving the page hashes
	the client already, because the stamp on `/client/app.js?v=…` is that same
	hash; this keeps the answer instead of throwing it away.

	**And the answer is refreshed rather than frozen, because the page's stamp
	and this must be allowed to differ** — that difference *is* how a panel
	learns it is behind (#2164).  The page compares the `?v=` it was fetched
	under against what it is told here, so a value that could only ever equal
	that stamp would make "newer page available" unreachable.  A hello asks for a
	re-read; the re-read happens **off the loop**; a panel is told if it moved.

	**Hashing once at import was the other candidate** and fails the same test,
	with a second fault on top: the hash is also the cache-buster, so a frozen
	one would let a browser answer a reload out of its own cache and destroy the
	property this project leans on — a reload always gets new JavaScript.
	"""

	def __init__ (self) -> None:
		self.told: str | None = None
		"""The answer a panel is given, and the only thing a socket handler reads.

		None until a page has been served in this process — a panel that
		reconnected without reloading, because the service restarted and the
		browser did not.  **Silence rather than a guess**: the bar says nothing
		about a build, and the refresh below fills it a moment later.
		"""

		self._reading: asyncio.Task[None] | None = None
		"""The re-read in flight, if there is one.

		**At most one, ever**, and that is what bounds the damage a stalled mount
		can do: a panel on a reconnect backoff would otherwise start one per
		attempt and exhaust the default executor — which is the same pool that
		serves the page and the static files, so the glass would go down by
		another route.  A read that never returns leaves this pending for the
		life of the process and nothing is asked again, which is the right answer
		when the mount is what is broken.
		"""

	def stamp (self, build: str | None) -> None:
		"""Keep what serving the page has just worked out."""

		self.told = build

	def refresh (self, hub: superconductor.hub.Hub) -> None:
		"""Ask, off the loop, whether the client has changed under this service.

		**Returns at once and nothing awaits the answer**, so a greeting is never
		held up by the disk.  Whoever provoked it is not told; every panel is, and
		only if there is something to say.
		"""

		if self._reading is not None and not self._reading.done():
			return

		self._reading = asyncio.ensure_future(self._reread(hub))

	async def _reread (self, hub: superconductor.hub.Hub) -> None:
		"""Re-read the client on a worker thread, and say so if it moved."""

		try:
			found = await asyncio.get_running_loop().run_in_executor(
				None, superconductor.build.client_build, CLIENT_DIR)

		except OSError:
			LOG.warning("could not re-read the client to see whether it had changed",
			            exc_info=True)
			return

		if found is None or found == self.told:
			return

		LOG.info("the client changed under this service: %s is now %s", self.told, found)
		self.told = found

		# **Said to every panel rather than to whichever one provoked the read.**
		# What changed is the client, and each panel is running a copy of it — so
		# a panel that happened not to say hello just then is exactly as stale as
		# the one that did.
		await hub.to_panels(superconductor.protocol.service(LOADED_VERSION, found))


def build (config: superconductor.config.Config) -> starlette.applications.Starlette:
	"""Assemble the service: the page, the static files and the two sockets."""

	hub = superconductor.hub.Hub(page={"name": config.page})

	stamped = _ClientBuild()

	def index (request: starlette.requests.Request) -> starlette.responses.Response:
		"""Serve the page itself, with its assets stamped by the build they are.

		Two decisions about caching live here, and they are deliberate (#2056).
		The page is never stored: it is a few hundred bytes whose only job is to
		name the files that matter, so caching it saves nothing and can only
		make it lie about them. Those files keep a content hash in their URL, so
		a browser holding an old copy cannot serve it in place of a new one —
		the URL it was cached under no longer exists.

		**Deliberately not `async`** (#2422).  Starlette runs a coroutine
		endpoint on the event loop and a plain one in a threadpool, and this
		reads three times off a mount that can stall — `exists`, `read_text` and
		the client hash.  Written `async def` it is the same hazard the socket
		was just relieved of, arriving by the other door: a person whose glass
		looks wrong reloads the page, which is precisely when the read would be
		on the loop.
		"""

		page = CLIENT_DIR / "index.html"

		if not page.exists():
			return starlette.responses.PlainTextResponse(f"No page to serve: {page} is missing.", status_code=500)

		markup = page.read_text(encoding="utf-8")
		build = superconductor.build.client_build(CLIENT_DIR)

		stamped.stamp(build)

		if build is not None:
			for asset in ("/client/style.css", "/client/app.js"):
				markup = markup.replace(f'"{asset}"', f'"{asset}?v={build}"')

		return starlette.responses.HTMLResponse(markup, headers={"Cache-Control": "no-store"})

	async def panel_socket (websocket: starlette.websockets.WebSocket) -> None:
		"""Hold one browser's socket for as long as the browser is there."""

		await websocket.accept()
		await _serve_panel(hub, websocket, stamped)

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


def _origin (websocket: starlette.websockets.WebSocket) -> str:
	"""Where a socket dialled in from, as a string fit for a log line.

	Best effort by design: a test client has no address at all, and a proxy in
	front would report itself. It is never identity (#2133) — only what makes a
	replacement describable instead of merely announced.
	"""

	client = websocket.client

	return f"{client.host}:{client.port}" if client else "an unnamed socket"


def _note_contract (side: str, who: str, frame: superconductor.protocol.Frame) -> None:
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

	gap = superconductor.protocol.contract_gap(frame.get("contract"))

	if gap is None:
		return

	spoken = frame.get("contract")
	ours = superconductor.protocol.CONTRACT_VERSION

	if gap == "major":
		LOG.error("%s %r speaks contract %r against this service's %r; a frame either"
		          " end already knows may have changed shape", side, who, spoken, ours)
	elif gap == "unreadable":
		LOG.error("%s %r named no readable contract version (%r)", side, who, spoken)
	else:
		LOG.warning("%s %r is %s than this service: contract %r against %r",
		            side, who, gap, spoken, ours)


def _note_builds (who: str, spoken: object) -> None:
	"""Say so when an app and this service are not running the same code (#2220).

	Both halves hash the package **as they import it** and neither ever reads the
	disk again.  So this compares *what that process loaded* with *what this one
	loaded*, and the two differing means one of them started before a change —
	which is the staleness a contract version cannot see, because a fix inside an
	adapter moves no frame and both ends go on agreeing about the wire while one
	of them executes yesterday's Python.  That cost a round trip on 2026-09-07,
	an hour after the contract check was built to prevent the same class of thing.

	**Comparing against what is on disk *now* would be the better question and is
	not worth what it costs.**  It would name which half is behind rather than
	only that they differ.  It also means reading eleven files inside the socket
	handler, and this working tree is a CIFS mount with a live kernel bug in it:
	the suite deadlocked outright the first time this was written that way, and on
	a rig the same read would stop the whole service — no panel, no taps — on a
	filesystem that has already hung this machine twice.  A check that can take
	the thing it is checking off the air is not a check.  So it asks a slightly
	weaker question for free, and never touches a disk on a socket.

	**Said as two facts and not as a verdict**, because the same difference means
	two things and only the reader knows which.  Where the two share a filesystem
	it means one of them wants restarting.  Where they do not — an app on another
	host, which the service is bound to every interface to allow — it means the
	halves were installed from different sources, which is worth knowing and is
	not a fault (#2049).  Naming either setup unsupported would be this package
	deciding how somebody's studio is wired.

	An app too old to send a build says nothing, and nothing is checked.
	"""

	if not isinstance(spoken, str) or not spoken:
		return

	if LOADED_BUILD is None or spoken == LOADED_BUILD:
		return

	LOG.warning("app %r loaded superconductor build %r and this service loaded"
	            " %r — the two are not running the same code, so on a shared"
	            " filesystem one of them was started before a change and wants"
	            " restarting", who, spoken, LOADED_BUILD)


async def _serve_panel (
	hub: superconductor.hub.Hub,
	websocket: starlette.websockets.WebSocket,
	stamped: _ClientBuild,
) -> None:
	"""Greet one panel, then carry its frames until it goes away."""

	panel: superconductor.hub.PanelLink | None = None

	try:
		while True:
			frame = superconductor.protocol.decode(await websocket.receive_text())
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

				panel = superconductor.hub.PanelLink(
					client=str(frame.get("client", "panel")), send=_sender(websocket))

				# Said before anything else, and said again on every hello, so a
				# panel that reconnects to a restarted service learns at once
				# whether the page it is still running has been left behind.
				await panel.send(superconductor.protocol.service(
					LOADED_VERSION, stamped.told))

				await hub.panel_joined(panel)

				# **Asked for after the greeting and never awaited** (#2422).
				# This is the one thing here that reads the client, it happens on
				# a worker thread, and a panel that is behind is told when it
				# lands rather than being kept waiting to be greeted.
				stamped.refresh(hub)

			elif panel is None:
				LOG.warning("panel sent %r before saying hello; closing", kind)
				break

			elif kind == "set":
				await hub.set_requested(panel, frame)

			elif kind == "layout":
				await hub.layout_requested(panel, frame)

			elif kind == "ping":
				await panel.send(superconductor.protocol.pong(
					superconductor.protocol.number(frame, "ts", 0.0)))

			else:
				LOG.debug("panel %s sent %r, which this version ignores", panel.client, kind)

	except starlette.websockets.WebSocketDisconnect:
		LOG.debug("panel socket closed")

	except superconductor.protocol.ProtocolError:
		LOG.warning("panel sent a frame that could not be read; closing", exc_info=True)

	finally:
		if panel is not None:
			hub.panel_left(panel)


async def _serve_app (hub: superconductor.hub.Hub, websocket: starlette.websockets.WebSocket) -> None:
	"""Take one app's declaration, then carry what it reports until it goes."""

	app: superconductor.hub.AppLink | None = None

	# One token for the life of this socket, so a second declaration down the
	# *same* socket — which is how an app says its controls have changed — is not
	# mistaken for a second app of the same name (#2133).
	connection = object()

	try:
		while True:
			frame = superconductor.protocol.decode(await websocket.receive_text())
			kind = frame["t"]

			if kind == "declare":
				_note_contract("app", str(frame.get("app", "app")), frame)

				# **Only on the first declaration down this socket.** A second
				# one is how an app says its controls changed, and that happens
				# every time somebody drags a block: a layout save re-declares so
				# the other panels learn the arrangement. The build it carries is
				# a constant taken as that process started, so checking it again
				# could only repeat the same line once a drag.
				if app is None:
					_note_builds(str(frame.get("app", "app")), frame.get("build"))

				app = superconductor.hub.AppLink(
					name=str(frame.get("app", "app")),
					send=_sender(websocket),
					controls=dict(frame.get("controls") or {}),
					state=dict(frame.get("state") or {}),
					version=superconductor.protocol.whole(frame, "ver", 0),
					pages=list(frame.get("pages") or []),
					origin=_origin(websocket),
					connection=connection,
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

			elif kind == "ack":
				await hub.settled_reported(app, frame)

			else:
				LOG.debug("app %r sent %r, which this version ignores", app.name, kind)

	except starlette.websockets.WebSocketDisconnect:
		LOG.debug("app socket closed")

	except superconductor.protocol.ProtocolError:
		LOG.warning("app sent a frame that could not be read; closing", exc_info=True)

	finally:
		if app is not None:
			await hub.app_left(app)


def _sender (websocket: starlette.websockets.WebSocket) -> superconductor.hub.Sender:
	"""Give the hub one way to write to this socket, knowing nothing else about it."""

	async def send (frame: superconductor.protocol.Frame) -> None:
		"""Write one frame."""

		await websocket.send_text(superconductor.protocol.encode(frame))

	return typing.cast(superconductor.hub.Sender, send)
