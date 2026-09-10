"""Fixtures for the tests that drive the page in a real browser.

The page is the half of Superconductor that a person actually touches, and the
only way to test it honestly is to run it: serve it, connect something that
behaves like an app, and drive the glass. These fixtures provide the first two.
"""

import asyncio
import contextlib
import copy
import socket
import threading
import time
import typing

import pytest
import uvicorn
import websockets.asyncio.client

import superconductor.config
import superconductor.controls
import superconductor.protocol
import superconductor.service


CONTROLS: dict[str, typing.Any] = {
	"grid": {"type": "step_grid", "rows": ["kick", "snare"], "steps": 8, "beats": 2, "title": "Drums",
	         "velocity_range": [1, 127],
	         "about": [{"label": "ch", "value": "10"}, {"label": "", "value": "Vermona DRM1"}]},
	"second": {"type": "step_grid", "rows": ["kick"], "steps": 8, "beats": 2,
	           "velocity_range": [1, 127]},
	"bass": {"type": "note_grid", "rows": ["D2", "C#2", "C2"], "steps": 8, "beats": 2,
	         "visible_rows": 2,
	         "voices": 1, "default_length": 1, "default_velocity": 100,
	         "max_length": 8, "velocity_range": [1, 127], "title": "Bass",
	         # Narrow on purpose, so a test can reach the end of it in two taps.
	         "transpose_range": [-3, 3]},
	"fine": {"type": "note_grid", "rows": ["D2", "C2"], "steps": 4, "beats": 1,
	         "voices": None, "divisions": 4, "default_length": 4, "default_velocity": 100,
	         "max_length": 16, "velocity_range": [1, 127], "title": "Fine"},
	"moog": {"type": "params", "title": "Moog",
	         # **Belongs to the bass grid** (#2201), so it is put away wherever
	         # that grid is drawn and stands on its own wherever it is not —
	         # which is what the Moog page is for, and is how both halves of
	         # the rule get drawn without a second control to keep in step.
	         "configures": "bass",
	         "fields": [
	             {"name": "glide", "kind": "switch", "label": "Glide", "group": "Glide"},
	             {"name": "rate", "kind": "number", "label": "Rate", "min": 0, "max": 127,
	              "step": 1, "group": "Glide"},
	             {"name": "shape", "kind": "choice", "label": "Shape",
	              # Lower-cased on purpose, because that is what a composition
	              # reading an instrument definition now sends: the states are
	              # named in the file and the panel is what letters them.
	              "options": [{"value": "lcr", "label": "lcr"},
	                          {"value": "exp", "label": "exp"}]},
	             # Holds nothing and is never drawn as chosen (#2179). It carries
	             # no entry in STATE below for the same reason.
	             {"name": "voicing", "kind": "action", "label": "Set voicing",
	              "options": [{"value": "one", "label": "1"},
	                          {"value": "four", "label": "4"}]},
	         ]},
	# A rack: its value is the grids somebody made, and the grids themselves
	# arrive as ordinary declared controls on the app's next declaration (#2226).
	"rack": {"type": "grids", "title": "Made here",
	         "rows": ["kick", "snare", "clap"],
	         "min_steps": 1, "max_steps": 32, "opening_steps": 16},

	"stack": {"type": "recipe", "title": "Generators", "builds": "grid",
	          "sources": ["second"], "generators": [
		{"name": "euclidean", "summary": "Spread pulses evenly.", "partial": False,
		 "parameters": [
		     {"name": "pitch", "label": "pitch", "kind": "choice", "role": "pitch",
		      "required": True,
		      "options": [{"value": voice, "label": voice}
		                  for voice in ("kick", "snare", "clap", "rim", "tom", "hat")]},
		     {"name": "pulses", "label": "pulses", "kind": "number",
		      "min": 0, "max": 8, "step": 1, "required": True},
		     {"name": "velocity", "label": "velocity", "kind": "range",
		      "min": 1, "max": 127, "step": 1, "required": False, "default": None},
		     {"name": "duration", "label": "duration", "kind": "number", "step": 1,
		      "required": False, "default": None},
		     {"name": "probability", "label": "probability", "kind": "number",
		      "min": 0, "max": 1, "required": False, "default": None},
		 ]},
		{"name": "evolve", "summary": "Mutate a sequence.", "partial": True, "parameters": []},
		# **A generator with two forms**, which is the shape #2410 made readable.
		# `arpeggio`, `chord` and `strum` each take either a chord or a pitch
		# list, and `root`/`count`/`inversion` apply to the chord alone — so
		# beside a pitch list the panel must not offer them at all.
		{"name": "arpeggio", "summary": "Cycle a chord's notes one at a time.",
		 "partial": False,
		 "parameters": [
		     {"name": "notes", "label": "notes", "kind": "choices", "role": "pitch",
		      "required": True, "accepts": ["chord", "pitches"],
		      "chord": {"roots": [{"value": "C", "label": "C"}],
		                "qualities": [{"value": "", "label": "major"}],
		                "needs": ["root"],
		                "only": ["root", "count", "inversion"]},
		      "options": [{"value": voice, "label": voice}
		                  for voice in ("kick", "snare", "clap", "rim", "tom", "hat")]},
		     {"name": "root", "label": "root", "kind": "number", "step": 1,
		      "required": False, "default": None},
		     {"name": "count", "label": "count", "kind": "number", "step": 1,
		      "required": False, "default": None},
		     {"name": "inversion", "label": "inversion", "kind": "number", "step": 1,
		      "required": False, "default": 0},
		     {"name": "spacing", "label": "spacing", "kind": "number",
		      "required": False, "default": 0.25},
		 ]},
		# **And one with only the chord form**, which is `broken_chord`: it names
		# two rather than three because it has no `count` at all, so a panel
		# reading `only` as a fixed triple would be wrong here.  Nothing it owns
		# is ever out of place, because there is no other form to be in.
		{"name": "broken_chord", "summary": "Roll a chord's tones in an order.",
		 "partial": False,
		 "parameters": [
		     {"name": "chord_obj", "label": "chord", "kind": "choices", "role": "pitch",
		      "required": True, "accepts": ["chord"],
		      "chord": {"roots": [{"value": "C", "label": "C"}],
		                "qualities": [{"value": "", "label": "major"}],
		                "needs": ["root"],
		                "only": ["root", "inversion"]},
		      "options": [{"value": voice, "label": voice}
		                  for voice in ("kick", "snare")]},
		     {"name": "root", "label": "root", "kind": "number", "step": 1,
		      "required": True},
		     {"name": "inversion", "label": "inversion", "kind": "number", "step": 1,
		      "required": False, "default": 0},
		 ]},
		# Two pools, because the panel draws a short one flat and a long one
		# behind a menu, and the line between them is where a drawing bug hides.
		{"name": "chord", "summary": "Sound several pitches together.", "partial": False,
		 "parameters": [
		     {"name": "pitches", "label": "pitches", "kind": "choices", "role": "pitch",
		      "required": True,
		      "options": [{"value": voice, "label": voice}
		                  for voice in ("kick", "snare", "clap", "rim", "tom", "hat")]},
		     {"name": "shape", "label": "shape", "kind": "choices", "required": False,
		      "options": [{"value": "up", "label": "up"},
		                  {"value": "down", "label": "down"}]},
		 ]},
		# **Two pitch inputs, which nothing in Subsequence's catalogue has** and
		# which is exactly why it is here (#2425).  A note cable's address is a
		# *parameter* rather than a block, and until this nothing tested that:
		# the drop took `takesPitch[0]` while a comment beside it said it
		# resolved to the row under the finger.  A generator with one pool cannot
		# tell those two apart, so every fixture entry agreed with the bug.
		{"name": "duet", "summary": "Play two pools against one another.",
		 "partial": False,
		 "parameters": [
		     {"name": "lead", "label": "lead", "kind": "choices", "role": "pitch",
		      "required": True,
		      "options": [{"value": voice, "label": voice}
		                  for voice in ("kick", "snare")]},
		     {"name": "answer", "label": "answer", "kind": "choices", "role": "pitch",
		      "required": True,
		      "options": [{"value": voice, "label": voice}
		                  for voice in ("kick", "snare")]},
		 ]},
	 ],
	 # What this stack may *reshape* with, as against what it may add (#2246).
	 # Two catalogues rather than one, because the two are different things and
	 # the glass has to say which is which.
	 "transforms": [
		{"name": "rotate", "summary": "Roll the pattern, wrapping around.", "partial": False,
		 "parameters": [
		     {"name": "steps", "label": "steps", "kind": "number",
		      "min": -8, "max": 8, "step": 1, "required": True},
		 ]},
		{"name": "reverse", "summary": "Flip the pattern backwards.",
		 "partial": False, "parameters": []},
	 ]},
	# **A set of notes, which is a source and sounds nothing** (#2374).  It is
	# here because the page suite had never drawn one at all: the control was
	# built, shipped and played with thirteen adapter tests and nothing that
	# rendered it, so a keyboard whose black keys came out one row square and a
	# block that could not draw its own outlet both reached the glass.
	#
	# Two octaves would be truer to the rig and is not what a fixture is for;
	# these are enough to have a natural, an accidental, and one of each chosen.
	"notes": {"type": "pitch_set", "title": "Notes",
	          "pitches": [{"value": named, "label": named, "midi": note} for named, note in
	                      (("C4", 60), ("C#4", 61), ("D4", 62), ("D#4", 63), ("E4", 64))],
	          "about": [{"label": "feeds", "value": "any generator that takes pitches"}]},

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
	# Beside the bass rather than on a page of its own: seven pages is one more
	# than `PAGE_BUTTONS`, and the row of named buttons gives way to previous
	# and next — which is correct behaviour and takes every test that reaches a
	# page by its name down with it.
	# **The settings are deliberately not named here**, and that is the case the
	# rig actually has: the Band page carries the Minitaur's pattern and not its
	# settings, so the latch was offered where the block could not be drawn and
	# tapping it flickered the layout and revealed nothing. Naming `moog` on this
	# page hid that for a month. A settings block goes wherever the pattern it
	# configures goes, exactly as a stack does (#2211).
	{"id": "bass", "title": "Bass", "parts": ["bass", "fine"]},
	{"id": "moog", "title": "Moog", "parts": ["moog"]},
	# **The note set goes here rather than on a page of its own**, because seven
	# pages is one more than `PAGE_BUTTONS` (see above) — and because this is the
	# page with a stack on it, which is the only thing a note set can feed.
	{"id": "stack", "title": "Generators", "parts": ["grid", "second", "stack", "notes"]},
	# The rack goes here rather than on a page of its own, because seven pages is
	# one more than `PAGE_BUTTONS` (see above) — and beside the stack, which is
	# the other control whose value is a list somebody builds up (#2226).
	{"id": "alone", "title": "Stack alone", "parts": ["stack", "rack"]},
]
"""Two views over the same two grids, one of which carries both.

The first is what a panel opens on, so everything declared is on the glass
unless a test goes looking for the other one.  ``grid`` appears on both, which
is the case #2075 says needs no synchronising.
"""


STATE: dict[str, typing.Any] = {
	"grid": {"kick": [0, 4], "snare": []},
	"second": {"kick": [2]},
	"bass": {"C2": {"0": {"length": 2, "velocity": 90}}},
	# A step divided into four, so a note can sit and end between two of them:
	# a quarter-step note on the boundary, and one starting halfway through the
	# next step. Geometry measured in whole cells cannot tell either of them
	# from a note on the step, which is exactly what went wrong.
	"fine": {"C2": {"0": {"length": 1, "velocity": 100},
	                "6": {"length": 2, "velocity": 100}}},
	"moog": {"glide": False, "rate": 24, "shape": "lcr"},
	"rack": {"grids": []},
	"notes": {"chosen": ["C4", "D#4"], "enabled": True},
	"stack": {"layers": [
		{"id": "one", "generator": "euclidean", "index": 1, "bypassed": False,
		 "params": {"pitch": "kick", "pulses": 3, "velocity": [40, 80],
		            "duration": 1, "probability": 1}},
		# **Patched at the note set rather than holding a pool of its own**
		# (#2374), so the suite draws a cable as well as the loom every
		# generator already draws to the pattern it builds.
		{"id": "two", "generator": "chord", "index": 2, "bypassed": False,
		 "params": {"pitches": {"from": "control", "id": "notes"}, "shape": ["up"]}},
	]},
	"transport": {"paused": False, "bpm": 120.0},
}
"""What the stand-in app starts out holding.

One layer rather than none, because a stack with nothing in it draws none of
the controls most of these tests are about.
"""


def _held_port () -> tuple[socket.socket, int]:
	"""A listening socket, and the port it is holding for as long as it is open.

	**Asking for a free port and then letting go of it is a race**, and one that
	only appears when there is more than one asker: under `pytest-xdist` eight
	workers start within milliseconds of each other, and between the answer and
	the moment uvicorn binds there is a window in which the same port is free for
	somebody else too.  The failure would be one worker's service refusing to
	start, on a port number, in a run that had been green a minute earlier.

	So the socket is never released — it is handed to uvicorn, which serves on it
	rather than binding one of its own.  There is then no window at all.
	"""

	held = socket.socket()
	held.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	held.bind(("127.0.0.1", 0))
	held.listen()

	return held, int(held.getsockname()[1])


class FakeApp:
	"""Stands in for a music app: declares controls and answers what the panel asks.

	It speaks the real protocol over a real socket, so the page under test cannot
	tell it from Subsequence.
	"""

	def __init__ (self, url: str) -> None:
		"""Connect on a thread of its own and wait until the socket is up."""

		self.url = url
		self.sets: list[superconductor.protocol.Frame] = []
		self.arrangements: dict[str, list[dict[str, typing.Any]]] = {}
		self.version = 1

		self.state: dict[str, typing.Any] = copy.deepcopy(STATE)
		"""What this app holds, kept rather than rebuilt from a literal.

		An arrangement is answered with a fresh declaration, and a declaration
		carries the state — so an app that made one up each time would forget
		everything a test had confirmed the moment a block was dragged.  It did,
		silently, and the second layer of a stack vanished mid-drag.
		"""

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

			await socket_.send(superconductor.protocol.encode(self._declaration()))

			self._ready.set()

			async for raw in socket_:
				frame = superconductor.protocol.decode(raw)

				if frame["t"] == "set":
					self.sets.append(frame)

				elif frame["t"] == "layout":
					self.arrangements[str(frame.get("page"))] = list(frame.get("parts") or [])

					await socket_.send(superconductor.protocol.encode(self._declaration()))

	def _declaration (self) -> superconductor.protocol.Frame:
		"""What this app offers, including any arrangement it has been given.

		Re-sent after an arrangement is kept, which is how a page set stays
		shared: what one panel arranged, every panel sees.
		"""

		pages = [{**page, **({"layout": self.arrangements[page["id"]]}
		                     if page["id"] in self.arrangements else {})}
		         for page in PAGES]

		return superconductor.protocol.declare(
			"subsequence", CONTROLS, self.state, self.version, pages)

	def redeclare (self, controls: dict[str, typing.Any],
	               pages: list[dict[str, typing.Any]] | None = None) -> None:
		"""Declare again with a different set of controls.

		An app may redeclare at any time on the socket it already has — keeping
		an arrangement does it, and adding a generator does it — so this is the
		ordinary way to put a differently-shaped control in front of the panel
		without reshaping the fixture for every test that shares it.
		"""

		self.version += 1

		self.send(superconductor.protocol.declare(
			"subsequence", controls, self.state, self.version,
			PAGES if pages is None else pages))

	def send (self, frame: superconductor.protocol.Frame) -> None:
		"""Put one frame on the wire from the app's side."""

		assert self._loop is not None and self._socket is not None

		asyncio.run_coroutine_threadsafe(
			self._socket.send(superconductor.protocol.encode(frame)), self._loop).result(5.0)

	def confirm (self, path: str, value: typing.Any, by: str = "panel",
	             client: str | None = None, seq: int | None = None) -> None:
		"""Report a change as applied, the way an app confirms a tap."""

		self.version += 1

		# By the service's own rules, so what the fake remembers and what the
		# service remembers cannot come apart.
		with contextlib.suppress(superconductor.controls.ControlError):
			superconductor.controls.apply_change(self.state, CONTROLS, path, value)

		self.send(superconductor.protocol.changed(
			"subsequence", path, value, self.version, by=by, client=client, seq=seq))

	def beat (self, beat: int, interval: float = 0.5,
	          steps: int = 8, beats: int = 2) -> None:
		"""Sound one beat, the way a running composition does.

		An event and never a change: nothing keeps it and nothing applies it to
		any control's state (#1965).  It is what the playhead and the transport
		counter are both driven by, and the only way to test either without a
		sequencer actually running.
		"""

		self.send(superconductor.protocol.event(
			"subsequence", "beat", beat=beat, ts=0.0, interval=interval,
			steps=steps, beats=beats))

	def realised (self, control: str, cells: dict, source: str = "one",
	              sources: dict[str, str] | None = None) -> None:
		"""Say what the algorithms put on a grid this cycle.

		An event and never a change (#1965): nothing stores it, and a panel that
		joins afterwards has nowhere to read it from — which is exactly why it
		has to stop being drawn the moment it stops being true.
		"""

		# Written as `{row: {step: velocity}}` because that is what a test is
		# usually about, and wrapped here into the shape the wire carries since
		# contract 1.13.0 — each cell says how hard *and* which layer put it
		# there, so a routed grid's note can be told from a generator's.
		# One event carries a whole cycle, and a cycle is several layers — so a
		# row may name the layer that produced it. Sending two events instead
		# would not do: each replaces the control's cells entirely, which is
		# what a cycle's report is.
		self.send(superconductor.protocol.event(
			"subsequence", "realised", control=control,
			cells={
				row: {step: {"v": loud, "from": (sources or {}).get(row, source)}
				      for step, loud in steps.items()}
				for row, steps in cells.items()}))

	def stalled (self, control: str, layers: dict[str, str]) -> None:
		"""Say which layers of a stack did not run this cycle, and why (#2368).

		One place knows the wire's shape, which is why this lives here beside
		`beat` and `realised` rather than being built by hand in a test: a second
		helper that built frames itself went on sending the pre-1.13.0 shape
		after the first had moved on, and every dot drew at one size whatever its
		velocity.
		"""

		self.send(superconductor.protocol.event(
			"subsequence", "stalled", control=control, layers=layers))

	def refuse (self, path: str, client: str, seq: int, reason: str) -> None:
		"""Refuse a request, the way an app that cannot do it does."""

		self.send(superconductor.protocol.nack("subsequence", path, client, seq, reason))

	def stop (self) -> None:
		"""Close the socket and let the thread that owns it finish.

		Without this a `FakeApp` outlives the test that made it: a daemon
		thread, an event loop and an open socket each, all still declared to the
		one session-scoped service as ``subsequence``.  A full run leaked about
		a hundred and sixty of each and raised a warning for every one, which is
		enough noise to hide a real thread fault — and it put the reconnection
		defect this suite is meant to catch *inside* the suite, where a leaked
		socket dropping mid-session would take the app under test away with it.
		"""

		if self._loop is None or self._loop.is_closed():
			return

		closing = None

		if self._socket is not None:
			with contextlib.suppress(Exception):
				closing = asyncio.run_coroutine_threadsafe(self._socket.close(), self._loop)

		# **Waited for by joining the thread, not by waiting on the close.**
		# Closing the socket is what ends `_serve`, which ends
		# `run_until_complete`, which stops the loop — and a loop that has
		# stopped never runs the callback that would resolve the close's own
		# future. Waiting on that future therefore always costs the full
		# timeout, on every test, while the work itself is already done: five
		# seconds each, measured, which is where a hundred-second suite went
		# when this was written the obvious way.
		self._thread.join(timeout=5.0)

		if closing is not None and closing.done():
			with contextlib.suppress(Exception):
				closing.result()

		with contextlib.suppress(Exception):
			self._loop.close()

	def await_set (self, path: str, limit: float = 5.0) -> superconductor.protocol.Frame:
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

	held, port = _held_port()
	config = superconductor.config.Config(host="127.0.0.1", port=port)

	server = uvicorn.Server(uvicorn.Config(
		superconductor.service.build(config), host="127.0.0.1", port=port, log_level="error"))

	thread = threading.Thread(target=lambda: server.run(sockets=[held]), daemon=True)
	thread.start()

	deadline = time.monotonic() + 10.0

	while not server.started and time.monotonic() < deadline:
		time.sleep(0.05)

	if not server.started:
		raise RuntimeError("the service never started")

	yield f"http://127.0.0.1:{port}"

	server.should_exit = True
	thread.join(timeout=5.0)
	held.close()


@pytest.fixture
def fake_app (service_url: str) -> typing.Iterator[FakeApp]:
	"""An app dialled in to that service, declaring a grid and a transport."""

	app = FakeApp(service_url.replace("http://", "ws://") + "/ws/app")

	try:
		yield app

	finally:
		app.stop()


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
