"""Pull Brettel 1997's precomputed parameters out of DaltonLens at full precision."""

import numpy

from daltonlens import simulate

captured = {}


def capture (self, deficiency, H1, H2, n_sep_plane):
	element = {simulate.Deficiency.PROTAN: 0, simulate.Deficiency.DEUTAN: 1, simulate.Deficiency.TRITAN: 2}[deficiency]
	captured[deficiency] = (element, H1[element], H2[element], n_sep_plane)
	captured["model"] = (self.color_model.LMS_from_linearRGB, self.color_model.linearRGB_from_LMS)


simulate.Simulator_Brettel1997._dump_brettel_data = capture

simulator = simulate.Simulator_Brettel1997()
simulator.dumpPrecomputedValues = True

for deficiency in (simulate.Deficiency.PROTAN, simulate.Deficiency.DEUTAN, simulate.Deficiency.TRITAN):
	simulator._simulate_dichromacy_linear_rgb(numpy.zeros((1, 1, 3), dtype=numpy.float32), deficiency)

numpy.set_printoptions(precision=17, floatmode="unique")

fmt = lambda v: "(" + ", ".join(repr(float(x)) for x in v) + ")"

forward, back = captured["model"]
print("LMS_FROM_LINEAR = (")
for row in forward:
	print("\t" + fmt(row) + ",")
print(")")
print("LINEAR_FROM_LMS = (")
for row in back:
	print("\t" + fmt(row) + ",")
print(")")

for deficiency, name in ((simulate.Deficiency.PROTAN, "protanopia"), (simulate.Deficiency.DEUTAN, "deuteranopia"), (simulate.Deficiency.TRITAN, "tritanopia")):
	element, one, two, normal = captured[deficiency]
	print(f'"{name}": ({element}, {fmt(one)}, {fmt(two)}, {fmt(normal)}),')
