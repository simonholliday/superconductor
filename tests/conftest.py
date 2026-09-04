"""Fixtures for the tests that drive the page in a real browser.

The page is the half of Superintendent that a person actually touches, and the
only way to test it honestly is to run it: serve it, connect something that
behaves like an app, and drive the glass. These fixtures provide the first two.
"""

import asyncio
import contextlib
import socket
import threading
import time
import typing

import pytest
import uvicorn
import websockets.asyncio.client

import superintendent.config
import superintendent.protocol
import superintendent.service


CONTROLS: dict[str, typing.Any] = {
	"grid": {"type": "step_grid", "rows": ["kick", "snare"], "steps": 8, "beats": 2, "title": "Drums"},
	"second": {"type": "step_grid", "rows": ["kick"], "steps": 8, "beats": 2},
	"bass": {"type": "note_grid", "rows": ["D2", "C#2", "C2"], "steps": 8, "beats": 2,
	         "visible_rows": 2,
	         "mono": True, "default_length": 1, "default_velocity": 100,
	         "max_length": 8, "velocity_range": [1, 127], "title": "Bass"},
	"transport": {"type": "transport", "fields": ["paused", "bpm"], "tempo_range": [40.0, 240.0]},
}
"""A small declaration: enough shapes to draw, few enough cells to read.

Two grids rather than one, and the second sharing a row name with the first on
purpose.  A panel that addressed a cell by row and step alone would confuse
them, and did until cells were addressed by their whole path.  One grid carries
a title and one does not, so both halves of that are drawn every run.
"""

PAGES: list[dict[str, typing.Any]] = [
	{"id": "all", "title": "All", "parts": ["grid", "second"]},
	{"id": "drums", "title": "Drums", "parts": ["grid"]},
	{"id": "bass", "title": "Bass", "parts": ["bass"]},
]
"""Two views over the same two grids, one of which carries both.

The first is what a panel opens on, so everything declared is on the glass
unless a test goes looking for the other one.  ``grid`` appears on both, which
is the case #2075 says needs no synchronising.
"""


def _free_port () -> int:
	"""Take a port the operating system says is free."""

	with contextlib.closing(socket.socket()) as probe:
		probe.bind(("127.0.0.1", 0))

		return int(probe.getsockname()[1])


class FakeApp:
	"""Stands in for a music app: declares controls and answers what the panel asks.

	It speaks the real protocol over a real socket, so the page under test cannot
	tell it from Subsequence.
	"""

	def __init__ (self, url: str) -> None:
		"""Connect on a thread of its own and wait until the socket is up."""

		self.url = url
		self.sets: list[superintendent.protocol.Frame] = []
		self.arrangements: dict[str, list[dict[str, typing.Any]]] = {}
		self.version = 1

		self._loop: asyncio.AbstractEventLoop | None = None
		self._socket: typing.Any = None
		self._ready = threading.Event()

		self._thread = threading.Thread(target=self._run, daemon=True)
		self._thread.start()

		if not self._ready.wait(10.0):
			raise RuntimeError("the stand-in app never connected")

	def _run (self) -> None:
		"""Own a loop on this thread and hold the socket open."""

		self._loop = asyncio.new_event_loop()
		asyncio.set_event_loop(self._loop)
		self._loop.run_until_complete(self._serve())

	async def _serve (self) -> None:
		"""Declare, then keep whatever the service sends."""

		async with websockets.asyncio.client.connect(self.url) as socket_:
			self._socket = socket_

			await socket_.send(superintendent.protocol.encode(self._declaration()))

			self._ready.set()

			async for raw in socket_:
				frame = superintendent.protocol.decode(raw)

				if frame["t"] == "set":
					self.sets.append(frame)

				elif frame["t"] == "arrange":
					self.arrangements[str(frame.get("page"))] = list(frame.get("parts") or [])

					await socket_.send(superintendent.protocol.encode(self._declaration()))

	def _declaration (self) -> superintendent.protocol.Frame:
		"""What this app offers, including any arrangement it has been given.

		Re-sent after an arrangement is kept, which is how a page set stays
		shared: what one panel arranged, every panel sees.
		"""

		pages = [{**page, **({"layout": self.arrangements[page["id"]]}
		                     if page["id"] in self.arrangements else {})}
		         for page in PAGES]

		return superintendent.protocol.declare(
			"subsequence", CONTROLS,
			{"grid": {"kick": [0, 4], "snare": []}, "second": {"kick": [2]},
			 "bass": {"C2": {"0": {"length": 2, "velocity": 90}}},
			 "transport": {"paused": False, "bpm": 120.0}},
			self.version, pages)

	def send (self, frame: superintendent.protocol.Frame) -> None:
		"""Put one frame on the wire from the app's side."""

		assert self._loop is not None and self._socket is not None

		asyncio.run_coroutine_threadsafe(
			self._socket.send(superintendent.protocol.encode(frame)), self._loop).result(5.0)

	def confirm (self, path: str, value: typing.Any, by: str = "panel",
	             client: str | None = None, seq: int | None = None) -> None:
		"""Report a change as applied, the way an app confirms a tap."""

		self.version += 1
		self.send(superintendent.protocol.changed(
			"subsequence", path, value, self.version, by=by, client=client, seq=seq))

	def refuse (self, path: str, client: str, seq: int, reason: str) -> None:
		"""Refuse a request, the way an app that cannot do it does."""

		self.send(superintendent.protocol.nack("subsequence", path, client, seq, reason))

	def await_set (self, path: str, limit: float = 5.0) -> superintendent.protocol.Frame:
		"""Wait for the panel to ask for a path, and return what it asked."""

		deadline = time.monotonic() + limit

		while time.monotonic() < deadline:
			for frame in list(self.sets):
				if frame.get("path") == path:
					return frame

			time.sleep(0.02)

		raise AssertionError(f"the panel never asked for {path!r}; it asked for "
		                     f"{[f.get('path') for f in self.sets]}")


@pytest.fixture(scope="session")
def browser_name () -> str:
	"""Firefox, which is the browser this is for.

	pytest-playwright offers Chromium by default, and the panel is a Firefox
	panel — chosen on Simon's preference and supported by the measurement, which
	found Firefox's touch path delivering `pointerdown` and input-to-commit
	faster than Chromium's on this class of hardware (#1941).  Testing the one
	we do not ship against would be testing the wrong thing.

	Overridden here rather than left to `--browser` so that plain `pytest` does
	the right thing, which is what anybody will type.
	"""

	return "firefox"


@pytest.fixture(scope="session")
def service_url () -> typing.Iterator[str]:
	"""A real service, on a real port, for the whole session."""

	port = _free_port()
	config = superintendent.config.Config(host="127.0.0.1", port=port)

	server = uvicorn.Server(uvicorn.Config(
		superintendent.service.build(config), host="127.0.0.1", port=port, log_level="error"))

	thread = threading.Thread(target=server.run, daemon=True)
	thread.start()

	deadline = time.monotonic() + 10.0

	while not server.started and time.monotonic() < deadline:
		time.sleep(0.05)

	if not server.started:
		raise RuntimeError("the service never started")

	yield f"http://127.0.0.1:{port}"

	server.should_exit = True
	thread.join(timeout=5.0)


@pytest.fixture
def fake_app (service_url: str) -> typing.Iterator[FakeApp]:
	"""An app dialled in to that service, declaring a grid and a transport."""

	app = FakeApp(service_url.replace("http://", "ws://") + "/ws/app")

	yield app


@pytest.fixture
def panel (page: typing.Any, service_url: str, fake_app: FakeApp) -> typing.Any:
	"""The page, loaded in a browser, with an app already connected to it.

	Waits for the grid to be drawn, so a test starts from the state a person
	would be looking at rather than from a blank page.
	"""

	page.goto(service_url)
	page.wait_for_selector(".cell", timeout=10_000)

	return page


def cell (path: str) -> str:
	"""The selector for one cell, addressed the way the protocol addresses it.

	By its whole path, control included: two grids may name a row the same and
	only the control tells them apart.
	"""

	return f'.cell[data-path="{path}"]'
