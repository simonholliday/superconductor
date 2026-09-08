"""Starting the service from a terminal.

There is no command line beyond this: the surface is the page on the panel and
the settings file.  What this does is bind a port and stay up.
"""

import argparse
import dataclasses
import logging
import pathlib
import socket

import uvicorn

import superconductor.config
import superconductor.service


def main (argv: list[str] | None = None) -> int:
	"""Start the service, and report plainly if it cannot start."""

	args = _parse_args(argv)

	logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s  %(message)s")

	try:
		config = superconductor.config.Config.load(args.config)

	except superconductor.config.ConfigError as error:
		print(f"superconductor: {error}")
		return 1

	config = dataclasses.replace(
		config,
		host=args.host if args.host is not None else config.host,
		port=args.port if args.port is not None else config.port,
	)

	for address in _addresses(config.host):
		print(f"Superconductor is serving the panel at http://{address}:{config.port}/")

	uvicorn.run(superconductor.service.build(config), host=config.host, port=config.port, log_level="warning")

	return 0


def _parse_args (argv: list[str] | None) -> argparse.Namespace:
	"""Read the few things that can be said on the command line."""

	parser = argparse.ArgumentParser(
		prog="superconductor", description="Serve the touchscreen control surface.")

	parser.add_argument(
		"--config", type=pathlib.Path, default=None,
		help="settings file; without one the defaults are used")
	parser.add_argument(
		"--host", default=None,
		help="address to listen on (default: every interface)")
	parser.add_argument(
		"--port", type=int, default=None,
		help=f"port to listen on (default: {superconductor.config.DEFAULT_PORT})")

	return parser.parse_args(argv)


def _addresses (host: str) -> list[str]:
	"""Every address a person could type into a panel to reach this.

	Binding every interface is the ordinary case, and printing "<this machine>"
	for it was honest and useless: somebody standing at a touchscreen needs a
	number.  The machine knows its own, so it says them.

	If they cannot be worked out — no network, an unusual resolver — the name of
	the machine is offered instead, which is at least something to try.
	"""

	if host not in ("0.0.0.0", "::"):
		return [host]

	try:
		# Which address this machine would use to reach the wider network, which
		# is the one a panel on the same network can reach it back on. Asking the
		# resolver for the machine's own name is the obvious way and the wrong
		# one: on a Debian-like system that answers 127.0.1.1, which is true and
		# useless. Nothing is sent — connecting a datagram socket only chooses a
		# route — and the address is in the range reserved for documentation.
		with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
			probe.connect(("192.0.2.1", 9))

			return [str(probe.getsockname()[0])]

	except OSError:
		return [socket.gethostname()]


if __name__ == "__main__":
	raise SystemExit(main())
