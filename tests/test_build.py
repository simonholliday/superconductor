"""What the service says it is, and how a stale page is caught.

A browser keeps whatever it loaded until someone reloads it. These cover the two
halves of noticing that: an identity the service can state, and a page that
cannot be served from a cache under a name the new one does not use (#2056).
"""

import pathlib

import starlette.testclient

import superintendent.build
import superintendent.config
import superintendent.protocol
import superintendent.service


def test_a_version_that_cannot_be_derived_is_not_reported_as_one () -> None:
	"""0.0.0 is the fallback for a tree with no history, and means "unknown"."""

	assert superintendent.build.version() not in superintendent.build.UNKNOWN_VERSIONS


def test_the_build_changes_when_any_client_file_does (tmp_path: pathlib.Path) -> None:
	"""Which is the whole mechanism: a hash that missed an edit would be worse
	than no hash at all, because it would assert freshness that was not there."""

	(tmp_path / "app.js").write_text("one")
	first = superintendent.build.client_build(tmp_path)

	(tmp_path / "app.js").write_text("two")
	assert superintendent.build.client_build(tmp_path) != first

	(tmp_path / "app.js").write_text("one")
	assert superintendent.build.client_build(tmp_path) == first, "and is stable when nothing changed"

	(tmp_path / "vendor").mkdir()
	(tmp_path / "vendor" / "library.js").write_text("")
	assert superintendent.build.client_build(tmp_path) != first, "including a file in a subdirectory"


def test_a_directory_with_no_client_in_it_has_no_build (tmp_path: pathlib.Path) -> None:
	"""Reported as nothing rather than as the hash of nothing, so a panel served
	by something else does not compare itself against a fiction."""

	assert superintendent.build.client_build(tmp_path / "absent") is None
	assert superintendent.build.client_build(tmp_path) is None


def test_the_panel_is_told_what_it_has_reached () -> None:
	"""Before the manifest, so the answer is there whatever else follows."""

	client = starlette.testclient.TestClient(superintendent.service.build(superintendent.config.Config()))

	with client.websocket_connect("/ws/panel") as panel:
		panel.send_json(superintendent.protocol.hello("panel-1", "grid"))

		frame = panel.receive_json()

	assert frame["t"] == "service"
	assert frame["version"] == superintendent.build.version()
	assert frame["build"] == superintendent.build.client_build(superintendent.service.CLIENT_DIR)
	assert frame["contract"] == superintendent.protocol.CONTRACT_VERSION


def test_the_page_names_its_assets_by_their_build () -> None:
	"""So a cached copy cannot answer for a new one: the URL it was kept under
	is not the URL the page now asks for."""

	client = starlette.testclient.TestClient(superintendent.service.build(superintendent.config.Config()))
	build = superintendent.build.client_build(superintendent.service.CLIENT_DIR)

	page = client.get("/")

	assert page.status_code == 200
	assert f"/client/app.js?v={build}" in page.text
	assert f"/client/style.css?v={build}" in page.text


def test_the_page_itself_is_never_stored () -> None:
	"""It is the file that names the others, so a cached one would name the
	wrong ones. It is also a few hundred bytes, so nothing is lost by saying so."""

	client = starlette.testclient.TestClient(superintendent.service.build(superintendent.config.Config()))

	assert client.get("/").headers["cache-control"] == "no-store"


def test_a_stamped_asset_is_still_served () -> None:
	"""The query is for the browser's cache, not for the router: the file is
	found by its path and the stamp is ignored."""

	client = starlette.testclient.TestClient(superintendent.service.build(superintendent.config.Config()))
	build = superintendent.build.client_build(superintendent.service.CLIENT_DIR)

	assert client.get(f"/client/app.js?v={build}").status_code == 200
