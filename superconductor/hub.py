"""What the service holds while it is running, and how a frame finds its way.

The hub is the only place that knows who is connected.  Panels are browsers on
the glass; apps are the music software, each dialled in over a socket of its
own.  A tap travels panel to hub to app; what the app actually applied travels
back to every panel, so no two panels can disagree about a cell.

Nothing here is stored on disk.  The apps are the authority for their own state
and re-declare it whenever they reconnect.
"""

import dataclasses
import logging
import time
import typing

import superconductor.controls
import superconductor.protocol


LOG = logging.getLogger(__name__)

Sender = typing.Callable[[superconductor.protocol.Frame], typing.Awaitable[None]]
"""How the hub writes one frame to one socket, whatever is on the other end."""


@dataclasses.dataclass(eq=False)
class AppLink:
	"""One music app, and the state it last told us it holds.

	**Compared by identity, deliberately, exactly as `PanelLink` is** — and for
	the same reason, which `app_left` has relied on since it was written: two
	links may carry the same name and what has to be removed is *this socket's*
	registration rather than one that merely looks like it.  A generated
	`__eq__` would also make a link unhashable, and #2133 counts open sockets in
	a set.
	"""

	name: str
	send: Sender
	controls: dict[str, typing.Any] = dataclasses.field(default_factory=dict)
	state: dict[str, typing.Any] = dataclasses.field(default_factory=dict)
	version: int = 0
	pages: list[dict[str, typing.Any]] = dataclasses.field(default_factory=list)
	"""The views this app offers over its own controls, in the order it gave them.

	Held and passed on, never interpreted.  A page set belongs to the
	composition that declared it; the service assembles the list and reads no
	file of its own (#2075).
	"""

	since: float = dataclasses.field(default_factory=time.monotonic)
	"""When this link declared itself, for describing what it replaced."""

	connection: object = None
	"""A token standing for the socket this arrived on, compared and never read.

	**A link is rebuilt on every declaration, including a second one down the
	socket already held** — which is how an app says its controls have changed.
	So the object cannot say whether two declarations came from the same place,
	and comparing the objects called an ordinary re-declaration a replacement and
	cried wolf on the common case.  A warning that fires when nothing is wrong
	stops being read, and this one has exactly one job.

	Given by whatever owns the socket.  `None` means nobody said, and then two
	links are only the same if they are the same object.
	"""

	origin: str = "?"
	"""Where this socket came from, kept only so a replacement can be described.

	Not identity and not used as any (#2133).  Two instances on one machine share
	it, and a machine's address can change under a running app.  It is here
	because "app *substation* replaced app *substation*" is a useless sentence
	and "from 192.168.0.31, replacing the one from 192.168.0.30" is not.
	"""


def _socket_of (app: AppLink) -> typing.Any:
	"""Something that stands for one socket and can go in a set.

	The token where there is one, and the link itself where there is not — which
	is the same fallback `app_declared` makes when it decides whether a
	declaration replaced anything.  The two have to agree, or the count of open
	sockets and the decision that one replaced another would disagree about what
	a second connection is.

	**Only a caller that gives no token reaches the fallback**, and the service
	always gives one; it is the tests and any future caller that rely on it.
	Without a token every declaration looks like its own socket, so a
	re-declaration would read as a second connection — which is the cry-wolf
	case `connection` was added to stop.
	"""

	return app.connection if app.connection is not None else app


@dataclasses.dataclass(eq=False)
class PanelLink:
	"""One browser on the glass.

	**Compared by identity, deliberately.** Two panels may report the same
	client name, and what `panel_left` has to remove is *this socket's*
	registration rather than one that merely looks like it.  It happened to work
	before only because the sender is a fresh closure per socket and so no two
	links were ever equal — a property of a different module, holding by
	accident.
	"""

	client: str
	send: Sender


class Hub:
	"""The connected panels and apps, and the routing between them."""

	def __init__ (self, page: dict[str, typing.Any]) -> None:
		"""Start with nothing connected and one page to serve."""

		self.page = page
		self.apps: dict[str, AppLink] = {}
		self.panels: list[PanelLink] = []

		self._sockets: dict[str, dict[typing.Any, AppLink]] = {}
		"""Every open app socket, by the name it declared itself under (#2133).

		**`self.apps` cannot answer this**, because it holds one link per name by
		design — the replacement below is deliberate and stays.  This is the
		other question: *how many connections are using that name right now*, and
		it is what says a second copy is running rather than that one restarted.

		Keyed by the per-socket token rather than by the link, because a link is
		rebuilt on every declaration including a second one down the socket
		already held.  Counting links would call an ordinary re-declaration a
		duplicate.

		The link is kept as the value rather than thrown away, because when the
		registered copy leaves and another is still connected, that one is the
		app now and has to be put back — see `app_left`.
		"""

	async def panel_joined (self, panel: PanelLink) -> None:
		"""Take a panel's greeting and send it everything it needs to draw.

		The whole state goes out on every connect rather than only when the
		panel's versions are behind.  A grid this size is under a kilobyte, and
		always sending it means there is no comparison that can be wrong.
		"""

		self.panels.append(panel)

		await panel.send(superconductor.protocol.manifest(
			self._declarations(), self.page, self._pages(), self.duplicated()))

		for app in self.apps.values():
			await panel.send(superconductor.protocol.snapshot(app.name, app.state, app.version))

		LOG.info("panel %s joined; %d now connected", panel.client, len(self.panels))

	def panel_left (self, panel: PanelLink) -> None:
		"""Forget a panel that has gone away."""

		if panel in self.panels:
			self.panels.remove(panel)

		LOG.info("panel %s left; %d still connected", panel.client, len(self.panels))

	async def app_declared (self, app: AppLink) -> None:
		"""Take an app's declaration and tell every panel it can be reached.

		A re-declaration replaces what went before, because an app that has just
		reconnected is the authority on its own state and may have been restarted
		with a different one.

		**And a second app of the same name replaces the first in exactly the
		same way, which is #2133 and is not fixed here — it is made audible.**

		The two are indistinguishable to this service and the reason is recorded
		one method down, in `app_left`: an app that reconnects declares on its new
		socket *before the old one is noticed to have died*, because the adapter
		gives up after about ten seconds while the service can take minutes of TCP
		keepalive to see a corpse. So "a link for this name already exists" does
		not mean a second instance, and refusing on it would refuse every
		reconnection after a crash for as long as the corpse lingers — which is a
		worse failure than the one being fixed, and a silent one on the app's side.

		Telling them apart needs an identity the app supplies, which is #1916's
		instance name and a contract change. Until then this logs the replacement
		with both origins and how long the incumbent had been there, so the case
		#2133 describes — a second scanner displacing the first, the panel showing
		one, and nothing anywhere saying why — is at least answerable.
		"""

		self._sockets.setdefault(app.name, {})[_socket_of(app)] = app

		standing = self.apps.get(app.name)
		elsewhere = standing is not None and (
			standing.connection is not app.connection if app.connection is not None
			else standing is not app)

		if standing is not None and elsewhere:
			LOG.warning(
				"app %r declared from %s, replacing the one from %s that had been"
				" connected for %.0fs — a reconnection and a second instance of the"
				" same name look alike here (#2133)",
				app.name, app.origin, standing.origin, time.monotonic() - standing.since)

		self.apps[app.name] = app

		await self.to_panels(superconductor.protocol.manifest(
			self._declarations(), self.page, self._pages(), self.duplicated()))
		await self.to_panels(superconductor.protocol.app_presence(app.name, True))
		await self.to_panels(superconductor.protocol.snapshot(app.name, app.state, app.version))

		LOG.info("app %r declared %d control(s) at version %d", app.name, len(app.controls), app.version)

	async def app_left (self, app: AppLink) -> None:
		"""Forget an app and grey it out on every panel.

		**Only if this is still the link that is registered.** An app that
		reconnects declares on its new socket before the old one is noticed to
		have died — the adapter's client gives up after about ten seconds while
		the service can take minutes of TCP keepalive to see a corpse — and
		popping by name then removed the *live* app.  Every control greyed out
		and nothing recovered, because the app believes it is connected and will
		not declare again.  Two copies of a composition running at once did it
		too, which `tools/play_loudly.py` makes easy to do by accident.

		`panel_left` has always compared the object; this is the same rule for
		the other kind of link.
		"""

		# **Forgotten here, above the check, because a socket closing is a socket
		# closing whether or not this link is the one registered** (#2133).  The
		# displaced copy is exactly the one that returns early below, and it is
		# also the one whose closing is the good news: killing a stray second
		# composition is what ends the duplicate, so a panel told about it has to
		# be told when it stops.
		was = self.duplicated()
		open_now = self._sockets.get(app.name)

		if open_now is not None:
			open_now.pop(_socket_of(app), None)

			if not open_now:
				del self._sockets[app.name]

		if self.apps.get(app.name) is not app:
			LOG.debug("app %r closed a socket that had already been replaced", app.name)

			# Nothing about what a panel draws has changed except this, and it
			# has: two copies were connected and now one is.
			if self.duplicated() != was:
				await self.to_panels(superconductor.protocol.manifest(
					self._declarations(), self.page, self._pages(), self.duplicated()))

			return

		del self.apps[app.name]

		# **A copy that is still connected is the app now, and has to be put
		# back** (#2133).  Registering by name and deleting by name means the
		# *other* live copy is stranded the moment the registered one goes: it
		# believes it is connected and will never declare again, so every control
		# greys out and nothing recovers — which is the failure this method's
		# docstring already describes, reached from the other side.
		#
		# It matters because of what the bar now says.  Told that two copies are
		# connected, a person goes and kills one, and half the time that is this
		# one — so without this, the remedy for a duplicate would blank the glass
		# and the composition would play on unreachable.
		#
		# **Promoting a corpse is possible and self-correcting.**  If the
		# survivor is a socket that has died without being noticed, its close
		# brings us back here and the app is removed properly then.  A wrong
		# answer that heals beats a blank panel that does not.
		survivor = self._survivor(app.name)

		if survivor is not None:
			self.apps[app.name] = survivor

			LOG.warning(
				"app %r closed, and another copy from %s is still connected —"
				" it is the app now (#2133)",
				app.name, survivor.origin)

			await self.to_panels(superconductor.protocol.manifest(
				self._declarations(), self.page, self._pages(), self.duplicated()))

			return

		await self.to_panels(superconductor.protocol.manifest(
			self._declarations(), self.page, self._pages(), self.duplicated()))
		await self.to_panels(superconductor.protocol.app_presence(app.name, False))

		LOG.info("app %r disconnected", app.name)

	def duplicated (self) -> dict[str, int]:
		"""Which app names more than one connection is using, and how many.

		**A live fact and not a record of one.**  It becomes true when a second
		connection declares a name that is already taken and false again when
		that connection closes, so killing the stray copy clears it without
		anybody dismissing anything.

		**It does not claim the older connection is healthy.**  A composition
		that crashed leaves a socket the service can take minutes of TCP
		keepalive to notice, so a restart can read as two for a while.  That is
		the honest answer available here — telling the two apart needs a round
		trip nobody has asked for — and it errs towards saying something, which
		is the right way round for a fault whose only remedy is a person.
		"""

		return {name: len(open_now) for name, open_now in sorted(self._sockets.items())
		        if len(open_now) > 1}

	def _survivor (self, name: str) -> AppLink | None:
		"""The most recently declared connection still open under this name."""

		open_now = self._sockets.get(name) or {}

		return max(open_now.values(), key=lambda one: one.since, default=None)

	def _declarations (self) -> dict[str, dict[str, typing.Any]]:
		"""What every connected app says it can be controlled by.

		A control of a kind this service does not know is marked as such rather
		than passed on as though it were fine.  The service is what keeps each
		app's state for panels arriving late, so a kind it cannot place is one
		whose changes it quietly drops — which on the glass looks like a control
		that has stopped responding, with the reason only in a log nobody is
		reading.  Saying so is the difference between a puzzle and a message.
		"""

		return {
			name: {
				control: declared if declared.get("type") in superconductor.controls.KINDS
				else {**declared, "unsupported": declared.get("type")}
				for control, declared in app.controls.items()
			}
			for name, app in sorted(self.apps.items())
		}

	def _pages (self) -> list[dict[str, typing.Any]]:
		"""Every page every connected app declared, each naming its own app.

		In the order the apps declared them, so a composition decides what its
		panel opens on rather than the service deciding by sorting.
		"""

		return [{**page, "app": name}
		        for name, app in sorted(self.apps.items())
		        for page in app.pages]

	async def to_panels (self, frame: superconductor.protocol.Frame) -> None:
		"""Send one frame to every panel, surviving any that has gone quiet.

		A panel whose socket has already failed is dropped rather than allowed
		to hold up the others: the grid on the remaining glass matters more than
		a tidy shutdown of one that has gone.
		"""

		for panel in list(self.panels):
			try:
				await panel.send(frame)

			except Exception:
				LOG.warning("panel %s could not be written to; dropping it", panel.client, exc_info=True)
				self.panel_left(panel)

	async def layout_requested (self, panel: PanelLink, frame: superconductor.protocol.Frame) -> None:
		"""Pass a page's layout to the app that declared the page.

		Handled exactly as a tap is, and for the same reason: the app is the
		authority.  A page set belongs to the composition that sent it, so the
		composition is what decides whether an arrangement can be kept and where
		it goes.  The service holds no page files and writes nothing (#2075).
		"""

		name = frame.get("app")
		app = self.apps.get(name) if isinstance(name, str) else None

		if app is None:
			await panel.send(superconductor.protocol.nack(
				str(name), str(frame.get("page", "")), panel.client,
				superconductor.protocol.whole(frame, "seq", 0), f"{name} is not connected"))
			return

		await app.send(frame)

	async def set_requested (self, panel: PanelLink, frame: superconductor.protocol.Frame) -> None:
		"""Pass a panel's tap to the app that owns the control it names.

		Nothing is applied here and nothing is acknowledged here.  The app is
		the authority: it applies the change on its own loop and reports back,
		and that report is what clears the ring under the finger.
		"""

		name = frame.get("app")
		app = self.apps.get(name) if isinstance(name, str) else None

		if app is None:
			await panel.send(superconductor.protocol.nack(
				str(name), str(frame.get("path", "")), panel.client,
				superconductor.protocol.whole(frame, "seq", -1), f"{name} is not connected"))
			return

		await app.send(superconductor.protocol.set_frame(
			app.name, str(frame.get("path", "")), frame.get("v"), panel.client,
			superconductor.protocol.whole(frame, "seq", -1)))

	async def change_reported (self, app: AppLink, frame: superconductor.protocol.Frame) -> None:
		"""Record what an app applied, tell every panel, and confirm to the asker.

		The panel that asked gets an ``ack`` as well as the ``changed`` every
		panel gets.  The two carry the same version, so a panel that has both
		can tell its own tap from someone else's.
		"""

		path = str(frame.get("path", ""))
		value = frame.get("v")
		app.version = superconductor.protocol.whole(frame, "ver", app.version + 1)

		try:
			superconductor.controls.apply_change(app.state, app.controls, path, value)

		except superconductor.controls.ControlError:
			LOG.warning("app %r reported a change this service cannot place: %s", app.name, path, exc_info=True)

		client = frame.get("client")
		seq = frame.get("seq")

		await self.to_panels(superconductor.protocol.changed(
			app.name, path, value, app.version,
			by=str(frame.get("by", "app")),
			client=client if isinstance(client, str) else None,
			seq=int(seq) if isinstance(seq, int) else None,
		))

		if isinstance(client, str) and isinstance(seq, int):
			await self.to_panel(client, superconductor.protocol.ack(app.name, client, seq, app.version))

	async def refusal_reported (self, app: AppLink, frame: superconductor.protocol.Frame) -> None:
		"""Pass an app's refusal back to the panel that asked for it.

		An app refuses when it cannot do what was asked — a transport that
		follows an external clock, a tempo outside what it offers. The panel
		that tapped is told, so the control springs back with a reason instead
		of waiting for a confirmation that is never coming.
		"""

		client = frame.get("client")

		if isinstance(client, str):
			await self.to_panel(client, dict(frame, app=app.name))

	async def to_panel (self, client: str, frame: superconductor.protocol.Frame) -> None:
		"""Send one frame to one named panel, if it is still connected."""

		for panel in list(self.panels):
			if panel.client == client:
				await panel.send(frame)
				return

	async def event_reported (self, app: AppLink, frame: superconductor.protocol.Frame) -> None:
		"""Pass on something the app reports that nobody asked for.

		The beat is the one that matters here: it is what the playhead on the
		glass extrapolates between.
		"""

		await self.to_panels(dict(frame, app=app.name))
