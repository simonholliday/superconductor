"""The Subsequence side: what a tap does to the grid, on the composition's loop."""

import asyncio
import threading
import typing

import pytest

import superintendent.protocol
import superintendent.subsequence_adapter


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


def _link () -> tuple[superintendent.subsequence_adapter.AppLink, list[superintendent.protocol.Frame]]:
	"""A link over a fake composition, with everything it would send recorded."""

	composition = FakeComposition()
	link = superintendent.subsequence_adapter.AppLink(
		composition,
		controls=[
			superintendent.subsequence_adapter.StepGrid(composition, rows=ROWS, steps=16),
			superintendent.subsequence_adapter.Transport(composition),
		],
	)
	sent: list[superintendent.protocol.Frame] = []

	link._emit = sent.append  # type: ignore[method-assign]

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


def _transport () -> tuple[superintendent.subsequence_adapter.Transport, FakeComposition]:
	"""A transport over a composition that can hold its clock."""

	composition = FakeComposition()

	return superintendent.subsequence_adapter.Transport(composition), composition


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

	with pytest.raises(superintendent.subsequence_adapter.Refused):
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

	with pytest.raises(superintendent.subsequence_adapter.Refused):
		transport.apply(["bpm"], 5000)

	with pytest.raises(superintendent.subsequence_adapter.Refused):
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

	transport = superintendent.subsequence_adapter.Transport(WithoutPause())

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
	grid = superintendent.subsequence_adapter.StepGrid(
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

	grid = superintendent.subsequence_adapter.StepGrid(
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

	with pytest.raises(superintendent.subsequence_adapter.Refused):
		transport.apply(["tempo"], 120.0)

	with pytest.raises(superintendent.subsequence_adapter.Refused):
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

	transport = superintendent.subsequence_adapter.Transport(WithoutPause())

	with pytest.raises(superintendent.subsequence_adapter.Refused):
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
	link = superintendent.subsequence_adapter.AppLink(
		composition,
		controls=[
			superintendent.subsequence_adapter.NoteGrid(
				composition, rows=["C2"], steps=12, beats=3, data_key="bass", name="bass"),
		],
	)

	sent: list[superintendent.protocol.Frame] = []
	link._emit = sent.append  # type: ignore[method-assign]
	link._clock_loop = asyncio.new_event_loop()

	try:
		link._on_beat(1)

	finally:
		link._clock_loop.close()

	beats = [one for one in sent if one.get("t") == "event" and one.get("name") == "beat"]

	assert beats, f"no beat event was sent: {sent}"
	assert beats[-1]["steps"] == 12, beats[-1]
	assert beats[-1]["beats"] == 3, beats[-1]
