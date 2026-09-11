"""What a person made on the glass, kept across a restart of the composition (#2487).

A restart used to discard every edit made on the panel (#2067), and variants
would multiply that by four (#2485).  So a composition may hand its link a
`PatternStore`, and everything a person *authors* — cells, stacks, settings, the
note set, transpositions, mutes and the grids they made — is written to it off
the clock and put back before the link first declares.

Each test here builds the same small piece twice, the way a composition file is
read twice by two starts: the second `_piece` is a restart.
"""

import asyncio
import contextlib
import json
import logging
import pathlib
import threading
import time
import types
import typing

import pytest

import superconductor.subsequence_adapter as adapter


ROWS = ["kick", "snare", "hat"]
PITCHES = ["E2", "D2", "C2"]

OPENING = {"kick": [0, 8], "hat": [0, 4, 8, 12]}
"""What the piece seeds on every start, as `OPENING_PATTERN` does on the rig."""

CATALOGUE: list[dict[str, typing.Any]] = [
	{
		"name": "euclidean",
		"summary": "Generate a Euclidean rhythm.",
		"partial": False,
		"parameters": [
			{"name": "pitch", "label": "pitch", "kind": "pitch", "required": True},
			{"name": "pulses", "label": "pulses", "kind": "number", "step": 1,
			 "required": True},
		],
	},
]


class Composition:
	"""The little of a composition a link and its controls touch.

	**Its patterns do not exist until it plays**, as a real one's do not:
	Subsequence's `mute` raises for a pattern it has not started, so a mute put
	back before `play()` has to wait for the first beat.
	"""

	def __init__ (self) -> None:
		"""Not playing, with nothing muted and nothing listening."""

		self.data: dict[str, typing.Any] = {}
		self.listeners: dict[str, typing.Any] = {}
		self.running = False
		self.muted: set[str] = set()
		self.sequencer = types.SimpleNamespace(current_bpm=120.0)
		self.is_paused = False

	def on_event (self, name: str, callback: typing.Any) -> None:
		"""Register a callback the way the real composition does."""

		self.listeners[name] = callback

	def mute (self, name: str) -> None:
		"""Silence a running pattern, and refuse one that is not running yet."""

		if not self.running:
			raise ValueError(f"Pattern '{name}' not found. Available: []")

		self.muted.add(name)

	def unmute (self, name: str) -> None:
		"""Bring a running pattern back, refusing as `mute` does."""

		if not self.running:
			raise ValueError(f"Pattern '{name}' not found. Available: []")

		self.muted.discard(name)

	def set_bpm (self, bpm: float) -> None:
		"""Take a tempo."""

		self.sequencer.current_bpm = bpm

	def pause (self) -> None:
		"""Hold the clock."""

		self.is_paused = True

	def resume (self) -> None:
		"""Let it go."""

		self.is_paused = False


def _piece (path: pathlib.Path) -> tuple[adapter.AppLink, Composition]:
	"""The composition file, read: what starting it does, every time.

	It seeds a pattern first, as a composition file does, so calling this again
	is exactly a restart — the same file read again, beside whatever was kept.
	"""

	composition = Composition()
	composition.data["grid"] = {row: list(OPENING.get(row, [])) for row in ROWS}

	# The composition's own register of what can be routed, shared with the
	# stack rather than copied (#2421), and grown by the rack as it makes grids.
	sources: dict[str, typing.Any] = {}

	def make (spec: dict[str, typing.Any]) -> adapter.Control:
		"""One grid the rack was asked for, routable the moment it exists."""

		composition.data.setdefault(spec["name"], {row: [] for row in spec["rows"]})
		sources[spec["name"]] = lambda pattern: None

		return adapter.StepGrid(
			composition, rows=spec["rows"], steps=spec["steps"],
			data_key=spec["name"], name=spec["name"])

	link = adapter.AppLink(
		composition,
		controls=[
			adapter.StepGrid(composition, rows=ROWS, steps=16, data_key="grid",
			                 name="grid", pattern="drums"),
			adapter.NoteGrid(composition, rows=PITCHES, steps=16, data_key="bass",
			                 name="bass", pattern="bass",
			                 relabel=lambda row, semitones: f"{row}{semitones:+d}"),
			adapter.Params(composition, parameters=[
				adapter.Parameter("glide", "switch", default=False),
				adapter.Parameter("rate", "number", default=24, minimum=0, maximum=127),
				adapter.Parameter("mode", "choice", default="lcr",
				                  options=[("lcr", "lcr"), ("exp", "exp")]),
				adapter.Parameter("voicing", "action", options=[("one", "1"), ("four", "4")]),
			], data_key="synth", name="synth",
			# Where the instrument would be sent a control change; an instrument
			# is only ever owed its settings where there is somewhere to send them.
			on_change=lambda name, value: None),
			adapter.PitchSet(composition, name="notes",
			                 pitches={"C3": 48, "E3": 52, "G3": 55}),
			adapter.Recipe(composition, catalogue=CATALOGUE, pitches=ROWS,
			               sources=sources, data_key="stack", name="stack"),
			adapter.GridRack(composition, make=make, rows=ROWS, data_key="rack", name="rack"),
			adapter.Transport(composition),
		],
		pattern_store=adapter.PatternStore(path),
		url="ws://127.0.0.1:1/ws/app",
	)

	return link, composition


@pytest.fixture
def unthreaded (monkeypatch: pytest.MonkeyPatch) -> None:
	"""Starting a link does everything but dial.

	The link's own thread dials a socket, and on the rig's machine a real one is
	usually listening — a test that let it would reach into the studio.  So its
	body is emptied rather than `threading.Thread` replaced: the store writes on a
	worker thread, and so does the clock these tests stand in for.
	"""

	monkeypatch.setattr(adapter.AppLink, "_run_link", lambda self: None)


def _on_a_loop (work: typing.Callable[[], None]) -> threading.Thread:
	"""Run *work* inside a running event loop on a thread of its own, as the clock does."""

	async def run () -> None:
		work()

	thread = threading.Thread(target=lambda: asyncio.run(run()), name="clock")
	thread.start()
	thread.join(timeout=5)

	assert not thread.is_alive(), "the work never finished"

	return thread


@contextlib.contextmanager
def _link_thread (link: adapter.AppLink) -> typing.Iterator[asyncio.AbstractEventLoop]:
	"""Give the link a loop on a thread of its own, without dialling anything."""

	loop = asyncio.new_event_loop()
	thread = threading.Thread(target=loop.run_forever, name="superconductor-link", daemon=True)
	thread.start()

	link._link_loop = loop

	try:
		yield loop

	finally:
		loop.call_soon_threadsafe(loop.stop)
		thread.join(timeout=5)
		loop.close()


def _kept (path: pathlib.Path) -> dict[str, typing.Any]:
	"""What the store holds, by control."""

	held: dict[str, typing.Any] = json.loads(path.read_text(encoding="utf-8"))["controls"]

	return held


def _edit_everything (link: adapter.AppLink) -> None:
	"""Work every kind of control the way a person on the glass would."""

	edits: list[tuple[str, typing.Any]] = [
		("grid/snare/4", True),
		("grid/kick/8", False),
		("grid/enabled", False),
		("bass/C2/0", True),
		("bass/transpose", 3),
		("bass/enabled", False),
		("synth/glide", True),
		("synth/rate", 90),
		("synth/mode", "exp"),
		("notes/chosen", ["G3", "C3"]),
		("rack/grids", [{"id": "a", "rows": ["snare"], "steps": 8}]),
		("rack-a/snare/3", True),
		("stack/layers", [
			{"id": "one", "kind": "generator", "generator": "euclidean",
			 "params": {"pitch": "kick", "pulses": 5}},
			{"id": "two", "kind": "route", "source": "rack-a"},
		]),
		("transport/bpm", 140),
	]

	for seq, (path, value) in enumerate(edits):
		link._apply(path, value, "panel-1", seq)


# --- a restart puts it all back ---------------------------------------------

def test_a_piece_nobody_has_played_has_nothing_kept_and_starts_as_written (
	tmp_path: pathlib.Path, unthreaded: None) -> None:
	"""No file is the ordinary case, not an error: the piece opens as its file says."""

	path = tmp_path / "piece.patterns.json"

	assert adapter.PatternStore(path).load() is None

	link, composition = _piece(path)
	link.start()

	assert composition.data["grid"]["kick"] == [0, 8]
	assert not path.exists(), "starting writes nothing"


def test_a_restart_puts_back_every_control_a_person_worked (
	tmp_path: pathlib.Path, unthreaded: None) -> None:
	"""Cells, mutes, a transposition, settings, the note set, a made grid and
	what is drawn on it, and a stack that routes from that grid.

	**The route is the ordering test.**  A stack refuses a layer whose source
	does not exist, and a made grid only exists once the rack has made it — so
	the rack has to be put back before anything that routes from it.
	"""

	path = tmp_path / "piece.patterns.json"

	first, composition = _piece(path)
	first.start()
	composition.running = True
	_edit_everything(first)
	first._keep_now()

	again, _ = _piece(path)
	again.start()

	for name, control in first.controls.items():
		if name == "transport":
			continue

		assert again.controls[name].kept() == control.kept(), f"{name} did not come back"

	stack = typing.cast(adapter.Recipe, again.controls["stack"])

	assert again.controls["rack-a"].kept()["rows"] == {"snare": [3]}
	assert [one["id"] for one in stack.layers()] == ["one", "two"]


def test_a_seeded_grid_somebody_emptied_stays_empty (
	tmp_path: pathlib.Path, unthreaded: None) -> None:
	"""**The case #2465 exists for.**  The piece seeds a kick and a hat on every
	start; a person took them all out.  A store that only *added* what it kept
	would bring the seed back on top, which is what the rig did twice on
	2026-09-11 — a clap at 10:54 and five cells at 12:05.
	"""

	path = tmp_path / "piece.patterns.json"

	first, composition = _piece(path)
	first.start()
	composition.running = True
	first._apply("grid/rows", {}, "panel-1", 1)
	first._keep_now()

	again, composition = _piece(path)

	assert composition.data["grid"]["kick"] == [0, 8], "the file seeds it, as ever"

	again.start()

	assert again.controls["grid"].kept()["rows"] == {}


def test_the_transport_is_not_kept (tmp_path: pathlib.Path, unthreaded: None) -> None:
	"""Tempo and pause are how the piece is being played, not what was made.

	A capture restored paused reads exactly like a stopped clock, and that cost
	a session on 2026-09-10 — a store that brought back a pause would do it on
	every start.
	"""

	path = tmp_path / "piece.patterns.json"

	first, composition = _piece(path)
	first.start()
	composition.running = True
	_edit_everything(first)
	first._keep_now()

	assert "transport" not in _kept(path)


def test_an_action_is_not_kept (tmp_path: pathlib.Path, unthreaded: None) -> None:
	"""A control that does something and holds nothing (#2179) has nothing to put back."""

	path = tmp_path / "piece.patterns.json"

	first, composition = _piece(path)
	first.start()
	composition.running = True
	first._apply("synth/voicing", "four", "panel-1", 1)
	first._apply("synth/rate", 90, "panel-1", 2)
	first._keep_now()

	assert "voicing" not in _kept(path)["synth"]


def test_a_mute_put_back_before_the_patterns_run_is_applied_at_the_first_beat (
	tmp_path: pathlib.Path, unthreaded: None) -> None:
	"""The store is read before `play()`, and Subsequence cannot mute a pattern it
	has not started — so the mute is held, and handed over on the first beat,
	which is the first moment there is a pattern to hand it to.
	"""

	path = tmp_path / "piece.patterns.json"

	first, composition = _piece(path)
	first.start()
	composition.running = True
	first._apply("grid/enabled", False, "panel-1", 1)
	first._keep_now()

	again, composition = _piece(path)
	again.start()

	assert again.controls["grid"].enabled is False, "the glass is told at once"
	assert composition.muted == set(), "nothing can be muted yet"

	composition.running = True
	_on_a_loop(lambda: again._on_beat(0))

	assert composition.muted == {"drums"}


# --- when and where it writes ------------------------------------------------

def test_the_store_is_written_off_the_clock_and_never_on_it (
	tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, unthreaded: None) -> None:
	"""A tap lands on the clock loop, and the clock is paramount (#2046): what it
	may do there is note that something changed.  The writing happens on another
	thread, a little later, once the hands have stopped.
	"""

	monkeypatch.setattr(adapter, "KEEP_AFTER", 0.05)

	path = tmp_path / "piece.patterns.json"
	link, composition = _piece(path)
	link.start()
	composition.running = True

	writers: list[threading.Thread] = []
	real = adapter.PatternStore.save

	def save (store: adapter.PatternStore, controls: dict[str, typing.Any]) -> None:
		# Noted once the file is written rather than before, or the wait below
		# ends while the write is still going and the read finds no file — which
		# is what a slow runner did on the first push.
		real(store, controls)
		writers.append(threading.current_thread())

	monkeypatch.setattr(adapter.PatternStore, "save", save)

	with _link_thread(link):
		clock = _on_a_loop(lambda: link._apply("grid/snare/4", True, "panel-1", 1))

		deadline = time.monotonic() + 5

		while not writers and time.monotonic() < deadline:
			time.sleep(0.01)

	assert writers, "nothing was written at all"
	assert clock not in writers
	assert _kept(path)["grid"]["rows"]["snare"] == [4]


class _Handle:
	"""One call a loop has been asked to make later."""

	def __init__ (self, when: float, callback: typing.Callable[[], None]) -> None:
		"""Due at *when*, and not cancelled yet."""

		self.when = when
		self.callback = callback
		self.cancelled = False

	def cancel (self) -> None:
		"""Never make it."""

		self.cancelled = True


class _Clockwork:
	"""A loop whose time is told rather than read, so a wait needs no waiting."""

	def __init__ (self) -> None:
		"""At time zero, with nothing due."""

		self.now = 0.0
		self.due: list[_Handle] = []
		self.ran: list[typing.Callable[[], None]] = []

	def time (self) -> float:
		"""What time this loop says it is."""

		return self.now

	def call_at (self, when: float, callback: typing.Callable[[], None]) -> _Handle:
		"""Write the call down rather than making it."""

		handle = _Handle(when, callback)
		self.due.append(handle)

		return handle

	def run_in_executor (self, executor: typing.Any, work: typing.Callable[[], None]) -> None:
		"""Do it at once, here."""

		self.ran.append(work)
		work()

	def live (self) -> list[float]:
		"""When each call still standing is due."""

		return [handle.when for handle in self.due if not handle.cancelled]


def test_a_change_waits_for_the_hands_to_stop_but_never_longer_than_the_ceiling (
	tmp_path: pathlib.Path, unthreaded: None) -> None:
	"""Written once the changes stop, so a run of taps is one write rather than
	thirty — and never later than the ceiling after the first of them, so a
	person working steadily for an hour is not one power cut from losing it.
	"""

	link, _ = _piece(tmp_path / "piece.patterns.json")
	loop = _Clockwork()
	link._link_loop = typing.cast(typing.Any, loop)

	writes: list[float] = []

	def written (wait: float = -1, everything: bool = False) -> None:
		"""Note when the store would have been written, instead of writing it."""

		writes.append(loop.now)

	link._keep_now = written  # type: ignore[method-assign]

	link._keep_later()

	assert loop.live() == [adapter.KEEP_AFTER], "the first waits for quiet"

	# A tap a second, for half a minute.
	for second in range(1, 30):
		loop.now = float(second)

		if loop.live() and loop.live()[0] <= loop.now:
			due = next(handle for handle in loop.due if not handle.cancelled)
			due.cancel()
			due.callback()

		link._keep_later()

	assert writes, "never written while the hands were busy"
	assert writes[0] == adapter.KEEP_AT_MOST, "held past the ceiling"


def test_the_declared_path_is_honoured_and_nothing_is_written_beside_it (
	tmp_path: pathlib.Path, unthreaded: None) -> None:
	"""**Where it writes is the composition's to say** — the rig's composition
	sits on a network share where a write can wedge (nuc14 #2438), so the rig
	keeps its store on local disk instead.  A folder that is not there yet is
	made, and nothing is left beside the file once it is written.
	"""

	path = tmp_path / "somewhere" / "else" / "piece.patterns.json"

	link, composition = _piece(path)
	link.start()
	composition.running = True
	link._apply("grid/snare/4", True, "panel-1", 1)
	link._keep_now()

	assert _kept(path)["grid"]["rows"]["snare"] == [4]
	assert sorted(one.name for one in path.parent.iterdir()) == ["piece.patterns.json"]


def test_a_store_saying_nothing_about_where_writes_beside_its_composition () -> None:
	"""The ordinary case, for a composition not sitting on a network share."""

	assert adapter.PatternStore.beside("/pieces/drums.py").path == pathlib.Path(
		"/pieces/drums.patterns.json")


def test_stopping_keeps_what_was_not_kept_yet_and_nothing_when_nothing_changed (
	tmp_path: pathlib.Path, unthreaded: None) -> None:
	"""A clean shutdown writes the last change down rather than leaving it to a
	timer that will never fire — and a piece nobody touched is not rewritten
	every time it stops, which would be churn with nothing in it.
	"""

	path = tmp_path / "piece.patterns.json"

	untouched, _ = _piece(path)
	untouched.start()
	untouched.stop()

	assert not path.exists()

	touched, composition = _piece(path)
	touched.start()
	composition.running = True
	touched._apply("grid/snare/4", True, "panel-1", 1)
	touched.stop()

	assert _kept(path)["grid"]["rows"]["snare"] == [4]


# --- what cannot be put back -------------------------------------------------

def test_a_store_that_cannot_be_read_is_put_aside_loudly_and_never_written_over (
	tmp_path: pathlib.Path, unthreaded: None, caplog: pytest.LogCaptureFixture) -> None:
	"""**Refused, and nothing seeded over it in silence.**  The piece still
	starts, because refusing to play is the worse failure on a stage; but the
	file is moved aside byte for byte, so the first save cannot destroy what
	somebody may still be able to recover, and the log says where it went.
	"""

	path = tmp_path / "piece.patterns.json"
	path.write_text("{ this is not json", encoding="utf-8")

	link, composition = _piece(path)

	with caplog.at_level(logging.ERROR, logger=adapter.LOG.name):
		link.start()

	aside = list(tmp_path.glob("piece.patterns.json.unreadable-*"))

	assert len(aside) == 1
	assert aside[0].read_text(encoding="utf-8") == "{ this is not json"
	assert composition.data["grid"]["kick"] == [0, 8], "the file's own seed plays"
	assert any(aside[0].name in record.getMessage()
	           for record in caplog.records if record.levelno >= logging.ERROR)

	composition.running = True
	link._apply("grid/snare/4", True, "panel-1", 1)
	link._keep_now()

	assert _kept(path)["grid"]["rows"]["snare"] == [4]
	assert aside[0].read_text(encoding="utf-8") == "{ this is not json", "never touched again"


def test_a_store_in_a_shape_this_version_does_not_know_is_put_aside_too (
	tmp_path: pathlib.Path, unthreaded: None) -> None:
	"""A later version's file is somebody's work in a shape this cannot read, and
	reading it as though it were this one's is how it would be quietly ruined."""

	path = tmp_path / "piece.patterns.json"
	path.write_text(json.dumps({"format": 99, "controls": {"grid": "?"}}), encoding="utf-8")

	link, composition = _piece(path)
	link.start()

	assert len(list(tmp_path.glob("piece.patterns.json.unreadable-*"))) == 1
	assert composition.data["grid"]["kick"] == [0, 8]


def test_what_the_composition_no_longer_takes_is_refused_and_the_rest_comes_back (
	tmp_path: pathlib.Path, unthreaded: None, caplog: pytest.LogCaptureFixture) -> None:
	"""A composition edited between two starts may no longer take everything the
	store kept — an option renamed, a row dropped, a control gone.  **Each is
	refused on its own and said**, the rest comes back, and the file as it was is
	kept aside whole, so nothing refused is lost for good.
	"""

	path = tmp_path / "piece.patterns.json"

	first, composition = _piece(path)
	first.start()
	composition.running = True
	first._apply("grid/snare/4", True, "panel-1", 1)
	first._apply("synth/rate", 90, "panel-1", 2)
	first._apply("notes/chosen", ["G3", "C3"], "panel-1", 3)
	first._keep_now()

	held = json.loads(path.read_text(encoding="utf-8"))
	held["controls"]["synth"]["mode"] = "sine"
	held["controls"]["grid"]["rows"]["cowbell"] = [2]
	held["controls"]["notes"]["chosen"] = ["G3", "B7", "C3"]
	held["controls"]["gone"] = {"rows": {}}
	path.write_text(json.dumps(held), encoding="utf-8")
	before = path.read_text(encoding="utf-8")

	again, composition = _piece(path)

	with caplog.at_level(logging.WARNING, logger=adapter.LOG.name):
		again.start()

	said = "\n".join(record.getMessage() for record in caplog.records)

	for refused in ("sine", "cowbell", "B7", "gone"):
		assert refused in said, f"{refused} was refused without a word"

	assert composition.data["synth"]["mode"] == "lcr", "the file's own opening"
	assert composition.data["synth"]["rate"] == 90, "and the rest came back"
	assert again.controls["grid"].kept()["rows"]["snare"] == [4], "the rows it still has"
	assert again.controls["notes"].kept()["chosen"] == ["G3", "C3"]

	aside = list(tmp_path.glob("piece.patterns.json.refused-*"))

	assert len(aside) == 1
	assert aside[0].read_text(encoding="utf-8") == before
	assert "cowbell" not in json.dumps(_kept(path)), "the store now says what is playing"


def test_a_restore_that_fails_outright_costs_that_control_and_not_the_start (
	tmp_path: pathlib.Path, unthreaded: None, monkeypatch: pytest.MonkeyPatch,
	caplog: pytest.LogCaptureFixture) -> None:
	"""A store is a file anybody can edit, so a shape nobody foresaw must cost
	the control it names — and never the music, which is what an exception out
	of `start` would cost."""

	path = tmp_path / "piece.patterns.json"

	first, composition = _piece(path)
	first.start()
	composition.running = True
	first._apply("grid/snare/4", True, "panel-1", 1)
	first._apply("synth/rate", 90, "panel-1", 2)
	first._keep_now()

	def explode (self: adapter.StepGrid, kept: typing.Any) -> list[str]:
		raise RuntimeError("nobody foresaw this")

	monkeypatch.setattr(adapter.StepGrid, "restore", explode)

	again, composition = _piece(path)

	with caplog.at_level(logging.WARNING, logger=adapter.LOG.name):
		again.start()

	assert composition.data["synth"]["rate"] == 90, "everything else came back"
	assert "nobody foresaw this" in "\n".join(record.getMessage() for record in caplog.records)


# --- what the store says on the glass ---------------------------------------

@contextlib.contextmanager
def _clock_thread (link: adapter.AppLink) -> typing.Iterator[asyncio.AbstractEventLoop]:
	"""Give the link a clock loop that stays running, as a playing composition's does."""

	loop = asyncio.new_event_loop()
	thread = threading.Thread(target=loop.run_forever, name="clock", daemon=True)
	thread.start()

	link._clock_loop = loop

	try:
		yield loop

	finally:
		loop.call_soon_threadsafe(loop.stop)
		thread.join(timeout=5)
		loop.close()


def _status (link: adapter.AppLink) -> dict[str, typing.Any]:
	"""What the store's own control says about it."""

	assert link.status is not None, "a link with a store has no status"

	return link.status.snapshot()


def test_a_link_with_a_store_offers_its_status_and_one_without_offers_none (
	tmp_path: pathlib.Path) -> None:
	"""Made by the link rather than listed by the composition, so a composition
	that keeps something cannot forget to say so on the glass, and one keeping
	nothing offers nothing."""

	link, _ = _piece(tmp_path / "piece.patterns.json")

	assert link.controls["store"].declaration()["type"] == "store"
	assert link.controls["store"].declaration()["start_again"], "nothing for a panel to ask with"

	bare = adapter.AppLink(Composition(), controls=[])

	assert "store" not in bare.controls


def test_the_name_store_is_the_status_s_and_nobody_else_s (tmp_path: pathlib.Path) -> None:
	"""A composition control called `store` beside a pattern store would be two
	things at one address, and the second would silently shadow the first."""

	composition = Composition()

	with pytest.raises(ValueError, match="already called 'store'"):
		adapter.AppLink(
			composition,
			controls=[adapter.StepGrid(composition, rows=ROWS, name="store", data_key="store")],
			pattern_store=adapter.PatternStore(tmp_path / "piece.patterns.json"))


def test_the_store_says_when_it_last_wrote_and_what_it_started_from (
	tmp_path: pathlib.Path, unthreaded: None) -> None:
	"""The ordinary case, and the one a person reads at a glance: when it last
	kept anything — and after a restart, when the store it started from was."""

	path = tmp_path / "piece.patterns.json"

	first, composition = _piece(path)
	first.start()

	assert _status(first)["kept"] is None, "nothing kept yet"
	assert _status(first)["where"] == str(path)

	composition.running = True
	first._apply("grid/snare/4", True, "panel-1", 1)
	first._keep_now()

	written = json.loads(path.read_text(encoding="utf-8"))["written"]

	assert _status(first)["kept"] == written

	again, _ = _piece(path)
	again.start()

	assert _status(again)["kept"] == written
	assert _status(again)["trouble"] is None


def test_a_store_that_could_not_be_read_says_so_on_the_glass (
	tmp_path: pathlib.Path, unthreaded: None) -> None:
	"""**The gap this control was chosen to close.**  Moved aside and logged, the
	piece starting as its file says — which on the glass looked exactly like a
	piece nobody had ever touched."""

	path = tmp_path / "piece.patterns.json"
	path.write_text("{ this is not json", encoding="utf-8")

	link, _ = _piece(path)
	link.start()

	said = _status(link)

	assert said["trouble"] and "could not be read" in said["trouble"]
	assert said["aside"] == str(next(tmp_path.glob("piece.patterns.json.unreadable-*")))


def test_what_the_store_held_and_was_refused_is_said_on_the_glass (
	tmp_path: pathlib.Path, unthreaded: None) -> None:
	"""Each refusal in the app's own words, and where the whole store went."""

	path = tmp_path / "piece.patterns.json"

	first, composition = _piece(path)
	first.start()
	composition.running = True
	first._apply("synth/rate", 90, "panel-1", 1)
	first._keep_now()

	held = json.loads(path.read_text(encoding="utf-8"))
	held["controls"]["synth"]["mode"] = "sine"
	path.write_text(json.dumps(held), encoding="utf-8")

	again, _ = _piece(path)
	again.start()

	said = _status(again)

	assert said["trouble"] == "1 thing the store held could not be put back"
	assert len(said["refused"]) == 1 and "sine" in said["refused"][0]
	assert said["aside"] == str(next(tmp_path.glob("piece.patterns.json.refused-*")))


def test_what_the_store_says_reaches_the_glass_from_the_clock_loop (
	tmp_path: pathlib.Path, unthreaded: None) -> None:
	"""A save finishes on a worker, and a change is numbered and sent on the
	clock loop: reporting from the worker would number two frames at once when a
	tap landed at the same moment."""

	path = tmp_path / "piece.patterns.json"
	link, composition = _piece(path)
	link.start()
	composition.running = True

	sent: list[tuple[typing.Any, threading.Thread]] = []

	def heard (frame: dict[str, typing.Any]) -> None:
		"""Note each frame and the thread that sent it, instead of sending it."""

		sent.append((frame, threading.current_thread()))

	link._emit = heard  # type: ignore[method-assign]

	with _clock_thread(link):
		link._apply("grid/snare/4", True, "panel-1", 1)
		link._keep_now()

		deadline = time.monotonic() + 5

		while not any(frame.get("path") == "store/kept" for frame, _ in sent) \
				and time.monotonic() < deadline:
			time.sleep(0.01)

	kept = [(frame, thread) for frame, thread in sent if frame.get("path") == "store/kept"]

	assert kept, "the glass was never told the store had written"
	assert kept[0][0]["v"] == _status(link)["kept"]
	assert kept[0][1].name == "clock"


def test_a_failed_save_says_why_until_one_succeeds (
	tmp_path: pathlib.Path, unthreaded: None, monkeypatch: pytest.MonkeyPatch) -> None:
	"""A disk that is full or has gone is the other thing a log used to be the
	only one to know about."""

	path = tmp_path / "piece.patterns.json"
	link, composition = _piece(path)
	link.start()
	composition.running = True

	real = adapter.PatternStore.save

	def full (store: adapter.PatternStore, controls: dict[str, typing.Any]) -> str | None:
		raise OSError(28, "No space left on device")

	monkeypatch.setattr(adapter.PatternStore, "save", full)
	link._apply("grid/snare/4", True, "panel-1", 1)
	link._keep_now()

	assert "No space left on device" in (_status(link)["unwritten"] or "")

	monkeypatch.setattr(adapter.PatternStore, "save", real)
	link._keep_now()

	assert _status(link)["unwritten"] is None
	assert _status(link)["kept"] is not None


def test_starting_again_is_a_press_on_the_store_and_is_remembered_by_nobody (
	tmp_path: pathlib.Path, unthreaded: None) -> None:
	"""A panel asks with `store/start_again`; the app does it and declares again.

	Nothing is *remembered* for the press, because nothing holds it (#2179) — so
	no `changed` frame, which is the service's cue to keep a value.  It is still
	**answered**, with an `ack` naming the path (#2502): a press nothing replies
	to sat out its five-second expiry on the glass and was then recorded as a
	failure, for the one control here whose whole job is to be pressed once.
	"""

	path = tmp_path / "piece.patterns.json"
	link, composition = _piece(path)
	link.start()
	composition.running = True

	sent: list[typing.Any] = []
	link._emit = sent.append  # type: ignore[assignment, method-assign]

	link._apply("grid/rows", {}, "panel-1", 1)
	sent.clear()

	link._apply("store/start_again", True, "panel-1", 2)

	assert composition.data["grid"]["kick"] == [0, 8], "the file's seed is back"
	assert [frame["t"] for frame in sent if frame.get("path") == "store/start_again"] == ["ack"], (
		f"the press was answered with {[frame['t'] for frame in sent]}, and a `changed` "
		f"among them would be the service keeping a value nothing holds")

	link._apply("store/start_again", "please", "panel-1", 3)

	assert sent[-1]["t"] == "nack", "anything but a press is refused, with a reason"


# --- starting again from the file -------------------------------------------

def test_starting_again_puts_back_what_the_file_seeds_and_puts_the_store_aside (
	tmp_path: pathlib.Path, unthreaded: None) -> None:
	"""**The way back to the composition as written**, once a store has taken over
	from it (#2487).  Every control goes back to what the file seeds, the grids
	a person made go, mutes lift, and the instruments are told their settings
	again — and the store is moved aside rather than deleted, so the next start
	is the file's too until somebody edits something.
	"""

	path = tmp_path / "piece.patterns.json"

	first, composition = _piece(path)
	first.start()
	composition.running = True
	_edit_everything(first)
	first._keep_now()

	again, composition = _piece(path)
	again.start()
	composition.running = True
	_on_a_loop(lambda: again._on_beat(0))

	assert composition.muted == {"drums", "bass"}

	fresh, _ = _piece(tmp_path / "never.patterns.json")
	fresh.start()

	# Told everything once already, as the first beat would have paid it.
	again.controls["synth"].settled()

	with _link_thread(again):
		_on_a_loop(again.start_again)

		deadline = time.monotonic() + 5

		while path.exists() and time.monotonic() < deadline:
			time.sleep(0.01)

	for name, control in fresh.controls.items():
		if name == "transport":
			continue

		assert again.controls[name].kept() == control.kept(), f"{name} is not as the file seeds it"

	assert "rack-a" not in again.controls, "the grid somebody made has gone"
	assert composition.muted == set()
	assert again.controls["synth"].owed(), "the instrument is told its settings again"

	assert not path.exists()
	assert len(list(tmp_path.glob("piece.patterns.json.started-again-*"))) == 1
