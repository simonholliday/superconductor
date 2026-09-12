"""Which simulation procedure reproduces #2190's published worst-dichromacy row?"""

import numpy

from daltonlens import simulate

PUBLISHED = {
	"light":       ("#b87400", "#1c6fe0", 0.277),
	"dark":        ("#f0b429", "#4dabf7", 0.254),
	"modular":     ("#efe0bc", "#4c86d8", 0.201),
	"phosphor":    ("#3be07c", "#15834a", 0.217),
	"phaedra":     ("#de84d6", "#4a5fd8", 0.175),
	"constructor": ("#f44336", "#ededed", 0.202),
	"aluminium":   ("#b34a10", "#17479e", 0.236),
	"airports":    ("#24445d", "#b87f8c", 0.258),
	"oxygene":     ("#0e5450", "#3a6fd0", 0.194),
	"workbench":   ("#a33a05", "#10428f", 0.212),
}

KINDS = {"protan": simulate.Deficiency.PROTAN, "deutan": simulate.Deficiency.DEUTAN, "tritan": simulate.Deficiency.TRITAN}


def rgb8 (hex_):
	h = hex_.lstrip("#")
	return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def lin (c):
	return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def oklab_from_srgb8 (rgb):
	r, g, b = (lin(v / 255) for v in rgb)
	l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
	m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
	s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
	return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
	        1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
	        0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def dist (a, b):
	return sum((x - y) ** 2 for x, y in zip(oklab_from_srgb8(a), oklab_from_srgb8(b))) ** 0.5


def daltonlens_procedure (simulator):
	def run (colour, kind):
		image = numpy.array([[rgb8(colour)]], dtype=numpy.uint8)
		return [int(v) for v in simulator.simulate_cvd(image, KINDS[kind], severity=1.0)[0, 0]]
	return run


TOOL = {  # the rebuilt tool's matrices, verbatim
	"protan": [[0.170556992, 0.829443014, 0.0], [0.170556991, 0.829443008, 0.0], [-0.004517144, 0.004517144, 1.0]],
	"deutan": [[0.33066007, 0.66933993, 0.0], [0.33066007, 0.66933993, 0.0], [-0.02785538, 0.02785538, 1.0]],
	"tritan": [[1.0, 0.1273989, -0.1273989], [0.0, 0.8739093, 0.1260907], [0.0, 0.8739093, 0.1260907]],
}


def enc (c):
	c = max(0.0, min(1.0, c))
	return round(255 * (12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055))


def matrix_procedure (matrices, in_linear):
	def run (colour, kind):
		rgb = [v / 255 for v in rgb8(colour)]
		if in_linear:
			rgb = [lin(v) for v in rgb]
		out = [sum(row[i] * rgb[i] for i in range(3)) for row in matrices[kind]]
		return [enc(v) for v in out] if in_linear else [round(255 * max(0.0, min(1.0, v))) for v in out]
	return run


procedures = {
	"Brettel 1997 (DaltonLens)": daltonlens_procedure(simulate.Simulator_Brettel1997()),
	"Viénot 1999 (DaltonLens)": daltonlens_procedure(simulate.Simulator_Vienot1999()),
	"Machado 2009 (DaltonLens)": daltonlens_procedure(simulate.Simulator_Machado2009()),
	"Coblis v1 (DaltonLens)": daltonlens_procedure(simulate.Simulator_CoblisV1()),
	"Coblis v2 (DaltonLens)": daltonlens_procedure(simulate.Simulator_CoblisV2()),
	"Vischeck (DaltonLens)": daltonlens_procedure(simulate.Simulator_Vischeck()),
	"the rebuilt tool, linear RGB": matrix_procedure(TOOL, True),
	"the rebuilt tool's matrices, gamma sRGB": matrix_procedure(TOOL, False),
}

rows = []

for name, run in procedures.items():
	errors = []
	values = {}
	for theme, (on, ring, published) in PUBLISHED.items():
		worst_with_normal = min([dist(rgb8(on), rgb8(ring))] + [dist(run(on, k), run(ring, k)) for k in KINDS])
		values[theme] = worst_with_normal
		errors.append(abs(worst_with_normal - published))
	rows.append((max(errors), sum(errors) / len(errors), name, values))

rows.sort()

print(f"{'procedure':42} {'max err':>8} {'mean err':>9}   " + " ".join(f"{t[:6]:>7}" for t in PUBLISHED))
print(f"{'#2190 published':42} {'':>8} {'':>9}   " + " ".join(f"{p[2]:7.3f}" for p in PUBLISHED.values()))
for worst, mean, name, values in rows:
	print(f"{name:42} {worst:8.3f} {mean:9.3f}   " + " ".join(f"{values[t]:7.3f}" for t in PUBLISHED))


# ---- second round: the distance measure may have differed too -----------------

import math


def oklab_gamma (rgb):
	r, g, b = (v / 255 for v in rgb)
	l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
	m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
	s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
	return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
	        1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
	        0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def lab (rgb):
	r, g, b = (lin(v / 255) for v in rgb)
	x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
	y = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 1.0
	z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
	f = lambda t: t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116
	return (116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z)))


def ciede2000 (one, two):
	L1, a1, b1 = one
	L2, a2, b2 = two
	C1, C2 = math.hypot(a1, b1), math.hypot(a2, b2)
	Cm = (C1 + C2) / 2
	G = 0.5 * (1 - math.sqrt(Cm ** 7 / (Cm ** 7 + 25 ** 7)))
	a1p, a2p = (1 + G) * a1, (1 + G) * a2
	C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
	h1p = math.degrees(math.atan2(b1, a1p)) % 360
	h2p = math.degrees(math.atan2(b2, a2p)) % 360
	dLp, dCp = L2 - L1, C2p - C1p
	dh = h2p - h1p
	if C1p * C2p == 0: dh = 0
	elif dh > 180: dh -= 360
	elif dh < -180: dh += 360
	dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dh / 2))
	Lm, Cmp = (L1 + L2) / 2, (C1p + C2p) / 2
	hsum = h1p + h2p
	if C1p * C2p == 0: hm = hsum
	elif abs(h1p - h2p) > 180: hm = (hsum + 360) / 2 if hsum < 360 else (hsum - 360) / 2
	else: hm = hsum / 2
	T = 1 - 0.17 * math.cos(math.radians(hm - 30)) + 0.24 * math.cos(math.radians(2 * hm)) \
		+ 0.32 * math.cos(math.radians(3 * hm + 6)) - 0.20 * math.cos(math.radians(4 * hm - 63))
	SL = 1 + 0.015 * (Lm - 50) ** 2 / math.sqrt(20 + (Lm - 50) ** 2)
	SC, SH = 1 + 0.045 * Cmp, 1 + 0.015 * Cmp * T
	RT = -2 * math.sqrt(Cmp ** 7 / (Cmp ** 7 + 25 ** 7)) * math.sin(math.radians(60 * math.exp(-((hm - 275) / 25) ** 2)))
	return math.sqrt((dLp / SL) ** 2 + (dCp / SC) ** 2 + (dHp / SH) ** 2 + RT * (dCp / SC) * (dHp / SH))


metrics = {
	"OKLab": dist,
	"OKLab, no linearising": lambda a, b: sum((x - y) ** 2 for x, y in zip(oklab_gamma(a), oklab_gamma(b))) ** 0.5,
	"CIELAB ΔE76 / 100": lambda a, b: sum((x - y) ** 2 for x, y in zip(lab(a), lab(b))) ** 0.5 / 100,
	"CIEDE2000 / 100": lambda a, b: ciede2000(lab(a), lab(b)) / 100,
}

rows = []

for pname, run in procedures.items():
	for mname, metric in metrics.items():
		for with_normal in (True, False):
			errors, values = [], {}
			for theme, (on, ring, published) in PUBLISHED.items():
				seen = [metric(run(on, k), run(ring, k)) for k in KINDS]
				if with_normal:
					seen.append(metric(rgb8(on), rgb8(ring)))
				values[theme] = min(seen)
				errors.append(abs(values[theme] - published))
			rows.append((max(errors), sum(errors) / len(errors), f"{pname} | {mname}{'' if with_normal else ' | dichromacies only'}", values))

rows.sort()
print("\n--- second round, best ten of", len(rows), "---")
print(f"{'#2190 published':78}                 " + " ".join(f"{p[2]:6.3f}" for p in PUBLISHED.values()))
for worst, mean, name, values in rows[:10]:
	print(f"{name:78} {worst:6.3f} {mean:6.3f}   " + " ".join(f"{values[t]:6.3f}" for t in PUBLISHED))
