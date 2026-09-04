"""The Subsequence side of the link: what a composition adds to be playable.

A composition builds an :class:`AppLink`, gives it the controls it wants to
offer — a :class:`StepGrid` over a dict it keeps, a :class:`Transport` over its
own playback — and starts it.  From then on a tap on the glass reaches the
composition, and what the composition does reaches the glass.

**No part of the Subsequence package is changed**, and none of it needs to be.
The link reaches the composition's clock loop through ``composition.on_event``,
which is public: a callback registered there runs *on* that loop, so the first
beat is where the link learns which loop to hand later taps to.  Subroutine
#2046 fixes the no-package-change rule and #1963 carries what a future version
might expose instead.

What a control is *for* is never known here.  A grid's rows are names whoever
built it chose, which is the rule in this project's CLAUDE.md.

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


class Refused (Exception):
	"""A request the app will not carry out, carrying why so a panel can say so.

	Distinct from a request that changes nothing: refusing means the panel
	asked for something this app cannot do, and the person who tapped should
	be told rather than left watching a control that never moves.
	"""



class Control:
	"""One thing a panel can see and work, offered under a name."""

	name: str

	title: str | None = None
	"""What to call this on the glass, if not the name it is addressed by.

	The app names its own parts and the panel repeats them (#2071).  Nothing in
	Superintendent knows that a row called ``kick`` is a drum or that a grid is
	a pattern for one, so a title is the composition's to give: it is the same
	rule as the row names, and the same reason.
	"""

	def declaration (self) -> dict[str, typing.Any]:
		"""What a panel needs in order to draw this."""

		raise NotImplementedError

	def snapshot (self) -> typing.Any:
		"""What this control holds at the moment."""

		raise NotImplementedError

	def apply (self, rest: list[str], value: typing.Any) -> bool:
		"""Take a request, on the clock loop, and say whether anything changed."""

		raise NotImplementedError

	def poll (self) -> list[tuple[str, typing.Any]]:
		"""Anything that changed without the panel asking, as path and value.

		Called on the clock loop once a beat.  It is how a control follows the
		composition's own hand — a tempo ramp, say — rather than only the
		panel's.
		"""

		return []

	def attach (self, link: "AppLink") -> None:
		"""Take the link, so a control that must report between beats can.

		Polling once a beat is enough for anything that moves while the music
		plays.  It is not enough for a transport, because a paused composition
		emits no beats at all.
		"""


class StepGrid (Control):
	"""A grid of rows against steps, kept as a plain dict on ``composition.data``.

	The dict is the composition's: the pattern builder reads it and this writes
	to it.  Nothing wraps it, which is what #2046 decided and what #1914
	anticipated a helper would later replace.
	"""

	def __init__ (
		self,
		composition: typing.Any,
		rows: collections.abc.Sequence[str],
		steps: int = 16,
		beats: int = 4,
		data_key: str = "grid",
		name: str = "grid",
		title: str | None = None,
	) -> None:
		"""Describe the grid to offer over a dict the composition already keeps."""

		self.composition = composition
		self.rows = list(rows)
		self.steps = steps
		self.beats = beats
		self.data_key = data_key
		self.name = name
		self.title = title

	def declaration (self) -> dict[str, typing.Any]:
		"""Rows, width, how long one time round takes, and what to call it."""

		declared: dict[str, typing.Any] = {
			"type": "step_grid", "rows": self.rows, "steps": self.steps, "beats": self.beats}

		if self.title is not None:
			declared["title"] = self.title

		return declared

	def snapshot (self) -> dict[str, list[int]]:
		"""The grid as it stands, one row at a time, empty rows included.

		Read from the link thread rather than the clock loop, deliberately: the
		only hazard is a row being sorted at this instant, and copying a list is
		a single step under the interpreter's lock.  Crossing onto the loop for
		a read would put socket work on the path that generates MIDI timing.
		"""

		grid = self.composition.data.get(self.data_key) or {}

		return {row: sorted(grid.get(row, [])) for row in self.rows}

	def apply (self, rest: list[str], value: typing.Any) -> bool:
		"""Switch one cell, absolutely rather than by toggling.

		Absolute is what makes a re-send after a reconnect safe: applying it
		twice reaches the same grid as applying it once.
		"""

		if len(rest) != 2 or not rest[1].isdigit():
			raise Refused(f"{'/'.join(rest)!r} does not name a cell of this grid")

		row, step = rest[0], int(rest[1])

		if row not in self.rows:
			raise Refused(f"this grid has no {row!r} row")

		if not 0 <= step < self.steps:
			raise Refused(f"step {step} is outside a grid {self.steps} steps wide")

		steps = self.composition.data.setdefault(self.data_key, {}).setdefault(row, [])

		if value and step not in steps:
			steps.append(step)
			steps.sort()
			return True

		if not value and step in steps:
			steps.remove(step)
			return True

		return False


class Transport (Control):
	"""Whether the composition is playing, and at what tempo.

	Pause holds the clock where it is: the position is kept, sounding notes are
	released, and MIDI Stop goes out to anything following.  Resume continues
	from the same pulse rather than restarting.

	**The face follows the composition, never the button.**  A tap asks; the
	composition answers with its own ``pause`` or ``resume`` event once the
	clock has really stopped or started, and that is what moves the face.

	**A refusal has to be caught by reading back, not by waiting.**  Subsequence
	ignores ``pause()`` when the pulse is not its to hold — under an external
	clock, an Ableton Link session, or in render mode — and says so only in its
	log: no exception, and no event will ever arrive.  So the request is read
	back at once, and a refusal is passed to the panel rather than left as a
	button that waits forever.

	A Subsequence too old to pause does not have the field declared at all, and
	a panel draws what is declared, so nothing breaks.
	"""

	def __init__ (
		self,
		composition: typing.Any,
		name: str = "transport",
		tempo_range: tuple[float, float] = (40.0, 240.0),
	) -> None:
		"""Offer tempo, and pause where the composition can hold its clock."""

		self.composition = composition
		self.name = name
		self.tempo_range = tempo_range

		self._link: "AppLink | None" = None
		self._last_bpm: float | None = None
		self._can_pause = (
			callable(getattr(composition, "pause", None))
			and callable(getattr(composition, "resume", None))
		)

		if not self._can_pause:
			LOG.info("this Subsequence cannot hold its clock; offering tempo alone")

	def attach (self, link: "AppLink") -> None:
		"""Follow the transport the composition reports, not the button tapped."""

		self._link = link

		if not self._can_pause:
			return

		self.composition.on_event("pause", lambda *_: self._report_paused(True))
		self.composition.on_event("resume", lambda *_: self._report_paused(False))

	def declaration (self) -> dict[str, typing.Any]:
		"""The fields this offers, and the tempo a panel may ask for."""

		fields = ["bpm"]

		if self._can_pause:
			fields.insert(0, "paused")

		return {"type": "transport", "fields": fields, "tempo_range": list(self.tempo_range)}

	def snapshot (self) -> dict[str, typing.Any]:
		"""Whether it is held, and the tempo the sequencer actually holds."""

		state: dict[str, typing.Any] = {"bpm": self._bpm()}

		if self._can_pause:
			state["paused"] = self._paused()

		return state

	def apply (self, rest: list[str], value: typing.Any) -> bool:
		"""Hold the transport, let it go, or set the tempo."""

		if len(rest) != 1:
			return False

		if rest[0] == "paused" and self._can_pause:
			return self._set_paused(bool(value))

		if rest[0] == "bpm":
			return self._set_bpm(value)

		return False

	def poll (self) -> list[tuple[str, typing.Any]]:
		"""Report a tempo the composition changed itself, so the panel follows it."""

		bpm = self._bpm()

		if bpm is not None and bpm != self._last_bpm:
			self._last_bpm = bpm
			return [(f"{self.name}/bpm", bpm)]

		return []

	def _paused (self) -> bool:
		"""Whether the composition says it is holding."""

		return bool(getattr(self.composition, "is_paused", False))

	def _bpm (self) -> float | None:
		"""The tempo the sequencer is running at, or nothing before it starts."""

		bpm = getattr(self.composition.sequencer, "current_bpm", 0.0)

		return round(float(bpm), 2) if bpm else None

	def _set_paused (self, paused: bool) -> bool:
		"""Ask the composition to hold or continue, and check it took.

		Nothing is reported from here on success: the composition's own event
		moves the face a few milliseconds later, once the clock has actually
		stopped.  Returning False says only that this call has changed nothing
		a panel should be told about *yet*.
		"""

		if paused == self._paused():
			return False

		if paused:
			self.composition.pause()

		else:
			self.composition.resume()

		if self._paused() != paused:
			raise Refused("the transport follows an external clock or a Link session")

		return False

	def _report_paused (self, paused: bool) -> None:
		"""Tell every panel what the transport actually did."""

		if self._link is not None:
			self._link.report(f"{self.name}/paused", paused)

	def _set_bpm (self, value: typing.Any) -> bool:
		"""Set the tempo, refusing anything outside what was declared."""

		try:
			bpm = float(value)

		except (TypeError, ValueError):
			raise Refused(f"{value!r} is not a tempo")

		low, high = self.tempo_range

		if not low <= bpm <= high:
			raise Refused(f"{bpm:g} is outside the {low:g} to {high:g} this offers")

		self.composition.set_bpm(bpm)
		self._last_bpm = self._bpm()

		return True


class Page:
	"""One view over some of an app's controls, offered as part of a set.

	A composition owns its page set (#2075): several pages served at one URL,
	each naming the parts it carries, navigated from the panel's header. A part
	may appear on more than one page and needs no synchronising to do it —
	every widget draws the app's own state, so two views of one control cannot
	disagree.

	Offering no pages at all is a complete answer: a panel then shows every
	control declared, which is what it did before pages existed.
	"""

	def __init__ (self, page_id: str, parts: collections.abc.Sequence[str], title: str | None = None) -> None:
		"""Name a view and say which declared controls appear on it."""

		self.page_id = page_id
		self.parts = list(parts)
		self.title = title

	def declaration (self) -> dict[str, typing.Any]:
		"""What a panel needs in order to offer this page and draw it."""

		return {"id": self.page_id, "title": self.title or self.page_id, "parts": self.parts}


class AppLink:
	"""One app's socket to the service, and the controls it offers over it."""

	def __init__ (
		self,
		composition: typing.Any,
		controls: collections.abc.Sequence[Control],
		app_name: str = "subsequence",
		url: str = DEFAULT_URL,
		pages: collections.abc.Sequence[Page] | None = None,
	) -> None:
		"""Describe what to offer, without connecting anything yet."""

		self.composition = composition
		self.controls = {control.name: control for control in controls}
		self.app_name = app_name
		self.url = url
		self.pages = list(pages or [])

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

		for control in self.controls.values():
			control.attach(self)

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
		"""Note the beat, pass it on, and report anything the composition changed.

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

		grid = next((c for c in self.controls.values() if isinstance(c, StepGrid)), None)

		self._emit(superintendent.protocol.event(
			self.app_name, "beat", beat=beat, ts=now, interval=interval,
			steps=grid.steps if grid else None, beats=grid.beats if grid else None))

		for control in self.controls.values():
			for path, value in control.poll():
				self.version += 1
				self._emit(superintendent.protocol.changed(
					self.app_name, path, value, self.version, by="app"))

	def _apply (self, path: str, value: typing.Any, client: str, seq: int) -> None:
		"""Hand one request to the control that owns it, on the clock loop."""

		name, _, rest = path.partition("/")
		control = self.controls.get(name)

		if control is None or not rest:
			LOG.warning("panel asked for %r, which names no control here", path)
			return

		try:
			changed = control.apply(rest.split("/"), value)

		except Refused as refusal:
			LOG.info("refused %r: %s", path, refusal)
			self._emit(superintendent.protocol.nack(self.app_name, path, client, seq, str(refusal)))
			return

		except Exception:
			LOG.warning("applying %r failed", path, exc_info=True)
			self._emit(superintendent.protocol.nack(self.app_name, path, client, seq, "the app could not do that"))
			return

		if not changed:
			return

		self.version += 1

		self._emit(superintendent.protocol.changed(
			self.app_name, path, value, self.version, by="panel", client=client, seq=seq))

	def report (self, path: str, value: typing.Any) -> None:
		"""Announce something the app did of its own accord, on the clock loop.

		A control polled once a beat cannot report a pause, because a paused
		composition has no beats.
		"""

		self.version += 1

		self._emit(superintendent.protocol.changed(
			self.app_name, path, value, self.version, by="app"))

	def _emit (self, frame: superintendent.protocol.Frame) -> None:
		"""Hand a frame to the link thread, in the order it was produced.

		Called on the clock loop and never blocking there: the send itself
		happens on the link thread, so a slow socket cannot delay a pulse.
		"""

		loop = self._link_loop

		if loop is None or self._socket is None:
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

		await self._send(superintendent.protocol.declare(
			self.app_name,
			{name: control.declaration() for name, control in self.controls.items()},
			{name: control.snapshot() for name, control in self.controls.items()},
			self.version,
			[page.declaration() for page in self.pages],
		))

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
		"""Hand one request to the clock loop, the only place it may land.

		This is the crossing Subroutine #2046 chose: one per message, no
		batching, measured at about a millisecond at p99 (#1926, #2043).
		"""

		loop = self._clock_loop

		if loop is None:
			LOG.warning("a request arrived before the first beat; nothing to apply it to yet")
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
