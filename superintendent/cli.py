"""Starting the service from a terminal.

There is no command line beyond this: the surface is the page on the panel and
the settings file.  What this does is bind a port and stay up.
"""

import argparse
import dataclasses
import logging
import pathlib

import uvicorn

import superintendent.config
import superintendent.service


def main (argv: list[str] | None = None) -> int:
	"""Start the service, and report plainly if it cannot start."""

	args = _parse_args(argv)

	logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s  %(message)s")

	try:
		config = superintendent.config.Config.load(args.config)

	except superintendent.config.ConfigError as error:
		print(f"superintendent: {error}")
		return 1

	config = dataclasses.replace(
		config,
		host=args.host if args.host is not None else config.host,
		port=args.port if args.port is not None else config.port,
	)

	print(f"Superintendent is serving the panel at http://{_reachable_host(config.host)}:{config.port}/")

	uvicorn.run(superintendent.service.build(config), host=config.host, port=config.port, log_level="warning")

	return 0


def _parse_args (argv: list[str] | None) -> argparse.Namespace:
	"""Read the few things that can be said on the command line."""

	parser = argparse.ArgumentParser(
		prog="superintendent", description="Serve the touchscreen control surface.")

	parser.add_argument(
		"--config", type=pathlib.Path, default=None,
		help="settings file; without one the defaults are used")
	parser.add_argument(
		"--host", default=None,
		help="address to listen on (default: every interface)")
	parser.add_argument(
		"--port", type=int, default=None,
		help=f"port to listen on (default: {superintendent.config.DEFAULT_PORT})")

	return parser.parse_args(argv)


def _reachable_host (host: str) -> str:
	"""Turn a listening address into something a person can type into a browser."""

	return "<this machine>" if host in ("0.0.0.0", "::") else host


if __name__ == "__main__":
	raise SystemExit(main())
