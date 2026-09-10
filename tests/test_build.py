"""What each half says it is, and how one running old code is caught.

A browser keeps whatever it loaded until someone reloads it, and a process keeps
whatever it imported until someone restarts it.  These cover all three halves of
noticing that: an identity the service can state, a page that cannot be served
from a cache under a name the new one does not use (#2056), and — the one that
had nothing at all — an **app** whose adapter was fixed hours ago and which is
still playing the code it started with (#2220).
"""

import logging
import pathlib
import threading
import time
import typing

import pytest
import starlette.testclient

import superconductor.build
import superconductor.config
import superconductor.protocol
import superconductor.service


def test_a_version_that_cannot_be_derived_is_not_reported_as_one () -> None:
	"""0.0.0 is the fallback for a tree with no history, and means "unknown"."""

	assert superconductor.build.version() not in superconductor.build.UNKNOWN_VERSIONS


def test_the_build_changes_when_any_client_file_does (tmp_path: pathlib.Path) -> None:
	"""Which is the whole mechanism: a hash that missed an edit would be worse
	than no hash at all, because it would assert freshness that was not there."""

	(tmp_path / "app.js").write_text("one")
	first = superconductor.build.client_build(tmp_path)

	(tmp_path / "app.js").write_text("two")
	assert superconductor.build.client_build(tmp_path) != first

	(tmp_path / "app.js").write_text("one")
	assert superconductor.build.client_build(tmp_path) == first, "and is stable when nothing changed"

	(tmp_path / "vendor").mkdir()
	(tmp_path / "vendor" / "library.js").write_text("")
	assert superconductor.build.client_build(tmp_path) != first, "including a file in a subdirectory"


def test_a_directory_with_no_client_in_it_has_no_build (tmp_path: pathlib.Path) -> None:
	"""Reported as nothing rather than as the hash of nothing, so a panel served
	by something else does not compare itself against a fiction."""

	assert superconductor.build.client_build(tmp_path / "absent") is None
	assert superconductor.build.client_build(tmp_path) is None


def _panel_greeting (client: starlette.testclient.TestClient) -> dict[str, typing.Any]:
	"""Say hello on a panel socket and hand back the frame that comes back first."""

	with client.websocket_connect("/ws/panel") as panel:
		panel.send_json(superconductor.protocol.hello("panel-1", "grid"))

		frame: dict[str, typing.Any] = panel.receive_json()

	return frame


def test_the_panel_is_told_what_it_has_reached () -> None:
	"""Before the manifest, so the answer is there whatever else follows.

	**The page is fetched first because fetching it is what fills the answer**
	(#2422): the socket reports the build the last page load stamped its assets
	with rather than hashing the client itself, and a browser cannot hold a
	socket without having fetched a page to open one from.
	"""

	client = starlette.testclient.TestClient(superconductor.service.build(superconductor.config.Config()))

	client.get("/")
	frame = _panel_greeting(client)

	assert frame["t"] == "service"
	assert frame["version"] == superconductor.build.version()
	assert frame["build"] == superconductor.build.client_build(superconductor.service.CLIENT_DIR)
	assert frame["contract"] == superconductor.protocol.CONTRACT_VERSION


def test_a_panel_that_did_not_fetch_the_page_is_told_nothing_and_then_told () -> None:
	"""A service restarted under a browser that did not reload has served no page
	in this process, so its greeting has no stamp to report.

	**Silence rather than a guess**, because a panel told nothing draws nothing
	about its build while one told a guess claims to be up to date.  And then the
	re-read fills it — off the loop, on a worker thread — and the panel is told
	without having to ask again.

	This was written up as an accepted cost of #2422 and turns out not to be one:
	the refresh that keeps *newer page available* reachable closes this as well.
	"""

	client = starlette.testclient.TestClient(superconductor.service.build(superconductor.config.Config()))

	with client.websocket_connect("/ws/panel") as panel:
		panel.send_json(superconductor.protocol.hello("panel-1", "grid"))

		assert panel.receive_json()["build"] is None, "the greeting guessed at a build"
		assert panel.receive_json()["t"] == "manifest"

		told = panel.receive_json()

	assert told["t"] == "service"
	assert told["build"] == superconductor.build.client_build(superconductor.service.CLIENT_DIR)


def test_a_panel_is_told_when_the_client_changes_under_the_service (
	monkeypatch: pytest.MonkeyPatch) -> None:
	"""#2164's second half, which reporting the stored stamp alone would kill.

	A page decides it is behind by comparing what it is told against the `?v=` it
	was **fetched under** — and that stamp is written by the same read that fills
	the stored answer.  So a service that could only ever report that one value
	would agree with every panel for ever, and *newer page available* would be
	unreachable: the two reads disagreeing is not a flaw in the mechanism, it is
	the mechanism.

	The re-read is what keeps them able to differ, and what it finds arrives as a
	`service` frame of its own — so a panel learns without saying hello again,
	which is better than what reading on the loop used to give it.

	The client is answered from a list rather than from the disk, so this asserts
	the plumbing rather than a hash, and writes nothing to a mount that stalls.
	"""

	answers = iter(["aaaaaaaaaaaa", "bbbbbbbbbbbb"])

	monkeypatch.setattr(
		superconductor.build, "client_build",
		lambda directory: next(answers, "bbbbbbbbbbbb"))

	client = starlette.testclient.TestClient(superconductor.service.build(superconductor.config.Config()))

	client.get("/")

	with client.websocket_connect("/ws/panel") as panel:
		panel.send_json(superconductor.protocol.hello("panel-1", "grid"))

		greeting = panel.receive_json()

		assert greeting["build"] == "aaaaaaaaaaaa", "the greeting did not report the stored stamp"
		assert panel.receive_json()["t"] == "manifest"

		told = panel.receive_json()

	assert told["t"] == "service"
	assert told["build"] == "bbbbbbbbbbbb", "the panel was never told the client had moved"


def test_the_page_names_its_assets_by_their_build () -> None:
	"""So a cached copy cannot answer for a new one: the URL it was kept under
	is not the URL the page now asks for."""

	client = starlette.testclient.TestClient(superconductor.service.build(superconductor.config.Config()))
	build = superconductor.build.client_build(superconductor.service.CLIENT_DIR)

	page = client.get("/")

	assert page.status_code == 200
	assert f"/client/app.js?v={build}" in page.text
	assert f"/client/style.css?v={build}" in page.text


def test_the_page_itself_is_never_stored () -> None:
	"""It is the file that names the others, so a cached one would name the
	wrong ones. It is also a few hundred bytes, so nothing is lost by saying so."""

	client = starlette.testclient.TestClient(superconductor.service.build(superconductor.config.Config()))

	assert client.get("/").headers["cache-control"] == "no-store"


def test_a_stamped_asset_is_still_served () -> None:
	"""The query is for the browser's cache, not for the router: the file is
	found by its path and the stamp is ignored."""

	client = starlette.testclient.TestClient(superconductor.service.build(superconductor.config.Config()))
	build = superconductor.build.client_build(superconductor.service.CLIENT_DIR)

	assert client.get(f"/client/app.js?v={build}").status_code == 200


# --- the third staleness, which nothing could see (#2220) --------------------

def _app_says (
	caplog: pytest.LogCaptureFixture,
	build: str | None,
	declarations: int = 1,
) -> list[str]:
	"""Let one app dial in claiming *build*, and hand back what the service said."""

	client = starlette.testclient.TestClient(
		superconductor.service.build(superconductor.config.Config()))

	with caplog.at_level(logging.WARNING, logger="superconductor.service"):
		with client.websocket_connect("/ws/app") as app:
			for _ in range(declarations):
				app.send_json(superconductor.protocol.declare(
					"subsequence", {}, {}, 1, build=build))

			# One more frame afterwards, so every declaration above has certainly
			# been read by the time the socket closes and the log is inspected.
			app.send_json(superconductor.protocol.event("subsequence", "beat", beat=1))

	return [record.getMessage() for record in caplog.records]


def test_the_package_build_changes_when_any_python_file_does (
	tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
	"""The same mechanism as the client's, asked about the half with no glass."""

	monkeypatch.setattr(superconductor.build, "PACKAGE_DIR", tmp_path)

	(tmp_path / "hub.py").write_text("one")
	first = superconductor.build.package_build()

	assert first is not None

	(tmp_path / "hub.py").write_text("two")
	assert superconductor.build.package_build() != first

	(tmp_path / "hub.py").write_text("one")
	assert superconductor.build.package_build() == first, "and is stable when nothing changed"


def test_importing_the_package_does_not_change_its_build (
	tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
	"""Or a fresh checkout and an imported one would report different builds for
	identical source, and the check would fire at every app that ever connected.

	The client's hash counts every file it finds, because everything under
	``client/`` is served.  This one counts source, because a compiled copy is
	written by the act of reading the source and says nothing else.
	"""

	monkeypatch.setattr(superconductor.build, "PACKAGE_DIR", tmp_path)

	(tmp_path / "hub.py").write_text("one")
	first = superconductor.build.package_build()

	(tmp_path / "__pycache__").mkdir()
	(tmp_path / "__pycache__" / "hub.cpython-313.pyc").write_bytes(b"compiled")

	assert superconductor.build.package_build() == first

	(tmp_path / "client").mkdir()
	(tmp_path / "client" / "app.js").write_text("a page")

	assert superconductor.build.package_build() == first, (
		"the page has a build of its own and is not this one")


def test_an_app_running_code_from_before_a_change_is_said_so (
	caplog: pytest.LogCaptureFixture) -> None:
	"""#2220: the one staleness a contract version cannot see.

	A page knows when it is behind and a service is caught by the contract.  An
	app is caught by neither, because a fix inside an adapter moves no frame —
	so both ends agree about the wire while one runs yesterday's Python.  That
	cost a round trip an hour after the contract check was built.
	"""

	said = " ".join(_app_says(caplog, "0000deadbeef"))

	assert "subsequence" in said, f"the app was not named: {said}"
	assert "0000deadbeef" in said, f"what the app loaded was not said: {said}"
	assert "restarting" in said, f"nothing said what to do about it: {said}"


def test_an_app_running_the_same_code_is_not_accused (
	caplog: pytest.LogCaptureFixture) -> None:
	"""Which is every app on a rig where the two halves share a filesystem, and
	is therefore the case that must stay silent or the warning becomes wallpaper."""

	assert _app_says(caplog, superconductor.build.package_build()) == []


def test_an_app_too_old_to_say_what_it_loaded_is_not_accused_either (
	caplog: pytest.LogCaptureFixture) -> None:
	"""Additive in both directions: an app that sends no build says nothing, and
	nothing is checked — which is what every app did before 1.20.0."""

	assert _app_says(caplog, None) == []


def test_nothing_reads_the_disk_while_a_socket_is_open (
	caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
	"""The rule this check was rewritten to obey, asserted rather than remembered.

	The first version compared what an app loaded against what was **on disk now**,
	which names *which* half is behind and is the better question.  It reads every
	`.py` file in the package — nine of them — inside the socket handler to ask it, and this working tree is a CIFS
	mount with a live kernel bug: the suite deadlocked outright — pytest waiting
	for ever on a frame the service never sent, both event loops idle — and on a
	rig the same read would have taken the whole service off the air, no panel and
	no taps, in order to check whether a composition wanted restarting.

	So both halves hash themselves as they import and compare two constants.  A
	`package_build` that explodes when called proves the socket path never calls
	it, which a comment could only claim.
	"""

	def refuse () -> str | None:
		"""Stand in for a read that hangs, which is what a CIFS read can do here."""

		raise AssertionError("the disk was read while a socket was being served")

	monkeypatch.setattr(superconductor.build, "package_build", refuse)

	assert _app_says(caplog, "0000deadbeef") != [], "the check did not run at all"


def test_greeting_a_panel_never_waits_for_the_disk (
	monkeypatch: pytest.MonkeyPatch) -> None:
	"""The other half of the rule above, which the test carrying its name never
	covered.

	That one patches `package_build` and drives `/ws/app`.  The **panel** path
	read the client *and* the package metadata on the same loop and sat outside
	it, so the rule was proved for one half of two — and the unproved half is the
	one a person is looking at.  It was not hypothetical: on 2026-09-10 a stalled
	read there left the service's main thread in `netfs_start_io_read` while the
	composition went on playing (#2422, #2432).

	**The stand-in hangs rather than explodes, and that is the whole point of
	it.**  An exploding one would assert that the client is never read, which is
	no longer true and should not be: it is re-read deliberately, on a worker
	thread.  What has to be true is that nothing *waits* for it — so this blocks
	the read for as long as the test allows and asks how long the greeting took.
	"""

	client = starlette.testclient.TestClient(superconductor.service.build(superconductor.config.Config()))
	stamped = superconductor.build.client_build(superconductor.service.CLIENT_DIR)

	client.get("/")

	wedged = threading.Event()

	def hang (*_: object) -> str | None:
		"""A read that does not come back, which is what a read here can do."""

		wedged.wait(timeout=30)

		return None

	monkeypatch.setattr(superconductor.build, "client_build", hang)
	monkeypatch.setattr(superconductor.build, "version", hang)

	try:
		with client.websocket_connect("/ws/panel") as panel:
			panel.send_json(superconductor.protocol.hello("panel-1", "grid"))

			began = time.monotonic()
			frame = panel.receive_json()
			took = time.monotonic() - began

			# Let the read finish before the socket closes, because the *close*
			# does wait for it — which is this harness rather than the service:
			# a running service never tears its loop down between greetings, and
			# what a stalled mount can delay there is its own shutdown.
			wedged.set()

	finally:
		wedged.set()

	# The timing first, because it is what this test is named for: asked the
	# other way round, a greeting that waited thirty seconds and then answered
	# `None` fails on the wrong line and reads as a wrong value rather than a
	# stalled one.
	assert took < 5, f"the greeting waited {took:.1f}s on a read that never came back"
	assert frame["build"] == stamped, "the greeting reported something other than the stored stamp"


def test_the_two_halves_are_asked_once_a_socket_and_not_once_a_declaration (
	caplog: pytest.LogCaptureFixture) -> None:
	"""Because a second declaration is how an app says its controls changed, and
	that happens on every block somebody drags — a layout save re-declares so the
	other panels learn the arrangement.

	Reading the package off a CIFS mount is 10 ms at the median and 25 at the
	worst, measured, so asking there would put that on the release of every drag.
	Nothing is lost by asking once: an app cannot stop being stale without
	restarting, and a restart is a new socket.
	"""

	assert len(_app_says(caplog, "0000deadbeef", declarations=3)) == 1
