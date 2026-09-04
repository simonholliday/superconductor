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


def test_arranging_is_latched_and_a_tap_outside_it_still_plays (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""The latch is the only thing between a stray finger and somebody's layout,
	so it has to be entered deliberately and leave the music alone until it is."""

	assert panel.locator(".grid-wrap.arranging").count() == 0

	panel.locator(conftest.cell("grid/snare/1")).click()
	fake_app.await_set("grid/snare/1")

	panel.locator(".bar .arrange").click()

	playwright_api.expect(panel.locator(".grid-wrap.arranging")).to_have_count(1, timeout=5_000)
	assert panel.eval_on_selector(".grid-wrap.arranging .grid", "el => getComputedStyle(el).pointerEvents") == "none"


def test_a_block_is_dragged_by_its_title_a_cell_at_a_time (panel: typing.Any) -> None:
	"""#2078: the title bar is the only surface of a block that is not a control,
	and a drag snaps to the lattice rather than to the pixel."""

	panel.locator(".bar .arrange").click()
	panel.wait_for_selector(".grid-wrap.arranging", timeout=5_000)

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

	panel.locator(".bar .arrange").click()
	panel.wait_for_selector(".grid-wrap.arranging", timeout=5_000)

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

	panel.locator(".bar .arrange").click()
	panel.wait_for_selector(".grid-wrap.arranging", timeout=5_000)

	def depth (part: str) -> int:
		return int(panel.eval_on_selector(f'.part[data-part="{part}"]', "el => getComputedStyle(el).zIndex"))

	panel.locator(".inventory button", has_text="Drums").click()

	assert depth("grid") > depth("second")


def test_an_arrangement_outlives_a_reload (panel: typing.Any) -> None:
	"""Until it can be sent to the composition that owns the page (#2077), a
	layout that vanished on reload would not be a layout."""

	panel.locator(".bar .arrange").click()
	panel.wait_for_selector(".grid-wrap.arranging", timeout=5_000)

	block = panel.locator('.part[data-part="grid"]')
	before = block.bounding_box()
	title = panel.locator('.part[data-part="grid"] .part-title').bounding_box()

	panel.mouse.move(title["x"] + 20, title["y"] + 5)
	panel.mouse.down()
	panel.mouse.move(title["x"] + 20, title["y"] + 200, steps=8)
	panel.mouse.up()

	moved = block.bounding_box()
	assert moved["y"] > before["y"]

	panel.reload()
	panel.wait_for_selector(".cell", timeout=10_000)

	assert abs(panel.locator('.part[data-part="grid"]').bounding_box()["y"] - moved["y"]) < 2


def _open_the_bass (panel: typing.Any) -> None:
	"""Go to the page carrying the pitched pattern."""

	panel.locator(".pages button", has_text="Bass").click()
	panel.wait_for_selector(".grid.notes", timeout=5_000)


def test_a_note_is_drawn_as_a_bar_reaching_across_the_steps_it_lasts (
	panel: typing.Any) -> None:
	"""Which is how every piano roll draws one, and needs no explaining."""

	_open_the_bass(panel)

	cell = panel.locator(conftest.cell("bass/C2/0")).bounding_box()
	note = panel.locator('.cell[data-path="bass/C2/0"] .note').bounding_box()

	assert note["width"] > cell["width"], "a two-step note reaches past its own cell"
	assert round(note["width"]) == round(cell["width"] * 2 + 4), "exactly two steps and the gap between"


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

	scroller = panel.locator('.part[data-part="bass"] .scroller')

	overflow = panel.eval_on_selector(
		'.part[data-part="bass"] .scroller', "el => el.scrollHeight - el.clientHeight")

	assert overflow > 0, "three rows do not fit in a window of two"
	assert scroller.evaluate("el => el.scrollTop > 0"), "opened at the bottom, where a bass line lives"


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

	panel.locator(".pages button", has_text="All").click()
	panel.wait_for_selector(".grid .cell", timeout=5_000)

	def label (part: str) -> dict:
		return panel.eval_on_selector(
			f'.part[data-part="{part}"] .row-label',
			"""el => {
				const seen = getComputedStyle(el);
				return {
					justify: seen.justifyContent,
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

	assert drums["justify"] == pitched["justify"] == "flex-end"
	assert drums["size"] == pitched["size"]
	assert drums["colour"] == pitched["colour"]
	assert drums["rail"] and pitched["rail"], "both carry the mark that says push the view from here"


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

	stacking = panel.eval_on_selector_all(
		'.part[data-part="bass"] .window .track, .part[data-part="bass"] .row-label',
		"els => els.map(el => Number(getComputedStyle(el).zIndex) || 0)")

	assert stacking[0] > max(stacking[1:]), "the mark sits above every label"


def test_the_playhead_cannot_widen_the_page_as_it_wraps (panel: typing.Any) -> None:
	"""It is drawn between beats, so it passes 15.9 of 16 steps before wrapping,
	which put it most of a cell past the last one and flashed a scrollbar up
	once a bar. A block is exactly as wide as its pattern, so it clips."""

	_open_the_bass(panel)

	assert panel.eval_on_selector(
		'.part[data-part="bass"] .part-body',
		"el => getComputedStyle(el).overflow") == "hidden"


def test_a_part_that_fits_draws_no_scroll_mark (panel: typing.Any) -> None:
	"""A mark on a block with nowhere to go would be furniture, and worse, a lie."""

	panel.locator(".pages button", has_text="All").click()
	panel.wait_for_selector(".grid .cell", timeout=5_000)

	assert panel.locator('.part[data-part="grid"] .track').count() == 0


def test_a_cell_looks_the_same_whatever_kind_of_grid_it_is_in (panel: typing.Any) -> None:
	"""A person learns a cell once. Two designs of it would be two to learn."""

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
