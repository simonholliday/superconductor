"""The half of a theme's rules that the suite deliberately does not assert.

`tests/test_themes.py` measures every contrast floor #2194 names, and stops
there.  The one remaining rule — that a lit step and a press in flight stay
**0.15 apart in OKLab under every dichromacy** — is a by-hand step on purpose:
a simulation of colour vision is a model of an average observer, a result near
the floor needs an eye, and a test that cannot be trusted at its own boundary is
worse than a document saying to check by hand.

**This is the instrument, and it is Brettel, Viénot & Mollon 1997** —
*Computerized simulation of color appearance for dichromats* — the standard
model for full dichromacy, and the one that holds for tritanopia, where the
single-matrix approximations are weakest (#2297).  #2194 named it as the more
correct procedure its own harness was not using.

**The constants are DaltonLens's**, the reference implementation
(`Simulator_Brettel1997` in DaltonLens-Python 0.1.5, with its defaults: the
Smith & Pokorny 1975 cone fundamentals behind its sRGB LMS model, and sRGB white
as the neutral axis).  They were taken at full precision on 2026-09-12 and this
file was checked against that implementation directly: across 20,024 colours
and all three dichromacies the two differ by at most 2.1e-15 in linear RGB.
Repeat that check — `research/theme-separation/verify_brettel.py` — before
changing any number below.

**What it replaced, and why the old figures cannot be compared.**  The first
harness was thrown away, and the numbers it published in #2190 cannot be
reproduced by *any* standard procedure: eight simulations (Brettel, Viénot,
Machado, Vischeck, two Coblis variants, and this file's own earlier matrices in
linear and gamma-encoded RGB), four distance measures and two readings of
*worst* — 64 combinations — and none comes within 0.05 of that table.  The
rebuild of 2026-09-08 used ad-hoc linear matrices of unrecorded provenance and
rounded each simulated colour to eight bits before measuring.  **Read numbers
from this file against other numbers from this file**, and treat both earlier
sets as superseded.

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
"""#2194's separation floor, generous partly to absorb what a model of vision cannot."""


Vector = tuple[float, float, float]


LMS_FROM_LINEAR: tuple[Vector, Vector, Vector] = (
	(0.1788595581, 0.43997116989800006, 0.03596576702400001),
	(0.03380393502, 0.27515242401400003, 0.036206345976000004),
	(0.00031087464, 0.0019166073600000002, 0.015280889928),
)
"""Linear sRGB into cone responses, as DaltonLens's sRGB model has it."""

LINEAR_FROM_LMS: tuple[Vector, Vector, Vector] = (
	(8.005328596048955, -12.88195449917583, 11.680649428743665),
	(-0.9782114906043382, 5.269449034168102, -10.183004327358567),
	(-0.040168230105817854, -0.3988505815643625, 66.48078797381677),
)
"""And back again."""


BRETTEL: dict[str, tuple[int, Vector, Vector, Vector]] = {
	"protanopia": (
		0,
		(0.0, 2.1839432772492007, -5.655538650248988),
		(0.0, 2.1661393080962634, -5.30454849662342),
		(0.0, 0.017508371928, -0.34516270501),
	),
	"deuteranopia": (
		1,
		(0.4616508256243508, 0.0, 2.4488491930306107),
		(0.4578873501053362, 0.0, 2.5895996059808186),
		(-0.017508371928, 0.0, 0.6547964950220001),
	),
	"tritanopia": (
		2,
		(-0.0021311449439688967, 0.0547679047976722, 0.0),
		(-0.061954832542766014, 0.16825739943426266, 0.0),
		(0.34516270501, -0.6547964950220001, 0.0),
	),
}
"""Brettel 1997, one entry per dichromacy.

Each is the cone response that dichromat lacks, the two half-planes it is
projected onto — one either side of the neutral axis, anchored at 475 and 575 nm
for protanopia and deuteranopia and at 485 and 660 nm for tritanopia — and the
normal of the plane that decides which half a colour falls in.  A single matrix
cannot say that, which is why the single-matrix approximations go wrong for
tritanopia.
"""


def _linear (colour: str) -> Vector:
	"""A `#rrggbb` as three linear-light channels, 0 to 1."""

	digits = colour.lstrip("#")
	red, green, blue = (test_themes.linear(int(digits[at:at + 2], 16) / 255) for at in (0, 2, 4))

	return red, green, blue


def _apply (matrix: tuple[Vector, Vector, Vector], vector: Vector) -> Vector:
	"""A 3 by 3 matrix times a column vector."""

	first, second, third = (sum(weight * value for weight, value in zip(row, vector)) for row in matrix)

	return first, second, third


def simulate (linear: Vector, how: str) -> Vector:
	"""*linear* as one form of dichromacy sees it, still in linear light.

	Clamped to the displayable range afterwards, as a screen would: a projection
	can land a colour just outside sRGB, and no panel can paint that.
	"""

	lms = list(_apply(LMS_FROM_LINEAR, linear))
	missing, one, two, normal = BRETTEL[how]

	# Which side of the neutral axis this colour lies on decides the half-plane.
	# DaltonLens takes the second only when the product is strictly negative.
	plane = two if sum(n * v for n, v in zip(normal, lms)) < 0 else one

	lms[missing] = sum(weight * value for weight, value in zip(plane, lms))

	red, green, blue = (max(0.0, min(1.0, value)) for value in _apply(LINEAR_FROM_LMS, (lms[0], lms[1], lms[2])))

	return red, green, blue


def oklab (linear: Vector) -> Vector:
	"""Perceptual coordinates, where a Euclidean distance means something.

	Roughly: 0.02 is just noticeable, 0.10 is clearly a different colour, 0.20 is
	unmistakable across a room.
	"""

	red, green, blue = linear

	long = (0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue) ** (1 / 3)
	medium = (0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue) ** (1 / 3)
	short = (0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue) ** (1 / 3)

	return (
		0.2104542553 * long + 0.7936177850 * medium - 0.0040720468 * short,
		1.9779984951 * long - 2.4285922050 * medium + 0.4505937099 * short,
		0.0259040371 * long + 0.7827717662 * medium - 0.8086757660 * short,
	)


def separation (one: Vector, other: Vector) -> float:
	"""How far apart two linear-light colours look."""

	return float(sum((a - b) ** 2 for a, b in zip(oklab(one), oklab(other))) ** 0.5)


def report (name: str, theme: dict[str, str]) -> bool:
	"""Say how far this theme's lit state is from its state in flight."""

	lit, flight = _linear(theme["--on"]), _linear(theme["--ring"])

	seen = {"normal": separation(lit, flight)}

	for how in BRETTEL:
		seen[how] = separation(simulate(lit, how), simulate(flight, how))

	worst = min(seen.values())

	print(f"  {name:14} " + "  ".join(f"{how} {value:.3f}" for how, value in seen.items())
	      + f"   worst {worst:.3f}  {'ok' if worst >= FLOOR else 'BELOW ' + str(FLOOR)}")

	return worst >= FLOOR


def main () -> int:
	"""Report every theme, or the one named on the command line."""

	themes = test_themes.palettes()
	wanted = sys.argv[1:] or sorted(themes)

	print(f"--on against --ring, OKLab, Brettel 1997, floor {FLOOR} (#2194, #2297)")

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
