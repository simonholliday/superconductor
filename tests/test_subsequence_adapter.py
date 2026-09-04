"""The Subsequence side: what a tap does to the grid, on the composition's loop."""

import typing

import superintendent.protocol
import superintendent.subsequence_adapter


ROWS = ["kick", "snare"]


class FakeComposition:
	"""A composition with the two things the link uses and nothing else.

	That the link needs so little of one is the point: no part of the
	Subsequence package is changed to make this work.
	"""

	def __init__ (self) -> None:
		"""Start with an empty grid and no listeners."""

		self.data: dict[str, typing.Any] = {}
		self.listeners: dict[str, typing.Any] = {}

	def on_event (self, name: str, callback: typing.Any) -> None:
		"""Register a callback the way the real composition does."""

		self.listeners[name] = callback


def _link () -> tuple[superintendent.subsequence_adapter.GridLink, list[superintendent.protocol.Frame]]:
	"""A link over a fake composition, with everything it would send recorded."""

	link = superintendent.subsequence_adapter.GridLink(FakeComposition(), rows=ROWS, steps=16)
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


def test_a_cell_outside_the_grid_is_ignored_and_reported_to_nobody () -> None:
	"""The declaration is the boundary, and a bad address never reaches the dict."""

	link, sent = _link()

	link._apply("grid/cowbell/4", True, "panel-1", 1)
	link._apply("grid/kick/99", True, "panel-1", 2)
	link._apply("mixer/kick/4", True, "panel-1", 3)
	link._apply("nonsense", True, "panel-1", 4)

	assert link.composition.data.get("grid", {}) == {}
	assert sent == []


async def test_the_first_beat_is_where_the_clock_loop_is_found () -> None:
	"""Public events reach the loop, so no private name has to be read."""

	link, sent = _link()
	link.start = lambda: None  # type: ignore[method-assign]

	link._on_beat(0)

	assert link._clock_loop is not None
	assert sent[0]["name"] == "beat"


async def test_a_beat_carries_what_the_playhead_needs_to_place_itself () -> None:
	"""The gap between two beats is what the highlight moves across."""

	link, sent = _link()

	link._on_beat(0)
	link._on_beat(1)

	assert sent[0]["interval"] is None
	assert sent[1]["interval"] is not None
	assert sent[1]["steps"] == 16
	assert sent[1]["beats"] == 4


def test_the_grid_is_offered_whole_with_every_row_named () -> None:
	"""A row nobody has touched is empty rather than absent."""

	link, _ = _link()

	link._apply("grid/kick/4", True, "panel-1", 1)

	assert link._snapshot() == {"kick": [4], "snare": []}
