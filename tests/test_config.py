"""Settings, their defaults, and the errors a bad file produces."""

import pathlib

import pytest

import superintendent.config


def test_the_defaults_are_a_working_service () -> None:
	"""No file at all is a valid way to run this."""

	config = superintendent.config.Config.load(None)

	assert config.port == 8090
	assert config.host == "0.0.0.0"


def test_a_file_supplies_what_it_names_and_no_more (tmp_path: pathlib.Path) -> None:
	"""Settings the file omits keep their defaults."""

	path = tmp_path / "config.yaml"
	path.write_text("port: 9999\n")

	config = superintendent.config.Config.load(path)

	assert config.port == 9999
	assert config.host == "0.0.0.0"


def test_a_named_file_that_is_missing_is_an_error (tmp_path: pathlib.Path) -> None:
	"""Silently ignoring it would run with settings nobody chose."""

	with pytest.raises(superintendent.config.ConfigError):
		superintendent.config.Config.load(tmp_path / "absent.yaml")


def test_a_setting_this_version_does_not_know_is_named (tmp_path: pathlib.Path) -> None:
	"""A typo in a setting name is reported rather than ignored."""

	path = tmp_path / "config.yaml"
	path.write_text("prot: 8090\n")

	with pytest.raises(superintendent.config.ConfigError, match="prot"):
		superintendent.config.Config.load(path)


@pytest.mark.parametrize("value", ["0", "70000", "'eighty ninety'", "true"])
def test_a_port_that_is_not_a_port_is_refused (tmp_path: pathlib.Path, value: str) -> None:
	"""Refused at startup, rather than failing later at the bind."""

	path = tmp_path / "config.yaml"
	path.write_text(f"port: {value}\n")

	with pytest.raises(superintendent.config.ConfigError, match="port"):
		superintendent.config.Config.load(path)
