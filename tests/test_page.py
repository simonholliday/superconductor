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

	assert panel.locator('.part[data-part="grid"] .cell').count() == 16
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


def test_the_cell_size_is_a_setting_and_not_a_constant (panel: typing.Any) -> None:
	"""The point of #2055: no single target size is right for everybody.

	A person with steady hands on a large panel wants more music on the glass;
	a person without wants a bigger target. Both must be reachable with one
	finger, which is why the chooser is worked here rather than assumed.
	"""

	before = panel.locator(conftest.cell("grid/kick/0")).bounding_box()["width"]

	panel.locator(".sizes > button").click()
	panel.locator(".sizes .choices button", has_text="Compact").click()

	playwright_api.expect(panel.locator(".sizes .choices")).to_have_count(0, timeout=5_000)

	after = panel.locator(conftest.cell("grid/kick/0")).bounding_box()["width"]

	assert after == 22
	assert after < before


def test_the_chosen_size_is_remembered_by_the_panel (panel: typing.Any) -> None:
	"""A setting a person has to make again after every reload is not a setting."""

	panel.locator(".sizes > button").click()
	panel.locator(".sizes .choices button", has_text="Snug").click()

	panel.reload()
	panel.wait_for_selector(".cell", timeout=10_000)

	assert panel.locator(conftest.cell("grid/kick/0")).bounding_box()["width"] == 32


def test_by_default_the_grid_is_measured_against_this_viewport (panel: typing.Any) -> None:
	"""#2050: the size comes from the glass in front of you, not from 1920 by 1080.

	The browser here is 1280 by 720, which is neither the development panel nor
	anything the code was written against, so a grid that fits it without
	scrolling could only have been worked out rather than assumed.
	"""

	fitted = panel.locator(conftest.cell("grid/kick/0")).bounding_box()["width"]

	assert fitted > 44, "a fitted grid should use the space it has"

	overflow = panel.evaluate(
		"""() => {
			const wrap = document.querySelector(".grid-wrap");
			return [wrap.scrollWidth - wrap.clientWidth, wrap.scrollHeight - wrap.clientHeight];
		}""")

	assert overflow == [0, 0], "a fitted grid should not need scrolling"


def test_the_page_says_what_it_is_running (panel: typing.Any) -> None:
	"""Simon's ask: something on the glass that answers "is this the latest"."""

	playwright_api.expect(panel.locator(".bar .build")).to_be_visible(timeout=5_000)


def test_a_page_left_behind_by_the_service_says_so_and_offers_the_way_back (
	panel: typing.Any, service_url: str) -> None:
	"""The confusion this feature exists to end.

	The service is made newer than the loaded page by changing a client file,
	which is exactly what happens during development. The panel finds out on its
	next hello, which a `pageshow` provokes without a reload — a reload would
	fetch the new page and there would be nothing left to detect.
	"""

	import superintendent.service

	marker = superintendent.service.CLIENT_DIR / ".build-changed-by-a-test"

	try:
		marker.write_text("any content at all changes the hash")

		panel.evaluate("() => window.dispatchEvent(new Event('pageshow'))")

		playwright_api.expect(panel.locator(".bar .reload")).to_be_visible(timeout=5_000)
		playwright_api.expect(panel.locator(".bar .build")).to_have_count(0)

	finally:
		marker.unlink(missing_ok=True)


def test_every_declared_grid_is_drawn_not_only_the_first (panel: typing.Any) -> None:
	"""Two patterns driving one instrument belong on one page (#1944), so a page
	showing only the first grid an app declared would be quietly wrong."""

	assert panel.locator(".part").count() == 2
	assert panel.locator(conftest.cell("second/kick/2")).count() == 1


def test_two_grids_sharing_a_row_name_do_not_share_its_cells (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""Both fixtures declare a row called 'kick'. A cell addressed by row and
	step alone would move both, which is the bug this addressing prevents."""

	fake_app.confirm("second/kick/5", True, by="app")

	playwright_api.expect(panel.locator(conftest.cell("second/kick/5"))).to_have_class(
		lambda value: "on" in value, timeout=5_000)

	assert "on" not in (panel.locator(conftest.cell("grid/kick/5")).get_attribute("class") or "")


def test_a_part_is_titled_by_the_app_or_by_its_address (panel: typing.Any) -> None:
	"""The title is the app's to give (#2071): nothing here knows that a grid is
	a drum pattern. An app that offers none gets its address tidied, which is
	honest about where the words came from."""

	assert panel.locator('.part[data-part="grid"] .part-title').inner_text().strip().lower() == "drums"
	assert panel.locator('.part[data-part="second"] .part-title').inner_text().strip().lower() == "second"


def test_a_page_larger_than_the_glass_can_be_pushed_around (panel: typing.Any) -> None:
	"""#2073: every cell is a control and a tap acts on the finger landing, so a
	swipe may scroll from anywhere except a cell — and must not scroll from one."""

	def action (selector: str) -> str:
		return panel.eval_on_selector(selector, "el => getComputedStyle(el).touchAction")

	assert action(conftest.cell("grid/kick/0")) == "none", "a swipe here has already changed the music"

	for surface in (".grid-wrap", ".part-title", ".row-label"):
		assert "pan" in action(surface), f"{surface} is not a control and should take hold of the page"

	assert "pinch" not in action("body"), "pinch zoom is still the browser claiming a musician's gesture"


def test_a_page_shows_only_the_parts_it_carries (panel: typing.Any) -> None:
	"""A page is a view over some of what an app offers, not all of it (#2075)."""

	assert panel.locator(".part").count() == 2, "the first page carries both grids"

	panel.locator(".pages button", has_text="Drums").click()

	playwright_api.expect(panel.locator(".part")).to_have_count(1, timeout=5_000)
	assert panel.locator('.part[data-part="grid"]').count() == 1


def test_the_page_a_panel_is_on_survives_a_reload (panel: typing.Any) -> None:
	"""In performance a reload must return a player to their own page, not to
	whichever one the composition happened to declare first."""

	panel.locator(".pages button", has_text="Drums").click()
	playwright_api.expect(panel.locator(".part")).to_have_count(1, timeout=5_000)

	panel.reload()
	panel.wait_for_selector(".cell", timeout=10_000)

	assert panel.locator(".part").count() == 1


def test_a_page_named_in_the_address_is_the_one_that_opens (
	panel: typing.Any, service_url: str) -> None:
	"""So a performer's tablet can be pointed once and left alone, with no code."""

	panel.goto(f"{service_url}/?page=drums")
	panel.wait_for_selector(".cell", timeout=10_000)

	assert panel.locator(".part").count() == 1


def test_a_remembered_page_that_is_no_longer_offered_is_not_forgotten (
	panel: typing.Any, service_url: str) -> None:
	"""A composition restarted without one pattern should not cost a performer
	the page they had set, once it comes back."""

	panel.evaluate("() => localStorage.setItem('superintendent.page', 'a-page-that-went-away')")
	panel.reload()
	panel.wait_for_selector(".cell", timeout=10_000)

	assert panel.locator(".part").count() == 2, "falls back to the first page"
	assert panel.evaluate("() => localStorage.getItem('superintendent.page')") == "a-page-that-went-away"
