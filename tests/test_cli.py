"""Starting the service from a terminal: what it reads and what it refuses."""

import pathlib

import superconductor.cli
import superconductor.config


def test_the_defaults_need_nothing_on_the_command_line () -> None:
	"""Running it with no arguments is a supported way to run it."""

	args = superconductor.cli._parse_args([])

	assert args.config is None
	assert args.host is None
	assert args.port is None


def test_a_port_given_on_the_command_line_is_read () -> None:
	"""And as a number, so a bad one fails at the boundary rather than at the bind."""

	args = superconductor.cli._parse_args(["--port", "9001", "--host", "127.0.0.1"])

	assert args.port == 9001
	assert args.host == "127.0.0.1"


def test_a_settings_file_that_cannot_be_used_stops_the_service (
	tmp_path: pathlib.Path, capsys: object) -> None:
	"""Rather than starting with settings nobody chose.

	It must not reach the bind: a service listening on the wrong port is worse
	than one that did not start.
	"""

	assert superconductor.cli.main(["--config", str(tmp_path / "absent.yaml")]) == 1


def test_the_error_says_what_is_wrong_with_the_file (tmp_path: pathlib.Path, capsys: object) -> None:
	"""The person running it has to be able to fix it from what is printed."""

	path = tmp_path / "config.yaml"
	path.write_text("port: 70000\n")

	assert superconductor.cli.main(["--config", str(path)]) == 1
	assert "port" in capsys.readouterr().out  # type: ignore[attr-defined]


def test_a_listening_address_is_printed_as_something_a_person_can_type () -> None:
	"""Binding every interface is the ordinary case, and "<this machine>" was
	honest and useless — somebody standing at a panel needs a number."""

	for every in ("0.0.0.0", "::"):
		found = superconductor.cli._addresses(every)

		assert found, "something has to be offered"
		assert "<this machine>" not in found


def test_a_named_interface_is_printed_as_itself () -> None:
	"""Nothing is guessed when the person has already said which one."""

	assert superconductor.cli._addresses("127.0.0.1") == ["127.0.0.1"]
