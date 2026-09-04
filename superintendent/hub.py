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
import typing

import superintendent.controls
import superintendent.protocol


LOG = logging.getLogger(__name__)

Sender = typing.Callable[[superintendent.protocol.Frame], typing.Awaitable[None]]
"""How the hub writes one frame to one socket, whatever is on the other end."""


@dataclasses.dataclass
class AppLink:
	"""One music app, and the state it last told us it holds."""

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


@dataclasses.dataclass
class PanelLink:
	"""One browser on the glass."""

	client: str
	send: Sender


class Hub:
	"""The connected panels and apps, and the routing between them."""

	def __init__ (self, page: dict[str, typing.Any]) -> None:
		"""Start with nothing connected and one page to serve."""

		self.page = page
		self.apps: dict[str, AppLink] = {}
		self.panels: list[PanelLink] = []

	async def panel_joined (self, panel: PanelLink) -> None:
		"""Take a panel's greeting and send it everything it needs to draw.

		The whole state goes out on every connect rather than only when the
		panel's versions are behind.  A grid this size is under a kilobyte, and
		always sending it means there is no comparison that can be wrong.
		"""

		self.panels.append(panel)

		await panel.send(superintendent.protocol.manifest(self._declarations(), self.page, self._pages()))

		for app in self.apps.values():
			await panel.send(superintendent.protocol.snapshot(app.name, app.state, app.version))

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
		"""

		self.apps[app.name] = app

		await self.to_panels(superintendent.protocol.manifest(self._declarations(), self.page, self._pages()))
		await self.to_panels(superintendent.protocol.app_presence(app.name, True))
		await self.to_panels(superintendent.protocol.snapshot(app.name, app.state, app.version))

		LOG.info("app %r declared %d control(s) at version %d", app.name, len(app.controls), app.version)

	async def app_left (self, name: str) -> None:
		"""Forget an app and grey it out on every panel."""

		self.apps.pop(name, None)

		await self.to_panels(superintendent.protocol.manifest(self._declarations(), self.page, self._pages()))
		await self.to_panels(superintendent.protocol.app_presence(name, False))

		LOG.info("app %r disconnected", name)

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
				control: declared if declared.get("type") in superintendent.controls.KINDS
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

	async def to_panels (self, frame: superintendent.protocol.Frame) -> None:
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

	async def arrange_requested (self, panel: PanelLink, frame: superintendent.protocol.Frame) -> None:
		"""Pass a page's arrangement to the app that declared the page.

		Handled exactly as a tap is, and for the same reason: the app is the
		authority.  A page set belongs to the composition that sent it, so the
		composition is what decides whether an arrangement can be kept and where
		it goes.  The service holds no page files and writes nothing (#2075).
		"""

		name = frame.get("app")
		app = self.apps.get(name) if isinstance(name, str) else None

		if app is None:
			await panel.send(superintendent.protocol.nack(
				str(name), str(frame.get("page", "")), panel.client,
				int(frame.get("seq", 0)), f"{name} is not connected"))
			return

		await app.send(frame)

	async def set_requested (self, panel: PanelLink, frame: superintendent.protocol.Frame) -> None:
		"""Pass a panel's tap to the app that owns the control it names.

		Nothing is applied here and nothing is acknowledged here.  The app is
		the authority: it applies the change on its own loop and reports back,
		and that report is what clears the ring under the finger.
		"""

		name = frame.get("app")
		app = self.apps.get(name) if isinstance(name, str) else None

		if app is None:
			await panel.send(superintendent.protocol.nack(
				str(name), str(frame.get("path", "")), panel.client,
				int(frame.get("seq", -1)), f"{name} is not connected"))
			return

		await app.send(superintendent.protocol.set_frame(
			app.name, str(frame.get("path", "")), frame.get("v"), panel.client, int(frame.get("seq", -1))))

	async def change_reported (self, app: AppLink, frame: superintendent.protocol.Frame) -> None:
		"""Record what an app applied, tell every panel, and confirm to the asker.

		The panel that asked gets an ``ack`` as well as the ``changed`` every
		panel gets.  The two carry the same version, so a panel that has both
		can tell its own tap from someone else's.
		"""

		path = str(frame.get("path", ""))
		value = frame.get("v")
		app.version = int(frame.get("ver", app.version + 1))

		try:
			superintendent.controls.apply_change(app.state, app.controls, path, value)

		except superintendent.controls.ControlError:
			LOG.warning("app %r reported a change this service cannot place: %s", app.name, path, exc_info=True)

		client = frame.get("client")
		seq = frame.get("seq")

		await self.to_panels(superintendent.protocol.changed(
			app.name, path, value, app.version,
			by=str(frame.get("by", "app")),
			client=client if isinstance(client, str) else None,
			seq=int(seq) if isinstance(seq, int) else None,
		))

		if isinstance(client, str) and isinstance(seq, int):
			await self.to_panel(client, superintendent.protocol.ack(app.name, client, seq, app.version))

	async def refusal_reported (self, app: AppLink, frame: superintendent.protocol.Frame) -> None:
		"""Pass an app's refusal back to the panel that asked for it.

		An app refuses when it cannot do what was asked — a transport that
		follows an external clock, a tempo outside what it offers. The panel
		that tapped is told, so the control springs back with a reason instead
		of waiting for a confirmation that is never coming.
		"""

		client = frame.get("client")

		if isinstance(client, str):
			await self.to_panel(client, dict(frame, app=app.name))

	async def to_panel (self, client: str, frame: superintendent.protocol.Frame) -> None:
		"""Send one frame to one named panel, if it is still connected."""

		for panel in list(self.panels):
			if panel.client == client:
				await panel.send(frame)
				return

	async def event_reported (self, app: AppLink, frame: superintendent.protocol.Frame) -> None:
		"""Pass on something the app reports that nobody asked for.

		The beat is the one that matters here: it is what the playhead on the
		glass extrapolates between.
		"""

		await self.to_panels(dict(frame, app=app.name))
