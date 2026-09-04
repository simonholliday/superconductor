"""What can be checked about the client without a browser.

The page is the half of the system with no runnable tests on this host, so the
two things that can be established cheaply are established here: that it parses,
and that the one value it has to keep in step with Python is in step.
"""

import pathlib
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
	"""A syntax error in the client is invisible until a browser loads it, and
	no browser runs on this host. This is the only guard between the two."""

	engine = _node()

	if engine is None:
		pytest.skip("no JavaScript engine on this host, not even Playwright's own")

	for script in sorted(superintendent.service.CLIENT_DIR.glob("*.js")):
		done = subprocess.run(
			[str(engine), "--check", str(script)], capture_output=True, text=True)

		assert done.returncode == 0, f"{script.name} does not parse:\n{done.stderr}"


def test_the_client_speaks_the_contract_python_does () -> None:
	"""The version is written in both languages and cannot be shared between
	them, so the only thing keeping them together is this."""

	source = (superintendent.service.CLIENT_DIR / "app.js").read_text(encoding="utf-8")
	spoken = {line.split('contract: "')[1].split('"')[0]
	          for line in source.splitlines() if 'contract: "' in line}

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
