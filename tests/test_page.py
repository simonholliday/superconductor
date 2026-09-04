"""The page, driven in a real browser against a real service.

These exist because the two bugs that reached the panel were both here, in the
only half of the system that had no tests, while the equivalent Python logic was
covered and correct. Each test below is one of those bugs, or the shape of one.
"""

import typing

import pytest

import conftest


playwright_api = pytest.importorskip("playwright.sync_api")


def _browser_runs () -> bool:
	"""Whether a browser can actually be launched on this machine."""

	try:
		with playwright_api.sync_playwright() as p:
			p.firefox.launch().close()

		return True

	except Exception:
		return False


pytestmark = pytest.mark.skipif(
	not _browser_runs(),
	reason="no browser on this host: run 'sudo playwright install-deps' to enable the page tests")


def test_the_grid_is_drawn_from_what_the_app_declared (panel: typing.Any) -> None:
	"""Two rows of eight, because that is what was declared — not what was coded."""

	assert panel.locator(".grid .cell").count() == 16
	assert panel.locator(conftest.cell("grid/kick/0")).count() == 1
	assert panel.locator(conftest.cell("grid/snare/7")).count() == 1


def test_the_opening_pattern_is_on_the_glass (panel: typing.Any) -> None:
	"""The snapshot decides the faces, so a panel joining late sees the truth."""

	assert "on" in (panel.locator(conftest.cell("grid/kick/0")).get_attribute("class") or "")
	assert "on" in (panel.locator(conftest.cell("grid/kick/4")).get_attribute("class") or "")
	assert "on" not in (panel.locator(conftest.cell("grid/snare/0")).get_attribute("class") or "")


def test_a_tap_asks_the_app_and_does_not_move_the_face_by_itself (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""Nothing drawn on a face is speculative: the app decides, the panel asks."""

	panel.locator(conftest.cell("grid/snare/2")).click()

	asked = fake_app.await_set("grid/snare/2")

	assert asked["v"] is True
	assert "on" not in (panel.locator(conftest.cell("grid/snare/2")).get_attribute("class") or "")


def test_the_face_follows_the_app (panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""And only then."""

	panel.locator(conftest.cell("grid/snare/2")).click()
	asked = fake_app.await_set("grid/snare/2")
	fake_app.confirm("grid/snare/2", True, by="panel", client=asked["client"], seq=asked["seq"])

	playwright_api.expect(panel.locator(conftest.cell("grid/snare/2"))).to_have_class(
		lambda value: "on" in value, timeout=5_000)


def test_a_transport_field_moves_the_transport_not_the_grid (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""The bug that reached the panel: a field change applied as though it were a cell.

	Pausing worked, the button never moved, and there was no way back. It was
	only findable by hand, which is what this file exists to change.
	"""

	assert panel.locator(".transport .hold").inner_text().strip() == "PAUSE"

	fake_app.confirm("transport/paused", True, by="app")

	playwright_api.expect(panel.locator(".transport .hold")).to_have_text("PLAY", timeout=5_000)

	fake_app.confirm("transport/paused", False, by="app")

	playwright_api.expect(panel.locator(".transport .hold")).to_have_text("PAUSE", timeout=5_000)


def test_the_tempo_reading_follows_the_app (panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""So a ramp or a poke from elsewhere shows, not just what was last tapped."""

	fake_app.confirm("transport/bpm", 137.5, by="app")

	playwright_api.expect(panel.locator(".tempo .reading")).to_contain_text("137.5", timeout=5_000)


def test_a_refused_request_says_why_and_gives_the_cell_back (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""The only moment a panel can tell the player that something did not happen."""

	panel.locator(conftest.cell("grid/kick/1")).click()
	asked = fake_app.await_set("grid/kick/1")
	fake_app.refuse("grid/kick/1", asked["client"], asked["seq"], "this grid has no room for that")

	playwright_api.expect(panel.locator(".bar .warn")).to_contain_text("no room", timeout=5_000)
	assert "on" not in (panel.locator(conftest.cell("grid/kick/1")).get_attribute("class") or "")
