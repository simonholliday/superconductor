"""The half of a theme's rules that the suite deliberately does not assert.

`tests/test_themes.py` measures every contrast floor #2194 names, and stops
there.  The one remaining rule — that a lit step and a press in flight stay
**0.15 apart in OKLab under every dichromacy** — is a by-hand step on purpose:
the linear LMS simulation matrices are an approximation rather than the full
Brettel-Viénot-Mollon procedure, the absolute figures carry real error, and a
test that cannot be trusted at its own boundary is worse than a document saying
to check by hand.

**This exists because the last harness that computed it was thrown away**, and
#2194 had to carry enough prose to rebuild it.  It was rebuilt on 2026-09-08 for
Prism and is kept this time.

**And the rebuild does not agree with the numbers it was rebuilt from.**  #2190
publishes a worst-dichromacy figure per palette; this reports 0.329 for Modular
where that table says 0.201, and 0.371 for Constructor against 0.202.  So the two
are different instruments rather than one instrument run twice — the prose in
#2194 was enough to rebuild *a* computation and not enough to rebuild *the* one.
Which is the sharper version of that document's own complaint about the harness
being thrown away: the loss was not the hour of work, it was the comparability.

**Read a number here against other numbers here**, never against #2190's table.
And read anything near the floor with an eye, which is what #2194 says and why
this is not in the suite.

Run it over every theme in the stylesheet:

    python tools/theme_separation.py

Or over one:

    python tools/theme_separation.py prism

It reads the stylesheet, so there is one copy of every value and it is the one
the browser paints.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tests"))

import test_themes


FLOOR = 0.15
"""#2194's separation floor, generous partly to absorb the simulation's error."""


def _rgb (colour: str) -> list[float]:
	"""A `#rrggbb` as three channels, 0 to 1."""

	digits = colour.lstrip("#")

	return [int(digits[at:at + 2], 16) / 255 for at in (0, 2, 4)]


def oklab (colour: str) -> tuple[float, float, float]:
	"""Perceptual coordinates, where a Euclidean distance means something.

	Roughly: 0.02 is just noticeable, 0.10 is clearly a different colour, 0.20 is
	unmistakable across a room.
	"""

	red, green, blue = (test_themes.linear(one) for one in _rgb(colour))

	long = (0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue) ** (1 / 3)
	medium = (0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue) ** (1 / 3)
	short = (0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue) ** (1 / 3)

	return (
		0.2104542553 * long + 0.7936177850 * medium - 0.0040720468 * short,
		1.9779984951 * long - 2.4285922050 * medium + 0.4505937099 * short,
		0.0259040371 * long + 0.7827717662 * medium - 0.8086757660 * short,
	)


def separation (one: str, other: str) -> float:
	"""How far apart two colours look."""

	return float(sum((a - b) ** 2 for a, b in zip(oklab(one), oklab(other))) ** 0.5)


BLIND: dict[str, list[list[float]]] = {
	"protanopia": [[0.170556992, 0.829443014, 0.0],
	               [0.170556991, 0.829443008, 0.0],
	               [-0.004517144, 0.004517144, 1.0]],
	"deuteranopia": [[0.33066007, 0.66933993, 0.0],
	                 [0.33066007, 0.66933993, 0.0],
	                 [-0.02785538, 0.02785538, 1.0]],
	"tritanopia": [[1.0, 0.1273989, -0.1273989],
	               [0.0, 0.8739093, 0.1260907],
	               [0.0, 0.8739093, 0.1260907]],
}
"""The common linear approximations, applied in *linear* sRGB and converted back.

Approximations, and #2194 says so at length: read a result near the floor with an
eye rather than with this.
"""


def simulate (colour: str, how: str) -> str:
	"""*colour* as one form of dichromacy renders it."""

	channels = [test_themes.linear(one) for one in _rgb(colour)]
	seen = [sum(row[at] * value for at, value in enumerate(channels)) for row in BLIND[how]]

	def back (channel: float) -> str:
		"""One linear channel, clamped and encoded the way sRGB wants it."""

		held = max(0.0, min(1.0, channel))
		held = 12.92 * held if held <= 0.0031308 else 1.055 * (held ** (1 / 2.4)) - 0.055

		return f"{round(held * 255):02x}"

	return "#" + "".join(back(one) for one in seen)


def report (name: str, theme: dict[str, str]) -> bool:
	"""Say how far this theme's lit state is from its state in flight."""

	lit, flight = theme["--on"], theme["--ring"]

	seen = {"normal": separation(lit, flight)}

	for how in BLIND:
		seen[how] = separation(simulate(lit, how), simulate(flight, how))

	worst = min(seen.values())

	print(f"  {name:14} " + "  ".join(f"{how} {value:.3f}" for how, value in seen.items())
	      + f"   {'ok' if worst >= FLOOR else 'BELOW ' + str(FLOOR)}")

	return worst >= FLOOR


def main () -> int:
	"""Report every theme, or the one named on the command line."""

	themes = test_themes.palettes()
	wanted = sys.argv[1:] or sorted(themes)

	print(f"--on against --ring, OKLab, floor {FLOOR} (#2194)")

	clear = True

	for name in wanted:
		if name not in themes:
			print(f"  {name}: no such theme in the stylesheet")
			clear = False
			continue

		# `light` and `dark` declare no colours of their own; the pairs in
		# `:root` are what they resolve to, and those are the two entries above.
		if not themes[name].get("--on"):
			continue

		clear = report(name, themes[name]) and clear

	return 0 if clear else 1


if __name__ == "__main__":
	raise SystemExit(main())
