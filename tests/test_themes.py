"""Every theme declares every token, and every theme clears every floor.

These are the two guards #2181 asked for, and they exist because a theme is the
one thing in this project that is *only* data: eleven blocks of colour with no
behaviour to go wrong and therefore nothing that fails loudly when one is wrong.
A missing token silently inherits the default's value and produces a single
wrong colour that nobody notices for weeks.  A value that does not clear its
floor produces a panel that is merely hard to read, which nobody reports as a
bug either.

**The numbers are not written down here.**  The stylesheet is read and measured,
so there is one copy of every value and it is the one the browser paints.  The
harness that produced the values in #2190 was a scratch script and is gone; this
is what replaced it, which is what #2194 says should happen.

The method is #2194's and is restated nowhere: floors are WCAG 2.2 — 4.5:1 for
text, 3:1 for a non-text mark or boundary — over WCAG relative luminance.

**What is deliberately not here** is the third check #2194 describes: `--on`
against `--ring` at ΔE 0.15 in OKLab under all three dichromacies.  It wants an
OKLab conversion and three simulation matrices, and #2194 is explicit that the
matrices are an approximation carrying real error and that a result near the
floor needs a human eye rather than an assertion.  A test that cannot be trusted
at its own boundary is worse than the document that says to check by hand.
"""

import re
import typing

import superintendent.service


# A token block has no nested braces, which is what lets this be a regex at all.
# If one ever grows a nested rule, this stops matching it and the completeness
# test below fails loudly rather than skipping it — which is the right way round.
THEME_BLOCK = re.compile(r'\[data-theme="([a-z]+)"\]\s*\{([^{}]*)\}')

ROOT_BLOCK = re.compile(r"^:root \{$(.*?)^\}$", re.MULTILINE | re.DOTALL)

DECLARATION = re.compile(r"^\t(--[a-z-]+):\s*(.+?);\s*$", re.MULTILINE)

PAIR = re.compile(r"^light-dark\((.+),\s*(.+)\)$")

# `:root` holds the geometry and the type scale as well as the palette — `--cell`
# is `44px` and `--face-body` is a font stack — so a colour is picked out by how
# its value starts rather than by name.  Same test as the one `test_client.py`
# uses to find a literal in the wrong place, and for the same reason: there is no
# naming convention separating them and inventing one would be a rule to keep.
COLOUR = re.compile(r"^(?:light-dark\(|#|rgba?\()")

# `SIZES` in the client is the same shape as `THEMES`, so the keys have to be
# read out of the right array rather than off the whole file.
THEME_LIST = re.compile(r"^const THEMES = \[$(.*?)^\];$", re.MULTILINE | re.DOTALL)


# **The two that ride on `light-dark()` are the exception, and it is named here
# rather than inferred.**  They pin `color-scheme` and let the pairs in `:root`
# resolve; every other theme writes its colours out flat.  A block that is
# neither — one declaring some tokens and not others — is the defect these tests
# exist to catch, so "declares nothing" has to be a stated exemption rather than
# a quantity small enough to wave through.
RIDES_ON_ROOT = {"light", "dark"}

# Never set on the root: choosing it removes the attribute.  It carries a
# `color-scheme` for the picker's swatch and nothing else.
SWATCH_ONLY = {"system"}


def stylesheet () -> str:
	return (superintendent.service.CLIENT_DIR / "style.css").read_text(encoding="utf-8")


def declared (body: str) -> dict[str, str]:
	"""The colours a block declares, and nothing else it declares."""

	return {name: value for name, value in DECLARATION.findall(body) if COLOUR.match(value)}


def offered () -> list[str]:
	"""The theme keys the client offers, in the order the picker lists them."""

	source = (superintendent.service.CLIENT_DIR / "app.js").read_text(encoding="utf-8")
	listing = THEME_LIST.search(source)
	assert listing, "the client no longer has a `THEMES` list, or it has been reshaped"

	return re.findall(r'\{ key: "([^"]+)"', listing.group(1))


def palettes () -> dict[str, dict[str, str]]:
	"""Every theme the stylesheet carries, as a flat map of token to colour.

	`:root` is two of them.  Its declarations are `light-dark()` pairs, so it
	defines the light and the dark palettes at once — which is exactly what the
	two named blocks above are relying on, and the reason they are allowed to be
	empty.
	"""

	style = stylesheet()
	root = ROOT_BLOCK.search(style)
	assert root, "the stylesheet has no `:root` block, or it is not written as one"

	found: dict[str, dict[str, str]] = {"light": {}, "dark": {}}

	for name, value in declared(root.group(1)).items():
		pair = PAIR.match(value)
		assert pair, f"{name} is not a `light-dark()` pair: {value}"
		found["light"][name], found["dark"][name] = (half.strip() for half in pair.groups())

	for name, body in THEME_BLOCK.findall(style):
		if name in RIDES_ON_ROOT or name in SWATCH_ONLY:
			continue
		found[name] = declared(body)

	return found


def linear (channel: float) -> float:
	return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def luminance (colour: str) -> float:
	"""WCAG relative luminance of a `#rrggbb`."""

	digits = colour.lstrip("#")
	channels = (int(digits[at:at + 2], 16) / 255 for at in (0, 2, 4))
	red, green, blue = (linear(one) for one in channels)

	return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast (one: str, other: str) -> float:
	lit, unlit = sorted((luminance(one), luminance(other)), reverse=True)

	return (lit + 0.05) / (unlit + 0.05)


# The 25 pairings of #2194, at their floors.
#
# **The expensive knowledge here is the pairings, not the floors.**  Knowing text
# needs 4.5:1 is free; knowing that a block's title bar is drawn in `--ink-quiet`
# and that `--edge-strong` lands on a *cell* as well as on a block took reading
# the stylesheet, and getting one of those wrong is how a check passes while the
# panel is still wrong.  Every defect found in this area so far has been a
# pairing nobody had measured rather than a floor nobody had met — #2192, #2193
# and #2196 in turn.
CHECKS: tuple[tuple[str, str, float], ...] = (
	("ink", "ground", 4.5),
	("ink", "part", 4.5),
	("ink", "panel", 4.5),
	("ink", "title-ground", 4.5),
	("ink-quiet", "part", 4.5),
	("ink-quiet", "panel", 4.5),
	("ink-quiet", "title-ground", 4.5),          # #2192 was found here
	("ink-faint", "part", 3.0),
	("ink-faint", "panel", 3.0),
	("ink-faint", "sunk", 3.0),                  # #2196 added this one
	("on", "panel", 3.0),
	("on", "part", 3.0),
	("on-ink", "on", 4.5),
	("on-edge", "panel", 3.0),
	("readout", "sunk", 4.5),
	("edge-strong", "sunk", 3.0),
	("ring", "panel", 3.0),
	("ring-ink", "ring", 4.5),
	("edge-strong", "part", 3.0),
	("edge-strong", "panel", 3.0),               # #2193 was found here
	("good", "part", 3.0),
	("bad", "part", 3.0),
	("warn", "part", 3.0),
	("danger", "part", 3.0),
	("danger", "panel", 3.0),
)

# `--ink-faint` is floored at 3.0 and its neighbour `--ink-quiet` at 4.5, though
# both are small condensed uppercase.  That is deliberate and is Simon's call of
# 2026-09-07 settling #2196: this ink is a mark rather than a word — a legend
# noticed once beside a reading, never read as a sentence — so it answers to a
# non-text floor.  The stylesheet says so at the declaration.


def test_every_theme_declares_every_token () -> None:
	"""A theme missing a token does not fail: it inherits the default's value
	and paints one wrong colour, on one surface, which nobody notices for weeks.

	The set is taken from `:root` rather than written down, so adding a token
	means adding it everywhere or watching this fail — which is the whole reason
	#2181 insisted the token set be settled before any theme was built.
	"""

	found = palettes()
	expected = set(found["dark"])

	assert len(expected) == 29, f"the token set is {len(expected)}, not 29: {sorted(expected)}"

	for name, theme in sorted(found.items()):
		assert set(theme) == expected, (
			f"{name} is missing {sorted(expected - set(theme))}"
			f" and declares {sorted(set(theme) - expected)} that no other theme has")


def test_the_two_that_ride_on_light_dark_declare_no_colours_of_their_own () -> None:
	"""`[data-theme="light"]` and `[data-theme="dark"]` pin `color-scheme` and
	stop there, which is what lets the pairs in `:root` be the whole of them.

	Asserted rather than assumed, because the failure is silent in the worst
	direction: a colour added to one of these blocks would override that half of
	every pair, and the pair would still be sitting in `:root` looking correct.
	"""

	blocks = dict(THEME_BLOCK.findall(stylesheet()))

	for name in sorted(RIDES_ON_ROOT | SWATCH_ONLY):
		assert name in blocks, f"there is no `[data-theme=\"{name}\"]` block at all"
		assert declared(blocks[name]) == {}, (
			f"{name} declares {sorted(declared(blocks[name]))}, but it is supposed to"
			f" carry nothing but `color-scheme`")


def test_every_theme_clears_every_contrast_floor () -> None:
	"""The numbers were prose in comments until now — 3.8:1 against the cell,
	4.6:1 under the button ink — which meant a new theme could ship something
	invisible at a glance and nothing would say so.

	This is the only basis on which a theme written by somebody else could be
	trusted, and it has already earned itself: run against the palette that
	shipped, it is what found #2192 and #2193.
	"""

	failures: list[str] = []

	for name, theme in sorted(palettes().items()):
		for ink, ground, floor in CHECKS:
			measured = contrast(theme[f"--{ink}"], theme[f"--{ground}"])

			if measured < floor:
				failures.append(
					f"{name}: --{ink} on --{ground} is {measured:.2f}:1, below {floor}")

	assert failures == [], "\n".join(failures)


def test_the_client_offers_exactly_the_themes_the_stylesheet_carries () -> None:
	"""Adding a theme is a block in one language and a line in another, and
	nothing but this keeps the two together.

	Both directions matter and they fail differently. A block with no line is a
	palette nobody can reach; a line with no block is a name in the picker that
	silently paints the default — and that one looks like the theme system is
	broken rather than like a theme is missing.
	"""

	listed = set(offered())
	carried = {name for name, _ in THEME_BLOCK.findall(stylesheet())}

	assert listed, "the client offers no themes at all, so this test proves nothing"
	assert listed == carried, (
		f"offered but not styled: {sorted(listed - carried)};"
		f" styled but not offered: {sorted(carried - listed)}")


def test_a_theme_key_is_the_selector_and_the_stored_value () -> None:
	"""One string is the `data-theme` attribute, the CSS selector and the
	`localStorage` value, and `index.html` writes it into the DOM before the app
	has loaded — checked by shape rather than against a list, so the shape is
	what has to hold.

	It is also a product string, which is where #2194's naming rule bites: no
	manufacturer's or artist's mark, and the provenance stays in the documents
	and in the stylesheet's comments.
	"""

	page = (superintendent.service.CLIENT_DIR / "index.html").read_text(encoding="utf-8")

	guard = re.search(r"/\^(\[a-z\]\+)\$/", page)
	assert guard, "index.html no longer checks the stored theme by shape"

	keys = offered()
	assert keys, "the client offers no themes at all, so this test proves nothing"

	for key in keys:
		assert re.fullmatch(r"[a-z]+", key), (
			f"{key!r} would be refused by index.html's guard and would flash the"
			f" default theme on every load")


def test_the_swatch_paints_itself_rather_than_a_copy_of_the_theme () -> None:
	"""The picker's swatch carries `data-theme`, so the theme's own block applies
	to it and every colour in it comes from that block.

	The alternative — a swatch listing its own hex — is a second copy of every
	palette, and a second copy is the thing this stylesheet's whole token scheme
	exists to prevent. It would also be wrong in the direction nobody checks: a
	swatch is what somebody picks a theme *by*.
	"""

	source = (superintendent.service.CLIENT_DIR / "app.js").read_text(encoding="utf-8")
	style = stylesheet()

	assert "<i data-theme=${theme.key}>" in source, (
		"the swatch no longer carries the theme it offers")

	swatch = re.search(r"^\.theme \.choices i \{([^{}]*)\}", style, re.MULTILINE)
	assert swatch, "the swatch has no rule"

	loose = re.findall(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(", swatch.group(1))
	assert loose == [], f"the swatch names its own colours rather than the theme's: {loose}"


def _every_reference (style: str) -> typing.Iterator[str]:
	for name in re.findall(r"var\((--[a-z-]+)\)", style):
		yield name


def test_the_recess_reads_its_own_ink () -> None:
	"""`--readout` exists because the recess and the grid pull `--on` in opposite
	directions on a light theme (#2191), and it does nothing at all unless
	`.lcd-value` actually reads it.

	Worth its own test because the failure is invisible on every dark theme —
	where the two are equal by design — and shows up only on a light one, which
	is the half nobody develops against.
	"""

	style = stylesheet()

	value = re.search(r"^\.lcd-value \{([^{}]*)\}", style, re.MULTILINE)
	assert value, "there is no `.lcd-value` rule"

	assert "var(--readout)" in value.group(1), (
		"the readout is not drawn in `--readout`, so the token is decoration")

	assert "--readout" in set(_every_reference(style)), "nothing reads `--readout`"
