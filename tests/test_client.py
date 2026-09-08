"""What can be checked about the client without a browser.

The page is the half of the system with no runnable tests on this host, so the
two things that can be established cheaply are established here: that it parses,
and that the one value it has to keep in step with Python is in step.
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

import superintendent.protocol
import superintendent.service

# One parser for the stylesheet's theme blocks, rather than a second regex here
# answering a slightly different question and drifting from the first.
import test_themes


def _node () -> pathlib.Path | None:
	"""A JavaScript engine, if this machine has one anywhere.

	Playwright bundles its own `node`, which is usually the only one present on
	a headless server: without it nothing here can so much as parse the client.
	"""

	found = shutil.which("node")

	if found:
		return pathlib.Path(found)

	try:
		import playwright

	except ImportError:
		return None

	bundled = pathlib.Path(playwright.__file__).parent / "driver" / "node"

	return bundled if bundled.exists() else None


def test_the_client_parses () -> None:
	"""A syntax error in the client is a page that draws nothing at all.

	Checked as a **module**, from standard input, and not as a path. Measured on
	this host on 2026-09-05: ``node --check <path>`` silently passes a ``const``
	redeclaration inside an ES module and catches the same code in a plain
	script. Two ``const at`` in one function got through the path form, and what
	found it was the page suite failing nineteen tests at once because the
	module never evaluated.
	"""

	engine = _node()

	if engine is None:
		pytest.skip("no JavaScript engine on this host, not even Playwright's own")

	for script in sorted(superintendent.service.CLIENT_DIR.glob("*.js")):
		done = subprocess.run(
			[str(engine), "--input-type=module", "--check"],
			input=script.read_text(encoding="utf-8"), capture_output=True, text=True)

		assert done.returncode == 0, f"{script.name} does not parse:\n{done.stderr}"


def test_the_client_checker_would_catch_a_redeclaration () -> None:
	"""The check above is only worth running if it catches what the old one missed.

	This is the exact fault that reached the panel: a name declared twice in one
	function, which Firefox refuses outright. Asserting the checker's teeth
	rather than trusting the flag.
	"""

	engine = _node()

	if engine is None:
		pytest.skip("no JavaScript engine on this host, not even Playwright's own")

	done = subprocess.run(
		[str(engine), "--input-type=module", "--check"],
		input='const [a, b] = [1, 2];\nconst a = 3;\n', capture_output=True, text=True)

	assert done.returncode != 0, "the syntax check no longer catches a redeclaration"


def test_every_size_in_the_stylesheet_comes_from_the_scale () -> None:
	"""Consistency has to be enforced rather than remembered.

	Eleven distinct font sizes had accumulated, of which exactly one scaled with
	the cell — so the pattern shrank when a person resized the grid and the
	controls beside it did not. A convention would drift again; this cannot.
	"""

	style = (superintendent.service.CLIENT_DIR / "style.css").read_text(encoding="utf-8")

	declared = re.findall(r"font-size:\s*([^;]+);", style)
	loose = [one.strip() for one in declared if not one.strip().startswith("var(--type-")]

	assert loose == [], f"these sizes are outside the scale: {loose}"


def test_the_scale_is_small_and_every_step_of_it_is_used () -> None:
	"""A scale nobody uses all of is a scale with a spare step in it, and a
	spare step is where the next inconsistency goes."""

	style = (superintendent.service.CLIENT_DIR / "style.css").read_text(encoding="utf-8")

	defined = set(re.findall(r"(--type-[a-z-]+):", style))
	used = set(re.findall(r"var\((--type-[a-z-]+)\)", style))

	assert len(defined) <= 6, f"the scale has grown to {len(defined)}: {sorted(defined)}"
	assert defined == used, f"defined but unused: {sorted(defined - used)}"


def test_no_rule_in_the_stylesheet_names_a_colour_of_its_own () -> None:
	"""A colour literal may appear in exactly two places: as half of a
	`light-dark()` pair in `:root`, or inside a `[data-theme]` block.  Anywhere
	else it is a colour the theme cannot reach.

	**This test used to say something narrower** — that every colour is a
	`light-dark()` pair and there is no second block at all — which was true
	while there were two themes and stopped being true at eleven.  The defect it
	was guarding against has not changed: a value written into an ordinary rule
	works in whichever theme it was picked for and is wrong in the other ten,
	and nothing about it looks wrong while you are in the theme it was picked
	for.  What changed is only where the legitimate copies live, and
	`test_themes.py` is what now holds them to declaring the same set.
	"""

	style = (superintendent.service.CLIENT_DIR / "style.css").read_text(encoding="utf-8")

	# Comments carry item numbers, which look exactly like short hex colours;
	# the two halves of a pair are of course literals, which is the point; and a
	# theme block is nothing but literals, which is also the point.
	code = re.sub(r"/\*.*?\*/", "", style, flags=re.DOTALL)
	code = test_themes.THEME_BLOCK.sub("", code)

	# **And a rule scoped to one theme is the third legitimate place**, which
	# Prism established: a theme may be a rule as well as a set of values, and a
	# colour in `[data-theme="x"] .thing` is as reachable by that theme as one in
	# its block. What is forbidden is a colour in an *ordinary* rule, which works
	# in the theme it was picked for and is wrong in every other.
	code = re.sub(r'^[^{}\n]*\[data-theme="[a-z]+"\][^{}]*\{[^{}]*\}',
	              "", code, flags=re.MULTILINE)

	code = re.sub(r"light-dark\((?:[^()]|\([^()]*\))*\)", "", code)

	# **Every way CSS can name a colour, not just the two this used to know.**
	# It looked for `#rrggbb` and `rgb()` alone, so `hsl()`, `color-mix()` and
	# the named colours went straight through — measured on 2026-09-08 by
	# planting all three in an ordinary rule and watching this pass. That hole
	# was harmless while nothing used those forms and stopped being harmless the
	# moment a theme did: the next person copies what they see.
	loose = re.findall(
		r"#[0-9a-fA-F]{3,8}\b"
		r"|\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color|color-mix)\("
		# Not followed by a hyphen or a letter, or `white-space` is a colour and
		# every rule in the sheet names one.
		r"|\b(?:red|green|blue|white|black|yellow|orange|purple|pink|cyan"
		r"|magenta|grey|gray|silver|gold|teal|navy|olive|maroon|lime|aqua"
		r"|fuchsia|rebeccapurple)(?![-\w])",
		code)

	assert loose == [], f"these colours belong to no theme: {loose}"


def test_every_colour_is_named_once_and_read_somewhere () -> None:
	"""A colour written into a rule is a colour the theme cannot reach, and a
	colour named and never read is where the next one goes."""

	style = (superintendent.service.CLIENT_DIR / "style.css").read_text(encoding="utf-8")

	defined = set(re.findall(r"^\t(--[a-z-]+):\s*(?:light-dark|rgba?\(|#)", style, re.MULTILINE))
	used = set(re.findall(r"var\((--[a-z-]+)\)", style))

	assert defined - used == set(), f"named but never read: {sorted(defined - used)}"


def test_the_client_speaks_the_contract_python_does () -> None:
	"""The version is written in both languages and cannot be shared between
	them, so the only thing keeping them together is this."""

	source = (superintendent.service.CLIENT_DIR / "app.js").read_text(encoding="utf-8")

	# Both spellings, so moving the literal into a constant cannot make this
	# test pass by finding nothing — an empty set would otherwise equal an empty
	# set and say the two languages agree about nothing at all.
	spoken = set(re.findall(r'contract: "([^"]+)"', source)) \
		| set(re.findall(r'CONTRACT = "([^"]+)"', source))

	assert spoken, "the client names no contract version anywhere"

	assert spoken == {superintendent.protocol.CONTRACT_VERSION}, (
		f"the client says {spoken} and Python says {superintendent.protocol.CONTRACT_VERSION!r}")


def test_the_page_asks_for_the_assets_the_service_stamps () -> None:
	"""The stamping rewrites two literal URLs. If the page ever spells one
	differently the rewrite silently stops happening, and the caching guarantee
	goes with it."""

	markup = (superintendent.service.CLIENT_DIR / "index.html").read_text(encoding="utf-8")

	for asset in ("/client/style.css", "/client/app.js"):
		assert f'"{asset}"' in markup, f"{asset} is not spelled the way the service rewrites it"


def test_the_gap_between_cells_is_the_same_number_in_both_languages () -> None:
	"""The lattice is arithmetic in JavaScript and layout in CSS, and the two
	only agree because they use the same gap. Nothing else would notice."""

	source = (superintendent.service.CLIENT_DIR / "app.js").read_text(encoding="utf-8")
	styles = (superintendent.service.CLIENT_DIR / "style.css").read_text(encoding="utf-8")

	in_script = next(line for line in source.splitlines() if line.startswith("const GAP = "))
	in_styles = next(line for line in styles.splitlines() if line.strip().startswith("--gap:"))

	assert in_script.split("=")[1].strip(" ;") == in_styles.split(":")[1].strip(" ;").removesuffix("px")


def test_both_languages_agree_about_what_a_contract_gap_is () -> None:
	"""There are two implementations of one rule, and this is what holds them
	together.

	**The duplication is deliberate** and `app.js` carries the argument: the
	obvious design has the service compare the two versions — it knows both —
	and send the verdict.  That fails in precisely the case worth catching, a
	panel *newer* than the service, because the service is then by definition too
	old to have been taught to send it.  So the new half has to be able to work
	it out alone.

	Which leaves the same hazard this project keeps meeting: both halves correct
	by their own tests and wrong together.  So the client's own function is
	pulled out of the file and run, and its answers are compared with Python's
	over the same table — including the ones nobody would think to write twice.
	"""

	node = _node()

	if node is None:
		pytest.skip("no JavaScript engine on this machine")

	source = (superintendent.service.CLIENT_DIR / "app.js").read_text(encoding="utf-8")

	spoken = re.search(r'^const CONTRACT = "([^"]+)";$', source, re.MULTILINE)
	assert spoken, "the client no longer names a contract version in one place"

	# Sliced rather than imported: `app.js` is a module that reaches for the DOM
	# as it loads, so it cannot be evaluated here at all. The slice is bounded by
	# the closing `};` of the arrow function and asserted to contain it, because
	# a slice that silently caught nothing would compare nothing and pass.
	start = source.index("const contractGap = (spoken) => {")
	end = source.index("\n};\n", start)
	sliced = source[start:end + 4]

	assert sliced.count("return") >= 4, f"the slice did not catch the whole function: {sliced!r}"

	cases = ["1.0.0", "9.0.0", "", "banana", "1.17", "1.17.0.1", "1.-1.0",
	         spoken.group(1), "0.0.0", "1.99.99", "10.0.0"]

	major, minor, patch = (int(one) for one in spoken.group(1).split("."))
	cases += [f"{major}.{minor + 1}.0", f"{major}.{minor}.{patch + 1}",
	          f"{major + 1}.0.0", f"{major}.{minor}.{patch}"]

	driver = (f'const CONTRACT = {json.dumps(spoken.group(1))};\n'
	          f"{sliced}\n"
	          f"const cases = {json.dumps(cases)};\n"
	          "console.log(JSON.stringify(cases.map(contractGap)));\n"
	          # `null` and a number are what a missing or malformed field looks
	          # like, and neither can be written into a JSON list of strings.
	          "console.log(JSON.stringify([contractGap(null), contractGap(undefined),"
	          " contractGap(5)]));\n")

	run = subprocess.run([str(node), "--input-type=module", "-"], input=driver,
	                     capture_output=True, text=True, timeout=30)

	assert run.returncode == 0, f"the client's own function would not run: {run.stderr}"

	said, odd = (json.loads(line) for line in run.stdout.strip().splitlines())

	assert said == [superintendent.protocol.contract_gap(one) for one in cases], (
		f"the two languages disagree: JavaScript said {said}")

	assert odd == [superintendent.protocol.contract_gap(one) for one in (None, None, 5)]
