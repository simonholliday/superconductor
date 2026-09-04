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
		found = importlib.metadata.version("superintendent")

	except importlib.metadata.PackageNotFoundError:
		return None

	return None if found in UNKNOWN_VERSIONS else found


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

	digest = hashlib.sha256()
	found = False

	for path in sorted(p for p in directory.rglob("*") if p.is_file()):
		found = True

		# The name as well as the bytes, so a rename is a new build.
		digest.update(str(path.relative_to(directory)).encode("utf-8"))
		digest.update(path.read_bytes())

	return digest.hexdigest()[:BUILD_LENGTH] if found else None
