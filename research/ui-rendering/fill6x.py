"""Fill the 6x placeholders in finding.md from results_throttle6x.json (prototype scaffolding)."""

import json
import pathlib

HERE = pathlib.Path(__file__).parent
rows = json.loads((HERE / "results_throttle6x.json").read_text())
doc = (HERE / "finding.md").read_text()

TECH = {"dom": "DOM", "svg": "SVG", "canvas": "CV", "webgl": "GL"}
MODE = {"incremental": "INC", "full": "FULL"}

def fmt(s: dict) -> str:
	return f"{s['mean']:.2f} ({s['p95']:.1f})"

for r in rows:
	if "scenario" in r:
		if r["scenario"].startswith("waveform"):
			key = "6X_WAVE_" + TECH[r["tech"]]
		else:
			key = "6X_PAGE"
		doc = doc.replace(key + " ", fmt(r["js"]) + " ").replace("6X_L_" + key[3:], str(r["longFrames"]))
	elif "js" in r:
		key = f"6X_{TECH[r['tech']]}_{r['cells']}_{MODE[r['mode']]}"
		doc = doc.replace(key + " ", fmt(r["js"]) + " ").replace("6X_L_" + key[3:], str(r["longFrames"]))
	elif "jsPlusLayout" in r:
		key = f"6X_{TECH[r['tech']]}_{r['cells']}_{MODE[r['mode']]}_SL"
		doc = doc.replace(key + " ", fmt(r["jsPlusLayout"]) + " ")

(HERE / "finding.md").write_text(doc)
left = [l for l in doc.splitlines() if "6X_" in l]
print("unfilled lines:", len(left))
for l in left:
	print(l[:160])
