"""Reading the service's settings, and the defaults it falls back on.

Every setting here has a default that works, so the service starts with no
configuration file at all.  What a file is *for* is the things only the person
running it knows: which address the panel reaches it on, and which page to
serve.
"""

import dataclasses
import pathlib
import typing

import yaml


DEFAULT_PORT = 8090
"""Clear of every port the three music apps use.  Subroutine #2020."""

DEFAULT_HOST = "0.0.0.0"
"""All interfaces, because the panel is a different machine on the network."""


class ConfigError (Exception):
	"""A configuration file that could not be used, named by what is wrong."""


@dataclasses.dataclass(frozen=True)
class Config:
	"""Everything the service needs to know before it starts listening."""

	host: str = DEFAULT_HOST
	port: int = DEFAULT_PORT
	page: str = "grid"

	@classmethod
	def load (cls, path: pathlib.Path | None) -> "Config":
		"""Read settings from a YAML file, falling back to the defaults it omits.

		A missing file is not an error when none was asked for: the defaults are
		a working service.  A file that was named and cannot be read is an
		error, because the person meant it to be used.
		"""

		if path is None:
			return cls()

		if not path.exists():
			raise ConfigError(f"no configuration file at {path}")

		try:
			raw = yaml.safe_load(path.read_text()) or {}

		except yaml.YAMLError as error:
			raise ConfigError(f"{path} is not readable as YAML: {error}") from error

		if not isinstance(raw, dict):
			raise ConfigError(f"{path} should hold a mapping of settings, not a {type(raw).__name__}")

		return cls._from_mapping(raw, path)

	@classmethod
	def _from_mapping (cls, raw: dict[str, typing.Any], path: pathlib.Path) -> "Config":
		"""Build a config from a mapping, refusing settings of the wrong shape."""

		unknown = set(raw) - {"host", "port", "page"}

		if unknown:
			raise ConfigError(f"{path} has settings this version does not know: {', '.join(sorted(unknown))}")

		port = raw.get("port", DEFAULT_PORT)

		if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
			raise ConfigError(f"{path}: 'port' should be a number from 1 to 65535, not {port!r}")

		return cls(host=str(raw.get("host", DEFAULT_HOST)), port=port, page=str(raw.get("page", "grid")))
