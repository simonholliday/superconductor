"""The package imports, carries its docstring, and never writes its own version."""

import pathlib
import re
import tomllib

import superconductor


def test_package_imports () -> None:
	"""The package is importable and documented."""
	assert superconductor.__doc__ is not None


def _pyproject () -> dict:
	"""The project's own metadata, read rather than pattern-matched."""

	return tomllib.loads(
		pathlib.Path(__file__).resolve().parent.parent.joinpath("pyproject.toml")
		.read_text(encoding="utf-8"))


def test_the_version_comes_from_the_tag_and_is_written_nowhere () -> None:
	"""A version written down is a second copy of something git already holds,
	and two copies of one number is how they come to disagree — the rule this
	repository keeps hitting.  Here the disagreement is silent both ways round:
	tag without editing, or edit without tagging, and both are ordinary.

	**What makes deriving it safe is what happens with no tag.**  An untagged
	commit builds `0.0.1.devN+g<sha>`, and PyPI refuses any version carrying a
	local segment, so an untagged commit cannot be published by accident.
	Measured on 2026-09-08 by building both: `superconductor-0.0.1.dev143+gc07ebda2f`
	against `superconductor-0.1.0` at `v0.1.0`.
	"""

	held = _pyproject()

	assert "version" in held["project"].get("dynamic", []), (
		"the version is no longer declared dynamic, so something else supplies it")
	assert "version" not in held["project"], (
		"a version is written into [project], where the tag already says it")
	assert "setuptools_scm" in held.get("tool", {}), (
		"nothing derives the version from git any more")


def test_no_module_carries_a_version_of_its_own () -> None:
	"""The one accessor is `build.version()`, and it asks the installed
	distribution.  A literal anywhere else is a copy that outlives the release
	it was true for — and unlike the `pyproject.toml` case, nothing about
	building would notice.

	A derived `__version__` is fine and is not what this refuses; a quoted one
	is.
	"""

	written = re.compile(r"""__version__\s*=\s*['"]""")
	package = pathlib.Path(__file__).resolve().parent.parent / "superconductor"

	for path in sorted(package.rglob("*.py")):
		assert not written.search(path.read_text(encoding="utf-8")), (
			f"{path.name} writes a version literal; ask the distribution instead")
