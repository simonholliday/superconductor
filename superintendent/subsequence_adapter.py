"""The Subsequence side of the link: what a composition adds to be playable.

A composition creates one :class:`GridLink`, hands it the grid it keeps in
``composition.data`` and the names of its rows, and starts it.  From then on a
tap on the glass reaches that dict, and anything the composition itself does to
the dict reaches the glass.

**No part of the Subsequence package is changed**, and none of it needs to be.
The link reaches the composition's clock loop through ``composition.on_event``,
which is public: a callback registered there runs *on* that loop, so the first
beat is where the link learns which loop to hand later taps to.  Subroutine
#2046 fixes the no-package-change rule and #1963 carries what a future version
might expose instead.

The rows are named by whoever builds the link.  This module never learns what a
row is for, which is the rule in this project's CLAUDE.md.

Where this module finally lives — here, or shared between the three apps — is
Subroutine #1972 and is still open.
"""

import asyncio
import collections.abc
import logging
import threading
import time
import typing

import websockets.asyncio.client
import websockets.exceptions

import superintendent.protocol


LOG = logging.getLogger(__name__)

DEFAULT_URL = "ws://127.0.0.1:8090/ws/app"
"""The service on this machine.  A different one is a constructor argument."""

RECONNECT_FLOOR = 0.25
RECONNECT_CEILING = 5.0
"""Seconds between attempts to dial the service, backing off to the ceiling."""


class GridLink:
	"""One step grid, offered to the panel and written back on the clock loop."""

	def __init__ (
		self,
		composition: typing.Any,
		rows: collections.abc.Sequence[str],
		steps: int = 16,
		beats: int = 4,
		data_key: str = "grid",
		control: str = "grid",
		app_name: str = "subsequence",
		url: str = DEFAULT_URL,
	) -> None:
		"""Describe the grid to offer, without connecting anything yet."""

		self.composition = composition
		self.rows = list(rows)
		self.steps = steps
		self.beats = beats
		self.data_key = data_key
		self.control = control
		self.app_name = app_name
		self.url = url

		self.version = 0

		self._clock_loop: asyncio.AbstractEventLoop | None = None
		self._link_loop: asyncio.AbstractEventLoop | None = None
		self._socket: typing.Any = None
		self._thread: threading.Thread | None = None
		self._stopping = threading.Event()
		self._last_beat_at: float | None = None

	def start (self) -> None:
		"""Begin listening to the clock and dialling the service.

		Safe to call before the composition plays: the link simply waits, and
		the panel shows the app as absent until it answers.
		"""

		self.composition.on_event("beat", self._on_beat)

		self._thread = threading.Thread(target=self._run_link, name="superintendent-link", daemon=True)
		self._thread.start()

		LOG.info("Superintendent link started; dialling %s", self.url)

	def stop (self) -> None:
		"""Stop dialling and let the link thread finish."""

		self._stopping.set()

		if self._link_loop is not None:
			self._link_loop.call_soon_threadsafe(self._link_loop.stop)

	# ------------------------------------------------------------------
	# On the composition's clock loop
	# ------------------------------------------------------------------

	def _on_beat (self, beat: int) -> None:
		"""Note the beat and pass it on, so the playhead has something to follow.

		This runs on the clock loop, which is the point: the first call is how
		the link learns which loop to hand taps to, without reaching for any
		private name.
		"""

		if self._clock_loop is None:
			self._clock_loop = asyncio.get_running_loop()
			LOG.debug("clock loop captured from the first beat")

		now = time.monotonic()
		interval = None if self._last_beat_at is None else now - self._last_beat_at
		self._last_beat_at = now

		self._emit(superintendent.protocol.event(
			self.app_name, "beat", beat=beat, ts=now, interval=interval,
			steps=self.steps, beats=self.beats))

	def _apply (self, path: str, value: typing.Any, client: str, seq: int) -> None:
		"""Write one cell, on the clock loop, and report what was written.

		Absolute rather than a toggle, so re-sending it after a reconnect
		reaches the same grid as sending it once.  The later hand wins, which
		for an instrument is the only rule that makes sense.
		"""

		try:
			control, row, step = _split(path)

		except ValueError:
			LOG.warning("panel asked for %r, which does not name a cell", path)
			return

		if control != self.control or row not in self.rows or not 0 <= step < self.steps:
			LOG.warning("panel asked for %r, which is outside this grid", path)
			return

		grid = self.composition.data.setdefault(self.data_key, {})
		steps = grid.setdefault(row, [])

		if value and step not in steps:
			steps.append(step)
			steps.sort()

		elif not value and step in steps:
			steps.remove(step)

		self.version += 1

		self._emit(superintendent.protocol.changed(
			self.app_name, path, bool(value), self.version, by="panel", client=client, seq=seq))

	def _emit (self, frame: superintendent.protocol.Frame) -> None:
		"""Hand a frame to the link thread, in the order it was produced.

		Called on the clock loop and never blocking there: the send itself
		happens on the link thread, so a slow socket cannot delay a pulse.
		"""

		loop = self._link_loop
		socket = self._socket

		if loop is None or socket is None:
			return

		asyncio.run_coroutine_threadsafe(self._send(frame), loop)

	# ------------------------------------------------------------------
	# On the link thread
	# ------------------------------------------------------------------

	def _run_link (self) -> None:
		"""Own an event loop on this thread and keep the service dialled."""

		self._link_loop = asyncio.new_event_loop()
		asyncio.set_event_loop(self._link_loop)

		try:
			self._link_loop.run_until_complete(self._dial_forever())

		finally:
			self._link_loop.close()

	async def _dial_forever (self) -> None:
		"""Connect, serve, and reconnect for as long as the composition runs."""

		delay = RECONNECT_FLOOR

		while not self._stopping.is_set():
			try:
				async with websockets.asyncio.client.connect(self.url, ping_interval=5, ping_timeout=5) as socket:
					self._socket = socket
					delay = RECONNECT_FLOOR

					LOG.info("connected to Superintendent at %s", self.url)

					await self._declare()
					await self._serve(socket)

			except (OSError, websockets.exceptions.WebSocketException) as error:
				LOG.debug("Superintendent not reachable (%s); retrying in %.2fs", error, delay)

			finally:
				self._socket = None

			await asyncio.sleep(delay)
			delay = min(delay * 2, RECONNECT_CEILING)

	async def _declare (self) -> None:
		"""Say what this app offers and what it currently holds."""

		controls = {self.control: {
			"type": "step_grid", "rows": self.rows, "steps": self.steps, "beats": self.beats}}

		await self._send(superintendent.protocol.declare(
			self.app_name, controls, {self.control: self._snapshot()}, self.version))

	def _snapshot (self) -> dict[str, list[int]]:
		"""The grid as it stands, one row at a time.

		Read off the clock loop's dict without crossing onto it: a list that is
		being sorted at this instant is the only hazard, and copying under the
		GIL is enough against it.
		"""

		grid = self.composition.data.get(self.data_key) or {}

		return {row: sorted(grid.get(row, [])) for row in self.rows}

	async def _serve (self, socket: typing.Any) -> None:
		"""Carry what the service sends until the socket closes."""

		async for raw in socket:
			try:
				frame = superintendent.protocol.decode(raw)

			except superintendent.protocol.ProtocolError:
				LOG.warning("service sent a frame that could not be read", exc_info=True)
				continue

			if frame["t"] == "set":
				self._cross(frame)

	def _cross (self, frame: superintendent.protocol.Frame) -> None:
		"""Hand one tap to the clock loop, which is the only place it may land.

		This is the crossing Subroutine #2046 chose: one per message, no
		batching, measured at about a millisecond at p99 (#1926, #2043).
		"""

		loop = self._clock_loop

		if loop is None:
			LOG.warning("a tap arrived before the first beat; nothing to write to yet")
			return

		loop.call_soon_threadsafe(
			self._apply,
			str(frame.get("path", "")),
			frame.get("v"),
			str(frame.get("client", "")),
			int(frame.get("seq", -1)),
		)

	async def _send (self, frame: superintendent.protocol.Frame) -> None:
		"""Write one frame, forgiving a socket that has closed underneath it."""

		socket = self._socket

		if socket is None:
			return

		try:
			await socket.send(superintendent.protocol.encode(frame))

		except websockets.exceptions.WebSocketException:
			LOG.debug("frame dropped: the service went away mid-send")


def _split (path: str) -> tuple[str, str, int]:
	"""Split ``control/row/step`` into its three parts."""

	control, _, rest = path.partition("/")
	row, _, step = rest.rpartition("/")

	if not control or not row or not step.isdigit():
		raise ValueError(path)

	return control, row, int(step)
