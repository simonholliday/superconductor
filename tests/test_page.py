"""The page, driven in a real browser against a real service.

These exist because the two bugs that reached the panel were both here, in the
only half of the system that had no tests, while the equivalent Python logic was
covered and correct. Each test below is one of those bugs, or the shape of one.
"""

import re
import time
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
		re.compile(r"\bon\b"), timeout=5_000)


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

	panel.wait_for_function(
		"() => getComputedStyle(document.documentElement).getPropertyValue('--cell') === '22px'",
		timeout=5_000)

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
		re.compile(r"\bon\b"), timeout=5_000)

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

	# `touch-action` is not inherited, so a surface that says nothing computes to
	# `auto` — which permits panning. What matters is that it is not `none`, which
	# is the only value that refuses.
	for surface in (".grid-wrap", ".part-title", ".row-label"):
		assert action(surface) != "none", f"{surface} is not a control and should take hold of the page"

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


def test_parts_are_placed_on_the_lattice_and_their_steps_line_up (
	panel: typing.Any, service_url: str) -> None:
	"""#2078's reason for making the lattice cell the step cell: two patterns on
	one page land step-aligned, so step five of one sits above step five of the
	other. Almost-aligned would be worse than either aligned or plainly apart."""

	boxes = [panel.locator(f'.part[data-part="{name}"]').bounding_box() for name in ("grid", "second")]

	assert boxes[1]["x"] > boxes[0]["x"], "placed left to right before wrapping"

	cells = [panel.locator(conftest.cell(f"{part}/kick/3")).bounding_box()["x"]
	         for part in ("grid", "second")]

	assert abs(cells[0] - (cells[1] - (boxes[1]["x"] - boxes[0]["x"]))) < 1, (
		"the same step of each pattern sits at the same offset within its block")


def test_the_latch_holds_the_layout_still_and_never_the_music (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""It used to be a mode: either you moved blocks or you played, never both,
	and the cells stopped answering while it was on.

	There was never a reason for the exclusion. The handle is the title bar,
	which carries no controls, so a drag and a tap cannot mean the same thing.
	What the latch is for is *unintended* movement — so it holds the layout
	still, and the grid goes on playing on both sides of it.
	"""

	assert panel.locator(".grid-wrap.unlocked").count() == 0, "locked by default"

	panel.locator(conftest.cell("grid/snare/1")).click()
	fake_app.await_set("grid/snare/1")

	panel.locator(".bar .latch").click()
	playwright_api.expect(panel.locator(".grid-wrap.unlocked")).to_have_count(1, timeout=5_000)

	# The whole change, in one assertion.
	panel.locator(conftest.cell("grid/snare/3")).click()
	fake_app.await_set("grid/snare/3")


def test_a_locked_layout_does_not_move_under_a_drag (panel: typing.Any) -> None:
	"""Which is what the padlock is for: a stray finger on a title bar costs
	nothing until somebody says it may."""

	_settled(panel)

	block = panel.locator('.part[data-part="grid"]')
	before = block.bounding_box()
	title = panel.locator('.part[data-part="grid"] .part-title').bounding_box()

	panel.mouse.move(title["x"] + 20, title["y"] + 5)
	panel.mouse.down()
	panel.mouse.move(title["x"] + 220, title["y"] + 205, steps=8)
	panel.mouse.up()

	assert block.bounding_box() == before, "the block moved while the layout was locked"


def test_a_block_is_dragged_by_its_title_a_cell_at_a_time (panel: typing.Any) -> None:
	"""#2078: the title bar is the only surface of a block that is not a control,
	and a drag snaps to the lattice rather than to the pixel."""

	panel.locator(".bar .latch").click()
	panel.wait_for_selector(".grid-wrap.unlocked", timeout=5_000)

	block = panel.locator('.part[data-part="grid"]')
	before = block.bounding_box()
	cell = panel.evaluate(
		"() => parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--cell'))")
	gap = panel.evaluate(
		"() => parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--gap'))")

	title = panel.locator('.part[data-part="grid"] .part-title')
	grip = title.bounding_box()

	panel.mouse.move(grip["x"] + 20, grip["y"] + 5)
	panel.mouse.down()
	panel.mouse.move(grip["x"] + 20 + (cell + gap) * 2, grip["y"] + 5 + (cell + gap), steps=8)
	panel.mouse.up()

	after = block.bounding_box()

	assert round(after["x"] - before["x"]) == round((cell + gap) * 2)
	assert round(after["y"] - before["y"]) == round(cell + gap)


def test_a_block_may_be_dragged_over_another_and_the_last_moved_is_on_top (
	panel: typing.Any) -> None:
	"""Overlap is legal, which is what deletes collision resolution — and what
	makes an inventory necessary, since a covered block cannot be grabbed."""

	panel.locator(".bar .latch").click()
	panel.wait_for_selector(".grid-wrap.unlocked", timeout=5_000)

	def depth (part: str) -> int:
		return int(panel.eval_on_selector(f'.part[data-part="{part}"]', "el => getComputedStyle(el).zIndex"))

	assert depth("second") > depth("grid"), "nothing moved yet, so declaration order stands"

	title = panel.locator('.part[data-part="grid"] .part-title').bounding_box()

	panel.mouse.move(title["x"] + 20, title["y"] + 5)
	panel.mouse.down()
	panel.mouse.move(title["x"] + 60, title["y"] + 5, steps=4)
	panel.mouse.up()

	assert depth("grid") > depth("second"), "the block just moved is on top"


def test_the_inventory_brings_a_buried_block_back (panel: typing.Any) -> None:
	"""The one hazard overlap introduces: a block covered completely cannot be
	taken hold of, because a title bar is the only handle it has."""

	panel.locator(".bar .latch").click()
	panel.wait_for_selector(".grid-wrap.unlocked", timeout=5_000)

	def depth (part: str) -> int:
		return int(panel.eval_on_selector(f'.part[data-part="{part}"]', "el => getComputedStyle(el).zIndex"))

	panel.locator(".inventory button", has_text="Drums").click()

	assert depth("grid") > depth("second")


def test_an_arrangement_outlives_a_reload (panel: typing.Any) -> None:
	"""Until it can be sent to the composition that owns the page (#2077), a
	layout that vanished on reload would not be a layout."""

	panel.locator(".bar .latch").click()
	panel.wait_for_selector(".grid-wrap.unlocked", timeout=5_000)

	block = panel.locator('.part[data-part="grid"]')
	before = block.bounding_box()
	title = panel.locator('.part[data-part="grid"] .part-title').bounding_box()

	panel.mouse.move(title["x"] + 20, title["y"] + 5)
	panel.mouse.down()
	panel.mouse.move(title["x"] + 20, title["y"] + 200, steps=8)
	panel.mouse.up()

	assert block.bounding_box()["y"] > before["y"]

	# Leaving is what saves, deliberately: once rather than on every nudge, so a
	# drag in progress is never half-kept (#2075). A reload before this would
	# find nothing, and should.
	panel.locator(".bar .latch").click()
	playwright_api.expect(panel.locator(".grid-wrap.unlocked")).to_have_count(0, timeout=5_000)
	_settled(panel)

	# Measured after leaving rather than during. The fit is frozen while a drag
	# is going on and catches up on the way out (#2072), so a position taken
	# mid-drag is under a different cell size from every later one — and a
	# block placed some cells down then lands a few pixels off for a reason
	# that has nothing to do with what this is testing.
	moved = block.bounding_box()

	panel.reload()
	panel.wait_for_selector(".cell", timeout=10_000)
	_settled(panel)

	assert abs(panel.locator('.part[data-part="grid"]').bounding_box()["y"] - moved["y"]) < 2


def _settled (panel: typing.Any) -> None:
	"""Wait until the cell size has stopped moving.

	The fit runs in an effect and again whenever a ResizeObserver fires, so a
	measurement taken the instant a page is drawn is a measurement of an
	intermediate layout. Every geometric test here was failing on that and not
	on anything the page was doing wrong.
	"""

	panel.wait_for_function(
		"""() => {
			const now = getComputedStyle(document.documentElement).getPropertyValue('--cell');
			const settled = window.__settled === now;
			window.__settled = now;
			return settled;
		}""",
		timeout=5_000, polling=100)


def _open_the_bass (panel: typing.Any) -> None:
	"""Go to the page carrying the pitched pattern."""

	panel.locator(".pages button", has_text="Bass").click()
	panel.wait_for_selector(".grid.notes", timeout=5_000)
	_settled(panel)


def test_a_note_is_drawn_as_a_bar_reaching_across_the_steps_it_lasts (
	panel: typing.Any) -> None:
	"""Which is how every piano roll draws one, and needs no explaining."""

	_open_the_bass(panel)

	# Both widths in one reading: taken separately, a re-fit between them would
	# compare a note drawn at one cell size against a cell measured at another.
	drawn = panel.evaluate("""() => {
		const cell = document.querySelector('.cell[data-path="bass/C2/0"]');
		return {
			cell: cell.getBoundingClientRect().width,
			note: cell.querySelector('.note').getBoundingClientRect().width,
		};
	}""")

	assert drawn["note"] > drawn["cell"], "a two-step note reaches past its own cell"
	assert round(drawn["note"]) == round(drawn["cell"] * 2 + 4), "exactly two steps and the gap between"


def test_pressing_an_empty_cell_places_a_note (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""On the finger landing, as every other control here acts (#2046)."""

	_open_the_bass(panel)

	panel.locator(conftest.cell("bass/D2/3")).click()

	assert fake_app.await_set("bass/D2/3")["v"] is True


def test_pressing_a_note_takes_it_away (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""The other half of the same gesture, and the reason it is unambiguous."""

	_open_the_bass(panel)

	panel.locator(conftest.cell("bass/C2/0")).click(position={"x": 3, "y": 3})

	assert fake_app.await_set("bass/C2/0")["v"] is False


def test_the_velocity_lane_shapes_the_note_in_its_column (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""A lane rather than a dial: the whole dynamic shape is visible at once."""

	_open_the_bass(panel)

	bar = panel.locator('.lane .bar[data-velocity="0"]').bounding_box()

	panel.mouse.move(bar["x"] + bar["width"] / 2, bar["y"] + 2)
	panel.mouse.down()
	panel.mouse.up()

	asked = fake_app.await_set("bass/C2/0/velocity")

	assert asked["v"] > 100, "pressing near the top of the lane asks for a hard hit"


def test_the_lane_does_nothing_where_there_is_no_note (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""A velocity with no note is not a state the sequencer could report."""

	_open_the_bass(panel)

	bar = panel.locator('.lane .bar[data-velocity="5"]').bounding_box()

	panel.mouse.move(bar["x"] + bar["width"] / 2, bar["y"] + 2)
	panel.mouse.down()
	panel.mouse.up()

	assert not any(frame.get("path", "").startswith("bass/") for frame in fake_app.sets)


def test_a_pitch_grid_is_drawn_high_note_first (panel: typing.Any) -> None:
	"""So a rising line rises. The order is the composition's — a declared row
	list is drawn in the order it is given — and this is the pitched case of it."""

	_open_the_bass(panel)

	high = panel.locator(conftest.cell("bass/D2/0")).bounding_box()
	low = panel.locator(conftest.cell("bass/C2/0")).bounding_box()

	assert high["y"] < low["y"], "the higher note sits above the lower one"


def test_a_tall_pattern_shows_a_window_that_scrolls_within_its_block (
	panel: typing.Any) -> None:
	"""Two octaves is twenty-five rows against a drum machine's ten, and a block
	tall enough for all of it crowds everything else off the page."""

	_open_the_bass(panel)

	panel.wait_for_function(
		"""() => {
			const el = document.querySelector('.part[data-part="bass"] .scroller');
			return el && el.scrollHeight > el.clientHeight;
		}""",
		timeout=5_000)

	seen = panel.evaluate("""() => {
		const el = document.querySelector('.part[data-part="bass"] .scroller');
		return { overflow: el.scrollHeight - el.clientHeight, top: el.scrollTop };
	}""")

	assert seen["overflow"] > 0, "three rows do not fit in a window of two"
	assert seen["top"] > 0, "opened at the bottom, where a bass line lives"


def test_the_velocity_lane_does_not_scroll_with_the_pitches (panel: typing.Any) -> None:
	"""It is a sibling of the pitches, not a child: a column is a moment in time,
	and scrolling up and down does not change the time."""

	_open_the_bass(panel)

	assert panel.locator('.part[data-part="bass"] .scroller .lane').count() == 0
	assert panel.locator('.part[data-part="bass"] .lane').count() == 1


def test_both_kinds_of_grid_label_their_rows_the_same_way (panel: typing.Any) -> None:
	"""One rule for every kind, until something needs the exception.

	There are two instrument designs on the glass now and there will be more, so
	this asserts they agree rather than trusting them to.
	"""

	# Pinned to one size before anything is measured. Type scales with the cell
	# now, and the two pages fit at different cell sizes — so comparing raw
	# pixels across them would be comparing two settings, not two rules.
	panel.locator(".sizes > button").click()
	panel.locator(".sizes .choices button", has_text="Tested").click()
	panel.wait_for_function(
		"() => getComputedStyle(document.documentElement).getPropertyValue('--cell') === '44px'",
		timeout=5_000)

	panel.locator(".pages button", has_text="All").click()
	panel.wait_for_selector(".grid .cell", timeout=5_000)

	def label (part: str) -> dict:
		return panel.eval_on_selector(
			f'.part[data-part="{part}"] .row-label',
			"""el => {
				const seen = getComputedStyle(el);
				const box = el.getBoundingClientRect();
				const range = document.createRange();

				range.selectNodeContents(el);

				return {
					/* Where the words actually end, not which keyword put them
					   there: the direction is reversed so an over-long name is
					   trimmed at its front, and that reverses what "flex-end"
					   means. The rule is right-aligned (#2073); this measures
					   whether they are, rather than how. */
					fromRight: Math.round(box.right - range.getBoundingClientRect().right),
					size: seen.fontSize,
					colour: seen.color,
					rail: seen.backgroundImage !== "none",
				};
			}""")

	panel.locator(".pages button", has_text="Bass").click()
	panel.wait_for_selector(".grid.notes", timeout=5_000)
	pitched = label("bass")

	panel.locator(".pages button", has_text="All").click()
	panel.wait_for_selector(".grid .cell", timeout=5_000)
	drums = label("grid")

	assert drums["fromRight"] == pitched["fromRight"], "the two kinds align differently"
	assert drums["fromRight"] >= 0, "a label reaches past its own right edge"
	assert drums["size"] == pitched["size"]
	assert drums["colour"] == pitched["colour"]
	# A block with a window carries the strip instead, which is the same idea
	# drawn once rather than twice — so what has to agree is that each part
	# offers exactly one mark saying the view can be pushed from here.
	assert drums["rail"], "a block with no window carries the rail on its labels"
	assert not pitched["rail"], "a block with one carries the strip instead"


def test_a_window_shows_how_much_of_itself_you_are_seeing (panel: typing.Any) -> None:
	"""Drawn rather than left to the browser.

	A touch panel's scrollbar is an overlay that fades when nothing is moving,
	so it says nothing at the moment somebody is deciding whether there is more;
	and the inset shadow that was tried first is invisible against a panel this
	dark. Simon saw neither, which is why this asserts the mark is there and is
	shorter than the track it runs in.
	"""

	_open_the_bass(panel)

	thumb = panel.locator('.part[data-part="bass"] .window .track i')
	track = panel.locator('.part[data-part="bass"] .window .track')

	playwright_api.expect(thumb).to_be_visible(timeout=5_000)

	assert thumb.bounding_box()["height"] < track.bounding_box()["height"], (
		"the mark is shorter than its track, which is what says there is more")


def test_the_scroll_mark_is_not_painted_over_by_the_row_labels (panel: typing.Any) -> None:
	"""It was, and showed only in the gaps between rows as a column of squares.

	The labels are sticky and opaque so they can stay above the playhead while a
	wide grid scrolls under them; the mark has to clear them in turn.
	"""

	_open_the_bass(panel)

	# Asked for separately: a single selector returns document order, and the
	# labels come before the track, so the first result was never the mark.
	mark = panel.eval_on_selector(
		'.part[data-part="bass"] .window .track',
		"el => Number(getComputedStyle(el).zIndex) || 0")

	labels = panel.eval_on_selector_all(
		'.part[data-part="bass"] .row-label',
		"els => els.map(el => Number(getComputedStyle(el).zIndex) || 0)")

	assert mark > max(labels), "the mark sits above every label"


def test_the_playhead_cannot_widen_the_page_as_it_wraps (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""It is drawn between beats, so it passes 15.9 of 16 steps before wrapping,
	which put it most of a cell past the last one and flashed a scrollbar up
	once a bar. A block is exactly as wide as its pattern, so it clips."""

	_open_the_bass(panel)

	# Drive it to the very end of the pattern, which is where it used to reach
	# most of a cell past the last step and widen the document.
	fake_app.beat(7)
	panel.wait_for_timeout(600)

	assert panel.evaluate(
		"() => document.documentElement.scrollWidth <= document.documentElement.clientWidth"), (
		"a playhead between two steps is a position, not something to make room for")


def test_nothing_on_the_page_reaches_past_the_glass (panel: typing.Any) -> None:
	"""A horizontal scrollbar on the document is always a fault here: a page
	that does not fit scrolls inside its own area, and the header wraps. This
	found the header hanging 93 px past the edge on a 1280-wide viewport, which
	the playhead's own test could not see because it was asserting a stylesheet
	line rather than looking."""

	_settled(panel)

	past = panel.evaluate("""() => [...document.querySelectorAll('body *')]
		.filter(el => el.getBoundingClientRect().right > document.documentElement.clientWidth + 1)
		.map(el => el.className || el.tagName)""")

	assert past == [], f"these reach past the glass: {past}"


def test_a_part_that_fits_draws_no_scroll_mark (panel: typing.Any) -> None:
	"""A mark on a block with nowhere to go would be furniture, and worse, a lie."""

	panel.locator(".pages button", has_text="All").click()
	panel.wait_for_selector(".grid .cell", timeout=5_000)

	assert panel.locator('.part[data-part="grid"] .track').count() == 0


def test_a_cell_looks_the_same_whatever_kind_of_grid_it_is_in (panel: typing.Any) -> None:
	"""A person learns a cell once. Two designs of it would be two to learn."""

	# Both pages fit to their own contents, so a cell's corner radius — which
	# scales with the cell — is only comparable once the size is pinned.
	panel.locator(".sizes > button").click()
	panel.locator(".sizes .choices button", has_text="Tested").click()
	playwright_api.expect(panel.locator(".sizes .choices")).to_have_count(0, timeout=5_000)

	def cell_shape (selector: str) -> dict:
		return panel.eval_on_selector(selector, """el => {
			const seen = getComputedStyle(el);
			return { radius: seen.borderRadius, border: seen.borderWidth };
		}""")

	panel.locator(".pages button", has_text="Bass").click()
	panel.wait_for_selector(".grid.notes", timeout=5_000)
	pitched = cell_shape(conftest.cell("bass/C2/1"))

	panel.locator(".pages button", has_text="All").click()
	panel.wait_for_selector(".grid .cell", timeout=5_000)
	drums = cell_shape(conftest.cell("grid/snare/1"))

	assert drums == pitched


def test_the_scroll_strip_is_the_thing_you_take_hold_of (panel: typing.Any) -> None:
	"""It reported where you were without ever saying it was the thing to touch,
	so Simon had to drag the empty space beside it. Pressing it now brings that
	part of the pattern into the middle of the window."""

	_open_the_bass(panel)

	scroller = '.part[data-part="bass"] .scroller'
	strip = panel.locator('.part[data-part="bass"] .window .track')

	assert panel.eval_on_selector(
		'.part[data-part="bass"] .window .track',
		"el => getComputedStyle(el).pointerEvents") != "none", "the strip answers a finger"

	before = panel.eval_on_selector(scroller, "el => el.scrollTop")

	box = strip.bounding_box()
	panel.mouse.move(box["x"] + box["width"] / 2, box["y"] + 4)
	panel.mouse.down()
	panel.mouse.up()

	assert panel.eval_on_selector(scroller, "el => el.scrollTop") < before, (
		"pressing near the top of the strip moves the window up")


def test_only_one_scrollbar_and_it_is_ours (panel: typing.Any) -> None:
	"""The browser's own is a second bar on a desktop and an overlay that fades
	on a touch panel — neither of which is a thing to take hold of."""

	_open_the_bass(panel)

	seen = panel.evaluate("""() => {
		const part = document.querySelector('.part[data-part="bass"]');
		const scroller = part.querySelector('.scroller');
		return {
			// A native scrollbar takes its width out of the content box.
			gutter: scroller.offsetWidth - scroller.clientWidth,
			scrolling: [...part.querySelectorAll('*')]
				.filter(el => el.scrollHeight > el.clientHeight).length,
			marks: part.querySelectorAll('.track').length,
		};
	}""")

	assert seen["gutter"] == 0, "the browser's own bar takes no room, because it is not drawn"
	assert seen["scrolling"] == 1, "exactly one thing in the block scrolls"
	assert seen["marks"] == 1, "and exactly one mark says so"


def test_settings_do_not_overlap_each_other_at_a_small_cell_size (panel: typing.Any) -> None:
	"""A block's rows are a cell tall; a switch has a size below which it cannot
	be pressed. Both are right, and until they were made to agree the settings
	overlapped by eighteen pixels at the compact size."""

	panel.locator(".pages button", has_text="Moog").click()
	panel.wait_for_selector(".grid.params", timeout=5_000)

	panel.locator(".sizes > button").click()
	panel.locator(".sizes .choices button", has_text="Compact").click()
	panel.wait_for_function(
		"() => getComputedStyle(document.documentElement).getPropertyValue('--cell') === '22px'",
		timeout=5_000)

	boxes = panel.evaluate("""() => [...document.querySelectorAll('.part[data-part="moog"] .setting')]
		.map(el => { const b = el.getBoundingClientRect(); return [b.top, b.bottom]; })""")

	for above, below in zip(boxes, boxes[1:]):
		assert above[1] <= below[0] + 1, "one setting reaches into the next"


def test_the_page_does_not_resize_itself_under_a_dragging_finger (panel: typing.Any) -> None:
	"""#2072: a page that no longer fits scrolls. It does not rearrange or
	resize itself, and a drag is the moment that decision exists for — the
	whole page used to shrink by nearly half while the block was still moving."""

	_settled(panel)

	before = panel.evaluate(
		"() => getComputedStyle(document.documentElement).getPropertyValue('--cell')")

	panel.locator(".bar .latch").click()
	panel.wait_for_selector(".grid-wrap.unlocked", timeout=5_000)

	title = panel.locator('.part[data-part="second"] .part-title').bounding_box()
	panel.mouse.move(title["x"] + 20, title["y"] + 5)
	panel.mouse.down()
	panel.mouse.move(title["x"] + 600, title["y"] + 5, steps=10)

	during = panel.evaluate(
		"() => getComputedStyle(document.documentElement).getPropertyValue('--cell')")

	panel.mouse.up()

	assert during == before, "the cells stayed where they were while the block moved"


def _open_the_stack (panel: typing.Any) -> None:
	"""Go to the page carrying the generator stack and wait for it to draw."""

	panel.locator(".pages button", has_text="Generators").click()
	panel.wait_for_selector(".recipe", timeout=5_000)
	_settled(panel)


def test_a_generator_is_added_from_the_glass (panel: typing.Any, fake_app: typing.Any) -> None:
	"""#2085: the panel picks from a catalogue the app described itself with.

	Adding sends the whole stack, because adding changes the list rather than a
	value in it — and the same is true of removing, bypassing and reordering.
	"""

	_open_the_stack(panel)

	panel.locator(".part-foot .offer.add").click()
	panel.wait_for_selector(".sheet", timeout=5_000)
	panel.locator(".sheet .offer", has_text="euclidean").click()

	asked = [one for one in fake_app.sets if one["path"] == "stack/layers"]

	assert asked, "adding a generator asked for nothing"
	assert [layer["generator"] for layer in asked[-1]["v"]] == ["euclidean", "euclidean"]


def test_a_generator_this_panel_cannot_fully_draw_is_shown_but_not_offered (
	panel: typing.Any) -> None:
	"""Shown rather than hidden: knowing it exists and why it is out of reach is
	worth more than a shorter list, and it is what the app itself says."""

	_open_the_stack(panel)
	panel.locator(".part-foot .offer.add").click()
	panel.wait_for_selector(".sheet", timeout=5_000)

	partial = panel.locator(".sheet .offer", has_text="evolve")

	assert partial.count() == 1
	assert partial.is_disabled()


def test_one_parameter_is_addressed_on_its_own_not_as_the_whole_stack (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Which is what lets two people turn different knobs without one of them
	overwriting the other's layer."""

	_open_the_stack(panel)

	panel.locator('.part[data-part="stack/one"] .switch').first.click()

	dial = panel.locator('.part[data-part="stack/one"] .dial').first
	box = dial.bounding_box()

	panel.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] / 2)

	moved = [one for one in fake_app.sets if one["path"].startswith("stack/one/")]

	assert moved, "turning a knob addressed no parameter"
	assert moved[-1]["path"] == "stack/one/pulses"


def test_a_number_with_no_declared_bounds_is_worked_with_one_finger (
	panel: typing.Any) -> None:
	"""Most of a generator's numbers have no natural range, so this is the
	ordinary case rather than the odd one.  A slider with invented ends would be
	a lie a finger could act on; a stepper claims nothing and still works with
	no keyboard attached."""

	_open_the_stack(panel)

	stepper = panel.locator('.part[data-part="stack/one"] .stepper')

	assert stepper.count() == 1, "duration has no bounds and should be a stepper"

	for index in range(stepper.locator("button").count()):
		box = stepper.locator("button").nth(index).bounding_box()

		assert box["width"] >= 44 and box["height"] >= 44, "a stepper button is not reachable"


def test_a_range_is_one_bar_with_two_handles (panel: typing.Any) -> None:
	"""The gap between them is the value, which is the reason to draw it at all
	rather than print two numbers."""

	_open_the_stack(panel)

	ranged = panel.locator('.part[data-part="stack/one"] .dial.ranged')

	assert ranged.count() == 1
	assert ranged.locator("b").count() == 2


def test_a_range_moves_the_end_the_finger_took_hold_of (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Deciding which end on the way down and keeping it: deciding again on
	every move would swap ends under the finger the moment the two crossed."""

	_open_the_stack(panel)

	ranged = panel.locator('.part[data-part="stack/one"] .dial.ranged')
	box = ranged.bounding_box()

	# Held is 40–80 of 1–127, so the left quarter is nearest the low end.
	panel.mouse.click(box["x"] + box["width"] * 0.1, box["y"] + box["height"] / 2)

	moved = [one for one in fake_app.sets if one["path"] == "stack/one/velocity"]

	assert moved, "the range asked for nothing"

	low, high = moved[-1]["v"]

	assert high == 80, "the end that was not touched moved"
	assert low < 40, "the end that was touched did not"


def test_a_layer_is_moved_up_and_down_the_stack (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""The order is musical content: a fill that skips an occupied step depends
	on what ran before it."""

	_open_the_stack(panel)

	panel.locator(".part-foot .offer.add").click()
	panel.wait_for_selector(".sheet", timeout=5_000)
	panel.locator(".sheet .offer", has_text="euclidean").click()

	fake_app.confirm("stack/layers", [
		{"id": "one", "generator": "euclidean", "bypassed": False, "params": {}},
		{"id": "two", "generator": "euclidean", "bypassed": False, "params": {}},
	], by="panel")

	panel.wait_for_function(
		"() => document.querySelectorAll('.recipe .layer').length === 2",
		timeout=5_000)

	# The second layer's own window, and the arrow that sends it up one.
	panel.locator('.part[data-part="stack/two"] .move').first.click()

	asked = [one for one in fake_app.sets if one["path"] == "stack/layers"]

	assert [layer["id"] for layer in asked[-1]["v"]] == ["two", "one"]


def test_a_layer_naming_a_generator_that_has_gone_says_so (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""A stored stack outlives the package that defines its generators.  When
	one is renamed away the layer must say it is not playing, rather than draw
	an empty set of parameters that looks like it is."""

	_open_the_stack(panel)

	fake_app.confirm("stack/layers", [
		{"id": "one", "generator": "withdrawn", "bypassed": False, "params": {}},
	], by="app")

	panel.wait_for_selector('.part[data-part="stack/one"] .unsupported', timeout=5_000)

	assert "withdrawn" in panel.locator('.part[data-part="stack/one"] .unsupported').inner_text()


def test_turning_a_layers_knob_moves_the_control_it_turned (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""A stack's parameter has exactly the shape of a grid cell — the control,
	then two more parts — so a handler reading the path's shape alone sends it
	to the branch that treats the layer's id as a row and the parameter's name
	as a step number.

	The knob then moved the music and nothing on the glass: pulses dragged to
	maximum played sixteen and went on reading five.
	"""

	_open_the_stack(panel)

	dial = panel.locator('.part[data-part="stack/one"] .dial').first
	box = dial.bounding_box()

	panel.mouse.click(box["x"] + box["width"] * 0.9, box["y"] + box["height"] / 2)

	asked = [one for one in fake_app.sets if one["path"] == "stack/one/pulses"][-1]

	assert asked["v"] > 3, "the drag did not ask for a larger value"

	fake_app.confirm(asked["path"], asked["v"], by="panel",
	                 client=asked["client"], seq=asked["seq"])

	playwright_api.expect(dial.locator("span")).to_have_text(str(asked["v"]), timeout=5_000)


def test_one_of_many_is_chosen_from_a_menu_rather_than_a_wall_of_buttons (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""A row of buttons is a good way to choose one of three and a poor way to
	choose one of ten: it reads as "several of these" while taking only one, and
	it costs three rows of height on a block that has better uses for them."""

	_open_the_stack(panel)

	menu = panel.locator('.part[data-part="stack/one"] .menu')

	assert menu.count() == 1, "the six voices should be behind a menu"
	assert menu.locator(".options").count() == 0, "and closed until it is asked for"

	menu.locator("button").first.click()
	panel.wait_for_selector('.part[data-part="stack/one"] .menu .options', timeout=5_000)

	menu.locator(".options button", has_text="clap").click()

	asked = [one for one in fake_app.sets if one["path"] == "stack/one/pitch"]

	assert asked and asked[-1]["v"] == "clap"
	playwright_api.expect(panel.locator('.part[data-part="stack/one"] .menu .options')).to_have_count(0)


def test_a_short_choice_stays_a_row_of_buttons (panel: typing.Any) -> None:
	"""Two options behind a menu would be worse than two buttons, which is why
	there is a threshold rather than one rule for every length."""

	panel.locator(".pages button", has_text="Moog").click()
	panel.wait_for_selector(".grid.params", timeout=5_000)

	assert panel.locator('.part[data-part="moog"] .menu').count() == 0
	assert panel.locator('.part[data-part="moog"] .choices button').count() == 2


def test_a_float_with_no_declared_step_is_not_snapped_to_whole_numbers (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""An absent step means a continuous value, however round the number
	standing in it looks.

	Reading the step off the held value instead broke the one case that
	mattered: probability runs 0 to 1 and defaults to 1.0, which crosses the
	wire as 1 — so the slider inferred a step of one and offered nothing
	between none and all.
	"""

	_open_the_stack(panel)

	dials = panel.locator('.part[data-part="stack/one"] .dial:not(.ranged)')
	probability = dials.last
	box = probability.bounding_box()

	panel.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] / 2)

	asked = [one for one in fake_app.sets if one["path"] == "stack/one/probability"]

	assert asked, "the probability slider asked for nothing"
	assert 0 < asked[-1]["v"] < 1, f"snapped to {asked[-1]['v']} instead of landing between"


def test_a_layers_controls_are_not_clipped_at_the_smallest_cell_size (
	panel: typing.Any) -> None:
	"""The header carries four controls and a name, and at the compact size the
	block is narrower than they are. Something has to give and it must be the
	name — letting the buttons shrink instead cut "remove" down to "rem" on the
	one screen this is for."""

	_open_the_stack(panel)

	panel.locator(".sizes > button").click()
	panel.locator(".sizes .choices button", has_text="Compact").click()
	panel.wait_for_function(
		"() => getComputedStyle(document.documentElement).getPropertyValue('--cell') === '22px'",
		timeout=5_000)
	_settled(panel)

	spilling = panel.evaluate("""() => {
		const header = document.querySelector('.part[data-part="stack/one"] .layer');
		const edge = header.getBoundingClientRect().right;

		return [...header.querySelectorAll('button')]
			.filter((one) => one.getBoundingClientRect().right > edge + 1)
			.map((one) => one.className + ':' + one.textContent);
	}""")

	assert spilling == [], f"these reach past the block: {spilling}"


def test_a_menu_is_not_clipped_by_the_block_it_opens_in (panel: typing.Any) -> None:
	"""A part clips its own body so the playhead cannot widen the page, and a
	menu drawn inside one is cut off by the same rule — which is not something a
	person can scroll to, because the block is what is cutting it off.

	Six voices in a short block lost their lower half. Ten would lose more.
	"""

	_open_the_stack(panel)

	panel.locator('.part[data-part="stack/one"] .menu > button').first.click()
	panel.wait_for_selector('.part[data-part="stack/one"] .menu .options', timeout=5_000)

	hidden = panel.evaluate("""() => {
		const block = document.querySelector('.part[data-part="stack/one"] .part-body');
		const edges = block.getBoundingClientRect();

		return [...document.querySelectorAll('.menu .options button')]
			.filter((one) => {
				const box = one.getBoundingClientRect();
				return box.bottom > edges.bottom + 1 || box.top < edges.top - 1;
			})
			.map((one) => ({
				label: one.textContent,
				reaches: one.getBoundingClientRect().bottom,
				viewport: window.innerHeight,
			}));
	}""")

	# Escaping the block is the point; what must not happen is leaving the glass.
	for option in hidden:
		assert option["reaches"] <= option["viewport"] + 1, \
			f"{option['label']} is drawn off the bottom of the screen"

	for index in range(panel.locator(".menu .options button").count()):
		assert panel.locator(".menu .options button").nth(index).is_visible(), \
			"an option is drawn but cannot be reached"


def test_a_control_is_the_size_the_person_chose (panel: typing.Any) -> None:
	"""One cell, the same cell as everything else.

	There was a 44px floor under this, on the grounds that a control must stay
	pressable however small the grid is set. It came out because a *step cell*
	is the most tapped thing on the surface and shrinks to 22px without
	complaint — so the floor was protecting a switch from a size a person is
	happily playing at, and it showed: the pattern shrank and the settings
	beside it stayed put.
	"""

	_open_the_stack(panel)

	for size, cell in (("Compact", "22px"), ("Snug", "32px"),
	                   ("Tested", "44px"), ("Large", "60px")):
		panel.locator(".sizes > button").click()
		panel.locator(".sizes .choices button", has_text=size).click()
		panel.wait_for_function(
			"() => getComputedStyle(document.documentElement)"
			f".getPropertyValue('--cell') === '{cell}'", timeout=5_000)

		row = panel.evaluate(
			"() => getComputedStyle(document.documentElement).getPropertyValue('--row')")

		assert row.strip() == cell, f"at {size} a control's row is {row}, not {cell}"


def test_every_control_on_the_lattice_is_a_row_tall (panel: typing.Any) -> None:
	"""The rule is worth nothing if a control declares its own height instead.

	Anything drawn on the lattice takes its height from --row; the bar and the
	popovers hanging off it keep a fixed target, because neither is on the
	lattice and neither should grow to 96px because the pattern behind it is
	set large.
	"""

	_open_the_stack(panel)

	panel.locator(".sizes > button").click()
	panel.locator(".sizes .choices button", has_text="Large").click()
	panel.wait_for_function(
		"() => getComputedStyle(document.documentElement).getPropertyValue('--cell') === '60px'",
		timeout=5_000)
	_settled(panel)

	short = panel.evaluate("""() => {
		const row = parseFloat(
			getComputedStyle(document.documentElement).getPropertyValue('--row'));

		return [...document.querySelectorAll('.part .setting > *, .part .layer > button')]
			.map((one) => ({ what: one.className || one.tagName,
			                 tall: Math.round(one.getBoundingClientRect().height) }))
			.filter((one) => one.tall < row);
	}""")

	assert short == [], f"these do not fill their row: {short}"


def test_type_follows_the_grid_a_person_chose (panel: typing.Any) -> None:
	"""The whole complaint in one assertion: resize the pattern and the words
	beside it should resize with it.

	A label and the value it names are also one size, not two — they are one
	role seen from two sides, and a value drawn larger than its own name was
	what inflated a settings block past the room it needed.
	"""

	_open_the_stack(panel)

	def measured (name: str, cell: str) -> dict:
		panel.locator(".sizes > button").click()
		panel.locator(".sizes .choices button", has_text=name).click()

		# Waiting on the number rather than on stillness: the cell has not begun
		# moving when the click returns, and a wait for "stopped moving" is
		# satisfied by a value that never started.
		panel.wait_for_function(
			"() => getComputedStyle(document.documentElement)"
			f".getPropertyValue('--cell') === '{cell}'",
			timeout=5_000)

		return panel.evaluate("""() => {
			const label = document.querySelector('.part .row-label');
			const value = document.querySelector('.part .dial span');

			return {
				label: parseFloat(getComputedStyle(label).fontSize),
				value: parseFloat(getComputedStyle(value).fontSize),
			};
		}""")

	small = measured("Compact", "22px")
	large = measured("Large", "60px")

	assert small["label"] == small["value"], "a value is not the size of its own label"
	assert large["label"] == large["value"], "a value is not the size of its own label"
	assert large["label"] > small["label"], "the words did not follow the grid"


def test_a_layout_is_kept_when_the_finger_lifts (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""It used to be kept on leaving a mode. With no mode to leave, the end of
	the drag is the moment — the same guarantee, finer: a layout in motion is
	never half-saved, and an accidental nudge is one write rather than twenty.
	"""

	panel.locator(".bar .latch").click()
	panel.wait_for_selector(".grid-wrap.unlocked", timeout=5_000)
	_settled(panel)

	title = panel.locator('.part[data-part="grid"] .part-title').bounding_box()

	panel.mouse.move(title["x"] + 20, title["y"] + 5)
	panel.mouse.down()
	panel.mouse.move(title["x"] + 20, title["y"] + 205, steps=8)

	assert "all" not in fake_app.arrangements, "kept while the finger was still down"

	panel.mouse.up()

	# The frame crosses two sockets and lands on the app's own thread, so this
	# waits for it rather than assuming it has arrived.
	deadline = time.monotonic() + 5

	while "all" not in fake_app.arrangements and time.monotonic() < deadline:
		time.sleep(0.05)

	kept = fake_app.arrangements.get("all")

	assert kept, "nothing was kept when the finger lifted"
	assert {one["name"] for one in kept} >= {"grid", "second"}


def test_a_drag_that_moves_nothing_writes_nothing (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""A tap on a title bar is not a layout change, and should not cost a write
	to the composition's file."""

	panel.locator(".bar .latch").click()
	panel.wait_for_selector(".grid-wrap.unlocked", timeout=5_000)
	_settled(panel)

	title = panel.locator('.part[data-part="grid"] .part-title').bounding_box()

	panel.mouse.move(title["x"] + 20, title["y"] + 5)
	panel.mouse.down()
	panel.mouse.up()

	# Long enough that a write would have landed if one had been sent.
	time.sleep(0.5)

	assert "all" not in fake_app.arrangements


def test_every_row_label_is_right_aligned_at_the_same_offset (panel: typing.Any) -> None:
	"""#2073 settled one rule for every kind: labels are right-aligned.

	Worth asserting rather than trusting, because the fix for a *different*
	problem broke it. An over-long name is trimmed at its front now — an
	ellipsis renders at the end of a line, which for right-aligned text is the
	end that fits, so "hihat_1_closed" was quietly losing its h. Reversing the
	direction puts the mark where the loss is, and reversing the direction also
	reverses what "start" means to the layout, which left every label hard
	against the wrong edge.
	"""

	panel.locator(".sizes > button").click()
	panel.locator(".sizes .choices button", has_text="Compact").click()
	panel.wait_for_function(
		"() => getComputedStyle(document.documentElement).getPropertyValue('--cell') === '22px'",
		timeout=5_000)
	_settled(panel)

	offsets = panel.evaluate("""() => {
		return [...document.querySelectorAll('.part .row-label')].map((el) => {
			const box = el.getBoundingClientRect();
			const range = document.createRange();

			range.selectNodeContents(el);

			return Math.round(box.right - range.getBoundingClientRect().right);
		});
	}""")

	assert offsets, "no labels were drawn"
	assert len(set(offsets)) == 1, f"labels sit at different offsets: {sorted(set(offsets))}"
	assert offsets[0] >= 0, "a label reaches past its own right edge"


def _two_fingers (panel: typing.Any, apart: int, then: int) -> None:
	"""Put two touch pointers on the page and move them to a new distance."""

	panel.evaluate("""([apart, then]) => {
		const wrap = document.querySelector('.grid-wrap');
		const box = wrap.getBoundingClientRect();
		const midX = box.left + box.width / 2;
		const midY = box.top + box.height / 2;

		const send = (type, id, x) => wrap.dispatchEvent(new PointerEvent(type, {
			pointerId: id, clientX: x, clientY: midY,
			pointerType: 'touch', bubbles: true, cancelable: true }));

		send('pointerdown', 1, midX - apart / 2);
		send('pointerdown', 2, midX + apart / 2);
		send('pointermove', 1, midX - then / 2);
		send('pointermove', 2, midX + then / 2);
		send('pointerup', 1, midX - then / 2);
		send('pointerup', 2, midX + then / 2);
	}""", [apart, then])


def test_two_fingers_spread_apart_make_the_grid_bigger (panel: typing.Any) -> None:
	"""Simon, after using a smaller screen: being able to spread two fingers to
	see one instrument closely, and pinch back to see every instrument, is how a
	person expects to move around a hand-held panel.

	It sets the panel's own size rather than the browser's zoom — browser zoom
	scales the type and the targets together and leaves the same amount of music
	on the glass, where this brings more of the piece into view.
	"""

	panel.locator(".sizes > button").click()
	panel.locator(".sizes .choices button", has_text="Tested").click()
	panel.wait_for_function(
		"() => getComputedStyle(document.documentElement).getPropertyValue('--cell') === '44px'",
		timeout=5_000)

	_two_fingers(panel, apart=200, then=300)

	panel.wait_for_function(
		"() => parseFloat(getComputedStyle(document.documentElement)"
		".getPropertyValue('--cell')) > 44", timeout=5_000)

	grown = panel.evaluate(
		"() => parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--cell'))")

	assert 60 <= grown <= 72, f"a half-again spread gave {grown}px from 44"


def test_two_fingers_brought_together_make_it_smaller (panel: typing.Any) -> None:
	"""And the way back, clamped so a pinch cannot shrink the page to nothing."""

	panel.locator(".sizes > button").click()
	panel.locator(".sizes .choices button", has_text="Tested").click()
	panel.wait_for_function(
		"() => getComputedStyle(document.documentElement).getPropertyValue('--cell') === '44px'",
		timeout=5_000)

	_two_fingers(panel, apart=400, then=40)

	panel.wait_for_function(
		"() => parseFloat(getComputedStyle(document.documentElement)"
		".getPropertyValue('--cell')) < 44", timeout=5_000)

	shrunk = panel.evaluate(
		"() => parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--cell'))")

	assert shrunk >= 22, f"a pinch went below the floor: {shrunk}px"


def test_two_fingers_that_do_not_move_are_still_two_taps (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""The whole reason there is a threshold.

	Playing several cells at once is what multi-touch was measured for (#1997),
	and a gesture that claimed the second finger would take that away. Two
	fingers that land and stay put switch two steps.
	"""

	before = panel.evaluate(
		"() => getComputedStyle(document.documentElement).getPropertyValue('--cell')")

	panel.evaluate("""() => {
		const cells = ['grid/kick/2', 'grid/snare/6'].map(
			(path) => document.querySelector(`.cell[data-path="${path}"]`));

		cells.forEach((cell, index) => {
			const box = cell.getBoundingClientRect();

			for (const type of ['pointerdown', 'pointerup']) {
				cell.dispatchEvent(new PointerEvent(type, {
					pointerId: index + 1,
					clientX: box.left + box.width / 2,
					clientY: box.top + box.height / 2,
					pointerType: 'touch', bubbles: true, cancelable: true }));
			}
		});
	}""")

	fake_app.await_set("grid/kick/2")
	fake_app.await_set("grid/snare/6")

	after = panel.evaluate(
		"() => getComputedStyle(document.documentElement).getPropertyValue('--cell')")

	assert after == before, f"two taps resized the page from {before} to {after}"


def test_a_range_is_moved_by_its_middle_without_changing_its_width (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""A velocity of 30 to 50 is a character. Wanting all of it louder is a
	different request from wanting it wider, and until now only the second could
	be asked for — each end moved alone and the span had to be rebuilt by hand.
	"""

	_open_the_stack(panel)

	ranged = panel.locator('.part[data-part="stack/one"] .dial.ranged')
	box = ranged.bounding_box()

	# Held is 40–80 of 1–127, so the middle of the span is around a third across.
	middle = (40 + 80) / 2
	across = (middle - 1) / (127 - 1)

	panel.mouse.move(box["x"] + box["width"] * across, box["y"] + box["height"] / 2)
	panel.mouse.down()
	panel.mouse.move(box["x"] + box["width"] * (across + 0.15),
	                 box["y"] + box["height"] / 2, steps=6)
	panel.mouse.up()

	asked = [one for one in fake_app.sets if one["path"] == "stack/one/velocity"]

	assert asked, "the range asked for nothing"

	low, high = asked[-1]["v"]

	assert high - low == 40, f"the span changed width: {low}–{high}"
	assert low > 40, f"the span did not move: {low}–{high}"


def test_a_range_moved_to_the_end_stops_rather_than_squashing (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Dragging a span into the ceiling should stop it, not compress it — a
	character does not narrow because it got loud."""

	_open_the_stack(panel)

	ranged = panel.locator('.part[data-part="stack/one"] .dial.ranged')
	box = ranged.bounding_box()

	across = ((40 + 80) / 2 - 1) / (127 - 1)

	panel.mouse.move(box["x"] + box["width"] * across, box["y"] + box["height"] / 2)
	panel.mouse.down()
	panel.mouse.move(box["x"] + box["width"] - 2, box["y"] + box["height"] / 2, steps=8)
	panel.mouse.up()

	low, high = [one for one in fake_app.sets if one["path"] == "stack/one/velocity"][-1]["v"]

	assert high == 127, f"the span did not reach the ceiling: {low}–{high}"
	assert high - low == 40, f"the span was squashed: {low}–{high}"


def test_blocks_nobody_placed_are_not_touching (panel: typing.Any) -> None:
	"""Packed edge to edge they read as one surface with lines drawn on it. A
	lane between them says they are separate things, which they are."""

	panel.locator(".pages button", has_text="All").click()
	panel.wait_for_selector(".grid .cell", timeout=5_000)
	_settled(panel)

	seen = panel.evaluate("""() => {
		const cell = parseFloat(
			getComputedStyle(document.documentElement).getPropertyValue('--cell'));
		const parts = [...document.querySelectorAll('.part')].map(
			(el) => el.getBoundingClientRect());

		const gaps = [];

		for (const one of parts) {
			for (const two of parts) {
				if (one === two) continue;

				const apart = Math.max(two.left - one.right, two.top - one.bottom);

				if (apart >= 0) gaps.push(apart);
			}
		}

		return { cell, closest: gaps.length ? Math.min(...gaps) : null };
	}""")

	assert seen["closest"] is not None, "only one block on the page to compare"
	assert seen["closest"] >= seen["cell"] - 1, \
		f"blocks sit {seen['closest']}px apart, less than one {seen['cell']}px cell"


def test_a_range_dragged_past_the_edge_still_goes_the_way_the_finger_went (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""A finger that overshoots the control is ordinary on a touchscreen, and it
	must not send the span the other way."""

	_open_the_stack(panel)

	ranged = panel.locator('.part[data-part="stack/one"] .dial.ranged')
	box = ranged.bounding_box()
	width = panel.evaluate("() => window.innerWidth")

	beyond = min(box["x"] + box["width"] + 120, width - 4)

	assert beyond > box["x"] + box["width"], "no room to the right to overshoot into"

	across = ((40 + 80) / 2 - 1) / (127 - 1)

	panel.mouse.move(box["x"] + box["width"] * across, box["y"] + box["height"] / 2)
	panel.mouse.down()
	panel.mouse.move(beyond, box["y"] + box["height"] / 2, steps=8)
	panel.mouse.up()

	asked = [one["v"] for one in fake_app.sets if one["path"] == "stack/one/velocity"]

	assert asked, "the drag asked for nothing"

	low, high = asked[-1]

	assert high - low == 40, f"the span changed width: {low}-{high} (all: {asked})"
	assert low > 40, f"overshooting sent the span backwards: {low}-{high} (all: {asked})"


def test_a_pattern_carries_the_button_that_adds_to_its_stack (panel: typing.Any) -> None:
	"""A stack says which pattern it feeds, and that one fact places its
	buttons: the pattern grows the button, not the stack.

	The title bar is the handle and has to stay one, so the foot of the grid is
	where a pattern's own actions accrue — and clear is already the second.
	"""

	_open_the_stack(panel)

	assert panel.locator('.part[data-part="grid"] .part-foot .offer.add').count() == 1
	assert panel.locator('.part[data-part="stack"] .part-foot .offer.add').count() == 0


def test_a_stack_whose_pattern_is_elsewhere_keeps_its_own_button (panel: typing.Any) -> None:
	"""A page showing the stack alone is an ordinary thing to make, and on one
	there would otherwise be no way to add a generator at all."""

	panel.locator(".pages button", has_text="Stack alone").click()
	panel.wait_for_selector(".recipe", timeout=5_000)
	_settled(panel)

	assert panel.locator('.part[data-part="stack"] .part-foot .offer.add').count() == 1


def test_clearing_a_pattern_asks_first_and_says_what_will_go (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""The count is the whole argument for a dialog over an armed button: only a
	dialog can say *what* is about to be lost, and a pattern may be the only
	copy there is until #2067 is settled."""

	_settled(panel)

	panel.locator('.part[data-part="grid"] .part-foot .clear').click()
	panel.wait_for_selector(".sheet", timeout=5_000)

	asking = panel.locator(".sheet .ask").inner_text()

	assert "2 steps" in asking, f"the dialog did not count what would go: {asking!r}"
	assert "Drums" in asking, f"the dialog did not name the pattern: {asking!r}"

	panel.locator(".sheet .answers button", has_text="keep them").click()
	playwright_api.expect(panel.locator(".sheet")).to_have_count(0, timeout=5_000)

	assert not [one for one in fake_app.sets if one["path"] == "grid/rows"]


def test_agreeing_to_clear_empties_the_whole_grid_in_one_request (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""A cell at a time would be a hundred and sixty frames to empty a drum
	pattern, and a clear that stops half way through is worse than one that
	never started."""

	_settled(panel)

	panel.locator('.part[data-part="grid"] .part-foot .clear').click()
	panel.wait_for_selector(".sheet", timeout=5_000)
	panel.locator(".sheet .answers button.danger").click()

	asked = [one for one in fake_app.sets if one["path"] == "grid/rows"]

	assert len(asked) == 1, f"clearing sent {len(asked)} requests"
	assert asked[0]["v"] == {}


# --- Each contribution in its own window (#2109) -----------------------------
#
# A stack drawn as one tall block could not be arranged: two generators sat on
# top of one another and neither could be moved. Simon asked for a window each,
# named and placed like any other, and for a line saying which pattern each one
# builds.


def _two_generators (panel: typing.Any, fake_app: typing.Any) -> None:
	"""Put a second layer in the stack and wait for both windows to draw."""

	held = {"pitch": "kick", "pulses": 3, "velocity": [40, 80],
	        "duration": 1, "probability": 1}

	fake_app.confirm("stack/layers", [
		{"id": "one", "generator": "euclidean", "index": 1, "bypassed": False, "params": held},
		{"id": "two", "generator": "euclidean", "index": 2, "bypassed": False, "params": held},
	], by="app")

	panel.wait_for_function(
		"() => document.querySelectorAll('.recipe .layer').length === 2", timeout=5_000)
	_settled(panel)


def _edges (panel: typing.Any, join: str) -> dict[str, typing.Any]:
	"""Where one line starts and ends, and where the two blocks it joins are.

	All four in the space the blocks are placed in — the wrapper's own scrolled
	content — because that is the space the overlay draws in.
	"""

	return panel.evaluate(
		"""(join) => {
			const wrap = document.querySelector('.grid-wrap');
			const outer = wrap.getBoundingClientRect();
			const at = (name) => {
				const box = document
					.querySelector(`.part[data-part="${name}"]`).getBoundingClientRect();

				return {
					x: box.left - outer.left + wrap.scrollLeft,
					y: box.top - outer.top + wrap.scrollTop,
					w: box.width, h: box.height,
				};
			};

			const [from, to] = join.split(">");
			const line = document.querySelector(`[data-join="${join}"] line`);

			return {
				from: at(from), to: at(to),
				a: { x: +line.getAttribute("x1"), y: +line.getAttribute("y1") },
				b: { x: +line.getAttribute("x2"), y: +line.getAttribute("y2") },
			};
		}""", join)


def _on_the_edge (point: dict[str, float], box: dict[str, float]) -> bool:
	"""Whether a point sits on the boundary of a block, give or take a pixel."""

	slack = 1.5
	inside = (box["x"] - slack <= point["x"] <= box["x"] + box["w"] + slack
	          and box["y"] - slack <= point["y"] <= box["y"] + box["h"] + slack)
	against = (abs(point["x"] - box["x"]) <= slack
	           or abs(point["x"] - box["x"] - box["w"]) <= slack
	           or abs(point["y"] - box["y"]) <= slack
	           or abs(point["y"] - box["y"] - box["h"]) <= slack)

	return inside and against


def test_each_contribution_is_a_window_of_its_own (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Simon: "when I add a second generator, it appears under the first, and the
	two are not independently draggable"."""

	_open_the_stack(panel)
	_two_generators(panel, fake_app)

	assert panel.locator('.part[data-part="stack/one"]').count() == 1
	assert panel.locator('.part[data-part="stack/two"]').count() == 1

	# And the stack itself is no longer a block, because there is nothing left
	# in it that is not in one of these.
	assert panel.locator('.part[data-part="stack"]').count() == 0


def test_a_contribution_is_named_for_its_generator_its_number_and_its_pattern (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""The number is the layer's own for life, so a person can reach for the
	window they read a moment ago.  The pattern is named beside it because a
	line that crosses another is not enough on a busy page.
	"""

	_open_the_stack(panel)
	_two_generators(panel, fake_app)

	second = panel.locator('.part[data-part="stack/two"] .part-title').inner_text().lower()

	assert "euclidean" in second
	assert "2" in second
	assert "drums" in second, f"the pattern is not named: {second!r}"


def test_a_contribution_says_where_it_runs_in_the_stack (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""A stack drawn as one block said this for nothing, by the order its layers
	sat in.  Windows that move freely cannot, and the order is what is heard: a
	fill told to skip an occupied step depends on what ran before it.
	"""

	_open_the_stack(panel)
	_two_generators(panel, fake_app)

	assert panel.locator('.part[data-part="stack/two"] .place').inner_text().strip() == "2 of 2"


def test_a_contribution_moves_on_its_own (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Which is the whole ask: two things a person arranges themselves are two
	things they can find again."""

	_open_the_stack(panel)
	_two_generators(panel, fake_app)

	panel.locator(".bar .latch").click()
	panel.wait_for_selector(".grid-wrap.unlocked", timeout=5_000)

	# In cells rather than in pixels. A drag that makes the arrangement taller
	# re-solves the fit when the finger lifts, so every block's pixel position
	# moves while its place on the lattice does not — and the lattice is what
	# this is about.
	def at (part: str) -> list[int]:
		return panel.evaluate(
			"""(part) => {
				const block = document.querySelector(`.part[data-part="${part}"]`);
				const root = getComputedStyle(document.documentElement);
				const pitch = parseFloat(root.getPropertyValue("--cell"))
					+ parseFloat(root.getPropertyValue("--gap"));

				return [Math.round(parseFloat(block.style.left) / pitch),
				        Math.round(parseFloat(block.style.top) / pitch)];
			}""", part)

	before = at("stack/one")
	was = at("stack/two")

	grip = panel.locator('.part[data-part="stack/two"] .part-title').bounding_box()

	panel.mouse.move(grip["x"] + 20, grip["y"] + 5)
	panel.mouse.down()
	panel.mouse.move(grip["x"] + 20, grip["y"] + 125, steps=8)
	panel.mouse.up()
	_settled(panel)

	assert at("stack/two")[1] > was[1], "the block did not move"
	assert at("stack/one") == before, "its neighbour moved with it"


def test_a_line_joins_each_contribution_to_the_pattern_it_feeds (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Nothing else on the glass says what builds what once the windows are
	scattered, which is why the line arrived with them."""

	_open_the_stack(panel)
	_two_generators(panel, fake_app)

	drawn = panel.eval_on_selector_all(
		".joins .join", "els => els.map((one) => one.dataset.join)")

	assert sorted(drawn) == ["stack/one>grid", "stack/two>grid"]


def test_a_line_runs_between_the_two_nearest_sides (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Corners are deliberately not offered: a line from one reads as pointing
	past a block rather than at it."""

	_open_the_stack(panel)
	_two_generators(panel, fake_app)

	line = _edges(panel, "stack/one>grid")

	assert _on_the_edge(line["a"], line["from"]), f"the tail is not on the generator: {line}"
	assert _on_the_edge(line["b"], line["to"]), f"the head is not on the pattern: {line}"


def test_a_line_carries_a_direction_and_points_at_the_pattern (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Only one direction exists today.  The other one is already named — an
	element that *shows* a property of a pattern rather than controlling it —
	and an arrowhead costs a triangle now against a format change later (#2109).

	The head is at the middle of the line rather than at the end it points to,
	because several contributions feeding one pattern all arrive at the same
	block and heads gathered on its edge merge into a smudge.  So what is
	measured here is which way it points, not where it sits.
	"""

	_open_the_stack(panel)
	_two_generators(panel, fake_app)

	line = _edges(panel, "stack/one>grid")
	head = panel.eval_on_selector(
		'[data-join="stack/one>grid"] path',
		"""one => {
			const [, tip, left, right] = one.getAttribute("d")
				.split(/[MLZ]/).map((part) => part.trim().split(/\s+/).map(Number));

			return { tip: { x: tip[0], y: tip[1] },
			         base: { x: (left[0] + right[0]) / 2, y: (left[1] + right[1]) / 2 } };
		}""")

	def away (point: dict[str, float], other: dict[str, float]) -> float:
		return ((point["x"] - other["x"]) ** 2 + (point["y"] - other["y"]) ** 2) ** 0.5

	assert away(head["tip"], line["b"]) < away(head["base"], line["b"]), (
		f"the head points away from the pattern: {head} on {line}")

	# And it is on the line, near the middle of it, rather than at either end.
	middle = {"x": (line["a"]["x"] + line["b"]["x"]) / 2,
	          "y": (line["a"]["y"] + line["b"]["y"]) / 2}

	assert away(head["tip"], middle) < away(line["a"], line["b"]) / 4, (
		f"the head is not near the middle: {head} on {line}")


def test_a_line_brightens_while_a_hand_is_on_either_end (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Faint the rest of the time, because it crosses the grids rather than
	sitting beside them.  A hand on a block is the moment the question is being
	asked."""

	_open_the_stack(panel)
	_two_generators(panel, fake_app)

	live = panel.locator('[data-join="stack/one>grid"].live')

	assert live.count() == 0, "a line was bright with nothing touched"

	grip = panel.locator('.part[data-part="grid"] .part-title').bounding_box()

	panel.mouse.move(grip["x"] + 20, grip["y"] + 5)
	panel.mouse.down()

	assert live.count() == 1, "the pattern was held and its line stayed faint"

	panel.mouse.up()

	assert live.count() == 0, "the line stayed bright after the hand left"


def test_a_contribution_appears_where_its_stack_does_not_where_its_pattern_does (
	panel: typing.Any) -> None:
	"""How a person chooses to see generators at all (#2085).  A page carrying
	the pattern alone is the uncluttered grid; a page carrying both is the one
	given over to building it.  Inheriting the pattern's pages instead would put
	generators on the page that was made without them.
	"""

	_settled(panel)

	# The opening page carries the pattern and not the stack.
	assert panel.locator('.part[data-part="grid"]').count() == 1
	assert panel.locator(".recipe").count() == 0
	assert panel.locator(".joins").count() == 0


def test_a_contribution_is_drawn_even_where_its_pattern_is_not (
	panel: typing.Any) -> None:
	"""A page showing the stack alone is an ordinary thing to make.  The line
	has nowhere to go, and the window's own title is then the only thing saying
	what it builds — which is why the title says it."""

	panel.locator(".pages button", has_text="Stack alone").click()
	panel.wait_for_selector(".recipe", timeout=5_000)
	_settled(panel)

	assert panel.locator('.part[data-part="stack/one"]').count() == 1
	assert panel.locator(".joins .join").count() == 0
	assert "drums" in panel.locator(
		'.part[data-part="stack/one"] .part-title').inner_text().lower()


def test_a_line_follows_the_block_it_is_joined_to (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Found by another test failing for a reason that took a while to see.

	A dragged block moves without changing size, and this overlay measures the
	page rather than calculating from the lattice — so a resize told it and a
	move did not, and the line stayed where the block had been.
	"""

	_open_the_stack(panel)
	_two_generators(panel, fake_app)

	# A fixed size rather than the fit. Under "fit the glass" a drag usually
	# changes the arrangement's extent and every block is resized to suit, and a
	# resize is a signal this does receive — which hid the defect. Held still,
	# the move is the only thing that happens.
	panel.locator(".sizes > button").click()
	panel.locator(".sizes .choices button", has_text="Compact").click()
	panel.wait_for_function(
		"() => getComputedStyle(document.documentElement).getPropertyValue('--cell') === '22px'",
		timeout=5_000)
	_settled(panel)

	panel.locator(".bar .latch").click()
	panel.wait_for_selector(".grid-wrap.unlocked", timeout=5_000)

	grip = panel.locator('.part[data-part="stack/one"] .part-title').bounding_box()

	panel.mouse.move(grip["x"] + 20, grip["y"] + 5)
	panel.mouse.down()
	panel.mouse.move(grip["x"] + 20, grip["y"] + 130, steps=8)
	panel.mouse.up()
	_settled(panel)

	line = _edges(panel, "stack/one>grid")

	assert _on_the_edge(line["a"], line["from"]), f"the line stayed behind: {line}"


# --- Light, dark, or whatever the machine says -------------------------------
#
# A panel is read in a room, and the room is not this one. Simon asked for all
# three states; the third is the default, because the browser has already been
# told which way round the room is and this has not.


def _ground (panel: typing.Any) -> str:
	"""The colour the page paints behind everything, as the browser resolved it."""

	return str(panel.evaluate("() => getComputedStyle(document.body).backgroundColor"))


def _pick_theme (panel: typing.Any, label: str, key: str) -> None:
	"""Choose a theme and wait for it to land.

	The wait is not politeness.  A state change settles on the next tick and the
	attribute is written by an effect after that, so a test reading the moment
	the click returns reads the theme that was in force before it.
	"""

	panel.locator(".theme > button").click()
	panel.locator(".theme .choices button", has_text=label).click()

	panel.wait_for_function(
		"(key) => (document.documentElement.dataset.theme || 'system') === key",
		arg=key, timeout=5_000)


def test_a_panel_told_nothing_follows_the_machine (panel: typing.Any) -> None:
	"""Which is what "match system" means, and it is the state a panel that has
	never been touched is in."""

	panel.emulate_media(color_scheme="dark")
	dark = _ground(panel)

	panel.emulate_media(color_scheme="light")
	light = _ground(panel)

	assert dark != light, f"the machine's answer changed nothing: {dark}"
	assert panel.evaluate("() => document.documentElement.dataset.theme") in (None, "")


def test_a_pinned_theme_outranks_the_machine (panel: typing.Any) -> None:
	"""The whole of what was missing: somebody whose machine is set light and
	who wants *this* screen dark, in a room with no ceiling lights, had no way
	to say so."""

	panel.emulate_media(color_scheme="light")
	following = _ground(panel)

	_pick_theme(panel, "Dark", "dark")

	assert _ground(panel) != following, "pinning dark against a light machine changed nothing"

	_pick_theme(panel, "Light", "light")

	assert _ground(panel) == following, "pinning light is not what a light machine gives"


def test_a_pinned_theme_is_applied_before_the_app_is_even_loaded (
	panel: typing.Any, service_url: str) -> None:
	"""Otherwise every load flashes the other theme at somebody who pinned one,
	which is the whole reason the boot script is in the head and not in app.js.

	Proved by taking app.js away: whatever sets the attribute with no client on
	the page is the only thing that could have.
	"""

	_pick_theme(panel, "Dark", "dark")

	panel.route("**/client/app.js", lambda route: route.abort())
	panel.goto(service_url)

	assert panel.evaluate("() => document.documentElement.dataset.theme") == "dark"


def test_a_theme_swatch_is_the_theme_it_offers (panel: typing.Any) -> None:
	"""Rather than a copy of it.  Each swatch carries that theme's own
	`color-scheme`, so the ground it paints is the ground the stylesheet paints
	— which is what stops the picker becoming a second place the palette is
	written down and a second place it goes wrong.
	"""

	_pick_theme(panel, "Dark", "dark")

	dark_page = _ground(panel)

	panel.locator(".theme > button").click()

	swatches = panel.eval_on_selector_all(
		".theme .choices i",
		"""els => els.map((one) => [one.dataset.scheme, getComputedStyle(one).backgroundColor])""")
	shown = dict(swatches)

	assert shown["dark"] == dark_page, (
		f"the dark swatch is not the dark ground: {shown} against {dark_page}")
	assert shown["light"] != shown["dark"], f"both swatches are the same colour: {shown}"

	# And "match system" shows the machine's answer rather than the pin. It
	# inherits `color-scheme` like everything else, so while dark is pinned it
	# would otherwise offer a picture of what the person already has.
	panel.emulate_media(color_scheme="light")

	following = panel.eval_on_selector(
		'.theme .choices i[data-scheme="system"]', "one => getComputedStyle(one).backgroundColor")

	assert following == shown["light"], (
		f"the system swatch followed the pin rather than the machine: {following}")


def test_a_theme_outlives_a_reload (panel: typing.Any, service_url: str) -> None:
	"""A setting a person has to make again every time the panel restarts is not
	a setting.  Kept on the panel, like the cell size, because a theme is a
	property of the glass and the room it is in (#2055)."""

	_pick_theme(panel, "Light", "light")
	chosen = _ground(panel)

	panel.goto(service_url)
	panel.wait_for_selector(".cell", timeout=10_000)

	assert _ground(panel) == chosen
	assert "light" in panel.locator(".theme > button").inner_text()
