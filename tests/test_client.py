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
import typing

import pytest

import superconductor.protocol
import superconductor.service
import superconductor.subsequence_adapter

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

	for script in sorted(superconductor.service.CLIENT_DIR.glob("*.js")):
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


def _rules (name: str = "style.css") -> str:
	"""One of the client's files with its comments taken out.

	**Every static check here reads prose as though it were code otherwise**, and
	that is not hypothetical twice over: the colours guard has stripped comments
	since it was written, because an item number reads exactly like a short hex
	colour — and the sizes guard did not, so a comment explaining *why* the
	long-hand size property is used rather than the `font:` shorthand was itself
	reported as a size outside the scale (2026-09-10).

	The lesson is the guard's rather than the comment's: **a rule about code
	should be asked of code.**  A test that can be tripped by an explanation
	teaches people to stop writing them.
	"""

	held = (superconductor.service.CLIENT_DIR / name).read_text(encoding="utf-8")

	return re.sub(r"/\*.*?\*/", "", held, flags=re.DOTALL)


def test_every_size_in_the_stylesheet_comes_from_the_scale () -> None:
	"""Consistency has to be enforced rather than remembered.

	Eleven distinct font sizes had accumulated, of which exactly one scaled with
	the cell — so the pattern shrank when a person resized the grid and the
	controls beside it did not. A convention would drift again; this cannot.
	"""

	declared = re.findall(r"font-size:\s*([^;]+);", _rules())
	loose = [one.strip() for one in declared if not one.strip().startswith("var(--type-")]

	assert loose == [], f"these sizes are outside the scale: {loose}"


def test_the_scale_is_small_and_every_step_of_it_is_used () -> None:
	"""A scale nobody uses all of is a scale with a spare step in it, and a
	spare step is where the next inconsistency goes."""

	# Comments too, and for the sharper reason: a step *named* in prose and used
	# nowhere would satisfy this while being the spare step it exists to forbid.
	style = _rules()

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

	style = (superconductor.service.CLIENT_DIR / "style.css").read_text(encoding="utf-8")

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

	style = (superconductor.service.CLIENT_DIR / "style.css").read_text(encoding="utf-8")

	defined = set(re.findall(r"^\t(--[a-z-]+):\s*(?:light-dark|rgba?\(|#)", style, re.MULTILINE))
	used = set(re.findall(r"var\((--[a-z-]+)\)", style))

	assert defined - used == set(), f"named but never read: {sorted(defined - used)}"


def test_the_client_speaks_the_contract_python_does () -> None:
	"""The version is written in both languages and cannot be shared between
	them, so the only thing keeping them together is this."""

	source = (superconductor.service.CLIENT_DIR / "app.js").read_text(encoding="utf-8")

	# Both spellings, so moving the literal into a constant cannot make this
	# test pass by finding nothing — an empty set would otherwise equal an empty
	# set and say the two languages agree about nothing at all.
	spoken = set(re.findall(r'contract: "([^"]+)"', source)) \
		| set(re.findall(r'CONTRACT = "([^"]+)"', source))

	assert spoken, "the client names no contract version anywhere"

	assert spoken == {superconductor.protocol.CONTRACT_VERSION}, (
		f"the client says {spoken} and Python says {superconductor.protocol.CONTRACT_VERSION!r}")


def test_the_page_asks_for_the_assets_the_service_stamps () -> None:
	"""The stamping rewrites two literal URLs. If the page ever spells one
	differently the rewrite silently stops happening, and the caching guarantee
	goes with it."""

	markup = (superconductor.service.CLIENT_DIR / "index.html").read_text(encoding="utf-8")

	for asset in ("/client/style.css", "/client/app.js"):
		assert f'"{asset}"' in markup, f"{asset} is not spelled the way the service rewrites it"


def test_the_gap_between_cells_is_the_same_number_in_both_languages () -> None:
	"""The lattice is arithmetic in JavaScript and layout in CSS, and the two
	only agree because they use the same gap. Nothing else would notice."""

	source = (superconductor.service.CLIENT_DIR / "app.js").read_text(encoding="utf-8")
	styles = (superconductor.service.CLIENT_DIR / "style.css").read_text(encoding="utf-8")

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

	source = (superconductor.service.CLIENT_DIR / "app.js").read_text(encoding="utf-8")

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

	assert said == [superconductor.protocol.contract_gap(one) for one in cases], (
		f"the two languages disagree: JavaScript said {said}")

	assert odd == [superconductor.protocol.contract_gap(one) for one in (None, None, 5)]


def test_both_languages_name_the_same_kinds_of_control () -> None:
	"""One vocabulary, three places that have to agree about it (#2420).

	`subsequence_adapter` never imports `controls`, so the half that declares a
	kind and the half that keeps one had no word in common until the tuple moved
	into `protocol.py` — and the client holds a third copy, which no test read at
	all.  A kind added in Python and not in the client is a control the panel
	quietly stops drawing, with nothing failing anywhere.
	"""

	source = (superconductor.service.CLIENT_DIR / "app.js").read_text(encoding="utf-8")
	known = set(superconductor.protocol.CONTROL_KINDS)

	named = {}

	for held in ("GRIDS", "DRAWN", "BAR"):
		line = next((one for one in source.splitlines()
		             if one.startswith(f"const {held} = [")), None)

		assert line is not None, f"the client no longer names {held} in one place"

		named[held] = set(re.findall(r'"([a-z_]+)"', line))

		assert named[held], f"{held} lists nothing, so this would compare two empty sets"

	for held, names in named.items():
		assert names <= known, (
			f"the client's {held} names {sorted(names - known)}, which Python does not")

	# **Everything the panel can draw, against everything there is.**  A kind is
	# drawn as a block on a page or in the bar — the transport and the store live
	# in the header, with what is constant across pages (#2075, #2487) — so this
	# is an equality over the two, rather than a subset that would pass while a
	# kind went undrawn, and a kind may not be both.
	assert named["DRAWN"] | named["BAR"] == known, (
		f"the client draws {sorted(named['DRAWN'] | named['BAR'])} and Python has "
		f"{sorted(known)}")
	assert not named["DRAWN"] & named["BAR"], (
		f"{sorted(named['DRAWN'] & named['BAR'])} is drawn both as a block and in the bar")


def test_the_app_side_declares_exactly_the_kinds_the_service_knows () -> None:
	"""The other end of the same join, and the one that had no word at all.

	Every `Control` subclass carries the kind it declares itself as, and the
	service keeps a tuple of the kinds it will place.  A kind on one side and not
	the other is a control the service marks unsupported and a panel greys out —
	visible, but only once somebody builds a composition that uses it.
	"""

	subclasses = [one for one in vars(superconductor.subsequence_adapter).values()
	              if isinstance(one, type)
	              and issubclass(one, superconductor.subsequence_adapter.Control)
	              and one is not superconductor.subsequence_adapter.Control]

	assert subclasses, "no controls were found, so this compares two empty sets"

	declared = {one.kind for one in subclasses}

	assert "" not in declared, (
		"a control left `kind` at its default, so nothing can be patched from it "
		"and its declaration says it is nothing")

	assert declared == set(superconductor.protocol.CONTROL_KINDS), (
		f"the adapter declares {sorted(declared)} and the service knows "
		f"{sorted(superconductor.protocol.CONTROL_KINDS)}")


def test_both_languages_agree_about_a_parameter_that_opens_unset () -> None:
	"""The second cross-language twin, driven the way `contract_gap` is (#2420).

	`opensUnset` is `protocol.may_be_unset` restated in JavaScript, and until
	this nothing read it.  If the two drift, the panel offers an `auto` the
	service refuses, or withholds one it would accept — and the sharp edge is
	the one CLAUDE.md calls easy to get wrong from either end: the ``default``
	key has to be **present** rather than merely null when read, because an
	instrument's settings declare no default at all.

	**The two languages do not share that trap, and the difference decides what
	this test can catch.**  Dropping ``"default" in field`` from the JavaScript
	changes nothing, because ``undefined === null`` is already false there — so
	the absent-``default`` guard is a *Python*-side hazard only, where
	``field.get("default") is None`` is true of a key that is not there.  The
	JavaScript-side equivalent is **loose** equality: ``field.default == null``
	*is* true for ``undefined``, and that is the break to reach for when
	checking whether this test has teeth.  Measured 2026-09-10, after the
	strict-equality version was mistaken for one.
	"""

	node = _node()

	if node is None:
		pytest.skip("no JavaScript engine on this machine")

	source = (superconductor.service.CLIENT_DIR / "app.js").read_text(encoding="utf-8")

	# Sliced rather than imported, for the reason the contract-gap slice is: the
	# module reaches for the DOM as it loads. Asserted to have caught the body,
	# because a slice that silently caught nothing would compare nothing.
	start = source.index("function opensUnset (field) {")
	end = source.index("\n}\n", start)
	sliced = source[start:end + 3]

	assert "return" in sliced, f"the slice did not catch the function: {sliced!r}"

	cases: list[dict[str, typing.Any]] = [
		# The rule itself: not required, and an explicit null default.
		{"required": False, "default": None},
		{"required": True, "default": None},
		{"required": False, "default": 0},
		{"required": False, "default": ""},
		{"required": False, "default": False},

		# **An absent `default` is the case that matters**, and is what every
		# switch and dial on an instrument looks like.
		{"required": False},
		{},
		{"required": True},

		# Shapes a catalogue really produces, so this is not only about the flag.
		{"name": "root", "kind": "number", "required": False, "default": None},
		{"name": "steps", "kind": "number", "required": True, "min": 0},
		{"name": "pool", "kind": "choices", "role": "pitch", "required": False,
		 "default": None},
	]

	driver = (f"{sliced}\n"
	          f"const cases = {json.dumps(cases)};\n"
	          "console.log(JSON.stringify(cases.map(opensUnset)));\n")

	run = subprocess.run([str(node), "--input-type=module", "-"], input=driver,
	                     capture_output=True, text=True, timeout=30)

	assert run.returncode == 0, f"the client's own function would not run: {run.stderr}"

	said = json.loads(run.stdout.strip())

	assert said == [superconductor.protocol.may_be_unset(one) for one in cases], (
		f"the two languages disagree: JavaScript said {said}")


def test_the_client_alone_decides_which_letters_a_scene_offers () -> None:
	"""**A scene is the letters a page's grids have in common** (#2489, #2485 Q8).

	The first slice here with **no Python twin to compare against**, and that is
	the point rather than a gap: which grids share a page is a fact about an
	arrangement, and the service has no view about arrangements.  So the table
	carries its own answers.

	What it guards is the two decisions easiest to undo by accident.  **Fewer than
	two grids is no scene at all** — on a page carrying one grid with variants a
	scene letter would do exactly what that grid's own column does a few inches to
	the right, and a control that can only duplicate another is worse than none
	(#2107).  And **shared means the intersection**, in the first grid's order, so
	two grids agreeing about nothing draw no row rather than a row that cues half
	a page.
	"""

	node = _node()

	if node is None:
		pytest.skip("no JavaScript engine on this machine")

	source = (superconductor.service.CLIENT_DIR / "app.js").read_text(encoding="utf-8")

	# Sliced rather than imported, for the reason every slice here is: the module
	# reaches for the DOM as it loads.
	start = source.index("function scenesFor (lists) {")
	end = source.index("\n}\n", start)
	sliced = source[start:end + 3]

	assert "filter" in sliced, f"the slice did not catch the function: {sliced!r}"

	cases: list[list[list[str]]] = [
		# Nothing to cue: no grid at all, and the one-grid page that is the rule.
		[],
		[["A", "B", "C", "D"]],

		# The rig's own shape — the same four on every grid a page carries.
		[["A", "B", "C", "D"], ["A", "B", "C", "D"]],
		[["A", "B", "C", "D"], ["A", "B", "C", "D"], ["A", "B", "C", "D"]],

		# Shared means shared, and the order is the first grid's rather than
		# sorted: the ids are the composition's and their order is a statement.
		[["A", "B", "C"], ["B", "C", "D"]],
		[["D", "C", "B", "A"], ["A", "B"]],
		[["A", "B"], ["C", "D"]],
		[["A", "B", "C"], ["A", "B", "C"], ["C"]],

		# Names rather than letters, because a composition may declare names.
		[["verse", "chorus"], ["chorus", "bridge"]],
	]

	expected = [
		[],
		[],
		["A", "B", "C", "D"],
		["A", "B", "C", "D"],
		["B", "C"],
		["B", "A"],
		[],
		["C"],
		["chorus"],
	]

	driver = (f"{sliced}\n"
	          f"const cases = {json.dumps(cases)};\n"
	          "console.log(JSON.stringify(cases.map(scenesFor)));\n")

	run = subprocess.run([str(node), "--input-type=module", "-"], input=driver,
	                     capture_output=True, text=True, timeout=30)

	assert run.returncode == 0, f"the client's own function would not run: {run.stderr}"

	assert json.loads(run.stdout.strip()) == expected, (
		f"the panel would offer the wrong letters: {run.stdout.strip()}")


def test_a_panel_and_the_service_keep_the_same_note_for_the_same_frame () -> None:
	"""The third cross-language twin, and the one for a pitched grid's cells (#2503).

	The service's copy of a note grid and a panel's are both built from the
	frames the app sends, and a panel that reloads reads the first while one that
	stayed reads the second.  So for every frame the two must hold the same
	note, or the glass depends on when somebody last reloaded.

	**A placement is answered with its shape since 1.32.0**, because a note placed
	near the end of a pattern is shorter than the default — and a panel that
	rebuilt it from the declaration drew it off the end of the grid, which is
	what Simon found.  `withCell` is the panel's half, and `controls._note` —
	reached through `apply_change`, as the service reaches it — the other.
	"""

	node = _node()

	if node is None:
		pytest.skip("no JavaScript engine on this machine")

	source = (superconductor.service.CLIENT_DIR / "app.js").read_text(encoding="utf-8")

	# Sliced rather than imported, for the reason the others are: the module
	# reaches for the DOM as it loads.  Asserted to hold the note branch, because
	# a slice that caught only the step grid's half would compare nothing here.
	start = source.index("function withCell (rows, declared, cell, value) {")
	end = source.index("\n}\n", start)
	sliced = source[start:end + 3]

	assert "note_grid" in sliced, f"the slice did not catch the note branch: {sliced!r}"

	declared = {"type": "note_grid", "rows": ["C2", "D2"], "steps": 4, "divisions": 4,
	            "default_length": 4, "default_velocity": 100}
	opening = {"C2": {"0": {"length": 1, "velocity": 100}}}

	cases: list[tuple[list[str], typing.Any]] = [
		# Placed near the end, and answered with the shape the app gave it.
		(["D2", "14"], {"length": 2, "velocity": 100}),
		# Placed by an app older than 1.32.0, which answers only `true`.
		(["D2", "8"], True),
		(["C2", "0"], False),
		(["C2", "0", "length"], 3),
		(["C2", "0", "velocity"], 64),
	]

	driver = (f"{sliced}\n"
	          f"const declared = {json.dumps(declared)};\n"
	          f"const opening = {json.dumps(opening)};\n"
	          f"const cases = {json.dumps(cases)};\n"
	          "console.log(JSON.stringify(cases.map(([cell, value]) =>"
	          " withCell(opening, declared, cell, value))));\n")

	run = subprocess.run([str(node), "--input-type=module", "-"], input=driver,
	                     capture_output=True, text=True, timeout=30)

	assert run.returncode == 0, f"the client's own function would not run: {run.stderr}"

	said = json.loads(run.stdout.strip())

	for (cell, value), panel in zip(cases, said, strict=True):
		state = {"bass": json.loads(json.dumps(opening))}

		superconductor.controls.apply_change(
			state, {"bass": declared}, "/".join(["bass", *cell]), value)

		# A row whose last note went is dropped by the service and left empty by
		# the panel, and neither draws anything for it.
		kept = {row: notes for row, notes in state["bass"].items() if notes}
		drawn = {row: notes for row, notes in panel.items() if notes}

		assert drawn == kept, (
			f"after {cell} = {value!r} the panel holds {drawn} and the service {kept}")
