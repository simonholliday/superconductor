"""The Subsequence side: what a tap does to the grid, on the composition's loop."""

import asyncio
import threading
import time
import typing

import pytest

import superconductor.protocol
import superconductor.subsequence_adapter


ROWS = ["kick", "snare"]


class FakeSequencer:
	"""The little of a sequencer a transport reads."""

	def __init__ (self) -> None:
		"""Start stopped, at no tempo."""

		self.current_bpm = 0.0


class FakePattern:
	"""A running pattern, which is only ever asked whether it is muted."""

	def __init__ (self) -> None:
		"""Start unmuted."""

		self._muted = False


class FakeComposition:
	"""A composition with the few things a link uses and nothing else.

	That a link needs so little of one is the point: no part of the Subsequence
	package is changed to make this work.
	"""

	def __init__ (self) -> None:
		"""Start with an empty grid, two patterns and no listeners."""

		self.data: dict[str, typing.Any] = {}
		self.listeners: dict[str, typing.Any] = {}
		self.sequencer = FakeSequencer()
		self.running_patterns: dict[str, FakePattern] = {"drums": FakePattern(), "bass": FakePattern()}
		self.bpm_set_to: list[float] = []
		self.is_paused = False
		self.refuses_pause = False

	def on_event (self, name: str, callback: typing.Any) -> None:
		"""Register a callback the way the real composition does."""

		self.listeners[name] = callback

	def mute (self, name: str) -> None:
		"""Mute one pattern by name."""

		self.running_patterns[name]._muted = True

	def unmute (self, name: str) -> None:
		"""Bring one pattern back."""

		self.running_patterns[name]._muted = False

	def set_bpm (self, bpm: float) -> None:
		"""Take a tempo the way the real composition does."""

		self.bpm_set_to.append(bpm)
		self.sequencer.current_bpm = bpm

	def pause (self) -> None:
		"""Hold the clock, unless this composition is set to refuse.

		Refusing silently is what the real one does when the pulse is not its
		to hold — under an external clock or an Ableton Link session.
		"""

		if not self.refuses_pause:
			self.is_paused = True

	def resume (self) -> None:
		"""Let the clock go again."""

		if not self.refuses_pause:
			self.is_paused = False


def _link () -> tuple[superconductor.subsequence_adapter.AppLink, list[superconductor.protocol.Frame]]:
	"""A link over a fake composition, with everything it would send recorded."""

	composition = FakeComposition()
	link = superconductor.subsequence_adapter.AppLink(
		composition,
		controls=[
			superconductor.subsequence_adapter.StepGrid(composition, rows=ROWS, steps=16),
			superconductor.subsequence_adapter.Transport(composition),
		],
	)
	sent: list[superconductor.protocol.Frame] = []

	link._emit = sent.append  # type: ignore[assignment, method-assign]

	return link, sent


def test_a_tap_switches_the_step_on_the_grid () -> None:
	"""Which is a plain dict on composition.data, read by the pattern builder."""

	link, _ = _link()

	link._apply("grid/kick/4", True, "panel-1", 1)
	link._apply("grid/kick/0", True, "panel-1", 2)

	assert link.composition.data["grid"]["kick"] == [0, 4]


def test_switching_a_step_off_removes_it () -> None:
	"""And a value applied twice leaves the same grid as applying it once."""

	link, _ = _link()

	link._apply("grid/kick/4", True, "panel-1", 1)
	link._apply("grid/kick/4", False, "panel-1", 2)
	link._apply("grid/kick/4", False, "panel-1", 3)

	assert link.composition.data["grid"]["kick"] == []


def test_what_was_applied_is_reported_with_the_tap_that_asked_for_it () -> None:
	"""That report is what clears the ring under the finger."""

	link, sent = _link()

	link._apply("grid/snare/12", True, "panel-1", 7)

	assert sent[0]["t"] == "changed"
	assert sent[0]["path"] == "grid/snare/12"
	assert sent[0]["by"] == "panel"
	assert sent[0]["client"] == "panel-1"
	assert sent[0]["seq"] == 7


def test_the_version_moves_with_every_change () -> None:
	"""So a panel can tell an answer to its own tap from a later one."""

	link, sent = _link()

	link._apply("grid/kick/0", True, "panel-1", 1)
	link._apply("grid/kick/1", True, "panel-1", 2)

	assert [frame["ver"] for frame in sent] == [1, 2]


def test_a_cell_outside_the_grid_is_refused_with_a_reason () -> None:
	"""The declaration is the boundary, and the person who tapped is told why.

	A panel holding a declaration older than the app's is exactly what a
	reconnect produces, so this is reachable rather than theoretical — and a
	request that vanished silently would sit pending until it timed out.
	"""

	link, sent = _link()

	link._apply("grid/cowbell/4", True, "panel-1", 1)
	link._apply("grid/kick/99", True, "panel-1", 2)

	assert link.composition.data.get("grid", {}) == {}
	assert [frame["t"] for frame in sent] == ["nack", "nack"]
	assert "cowbell" in sent[0]["reason"]
	assert "16 steps wide" in sent[1]["reason"]


def test_an_address_naming_no_control_here_is_dropped_rather_than_refused () -> None:
	"""It is not a refusal by this app: nothing here was ever asked."""

	link, sent = _link()

	link._apply("mixer/kick/4", True, "panel-1", 1)
	link._apply("nonsense", True, "panel-1", 2)

	assert sent == []


def _on_a_loop (work: typing.Callable[[], None]) -> None:
	"""Run something inside a running event loop, on a thread of its own.

	Which is what the composition's clock is — a loop on a thread that is not
	this one — so this is the honest arrangement as well as the workable one.
	It has to be a separate thread because by the time these run, the browser
	the page tests opened is holding a loop on this one, and a second cannot be
	started inside it.
	"""

	def run () -> None:
		asyncio.run(_as_coroutine(work))

	thread = threading.Thread(target=run)
	thread.start()
	thread.join(timeout=5)

	assert not thread.is_alive(), "the work never finished"


async def _as_coroutine (work: typing.Callable[[], None]) -> None:
	"""Give *work* a running loop to find with asyncio.get_running_loop()."""

	work()


def test_the_first_beat_is_where_the_clock_loop_is_found () -> None:
	"""Public events reach the loop, so no private name has to be read."""

	link, sent = _link()

	_on_a_loop(lambda: link._on_beat(0))

	assert link._clock_loop is not None
	assert sent[0]["name"] == "beat"


def test_a_beat_carries_what_the_playhead_needs_to_place_itself () -> None:
	"""The gap between two beats is what the highlight moves across."""

	link, sent = _link()

	def two_beats () -> None:
		link._on_beat(0)
		link._on_beat(1)

	_on_a_loop(two_beats)

	assert sent[0]["interval"] is None
	assert sent[1]["interval"] is not None
	assert sent[1]["steps"] == 16
	assert sent[1]["beats"] == 4


def test_the_grid_is_offered_whole_with_every_row_named () -> None:
	"""A row nobody has touched is empty rather than absent."""

	link, _ = _link()

	link._apply("grid/kick/4", True, "panel-1", 1)

	assert link.controls["grid"].snapshot() == {"kick": [4], "snare": [], "enabled": True}


def _transport () -> tuple[superconductor.subsequence_adapter.Transport, FakeComposition]:
	"""A transport over a composition that can hold its clock."""

	composition = FakeComposition()

	return superconductor.subsequence_adapter.Transport(composition), composition


def test_pausing_asks_the_composition_to_hold_its_clock () -> None:
	"""Which keeps the position, unlike stopping."""

	transport, composition = _transport()

	transport.apply(["paused"], True)

	assert composition.is_paused is True


def test_the_face_is_not_moved_by_the_asking () -> None:
	"""It moves on the composition's own pause event, once the clock really stopped."""

	transport, _ = _transport()

	assert transport.apply(["paused"], True) is False


def test_a_refused_pause_is_reported_rather_than_left_waiting () -> None:
	"""Subsequence refuses silently and sends no event, so the read-back is the only signal."""

	transport, composition = _transport()
	composition.refuses_pause = True

	with pytest.raises(superconductor.subsequence_adapter.Refused):
		transport.apply(["paused"], True)


def test_pausing_twice_asks_nothing_the_second_time () -> None:
	"""So a re-send after a reconnect cannot disturb a transport already held."""

	transport, _ = _transport()

	transport.apply(["paused"], True)

	assert transport.apply(["paused"], True) is False


def test_the_transport_reports_what_the_composition_did () -> None:
	"""Including a pause nobody on the glass asked for."""

	transport, composition = _transport()
	reported: list[tuple[str, typing.Any]] = []

	class Link:
		"""Stands in for the link, keeping what it was told."""

		def report (self, path: str, value: typing.Any) -> None:
			"""Keep one report."""

			reported.append((path, value))

	transport.attach(Link())  # type: ignore[arg-type]
	composition.listeners["pause"]()

	assert reported == [("transport/paused", True)]


def test_a_tempo_is_passed_through_and_one_outside_the_range_is_refused () -> None:
	"""The range is declared, so the panel knows it before it asks."""

	transport, composition = _transport()

	assert transport.apply(["bpm"], 137.5) is True
	assert composition.bpm_set_to == [137.5]

	with pytest.raises(superconductor.subsequence_adapter.Refused):
		transport.apply(["bpm"], 5000)

	with pytest.raises(superconductor.subsequence_adapter.Refused):
		transport.apply(["bpm"], "quickly")


def test_a_tempo_the_composition_changed_itself_is_reported () -> None:
	"""So the panel shows the tempo the sequencer holds, not the last one tapped."""

	transport, composition = _transport()

	composition.sequencer.current_bpm = 128.0

	assert transport.poll() == [("transport/bpm", 128.0)]
	assert transport.poll() == []


def test_the_transport_declares_what_a_panel_needs_to_draw_it () -> None:
	"""Its fields and the tempo range, so nothing about it is hard-coded on the glass."""

	transport, _ = _transport()

	declaration = transport.declaration()

	assert declaration["type"] == "transport"
	assert declaration["fields"] == ["paused", "bpm"]
	assert declaration["tempo_range"] == [40.0, 240.0]


def test_a_composition_that_cannot_pause_does_not_offer_the_field () -> None:
	"""An older Subsequence loses the button rather than gaining a broken one."""

	class WithoutPause (FakeComposition):
		"""A composition from before the transport could be held."""

		pause = None  # type: ignore[assignment]
		resume = None  # type: ignore[assignment]

	transport = superconductor.subsequence_adapter.Transport(WithoutPause())

	assert transport.declaration()["fields"] == ["bpm"]
	assert "paused" not in transport.snapshot()


def test_a_grid_that_drives_a_pattern_mutes_it () -> None:
	"""A mute in the sense a mixer means it: the notes stay where they are and
	stop being heard, which is what makes it reversible without loss.

	Everything the pattern plays, its stack of contributions included — "off"
	means this instrument is silent, not "off except for the algorithms".
	"""

	class Muting:
		"""A composition that writes down what it was asked to silence."""

		def __init__ (self) -> None:
			"""Start with nothing muted."""

			self.data: dict[str, typing.Any] = {}
			self.silenced: list[tuple[str, str]] = []

		def mute (self, name: str) -> None:
			"""Silence one pattern."""

			self.silenced.append(("mute", name))

		def unmute (self, name: str) -> None:
			"""Bring it back."""

			self.silenced.append(("unmute", name))

	composition = Muting()
	grid = superconductor.subsequence_adapter.StepGrid(
		composition, rows=["kick"], name="grid", pattern="drums")

	assert grid.apply(["enabled"], False) is True
	assert grid.enabled is False
	assert composition.silenced == [("mute", "drums")]

	# Setting it to what it already is changes nothing and says nothing.
	assert grid.apply(["enabled"], False) is False
	assert composition.silenced == [("mute", "drums")]

	assert grid.apply(["enabled"], True) is True
	assert composition.silenced == [("mute", "drums"), ("unmute", "drums")]


def test_a_composition_that_cannot_mute_is_not_an_error () -> None:
	"""What is lost is the half that was never this package's to do.  The flag
	is still kept and still honoured everywhere this package does the playing."""

	class Old:
		"""A composition from before mute."""

		def __init__ (self) -> None:
			"""Just the dict."""

			self.data: dict[str, typing.Any] = {}

	grid = superconductor.subsequence_adapter.StepGrid(
		Old(), rows=["kick"], name="grid", pattern="drums")

	assert grid.apply(["enabled"], False) is True
	assert grid.enabled is False


def test_a_transport_refuses_a_field_it_does_not_have () -> None:
	"""`False` means "nothing changed", which is the wrong answer for "there is
	no such thing".

	Returning it emitted nothing at all, so the panel's request sat pending for
	the full five seconds and then flashed as a failure with no reason given.
	Every other control raises `Refused` and the panel says why; this one went
	quiet.  It is the first review's finding about `StepGrid.apply`, fixed there
	and still true here.
	"""

	transport, _ = _transport()

	with pytest.raises(superconductor.subsequence_adapter.Refused):
		transport.apply(["tempo"], 120.0)

	with pytest.raises(superconductor.subsequence_adapter.Refused):
		transport.apply(["bpm", "extra"], 120.0)

	# And "nothing changed" is still allowed to mean exactly that.
	assert transport.apply(["paused"], False) is False


def test_a_composition_that_cannot_pause_says_so_rather_than_ignoring_it () -> None:
	"""The button is not declared, so this is only reachable by a stale panel —
	which is precisely when a silent refusal is hardest to work out."""

	class WithoutPause (FakeComposition):
		"""A composition from before the transport could be held."""

		pause = None  # type: ignore[assignment]
		resume = None  # type: ignore[assignment]

	transport = superconductor.subsequence_adapter.Transport(WithoutPause())

	with pytest.raises(superconductor.subsequence_adapter.Refused):
		transport.apply(["paused"], True)


def test_a_beat_carries_a_pitched_grid_s_geometry_when_that_is_all_there_is () -> None:
	"""The transport counter is driven by `steps` and `beats` on the beat event.

	Only a `StepGrid` was looked for, so a composition offering pitched patterns
	and nothing else sent `steps=None, beats=None` and the counter drew nothing
	at all, with nothing anywhere saying why.

	**Synchronous, and the loop is handed over rather than borrowed.**
	`_on_beat` captures the clock loop from the first beat it sees, so the
	obvious way to write this is as an async test — and an async test in this
	file fails, because `test_page.py` sorts before it and Playwright's sync API
	holds a running loop on the main thread for the rest of the session, which
	`Runner.run()` cannot start inside.  It passes alone and fails in the suite,
	which is the worst way for a test to be wrong.  The loop here is never run;
	it is only the thing the link records.
	"""

	composition = FakeComposition()
	link = superconductor.subsequence_adapter.AppLink(
		composition,
		controls=[
			superconductor.subsequence_adapter.NoteGrid(
				composition, rows=["C2"], steps=12, beats=3, data_key="bass", name="bass"),
		],
	)

	sent: list[superconductor.protocol.Frame] = []
	link._emit = sent.append  # type: ignore[assignment, method-assign]
	link._clock_loop = asyncio.new_event_loop()

	try:
		link._on_beat(1)

	finally:
		link._clock_loop.close()

	beats = [one for one in sent if one.get("t") == "event" and one.get("name") == "beat"]

	assert beats, f"no beat event was sent: {sent}"
	assert beats[-1]["steps"] == 12, beats[-1]
	assert beats[-1]["beats"] == 3, beats[-1]


def test_a_beat_hands_the_settings_burst_over_rather_than_doing_it () -> None:
	"""The clock loop asks what is owed; the link thread pays it.

	Measured before it was moved: the adapter's own cost in the burst is 0.012 ms
	and free, and the cost is one `composition.trigger()` per setting — ten for
	the Minitaur as `compositions/drm1_grid.py` declares it, thirty-six for a
	Matriarch.  That is linear in a number this project is deliberately
	increasing, on a callback with about 20 ms of headroom before it delays the
	next pulse, and it was the one path on the timing loop with no measurement
	behind it.

	Simon's rule of 2026-09-06 decides it: the clock must remain solid at all
	costs, so an unmeasured cost on the timing path is one to remove.  It is
	still *asked for* on a beat, because a beat is how this knows the clock is
	running, and `composition.trigger` is documented as the thread-safe way in.
	"""

	composition = FakeComposition()
	told: list[tuple[str, typing.Any]] = []

	settings = superconductor.subsequence_adapter.Params(
		composition,
		parameters=[superconductor.subsequence_adapter.Parameter("glide", "switch", default=False)],
		data_key="moog", name="moog",
		on_change=lambda name, value: told.append((name, value)))

	composition.data["moog"] = {"glide": True}

	link = superconductor.subsequence_adapter.AppLink(composition, controls=[settings])
	link._emit = lambda frame: None  # type: ignore[method-assign]

	settings.declared()

	# A link thread of its own, running, because that is what the work is handed
	# to. Not an async test: an async test in this file fails once test_page.py
	# has run, and this needs a loop either way.
	loop = asyncio.new_event_loop()
	thread = threading.Thread(target=loop.run_forever, daemon=True)
	thread.start()

	try:
		link._link_loop = loop
		link._clock_loop = loop

		link._on_beat(1)

		# The beat itself must not have told the instrument anything.
		assert told == [], f"the clock loop paid the burst inline: {told}"

		deadline = time.monotonic() + 5.0

		while not told and time.monotonic() < deadline:
			time.sleep(0.01)

		assert told == [("glide", True)], f"the link thread never paid it: {told}"

		# And once only, however many beats follow.
		told.clear()
		link._on_beat(2)
		time.sleep(0.2)

		assert told == [], "the burst was paid a second time"

	finally:
		loop.call_soon_threadsafe(loop.stop)
		thread.join(timeout=5.0)
		loop.close()


def _link_with_no_thread () -> superconductor.subsequence_adapter.AppLink:
	"""An app link that has never dialled, for testing what it queues.

	`_queue` is deliberately separate from `_emit` so this is possible: the
	decision about what supersedes what has nothing to do with a socket, and a
	test that needed a link thread to reach it would be testing asyncio.
	"""

	return superconductor.subsequence_adapter.AppLink(
		FakeComposition(), controls=[], app_name="app")


def test_an_event_about_a_control_supersedes_one_still_waiting () -> None:
	"""#2242.  Two waiting together are not two facts, they are one and a stale copy.

	An event is what the music did this cycle and nothing keeps it (#1965), so
	the older is untrue the moment the newer arrives — and drawing the stale one
	is worse than drawing neither.
	"""

	link = _link_with_no_thread()

	link._queue(superconductor.protocol.event("app", "realised", control="grid", cells={"a": 1}))
	link._queue(superconductor.protocol.event("app", "realised", control="grid", cells={"a": 2}))

	assert len(link._outbound) == 1

	(_, frame), = link._outbound.items()

	assert frame["cells"] == {"a": 2}, "the stale copy won"


def test_an_event_about_another_control_supersedes_nothing () -> None:
	"""Two grids realising in one cycle are two facts, not one."""

	link = _link_with_no_thread()

	link._queue(superconductor.protocol.event("app", "realised", control="grid", cells={}))
	link._queue(superconductor.protocol.event("app", "realised", control="bass", cells={}))

	assert len(link._outbound) == 2


def test_a_change_never_supersedes_anything () -> None:
	"""A change is intent and is kept (#1965); an ack is what a hand is waiting for.

	Merging two of those loses something nobody can get back, which is why the
	rule is written about events rather than about frames.
	"""

	link = _link_with_no_thread()

	for step in range(5):
		link._queue(superconductor.protocol.changed(
			"app", "grid/kick/0", step, step, by="app"))

	assert len(link._outbound) == 5


def test_a_burst_drops_the_oldest_and_keeps_the_newest () -> None:
	"""The queue is what a socket has not taken yet, so the newest is still true.

	Dropping the newest would mean the panel's last word about a control was
	whatever it happened to receive before the burst — which is the failure that
	took the rig down wearing different clothes.
	"""

	link = _link_with_no_thread()

	for step in range(superconductor.subsequence_adapter.OUTBOUND_CAP + 50):
		link._queue(superconductor.protocol.changed(
			"app", "grid/kick/0", step, step, by="app"))

	assert len(link._outbound) == superconductor.subsequence_adapter.OUTBOUND_CAP
	assert link._dropped == 50

	newest = list(link._outbound.values())[-1]

	assert newest["v"] == superconductor.subsequence_adapter.OUTBOUND_CAP + 49, "the newest frame was the one dropped"


def test_a_superseded_frame_keeps_its_place_rather_than_jumping_the_queue () -> None:
	"""It occupies the slot it would have had, so it does not overtake a change
	that was already waiting behind it."""

	link = _link_with_no_thread()

	link._queue(superconductor.protocol.event("app", "realised", control="grid", cells={"a": 1}))
	link._queue(superconductor.protocol.changed("app", "grid/kick/0", True, 1, by="app"))
	link._queue(superconductor.protocol.event("app", "realised", control="grid", cells={"a": 2}))

	kinds = [frame["t"] for frame in link._outbound.values()]

	assert kinds == ["event", "changed"], f"the queue reordered itself: {kinds}"


class _NoThread:
	"""A thread that is never started, so `start` can be exercised on its own.

	The link's own thread dials a real socket, and on this machine port 8090
	is usually the running rig — so a test that started it would reach out of
	the suite and into the studio.
	"""

	def __init__ (self, **rest: typing.Any) -> None:
		"""Take what a real thread takes, and keep none of it."""

	def start (self) -> None:
		"""Do nothing, which is the whole point."""


def test_starting_a_link_survives_a_control_that_registers_more_controls (
	monkeypatch: pytest.MonkeyPatch) -> None:
	"""A rack puts back the grids somebody made before this started (#2226), and
	each becomes a control on this link — so attaching one grows the very dict
	`start` is walking, and Python raises rather than quietly missing one.

	**It cannot fire until a grid has been made and the app started again**,
	which is why it outlived the rack landing: the rig ran for eight hours with
	an empty rack, Simon made a grid on the glass, and the next start died.
	Nothing in the suite had ever started a link with a rack that already held
	something.

	The rack calls `attach` on every grid it materialises, so walking a snapshot
	loses nothing.
	"""

	composition = FakeComposition()
	rack = superconductor.subsequence_adapter.GridRack(
		composition,
		make=lambda spec: superconductor.subsequence_adapter.StepGrid(
			composition, rows=spec["rows"], steps=spec["steps"],
			data_key=spec["name"], name=spec["name"]),
		rows=ROWS, data_key="rack", name="rack")

	# What a page store puts back: one grid, made before any of this started.
	composition.data["rack"] = {"grids": [{"id": "a", "rows": ["kick"], "steps": 8}]}

	link = superconductor.subsequence_adapter.AppLink(composition, controls=[rack])

	monkeypatch.setattr(
		superconductor.subsequence_adapter.threading, "Thread", _NoThread)

	link.start()

	assert rack.link is link, "the walk never reached the rack"
	assert "rack-a" in link.controls, "the grid the rack put back never reached the link"
	assert rack.made() == ["rack-a"], "the rack does not know what it put there"


def test_a_request_that_changed_nothing_is_still_answered () -> None:
	"""**Everything the app accepted gets an answer** (#2502).

	`_apply` returned in silence when a control reported that nothing moved, so
	the service had no `changed` frame to acknowledge and sent no `ack`.  The
	panel's ring then sat out its five-second expiry and recorded a success as a
	failure — and the request stayed in the map that a reconnect re-sends, which
	for an action means doing it twice.

	Answered with an `ack` naming the path, because no `changed` travels beside
	it to say which cell it was for.
	"""

	link, sent = _link()

	link._apply("grid/kick/4", True, "panel-1", 1)

	assert [frame["t"] for frame in sent] == ["changed"], "a change is answered by the change"

	sent.clear()

	link._apply("grid/kick/4", True, "panel-1", 2)

	assert [frame["t"] for frame in sent] == ["ack"], f"a request that moved nothing sent {sent}"
	assert sent[0]["path"] == "grid/kick/4"
	assert (sent[0]["client"], sent[0]["seq"]) == ("panel-1", 2)


def test_an_action_is_answered_although_it_keeps_nothing () -> None:
	"""The case #2502 was found on: an action holds nothing by design (#2179), so
	it can never report a change, and every press of one went unanswered."""

	composition = FakeComposition()
	told: list[tuple[str, typing.Any]] = []

	settings = superconductor.subsequence_adapter.Params(
		composition,
		parameters=[superconductor.subsequence_adapter.Parameter(
			"voicing", "action", label="Set voicing",
			options=[("one", "1"), ("four", "4")])],
		data_key="moog", name="moog",
		on_change=lambda name, value: told.append((name, value)))

	link = superconductor.subsequence_adapter.AppLink(composition, controls=[settings])
	sent: list[superconductor.protocol.Frame] = []

	link._emit = sent.append  # type: ignore[assignment, method-assign]

	link._apply("moog/voicing", "four", "panel-1", 3)

	assert told == [("voicing", "four")], "the composition was never told to act"
	assert [frame["t"] for frame in sent] == ["ack"], f"the press was answered with {sent}"
	assert sent[0]["path"] == "moog/voicing", "the ack must name what it answers"
	assert "voicing" not in composition.data.get("moog", {}), "an action kept a value (#2179)"


def test_a_change_to_what_an_app_offers_is_made_on_the_link_loop () -> None:
	"""**Where the declaration is built** (#2341), so the two cannot interleave.

	`_declare` walks `self.controls` four times on the link loop.  Anything that
	resizes that dict from another thread can kill a declare that is in flight,
	and a rack making a grid did exactly that from the clock loop.  Snapshotting
	the walks would have removed the exception and left a declaration describing
	half of one mutation; running the change on the loop that declares removes the
	question.
	"""

	link = superconductor.subsequence_adapter.AppLink(FakeComposition(), controls=[])
	ran: list[str] = []

	loop = asyncio.new_event_loop()
	thread = threading.Thread(target=loop.run_forever, name="link-loop-under-test", daemon=True)

	thread.start()

	try:
		link._link_loop = loop

		link.alter(lambda: ran.append(threading.current_thread().name))

		# The loop's next piece of work cannot begin before the one queued ahead
		# of it has finished, so this waits for the change without racing it.
		asyncio.run_coroutine_threadsafe(asyncio.sleep(0), loop).result(timeout=5)

		assert ran == ["link-loop-under-test"], (
			f"the change was made on {ran}, and the declare walks that dict on the link loop")

	finally:
		loop.call_soon_threadsafe(loop.stop)
		thread.join(timeout=5.0)


def test_a_change_before_the_link_thread_exists_is_made_where_it_stands () -> None:
	"""`start()` attaches every control before the thread is running, and a rack
	puts back the grids somebody made as it attaches (#2226).  There is nothing to
	hand it to yet — and nothing else running that could see half of it."""

	link = superconductor.subsequence_adapter.AppLink(FakeComposition(), controls=[])
	ran: list[str] = []

	link.alter(lambda: ran.append(threading.current_thread().name))

	assert ran == [threading.current_thread().name], "a change was deferred to nowhere"
