"""What is actually running, so a panel holding a stale page can say so.

A browser keeps whatever it loaded until someone reloads it, and nothing on the
glass says which page that was. During the proof of concept that produced the
only confusion worth a feature to end: the service was serving a newer page than
the panel was running, and the only symptom was behaviour that did not match the
code (#2056).

Two different questions are answered here, and they are not the same question.
The *version* says which release this is, and comes from the package metadata,
which is written when the package is installed and not when it runs — so it
describes the install rather than the files on disk. The *build* is a hash of
the client as it is on disk right now, so it changes the moment the page does.
Only the second can tell a panel that it is behind.
"""

import collections.abc
import hashlib
import importlib.metadata
import pathlib


UNKNOWN_VERSIONS = frozenset({"0.0.0"})
"""Versions that mean "could not be derived" rather than a release.

`pyproject.toml` names 0.0.0 as the fallback for a tree with no git history, so
printing it as though it were a release would be a small lie in the one place
that exists to be trusted.
"""

BUILD_LENGTH = 12
"""Enough hex to distinguish two builds by eye without filling the bar."""


def version () -> str | None:
	"""The installed version, or None when there is no honest answer.

	Note that this is the version at the time of installation. An editable
	install whose source has moved on since reports the older number and is not
	wrong to: that is what was installed. It is provenance, not freshness —
	`client_build` is the one that answers freshness.
	"""

	try:
		found = importlib.metadata.version("superconductor")

	except importlib.metadata.PackageNotFoundError:
		return None

	return None if found in UNKNOWN_VERSIONS else found


PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
"""Where this package's own source is, which is what `package_build` hashes."""


def _digest (
	directory: pathlib.Path,
	files: collections.abc.Iterable[pathlib.Path],
) -> str | None:
	"""One hash over *files*, named relative to *directory*, or None if there are none."""

	digest = hashlib.sha256()
	found = False

	for path in sorted(files):
		found = True

		# The name as well as the bytes, so a rename is a new build.
		digest.update(str(path.relative_to(directory)).encode("utf-8"))
		digest.update(path.read_bytes())

	return digest.hexdigest()[:BUILD_LENGTH] if found else None


def client_build (directory: pathlib.Path) -> str | None:
	"""A short hash of every file the page is made of, or None if there are none.

	Read on demand rather than once at startup. A service that hashed its client
	when it booted would keep insisting on that hash while the files underneath
	it changed, which is the fault this exists to catch rather than to commit.
	The client is a few files of a few kilobytes, so the cost of being right is
	not worth optimising away.
	"""

	if not directory.exists():
		return None

	return _digest(directory, (p for p in directory.rglob("*") if p.is_file()))


def package_build () -> str | None:
	"""A short hash of the Python in this package, as it is on disk right now.

	The mirror of `client_build` for the half that has no glass, and the answer
	to #2220: a **page** knows when it is behind because the build is stamped on
	its script URL, and a **service** is caught by the contract — but an *app*
	runs this package inside its own process, so a fix here moves no frame and
	the contract goes on agreeing while a composition executes code from before
	lunch. That cost a round trip on 2026-09-07, an hour after the contract
	check was built to stop exactly this.

	**Both callers take it once, as they start, and neither ever asks again.**
	Each then holds *the code I loaded*, and the two differing says one of them
	started before a change — which is the whole mechanism.

	**That is a weaker question than `client_build` asks, and deliberately so.**
	Reading on demand would name *which* half is behind rather than only that they
	differ, and `client_build` does exactly that for the page because it is
	answered on an HTTP request that can afford to take its time. This is answered
	inside a socket handler on the event loop, and this working tree is a CIFS
	mount with a live kernel bug in it: written that way the suite deadlocked
	outright, and on a rig the same read would take the whole service off the air
	— no panel, no taps — in order to check whether a composition needed
	restarting. A check that can stop the thing it is checking is not a check.

	`__pycache__` is left out because it is written by the act of importing, so
	including it would make a fresh checkout and an imported one report different
	builds for identical source. Only `.py` files count: the client has a build
	of its own and a compiled artefact is not source.
	"""

	if not PACKAGE_DIR.exists():
		return None

	return _digest(PACKAGE_DIR, (
		path for path in PACKAGE_DIR.rglob("*.py")
		if "__pycache__" not in path.parts))
