"""Is a pure-Python Brettel 1997 identical to DaltonLens's?"""

import random

import numpy

from daltonlens import simulate

LMS_FROM_LINEAR = (
	(0.1788595581, 0.43997116989800006, 0.03596576702400001),
	(0.03380393502, 0.27515242401400003, 0.036206345976000004),
	(0.00031087464, 0.0019166073600000002, 0.015280889928),
)
LINEAR_FROM_LMS = (
	(8.005328596048955, -12.88195449917583, 11.680649428743665),
	(-0.9782114906043382, 5.269449034168102, -10.183004327358567),
	(-0.040168230105817854, -0.3988505815643625, 66.48078797381677),
)
BRETTEL = {
	"protanopia": (0, (0.0, 2.1839432772492007, -5.655538650248988), (0.0, 2.1661393080962634, -5.30454849662342), (0.0, 0.017508371928, -0.34516270501)),
	"deuteranopia": (1, (0.4616508256243508, 0.0, 2.4488491930306107), (0.4578873501053362, 0.0, 2.5895996059808186), (-0.017508371928, 0.0, 0.6547964950220001)),
	"tritanopia": (2, (-0.0021311449439688967, 0.0547679047976722, 0.0), (-0.061954832542766014, 0.16825739943426266, 0.0), (0.34516270501, -0.6547964950220001, 0.0)),
}
KINDS = {"protanopia": simulate.Deficiency.PROTAN, "deuteranopia": simulate.Deficiency.DEUTAN, "tritanopia": simulate.Deficiency.TRITAN}


def lin (c):
	return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def enc (c):
	c = max(0.0, min(1.0, c))
	return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def mine (linear, how):
	lms = [sum(LMS_FROM_LINEAR[r][c] * linear[c] for c in range(3)) for r in range(3)]
	element, one, two, normal = BRETTEL[how]
	row = two if sum(n * v for n, v in zip(normal, lms)) < 0 else one
	lms[element] = sum(w * v for w, v in zip(row, lms))
	return [sum(LINEAR_FROM_LMS[r][c] * lms[c] for c in range(3)) for r in range(3)]


reference = simulate.Simulator_Brettel1997()

rng = random.Random(2297)
colours = [[rng.randrange(256) for _ in range(3)] for _ in range(20000)]
colours += [[int(h[i:i + 2], 16) for i in (0, 2, 4)] for h in (
	"b87400", "1c6fe0", "f0b429", "4dabf7", "efe0bc", "4c86d8", "3be07c", "15834a", "de84d6", "4a5fd8",
	"f44336", "ededed", "b34a10", "17479e", "24445d", "a96574", "0e5450", "3a6fd0", "a33a05", "10428f",
	"e2e2ea", "8f2bff", "000000", "ffffff")]

worst_linear = 0.0
mismatched_bytes = 0

for rgb in colours:
	linear = [lin(v / 255) for v in rgb]
	image_linear = numpy.array([[linear]], dtype=numpy.float64)
	image_srgb = numpy.array([[rgb]], dtype=numpy.uint8)

	for how, kind in KINDS.items():
		theirs = reference._simulate_dichromacy_linear_rgb(image_linear.copy(), kind)[0, 0]
		ours = mine(linear, how)
		worst_linear = max(worst_linear, max(abs(a - b) for a, b in zip(theirs, ours)))

		their_bytes = [int(v) for v in reference.simulate_cvd(image_srgb, kind, severity=1.0)[0, 0]]
		our_bytes = [round(255 * enc(v)) for v in ours]
		mismatched_bytes += sum(1 for a, b in zip(their_bytes, our_bytes) if abs(a - b) > 1)

print(f"colours checked: {len(colours)} x 3 dichromacies")
print(f"largest difference in linear RGB: {worst_linear:.2e}")
print(f"8-bit channels differing by more than one step: {mismatched_bytes}")
