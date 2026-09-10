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
import superconductor.protocol
import superconductor.service


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

	# Two keys rather than one word, as a transport has had since tape: which
	# one is engaged is the state, and pressing the engaged one does nothing.
	def engaged () -> str:
		return panel.eval_on_selector(
			".transport .tkeys",
			"""one => {
				const down = one.querySelector(".tkey.engaged");

				return down ? down.getAttribute("title").split(" ")[0] : "neither";
			}""")

	assert engaged() == "play"

	fake_app.confirm("transport/paused", True, by="app")
	panel.wait_for_selector('.transport .tkey.engaged[title^="pause"]', timeout=5_000)

	fake_app.confirm("transport/paused", False, by="app")
	panel.wait_for_selector('.transport .tkey.engaged[title^="play"]', timeout=5_000)


def test_the_counter_says_which_bar_beat_and_step (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""The largest thing in the transport, because on every machine these users
	own it is: an 808, an MPC, a tape remote, Logic's bar.  Ours had a big word
	reading PAUSE and no position at all, which is that arrangement inverted.

	``bar · beat · step`` — Ableton's bar.beat.sixteenth, said in the units this
	pattern actually has, and all of it arithmetic on what the beat event
	already carries.  The fixture's grid is eight steps over two beats, so a
	beat is four steps and a bar is two beats.
	"""

	fake_app.confirm("transport/paused", True, by="app")
	panel.wait_for_selector('.transport .tkey.engaged[title^="pause"]', timeout=5_000)

	# Held, so the reading is the beat itself rather than an extrapolation —
	# which is what makes this measurable at all.
	fake_app.beat(0)
	playwright_api.expect(panel.locator(".lcd.count .lcd-value")).to_have_text("001·1·1", timeout=5_000)

	fake_app.beat(1)
	playwright_api.expect(panel.locator(".lcd.count .lcd-value")).to_have_text("001·2·1", timeout=5_000)

	# Two beats to a bar in this fixture, so beat 2 is where the second begins.
	fake_app.beat(2)
	playwright_api.expect(panel.locator(".lcd.count .lcd-value")).to_have_text("002·1·1", timeout=5_000)

	fake_app.beat(9)
	playwright_api.expect(panel.locator(".lcd.count .lcd-value")).to_have_text("005·2·1", timeout=5_000)


def test_there_is_no_stop_key_because_the_app_declares_no_stop (
	panel: typing.Any) -> None:
	"""#2054's pause holds the clock rather than stopping it, and a stop that
	returns to bar one is a different operation this app does not offer.

	The rule since #2046 is that the panel loses a control rather than gaining a
	broken one — so it is not drawn.  Not drawn dimmed, which is furniture: a
	key that can never be pressed is a key that has to be explained.
	"""

	assert panel.locator(".transport .tkey").count() == 2, "the transport has a third key"


def test_a_dot_stops_being_drawn_when_it_stops_being_true (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""Simon: the Euclidean feeding the kick is off, and its dots are still on
	the grid, never changing.

	They were.  A dot means "an algorithm put this here *this cycle*", and it
	arrives as an event sent once a cycle (#1965) — so with the transport held
	there is no cycle, nothing new arrives, and the last set the panel received
	stays on the glass.  It outlived the cycle that put it there and then
	outlived the generator itself.

	Two things end it, and both heal on the next cycle: holding the clock, and
	changing the stack — because bypassing a generator makes every dot it
	contributed a statement about a cycle that will not happen.
	"""

	_settled(panel)

	fake_app.realised("grid", {"kick": {"2": 100, "6": 90}})
	panel.wait_for_selector('.part[data-part="grid"] .cell.ghost', timeout=5_000)

	fake_app.confirm("transport/paused", True, by="app")

	playwright_api.expect(
		panel.locator('.part[data-part="grid"] .cell.ghost')).to_have_count(0, timeout=5_000)


def test_changing_a_stack_takes_its_dots_with_it (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""The other half, and the one that matters while the clock is running: a
	generator switched off has not played the notes still drawn under it."""

	_open_the_stack(panel)

	fake_app.realised("grid", {"kick": {"1": 100}})
	panel.wait_for_selector('.part[data-part="grid"] .cell.ghost', timeout=5_000)

	fake_app.confirm("stack/layers", [
		{"id": "one", "generator": "euclidean", "index": 1, "bypassed": True, "params": {}},
	], by="app")

	playwright_api.expect(
		panel.locator('.part[data-part="grid"] .cell.ghost')).to_have_count(0, timeout=5_000)


def test_everything_on_the_bar_is_one_height (panel: typing.Any) -> None:
	"""Simon: "I'd like to see consistent heights and spacing between items
	where possible."

	Two readouts set at two type sizes came out two heights, which he spotted at
	a glance.  A display sits on the chrome surface like anything else: its
	contents fit it rather than deciding it.
	"""

	_settled(panel)

	tall = panel.evaluate("""() => {
		const out = {};

		for (const one of document.querySelectorAll(".bar button, .bar .lcd")) {
			const at = Math.round(one.getBoundingClientRect().height);

			out[at] = out[at] || [];
			out[at].push(one.className || one.tagName);
		}

		return out;
	}""")

	assert len(tall) == 1, f"the bar draws its controls at {sorted(tall)}px: {tall}"


def test_a_readout_centres_its_figures_and_not_its_boxes (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""The counterpart to the test above, and found the same way — by eye.

	Simon: "The numbers ... are aligned more closely to the top of the space
	than the bottom.  It looks a little cramped."  He was right by 2.3px in a
	44px chassis: `.lcd-value` declared `line-height: 1` and `.lcd-label` did
	not, so the label took the body's 1.4 and carried a sentence's leading under
	one line of panel lettering.

	Centring is done on *boxes*, and a box is not its ink.  Digits and capitals
	never reach into a font's descender space, so every bit of that leading
	landed below the label while the figures stayed hard against the top — which
	is why nothing measuring rectangles could see it, the test above included.

	So this one measures the ink.  `text-box-trim` is the feature that would
	make the question unnecessary and Firefox 153 does not implement it, so the
	arithmetic stays ours to get right and ours to hold.
	"""

	_settled(panel)

	# Both readouts have to be holding figures.  Written against whatever the
	# page happened to show, this measured the em dash that stands in for a
	# reading nobody has sent — whose ink is a thin bar near the middle, so it
	# sits 14px down a 44px chassis and always will.  That is not the rule.
	fake_app.confirm("transport/paused", True, by="app")
	fake_app.beat(0)
	fake_app.confirm("transport/bpm", 137.5, by="app")

	playwright_api.expect(
		panel.locator(".lcd.count .lcd-value")).to_have_text("001\u00b71\u00b71", timeout=5_000)
	playwright_api.expect(
		panel.locator(".lcd:not(.count) .lcd-value")).to_contain_text("137.5", timeout=5_000)

	space = panel.evaluate("""() => {
		/* Where a font actually puts its ink inside a line box, rather than
		   where the box is.  `measureText` reports both, and the difference is
		   the whole defect. */
		const ink = (el, text) => {
			const style = getComputedStyle(el);
			const pen = document.createElement("canvas").getContext("2d");

			pen.font =
				`${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;

			const m = pen.measureText(text);
			const box = el.getBoundingClientRect();
			const lead =
				(box.height - (m.fontBoundingBoxAscent + m.fontBoundingBoxDescent)) / 2;
			const base = box.top + lead + m.fontBoundingBoxAscent;

			return { top: base - m.actualBoundingBoxAscent,
			         bottom: base + m.actualBoundingBoxDescent };
		};

		const out = {};

		for (const lcd of document.querySelectorAll(".lcd")) {
			const box = lcd.getBoundingClientRect();
			const value = lcd.querySelector(".lcd-value");
			const label = lcd.querySelector(".lcd-label");

			out[lcd.className] = [
				ink(value, value.textContent.trim()).top - box.top,
				box.bottom - ink(label, label.textContent.trim().toUpperCase()).bottom,
			];
		}

		return out;
	}""")

	assert space, "the bar drew no readouts to measure"

	for what, (above, below) in space.items():
		assert abs(above - below) < 1, (
			f"`{what}` draws its figures {above:.2f}px from the top of the chassis "
			f"and its label {below:.2f}px from the bottom")


def test_the_tempo_reading_follows_the_app (panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""So a ramp or a poke from elsewhere shows, not just what was last tapped."""

	fake_app.confirm("transport/bpm", 137.5, by="app")

	playwright_api.expect(
		panel.locator(".lcd:not(.count) .lcd-value")).to_contain_text("137.5", timeout=5_000)


def test_a_refused_request_says_why_and_gives_the_cell_back (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""The only moment a panel can tell the player that something did not happen."""

	panel.locator(conftest.cell("grid/kick/1")).click()
	asked = fake_app.await_set("grid/kick/1")
	fake_app.refuse("grid/kick/1", asked["client"], asked["seq"], "this grid has no room for that")

	playwright_api.expect(panel.locator(".bar .warn")).to_contain_text("no room", timeout=5_000)
	assert "on" not in (panel.locator(conftest.cell("grid/kick/1")).get_attribute("class") or "")

	# **The cell says so itself, and not only the bar** (#2429).  `.cell.failed`
	# is drawn in three places and was asserted in none: the only test naming it
	# waits for it *not* to appear and passes on timeout, so the class could have
	# been renamed or dropped and nothing would have noticed but that test
	# getting seven seconds faster.
	playwright_api.expect(
		panel.locator(conftest.cell("grid/kick/1"))).to_have_class(
			re.compile(r"\bfailed\b"), timeout=5_000)


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

	# **Above the smallest size a person can choose, not above the chrome
	# finger.** It read `> 44` — the fixed size a control in the chrome takes —
	# and that was never this cell's floor: a step cell is the most tapped thing
	# on the surface and shrinks to 22px without complaint (#2107 §6). The number
	# held only because this page carried two blocks; it carries three now that a
	# stack travels with its pattern (#2211), and 39px is the fit working rather
	# than failing. What a regression would look like is the minimum, or overflow.
	assert fitted > 22, "a fitted grid should use the space it has, not the least it can"

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

	import superconductor.service

	marker = superconductor.service.CLIENT_DIR / ".build-changed-by-a-test"

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

	# By name: a count also sweeps up the stack that travels with `grid` (#2211),
	# and what this test is about is that the *second* grid is drawn at all.
	assert panel.locator('.part[data-part="grid"]').count() == 1
	assert panel.locator('.part[data-part="second"]').count() == 1
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

	assert panel.locator(
		'.part[data-part="grid"] .part-title > b').inner_text().strip().lower() == "drums"
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
	for surface in (".grid-wrap", ".row-label"):
		assert action(surface) != "none", f"{surface} is not a control and should take hold of the page"

	assert "pinch" not in action("body"), "pinch zoom is still the browser claiming a musician's gesture"

	# **A title bar is a grip while the layout is unlocked, and a place to push
	# from while it is held** — and unlocked is the default since #2215, so it is
	# a grip by default now. #2073 listed four surfaces a page could be pushed
	# from and the title bar was one of them; that is a real cost of the flipped
	# default and it is worth stating rather than discovering. The gutters, the
	# space between blocks and the row labels are the three that remain, which is
	# why the loop above still has something in it.
	assert action(".part-title") == "none", (
		"an unlocked title bar is a drag handle and must not scroll the page out"
		" from under the finger dragging it")

	_locked(panel)

	assert action(".part-title") != "none", (
		"a held layout gives the title bar back as somewhere to push the page from")

	_unlocked(panel)


def _on_the_drums_page (panel: typing.Any) -> None:
	"""The Drums page carries one grid and the All page carries two.

	**Asked by name rather than by counting blocks**, which is what these tests
	are actually about: which page is showing.  A count was the wrong question
	and became the wrong answer the moment a stack started travelling with the
	pattern it builds (#2211) — every one of these went red over a fact none of
	them was written to check.
	"""

	playwright_api.expect(panel.locator('.part[data-part="grid"]')).to_have_count(1, timeout=5_000)
	assert panel.locator('.part[data-part="second"]').count() == 0


def _on_the_all_page (panel: typing.Any) -> None:
	"""The page a panel opens on, which carries both grids."""

	playwright_api.expect(panel.locator('.part[data-part="grid"]')).to_have_count(1, timeout=5_000)
	assert panel.locator('.part[data-part="second"]').count() == 1


def test_a_page_shows_only_the_parts_it_carries (panel: typing.Any) -> None:
	"""A page is a view over some of what an app offers, not all of it (#2075).

	**With one amendment, which is #2211**: a stack goes wherever the pattern it
	builds goes, whether or not the page names it.  That is not this rule being
	weakened — the button that creates a generator sits on the *pattern*, and is
	offered on every page carrying that pattern, so a page drawing the button and
	not the result was the incoherence rather than the tidiness.
	"""

	_on_the_all_page(panel)

	panel.locator(".pages button", has_text="Drums").click()
	_on_the_drums_page(panel)

	# And the stack came with it, unnamed by that page.
	assert panel.locator(".recipe").count() > 0, (
		"a pattern's generators did not follow it onto a page that carries it")


def test_the_page_a_panel_is_on_survives_a_reload (panel: typing.Any) -> None:
	"""In performance a reload must return a player to their own page, not to
	whichever one the composition happened to declare first."""

	panel.locator(".pages button", has_text="Drums").click()
	_on_the_drums_page(panel)

	panel.reload()
	panel.wait_for_selector(".cell", timeout=10_000)

	_on_the_drums_page(panel)


def test_a_page_named_in_the_address_is_the_one_that_opens (
	panel: typing.Any, service_url: str) -> None:
	"""So a performer's tablet can be pointed once and left alone, with no code."""

	panel.goto(f"{service_url}/?page=drums")
	panel.wait_for_selector(".cell", timeout=10_000)

	_on_the_drums_page(panel)


def test_a_remembered_page_that_is_no_longer_offered_is_not_forgotten (
	panel: typing.Any, service_url: str) -> None:
	"""A composition restarted without one pattern should not cost a performer
	the page they had set, once it comes back."""

	panel.evaluate("() => localStorage.setItem('superconductor.page', 'a-page-that-went-away')")
	panel.reload()
	panel.wait_for_selector(".cell", timeout=10_000)

	_on_the_all_page(panel)
	assert panel.evaluate("() => localStorage.getItem('superconductor.page')") == "a-page-that-went-away"


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



def _unlocked (panel: typing.Any) -> None:
	"""Make sure the layout can be dragged, whatever it was.

	**Ensured rather than toggled**, which is the whole point: these read as
	"unlock the layout" and were a bare click on the latch, so every one of them
	*locked* it the day unlocked became the default (#2215) and twenty-one tests
	went red at once.  A step that assumes the state it is changing from is a
	step that breaks when the default moves.
	"""

	if panel.locator(".grid-wrap.unlocked").count() == 0:
		panel.locator(".bar .latch").click()

	panel.wait_for_selector(".grid-wrap.unlocked", timeout=5_000)


def _locked (panel: typing.Any) -> None:
	"""And the other way, for the state that is now the exceptional one."""

	if panel.locator(".grid-wrap.unlocked").count() != 0:
		panel.locator(".bar .latch").click()

	panel.wait_for_selector(".grid-wrap.unlocked", state="detached", timeout=5_000)


def test_the_latch_holds_the_layout_still_and_never_the_music (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""It used to be a mode: either you moved blocks or you played, never both,
	and the cells stopped answering while it was on.

	There was never a reason for the exclusion. The handle is the title bar,
	which carries no controls, so a drag and a tap cannot mean the same thing.
	What the latch is for is *unintended* movement — so it holds the layout
	still, and the grid goes on playing on both sides of it.
	"""

	assert panel.locator(".grid-wrap.unlocked").count() == 1, "unlocked by default (#2215)"

	panel.locator(conftest.cell("grid/snare/1")).click()
	fake_app.await_set("grid/snare/1")

	# And the music goes on answering on the other side of the latch, which is
	# the whole point of it not being a mode. Locking is the exceptional state
	# now, so that is the direction worth demonstrating.
	_locked(panel)

	panel.locator(conftest.cell("grid/snare/3")).click()
	fake_app.await_set("grid/snare/3")


def test_a_locked_layout_does_not_move_under_a_drag (panel: typing.Any) -> None:
	"""Which is what the padlock is for: a stray finger on a title bar costs
	nothing until somebody says it may.

	Locked on purpose now rather than found that way: unlocked is the default
	since #2215, so relying on the default would test the default rather than
	the padlock.
	"""

	_locked(panel)
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

	_unlocked(panel)

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

	_unlocked(panel)

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

	_unlocked(panel)

	def depth (part: str) -> int:
		return int(panel.eval_on_selector(f'.part[data-part="{part}"]', "el => getComputedStyle(el).zIndex"))

	# **Exact, not a substring.** A generator's own entry is named after the
	# pattern it builds — "euclidean 1 · Drums" — so `has_text` matched two
	# buttons the moment a stack started travelling with its pattern (#2211).
	panel.locator(".inventory").get_by_role("button", name="Drums", exact=True).click()

	assert depth("grid") > depth("second")


def test_an_arrangement_outlives_a_reload (panel: typing.Any) -> None:
	"""Until it can be sent to the composition that owns the page (#2077), a
	layout that vanished on reload would not be a layout."""

	_unlocked(panel)

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
	_locked(panel)
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

	# Exactly two cells, with no gap to account for: the lattice has none, which
	# is the simplification that removed a whole class of geometry bug.
	assert round(drawn["note"]) == round(drawn["cell"] * 2), "exactly two steps"


def test_pressing_an_empty_cell_places_a_note (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""On the finger landing, as every other control here acts (#2046)."""

	_open_the_bass(panel)

	panel.locator(conftest.cell("bass/D2/3")).click()

	assert fake_app.await_set("bass/D2/3")["v"] is True


def test_a_note_is_taken_away_by_a_second_tap_and_not_the_first (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""Simon's call, once a drag on a note started meaning move it.

	A tap that both selects and deletes cannot tell a nudge from a decision:
	the same press begins a move, so a shaky finger on glass would delete what
	it meant to shift. The first tap selects, which is also the state the
	length values below the grid act on.
	"""

	_open_the_bass(panel)

	panel.locator(conftest.cell("bass/C2/0")).click(position={"x": 3, "y": 3})

	panel.wait_for_selector('.part[data-part="bass"] .grid.notes .note.chosen', timeout=5_000)
	assert not [frame for frame in fake_app.sets if frame.get("path") == "bass/C2/0"], \
		"the first tap asked the sequencer for nothing"

	panel.locator(conftest.cell("bass/C2/0")).click(position={"x": 3, "y": 3})

	assert fake_app.await_set("bass/C2/0")["v"] is False


def test_pressing_the_middle_of_a_note_takes_that_note_away (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""A bar is one thing on the glass, so every cell of it is the same target.

	The fixture holds a two-step note at ``C2/0``, so ``C2/1`` is under the bar
	and holds no note of its own.  Before this, a tap there read as a tap on an
	empty cell and placed a second note underneath the first — silent as a
	second note, and on a monophonic part it retriggered the envelope and cut
	the long note short.

	Two taps, because the first of them selects.
	"""

	_open_the_bass(panel)

	panel.locator(conftest.cell("bass/C2/1")).click()
	panel.locator(conftest.cell("bass/C2/1")).click()

	assert fake_app.await_set("bass/C2/0")["v"] is False, "the note it landed on, taken away"
	assert not [frame for frame in fake_app.sets if frame.get("path") == "bass/C2/1"], \
		"nothing was placed in the cell the bar covers"


def test_the_cell_past_a_note_is_still_its_own (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""The bar claims the cells it covers and not one more.

	The companion to the test above, and the one that catches a coverage map
	counting a step too far: ``C2/2`` is the first cell the two-step note does
	not reach, so a tap there places a note of its own.
	"""

	_open_the_bass(panel)

	panel.locator(conftest.cell("bass/C2/2")).click()

	assert fake_app.await_set("bass/C2/2")["v"] is True


def _at_tested_size (panel: typing.Any) -> None:
	"""Pin the cell to a known size, so a drag can be measured in cells.

	Every geometric gesture below needs to know what a cell is worth in pixels,
	and the automatic fit picks whatever the window allows.
	"""

	panel.locator(".sizes > button").click()
	panel.locator(".sizes .choices button", has_text="Tested").click()
	panel.wait_for_function(
		"() => getComputedStyle(document.documentElement).getPropertyValue('--cell') === '44px'",
		timeout=5_000)


def _drag (panel: typing.Any, selector: str, dx: float, dy: float = 0) -> None:
	"""Drag with the real mouse, from the middle of one element.

	Real presses rather than dispatched ``PointerEvent``s because the handler
	calls ``setPointerCapture``, which throws on a synthetic ``pointerId`` and
	takes the handler down with it before it does anything at all.  Moved in
	steps so the intermediate ``pointermove`` the gesture needs actually
	arrives, and kept inside the window because Playwright clamps a move to the
	viewport silently — a drag aimed past the edge lands wherever the clamp puts
	it, which has read as a drag the other way.
	"""

	# Scrolled to first, because a bounding box is returned for an element the
	# block has scrolled out of sight just as readily as for one on the glass —
	# and the mouse would then be driven to where it merely would have been.
	# `click()` does this for itself, which is why only the raw-mouse drags
	# needed it and only they were silently landing on nothing.
	panel.locator(selector).scroll_into_view_if_needed()

	box = panel.locator(selector).bounding_box()
	x = box["x"] + box["width"] / 2
	y = box["y"] + box["height"] / 2

	panel.mouse.move(x, y)
	panel.mouse.down()
	panel.mouse.move(x + dx, y + dy, steps=8)
	panel.mouse.up()


def test_the_snap_selector_offers_what_the_grid_can_hold (panel: typing.Any) -> None:
	"""And nothing it could not store.

	The fixture's bass is eight steps over two beats and declares no divisions,
	so a beat is four positions.  A snap has to tile a beat exactly, which
	leaves a quarter, an eighth and a sixteenth — and rules out the dotted and
	triplet values without anybody having to name them, because neither divides
	four.
	"""

	_open_the_bass(panel)

	# Named rather than positional. This read `.note-row:first-child` until a
	# transposition row was added above it, at which point it silently measured
	# a different control and reported four values of `undefined` — a selector
	# that says where a thing sits rather than what it is.
	offered = panel.eval_on_selector_all(
		'.part[data-part="bass"] .note-controls button[data-snap]',
		"els => els.map(el => el.dataset.snap)")

	assert offered == ["1/4", "1/8", "1/16"], f"the snap row offered {offered}"


def test_the_snap_starts_at_one_drawn_cell (panel: typing.Any) -> None:
	"""Which is what every gesture did before there was a choice."""

	_open_the_bass(panel)

	assert panel.locator(
		'.part[data-part="bass"] .note-controls button[data-snap="1/16"].on').count() == 1


def test_a_selected_note_takes_its_length_from_a_named_value (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""The route to a length no edge grip could reach.

	The finest values are two or three pixels of bar, and a dotted eighth is
	not somewhere a drag arrives; a musician picks the value they were thinking
	of instead.
	"""

	_open_the_bass(panel)

	panel.locator(conftest.cell("bass/C2/0")).click(position={"x": 3, "y": 3})
	panel.locator('.part[data-part="bass"] .note-controls button[data-length="1/4"]').click()

	assert fake_app.await_set("bass/C2/0/length")["v"] == 4


def test_the_note_row_says_nothing_is_selected_until_something_is (
	panel: typing.Any) -> None:
	"""And keeps its height either way, so the block below it holds still."""

	_open_the_bass(panel)

	assert panel.locator('.part[data-part="bass"] .note-controls .note-row.idle').count() == 1

	panel.locator(conftest.cell("bass/C2/0")).click(position={"x": 3, "y": 3})

	assert panel.locator('.part[data-part="bass"] .note-controls .note-row.idle').count() == 0


def test_dragging_a_note_moves_it (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""Taken away and put back, because a note is addressed by where it starts.

	There is no set that says "the same note, elsewhere" — so the old address
	goes first and the new one is placed with the length it had.
	"""

	_open_the_bass(panel)
	_at_tested_size(panel)

	_drag(panel, conftest.cell("bass/C2/0"), dx=48)

	assert fake_app.await_set("bass/C2/1")["v"] is True, "put back one step later"
	assert fake_app.await_set("bass/C2/0")["v"] is False, "taken away where it was"
	assert fake_app.await_set("bass/C2/1/length")["v"] == 2, "and kept its length"


def test_a_drag_that_goes_nowhere_is_still_a_tap (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""Which is most taps on glass, and the whole reason there is a threshold."""

	_open_the_bass(panel)
	_at_tested_size(panel)

	_drag(panel, conftest.cell("bass/C2/0"), dx=3)

	panel.wait_for_selector('.part[data-part="bass"] .grid.notes .note.chosen', timeout=5_000)
	assert not [frame for frame in fake_app.sets
	            if str(frame.get("path") or "").startswith("bass/")], \
		"a wobble asked the sequencer for nothing"


def test_dragging_out_from_empty_ground_places_a_note_and_sizes_it (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""Placed on the landing and sized on the release.

	The placing is immediate because #2046 says a press acts on the finger
	landing; only the length waits, because that is what the drag decided.
	"""

	_open_the_bass(panel)
	_at_tested_size(panel)

	_drag(panel, conftest.cell("bass/D2/2"), dx=96)

	assert fake_app.await_set("bass/D2/2")["v"] is True

	# The last of them, not the first: placing sends the snap's own length so
	# the note exists at a legal size from the moment it is drawn, and the
	# release then sends what the drag actually decided.
	fake_app.await_set("bass/D2/2/length")
	lengths = [frame["v"] for frame in fake_app.sets if frame.get("path") == "bass/D2/2/length"]

	assert lengths[0] == 1, "placed at the snap's own length"
	assert lengths[-1] == 3, f"and sized by the drag: {lengths}"


def test_zooming_right_out_stops_the_grid_taking_taps (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""Simon asked for a view to get oriented from, not one to work in.

	At a cell this size a tap is a coin toss, so a page that still accepted one
	would be turning a look into an edit.
	"""

	_open_the_bass(panel)
	_at_tested_size(panel)

	_two_fingers(panel, apart=400, then=40)

	panel.wait_for_selector(".grid-wrap.overview", timeout=5_000)

	panel.locator(conftest.cell("bass/D2/3")).click(force=True)

	assert not [frame for frame in fake_app.sets
	            if str(frame.get("path") or "").startswith("bass/")], \
		"nothing was asked for from a view that cannot be aimed at"


def _open_the_fine_grid (panel: typing.Any) -> None:
	"""Go to the page carrying a grid that divides a step."""

	panel.locator(".pages button", has_text="Bass").click()
	panel.wait_for_selector('.part[data-part="fine"] .grid.notes', timeout=5_000)
	_settled(panel)


def test_a_note_inside_a_step_is_drawn_across_the_cell_and_not_the_gap (
	panel: typing.Any) -> None:
	"""Simon found this at 1/32: the marks did not line up with the cells.

	A step boundary is where a cell begins, and a step occupies the cell *plus*
	the gap after it — so a position measured as a fraction of ``cell + GAP`` is
	right for anything crossing a boundary and wrong for everything that does
	not. It put the half-step two pixels right of where a person reads the
	middle, which at a whole step is invisible and at a thirty-second is the
	only thing there is to look at.

	The fixture's fine grid divides a step into four and holds a note at
	position 6 — halfway through the second step — running half a step. So it
	must begin at the middle of that cell and end exactly on its right edge.
	"""

	_open_the_fine_grid(panel)

	drawn = panel.evaluate("""() => {
		const cell = document.querySelector('.cell[data-path="fine/C2/4"]');
		const note = cell.querySelector('.note');
		const box = cell.getBoundingClientRect();
		const bar = note.getBoundingClientRect();

		return { left: bar.left - box.left, right: box.right - bar.right, width: box.width };
	}""")

	middle = drawn["width"] / 2

	assert abs(drawn["left"] - middle) <= 1.5, (
		f"a note halfway through a step began {drawn['left']}px into a "
		f"{drawn['width']}px cell, and the middle is {middle}px")
	assert abs(drawn["right"]) <= 1.5, (
		f"a note ending on a step boundary stopped {drawn['right']}px short of "
		f"the cell edge — reaching into the lane that separates two cells")


def test_a_note_shorter_than_a_step_is_that_fraction_of_the_cell (
	panel: typing.Any) -> None:
	"""The other half of the same arithmetic, and the one that would catch a
	width measured over the gap: a quarter-step note is a quarter of the ink,
	not a quarter of the ink and the lane after it."""

	_open_the_fine_grid(panel)

	drawn = panel.evaluate("""() => {
		const cell = document.querySelector('.cell[data-path="fine/C2/0"]');
		return {
			cell: cell.getBoundingClientRect().width,
			note: cell.querySelector('.note').getBoundingClientRect().width,
		};
	}""")

	assert abs(drawn["note"] - drawn["cell"] / 4) <= 1.5, (
		f"a quarter-step note was {drawn['note']}px of a {drawn['cell']}px cell")


def test_the_subdivision_marks_are_spaced_across_the_cell (panel: typing.Any) -> None:
	"""Which is what Simon was actually looking at when he reported it.

	At 1/32 on a grid dividing a step into four, the marks fall every two
	positions — so exactly one of them lands in each cell, at its middle. Spaced
	over ``cell + GAP`` instead it sat past the middle, and a mark that does not
	agree with the cell it is drawn in is worse than no mark at all.
	"""

	_open_the_fine_grid(panel)

	panel.locator('.part[data-part="fine"] button[data-snap="1/32"]').click()
	panel.wait_for_selector('.part[data-part="fine"] .subs', timeout=5_000)

	spacing = panel.evaluate("""() => {
		const cell = document.querySelector('.cell[data-path="fine/C2/0"]');
		const marks = cell.querySelector('.subs');

		return {
			period: parseFloat(getComputedStyle(marks).backgroundSize),
			cell: cell.getBoundingClientRect().width,
		};
	}""")

	assert abs(spacing["period"] - spacing["cell"] / 2) <= 0.5, (
		f"marks every {spacing['period']}px in a {spacing['cell']}px cell, "
		f"which puts them at {spacing['period'] / spacing['cell']:.0%} across "
		f"rather than the half")


def test_the_velocity_lane_shapes_the_note_in_its_column (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""A lane rather than a dial: the whole dynamic shape is visible at once."""

	_open_the_bass(panel)

	bar = panel.locator('.part[data-part="bass"] .lane .weight[data-velocity="0"]').bounding_box()

	panel.mouse.move(bar["x"] + bar["width"] / 2, bar["y"] + 2)
	panel.mouse.down()
	panel.mouse.up()

	asked = fake_app.await_set("bass/C2/0/velocity")

	assert asked["v"] > 100, "pressing near the top of the lane asks for a hard hit"


def test_the_lane_does_nothing_where_there_is_no_note (
	panel: typing.Any, fake_app: conftest.FakeApp) -> None:
	"""A velocity with no note is not a state the sequencer could report."""

	_open_the_bass(panel)

	bar = panel.locator('.lane .weight[data-velocity="5"]').bounding_box()

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
					bare: seen.backgroundImage === "none",
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
	# A label is a mark: no surface, no edge, in either kind of block. It used to
	# carry a dot at its left edge, stacking into a rail down the column —
	# leftover furniture from before there was a rule for what a target looks
	# like, and Simon read it as exactly that. Scrolling is what everything but a
	# cell already does; it needs no announcing.
	assert drums["bare"] and pitched["bare"], "a row label is drawing something"


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


def test_each_kind_of_grid_draws_its_cells_one_way (panel: typing.Any) -> None:
	"""The two kinds differ, on purpose, and each is consistent with itself.

	This used to say a cell looks the same in every grid — a person learns a
	cell once — and Simon overturned it deliberately, knowing it introduces a
	difference in a pass about consistency.  The reasoning is that these are two
	instruments, not two designs of one: a step grid is a drum machine and its
	cells are pads, spaced, which is the 808 sitting in front of him.  A pitched
	grid is a piano roll, and every editor he uses draws one as a lattice with
	no gaps — because a note can begin between two steps and has to be drawn
	where it actually is.

	So what is tested is what is actually claimed: **pads are pads and lattice
	is lattice, and no cell is a third thing.**
	"""

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
	also_pitched = cell_shape(conftest.cell("bass/D2/3"))

	panel.locator(".pages button", has_text="All").click()
	panel.wait_for_selector(".grid .cell", timeout=5_000)

	drums = cell_shape(conftest.cell("grid/snare/1"))
	also_drums = cell_shape(conftest.cell("grid/kick/2"))

	assert pitched == also_pitched, "a pitched grid draws its cells two ways"
	assert drums == also_drums, "a step grid draws its cells two ways"

	assert drums != pitched, "the two kinds are the same, and one of them is wrong for its job"
	assert float(pitched["radius"].rstrip("px")) == 0, "a lattice cell is square-cornered"
	assert float(drums["radius"].rstrip("px")) > 0, "a pad is not"


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

	_unlocked(panel)

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
	# The fixture opens with two layers — a euclidean and a chord patched at the
	# note set (#2374) — and adding appends to what is there rather than
	# replacing it, which is the whole of what an absolute set has to get right.
	assert [layer["generator"] for layer in asked[-1]["v"]] \
		== ["euclidean", "chord", "euclidean"]


def _open_a_chord (panel: typing.Any, fake_app: typing.Any) -> typing.Any:
	"""A stack holding one generator that names several pitches, drawn and open."""

	_open_the_stack(panel)

	fake_app.confirm("stack/layers", [
		{"id": "one", "generator": "chord", "bypassed": False,
		 "params": {"pitches": ["kick"], "shape": ["up"]}},
	], by="panel")

	panel.wait_for_function(
		"() => document.querySelectorAll('.recipe .layer').length === 1", timeout=5_000)

	part = panel.locator('.part[data-part="stack/one"]')
	part.locator(".switch").first.click()

	return part


def test_a_long_pool_of_pitches_takes_several_from_one_menu (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""#2150 on the glass.

	A pitch parameter that takes several pitches had nowhere to go, so the
	adapter dropped it and marked its generator partial — twenty-two of the
	thirty-three a real panel is offered, and every chord and melody writer among
	them.  This is the drawing that ends that.
	"""

	part = _open_a_chord(panel, fake_app)

	picker = part.locator('.setting[data-field="pitches"] .picker')

	# Lower-cased because the panel letters its controls in capitals, which is a
	# surface rule rather than anything this test is about.
	assert "kick" in picker.inner_text().lower()

	picker.click()
	panel.wait_for_selector(".options", timeout=5_000)
	panel.locator(".options button", has_text="snare").click()

	sent = [one for one in fake_app.sets if one["path"] == "stack/one/pitches"]

	assert sent, "picking a second pitch asked for nothing"
	assert sent[-1]["v"] == ["kick", "snare"]


def test_a_pool_menu_stays_open_while_several_are_picked (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Picking several and shutting after the first would be a choice wearing a
	plural.  It closes the way it opened, on its own trigger."""

	part = _open_a_chord(panel, fake_app)

	part.locator('.setting[data-field="pitches"] .picker').click()
	panel.wait_for_selector(".options", timeout=5_000)
	panel.locator(".options button", has_text="snare").click()

	assert panel.locator(".options").count() == 1, "the menu shut after one pick"

	part.locator('.setting[data-field="pitches"] .picker').click()

	playwright_api.expect(panel.locator(".options")).to_have_count(0, timeout=5_000)


def test_a_short_pool_is_drawn_flat_and_a_second_tap_takes_one_back_out (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Few enough to take in at a glance are laid out flat, as a choice's are.

	And picking is a toggle rather than a replacement, which is the whole
	difference between this and the kind it is the plural of.
	"""

	part = _open_a_chord(panel, fake_app)
	buttons = part.locator('.setting[data-field="shape"] .choices button')

	assert buttons.count() == 2

	buttons.filter(has_text="down").click()

	sent = [one for one in fake_app.sets if one["path"] == "stack/one/shape"]

	assert sent[-1]["v"] == ["up", "down"]

	# Confirmed, because the panel's face is the app's value and never its own
	# guess — without this the second tap would be toggling against ["up"] still.
	fake_app.confirm("stack/one/shape", ["up", "down"], by="panel")
	panel.wait_for_function(
		"() => document.querySelectorAll("
		"'.part[data-part=\"stack/one\"] .setting[data-field=\"shape\"] .here').length === 2",
		timeout=5_000)

	buttons.filter(has_text="up").click()

	sent = [one for one in fake_app.sets if one["path"] == "stack/one/shape"]

	assert sent[-1]["v"] == ["down"], "a second tap did not take the pitch back out"


def test_a_choice_is_lettered_by_the_panel_and_not_by_the_app (panel: typing.Any) -> None:
	"""A control's states are named by whoever declares them; the capitals are ours.

	This matters because a composition reading an instrument definition sends the
	state names verbatim — `lcr`, `always`, `legato_only` — and a table of
	prettier labels beside them would be a second copy of the same fact.  It is
	only safe to leave them alone while the panel letters a control itself, so
	that is worth a test rather than a reading of the stylesheet: the rule lives
	in a selector list, and a selector list is exactly the kind of thing that gets
	narrowed by somebody tidying up.
	"""

	panel.locator(".pages button", has_text="Moog").click()
	panel.wait_for_selector(".grid.params", timeout=5_000)

	option = panel.locator('.part[data-part="moog"] .setting[data-field="shape"] .choices button').first

	assert option.inner_text().strip() == "LCR", (
		"the panel stopped lettering a choice, so a state named in an instrument "
		"definition now reads on the glass exactly as it is spelled in the file")


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

	# One whole cell, like every other control on the lattice. Not 44: that floor
	# was removed with an argument (#2107) — a step cell is the most tapped thing
	# on this surface and shrinks to 22 without complaint, so protecting a
	# stepper from a size a person is happily playing at was an inconsistency
	# rather than a trade-off. This asserted 44 and only passed while the page
	# happened to fit at that size.
	row = panel.evaluate(
		"() => parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--row'))")

	for index in range(stepper.locator("button").count()):
		box = stepper.locator("button").nth(index).bounding_box()

		assert box["height"] >= row - 1, f"a stepper button is {box['height']}px, not a cell"
		assert box["width"] >= row - 1, f"a stepper button is {box['width']}px wide, not a cell"


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


def test_transposing_asks_for_a_number_and_moves_nothing_on_its_own (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Two buttons and a readout, which is what hardware offers a performer.

	And the face is the app's, as everywhere else: the panel asks and draws what
	comes back, rather than moving the readout itself.
	"""

	panel.locator(".pages button", has_text="Bass").click()
	_settled(panel)

	block = '.part[data-part="bass"]'

	assert panel.locator(f'{block} [data-transpose="now"]').inner_text().strip() == "0"

	panel.locator(f'{block} [data-transpose="+1"]').click()

	sent = [one for one in fake_app.sets if one["path"] == "bass/transpose"]

	assert sent and sent[-1]["v"] == 1

	fake_app.confirm("bass/transpose", 1, by="panel")
	_settled(panel)

	assert panel.locator(f'{block} [data-transpose="now"]').inner_text().strip() == "+1"


def test_transposing_is_bounded_by_what_the_app_declared (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""The panel draws what it is told rather than inventing a range, and does
	not ask for a value the app would only refuse."""

	panel.locator(".pages button", has_text="Bass").click()
	_settled(panel)

	block = '.part[data-part="bass"]'

	fake_app.confirm("bass/transpose", 3, by="panel")
	_settled(panel)

	panel.locator(f'{block} [data-transpose="+12"]').click()

	sent = [one for one in fake_app.sets if one["path"] == "bass/transpose"]

	assert sent[-1]["v"] == 3, "the panel asked to go past the declared ceiling"


def test_a_row_says_the_pitch_it_sounds_and_says_when_it_sounds_nothing (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""**The whole of why transposition moves the labels** (#2144).

	The panel cannot work these out — it knows a row is called `C2` and nothing
	else — so the app sends the words.  And a row past the instrument's ceiling
	goes silent rather than wrong, which is invisible unless the glass says so.
	"""

	panel.locator(".pages button", has_text="Bass").click()
	_settled(panel)

	block = '.part[data-part="bass"] .grid.notes'

	assert panel.locator(f'{block} .row-label[data-row="C2"]').inner_text().strip() == "C2"

	fake_app.confirm("bass/labels", {"C2": "D2", "C#2": "D#2"}, by="panel")
	fake_app.confirm("bass/unreachable", ["D2"], by="panel")
	_settled(panel)

	assert panel.locator(f'{block} .row-label[data-row="C2"]').inner_text().strip() == "D2"

	assert panel.locator(f'{block} .row-label[data-row="D2"].unreachable').count() == 1, (
		"a row that cannot sound at this offset is drawn exactly like one that can"
	)

	# Marked rather than merely dimmed: colour alone says nothing on this panel.
	struck = panel.locator(f'{block} .row-label[data-row="D2"]').evaluate(
		"el => getComputedStyle(el).textDecorationLine")

	assert "line-through" in struck


def test_an_action_never_draws_a_chosen_button (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""#2179's whole point, on the glass.

	The setting behind this cannot be read back — a Matriarch's voicing is a
	front-panel switch as well as a control change — so a selected button would
	be a claim nobody can stand behind. Pressing one must therefore leave no
	button chosen, however many times it is pressed and whatever the app says.
	"""

	panel.locator(".pages button", has_text="Moog").click()
	panel.wait_for_selector(".grid.params", timeout=5_000)

	buttons = panel.locator('.part[data-part="moog"] .setting[data-field="voicing"] .actions button')

	# **Read off the buttons rather than asked of a class that cannot be there**
	# (#2429).  This asked for `.actions button.here` and got zero from a
	# selector nothing can match: the action branch emits `""` or `"sent"` and
	# never `here`, so it would have passed against a build that drew a chosen
	# state under any other name.
	def marked () -> list[str]:
		return panel.eval_on_selector_all(
			'.part[data-part="moog"] .setting[data-field="voicing"] .actions button',
			"els => els.map((one) => one.className.trim())"
			"          .filter((held) => held && held !== 'sent')")

	assert buttons.count() == 2
	assert marked() == [], f"an action opened with a state on it: {marked()}"

	buttons.filter(has_text="4").click()

	sent = [one for one in fake_app.sets if one["path"] == "moog/voicing"]

	assert sent, "pressing an action asked for nothing"
	assert sent[-1]["v"] == "four"

	# Even after the app has been told, and even if it reported one back.
	fake_app.confirm("moog/voicing", "four", by="panel")
	_settled(panel)

	assert marked() == [], (
		f"an action drew a chosen button ({marked()}), which is a state nobody "
		f"can verify")


def test_an_action_says_a_press_left_the_glass (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""A control that answers a press with nothing reads as a dead one.

	So the press flashes, in the colour a tapped cell's ring uses and for the
	same reason: it says the press was sent, not that anything holds it. Under
	#2107 a control that looks broken is broken, and this is the line between
	honest and broken.
	"""

	panel.locator(".pages button", has_text="Moog").click()
	panel.wait_for_selector(".grid.params", timeout=5_000)

	held = '.part[data-part="moog"] .setting[data-field="voicing"] .actions button'

	button = panel.locator(held).filter(has_text="1")
	resting = button.evaluate("el => getComputedStyle(el).backgroundColor")

	button.click()

	assert panel.locator(f"{held}.sent").count() == 1, "a press showed nothing at all"

	# **Measured rather than inferred from the class.** Asserting only that
	# `.sent` appears would pass against a stylesheet with the rule deleted, and
	# the whole point of the class is what it looks like.
	fired = button.evaluate("el => getComputedStyle(el).backgroundColor")

	assert fired != resting, (
		"a pressed action looks exactly like an unpressed one, so nothing on the "
		"glass says the press was received")

	# And it is an event rather than a selection: it goes on its own, with
	# nothing pressed to clear it, and comes back to where it started.
	panel.wait_for_function(
		f"() => document.querySelectorAll('{held}.sent').length === 0", timeout=5_000)

	assert button.evaluate("el => getComputedStyle(el).backgroundColor") == resting


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

	seen = panel.evaluate("""() => {
		const block = document.querySelector('.part[data-part="stack/one"] .part-body');
		const edges = block.getBoundingClientRect();
		const menu = document.querySelector(".menu .options").getBoundingClientRect();

		return {
			escapes: [...document.querySelectorAll('.menu .options button')].some((one) => {
				const box = one.getBoundingClientRect();
				return box.bottom > edges.bottom + 1 || box.top < edges.top - 1;
			}),
			top: menu.top, bottom: menu.bottom, viewport: window.innerHeight,
		};
	}""")

	assert seen["escapes"], "the menu did not escape the block that clips it"

	# Escaping the block is the point; what must not happen is leaving the glass.
	# The menu's own box is what has to stay on it — an option below the fold of
	# a menu that scrolls is reached by scrolling, which is what the scrolling is
	# for. Asserting on the options instead made this pass or fail on whether
	# they happened to fit, which is not the property.
	assert seen["top"] >= -1, f"the menu is drawn off the top of the screen: {seen}"
	assert seen["bottom"] <= seen["viewport"] + 1, \
		f"the menu is drawn off the bottom of the screen: {seen}"

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

	_unlocked(panel)
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

	_unlocked(panel)
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

	assert shrunk >= 6, f"a pinch went below the floor: {shrunk}px"


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


def test_a_confirmed_clear_empties_the_glass_and_the_service_too (
	panel: typing.Any, fake_app: typing.Any, service_url: str) -> None:
	"""The other half of clearing, and the half that was broken.

	The test above watches the *request* go out and stops there, so it passed
	against a client that ignored `changed` entirely — its name claimed a
	behaviour its body never checked.  This one lets the app answer, the way the
	real adapter answers, and then looks at the glass.

	Both copies are checked, because there are two and they failed differently.
	The panel that asked reads the `changed` frame; a panel arriving afterwards
	reads the service's own copy.  A clear that reached one and not the other
	would look fixed from wherever you happened to be standing.
	"""

	_settled(panel)

	assert "on" in (panel.locator(conftest.cell("grid/kick/0")).get_attribute("class") or ""), \
		"nothing was lit to begin with, so this test proves nothing"

	panel.locator('.part[data-part="grid"] .part-foot .clear').click()
	panel.wait_for_selector(".sheet", timeout=5_000)
	panel.locator(".sheet .answers button.danger").click()

	asked = fake_app.await_set("grid/rows")

	# Answered as `StepGrid.applied` answers it: the rows as they now stand, and
	# not the snapshot — the mute is a path of its own and travelling inside the
	# rows is what made the service throw the whole frame away.
	fake_app.confirm("grid/rows", {"kick": [], "snare": []},
	                 client=asked.get("client"), seq=asked.get("seq"))

	for step in (0, 4):
		playwright_api.expect(
			panel.locator(conftest.cell(f"grid/kick/{step}"))).not_to_have_class(
				re.compile(r"\bon\b"), timeout=5_000)

	# And for a panel that was not here when it happened.
	panel.goto(service_url)
	panel.wait_for_selector(".cell", timeout=10_000)
	_settled(panel)

	for step in (0, 4):
		assert "on" not in (
			panel.locator(conftest.cell(f"grid/kick/{step}")).get_attribute("class") or ""), \
			f"the service kept step {step} lit for a panel arriving after the clear"


# --- Each contribution in its own window (#2109) -----------------------------
#
# A stack drawn as one tall block could not be arranged: two generators sat on
# top of one another and neither could be moved. Simon asked for a window each,
# named and placed like any other, and for a line saying which pattern each one
# builds.


def _two_generators (panel: typing.Any, fake_app: typing.Any) -> None:
	"""Put a second layer in the stack and wait for both windows to draw."""

	held = {"pulses": 3, "velocity": [40, 80], "duration": 1, "probability": 1}

	# Two different voices, because two generators writing the same row is the
	# case that hides a line arriving at the wrong one.
	fake_app.confirm("stack/layers", [
		{"id": "one", "generator": "euclidean", "index": 1, "bypassed": False,
		 "params": {**held, "pitch": "kick"}},
		{"id": "two", "generator": "euclidean", "index": 2, "bypassed": False,
		 "params": {**held, "pitch": "snare"}},
	], by="app")

	panel.wait_for_function(
		"() => document.querySelectorAll('.recipe .layer').length === 2", timeout=5_000)
	_settled(panel)


def _one_euclidean (panel: typing.Any, fake_app: typing.Any,
                    params: dict[str, typing.Any]) -> typing.Any:
	"""One generator holding exactly what a test wants it to, drawn and settled."""

	fake_app.confirm("stack/layers", [
		{"id": "one", "generator": "euclidean", "index": 1, "bypassed": False,
		 "params": {"pitch": "kick", "pulses": 3, **params}},
	], by="app")

	panel.wait_for_function(
		"() => document.querySelectorAll('.recipe .layer').length === 1", timeout=5_000)
	_settled(panel)

	return panel.locator('.part[data-part="stack/one"]')


def test_a_parameter_holding_nothing_says_auto_rather_than_drawing_a_zero (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""#2381, and the half of it that no ticket had noticed.

	The stepper drew ``value ?? 0``, so an unset ``root`` and a ``root`` somebody
	had set to zero were the same three pixels on the glass — while one of them
	plays and the other kills the layer.  Three shapes draw a number here and all
	three had it: an unbounded number is a stepper, a bounded one is a dial, and
	a range is a dial with two handles.
	"""

	part = _one_euclidean(panel, fake_app, {})

	for field in ("duration", "probability", "velocity"):
		setting = part.locator(f'.setting[data-field="{field}"]')

		assert setting.locator(".auto").count() == 1, f"{field} should say it holds nothing"
		assert "auto" in setting.inner_text().lower()


def test_a_parameter_that_opened_unset_can_be_put_back_from_the_glass (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""The gesture that was missing, and the whole of why #2381 was unrecoverable.

	``count`` and ``root`` on an arpeggio are refused beside a pitch list at
	*every* number including zero, and the panel drew steppers that could reach
	zero and could not reach absent.  So a layer was one press from silence with
	no way back from the glass at all — Simon met exactly that on 2026-09-10 and
	it took the panel's own socket to undo it.

	What crosses is ``null``, which is a value the contract had no meaning for
	until 1.25.0.
	"""

	part = _one_euclidean(panel, fake_app, {"duration": 4})
	setting = part.locator('.setting[data-field="duration"]')

	assert setting.locator("button.auto").count() == 1, "there is a way back"

	setting.locator("button.auto").click()

	asked = fake_app.await_set("stack/one/duration")

	assert asked["v"] is None, f"the panel sent {asked['v']!r} rather than null"


def test_the_way_back_is_absent_rather_than_dead_when_there_is_nothing_to_undo (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""A control that looks pressable and does nothing reads as broken (#2107).

	And a parameter that must hold something never grows one at all: `pulses` is
	required and `pitch` has no unset to go back to, so offering either an "auto"
	would be offering a state the generator cannot be put into.
	"""

	part = _one_euclidean(panel, fake_app, {})

	assert part.locator('.setting[data-field="duration"] button.auto').count() == 0, \
		"nothing to go back from, so no target"

	part = _one_euclidean(panel, fake_app, {"duration": 4})

	# **Asserted in both directions on purpose.** A test that only counts zero
	# targets passes against a build that draws none at all, which is every build
	# before this one — so it would have been a guard that could never go red.
	assert part.locator('.setting[data-field="duration"] button.auto').count() == 1, \
		"and one appears the moment there is"

	assert part.locator('.setting[data-field="pulses"] button.auto').count() == 0
	assert part.locator('.setting[data-field="pitch"] button.auto').count() == 0


def _one_layer (panel: typing.Any, fake_app: typing.Any, generator: str,
                params: dict[str, typing.Any]) -> typing.Any:
	"""One layer of any generator, holding exactly what a test wants it to."""

	fake_app.confirm("stack/layers", [
		{"id": "one", "generator": generator, "index": 1, "bypassed": False,
		 "params": params},
	], by="app")

	panel.wait_for_function(
		"() => document.querySelectorAll('.recipe .layer').length === 1", timeout=5_000)
	_settled(panel)

	return panel.locator('.part[data-part="stack/one"]')


def _fields_on (part: typing.Any) -> list[str]:
	"""Which parameters a block is actually drawing, in order."""

	return [one.get_attribute("data-field") for one in part.locator(".setting").all()]


def test_a_dial_belonging_to_the_other_form_is_not_offered (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""#2381, using what #2410 added upstream.

	`root`, `count` and `inversion` apply to an arpeggio's **chord** form alone,
	and beside a pitch list every one of them kills the layer — zero included.
	The panel drew all three as ordinary numbers because that is what they are
	declared as, so a layer was one press from silence and the dial was a
	reasonable thing for a musician to reach for.
	"""

	part = _one_layer(panel, fake_app, "arpeggio", {"notes": ["kick"]})
	drawn = _fields_on(part)

	assert "notes" in drawn and "spacing" in drawn, "the shared parameters stay"

	for field in ("root", "count", "inversion"):
		assert field not in drawn, f"{field} belongs to the chord form"


def test_a_generator_with_only_a_chord_form_still_offers_all_of_it (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""`broken_chord` accepts a chord and nothing else, so nothing it owns is
	ever out of place — there is no other form to be in.

	It also names **two** rather than three, because it has no `count` at all.
	A panel reading `only` as a fixed triple rather than per entry would be
	wrong here, which is upstream's own warning on #2410.
	"""

	part = _one_layer(panel, fake_app, "broken_chord",
	                  {"chord_obj": ["kick"], "root": 48})
	drawn = _fields_on(part)

	assert "root" in drawn and "inversion" in drawn


def test_a_layer_already_holding_one_is_shown_it_with_the_way_back (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Hiding it would strand a layer that is already dead, which is the exact
	state Simon's composition was in.

	The value goes on being sent whether or not a dial is drawn for it, so a
	panel that simply hid the parameter would show a healthy-looking block that
	makes no sound and offers nothing to do about it — worse than before, because
	at least the dial was visible.  So the one way these appear beside a pitch
	list is that somebody set one, and then it appears with the gesture that
	takes it off.
	"""

	part = _one_layer(panel, fake_app, "arpeggio",
	                  {"notes": ["kick"], "count": 3})

	assert "count" in _fields_on(part), "a layer this is killing must say so"

	setting = part.locator('.setting[data-field="count"]')

	assert setting.locator("button.auto").count() == 1

	setting.locator("button.auto").click()

	assert fake_app.await_set("stack/one/count")["v"] is None


def test_a_shared_parameter_is_never_hidden_by_the_other_forms_list (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""`spacing` applies to both forms and is declared alongside the three that do
	not, which is the whole reason the catalogue had to say which is which rather
	than the panel guessing from the shape.

	**It is left at its opening value deliberately.** Written with a `spacing`
	somebody had set, this passed against a filter that hid every parameter of a
	generator with a chord form — because a value that has been chosen is drawn
	whatever else is true, so the other rule rescued it and the membership check
	went untested. Measured by breaking it exactly that way.
	"""

	part = _one_layer(panel, fake_app, "arpeggio", {"notes": ["kick"]})

	assert "spacing" in _fields_on(part)


def test_a_layer_that_will_not_run_says_so_on_its_own_block (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""#2368, and until now it was said once in a log nobody reads.

	Ten of the forty-six generators this panel offers can be added and will never
	play. **Nothing is refused when you add one** — the value is accepted, the
	app stores it, and the refusal happens a cycle later inside the build, so
	there is no `nack` to show. #2230 cost a session to exactly that silence, and
	it was the composition's log that ended it in one command.
	"""

	part = _one_layer(panel, fake_app, "euclidean", {"pitch": "kick", "pulses": 3})

	assert part.locator(".stalled").count() == 0, "nothing is wrong yet"

	fake_app.stalled("stack", {"one": "markov() missing 'transitions'"})
	panel.wait_for_function(
		"() => document.querySelectorAll('.stalled').length === 1", timeout=5_000)

	said = part.locator(".stalled").inner_text()

	assert "not playing" in said.lower(), "the fact, in this panel's own voice"
	assert "transitions" in said, "and the app's own words for why"


def test_a_layer_that_starts_working_stops_saying_it (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Nothing keeps an event (#1965), so without a clearing frame a block would
	go on saying it is not playing after somebody fixed it — and there would be
	nothing to correct it with."""

	part = _one_layer(panel, fake_app, "euclidean", {"pitch": "kick", "pulses": 3})

	fake_app.stalled("stack", {"one": "no"})
	panel.wait_for_function(
		"() => document.querySelectorAll('.stalled').length === 1", timeout=5_000)

	fake_app.stalled("stack", {})
	panel.wait_for_function(
		"() => document.querySelectorAll('.stalled').length === 0", timeout=5_000)


def test_a_report_lands_on_the_layer_it_names_and_not_its_neighbour (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Two layers of one generator are two blocks that can disagree — one
	arpeggio patched at a pitch list and one at a chord.

	This is why the report is keyed by layer where the log is keyed by generator:
	a block is what a person looks at, and marking both would send somebody to
	the wrong dial.
	"""

	_two_generators(panel, fake_app)

	fake_app.stalled("stack", {"two": "no"})
	panel.wait_for_function(
		"() => document.querySelectorAll('.stalled').length === 1", timeout=5_000)

	assert panel.locator('.part[data-part="stack/one"] .stalled').count() == 0
	assert panel.locator('.part[data-part="stack/two"] .stalled').count() == 1


def test_the_bar_says_when_two_copies_of_one_app_are_connected (
	panel: typing.Any, fake_app: typing.Any, service_url: str) -> None:
	"""#2133 on the glass, which is the only place the remedy can reach.

	The displaced copy goes on running and goes on playing MIDI — the service is
	not in the audio path and cannot stop it — so what ends a duplicate is a
	person noticing and killing the stray. On 2026-09-10 two compositions ran for
	seventeen minutes, the service logged the replacement four times, correctly,
	and nobody read the log.

	**It clears itself**, so there is nothing to dismiss: killing the extra copy
	is what makes it false, and a gesture for acknowledging it would be a second
	way to make the panel disagree with the world.
	"""

	assert panel.locator(".bar .doubled").count() == 0, "one app is not a duplicate"

	second = conftest.FakeApp(service_url.replace("http://", "ws://") + "/ws/app")

	try:
		panel.wait_for_function(
			"() => document.querySelectorAll('.bar .doubled').length === 1", timeout=5_000)

		said = panel.locator(".bar .doubled").inner_text()

		assert "2" in said and "subsequence" in said

	finally:
		second.stop()

	panel.wait_for_function(
		"() => document.querySelectorAll('.bar .doubled').length === 0", timeout=5_000)


def _joins_settled (panel: typing.Any) -> None:
	"""Wait until the overlay has stopped re-measuring.

	The same trap as the cell size, one layer along: the lines are measured from
	the page in an effect and again whenever a block resizes, so a reading taken
	the instant the blocks stop moving is of the frame before they did.  It made
	two of these tests flaky rather than wrong — a different one failed on each
	run and a run in between passed clean, which is the tell.
	"""

	panel.wait_for_function(
		"""() => {
			const now = [...document.querySelectorAll(".join .cable")]
				.map((one) => one.getAttribute("d")).join("|");
			const settled = now.length > 0 && window.__joins === now;

			window.__joins = now;

			return settled;
		}""",
		timeout=5_000, polling=100)


def _edges (panel: typing.Any, join: str) -> dict[str, typing.Any]:
	"""Where one line starts and ends, and where the two blocks it joins are.

	All four in the space the blocks are placed in — the wrapper's own scrolled
	content — because that is the space the overlay draws in.
	"""

	_joins_settled(panel)

	return panel.evaluate(
		r"""(join) => {
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

			/* The first and last points of the path, whichever kind of line it
			   is: a patch cable is a cubic with eight numbers in it and a wired
			   line is taut with four, and both start where they start and end
			   where they end. */
			const numbers = document.querySelector(`[data-join="${join}"] .cable`)
				.getAttribute("d").match(/-?[\d.]+/g).map(Number);

			return {
				from: at(from), to: at(to),
				a: { x: numbers[0], y: numbers[1] },
				b: { x: numbers[numbers.length - 2], y: numbers[numbers.length - 1] },
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

	_unlocked(panel)

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

	# **One sheet, because a line is two elements now** (#2415): the cable's path
	# is drawn behind every block and its fittings in front, from one
	# measurement, so counting both sheets counts every line twice.
	drawn = panel.eval_on_selector_all(
		".joins.under .join", "els => els.map((one) => one.dataset.join)")

	assert sorted(drawn) == ["stack/one>grid", "stack/two>grid"]


def test_a_cable_runs_behind_the_blocks_and_its_fittings_stand_in_front (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""#2415, reported by Simon: a window raised by a drag still had cables over it.

	It was simpler than the z-index he suspected — the overlay sat above *every*
	block all the time, and a block's own depth is its position in the stacking
	order, a single digit, so no raise could ever climb over it.

	**A lead runs behind a panel**, which is both what he asked for and what
	makes a busy page readable. But the whole overlay cannot sink: **every plug,
	collar, socket and hole sits over the block it attaches to** — measured, all
	eight on the rig's Notes page — so sinking them takes away the fitting a
	finger grabs and the only mark saying where a cable lands. Re-patching and
	unplugging both go through those.

	So it is #2107's own line drawn once more: what can be touched is in front,
	what is only drawn is behind.
	"""

	_open_the_stack(panel)
	_two_generators(panel, fake_app)
	_joins_settled(panel)

	depths = panel.evaluate("""() => {
		const depth = (el) => Number(getComputedStyle(el).zIndex) || 0;

		return {
			blocks: [...document.querySelectorAll('.part')].map(depth),
			under: depth(document.querySelector('.joins.under')),
			over: depth(document.querySelector('.joins.over')),
		};
	}""")

	assert depths["under"] < min(depths["blocks"]), "a cable was drawn over a block"
	assert depths["over"] > max(depths["blocks"]), "a fitting was drawn under a block"


def test_a_line_comes_forward_while_a_hand_is_on_the_block_it_joins (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""#2417, Simon's amendment to #2415.

	Cables run behind the blocks so a busy page stays readable — and the cost is
	that the ones you are moving vanish behind whatever they cross, which is
	exactly when you want to see them. So a line joined to the block under the
	hand is drawn on the front sheet for as long as the hand is there.

	**Nothing is remembered and nothing is restored.** `touched` is set on the
	block's own pointerdown and cleared at the document on pointerup, so the line
	goes back by itself — there is no state that could be left raised by a drag
	that ended somewhere unexpected, which is the failure a save-and-restore
	would have.

	**The pointer is moved between the press and the release** (#2424), because
	this said it covered a drag and did not: it pressed and released on one
	point, so the gesture the paragraph above is about never happened.  It still
	does not distinguish clearing at the document from clearing on the block —
	the header takes pointer capture, so the release bubbles through the section
	either way — and that is now said rather than implied.
	"""

	_open_the_stack(panel)
	_two_generators(panel, fake_app)
	_joins_settled(panel)

	def sheet_of (join: str) -> list[str]:
		return panel.eval_on_selector_all(
			f'[data-join="{join}"]',
			"els => els.filter((one) => one.querySelector('path.cable'))"
			"        .map((one) => one.closest('svg').classList.contains('under')"
			"                     ? 'under' : 'over')")

	assert sheet_of("stack/one>grid") == ["under"], "a line was forward with nothing held"

	grip = panel.locator('.part[data-part="stack/one"] .part-title').bounding_box()

	panel.mouse.move(grip["x"] + 20, grip["y"] + 5)
	panel.mouse.down()
	panel.mouse.move(grip["x"] + 60, grip["y"] + 45)

	assert sheet_of("stack/one>grid") == ["over"], "the line stayed behind the blocks"
	assert sheet_of("stack/two>grid") == ["under"], \
		"a line to a block nobody is holding came forward too"

	panel.mouse.up()

	assert sheet_of("stack/one>grid") == ["under"], "the line did not go back"


def test_a_held_cable_brings_its_path_forward_and_keeps_its_fittings (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""#2424 — the half #2417's own test cannot see.

	That test uses `_two_generators`, which replaces the stack and takes the only
	*patched* line with it.  A wired line has no fittings at all, so its claim
	that a line rides forward "path and fittings together" was asserted by
	nothing: invert the fittings' condition and a live cable loses the plug and
	socket a finger is reaching for, mid-gesture, with the suite still green.

	A route is patched, so it has both — and the fittings are already on the
	front sheet, which is exactly why nothing about them should move.
	"""

	_open_the_stack(panel)
	_route(panel, fake_app)
	_joins_settled(panel)

	def drawn () -> dict[str, int]:
		return panel.evaluate("""() => {
			const at = (sheet, what) => document.querySelectorAll(
				`.joins.${sheet} [data-join="second>grid"] ${what}`).length;

			return {
				under: at("under", "path.cable"),
				over: at("over", "path.cable"),
				fittings: at("over", "circle.collar, circle.socket"),
			};
		}""")

	rest = drawn()

	assert rest["under"] == 1 and rest["over"] == 0, f"a cable was forward at rest: {rest}"
	assert rest["fittings"] > 0, "a patched cable drew no fittings, so this proves nothing"

	grip = panel.locator('.part[data-part="grid"] .part-title').bounding_box()

	panel.mouse.move(grip["x"] + 20, grip["y"] + 5)
	panel.mouse.down()

	held = drawn()

	panel.mouse.up()

	assert held["over"] == 1 and held["under"] == 0, f"the path did not come forward: {held}"
	assert held["fittings"] == rest["fittings"], (
		f"the fittings changed while the cable was held: {held} against {rest}")

	assert drawn() == rest, "the line did not go back"


def test_a_fitting_is_the_topmost_thing_at_its_own_centre (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""The half of #2415 that would break silently.

	Sinking the cable is the visible change; taking its fittings down with it is
	the one nobody would notice until they tried to pull a lead out, because a
	*new* patch starts at the block's own outlet button and would go on working.
	Asked of the page rather than of the stylesheet, so a rule added anywhere
	that covered them would fail here.
	"""

	# **The fixture's own stack, not `_two_generators`.** That helper replaces the
	# stack with two euclideans and takes the patched layer away with it — a
	# wired route has no fittings at all, so this would find nothing and pass by
	# asserting about an empty list. It has caught three tests out before.
	_open_the_stack(panel)
	_joins_settled(panel)

	reachable = panel.evaluate("""() => {
		const out = [];

		for (const c of document.querySelectorAll('.joins.over circle')) {
			const box = c.getBoundingClientRect();
			const top = document.elementFromPoint(
				box.left + box.width / 2, box.top + box.height / 2);

			out.push(top ? top.tagName.toLowerCase() : "nothing");
		}

		return out;
	}""")

	assert reachable, "no fittings were drawn at all"
	assert set(reachable) == {"circle"}, f"a block covered a fitting: {reachable}"


def test_a_line_runs_between_the_two_nearest_sides (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Corners are deliberately not offered: a line from one reads as pointing
	past a block rather than at it."""

	_open_the_stack(panel)
	_two_generators(panel, fake_app)

	line = _edges(panel, "stack/one>grid")

	assert _on_the_edge(line["a"], line["from"]), f"the tail is not on the generator: {line}"
	assert _on_the_edge(line["b"], line["to"]), f"the head is not on the pattern: {line}"


def test_a_cable_carries_a_direction_by_its_two_fittings (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Only one direction exists today.  The other one is already named — an
	element that *shows* a property of a pattern rather than controlling it —
	and saying which way a route runs costs nothing now against a format change
	later (#2109).

	It used to be an arrowhead at the middle of the line, put there because
	several contributions feeding one pattern all arrive at the same block and
	heads gathered on an edge merge into a smudge.  **A plug and a socket cannot
	merge**, because they are at opposite ends of their own cable — so the
	direction went back to the ends, where a person patching anything expects to
	read it: the source is plugged in, the destination is the socket.
	"""

	_open_the_stack(panel)
	_two_generators(panel, fake_app)

	# A route, because this is about a *patch cable's* fittings: a generator is
	# hard-wired and ends in lugs rather than a plug and a socket, which is the
	# whole point of drawing the two kinds differently.
	_route(panel, fake_app)

	line = _edges(panel, "second>grid")
	ends = panel.evaluate("""(join) => {
		const at = (selector) => {
			const one = document.querySelector(`[data-join="${join}"] ${selector}`);

			return { x: +one.getAttribute("cx"), y: +one.getAttribute("cy") };
		};

		return { plug: at(".plug"), socket: at(".hole") };
	}""", "second>grid")

	def away (point: dict[str, float], other: dict[str, float]) -> float:
		return ((point["x"] - other["x"]) ** 2 + (point["y"] - other["y"]) ** 2) ** 0.5

	assert away(ends["plug"], line["a"]) < 1.5, f"the plug is not at the source: {ends} on {line}"
	assert away(ends["socket"], line["b"]) < 1.5, (
		f"the socket is not at the pattern: {ends} on {line}")


def test_a_line_brightens_while_a_hand_is_on_either_end (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Faint the rest of the time, because it crosses the grids rather than
	sitting beside them.  A hand on a block is the moment the question is being
	asked."""

	_open_the_stack(panel)
	_two_generators(panel, fake_app)
	_joins_settled(panel)

	# **Measured off the cable rather than counted off a sheet** (#2424).  This
	# asked `.joins.under [data-join=X].live` for a count of 1, and since #2417 a
	# held line's path is on the *front* sheet while the `<g>` wrapper stays on
	# both — so it was counting an element with no children at all, and would
	# have reported 1 against a build that drew the cable nowhere.  Width is what
	# `.join.live .cable` actually changes, so that is what is asked.
	def width () -> float:
		return panel.evaluate("""() => {
			const on = document.querySelectorAll('[data-join="stack/one>grid"] path.cable');

			if (on.length !== 1) throw new Error(`${on.length} cables, not one`);

			return parseFloat(getComputedStyle(on[0]).strokeWidth);
		}""")

	rest = width()

	grip = panel.locator('.part[data-part="grid"] .part-title').bounding_box()

	panel.mouse.move(grip["x"] + 20, grip["y"] + 5)
	panel.mouse.down()

	held = width()

	panel.mouse.up()

	assert held > rest, (
		f"the pattern was held and its line stayed faint: {held} against {rest}")
	assert width() == rest, "the line stayed bright after the hand left"


def test_a_contribution_appears_wherever_the_pattern_it_builds_does (
	panel: typing.Any) -> None:
	"""**This asserted the opposite until 2026-09-07**, and the reversal is
	Simon's (#2211).

	#2085 had it that a page carrying the pattern alone was the uncluttered grid
	and a page carrying both was the one given over to building it, so a stack
	appeared only where a page named it.  What that missed is that the *button*
	is not on the stack: `stackFor` searches every control, so "+ add generator"
	is offered on every page carrying the pattern — and the generators it made
	were drawn only where the stack was named.

	Simon added several from a page that showed none of them, heard them playing
	with nothing on the glass to explain it, and found them on another page.
	**A page that draws the button and not the result is the incoherence**, and
	the tidiness it bought is not worth it: if there is one Minitaur, its
	generators are its generators on every page that carries it.
	"""

	_settled(panel)

	# The opening page names the pattern and not the stack, and gets both.
	assert panel.locator('.part[data-part="grid"]').count() == 1
	assert panel.locator(".recipe").count() > 0, (
		"the stack did not follow the pattern it builds")

	# And the button that made them is on the pattern, where it always was.
	assert panel.locator('.part[data-part="grid"] .part-foot button.add').count() == 1


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

	_unlocked(panel)

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


def _swatches (panel: typing.Any) -> dict[str, tuple[str, str]]:
	"""Every swatch in the open picker, as its own painted bands and the lit
	colour the theme it offers actually resolves to.

	The second half is measured with a throwaway element carrying the same
	`data-theme`, because a custom property reads back as the text that was
	written — `light-dark(#b87400, #f0b429)` for the two that ride on a pair —
	and what is wanted is the colour the browser settled on.  Asking for it
	through `color` makes the browser do the resolving.
	"""

	found = panel.eval_on_selector_all(
		".theme .choices i",
		"""els => els.map((one) => {
			const probe = document.createElement("span");
			probe.dataset.theme = one.dataset.theme;
			probe.style.color = "var(--on)";
			document.body.appendChild(probe);
			const lit = getComputedStyle(probe).color;
			probe.remove();

			return [one.dataset.theme,
				[getComputedStyle(one).backgroundImage, lit]];
		})""")

	return {name: (bands, lit) for name, (bands, lit) in found}


def test_a_theme_swatch_is_the_theme_it_offers (panel: typing.Any) -> None:
	"""Rather than a copy of it.  Each swatch carries that theme's own
	`data-theme`, so the stylesheet's block for it applies to the swatch and
	every band in it is painted by that theme — which is what stops the picker
	becoming a second place the palette is written down and a second place it
	goes wrong.

	It is the swatch somebody picks a theme *by*, so a picker drifting from the
	palette is wrong in the one direction nobody would check.

	**One theme is exempt from the lit-colour half, and named here so the
	exemption cannot spread.**  Prism's lit colour is the beam going *into* the
	prism — an achromatic grey — and everything that theme is about happens after
	the glass, so a swatch of its chassis, its lit colour and its in-flight
	colour would be three true values and a false picture.  Its swatch samples
	its own fan instead.

	The rule it must still obey is the one that matters: **it is painted by the
	theme rather than hand-copied**, so it cannot drift.  What guards that is
	`test_themes.py::test_the_prism_swatch_is_the_fan_it_stands_for`, which
	reads the swatch's three hues out of the stylesheet and checks them against
	the spread the grid is drawn with.  The distinctness check below still
	applies to it, as does everything else here.
	"""

	_pick_theme(panel, "Dark", "dark")
	panel.locator(".theme > button").click()

	shown = _swatches(panel)

	assert len(shown) >= 3, f"the picker offers almost nothing: {sorted(shown)}"

	for name, (bands, lit) in sorted(shown.items()):
		if name == "prism":
			continue

		assert lit in bands, (
			f"the {name} swatch does not paint that theme's own lit colour:"
			f" {lit} is not in {bands}")

	assert "prism" in shown, (
		"the one theme exempted above is not in the picker, so the exemption is"
		" guarding nothing and should go")

	# Every theme but "match system" is a palette of its own, so no two of them
	# may draw the same swatch: two identical squares in a picker is a choice
	# that cannot be made.
	distinct = {name: bands for name, (bands, _) in shown.items() if name != "system"}
	assert len(set(distinct.values())) == len(distinct), (
		f"two themes draw the same swatch: {sorted(distinct)}")

	# And "match system" shows the machine's answer rather than the pin. It
	# inherits `color-scheme` like everything else, so while dark is pinned it
	# would otherwise offer a picture of what the person already has.
	panel.emulate_media(color_scheme="light")
	following = _swatches(panel)

	assert following["system"] == following["light"], (
		f"the system swatch followed the pin rather than the machine: {following['system']}")


def test_the_theme_picker_fits_what_it_offers (panel: typing.Any) -> None:
	"""Eleven themes do not go in one column without hanging half a metre of
	popover off the bar, so they go down a column of six and then across — and
	the first attempt at that drew the second column *on top of* the first.

	Every other test passed against it. The palettes were right, the swatches
	were right, the client and the stylesheet agreed about all eleven; the only
	thing wrong was that four of the names were unreadable, which nothing in the
	suite was looking at. Found in a screenshot, which is not a method.

	**It is the name overflowing the button, not the button overlapping its
	neighbour**, and the difference matters because the obvious test does not
	catch it. The rows sat side by side exactly as asked; each was 44px wide,
	which is the chrome finger's own minimum, and each label was 66 to 93px of
	text drawn straight through the one beside it. A test comparing button
	rectangles passes against the broken build — measured, not assumed.

	So this asks whether each row is wide enough for what is written in it, and
	whether the box is on the glass at all.
	"""

	panel.locator(".theme > button").click()
	panel.wait_for_selector(".theme .choices button")

	spilling = panel.eval_on_selector_all(".theme .choices button", """els => els
		.filter((one) => one.scrollWidth > one.clientWidth + 1)
		.map((one) => one.textContent.trim()
			+ " (" + one.scrollWidth + "px of name in " + one.clientWidth + "px)")""")

	assert spilling == [], f"these names are drawn outside their own row: {spilling}"

	# **Height only.** A page here may be wider than the glass on purpose — the
	# cell size is a setting and a big one overflows, which is why every surface
	# that is not a control is a place to take hold of the page. So the bar's
	# right-hand end being off-screen is the design rather than a fault, and
	# horizontal position is a question about scroll. Height is not: a popover
	# taller than the glass cannot be scrolled to, because every button in it
	# carries `touch-action: none` and a finger landing on one is a press. That
	# is the whole reason this list goes down a column of six and then across.
	tall, glass = panel.eval_on_selector(".theme .choices",
		"one => [one.getBoundingClientRect().height, window.innerHeight]")

	assert tall <= glass, (
		f"the picker is {tall}px on {glass}px of glass, and it cannot be scrolled")

	# Horizontal placement is #2197's and is asserted for every popover at once,
	# below, because it was never about the theme picker: that is only where it
	# was noticed.


def test_a_named_theme_repaints_the_whole_panel (panel: typing.Any) -> None:
	"""The eight written out flat are the ones `light-dark()` could not express,
	and nothing else in the suite proves one of those blocks reaches the root at
	all — the swatch test would pass just as well if they only ever applied to a
	24px square in a popover.

	Phosphor because it is the furthest from either default: a lit screen in an
	unlit room, where even the grounds are pulled toward green.
	"""

	panel.emulate_media(color_scheme="dark")
	before = _ground(panel)

	_pick_theme(panel, "Phosphor", "phosphor")

	assert _ground(panel) != before, "a named theme changed nothing on the page"

	lit = panel.evaluate(
		"""() => {
			const probe = document.createElement("span");
			probe.style.color = "var(--on)";
			document.body.appendChild(probe);
			const found = getComputedStyle(probe).color;
			probe.remove();

			return found;
		}""")

	assert lit == "rgb(59, 224, 124)", f"the panel is not lit in Phosphor's own green: {lit}"


def test_a_theme_outlives_a_reload (panel: typing.Any, service_url: str) -> None:
	"""A setting a person has to make again every time the panel restarts is not
	a setting.  Kept on the panel, like the cell size, because a theme is a
	property of the glass and the room it is in (#2055)."""

	_pick_theme(panel, "Light", "light")
	chosen = _ground(panel)

	panel.goto(service_url)
	panel.wait_for_selector(".cell", timeout=10_000)

	assert _ground(panel) == chosen
	assert "light" in panel.locator(".theme > button").inner_text().lower()


def _at_size (panel: typing.Any, label: str, cell: str) -> None:
	"""Set the cell size from the chooser and wait for the page to settle."""

	panel.locator(".sizes > button").click()
	panel.locator(".sizes .choices button", has_text=label).click()
	panel.wait_for_function(
		"(want) => getComputedStyle(document.documentElement).getPropertyValue('--cell') === want",
		arg=cell, timeout=5_000)
	_settled(panel)


def _fitting (panel: typing.Any, join: str) -> float:
	"""How large the fitting at the end of one line is.

	A patch cable ends in a round socket and a hard-wired line in a square lug,
	so this asks for whichever the line has — the mark rule applies to both, and
	the arrowhead this replaced was the mark whose scaling Simon found broken by
	zooming.
	"""

	_joins_settled(panel)

	return float(panel.eval_on_selector(
		f'[data-join="{join}"] .socket',
		"""one => +(one.getAttribute("r") || one.getAttribute("width"))"""))


def test_a_mark_on_the_lattice_grows_with_the_cell (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Simon found this by zooming: the arrowhead stayed the size it was while
	everything around it grew.

	It was written as a constant on the argument that nobody touches a mark,
	which is true and is an argument for a *floor* rather than for a constant.
	Every other mark on the lattice already scaled between a floor and a
	ceiling — the type scale, a cell's corner, the ring under an unconfirmed
	tap — and this one did not.
	"""

	# **The fixture's own patched layer, kept**: only a patch cable carries a
	# fitting now, and `_two_generators` replaces the stack with two euclideans —
	# which are wired, and a fixed route ends in nothing (Simon, 2026-09-10).
	_open_the_stack(panel)

	_at_size(panel, "Compact", "22px")
	small = _fitting(panel, "notes>stack/two")
	hair = panel.evaluate(
		"() => parseFloat(getComputedStyle(document.querySelector('.join .cable')).strokeWidth)")

	_at_size(panel, "Large", "60px")
	large = _fitting(panel, "notes>stack/two")
	thicker = panel.evaluate(
		"() => parseFloat(getComputedStyle(document.querySelector('.join .cable')).strokeWidth)")

	assert large > small, f"the fitting did not grow with the cell: {small} then {large}"
	assert thicker > hair, f"the cable did not thicken with the cell: {hair} then {thicker}"


def test_a_mark_stops_growing_rather_than_running_away (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""The other half of the same rule, and the half a bare proportion loses.

	A ceiling is what keeps a mark a mark: an arrowhead that went on scaling
	would end up larger than the parameter rows it points between.
	"""

	_open_the_stack(panel)

	_at_size(panel, "Large", "60px")
	large = _fitting(panel, "notes>stack/two")

	row = panel.evaluate(
		"() => parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--row'))")

	assert large <= row, f"the fitting is larger than a control row: {large} against {row}"


def test_a_line_shows_where_it_joins_at_both_ends (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""A line that stops at an edge and a line that passes behind a block are
	the same picture without something at the end saying which — which is what
	Simon read on the glass.  Both ends, because either could be the one read
	wrongly.
	"""

	_open_the_stack(panel)

	line = _edges(panel, "notes>stack/two")

	# A plug and a socket, because a patch cable stands off the block it feeds:
	# a line that stops short of an edge and a line that passes behind a block
	# are the same picture without something at the end saying which.
	#
	# **A fixed route answers the same question differently** (Simon,
	# 2026-09-10): it has no fitting at all, and instead of standing off it stays
	# *attached* — a line that touches has already said where it stops. Asserted
	# by the test below rather than here, because they are two answers and not
	# one rule with an exception.
	dots = panel.eval_on_selector_all(
		'[data-join="notes>stack/two"] circle.plug, [data-join="notes>stack/two"] circle.hole',
		"""els => els.map((one) => {
			const box = one.getBBox();

			return { x: box.x + box.width / 2, y: box.y + box.height / 2, r: box.width / 2 };
		})""")

	assert len(dots) == 2, f"a join drew {len(dots)} fittings"

	for dot in dots:
		assert dot["r"] > 0

	# Within a pixel rather than rounded to one. A lug's centre comes from its
	# bounding box and the line's end from its path, and the two agreed to six
	# decimal places while landing either side of x.5 — which rounding then
	# turned into a failure about nothing.
	def near (point: dict[str, float], end: dict[str, float]) -> bool:
		return abs(point["x"] - end["x"]) <= 1 and abs(point["y"] - end["y"]) <= 1

	for end in (line["a"], line["b"]):
		assert any(near(dot, end) for dot in dots), (
			f"nothing marks where the line ends: {dots} against {line}")

	# And each sits on the edge of the block it belongs to, not adrift of it.
	assert _on_the_edge(dots[0], line["from"]) or _on_the_edge(dots[0], line["to"])


def test_a_block_does_not_butt_its_content_against_its_frame (panel: typing.Any) -> None:
	"""Content on the frame reads as spilling out of it.  Simon: "let's have a
	little padding before the edge"."""

	_settled(panel)

	room = panel.evaluate("""() => {
		const block = document.querySelector('.part[data-part="grid"]');
		const inside = block.querySelector(".grid");
		const outer = block.getBoundingClientRect();
		const held = inside.getBoundingClientRect();

		return { left: held.left - outer.left, right: outer.right - held.right,
		         bottom: outer.bottom - held.bottom };
	}""")

	for side, gap in room.items():
		assert gap >= 4, f"the grid is {gap}px from the block's {side} edge"


def test_a_block_still_leaves_a_lane_beside_its_neighbour (panel: typing.Any) -> None:
	"""The frame has to be counted in a starting arrangement or the lane is the
	lane minus the frame — which is how a padding added for looks would quietly
	eat a rule that was measured and settled."""

	_settled(panel)

	seen = panel.evaluate("""() => {
		const blocks = [...document.querySelectorAll(".part")].map((one) => one.getBoundingClientRect());
		let closest = null;

		for (const one of blocks) {
			for (const other of blocks) {
				if (one === other) continue;

				const across = Math.max(other.left - one.right, one.left - other.right);

				if (across > 0 && (closest === null || across < closest)) closest = across;
			}
		}

		return {
			closest,
			cell: parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--cell")),
		};
	}""")

	assert seen["closest"] is not None, "only one block on the page to compare"
	assert seen["closest"] >= seen["cell"] - 1, \
		f"blocks sit {seen['closest']}px apart, less than one {seen['cell']}px cell"


def test_a_block_says_what_the_app_told_it_to_say_about_itself (panel: typing.Any) -> None:
	"""A MIDI channel and an instrument's name are facts about a studio, and
	this package is not allowed to hold one (#1465).  So a panel that worked
	them out would be a panel that knew what a rig looked like; a panel that is
	told them is repeating what the composition said, which is the same rule as
	the title and the row names."""

	_settled(panel)

	said = panel.eval_on_selector_all(
		'.part[data-part="grid"] .part-title .about span',
		"els => els.map((one) => one.textContent.trim())")

	assert said == ["ch10", "Vermona DRM1"], f"the block said {said}"

	# And a block the app said nothing about says nothing.
	assert panel.locator('.part[data-part="second"] .part-title .about').count() == 0


def test_a_line_arrives_level_with_the_row_the_generator_writes (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Simon asked for it, and the reason is why the lines exist at all: a
	generator that writes the snare should arrive at the snare, not at the
	middle of a pattern that has ten rows in it.

	Worked out without knowing the name of a single parameter.  A generator
	that writes one voice has a choice whose options are the pattern's own rows,
	because the composition is what joined those two together (#2085) — so the
	question is about the shape of what is offered, not about Subsequence's
	vocabulary.
	"""

	_open_the_stack(panel)
	_two_generators(panel, fake_app)

	for layer, voice in (("one", "kick"), ("two", "snare")):
		line = _edges(panel, f"stack/{layer}>grid")
		row = panel.eval_on_selector(
			f'.part[data-part="grid"] [data-row="{voice}"]',
			"""(one, wrap) => {
				const outer = wrap.getBoundingClientRect();
				const at = one.getBoundingClientRect();

				return at.top - outer.top + wrap.scrollTop + at.height / 2;
			}""", panel.query_selector(".grid-wrap"))

		assert abs(line["b"]["y"] - row) < 1.5, (
			f"the line for {voice} arrives at {line['b']['y']}, not at the row's {row}")

		# And it comes in from a side, which is what being level with a row costs.
		assert (abs(line["b"]["x"] - line["to"]["x"]) < 1.5
		        or abs(line["b"]["x"] - line["to"]["x"] - line["to"]["w"]) < 1.5), (
			f"the line arrived at the top or bottom edge: {line}")


def test_a_generator_that_names_no_row_points_at_the_pattern_itself (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""A generic generator feeds the whole pattern rather than a part of it, and
	pointing at one of its rows would be a claim that is not true."""

	_open_the_stack(panel)

	held = {"pulses": 3, "velocity": [40, 80], "duration": 1, "probability": 1}

	fake_app.confirm("stack/layers", [
		{"id": "one", "generator": "euclidean", "index": 1, "bypassed": False, "params": held},
	], by="app")
	_settled(panel)

	line = _edges(panel, "stack/one>grid")
	sides = [
		{"x": line["to"]["x"] + line["to"]["w"] / 2, "y": line["to"]["y"]},
		{"x": line["to"]["x"] + line["to"]["w"], "y": line["to"]["y"] + line["to"]["h"] / 2},
		{"x": line["to"]["x"] + line["to"]["w"] / 2, "y": line["to"]["y"] + line["to"]["h"]},
		{"x": line["to"]["x"], "y": line["to"]["y"] + line["to"]["h"] / 2},
	]

	assert any(abs(line["b"]["x"] - one["x"]) < 1.5 and abs(line["b"]["y"] - one["y"]) < 1.5
	           for one in sides), (
		f"a generator naming no row did not arrive at a side's middle: {line}")


def test_words_can_be_copied_where_there_is_a_mouse (panel: typing.Any) -> None:
	"""Simon went to paste what the panel was showing, so that we could compare
	it against what I thought it was showing, and could not.

	Selection is off everywhere by default and that is right for glass: a long
	press on a pattern must not raise a selection callout over the music.  It is
	wrong for a desk, and the two had never been separated.
	"""

	_settled(panel)

	# Dragged across with the mouse, rather than read off a computed value: an
	# element that only inherits the page default reports `auto` either way, so
	# the property says less than the gesture does.
	label = panel.locator('.part[data-part="grid"] .row-label').first.bounding_box()

	panel.mouse.move(label["x"] + 2, label["y"] + label["height"] / 2)
	panel.mouse.down()
	panel.mouse.move(label["x"] + label["width"] - 2, label["y"] + label["height"] / 2, steps=6)
	panel.mouse.up()

	assert "kick" in panel.evaluate("() => window.getSelection().toString()"), \
		"a row label could not be selected with a mouse"

	# And a right-click offers the menu that copies it.
	assert not panel.evaluate("""() => {
		const menu = new MouseEvent("contextmenu", { bubbles: true, cancelable: true });

		document.querySelector(".row-label").dispatchEvent(menu);

		return menu.defaultPrevented;
	}"""), "a right-click was refused its menu"

	# A cell is not text, and selecting one would mean nothing, so it does not
	# opt back in and the page default stands.
	assert panel.eval_on_selector(
		conftest.cell("grid/kick/0"), "one => getComputedStyle(one).userSelect") != "text"
	assert panel.eval_on_selector(
		"body", "one => getComputedStyle(one).userSelect") == "none"


def test_a_finger_still_selects_nothing_and_gets_no_menu (
	browser: typing.Any, service_url: str, fake_app: typing.Any) -> None:
	"""The other half of the same division, and the reason the default exists.

	A long press must not raise a selection callout or a context menu over the
	music.  Nothing about that changed; it just has nothing to do with a mouse.
	"""

	context = browser.new_context(has_touch=True, viewport={"width": 1280, "height": 720})
	page = context.new_page()

	try:
		page.goto(service_url)
		page.wait_for_selector(".cell", timeout=10_000)

		assert page.evaluate("() => matchMedia('(pointer: coarse)').matches"), \
			"this context is not standing in for a touch panel"

		# Nothing opts back in, so the page default of `none` stands over all of
		# it. A computed `auto` is what an element that only inherits reports.
		assert page.eval_on_selector(
			'.part[data-part="grid"] .part-title',
			"one => getComputedStyle(one).userSelect") != "text"
		assert page.eval_on_selector(
			"body", "one => getComputedStyle(one).userSelect") == "none"

		assert page.evaluate("""() => {
			const menu = new MouseEvent("contextmenu", { bubbles: true, cancelable: true });

			document.querySelector(".part-title").dispatchEvent(menu);

			return menu.defaultPrevented;
		}"""), "a long press was offered a context menu"

	finally:
		context.close()


def test_a_contributions_number_is_still_there_after_a_reload (
	panel: typing.Any, fake_app: typing.Any, service_url: str) -> None:
	"""Where it was not, and nothing said so.

	A panel that is connected when a stack changes reads the number off the
	``changed`` frame, which carries what the app said.  A panel that arrives
	afterwards reads the service's copy — and the service rebuilds a layer from
	a list of fields it names, which did not name this one.  So the number
	appeared, and came back missing, and both halves looked right from where
	they were being tested.
	"""

	_open_the_stack(panel)
	_two_generators(panel, fake_app)

	assert "2" in panel.locator('.part[data-part="stack/two"] .part-title').inner_text()

	panel.goto(service_url)
	panel.wait_for_selector(".recipe", timeout=10_000)
	_settled(panel)

	assert "2" in panel.locator('.part[data-part="stack/two"] .part-title').inner_text(), \
		"the number was lost on the way through the service"


# --- A grid routed into a pattern (#2108) ------------------------------------
#
# Simon: "I might create a 'generic' melodic grid, and route it to both
# instruments. The individual instrument grids might be empty, but inherit from
# the generic pattern." One mechanism, not two: a generator contributes notes to
# a pattern and a grid contributes notes to a pattern.


def _route (panel: typing.Any, fake_app: typing.Any) -> None:
	"""Route the second grid into the pattern the stack builds."""

	fake_app.confirm("stack/layers", [
		{"id": "one", "kind": "route", "source": "second", "index": 1,
		 "bypassed": False, "params": {}},
	], by="app")

	panel.wait_for_selector('[data-join="second>grid"]', timeout=5_000)
	_settled(panel)


def test_a_cable_dragged_from_an_outlet_makes_the_route (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Simon: "with the new patch cable design — I wonder whether we might
	simply drag a cable out from a designated output terminal to the input
	terminal of the target?"

	The destination is the whole block rather than a fitting on it: on glass a
	big target beats a precise one, and a person dragging a lead is looking at
	where it is going.  So the drop lands anywhere on the pattern.
	"""

	_open_the_stack(panel)
	_settled(panel)

	outlet = panel.locator('.part[data-part="second"] .outlet')

	assert outlet.count() == 1, "a grid that can feed a pattern has no outlet"

	outlet.scroll_into_view_if_needed()
	take = outlet.bounding_box()
	drop = panel.locator('.part[data-part="grid"] .part-title').bounding_box()

	panel.mouse.move(take["x"] + take["width"] / 2, take["y"] + take["height"] / 2)
	panel.mouse.down()
	panel.mouse.move(drop["x"] + drop["width"] / 2, drop["y"] + drop["height"] / 2, steps=12)

	# While a lead is in the air, everything that could take it says so.
	assert panel.locator(".grid-wrap.patching").count() == 1, "the page does not say a cable is out"
	assert panel.locator(".join.loose .cable").count() == 1, "no cable is drawn in the air"

	panel.mouse.up()

	asked = fake_app.await_set("stack/layers")
	routes = [layer for layer in asked["v"] if layer.get("kind") == "route"]

	assert len(routes) == 1, f"the drag asked for {asked['v']}"
	assert routes[0]["source"] == "second"


def test_a_note_set_has_an_outlet_to_take_a_cable_from (panel: typing.Any) -> None:
	"""Without it there is no way to start a patch at all, which is how #2374
	shipped: the routing existed and had no gesture.

	**Two separate faults put it here and only one of them is asserted.**  The
	outlet was wired to `sends`, which a note set does not set — that is what
	this covers.  The other is that `Footer` returns nothing when it can find no
	*button*, so a block whose only footer content was a fitting got no footer at
	all; that one is fixed and is **not** what makes this pass, because the set
	also gained a mute (#2107: a switch lives with the thing it switches, and
	silencing the set silences every cable out of it).  A block that is only ever
	a source would still need the guard, and there is not one here to prove it.
	"""

	_open_the_stack(panel)
	_settled(panel)

	assert panel.locator('.part[data-part="notes"] .outlet').count() == 1, \
		"a set of notes has nothing to take a cable from"


def test_the_two_kinds_of_connection_are_drawn_as_two_things (
	panel: typing.Any) -> None:
	"""Simon, 2026-09-10: *"anything which is tied is indicated by a solid routing
	line, anything flexible and independent by a patch cable."*

	A generator is created from a pattern, belongs to it and dies with it, so it
	is wired and terminated in lugs.  A note set exists on its own and feeds as
	many inputs as it likes, so it is patched, and its ends are a plug and a
	socket.  Both are on this page at once, which is the only arrangement in
	which the difference is a difference rather than a description (#2119).
	"""

	_open_the_stack(panel)
	_settled(panel)

	# **A line is two elements now** (#2415): its path is drawn behind every
	# block and its fittings in front, so each of these looks at the sheet its
	# own subject is on.
	wired = panel.locator(".joins.under .join.wired")
	patched = panel.locator(".joins.over .join.patched")

	assert wired.count() >= 1, "no generator is drawn as wired to what it builds"
	assert patched.count() >= 1, "the note set is not drawn as patched into anything"

	# **Told apart by their fittings, and by nothing else** (Simon, 2026-09-10).
	#
	# It used to be shape: a cable sagged and a wired line was taut.  That cost
	# more than it bought — the sag's own job is that two crossing cables read as
	# two rather than as an X (#2119), which is worth as much to a fixed route as
	# to a patched one.  So both hang, and what a hand can take hold of is what
	# says which is which.
	assert patched.first.locator("circle.plug").count() == 1, "a cable has no plug"
	assert patched.first.locator("circle.socket").count() == 1, "a cable has no socket"
	# **Asked of the front sheet, where a fitting would be if there were one.**
	# `wired` above is the back sheet, which carries paths and nothing else — so
	# asking it would pass against any build and assert nothing at all.
	assert panel.locator(".joins.over .join.wired").locator("circle, rect").count() == 0, \
		"a fixed route drew a fitting, and there is nothing to unplug"

	# Both hang.  **Colour cannot carry this on its own** and that is measured:
	# `--on` and `--ink-quiet` sit 1.09 apart in Phaedra, so a rule resting on
	# luminance would be no rule at all in one of the eleven themes.
	for kind, one in (("patched", patched), ("wired", wired)):
		assert "C" in (panel.locator(f".joins.under .join.{kind}").first
		               .locator("path.cable").get_attribute("d") or ""), \
			f"a {kind} line is drawn straight rather than hanging"


def test_a_note_cable_ends_level_with_the_input_it_feeds (panel: typing.Any) -> None:
	"""**The first destination on this surface finer than a block** (#2374).

	Every other cable lands on a stack and becomes a layer; this one lands on one
	*parameter* of one layer, which is what makes several patchable inputs on a
	generator expressible at all.  So it has to arrive beside the row it feeds
	rather than at the middle of a block with ten of them — the rule #2109 drew
	for a generator's own line, asked of a settings row.
	"""

	_open_the_stack(panel)
	_settled(panel)

	panel.locator('.part[data-part="stack/two"]').scroll_into_view_if_needed()
	_settled(panel)

	level = panel.evaluate("""() => {
		const socket = document.querySelector('.joins.over .join.patched circle.socket');
		const row = document.querySelector(
			'.part[data-part="stack/two"] [data-row="pitches"]');

		if (!socket || !row) return null;

		const at = row.getBoundingClientRect();

		return {
			cable: socket.getBoundingClientRect().top + socket.getBoundingClientRect().height / 2,
			row: at.top + at.height / 2,
		};
	}""")

	assert level, "no cable, or no row for it to land beside"
	assert abs(level["cable"] - level["row"]) < 6, \
		f"the cable lands {abs(level['cable'] - level['row']):.0f}px from its row"


def test_a_patched_parameter_says_what_feeds_it_and_offers_no_pool (
	panel: typing.Any) -> None:
	"""**And it is a statement rather than a control.**

	There was a button here that patched the parameter at the first note set it
	could find, which invented a second gesture for patching and asked for the
	*source* from the *destination* — both against #2119, and Simon's correction
	on 2026-09-10.  What is left names the source; the way to unpatch is to pull
	the cable out, which is where every other patch on this surface is undone.
	"""

	_open_the_stack(panel)
	_settled(panel)

	block = panel.locator('.part[data-part="stack/two"]')
	said = block.locator(".patched-from")

	assert said.count() == 1, "a patched parameter does not say what feeds it"
	assert "notes" in (said.text_content() or ""), "it does not name the set"

	assert block.locator('[data-field="pitches"] .picker').count() == 0, \
		"a patched parameter still offers a pool to choose from"


def test_a_note_set_is_dragged_into_the_generator_that_reads_it (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""The gesture is the one every other patch on this panel already has: take a
	cable out of the thing that produces and drop it on the thing that reads.

	The block is the target rather than a fitting on it, as it is for a grid — on
	glass a big one beats a precise one — and which *input* it lands on is the
	address the block carries.
	"""

	_open_the_stack(panel)
	_settled(panel)

	outlet = panel.locator('.part[data-part="notes"] .outlet')
	outlet.scroll_into_view_if_needed()
	take = outlet.bounding_box()
	drop = panel.locator('.part[data-part="stack/two"] .part-title').bounding_box()

	panel.mouse.move(take["x"] + take["width"] / 2, take["y"] + take["height"] / 2)
	panel.mouse.down()
	panel.mouse.move(drop["x"] + drop["width"] / 2, drop["y"] + drop["height"] / 2, steps=12)

	# What can read a set of notes says so while the lead is in the air, and what
	# can only take a grid does not: two kinds of cable, two sets of destination.
	assert panel.locator(".grid-wrap.patching.pitching").count() == 1, \
		"the page does not say a note cable is out"

	panel.mouse.up()

	asked = fake_app.await_set("stack/two/pitches")

	assert asked["v"] == {"from": "control", "id": "notes"}, \
		f"the drag asked for {asked['v']}"


def test_a_note_cable_lands_on_the_input_under_the_finger (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""#2425.  A generator with **two** pools is the only thing that can tell a
	block apart from a row, and Subsequence's catalogue has none — 13 of its 46
	entries offer a pool and every one of them offers exactly one — so the
	fixture carries `duet` for this.

	The drop resolved to `takesPitch[0]` while the comment beside it said it
	resolved to the row under the finger.  With one pool those are the same
	answer, which is why nothing noticed.
	"""

	_open_the_stack(panel)

	fake_app.confirm("stack/layers", [
		{"id": "duo", "generator": "duet", "index": 1, "bypassed": False, "params": {}},
	], by="app")

	panel.wait_for_selector('.part[data-part="stack/duo"]', timeout=5_000)
	_settled(panel)

	# The **second** input. Landing on the first is what this exists to catch,
	# and is what the code did.
	row = panel.locator('.part[data-part="stack/duo"] .setting[data-field="answer"]')
	row.scroll_into_view_if_needed()

	outlet = panel.locator('.part[data-part="notes"] .outlet')
	outlet.scroll_into_view_if_needed()

	take = outlet.bounding_box()
	drop = row.bounding_box()

	panel.mouse.move(take["x"] + take["width"] / 2, take["y"] + take["height"] / 2)
	panel.mouse.down()
	panel.mouse.move(drop["x"] + drop["width"] / 2, drop["y"] + drop["height"] / 2, steps=12)
	panel.mouse.up()

	asked = fake_app.await_set("stack/duo/answer")

	assert asked["v"] == {"from": "control", "id": "notes"}, \
		f"the drag asked for {asked['v']}"

	assert not [one for one in fake_app.sets if one["path"] == "stack/duo/lead"], \
		"the cable landed on the first pool rather than the row under the finger"


def test_a_second_finger_lifting_does_not_drop_a_line_the_first_is_holding (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""#2425.  `touched` is one slot and the release is heard at the *document*,
	so without a pointer check every release on the page cleared it.

	The panel is built for ten concurrent contacts (#1997).  One finger dragging
	a block had its lines dropped behind every other block the moment a second
	finger tapped anything at all and lifted — for the rest of the drag, with no
	way back but letting go and starting again.

	A synthetic release is dispatched rather than a second real pointer, because
	Playwright drives one mouse.  It is dispatched at the document, which is
	where the listener is, and carries an id no real pointer here has.
	"""

	_open_the_stack(panel)
	_two_generators(panel, fake_app)
	_joins_settled(panel)

	def forward () -> int:
		return panel.evaluate(
			"""() => document.querySelectorAll(
				'.joins.over [data-join="stack/one>grid"] path.cable').length""")

	grip = panel.locator('.part[data-part="grid"] .part-title').bounding_box()

	panel.mouse.move(grip["x"] + 20, grip["y"] + 5)
	panel.mouse.down()

	assert forward() == 1, "the line did not come forward at all"

	# A different finger, somewhere else, letting go.
	panel.evaluate("""() => document.dispatchEvent(
		new PointerEvent('pointerup', { pointerId: 4242, bubbles: true }))""")

	held = forward()

	panel.mouse.up()

	assert held == 1, "another finger's release dropped the line being held"
	assert forward() == 0, "the line stayed forward after the hand that held it left"


def test_a_note_cable_pulled_out_and_let_go_empties_the_pool (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""A lead pulled out of a rack and let go is unpatched, and an empty pool is
	what this parameter held before anybody patched it.

	Unpatching is the absence of a landing rather than an operation of its own,
	which is the same shape the grid cable already had — and is why there is no
	button anywhere that undoes a patch.
	"""

	_open_the_stack(panel)
	_settled(panel)

	socket = panel.locator(".joins.over .join.patched circle.socket").first
	socket.scroll_into_view_if_needed()
	at = socket.bounding_box()

	# Somewhere on the page that is over no block at all, and inside the window:
	# Playwright clamps a move to the viewport, so a drag aimed past the edge
	# lands wherever the clamp puts it rather than where it was sent.
	empty = panel.evaluate("""() => {
		for (let y = window.innerHeight - 40; y > 120; y -= 20)
			for (let x = window.innerWidth - 40; x > 120; x -= 20) {
				const one = document.elementFromPoint(x, y);

				if (one && !one.closest('[data-part]') && !one.closest('.bar')) return {x, y};
			}

		return null;
	}""")

	assert empty, "every point on this page is over a block"

	panel.mouse.move(at["x"] + at["width"] / 2, at["y"] + at["height"] / 2)
	panel.mouse.down()
	panel.mouse.move(empty["x"], empty["y"], steps=12)
	panel.mouse.up()

	assert fake_app.await_set("stack/two/pitches")["v"] == [], \
		"pulling the cable out left the parameter patched"


def test_a_cable_dropped_on_nothing_comes_away_in_the_hand (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""A lead let go over the page asks for nothing, and neither does one
	dropped on a block that cannot hold it — a refusal a moment later would be
	the app answering a question the panel should not have put."""

	_open_the_stack(panel)
	_settled(panel)

	outlet = panel.locator('.part[data-part="second"] .outlet')
	outlet.scroll_into_view_if_needed()
	take = outlet.bounding_box()

	panel.mouse.move(take["x"] + take["width"] / 2, take["y"] + take["height"] / 2)
	panel.mouse.down()
	panel.mouse.move(take["x"] + take["width"] / 2, take["y"] + 300, steps=10)
	panel.mouse.up()

	panel.wait_for_timeout(400)

	assert not [frame for frame in fake_app.sets if frame.get("path") == "stack/layers"], \
		"a cable dropped on nothing still made a route"
	assert panel.locator(".grid-wrap.patching").count() == 0, "the page still thinks a cable is out"


def test_a_pattern_adds_a_generator_and_nothing_else (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""A grid used to be on this list, on the argument that a pattern to take
	from and a generator to add are the same kind of thing.  Simon settled that
	they are not: **a generator is hard-wired and a grid is patched.**

	A generator is created here and belongs to this pattern — it cannot be
	moved, because it was never plugged in.  A grid exists on its own, carries
	the same notes wherever it goes, and is patched in from its own outlet or
	its own "send to…".  Offering it here as well was the second of two ways to
	make one connection, which is the shape this whole pass has been removing.
	"""

	_open_the_stack(panel)

	panel.locator('.part[data-part="grid"] .part-foot .offer.add').click()
	panel.wait_for_selector(".sheet", timeout=5_000)

	assert panel.locator(".sheet .offer", has_text="second").count() == 0, \
		"a grid is still offered where generators are added"

	offered = panel.eval_on_selector_all(
		".sheet .offer b", "els => els.map((one) => one.textContent.trim())")

	# **The list divides in two now, and that is not the division this test was
	# written against** (#2246).  A grid was taken off it because it was a second
	# way to make one connection — a generator is created here and belongs to
	# this pattern, a grid exists on its own and is patched.  A transform is
	# neither: it is a layer of this same stack, created here, belonging here,
	# and differing from a generator in what it *does* rather than in how it is
	# reached.  So it belongs on the list, under a heading, because a stack whose
	# order is its meaning cannot afford two kinds of layer that look alike
	# (#2119).
	declared = ([one["name"] for one in conftest.CONTROLS["stack"]["generators"]]
	            + [one["name"] for one in conftest.CONTROLS["stack"]["transforms"]])

	assert offered == declared, f"the sheet offers {offered} against {declared}"

	# Closed the way a panel with no keyboard closes it.
	panel.locator(".sheet-body header button").click()
	panel.wait_for_selector(".sheet", state="detached", timeout=5_000)

	# And the two ways left to route a grid are both *on the grid*, which is
	# where a route belongs: its own outlet, and its own list for a pattern that
	# is on another page.
	assert panel.locator('.part[data-part="second"] .outlet').count() == 1
	assert panel.locator('.part[data-part="second"] .part-foot .offer.send').count() == 1


def test_a_route_is_a_line_and_nothing_else (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""It had a window carrying its bypass, its place in the stack and a picker
	for where it came from.

	Simon: "surely a *route* is a line with an arrow head?"  He is right — a
	connection is not a thing that sits somewhere, it is the fact that two things
	are joined, and the window was answering a question nobody asked.
	"""

	_open_the_stack(panel)
	_route(panel, fake_app)

	drawn = panel.eval_on_selector_all(
		".joins.under .join", "els => els.map((one) => one.dataset.join)")

	assert drawn == ["second>grid"], f"a route drew {drawn}"

	# No block of its own, anywhere.
	assert panel.locator('.part[data-part^="stack/"]').count() == 0


def test_the_head_of_an_arrow_silences_the_link (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""The most direct mapping there is: a link is a line, so you disable it by
	touching the line."""

	_open_the_stack(panel)
	_route(panel, fake_app)

	panel.locator('[data-join="second>grid"] circle.node').click()

	asked = [one for one in fake_app.sets if one["path"] == "stack/layers"]

	assert asked, "tapping the head asked for nothing"
	assert asked[-1]["v"][0]["bypassed"] is True

	fake_app.confirm("stack/layers", asked[-1]["v"], by="panel")
	panel.wait_for_selector('[data-join="second>grid"].off', timeout=5_000)

	panel.locator('[data-join="second>grid"] circle.node').click()

	asked = [one for one in fake_app.sets if one["path"] == "stack/layers"]

	assert asked[-1]["v"][0]["bypassed"] is False, "the head would not turn it back on"


def test_a_silenced_link_is_dashed_and_hollow (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Said twice over, because it is the one thing about a line worth reading
	at a glance.

	Dashes were where these lines started and Simon could not see them, which is
	why they are solid now.  They come back here earning their place: a dash no
	longer means "this is quiet", it means *this is not sounding*, and a line
	that is hard to read is right for a link that is doing nothing.
	"""

	_open_the_stack(panel)

	fake_app.confirm("stack/layers", [
		{"id": "one", "kind": "route", "source": "second", "index": 1,
		 "bypassed": True, "params": {}},
	], by="app")
	panel.wait_for_selector('[data-join="second>grid"].off', timeout=5_000)
	_settled(panel)

	drawn = panel.evaluate("""() => {
		const at = (selector) => getComputedStyle(
			document.querySelector('[data-join="second>grid"] ' + selector));

		return {
			dashes: at(".cable").strokeDasharray,
			live: at(".cable").stroke,
			node: { fill: at(".node").fill, stroke: at(".node").stroke },
		};
	}""")

	assert drawn["dashes"] not in ("none", ""), f"a silenced link is not dashed: {drawn}"

	# And it loses the accent, which is the sentence every toggle here says when
	# it is off — a dead lead is not the colour of a live one.
	accent = panel.evaluate(
		"""() => {
			const swatch = document.createElement("span");
			swatch.style.color = getComputedStyle(document.documentElement)
				.getPropertyValue("--ring").trim();
			document.body.appendChild(swatch);
			const seen = getComputedStyle(swatch).color;
			swatch.remove();
			return seen;
		}""")

	assert drawn["live"] != accent, f"a silenced cable is drawn like a live one: {drawn}"

	# And its switch keeps its surface and its edge, because it is still a
	# target: off is the surface alone, never the absence of one.
	assert drawn["node"]["fill"] != "none", f"a silenced switch lost its surface: {drawn}"
	assert drawn["node"]["stroke"] != "none", f"a silenced switch lost its edge: {drawn}"


def test_only_a_control_on_the_overlay_takes_a_tap (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""The overlay sits above the blocks, so anything live on it takes a pointer
	from the grid underneath — and the grid is the most tapped surface there is.

	**Three things are live and every one of them is a control**: a route's
	switch, and a patch cable's two fittings, which are taken hold of to unplug
	it or re-route it.  The cables themselves are inert, and so are a hard-wired
	line's lugs — a generator cannot be moved, which is exactly why its lugs stay
	the size of a mark while a patch cable's fittings are a row across.
	"""

	_open_the_stack(panel)

	# One stack holding both kinds, because that is what this compares — and a
	# `_route` after `_two_generators` would replace the list rather than add to
	# it, leaving no wired line to check.
	fake_app.confirm("stack/layers", [
		{"id": "made", "generator": "euclidean", "index": 1, "bypassed": False,
		 "params": {"pitch": "kick"}},
		{"id": "sent", "kind": "route", "source": "second", "index": 2,
		 "bypassed": False, "params": {}},
	], by="app")

	panel.wait_for_selector('[data-join="second>grid"]', timeout=5_000)
	_joins_settled(panel)

	inert = panel.evaluate("""() => {
		const parts = (selector) => [...document.querySelectorAll(selector)]
			.map((one) => getComputedStyle(one).pointerEvents);

		return {
			overlay: getComputedStyle(document.querySelector(".joins")).pointerEvents,
			cables: parts(".joins.under .join .cable"),
			lugs: parts(".join .lug"),
			fittings: parts(".joins.over .join.patched .collar, .joins.over .join.patched .socket"),
			inners: parts(".joins.over .join .plug, .joins.over .join .hole"),
			switches: parts(".joins.over .join.switchable .node"),
		};
	}""")

	assert inert["overlay"] == "none"
	assert set(inert["cables"]) == {"none"}, f"a cable takes taps: {inert}"
	# **There are no lugs any more, and that is the assertion** (Simon,
	# 2026-09-10): a fixed route ends in nothing, because a fitting on something
	# that cannot be unplugged is an affordance that is not there.
	assert inert["lugs"] == [], f"a fixed route drew a fitting: {inert}"
	assert set(inert["inners"]) == {"none"}, f"a fitting's mark takes taps: {inert}"

	assert set(inert["switches"]) == {"all"}, f"a switch takes no taps: {inert}"

	# **And a patch cable's fittings are targets only where there is room for
	# them.** Three row-sized things need a cable long enough to hold them; two
	# blocks side by side make a lead about forty pixels long, and the switch
	# and both fittings landed on the same spot. #2107 decides it — a thing that
	# cannot be given a row must not be touchable — so what is asserted is that
	# the two agree, whichever way round they are on this page.
	room = panel.evaluate("""() => {
		const row = parseFloat(
			getComputedStyle(document.documentElement).getPropertyValue("--row"));

		return [...document.querySelectorAll(".joins.over .join.patched")].map((one) => {
			const fitting = one.querySelector(".socket");
			const box = fitting.getBoundingClientRect();

			return {
				holdable: one.classList.contains("holdable"),
				live: getComputedStyle(fitting).pointerEvents === "all",
				across: box.width,
				row,
			};
		});
	}""")

	assert room, "no patch cable to measure"

	for one in room:
		assert one["holdable"] == one["live"], (
			f"a fitting says one thing and behaves as another: {one}")

		if one["holdable"]:
			assert one["across"] >= one["row"] - 0.5, (
				f"a fitting that can be held is {one['across']}px "
				f"against a {one['row']}px row")
		else:
			assert one["across"] < one["row"], (
				f"a fitting that cannot be held is drawn as a target: {one}")


def _apart (panel: typing.Any, part: str, dx: float, dy: float) -> None:
	"""Move a block, so a cable between two of them is long enough to hold its
	fittings.

	Three row-sized targets need room: two blocks side by side make a lead about
	forty pixels long, and a switch and two fittings will not fit on one.  That
	is #2107 deciding it — a thing that cannot be given a row must not be
	touchable — so the fittings are only targets once there is somewhere to put
	them.
	"""

	_unlocked(panel)

	title = panel.locator(f'.part[data-part="{part}"] .part-title').bounding_box()

	panel.mouse.move(title["x"] + 20, title["y"] + 5)
	panel.mouse.down()
	panel.mouse.move(title["x"] + 20 + dx, title["y"] + 5 + dy, steps=10)
	panel.mouse.up()

	panel.locator(".bar .latch").click()
	panel.wait_for_selector(".grid-wrap.unlocked", state="detached", timeout=5_000)
	_joins_settled(panel)


def _pull_onto (panel: typing.Any, selector: str, target: str) -> None:
	"""Take hold of a cable's fitting and drop it on something."""

	panel.locator(selector).scroll_into_view_if_needed()

	box = panel.locator(selector).bounding_box()
	onto = panel.locator(target).bounding_box()

	panel.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
	panel.mouse.down()
	panel.mouse.move(onto["x"] + onto["width"] / 2, onto["y"] + onto["height"] / 2, steps=12)
	panel.mouse.up()


def _pull (panel: typing.Any, selector: str, dx: float, dy: float) -> None:
	"""Take hold of a cable's fitting and drag it somewhere."""

	panel.locator(selector).scroll_into_view_if_needed()

	box = panel.locator(selector).bounding_box()
	x = box["x"] + box["width"] / 2
	y = box["y"] + box["height"] / 2

	panel.mouse.move(x, y)
	panel.mouse.down()
	panel.mouse.move(x + dx, y + dy, steps=12)
	panel.mouse.up()


def test_a_cable_pulled_out_and_let_go_is_unpatched (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Simon: "I must be able to select an individual patch point to disconnect
	or move it."

	Letting go over nothing leaves it unpatched, because that is what happens
	when you pull a lead out of a rack and do not put it anywhere.
	"""

	_open_the_stack(panel)
	_route(panel, fake_app)
	_apart(panel, "grid", dx=0, dy=420)

	# Onto the header, which is not a block and never takes a cable. Dropped
	# far below instead, the move is clamped to the viewport and can land back
	# on something — the trap that has cost a diagnosis twice already.
	_pull_onto(panel, '[data-join="second>grid"] .socket', ".bar")

	asked = fake_app.await_set("stack/layers")

	assert [layer for layer in asked["v"] if layer.get("kind") == "route"] == [], \
		f"the route survived being unplugged: {asked['v']}"


def test_a_cable_taken_by_its_source_end_can_also_be_unpatched (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Either end comes away, which is Simon's "I might want to re-patch (move)
	the *source* end as well as the target end" — and the same gesture with
	nowhere to land is a disconnection."""

	_open_the_stack(panel)
	_route(panel, fake_app)
	_apart(panel, "grid", dx=0, dy=420)

	_pull_onto(panel, '[data-join="second>grid"] .collar', ".bar")

	asked = fake_app.await_set("stack/layers")

	assert [layer for layer in asked["v"] if layer.get("kind") == "route"] == [], \
		f"the route survived being unplugged: {asked['v']}"


def test_a_cable_put_back_where_it_was_is_still_one_cable (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""The property that makes a move a move rather than a copy.

	Taking a lead out and plugging it into the same socket must leave one route,
	not two — so the removal happens before anything is added, and a re-route to
	where it already was cannot double it silently.
	"""

	_open_the_stack(panel)
	_route(panel, fake_app)
	_apart(panel, "grid", dx=0, dy=420)

	box = panel.locator('.part[data-part="grid"] .part-title').bounding_box()
	fitting = panel.locator('[data-join="second>grid"] .socket').bounding_box()

	panel.mouse.move(fitting["x"] + fitting["width"] / 2, fitting["y"] + fitting["height"] / 2)
	panel.mouse.down()
	panel.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=12)
	panel.mouse.up()

	fake_app.await_set("stack/layers")
	panel.wait_for_timeout(400)

	asked = [one for one in fake_app.sets if one["path"] == "stack/layers"]
	routes = [layer for layer in asked[-1]["v"] if layer.get("kind") == "route"]

	assert len(routes) == 1, f"putting a cable back left {len(routes)} routes: {asked[-1]['v']}"
	assert routes[0]["source"] == "second"


def _two_routes (panel: typing.Any, fake_app: typing.Any) -> None:
	"""Route the second grid into the pattern twice, so two cables meet one edge."""

	fake_app.confirm("stack/layers", [
		{"id": "one", "kind": "route", "source": "second", "index": 1,
		 "bypassed": False, "params": {}},
		{"id": "two", "kind": "route", "source": "second", "index": 2,
		 "bypassed": False, "params": {}},
	], by="app")

	panel.wait_for_function(
		"""() => document.querySelectorAll(".join.patched .collar").length === 2""",
		timeout=5_000)
	_joins_settled(panel)


def _terminals (panel: typing.Any, selector: str) -> list[dict[str, float]]:
	"""Where each of these fittings sits, measured against the overlay itself.

	Not against the viewport.  The overlay is inside the scrolled content and
	moves with it, so a reading taken before a cable is added and one taken
	after are only comparable if both are relative to something that moved the
	same way.
	"""

	return panel.evaluate("""(selector) => {
		const svg = document.querySelector(".joins").getBoundingClientRect();

		return [...document.querySelectorAll(selector)].map((one) => {
			const box = one.getBoundingClientRect();

			return { x: box.x + box.width / 2 - svg.x, y: box.y + box.height / 2 - svg.y };
		});
	}""", selector)


def test_two_cables_on_one_edge_get_a_terminal_each (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""#2134.  Simon: "the first is connected, it is simply in the centre of the
	edge.  When I add a second, there are two adjacent patch points, equidistant
	on the edge."

	Every end used to be the middle of a side, so a grid feeding two patterns
	put both plugs on one point.  That was tolerable while a cable could only be
	looked at; once either end could be dragged it stopped being, because two
	fittings on one spot are one fitting to a finger and whichever the document
	hit first is the one that came away.

	Two things are asserted, and the second is the half that is easy to lose: a
	terminal each, *and* the pair still centred on the edge — so a second cable
	pushes the first aside rather than appearing beside it in some vacant socket
	while the first stays put.
	"""

	_open_the_stack(panel)
	_route(panel, fake_app)
	_apart(panel, "grid", dx=0, dy=420)

	alone = _terminals(panel, ".join.patched .collar")

	assert len(alone) == 1, f"one route, {len(alone)} plugs: {alone}"

	_two_routes(panel, fake_app)

	plugs = _terminals(panel, ".join.patched .collar")
	sockets = _terminals(panel, ".join.patched .socket")

	assert len(plugs) == 2 and len(sockets) == 2, f"{len(plugs)} plugs, {len(sockets)} sockets"

	row = panel.evaluate(
		"""() => parseFloat(
			getComputedStyle(document.documentElement).getPropertyValue("--row"))""")

	for pair, what in ((plugs, "plug"), (sockets, "socket")):
		away = ((pair[0]["x"] - pair[1]["x"]) ** 2 + (pair[0]["y"] - pair[1]["y"]) ** 2) ** 0.5

		assert away >= row - 0.5, (
			f"two {what}s sharing an edge are {away:.1f}px apart, "
			f"against a {row}px row: {pair}")

	middle = {axis: (plugs[0][axis] + plugs[1][axis]) / 2 for axis in ("x", "y")}

	assert abs(middle["x"] - alone[0]["x"]) < 1.5 and abs(middle["y"] - alone[0]["y"]) < 1.5, \
		f"a second cable moved the pair off the centre of the edge: {middle} was {alone[0]}"


def test_a_route_is_unmade_where_it_was_made (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""The head of the arrow silences a route; this is what takes it away.  One
	place to make a connection and unmake it, on the thing a person is holding.
	"""

	_open_the_stack(panel)
	_route(panel, fake_app)

	panel.locator('.part[data-part="second"] .part-foot .offer.send').click()
	panel.wait_for_selector(".sheet", timeout=5_000)

	offered = panel.locator(".sheet .offer").first

	assert "tap to stop" in offered.inner_text().lower(), offered.inner_text()

	offered.click()

	asked = [one for one in fake_app.sets if one["path"] == "stack/layers"]

	assert asked[-1]["v"] == [], "unrouting left the layer in place"


def test_a_stack_offering_no_patterns_still_says_generator (
	panel: typing.Any) -> None:
	"""Every stack before this offered generators alone, and a composition with
	nothing worth sharing still wants exactly that."""

	panel.locator(".pages button", has_text="Bass").click()
	panel.wait_for_selector(".grid.notes", timeout=5_000)
	_settled(panel)

	assert panel.locator(".part-foot .offer.add").count() == 0


# --- What an algorithm put there, drawn beside what a person tapped (#1925) ---


def _realised (panel: typing.Any, fake_app: typing.Any,
               cells: dict[str, dict[str, int]], source: str = "one",
               sources: dict[str, str] | None = None) -> None:
	"""Report a cycle's generated cells the way the app does.

	Through the fixture rather than building the frame here.  Two places knowing
	the wire's shape is two places to update, and this one silently kept sending
	the pre-1.13.0 shape after the other had moved on — so the dots drew at one
	size whatever the velocity, and only a test that measured them said so.
	"""

	fake_app.realised("grid", cells, source=source, sources=sources)

	panel.wait_for_timeout(200)


def test_a_generated_step_is_drawn_as_a_dot_not_as_a_face (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Nothing stores it, and next cycle an unseeded generator may put it
	somewhere else — a face would be claiming the pattern holds something it
	does not (#1965)."""

	_settled(panel)
	_realised(panel, fake_app, {"snare": {"1": 100}})

	ghost = panel.locator(f'{conftest.cell("grid/snare/1")}.ghost')

	assert ghost.count() == 1, "a generated step was not drawn"
	assert panel.locator(f'{conftest.cell("grid/snare/1")}.on').count() == 0, \
		"a generated step was drawn as though the pattern held it"


def test_a_generated_step_is_never_kept_as_state (
	panel: typing.Any, fake_app: typing.Any, service_url: str) -> None:
	"""An event, never a change.  A person's taps stay the only thing anything
	stores, which is the whole of #1965.

	A reload is what asks the question: the panel comes back with the service's
	own copy of everything, so a realised cell that survived one would be a
	realised cell the service had kept — which is the thing it must never do.
	"""

	_settled(panel)
	_realised(panel, fake_app, {"snare": {"1": 100}})

	assert panel.locator(".cell.ghost").count() == 1

	panel.goto(service_url)
	panel.wait_for_selector(".cell", timeout=10_000)
	_settled(panel)

	assert panel.locator(".cell.ghost").count() == 0, \
		"a generated step was kept somewhere and came back"


def test_a_generated_step_is_traced_by_an_ordinary_tap (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""It needs no gesture of its own: the cell is off, so a tap turns it on,
	and that is what tracing into a permanent step means."""

	_settled(panel)
	_realised(panel, fake_app, {"snare": {"1": 100}})

	panel.locator(conftest.cell("grid/snare/1")).click()

	asked = fake_app.await_set("grid/snare/1")

	assert asked["v"] is True, "tracing a generated step did not ask for it"


def test_a_traced_step_still_says_the_algorithm_wants_it (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Worth knowing that the note you kept is one it would have played anyway,
	so the dot stays under the face rather than disappearing."""

	_settled(panel)
	_realised(panel, fake_app, {"kick": {"0": 100}})

	cell = panel.locator(conftest.cell("grid/kick/0"))

	assert "on" in (cell.get_attribute("class") or ""), "the fixture's kick 0 is not lit"
	assert "ghost" in (cell.get_attribute("class") or ""), \
		"a traced step stopped saying the algorithm wants it"


def test_a_window_is_closed_from_its_title_bar (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Top right, where every windowed system has put it for forty years.

	It was among the controls, which put "remove this whole thing" next to
	"nudge it up one" — Simon's point, and it costs nothing to be where a hand
	already goes.
	"""

	_open_the_stack(panel)
	_two_generators(panel, fake_app)

	close = panel.locator('.part[data-part="stack/two"] .part-title .close')

	assert close.count() == 1, "a contribution cannot be closed from its title bar"

	block = panel.locator('.part[data-part="stack/two"]').bounding_box()
	where = close.bounding_box()

	assert where["x"] + where["width"] > block["x"] + block["width"] - 2 * where["width"], \
		"the close is not at the right-hand end of the title bar"

	# A block the composition declared cannot be closed: the panel did not make
	# it and taking it away is not the panel's to offer.
	assert panel.locator('.part[data-part="grid"] .part-title .close').count() == 0


def test_closing_a_window_does_not_drag_it (panel: typing.Any, fake_app: typing.Any) -> None:
	"""The title bar is the handle, so a button in it has to stop the drag it
	would otherwise begin under the same finger."""

	_open_the_stack(panel)
	_two_generators(panel, fake_app)

	_unlocked(panel)

	before = panel.locator('.part[data-part="stack/one"]').bounding_box()

	panel.locator('.part[data-part="stack/two"] .part-title .close').click()

	asked = [one for one in fake_app.sets if one["path"] == "stack/layers"]

	assert [layer["id"] for layer in asked[-1]["v"]] == ["one"], "the close did not remove it"
	assert panel.locator('.part[data-part="stack/one"]').bounding_box() == before, \
		"closing one block moved another"


def test_a_routed_note_is_drawn_apart_from_an_invented_one (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Simon: "I still see a dot on the 15th step of the hihat 1 open lane — and
	there is no generator linked to it at all, enabled or otherwise."

	There was not, and there never had been: the note came from the grid routed
	into that pattern.  The dot was truthful and unreadable — a routed grid's
	notes and an algorithm's wore the same mark, so the only way to find out
	what had put one there was to read the wire.

	A round dot is something made up this cycle and kept nowhere.  A square is a
	note somebody wrote down, which is what it is on the grid it came from and
	what a cell looks like here.
	"""

	_open_the_stack(panel)

	fake_app.confirm("stack/layers", [
		{"id": "made", "generator": "euclidean", "index": 1, "bypassed": False, "params": {}},
		{"id": "sent", "kind": "route", "source": "second", "index": 2,
		 "bypassed": False, "params": {}},
	], by="app")

	_settled(panel)

	# One event, because one report is one cycle: a second would replace the
	# first rather than add to it, which is what makes it a report at all.
	_realised(panel, fake_app,
	          {"kick": {"1": 100}, "snare": {"1": 100}},
	          sources={"kick": "made", "snare": "sent"})

	def corner (path: str) -> float:
		return float(panel.eval_on_selector(
			conftest.cell(path),
			"one => parseFloat(getComputedStyle(one, '::after').borderTopLeftRadius)"))

	invented = corner("grid/kick/1")
	routed = corner("grid/snare/1")

	assert panel.locator('.part[data-part="grid"] .cell.ghost.routed').count() == 1
	assert routed < invented / 2, \
		f"a routed note is drawn like an invented one: {routed}px against {invented}px"


def test_a_quiet_generated_note_is_drawn_smaller_than_a_loud_one (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""A ghost is a quiet note by its whole nature, and drawing it at the weight
	of a full hit says the opposite of what it is."""

	_settled(panel)
	_realised(panel, fake_app, {"kick": {"1": 127}, "snare": {"1": 20}})

	def across (path: str) -> float:
		return float(panel.eval_on_selector(
			conftest.cell(path),
			"one => parseFloat(getComputedStyle(one, '::after').width)"))

	loud = across("grid/kick/1")
	quiet = across("grid/snare/1")

	assert loud > quiet * 1.4, f"a note at 127 is drawn {loud}px and one at 20 is {quiet}px"

	# And the quietest is still something rather than nothing: this says how
	# hard, and a note that cannot be seen has stopped saying anything at all.
	assert quiet >= 4, f"a quiet note is {quiet}px across"


def test_a_grid_can_be_sent_to_a_pattern_from_its_own_footer (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Simon: "how should I connect the output of shared-drums to an
	instrument?"  The honest answer was: from the other end.  That is backwards
	from how anybody thinks about a signal — you have a thing, and you send it.
	"""

	_open_the_stack(panel)

	panel.locator('.part[data-part="second"] .part-foot .offer.send').click()
	panel.wait_for_selector(".sheet", timeout=5_000)

	panel.locator(".sheet .offer").first.click()

	asked = [one for one in fake_app.sets if one["path"] == "stack/layers"]

	assert asked, "sending a grid asked for nothing"

	added = asked[-1]["v"][-1]

	assert added == {**added, "kind": "route", "source": "second"}

	# A grid nothing can take from does not offer to send itself anywhere.
	assert panel.locator('.part[data-part="grid"] .part-foot .offer.send').count() == 0


def test_the_playhead_is_not_drawn_before_it_has_somewhere_to_be (
	panel: typing.Any) -> None:
	"""Simon: "those small marks on the left edge need to go — I've seen them
	before and they are inconsistent and distracting."

	They were one thing, not several: the playhead.  It is positioned by a frame
	loop that does nothing until the first beat gives it an anchor, and until
	then it kept whatever CSS left it — two pixels wide, full height, against
	the block's left edge, which the gaps between rows chopped into a column of
	little marks beside every pattern.

	The fixture's app sends no beats, so this is exactly that state.
	"""

	_settled(panel)

	assert panel.locator(".playhead").count() > 0, "the fixture draws no playhead at all"
	assert panel.locator(".playhead:not([hidden])").count() == 0, \
		"a playhead with no beat to stand on is still on the glass"


def _pressed_end (panel: typing.Any, selector: str) -> str:
	"""Which end of a rocker is pressed: "off", "on", or "neither"."""

	return panel.eval_on_selector(selector, """one => {
		const down = one.querySelector('.end[aria-pressed="true"]');

		return down ? down.textContent.trim() : "neither";
	}""")


def test_a_block_can_be_silenced_from_its_own_footer (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Simon asked for one on every item, and the panel had none: silencing one
	instrument for eight bars was not a thing a person could do at all."""

	_settled(panel)

	switch = panel.locator('.part[data-part="grid"] .part-foot .switch')

	assert switch.count() == 1, "a pattern cannot be silenced"

	# A rocker names both of its states and presses one of them, so the pressed
	# end is the reading. Each end *sets* rather than flips, which is why
	# pressing ON twice is on rather than back where it started.
	assert switch.get_attribute("data-on") == "true"
	assert _pressed_end(panel, '.part[data-part="grid"] .part-foot .switch') == "on"

	switch.click()

	asked = fake_app.await_set("grid/enabled")

	assert asked["v"] is False


def test_a_silenced_block_says_so_from_across_the_room (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""A silent block that looks identical to a live one is a block you will
	spend a minute staring at."""

	_settled(panel)

	fake_app.confirm("grid/enabled", False, by="panel")
	panel.wait_for_selector(".part.silent", timeout=5_000)

	dimmed = float(panel.eval_on_selector(
		'.part[data-part="grid"] .part-body', "one => getComputedStyle(one).opacity"))
	lit = float(panel.eval_on_selector(
		'.part[data-part="second"] .part-body', "one => getComputedStyle(one).opacity"))

	assert dimmed < lit, f"a silenced block is drawn like a live one: {dimmed} against {lit}"
	assert panel.locator(
		'.part[data-part="grid"] .part-foot .switch').get_attribute("data-on") == "false"
	assert _pressed_end(panel, '.part[data-part="grid"] .part-foot .switch') == "off"


def test_silencing_a_block_does_not_empty_it (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""A mute rather than a delete, which is what makes it reversible without
	loss: the notes stay where they are and stop being heard."""

	_settled(panel)

	before = panel.locator('.part[data-part="grid"] .cell.on').count()

	assert before > 0, "the fixture's grid has no notes to keep"

	fake_app.confirm("grid/enabled", False, by="panel")
	panel.wait_for_selector(".part.silent", timeout=5_000)

	assert panel.locator('.part[data-part="grid"] .cell.on').count() == before


def test_every_size_and_face_on_the_page_is_one_the_scale_names (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Simon, asking for a last pass: "weed out any accidental inconsistencies
	in styling ... the font size for the bar/beat/step numbers is larger than
	for the BPM number and I don't see a reason for this."

	There was not one, and he found it by eye.  The scale says six sizes and
	nothing outside them, and the faces say three — but neither was checked, so
	anything that inherited from the document or set a size by hand simply
	joined the set.  A hint below the note grid was drawing at the document's
	own 16px, and a stepper's value, a sheet's headings, the lamp and the build
	line had all quietly fallen back to the body face.

	**What a thing is decides its face**: lettering on the equipment, a
	sentence, or a figure.  What it does decides its size, out of six.
	"""

	_open_the_stack(panel)
	_two_generators(panel, fake_app)

	# A sheet as well, so the chrome that only exists while something is open is
	# measured rather than assumed.
	panel.locator('.part[data-part="grid"] .part-foot button.add').click()
	panel.wait_for_selector(".sheet .option", timeout=5_000)

	adrift = panel.evaluate(r"""() => {
		const root = getComputedStyle(document.documentElement);
		const probe = document.createElement("span");

		document.body.appendChild(probe);

		const resolve = (name) => {
			probe.style.font = "";
			probe.style.fontSize = root.getPropertyValue(name);

			return getComputedStyle(probe).fontSize;
		};

		const sizes = new Set(["--type-display", "--type-chrome", "--type-chrome-quiet",
			"--type-title", "--type-body", "--type-note"].map(resolve));

		/* Normalised, because a stack written across two lines in the
		   stylesheet comes back with its newline and the computed one does
		   not. */
		const tidy = (stack) => stack.replace(/\s+/g, " ").trim();

		const faces = new Set(["--face-panel", "--face-body", "--face-figures"]
			.map((name) => tidy(root.getPropertyValue(name))));

		probe.remove();

		const out = { sizes: [], faces: [] };

		for (const el of document.querySelectorAll("body *")) {
			const box = el.getBoundingClientRect();

			if (!box.width || !box.height) continue;
			if (![...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) continue;

			const seen = getComputedStyle(el);
			const named = el.tagName.toLowerCase() + "."
				+ ((el.className.baseVal ?? el.className ?? "").toString().split(" ")[0] || "-");

			if (!sizes.has(seen.fontSize)) out.sizes.push(named + " at " + seen.fontSize);
			if (!faces.has(tidy(seen.fontFamily))) out.faces.push(named + " in " + seen.fontFamily);
		}

		return { sizes: [...new Set(out.sizes)], faces: [...new Set(out.faces)] };
	}""")

	assert adrift["sizes"] == [], f"these are set outside the type scale: {adrift['sizes']}"
	assert adrift["faces"] == [], f"these are set in a face nobody declared: {adrift['faces']}"


SURFACE_RULES = {
	".part-title button, .part-body button, .part-foot button, .bar button,"
	" .sheet button, .menu .options button, .sizes .choices button,"
	" .theme .choices button",
	".part-title button",
	".part-body button, .part-foot button",
	".bar button, .sheet button, .menu .options button, .sizes .choices button,"
	" .theme .choices button",
	".part-body .menu .options button, .part-foot .menu .options button",
}
"""The only rules allowed to give a control a height or a type.

Named rather than matched by a prefix, so a fourth surface cannot arrive by
accident — adding one is a decision, and this is where it is made.
"""


def _button_sizes (panel: typing.Any) -> dict[str, dict[str, set]]:
	"""Every button on the page, grouped by the surface it sits on."""

	return panel.evaluate("""() => {
		const surface = (one) =>
			one.closest(".sheet, .menu .options, .sizes .choices, .theme .choices") ? "chrome"
			: one.closest(".bar") ? "chrome"
			: one.closest(".part-title") ? "title"
			: one.closest(".part") ? "lattice" : "loose";

		const seen = {};

		for (const one of document.querySelectorAll("button")) {
			const at = surface(one);
			const shape = getComputedStyle(one);

			seen[at] = seen[at] || {
				sizes: [], floors: [], widths: [], faces: [], who: [] };
			seen[at].sizes.push(shape.fontSize);
			seen[at].floors.push(shape.minHeight);

			/* **And the width, which this could not see.** A surface sets both
			   floors; only the height was collected, so `.stepper button`'s own
			   `min-width: 44px` sat unlayered — beating the layer outright —
			   and came out half a row wide beside its neighbours at Large and
			   Huge, with three tests looking at it and each blind for a
			   different reason. */
			seen[at].widths.push(shape.minWidth);

			/* **The family too.** A purpose that resets the font takes the panel
			   face off with it, and both halves of this test were blind to that:
			   the size and the height stayed correct while the lettering did
			   not. "LAYOUT" was the one word on the bar in the body face and
			   Simon saw it at a glance, which is exactly what a face is for. */
			seen[at].faces.push(shape.fontFamily);

			seen[at].who.push(one.className + "|" + shape.fontSize
				+ "|" + shape.minHeight + "|" + shape.minWidth + "|" + shape.fontFamily);
		}

		return seen;
	}""")


def test_a_control_takes_its_size_from_the_surface_it_sits_on (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Simon, twice: "I am not seeing consistency ... I want to ensure that as we
	build out more UI components, consistency is *default* not something I have
	to ask for each time."

	It was declared per purpose — `.offer`, `.clear`, `.switch`, `.move` — each
	in the place it was first needed and each correct there.  Then a button was
	added to a footer, inherited the sheet's size, and "send to…" came out half
	again as large as "clear" beside it.

	So a control's size is the surface's to decide and never the control's.
	A purpose may change colour, width and wording; it may not change height or
	type.  This is what makes that a rule rather than a paragraph.
	"""

	_open_the_stack(panel)
	_two_generators(panel, fake_app)

	# A sheet and a menu open, so chrome is measured with something in it rather
	# than only the bar.
	panel.locator('.part[data-part="grid"] .part-foot .offer.add').click()
	panel.wait_for_selector(".sheet .offer", timeout=5_000)

	for at, seen in _button_sizes(panel).items():
		assert len(set(seen["sizes"])) == 1, \
			f"{at} draws buttons at {sorted(set(seen['sizes']))}: {sorted(set(seen['who']))}"
		assert len(set(seen["floors"])) == 1, \
			f"{at} floors buttons at {sorted(set(seen['floors']))}: {sorted(set(seen['who']))}"
		assert len(set(seen["widths"])) == 1, \
			f"{at} floors button widths at {sorted(set(seen['widths']))}: {sorted(set(seen['who']))}"
		assert len(set(seen["faces"])) == 1, \
			f"{at} letters buttons in {sorted(set(seen['faces']))}: {sorted(set(seen['who']))}"


def test_a_control_on_the_lattice_is_a_cell_and_one_in_chrome_is_a_finger (
	panel: typing.Any) -> None:
	"""The division is the whole of the rule (#2107): what is on the lattice
	follows the size a person chose, and what is not keeps a fixed target.

	A menu option has no business being 96px tall because the pattern behind it
	is set large — and it has no business shrinking to 22 either, because it is
	not part of the music.
	"""

	_settled(panel)

	row = panel.evaluate(
		"() => getComputedStyle(document.documentElement).getPropertyValue('--row').trim()")

	seen = _button_sizes(panel)

	assert set(seen["lattice"]["floors"]) == {row}, \
		f"a control on the lattice is not one row: {sorted(set(seen['lattice']['who']))}"
	assert set(seen["chrome"]["floors"]) == {"44px"}, \
		f"a control in chrome is not a finger: {sorted(set(seen['chrome']['who']))}"


def test_no_button_declares_a_size_of_its_own (panel: typing.Any) -> None:
	"""The static half, and the one that catches it at the moment it is written
	rather than the moment somebody looks.

	A rule that names a button and sets its height or its type is a rule that
	will be right where it was written and wrong the first time that button is
	used somewhere else.  That is exactly how this went wrong.
	"""

	style = (superconductor.service.CLIENT_DIR / "style.css").read_text(encoding="utf-8")
	code = re.sub(r"/\*.*?\*/", "", style, flags=re.DOTALL)

	loose = []

	for block in re.findall(r"([^{}]+)\{([^{}]*)\}", code):
		selector, body = block[0].strip(), block[1]

		if "button" not in selector or ":" in selector.split("button")[-1].split(",")[0]:
			continue

		# The surface rules are the only ones allowed to say it, and they are
		# named here rather than matched by a prefix so that a fourth cannot be
		# added by accident.
		# Normalised, because the surface rules live in a cascade layer now and
		# every selector in one carries the layer's indentation.
		flattened = ", ".join(part.strip() for part in selector.split(","))

		if flattened in SURFACE_RULES:
			continue

		# `min-width` is in this list because it was not, and that is how
		# `.stepper button { min-width: 44px }` sat unlayered for as long as it
		# did — beating the surface rule outright and coming out half-size
		# beside its neighbours at Large and Huge. A rule that states height and
		# type and stops is a rule with a hole in it, which is the same sentence
		# the docstring above already had to be written for once.
		if ("min-height" in body or "min-width" in body or "font-size" in body
				or re.search(r"(?<!-)\bheight:", body)
				or re.search(r"(?<!-)\bwidth:", body)):
			loose.append(selector)

	assert loose == [], f"these name a button and set its own size: {loose}"


def test_every_control_centres_what_is_written_on_it (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""The hole the surface rule had, and Simon found it twice over.

	`.offer` set `align-items: flex-start` and `text-align: left` — right for the
	two-line options in a sheet, where it was written, and wrong the moment a
	footer button borrowed the class: "add a contribution" came out left-aligned
	beside a centred toggle.  The surface rule said height and type and stopped,
	so alignment was the property a purpose class could still quietly own.

	One exception, and it has to name itself: an option holds two lines rather
	than a label, and two lines centred read as neither.
	"""

	adrift = _in_every_state(panel, fake_app, lambda page: page.evaluate("""() => {
		const out = [];

		for (const one of document.querySelectorAll("*")) {
			const shape = getComputedStyle(one);

			/* **Every control, not every button.** This asked `<button>` alone,
			   so a dial — a div that captures the pointer and slides — had
			   never been checked, and neither had anything else that is a
			   control without being a button. `touch-action: none` is the
			   marker every target already carries, and the same one the target
			   rules are found by. */
			/* **A target constrains touch, and `none` is not the only way**
			   (#2213).  A list has to scroll, and a scroll starts on whatever is
			   under the finger — so the rows of the generator sheet declare
			   `pan-y`: they may be scrolled up and down and still may not be
			   panned sideways or pinched.  Selecting on `none` alone dropped
			   exactly the surface that had just changed out of this rule, which
			   is how a rule comes to be trusted and not enforced.

			   `body` declares `pan-x pan-y` and is not a target, which is why
			   this is a list of the two a control may say rather than "anything
			   but auto". */
			if (!["none", "pan-y"].includes(shape.touchAction)) continue;

			const text = (one.textContent || "").trim();

			if (!text) continue;

			/* Only the innermost control. A rocker is a framed group holding two
			   ends; the group carries the text of both and centres nothing
			   itself, so it is the ends that have to answer for it. */
			if ([...one.querySelectorAll("*")].some(
				(kid) => ["none", "pan-y"].includes(getComputedStyle(kid).touchAction))) continue;

			/* Centred by whichever mechanism applies: a flex control says so
			   with justify-content, anything else with text-align. */
			const flexed = shape.display === "flex" || shape.display === "inline-flex";
			const how = flexed ? shape.justifyContent : shape.textAlign;

			if (how === "center") continue;

			/* **Five exceptions, each named on the element and each with a
			   reason.** A list is only dangerous when it is implicit; this one
			   is the same shape as SURFACE_RULES — adding to it is a deliberate
			   act rather than something that happens.

			   - `option` stacks two lines, and two lines centred read as
			     neither.
			   - `picker` puts a label and its mark at opposite ends, the way a
			     select does.
			   - `part-title` is a bar and not a label: a block's name goes
			     where a name goes, with the close button at the far end. It is
			     the same shape as a picker and only becomes a control at all
			     when the layout is unlocked, which is why nothing had asked it
			     before this test looked past buttons.
			   - `dial` is a fader whose readout sits at the end of its own
			     track. Centred, the number would float in the middle of the
			     thing it describes and move as the fill moved under it.
			   - `choice` is one row of a list: a mark and then a name, which
			     have to line up down the column. Centred, each row places its
			     mark according to how long its own name is. **The size chooser
			     had been taking this exception since it was written and passing
			     anyway** — its third element carries `margin-left: auto`, which
			     eats the free space and leaves the first two at the start
			     whatever this property says. So the rule was already being
			     broken where the test could not see it, and it only became
			     visible when the theme picker grew to eleven rows and had no
			     such element. Simon saw it at a glance. */
			const named = ["option", "picker", "part-title", "dial", "choice"];

			if (named.some((one_) => one.classList.contains(one_))) continue;

			out.push((one.className || one.tagName) + " → " + how);
		}

		return out;
	}"""))

	assert adrift == [], f"these do not centre what is written on them: {adrift}"

	_open_the_stack(panel)
	panel.locator('.part[data-part="grid"] .part-foot button.add').click()
	panel.wait_for_selector(".sheet .option", timeout=5_000)

	# **And the other way round, which is the hole this had.** A control holding
	# two lines and *not* saying so came out centred, which this test permitted
	# — so the fault it exists to catch went through it three times: the footer
	# buttons, the send-to sheet's options, and the generator list. A button with
	# more than one element inside it is an option and must name itself one.
	#
	# `choice` is admitted here as well as above, and it is not a weakening: a
	# choice holds a mark and a name on **one** line, which is a different claim
	# from two lines and is asserted separately below. What this catches is a
	# control holding two lines and saying nothing, and a choice says something.
	unnamed = panel.evaluate("""() => [...document.querySelectorAll("button")]
		.filter((one) => one.children.length > 1
			&& !one.classList.contains("option") && !one.classList.contains("choice"))
		.map((one) => (one.className || one.tagName) + ": " + one.textContent.trim().slice(0, 30))
	""")

	assert unnamed == [], f"these hold two lines and do not say so: {unnamed}"

	stacked = panel.evaluate(
		"""() => getComputedStyle(document.querySelector(".sheet .option")).flexDirection""")

	assert stacked == "column", "an option stacks its two lines, and says so by its class"

	# And the counterpart, so the two exceptions cannot quietly become one
	# shape: a choice is a single row with its mark at the front.
	panel.locator(".sheet header button").click()
	playwright_api.expect(panel.locator(".sheet")).to_have_count(0, timeout=5_000)
	panel.locator(".theme > button").click()
	panel.wait_for_selector(".theme .choices button.choice", timeout=5_000)

	laid = panel.evaluate("""() => {
		const shape = getComputedStyle(document.querySelector(".theme .choices button.choice"));

		return [shape.flexDirection, shape.justifyContent];
	}""")

	assert laid == ["row", "flex-start"], (
		f"a choice is a row with its mark at the front, and this one is {laid}")


def test_the_switch_on_a_line_is_big_enough_to_find (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""It was a bare triangle, and it was already a switch — Simon asked whether
	it should become one, which is the finding rather than the request: an
	affordance nobody can see is not an affordance.

	Held to the same floor as a control on the lattice, because that is what it
	is: something a finger has to land on, at whatever size the person chose.
	"""

	_open_the_stack(panel)
	_route(panel, fake_app)

	row = float(panel.evaluate(
		"() => parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--row'))"))

	across = float(panel.eval_on_selector(
		'[data-join="second>grid"] circle.node',
		"one => one.getBoundingClientRect().width"))

	assert across >= row, f"the switch on a line is {across}px against a {row}px row"


def test_every_toggle_says_off_the_same_way (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Simon: "should we mandate the same toggle in all places where we
	enable/disable something?"

	The shape cannot be the same — a block has a row to put a button in and a
	line does not — but the *sentence* must be: a filled thing is sounding and an
	outlined one is not.  That is what makes a state readable without being
	learned twice.
	"""

	_open_the_stack(panel)
	_two_generators(panel, fake_app)

	# **The accent is the sentence, and where it is drawn is the shape.** A
	# rocker carries it on the end that is pressed, and the switch on a line
	# carries it on the disc itself — because a line has no room for two ends.
	# So this asks whether the accent is *present*, not which element holds it,
	# which is the only form of the question both shapes can answer.
	accent = panel.evaluate("""() => {
		const lit = (one) => {
			const wanted = getComputedStyle(document.documentElement)
				.getPropertyValue("--on").trim();
			const paint = (el) => {
				const seen = getComputedStyle(el);

				return [seen.backgroundColor, seen.fill].join(" ");
			};

			const swatch = document.createElement("span");
			swatch.style.color = wanted;
			document.body.appendChild(swatch);
			const resolved = getComputedStyle(swatch).color;
			swatch.remove();

			return [one, ...one.querySelectorAll("*")].some((el) => paint(el).includes(resolved));
		};

		return {
			live: lit(document.querySelector('.part[data-part="stack/one"] .switch')),
			mute: lit(document.querySelector('.part[data-part="grid"] .part-foot .switch')),
		};
	}""")

	assert accent == {"live": True, "mute": True}, f"a live toggle is not lit: {accent}"

	# And a silenced one shows no accent at all, in both places.
	fake_app.confirm("grid/enabled", False, by="panel")
	panel.wait_for_selector(".part.silent", timeout=5_000)

	assert _pressed_end(panel, '.part[data-part="grid"] .part-foot .switch') == "off", \
		"a silenced block's rocker is not pressed off"

	still = panel.eval_on_selector(
		'.part[data-part="grid"] .part-foot .switch .yes',
		"one => getComputedStyle(one).backgroundColor")

	assert still == "rgba(0, 0, 0, 0)", \
		f"a silenced toggle still carries the accent: {still}"


def test_a_switch_lives_with_the_thing_it_switches (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Simon: "If I disable a *route* I am not disabling the *source*, which
	might feed other *routes* which I have not disabled."

	He is right, and the mistake was mine to defend.  A generator is a stack
	entry in exactly one pattern, so it has exactly one link and its own on/off
	*is* that link's — one stored value, which I showed in two places and called
	a feature.  A person reading two switches reasonably believes they say two
	things.

	So: a generator has a block and its switch is in it; a route has only a line
	and its switch is there.  Nothing has two, and nothing switchable has none.
	"""

	_open_the_stack(panel)
	_two_generators(panel, fake_app)

	# A generator's line is a mark. Its switch is in its own window.
	assert panel.locator('[data-join="stack/one>grid"].switchable').count() == 0
	assert panel.locator('[data-join="stack/one>grid"] circle.node').count() == 0
	assert panel.locator('.part[data-part="stack/one"] .switch').count() == 1

	fake_app.confirm("stack/layers", [
		{"id": "one", "kind": "route", "source": "second", "index": 1,
		 "bypassed": False, "params": {}},
	], by="app")
	panel.wait_for_selector('[data-join="second>grid"]', timeout=5_000)
	_settled(panel)

	# A route has no window, so its switch is the one on its line.
	assert panel.locator('.joins.over [data-join="second>grid"].switchable').count() == 1
	assert panel.locator('[data-join="second>grid"] circle.node').count() == 1


def test_silencing_a_route_leaves_its_source_alone (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""The case Simon reasoned to before it could arise: a grid feeding several
	patterns, muted at one of them.  Silencing that link must not silence the
	grid, which is still feeding the others."""

	_open_the_stack(panel)
	_route(panel, fake_app)

	before = panel.locator('.part[data-part="second"] .part-foot .switch').inner_text().strip()

	panel.locator('[data-join="second>grid"] circle.node').click()

	asked = [one["path"] for one in fake_app.sets]

	assert "second/enabled" not in asked, f"silencing a route touched its source: {asked}"
	assert panel.locator(
		'.part[data-part="second"] .part-foot .switch').inner_text().strip() == before


def _in_every_state (panel: typing.Any, fake_app: typing.Any, look: typing.Any) -> list[str]:
	"""Run one measurement over every state that puts a target on the glass.

	**Both target rules used to be checked in exactly one state**: the
	Generators page, layout locked, nothing open.  Everything behind a popover,
	behind the latch, or on another page was unenforced — and that is where the
	violations were.  A rule with a hole in its test is worse than no rule,
	because it is trusted.

	Each state is named, so a failure says where it was found rather than only
	what.
	"""

	found = []

	def note (where: str) -> None:
		for one in look(panel):
			found.append(f"{where}: {one}")

	_open_the_stack(panel)
	_two_generators(panel, fake_app)
	note("the stack page")

	# A sheet, which is its own surface.
	panel.locator('.part[data-part="grid"] .part-foot .offer.add').click()
	panel.wait_for_selector(".sheet .offer", timeout=5_000)
	note("a sheet open")
	panel.locator(".sheet header button").click()
	playwright_api.expect(panel.locator(".sheet")).to_have_count(0, timeout=5_000)

	# A popover on the bar.
	panel.locator(".sizes > button").click()
	panel.wait_for_selector(".sizes .choices button", timeout=5_000)
	note("the size popover open")
	panel.locator(".sizes > button").click()
	playwright_api.expect(panel.locator(".sizes .choices")).to_have_count(0, timeout=5_000)

	# **And the other one, which was never a state here.** The size popover was
	# taken as standing for both, and it does not: it is the one whose rows carry
	# a third element with `margin-left: auto`, which is exactly what hid a
	# centring violation in both of them for as long as they have existed. Two
	# popovers of the same shape are two states, because the whole lesson of the
	# six is that a state nothing renders in is a state nothing checks.
	panel.locator(".theme > button").click()
	panel.wait_for_selector(".theme .choices button", timeout=5_000)
	note("the theme popover open")
	panel.locator(".theme > button").click()
	playwright_api.expect(panel.locator(".theme .choices")).to_have_count(0, timeout=5_000)

	# The inventory, which only exists while the layout is unlocked — the default
	# since #2215, so this is the state a panel opens in rather than one to
	# switch to. Waited for by name regardless, because a state that renders
	# nothing checks nothing and would report a clean pass for the wrong reason.
	_unlocked(panel)
	panel.wait_for_selector(".inventory button", timeout=5_000)
	note("the layout unlocked")

	# And held, which the flipped default made the state worth adding: the
	# padlock filled, the grips gone, every block still.
	_locked(panel)
	note("the layout held")
	_unlocked(panel)

	# A menu inside a block, which is a popover sitting on the lattice rather
	# than on the chrome. The generator's pitch has six voices behind one; the
	# Moog's two-option field draws buttons instead and has no menu at all.
	menu = panel.locator('.part[data-part="stack/one"] .menu')

	menu.locator("button").first.click()
	panel.wait_for_selector('.part[data-part="stack/one"] .menu .options', timeout=5_000)
	note("a menu open in a block")
	panel.keyboard.press("Escape")

	# A windowed grid, whose scroll strip is a target and renders only for a
	# control declaring `visible_rows`.
	panel.locator(".pages button", has_text="Bass").click()
	panel.wait_for_selector(".window .track", timeout=5_000)
	_settled(panel)
	note("the bass page")

	return sorted(set(found))


def test_a_target_has_a_surface_and_an_edge_and_a_mark_has_neither (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Simon: "How can we ensure a user can visually identify what is a touch
	target, and what is not?"

	A borderless button is a button nobody finds; a bordered label is a button
	that does nothing when pressed.  So every target is a filled shape with an
	edge, and nothing else is.

	Found by `touch-action: none`, which every target already had to declare —
	a target must not scroll the page out from under the finger using it — so
	the marker is honest rather than invented for this test.  SVG says surface
	and edge as fill and stroke, so both are asked in both languages.

	**One member of a group takes its edge from the group's frame.**  A rocker
	is one framed control with two ends and a divider between them, which is
	how the machines this panel is drawn after build one — and giving each end
	a border of its own would draw a box inside a box.  The rule's purpose is
	that a target must be findable, and inside a frame with a divider it is; so
	a group states that it is one, and its members are held to the surface
	alone.
	"""

	bare = _in_every_state(panel, fake_app, lambda page: page.evaluate(r"""() => {
		const empty = (paint) => !paint || paint === "none" || paint === "rgba(0, 0, 0, 0)";

		/* **An edge is what a person sees, not which property drew it.**
		
		   Two ways to draw one here. A border, which must actually be visible —
		   `border: 1px solid transparent` satisfied a width check while showing
		   nothing at all, and a target nobody can find is exactly what this rule
		   exists to stop. Or a spread ring, `0 0 0 1px`, which is how a block
		   draws its frame; a drop shadow is not an edge, so the ring is matched
		   rather than the presence of any shadow. */
		const edged = (shape) =>
			(parseFloat(shape.borderTopWidth) > 0 && !empty(shape.borderTopColor))
			|| /0px 0px 0px [\d.]+px/.test(shape.boxShadow);

		const wrong = [];

		/* A scrim is not a target. The whole glass behind a sheet takes a tap to
		   dismiss it, which is a region rather than a control: there is nothing
		   to find, and drawing an edge round the viewport would say there was. */
		const scrim = (one) => one.classList.contains("sheet");

		/* A piano roll's ground is bounded by the lattice it is part of. A step
		   grid's cells are pads and are drawn as pads, with a gap between them;
		   a note grid's cells touch on purpose, and what a finger is aiming at
		   there is a bar drawn across them. */
		const roll = (one) => one.classList.contains("cell") && one.closest(".grid.notes");

		for (const one of document.querySelectorAll("*")) {
			const shape = getComputedStyle(one);

			/* **A target constrains touch, and `none` is not the only way**
			   (#2213).  A list has to scroll, and a scroll starts on whatever is
			   under the finger — so the rows of the generator sheet declare
			   `pan-y`: they may be scrolled up and down and still may not be
			   panned sideways or pinched.  Selecting on `none` alone dropped
			   exactly the surface that had just changed out of this rule, which
			   is how a rule comes to be trusted and not enforced.

			   `body` declares `pan-x pan-y` and is not a target, which is why
			   this is a list of the two a control may say rather than "anything
			   but auto". */
			if (!["none", "pan-y"].includes(shape.touchAction)) continue;
			if (scrim(one) || roll(one)) continue;

			const named = (one.className.baseVal !== undefined
				? one.className.baseVal : one.className) || one.tagName.toLowerCase();

			const surface = !empty(shape.backgroundColor) || !empty(shape.fill);

			/* **A member of a framed container takes the container's edge.**
			
			   The rocker is why this exists — one framed control with two ends
			   and a divider, which is how the machines this panel is drawn
			   after build one, and giving each end its own border would draw a
			   box inside a box. The same is true of a popover: a floating,
			   bordered surface is the thing a person finds, and the rows inside
			   it are read as a list. And of a block's title bar, which is the
			   handle for the block and is bounded by the block.
			
			   **A container says so itself.** It used to be matched by class
			   name here — `.options`, `.choices` — which made the rule a list,
			   and a list is the thing that drifts: a fifth popover added later
			   would not be in it and nothing would say so. A framed group
			   declares a role, as the rocker always has.
			
			   A block is the one structural exception, because its title bar is
			   the handle for it and takes the block's own frame. Kept narrow on
			   purpose: this matches the parent only, so it exempts a block's
			   own header and nothing deeper. */
			const frames = '[role="group"], .part';
			const parent = one.parentElement;
			const frame = parent && getComputedStyle(parent);

			const framed = parent && parent.matches(frames) && edged(frame);

			/* **An invisible edge is not an edge.** `border: 1px solid
			   transparent` satisfied a width test while showing nothing on the
			   glass, which is precisely the thing this rule exists to stop:
			   a target a person cannot find. */
			const edge = framed || edged(shape)
				|| (!empty(shape.stroke) && parseFloat(shape.strokeWidth) > 0);

			if (!surface || !edge) {
				wrong.push(named + (surface ? "" : " (no surface)") + (edge ? "" : " (no edge)"));
			}
		}

		return [...new Set(wrong)];
	}"""))

	assert bare == [], f"these can be touched and do not look like it: {bare}"


def test_a_target_is_at_least_one_row_in_both_directions (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""The other half: if a thing cannot be given that much room, it must not be
	touchable.

	**This is a consistency check and not a reachability one, and the difference
	matters.**  `controlRow` returns the cell exactly, so `--row` and `--cell`
	are the same number and the floor moves with the target — which means this
	can never report anything as too small on the lattice.  What it does enforce
	is that a target is never smaller than the surface it sits on says a control
	should be, which is a real rule and the one that caught the scroll strip.

	What it does *not* answer is whether a finger can hit a 22px control at
	Compact.  Simon settled that deliberately on 2026-09-06 (#2140): a step cell
	is the most-tapped thing on this surface and works at that size, so exempting
	a switch from a size the person chose is the inconsistency.  The absolute
	question belongs to the panel probes (#1997, #1998) and is hardware-gated.
	Do not read a pass here as evidence about fingers.
	"""

	small = _in_every_state(panel, fake_app, lambda page: page.evaluate("""() => {
		const row = parseFloat(
			getComputedStyle(document.documentElement).getPropertyValue("--row"));
		const wrong = [];

		for (const one of document.querySelectorAll("*")) {
			if (!["none", "pan-y"].includes(getComputedStyle(one).touchAction)) continue;

			const box = one.getBoundingClientRect();

			// Chrome keeps a fixed 44; the lattice follows the person's cell.
			const floor = one.closest(".bar, .sheet, .menu .options") ? 44 : row;

			if (box.width + 0.5 < floor || box.height + 0.5 < floor) {
				const named = (one.className.baseVal !== undefined
					? one.className.baseVal : one.className) || one.tagName.toLowerCase();

				wrong.push(`${named} ${Math.round(box.width)}x${Math.round(box.height)} < ${floor}`);
			}
		}

		return [...new Set(wrong)];
	}"""))

	assert small == [], f"these can be touched and are too small to hit: {small}"


# --- Where a beat begins is the app's to say (#1465) --------------------------


def test_a_step_grid_marks_the_beat_the_app_declared (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Not every fourth step, which is a fact about a rig rather than about a grid.

	Three of the five places that mark a beat derived it from `steps` and
	`beats`; two wrote down 4.  Nothing caught it because every grid this
	fixture declares is four steps to the beat — which is exactly the reason the
	assumption was worth not writing down, and exactly why the test has to
	change the ratio rather than trust the default.
	"""

	_settled(panel)

	def marked () -> list[int]:
		return panel.evaluate("""() => [...document.querySelectorAll(
			'.part[data-part="second"] .cell')]
			.map((one, index) => [index % 8, one.classList.contains("downbeat")])
			.filter(([, on]) => on)
			.map(([step]) => step);""")

	assert sorted(set(marked())) == [0, 4], f"eight steps over two beats: {marked()}"

	# The same grid, told it is four beats long. Nothing else about it changes.
	fake_app.redeclare({
		**conftest.CONTROLS,
		"second": {**conftest.CONTROLS["second"], "beats": 4},
	})

	_settled(panel)

	playwright_api.expect(panel.locator(
		'.part[data-part="second"] .cell.downbeat')).to_have_count(4, timeout=5_000)

	assert sorted(set(marked())) == [0, 2, 4, 6], (
		f"eight steps over four beats should mark every second one: {marked()}")


def test_a_velocity_lane_marks_the_same_beats_as_the_grid_above_it (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""A note grid derived its beat and its own velocity lane wrote down 4.

	Neither looks wrong on its own, which is why this asserts that the two
	agree rather than asserting a number: whatever the strip says, the lane
	under the same pattern has to say it too.
	"""

	panel.locator(".pages button", has_text="Bass").click()
	_settled(panel)

	fake_app.redeclare({
		**conftest.CONTROLS,
		"bass": {**conftest.CONTROLS["bass"], "beats": 4},
	})

	_settled(panel)

	agreed = panel.evaluate("""() => {
		const block = document.querySelector('.part[data-part="bass"]');

		/* The strip alternates its weight beat by beat, so where one beat ends
		   and the next begins is where that alternation flips. It used to be a
		   run of four hues and this read the colour class; the mechanism moved
		   and the question did not. */
		const run = [...block.querySelectorAll(".beats .beat")].map(
			(one) => one.classList.contains("off"));

		return {
			strip: run.map((colour, step) => [step, colour])
				.filter(([step, colour]) => step === 0 || colour !== run[step - 1])
				.map(([step]) => step),
			lane: [...block.querySelectorAll(".lane .weight")]
				.map((one, index) => [index, one.classList.contains("downbeat")])
				.filter(([, on]) => on)
				.map(([step]) => step),
		};
	}""")

	assert agreed["lane"], f"the lane marked no beat at all: {agreed}"

	assert agreed["lane"] == agreed["strip"], (
		f"the lane and the strip above it disagree about where a beat is: {agreed}")

	assert agreed["lane"] == [0, 2, 4, 6], (
		f"eight steps over four beats should mark every second bar: {agreed}")


def test_a_press_that_snaps_onto_a_note_does_not_rewrite_it (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Aiming at the gap before a note must not shorten the note.

	`snapped` rounds, so a press on empty ground can round *up* onto a position
	where a note already starts.  Asking only about where the finger landed read
	that as empty, and placing there sent a `/length` for the note that was
	already there — the `true` beside it is a no-op on the app, but the length
	is not, so a note quietly took the current snap as its length.

	Reachable wherever a step holds more than one position, which is the whole
	point of `divisions`: this fixture's `fine` grid keeps four.
	"""

	panel.locator(".pages button", has_text="Bass").click()
	_settled(panel)

	# A note starting one whole step in, and deliberately not the length the
	# snap would give it — otherwise the defect writes the value that is already
	# there and nothing can see it.
	fake_app.confirm("fine/rows", {"C2": {"4": {"length": 2, "velocity": 100}}})
	_settled(panel)

	before = len(fake_app.sets)

	# The last quarter of step 0, which is position 3: empty ground, and one the
	# default snap of a whole step rounds up to position 4.
	cell = panel.locator('.part[data-part="fine"] [data-path="fine/C2/0"]')
	box = cell.bounding_box()

	panel.mouse.move(box["x"] + box["width"] * 0.88, box["y"] + box["height"] / 2)
	panel.mouse.down()
	panel.mouse.up()

	panel.wait_for_timeout(400)

	asked = [one["path"] for one in fake_app.sets[before:]]

	assert not [path for path in asked if path.startswith("fine/C2/4")], (
		f"pressing the gap before a note wrote to it: {asked}")

	# And it selected that note rather than doing nothing at all, which is the
	# other way this assertion could be satisfied.
	playwright_api.expect(
		panel.locator('.part[data-part="fine"] .note.chosen')).to_have_count(1, timeout=5_000)


def test_a_confirmed_request_never_flashes_as_refused (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""A ring's abandon timer must not outlive the request that set it.

	`request()` overwrote the timer in the map without clearing the one already
	there, so any second set on a path before the first was answered — every
	frame of a dial drag, every path in the reconnect re-send — left a timer
	running that nothing could reach.  Five seconds later it flashed a control
	whose request had succeeded as refused, and dropped the ring of whatever was
	in flight on that path by then.

	This waits out the full five seconds on purpose.  There is no shorter way to
	observe a timer that should not exist, and the alternative — trusting that
	one `clearTimeout` is in the right place — is what let it through.
	"""

	_settled(panel)

	path = "grid/kick/1"
	cell = panel.locator(conftest.cell(path))

	# Two sets on one path before either is answered, then an answer to the
	# second. Nothing should be left waiting.
	cell.click()
	cell.click()

	asked = [one for one in fake_app.sets if one["path"] == path]

	assert len(asked) >= 2, f"two taps sent {len(asked)} requests"

	fake_app.confirm(path, asked[-1]["v"], client=asked[-1].get("client"), seq=asked[-1].get("seq"))

	playwright_api.expect(panel.locator(".cell.pending")).to_have_count(0, timeout=5_000)

	try:
		panel.wait_for_selector(".cell.failed", timeout=7_000)

	except playwright_api.TimeoutError:
		return

	raise AssertionError("an orphaned timer flashed a confirmed request as refused")


def test_every_block_lands_inside_the_glass_at_the_fitted_size (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""What *fit the glass* claims, asserted rather than trusted.

	The fit searches for the largest cell at which every part still lands inside
	the box, and the only thing that made that search wrong was the measurement
	it searched with: the part of a block that does not scale was measured from
	whichever part came first in the DOM and applied to all of them.  A note
	grid carries a velocity lane, a settings strip and a footer; a params block
	has no footer at all.  So the answer depended on arrangement order, which a
	person changes by dragging.

	**This one did not fail against the commit that fixed it, and says so.**  It
	was written to, with a params block declared first and a note grid second —
	the ordering where the block measured has the least chrome of any kind and
	the one measured *for* has the most.  It still fitted: the note grid's rows
	were over-counted by as much as its chrome was under-measured, and the two
	errors cancelled.  So this is a guard on the property rather than evidence
	about the defect, and a reader should not mistake it for the second.  The
	measurement is right now for a reason that can be read in `fit`; what this
	holds down is the claim `fits()` makes.
	"""

	# **A params block first and a note grid second**, which is the ordering that
	# breaks it: the block measured has the least chrome of any kind, and the one
	# measured *for* has the most — a velocity lane, a settings strip and a
	# footer. The other way round the error is conservative and invisible, which
	# is why the pages this fixture ships could not tell the difference.
	fake_app.redeclare(conftest.CONTROLS, [
		{"id": "mixed", "title": "Mixed", "parts": ["moog", "bass"]},
	])

	panel.wait_for_selector('.part[data-part="bass"]', timeout=10_000)
	_settled(panel)

	over = panel.evaluate("""() => {
		const box = document.querySelector(".grid-wrap");
		const shape = getComputedStyle(box);
		const outer = box.getBoundingClientRect();

		const room = {
			right: outer.right - parseFloat(shape.paddingRight),
			bottom: outer.bottom - parseFloat(shape.paddingBottom),
		};

		return [...document.querySelectorAll(".part[data-part]")].map((part) => {
			const at = part.getBoundingClientRect();

			return {
				part: part.dataset.part,
				right: Math.round(at.right - room.right),
				bottom: Math.round(at.bottom - room.bottom),
			};
		}).filter((one) => one.right > 1 || one.bottom > 1);
	}""")

	assert over == [], f"the fit left blocks hanging off the glass: {over}"


# --- What the app did not declare, the panel does not invent (#2049) ---------


def test_a_tempo_with_no_declared_range_is_not_clamped_by_the_panel (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""40 to 240 BPM is a fact about the music a rig plays, not about a transport.

	It was written into the client as a fallback, and `nudge` clamps to whatever
	it finds — so an app declaring no range could not be taken outside those
	bounds from the glass, with nothing saying why or that a limit existed.  An
	app that has bounds declares them; one that does not refuses what it cannot
	do, with a reason the panel already knows how to show.
	"""

	fake_app.redeclare({
		**conftest.CONTROLS,
		"transport": {"type": "transport", "fields": ["paused", "bpm"]},
	})

	_settled(panel)

	fake_app.confirm("transport/bpm", 260.0)
	_settled(panel)

	before = len(fake_app.sets)

	panel.locator(".tempo button", has_text="+5").click()

	asked = [one for one in fake_app.sets[before:] if one["path"] == "transport/bpm"]

	assert asked, "the panel sent nothing"
	assert asked[-1]["v"] > 260.0, (
		f"the panel clamped a tempo to a range nobody declared: asked for {asked[-1]['v']}")


def test_a_grid_that_declares_no_weight_scale_draws_every_mark_the_same (
	panel: typing.Any, fake_app: typing.Any) -> None:
	""""How hard" is a question this panel cannot answer without being told.

	It divided by a hard-coded 127 — a MIDI number, in a package whose own
	`controls.py` says it carries no MIDI and leaves what a value means to the
	composition.  An app that declares its range gets marks in proportion to it;
	one that does not gets marks all the same size, rather than a scale invented
	on its behalf.
	"""

	fake_app.redeclare({
		**conftest.CONTROLS,
		"grid": {one: held for one, held in conftest.CONTROLS["grid"].items()
		         if one != "velocity_range"},
	})

	_settled(panel)
	_realised(panel, fake_app, {"kick": {"1": 127}, "snare": {"1": 20}})

	def across (path: str) -> float:
		return float(panel.eval_on_selector(
			conftest.cell(path),
			"one => parseFloat(getComputedStyle(one, '::after').width)"))

	loud = across("grid/kick/1")
	quiet = across("grid/snare/1")

	assert abs(loud - quiet) < 0.5, (
		f"a panel told nothing about weight drew {loud}px and {quiet}px")


def test_a_cable_lights_what_the_end_in_your_hand_can_land_on (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Two ends, two different sets of blocks, and it used to light one of them
	for both.

	Dragging the socket you are choosing a destination, so the blocks that can
	answer are the ones whose stack takes what is plugged in at the far end.
	Dragging the plug you are choosing a *source*, so the blocks that can answer
	are the ones that destination's stack declares it takes from.  Lighting the
	destinations for the plug showed precisely the set that cannot be what you
	are looking for.  The drop always resolved correctly against `sources`; only
	the affordance lied.
	"""

	_open_the_stack(panel)
	_route(panel, fake_app)
	_apart(panel, "grid", dx=0, dy=420)

	def lit_while_holding (selector: str) -> list[str]:
		"""Which blocks are lit part-way through a drag from this fitting."""

		panel.locator(selector).scroll_into_view_if_needed()

		box = panel.locator(selector).bounding_box()
		x = box["x"] + box["width"] / 2
		y = box["y"] + box["height"] / 2

		panel.mouse.move(x, y)
		panel.mouse.down()
		panel.mouse.move(x + 40, y + 40, steps=6)

		try:
			return panel.evaluate("""() => [...document.querySelectorAll(".part[data-part]")]
				.filter((one) => getComputedStyle(one).opacity === "1")
				.map((one) => one.dataset.part)
				.sort();""")

		finally:
			# Back where it started, so the route survives for the second half.
			panel.mouse.move(x, y, steps=6)
			panel.mouse.up()
			_joins_settled(panel)

	# The socket is looking for a pattern to feed. `grid` is the one whose stack
	# takes from `second`.
	holding_socket = lit_while_holding('[data-join="second>grid"] .socket')

	assert holding_socket == ["grid"], (
		f"a socket in the hand should light the destinations: {holding_socket}")

	# The plug is looking for something to feed *from*. `second` is what the
	# stack declares as a source; `grid` is the one block that cannot be one.
	holding_plug = lit_while_holding('[data-join="second>grid"] .collar')

	assert holding_plug == ["second"], (
		f"a plug in the hand should light the sources: {holding_plug}")


def _at_contract (panel: typing.Any, service_url: str, monkeypatch: typing.Any,
                  spoken: str) -> str:
	"""Reload the panel against a service claiming to speak *spoken*.

	The greeting is built per hello and reads the module global as it goes, so
	moving the global moves what the next panel is told — which is the only way
	to stand in front of a mismatched service without running two of them.
	"""

	monkeypatch.setattr(superconductor.protocol, "CONTRACT_VERSION", spoken)

	panel.goto(service_url)
	panel.wait_for_selector(".bar .build", timeout=10_000)

	return str(panel.locator(".bar .build").first.inner_text()).strip()


def test_the_panel_says_when_the_service_speaks_a_different_contract (
	panel: typing.Any, service_url: str, monkeypatch: typing.Any) -> None:
	"""#2164, and the case it exists for is the one the build stamp cannot see.

	A stale build means this browser is holding an old page, and the reload
	button beside this already offers the fix.  But the service serves the client
	from disk on *every* request, so a reload always fetches the newest
	JavaScript and the build hash matches even when the running Python is hours
	older than the files it is serving.  Everything looks picked up and nothing
	is — it cost a round trip on 2026-09-05, with a feature declared broken on
	the glass while both processes predated it.

	That case has exactly one symptom: page and service agreeing about the build
	and disagreeing about the contract.  So the message names the process to
	restart, rather than offering a reload that would do nothing.
	"""

	major, minor, _ = (int(one) for one in superconductor.protocol.CONTRACT_VERSION.split("."))

	behind = _at_contract(panel, service_url, monkeypatch, f"{major}.{minor - 1}.0")
	assert "service is behind this page" in behind, behind
	assert "restart" in behind, "it names no process to restart, which is the only useful half"

	ahead = _at_contract(panel, service_url, monkeypatch, f"{major}.{minor + 1}.0")
	assert "page is behind the service" in ahead, ahead

	# Across a major number a frame either end already knows may have changed
	# shape, so the direction stops being the useful thing to say.
	grave = _at_contract(panel, service_url, monkeypatch, f"{major + 1}.0.0")
	assert "disagree" in grave, grave

	drawn = panel.eval_on_selector(".bar .build", "one => one.className")
	assert "grave" in drawn, f"a major difference is drawn like a minor one: {drawn}"


def test_a_matching_contract_leaves_the_build_stamp_alone (
	panel: typing.Any, service_url: str) -> None:
	"""The ordinary case says nothing, or the warning stops meaning anything.

	It also proves the test above is measuring the mismatch rather than the bar:
	the same element carries both, and a message that were always there would
	pass every assertion in it.
	"""

	panel.goto(service_url)
	panel.wait_for_selector(".bar .build", timeout=10_000)

	stamp = str(panel.locator(".bar .build").first.inner_text()).strip()

	assert "behind" not in stamp and "disagree" not in stamp, stamp
	assert "mismatch" not in panel.eval_on_selector(".bar .build", "one => one.className")


def _on_the_glass (panel: typing.Any, selector: str) -> tuple[int, int, int]:
	"""Where a popover is drawn, against the width of the glass."""

	return tuple(panel.eval_on_selector(selector, """one => {
		const box = one.getBoundingClientRect();

		return [Math.round(box.left), Math.round(box.right), window.innerWidth];
	}"""))


def test_no_popover_is_drawn_off_the_side_of_the_glass (panel: typing.Any) -> None:
	"""#2197.  A popover hangs from the control that opened it, and a control is
	not always where the popover assumed it would be.

	**The chrome popovers pin `right: 0`**, which is correct while the bar is one
	line and that control is near the right-hand end.  The bar wraps at narrow
	widths — it carries the transport, the tempo, the pattern navigation, the
	latch, the inventory, both choosers, the lamp and two readouts — and the
	control then lands near the *left* edge, where a popover reaching leftwards
	runs off the glass.  Measured at 1280 before the fix: the theme picker at
	x 14–136 and its popover spanning −25 to 136.

    **The block menu has the mirror of it**, and had no horizontal bound at all:
	it is placed by JavaScript, pinned to its trigger's left, and a trigger near
	the right edge pushes it off that side instead.  Its own test asserted top
	and bottom and said nothing about either side, so one direction of one
	instance was covered and the rule was not.

	Neither reproduces at 1920×1080, which is why they went unseen — the panel
	this is developed on is wide enough that the bar never wraps.  That is #2049
	almost word for word.

	Nothing here can be scrolled to, either: every button in a popover carries
	`touch-action: none`, so a finger landing on one is a press.  A control drawn
	off the glass is a control that cannot be worked, which this project counts
	as a defect in its own right.
	"""

	for which in (".theme", ".sizes"):
		panel.locator(f"{which} > button").click()
		panel.wait_for_selector(f"{which} .choices button", timeout=5_000)

		left, right, glass = _on_the_glass(panel, f"{which} .choices")

		assert left >= 0, f"{which} is drawn {-left}px off the left: {left}–{right} on {glass}"
		assert right <= glass, f"{which} is drawn {right - glass}px off the right"

		panel.locator(f"{which} > button").click()
		playwright_api.expect(panel.locator(f"{which} .choices")).to_have_count(0, timeout=5_000)

	_open_the_stack(panel)
	panel.locator('.part[data-part="stack/one"] .menu > button').first.click()
	panel.wait_for_selector('.part[data-part="stack/one"] .menu .options', timeout=5_000)

	left, right, glass = _on_the_glass(panel, ".menu .options")

	assert left >= 0, f"the block menu is drawn {-left}px off the left"
	assert right <= glass, f"the block menu is drawn {right - glass}px off the right"


def test_every_block_measures_a_whole_number_of_lattice_cells (panel: typing.Any) -> None:
	"""`.part` has claimed this since it was written and it was not true.

	A block's *left* edge snaps to the lattice; its right edge lands wherever its
	contents stop.  So the lane between two blocks dragged as close as they go is
	`pitch` minus however far the first one overran — and the overrun differs by
	what is inside it.  Simon saw it with three blocks side by side: 29px after
	the drum grid and 11px after the bass, both dragged as far as they would go.

	**The cause is that a note grid's cells have no gaps between them and a step
	grid's do**, which is right — a piano roll is a hairline lattice and a drum
	machine is spaced pads (#2107 §12).  But it made a note grid
	`label + steps * cell` wide where the lattice counts `steps * pitch`, so it
	landed 18px off with nothing in the arithmetic aware of it.

	Both kinds are checked, because one kind was always correct: a test on the
	step grid alone passes against the defect.
	"""

	adrift = []

	for page in ("All", "Bass", "Generators"):
		panel.locator(".pages button", has_text=page).click()
		panel.wait_for_selector(".part", timeout=5_000)
		_settled(panel)

		adrift += panel.evaluate("""(where) => {
			const root = getComputedStyle(document.documentElement);
			const cell = parseFloat(root.getPropertyValue("--cell"));
			const gap = parseFloat(root.getPropertyValue("--gap"));
			const pitch = cell + gap;
			const out = [];

			for (const part of document.querySelectorAll(".part")) {
				/* **The frame is read off the element, not from `--pad`.** That
				   token is `calc(var(--gap) * 2)`, and a custom property reads
				   back as the text that was written — so `parseFloat` gave NaN,
				   every comparison against it was false, and the first version
				   of this test passed against the defect it was written for. */
				const seen = getComputedStyle(part);
				const frame = parseFloat(seen.paddingLeft) + parseFloat(seen.paddingRight);

				/* The *content* is what has to span whole cells: a block is its
				   content plus a frame, and the placer reserves a cell for the
				   frame separately. */
				const content = part.getBoundingClientRect().width - frame;
				const over = (content + gap) % pitch;

				/* Sub-pixel layout is real; a whole cell out is the defect. */
				if (over > 0.5 && over < pitch - 0.5) {
					out.push(where + " " + part.dataset.part
						+ ": content " + Math.round(content)
						+ " is " + Math.round(over) + "px past a cell boundary");
				}
			}

			return out;
		}""", page)

	assert adrift == [], "\n".join(adrift)


def test_an_instruments_settings_are_put_away_until_the_pattern_asks (
	panel: typing.Any) -> None:
	"""#2201, and Simon's requirement in his own words: a settings panel should
	not default open.

	The Matriarch's voicing stood beside its pattern for ever, on every page that
	carried it, whether or not anybody was setting the instrument up.  A settings
	control that names the pattern it configures is now behind a latch on that
	pattern's own footer: a tap reveals it, a second tap puts it away, and it has
	a close of its own.

	**The latch is on the pattern and the block is the instrument's**, which is
	what makes the relationship worth declaring rather than inferring: nothing
	about a grid says which instrument is on the other end of it, and only the
	composition knows (#1465).
	"""

	panel.locator(".pages button", has_text="Bass").click()
	panel.wait_for_selector('.part[data-part="bass"]', timeout=5_000)
	_settled(panel)

	settings = panel.locator('.part[data-part="moog"]')
	latch = panel.locator('.part[data-part="bass"] .part-foot button.settings')

	assert settings.count() == 0, "the settings were open before anybody asked"
	assert latch.count() == 1, "the pattern offers no way to reach its instrument"

	latch.click()
	panel.wait_for_selector('.part[data-part="moog"]', timeout=5_000)

	assert settings.count() == 1
	assert latch.get_attribute("aria-pressed") == "true", (
		"the latch does not say it is holding something open")

	# A second tap on the latch puts it away, which is what makes it a latch
	# rather than a button that only ever opens.
	latch.click()
	playwright_api.expect(settings).to_have_count(0, timeout=5_000)
	assert latch.get_attribute("aria-pressed") == "false"

	# And its own close does the same, without touching the settings themselves.
	latch.click()
	panel.wait_for_selector('.part[data-part="moog"]', timeout=5_000)
	panel.locator('.part[data-part="moog"] .part-title button').click()
	playwright_api.expect(settings).to_have_count(0, timeout=5_000)


def test_a_settings_block_is_joined_to_the_instrument_it_sets (
	panel: typing.Any) -> None:
	"""#2416, Simon's suggestion of 2026-09-10.

	A settings block floats where it is put like any other, and two of them open
	at once look alike — the same column of fields, and nothing saying which
	instrument each one belongs to. The fact was already on the wire: a `params`
	control declares `configures`, naming the pattern whose instrument it sets
	(#2201), and the panel used it only to decide where the block may be hidden.

	**Wired rather than patched**, for the reason a generator's line is: settings
	belong to one pattern, are made with it and die with it, so there is no
	gesture to offer and no fitting to draw.
	"""

	panel.locator(".pages button", has_text="Bass").click()
	panel.wait_for_selector('.part[data-part="bass"]', timeout=5_000)
	_settled(panel)

	assert panel.locator('.joins.under [data-join="moog>bass"]').count() == 0, \
		"a line was drawn to a settings block nobody had opened"

	panel.locator('.part[data-part="bass"] .part-foot button.settings').click()
	panel.wait_for_selector('.part[data-part="moog"]', timeout=5_000)
	_joins_settled(panel)

	line = panel.locator('.joins.under [data-join="moog>bass"]')

	assert line.count() == 1, "the settings say nothing about which pattern they set"
	assert "wired" in (line.get_attribute("class") or ""), \
		"a settings line offered a gesture that does not exist"

	assert panel.locator('.joins.over [data-join="moog>bass"]')\
		.locator("circle, rect").count() == 0, "a settings line drew a fitting"


def test_a_settings_panel_is_divided_by_the_sections_its_app_named (
	panel: typing.Any) -> None:
	"""Simon asked for all thirty-six of the Matriarch's controls, and said why:
	*"not because I'll necessarily need all 36, but I want to see how we handle a
	busy interface, and use it as an example to set some conventions."*

	So the heading is the deliverable rather than the controls.  It appears when
	the section changes and never otherwise — an instrument with six settings does
	not want them and one with thirty-six is unreadable without them, and the app
	is what decides which it is by declaring the sections or not.

	**Read in sequence rather than sorted**, because the order is the
	composition's: it is the order the settings appear on the instrument, which is
	the order somebody looking for one expects.
	"""

	panel.locator(".pages button", has_text="Bass").click()
	panel.wait_for_selector('.part[data-part="bass"]', timeout=5_000)
	panel.locator('.part[data-part="bass"] .part-foot button.settings').click()
	panel.wait_for_selector('.part[data-part="moog"]', timeout=5_000)

	drawn = panel.eval_on_selector_all(
		'.part[data-part="moog"] .grid.params > *',
		"""els => els.map((one) => [one.className.split(" ")[0],
			one.dataset.field || one.textContent.trim()])""")

	headings = [what for kind, what in drawn if kind == "group"]

	assert headings == ["Glide"], (
		f"one heading for the one section this app names, and once: {drawn}")

	# It comes before the fields it heads, and the ungrouped fields that follow
	# it get no heading of their own — a panel does not invent a section for
	# something the app did not put in one.
	order = [what for kind, what in drawn if kind in ("group", "setting")]

	assert order[0] == "Glide", f"the heading is not at the front of its section: {order}"
	assert "shape" in order and "voicing" in order, order


def test_a_note_grid_draws_what_a_generator_put_on_it (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Simon: I can create a generator on the Minitaur pattern and hear its
	result, but I do not see the generated note indicators on the grid.

	He could not, and the panel was not at fault: `Recipe._target` ended with
	`isinstance(grid, StepGrid)`, from when a stack could only be built onto the
	drum machine — so **no realised event was ever sent for a pitched pattern**
	and there was nothing to draw (#2218).  It went unnoticed for as long as it
	did because a stack on anything but the DRM1 is two days old (#2147).

	**Reported in the positions the grid is addressed in, not in steps.**  A note
	grid divides a step into places a note may start (#2115) and the rig's bass
	declares six, so a dot reported in steps would land at a sixth of where the
	note is.  `fine` declares four, which is why it is the one used here.
	"""

	panel.locator(".pages button", has_text="Bass").click()
	panel.wait_for_selector('.part[data-part="fine"]', timeout=5_000)
	_settled(panel)

	# Two positions inside one drawn cell, and one in the next: at four
	# divisions, positions 4 and 6 are both in step 1 and position 8 is step 2.
	fake_app.realised("fine", {"C2": {"4": 40, "6": 110, "8": 90}})

	marked = '.part[data-part="fine"] .cell.ghost'
	playwright_api.expect(panel.locator(marked)).to_have_count(2, timeout=5_000)

	drawn = panel.eval_on_selector_all(marked, """els => els.map((one) => [
		one.dataset.path, one.style.getPropertyValue("--struck")])""")

	# A note grid's cell is addressed by the *position* it begins at rather than
	# by a step number, so the cell holding step 1 is `.../4` at four divisions.
	# Positions 4 and 6 share that cell; position 8 is the next one.
	at = sorted(path.rsplit("/", 1)[1] for path, _ in drawn)
	assert at == ["4", "8"], f"a position was drawn in the wrong cell: {drawn}"

	# The loudest of the two sharing a cell is the one drawn, which is the rule
	# the app applies to a step: what is heard is one sound at the weight of the
	# louder. 110 against 40 in the first, 90 alone in the second.
	weights = dict((path.rsplit("/", 1)[1], float(w or 0)) for path, w in drawn)
	assert weights["4"] > weights["8"], (
		f"the quieter of two in one cell won, or the weight is not read: {drawn}")


def test_dragging_a_block_does_not_resize_the_page (panel: typing.Any) -> None:
	"""Simon: dragging a title bar zooms the display in or out, a lot, and the
	size readout changes with it.

	#2072 settled that a page which no longer fits **scrolls** rather than
	rearranging or resizing itself.  The fit already held still *during* a drag
	and then caught up on release — which does not honour that at all, it only
	moves the resize to the instant the finger lifts, when nothing is expected to
	move any more (#2217).

	So where a block sits is not an input to the fit: it re-fits for the glass,
	the page, the set of blocks and the chosen size, and never for an
	arrangement.
	"""

	_unlocked(panel)
	_settled(panel)

	def size () -> float:
		return float(panel.evaluate(
			"() => parseFloat(getComputedStyle(document.documentElement)"
			".getPropertyValue('--cell'))"))

	before = size()
	readout = panel.locator(".sizes > button").inner_text()

	block = panel.locator('.part[data-part="grid"]')
	stood = block.bounding_box()
	title = panel.locator('.part[data-part="grid"] .part-title').bounding_box()

	# Rightwards and down, which is the direction that grows the arrangement and
	# so the direction that used to shrink every cell on the page.
	# **Far enough to change the answer.** A short drag leaves the arrangement
	# fitting at the same cell size, so it would pass whatever the fit did — the
	# first version of this test did exactly that. Kept inside `innerWidth`,
	# because Playwright clamps a move past the edge and the drag then reads as
	# going the other way.
	panel.mouse.move(title["x"] + 20, title["y"] + 5)
	panel.mouse.down()
	panel.mouse.move(min(title["x"] + 900, 1200), title["y"] + 320, steps=12)
	panel.mouse.up()
	_settled(panel)

	# **The drag has to have moved something**, or this asserts that nothing
	# happened rather than that the right nothing happened.
	assert block.bounding_box() != stood, "the block did not move, so this proves nothing"

	assert size() == before, f"the drag resized the page: {before} to {size()}"
	assert panel.locator(".sizes > button").inner_text() == readout, (
		"the size readout followed a drag")


def test_a_transform_is_offered_under_its_own_heading (panel: typing.Any) -> None:
	"""#2246.  Two catalogues in one sheet, read as two.

	A generator invents notes and a transform reshapes whatever the layers above
	it put down.  They are reached identically — a name and parameters in the
	same shapes — which is exactly why the glass has to say which is which: a
	stack's *order* is the whole of what it means, and a list that hides the
	difference makes ordering unreadable.  Two kinds of connection must not look
	alike (#2119), for the third time.
	"""

	_open_the_stack(panel)

	panel.locator(".part-foot .offer.add").click()
	panel.wait_for_selector(".sheet", timeout=5_000)

	headings = panel.locator(".sheet-body .group").all_text_contents()

	assert [one.strip() for one in headings] == [
		"adds notes", "reshapes what is already there"]

	# And a transform's own row carries the mark, so nothing has to infer it
	# from where the row happens to sit in the list.
	assert panel.locator(".sheet .offer.reshaping", has_text="rotate").count() == 1
	assert panel.locator(".sheet .offer.reshaping", has_text="euclidean").count() == 0


def test_a_transform_added_from_the_sheet_reaches_the_app_as_a_transform (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""It names its function in `transform`, not in `generator`.

	The field is what tells the two apart on the wire, so an app reading
	`generator` on a transform layer would look it up in the wrong catalogue and
	refuse a name that exists — and a panel too old to know the kind finds no
	`generator` and draws nothing, rather than drawing it as something it is not.
	"""

	_open_the_stack(panel)

	panel.locator(".part-foot .offer.add").click()
	panel.wait_for_selector(".sheet", timeout=5_000)
	panel.locator(".sheet .offer", has_text="rotate").click()

	asked = [one for one in fake_app.sets if one["path"] == "stack/layers"]

	assert asked, "adding a transform asked for nothing"

	layer = asked[-1]["v"][-1]

	assert layer["kind"] == "transform"
	assert layer["transform"] == "rotate"
	assert "generator" not in layer, "a transform named itself as a generator"


def test_a_transform_block_is_marked_apart_from_a_generator (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""On the title bar rather than the body, because the body is a column of
	parameters and those are the same in both — it is the block's identity that
	differs, and the bar is where a block says what it is."""

	_open_the_stack(panel)

	# Confirmed by the app rather than tapped, because a face follows the app
	# and never the finger: a layer is not drawn until the app says it is there.
	fake_app.confirm("stack/layers", [
		{"id": "one", "generator": "euclidean", "index": 1, "bypassed": False,
		 "params": {"pitch": "kick", "pulses": 3, "velocity": [40, 80],
		            "duration": 1, "probability": 1}},
		{"id": "two", "kind": "transform", "transform": "rotate", "index": 1,
		 "bypassed": False, "params": {"steps": 3}},
	], by="app")

	panel.wait_for_function(
		"() => document.querySelectorAll('.recipe .layer').length === 2", timeout=5_000)
	_settled(panel)

	assert panel.locator(".part.reshaping").count() == 1, "the transform drew as a generator"

	marked = panel.locator(".part.reshaping .part-title").first
	plain = panel.locator(".part:not(.reshaping) .part-title").first

	assert marked.evaluate("el => getComputedStyle(el).borderBottomColor") \
		!= plain.evaluate("el => getComputedStyle(el).borderBottomColor"), \
		"a transform's bar is drawn exactly like a generator's"


def test_settings_are_reachable_on_a_page_that_names_only_their_pattern (
	panel: typing.Any) -> None:
	"""Simon, 2026-09-08: the latch flickered a cable and revealed nothing.

	`settingsFor` searches *every* control, so the latch is offered on any page
	carrying the pattern — while the block it reveals was drawn only where the
	page also named the settings. Tapping it changed which blocks were showing,
	which re-laid the page out and then drew nothing: the flicker was the re-fit.

	**The Matriarch worked and the Minitaur did not**, because the rig's Band
	page happens to name one and not the other — so the fault was invisible on
	the instrument anybody happened to test.

	This is #2211 one layer up, and the same rule settles it: a thing that
	belongs to a pattern is drawn wherever that pattern is drawn.
	"""

	panel.locator(".pages button", has_text="Bass").click()
	panel.wait_for_selector('.part[data-part="bass"]', timeout=5_000)
	_settled(panel)

	latch = panel.locator('.part[data-part="bass"] .part-foot button.settings')

	assert latch.count() == 1, "the pattern offers no way to reach its instrument"
	assert panel.locator('.part[data-part="moog"]').count() == 0, (
		"the settings were open before anybody asked")

	latch.click()
	panel.wait_for_selector('.part[data-part="moog"]', timeout=5_000)

	assert panel.locator('.part[data-part="moog"] .setting').count() > 0, (
		"the block appeared with nothing in it")

	# And away again, because a latch that only opens is a trap on a surface
	# with no keyboard.
	latch.click()
	panel.wait_for_selector('.part[data-part="moog"]', state="detached", timeout=5_000)


# --- a block's height is part of the arrangement (#2227) ---------------------

def test_a_block_can_be_pulled_to_a_different_height (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""Simon, 2026-09-07: *"they might want to work within 4 octaves and be able
	to see all the notes as they play — without scrolling."*

	`visible_rows` was the app's alone and fixed, so the rig's bass grid had 25
	rows and showed 12 with no way to see the rest.  How many rows a grid *has*
	is the app's fact; how many you want in front of you is the person's, and it
	belongs beside the x and y that already travel with a page.
	"""

	_unlocked(panel)
	_settled(panel)

	block = panel.locator('.part[data-part="grid"]')
	before = block.bounding_box()
	grip = panel.locator('.part[data-part="grid"] .part-grip').bounding_box()

	middle = grip["x"] + grip["width"] / 2

	panel.mouse.move(middle, grip["y"] + grip["height"] / 2)
	panel.mouse.down()
	panel.mouse.move(middle, grip["y"] + grip["height"] / 2 - 90, steps=8)
	panel.mouse.up()

	_settled(panel)

	assert block.bounding_box()["height"] < before["height"], (
		"the block did not shrink when its bottom edge was pulled up")

	# The frame crosses two sockets and lands on the app's own thread.
	deadline = time.monotonic() + 5

	while "all" not in fake_app.arrangements and time.monotonic() < deadline:
		time.sleep(0.05)

	kept = {one["name"]: one for one in fake_app.arrangements.get("all") or []}

	assert kept.get("grid", {}).get("rows") == 1, (
		f"the height did not reach the app: {kept.get('grid')}")


def test_a_height_outlives_a_reload (panel: typing.Any) -> None:
	"""It travels the same path as a position and is kept in the same file, so a
	height that vanished on reload would be the one half of an arrangement that
	did not survive — which is worse than not having it, because nothing would
	say which half was real."""

	_unlocked(panel)
	_settled(panel)

	block = panel.locator('.part[data-part="grid"]')
	grip = panel.locator('.part[data-part="grid"] .part-grip').bounding_box()
	middle = grip["x"] + grip["width"] / 2

	panel.mouse.move(middle, grip["y"] + grip["height"] / 2)
	panel.mouse.down()
	panel.mouse.move(middle, grip["y"] + grip["height"] / 2 - 90, steps=8)
	panel.mouse.up()

	_locked(panel)
	_settled(panel)

	shorter = block.bounding_box()

	panel.reload()
	panel.wait_for_selector(".cell", timeout=10_000)
	_settled(panel)

	assert abs(panel.locator('.part[data-part="grid"]').bounding_box()["height"]
		- shorter["height"]) < 2


def test_a_block_with_one_row_is_offered_no_grip (panel: typing.Any) -> None:
	"""Height is not a question there, and a control that cannot do anything is
	worse than one that is absent — this project's own rule, and the reason
	`rotate` is filed as a defect rather than a feature.

	`second` declares a single row: there is nothing to reveal and nothing to
	give back.
	"""

	_unlocked(panel)
	_settled(panel)

	assert panel.locator('.part[data-part="grid"] .part-grip').count() == 1
	assert panel.locator('.part[data-part="second"] .part-grip').count() == 0


def test_a_generator_block_is_offered_no_grip (panel: typing.Any) -> None:
	"""A stack and a settings block both name the pattern they belong to, because
	that is how they come to be drawn wherever it is (#2211).  Asking about the
	control alone therefore put a resize grip on a stack of knobs and offered to
	show it more drum voices — found by the placement test, not by reading.
	"""

	panel.locator(".pages button", has_text="Generators").click()
	panel.wait_for_selector('.part[data-part^="stack/"]', timeout=10_000)
	_unlocked(panel)
	_settled(panel)

	assert panel.locator('.part[data-part^="stack/"]').count() > 0, (
		"no generator block on the page to check")
	assert panel.locator('.part[data-part^="stack/"] .part-grip').count() == 0


# --- a rack of grids somebody made (#2226) -----------------------------------

def _on_the_rack_page (panel: typing.Any) -> None:
	"""Go to the page carrying the rack and wait for it to be drawn."""

	panel.locator(".pages button", has_text="Stack alone").click()
	panel.wait_for_selector('.part[data-part="rack"]', timeout=10_000)
	_settled(panel)


def test_a_rack_with_nothing_in_it_says_so (panel: typing.Any) -> None:
	"""A block with nothing in it and no sentence reads as broken rather than as
	empty, and a person who has just been given a way to make grids is exactly
	the person who would read it that way."""

	_on_the_rack_page(panel)

	assert panel.locator('.part[data-part="rack"] .empty').count() == 1
	assert panel.locator('.part[data-part="rack"] .made').count() == 0


def test_a_rack_offers_to_make_a_grid_rather_than_a_generator (
	panel: typing.Any) -> None:
	"""One footer button serves both, and the word is what differs — a rack and a
	stack both add something and they do not add the same thing."""

	_on_the_rack_page(panel)

	assert panel.locator('.part[data-part="rack"] footer button',
		has_text="add grid").count() == 1


def test_making_a_grid_describes_it_rather_than_choosing_one (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""**The sheet is a form, not a list**, which is what makes it different from
	adding a generator: there is nothing to pick from, because a grid is
	described rather than chosen.

	Nothing crosses the wire until it is committed to — a half-described grid is
	not a thing the app should be told about.
	"""

	_on_the_rack_page(panel)

	panel.locator('.part[data-part="rack"] footer button', has_text="add grid").click()
	panel.wait_for_selector(".sheet", timeout=10_000)

	assert not [one for one in fake_app.sets if one["path"].startswith("rack/")], (
		"the app was told about a grid before anybody asked for one")

	panel.locator(".sheet .choices button", has_text="snare").click()
	panel.locator(".sheet .offer", has_text="make it").click()

	deadline = time.monotonic() + 5
	asked = None

	while asked is None and time.monotonic() < deadline:
		asked = next((one for one in fake_app.sets if one["path"] == "rack/grids"), None)
		time.sleep(0.05)

	assert asked, "asking for a grid sent nothing"
	assert len(asked["v"]) == 1
	assert asked["v"][0]["rows"] == ["snare"]
	assert asked["v"][0]["steps"] == 16
	assert asked["v"][0]["id"], "a grid arrived with no id of its own"


def test_a_grid_cannot_be_made_with_no_rows (panel: typing.Any) -> None:
	"""Refused on the glass as well as in the app, because a control that lets
	you ask for something impossible and then refuses it is worse than one that
	does not offer it — and the button says which it is rather than going dead
	with no reason."""

	_on_the_rack_page(panel)

	panel.locator('.part[data-part="rack"] footer button', has_text="add grid").click()
	panel.wait_for_selector(".sheet", timeout=10_000)

	make = panel.locator(".sheet .offer")

	assert make.is_disabled()
	assert "choose at least one row" in make.inner_text().lower()


def test_a_made_grid_is_listed_and_can_be_taken_away (
	panel: typing.Any, fake_app: typing.Any) -> None:
	"""The rack lists what it made and nothing else — each grid is a block of its
	own drawn beside it, and listing them twice would be two places to look for
	one fact."""

	_on_the_rack_page(panel)

	fake_app.confirm("rack/grids", [
		{"id": "a", "rows": ["snare"], "steps": 9},
		{"id": "b", "rows": ["kick", "clap"], "steps": 16}], by="app")

	panel.wait_for_selector('.part[data-part="rack"] .made', timeout=10_000)

	assert panel.locator('.part[data-part="rack"] .made').count() == 2

	panel.locator('.part[data-part="rack"] .made', has_text="snare").locator(
		"button.close").click()

	deadline = time.monotonic() + 5
	asked = None

	while asked is None and time.monotonic() < deadline:
		asked = next((one for one in fake_app.sets if one["path"] == "rack/grids"), None)
		time.sleep(0.05)

	assert asked, "removing a grid sent nothing"
	assert [one["id"] for one in asked["v"]] == ["b"]


def test_a_rack_is_offered_no_resize_grip (panel: typing.Any) -> None:
	"""A rack declares `rows` too — the pool a new grid may be made from — so
	asking whether that field exists would put a grip on it and offer to show it
	more of a list it does not draw (#2227, #2226)."""

	_on_the_rack_page(panel)
	_unlocked(panel)

	assert panel.locator('.part[data-part="rack"] .part-grip').count() == 0
