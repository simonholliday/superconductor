"""What can be checked about the client without a browser.

The page is the half of the system with no runnable tests on this host, so the
two things that can be established cheaply are established here: that it parses,
and that the one value it has to keep in step with Python is in step.
"""

import pathlib
import re
import shutil
import subprocess

import pytest

import superintendent.protocol
import superintendent.service


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


def test_every_colour_in_the_stylesheet_is_a_pair () -> None:
	"""The defect a second theme block always has is a token defined in one
	theme and missing from the other, and the way to make that impossible is to
	have no second block: every colour is one `light-dark()` declaration.

	So a literal anywhere is either a colour that only works in one theme, or a
	colour that will be forgotten when the other one is touched.  Both are the
	same bug arriving at different times, and neither is caught by looking.
	"""

	style = (superintendent.service.CLIENT_DIR / "style.css").read_text(encoding="utf-8")

	# Comments carry item numbers, which look exactly like short hex colours;
	# and the two halves of a pair are of course literals, which is the point.
	code = re.sub(r"/\*.*?\*/", "", style, flags=re.DOTALL)
	code = re.sub(r"light-dark\((?:[^()]|\([^()]*\))*\)", "", code)
	loose = re.findall(r"#[0-9a-fA-F]{3,8}\b|\brgba?\([^)]*\)", code)

	assert loose == [], f"these colours are not a pair: {loose}"


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
