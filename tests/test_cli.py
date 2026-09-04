"""Starting the service from a terminal: what it reads and what it refuses."""

import pathlib

import superintendent.cli
import superintendent.config


def test_the_defaults_need_nothing_on_the_command_line () -> None:
	"""Running it with no arguments is a supported way to run it."""

	args = superintendent.cli._parse_args([])

	assert args.config is None
	assert args.host is None
	assert args.port is None


def test_a_port_given_on_the_command_line_is_read () -> None:
	"""And as a number, so a bad one fails at the boundary rather than at the bind."""

	args = superintendent.cli._parse_args(["--port", "9001", "--host", "127.0.0.1"])

	assert args.port == 9001
	assert args.host == "127.0.0.1"


def test_a_settings_file_that_cannot_be_used_stops_the_service (
	tmp_path: pathlib.Path, capsys: object) -> None:
	"""Rather than starting with settings nobody chose.

	It must not reach the bind: a service listening on the wrong port is worse
	than one that did not start.
	"""

	assert superintendent.cli.main(["--config", str(tmp_path / "absent.yaml")]) == 1


def test_the_error_says_what_is_wrong_with_the_file (tmp_path: pathlib.Path, capsys: object) -> None:
	"""The person running it has to be able to fix it from what is printed."""

	path = tmp_path / "config.yaml"
	path.write_text("port: 70000\n")

	assert superintendent.cli.main(["--config", str(path)]) == 1
	assert "port" in capsys.readouterr().out  # type: ignore[attr-defined]


def test_an_address_a_person_can_type_is_offered () -> None:
	"""Binding every interface has no single address, and says so."""

	assert superintendent.cli._reachable_host("192.168.0.146") == "192.168.0.146"
	assert "0.0.0.0" not in superintendent.cli._reachable_host("0.0.0.0")
