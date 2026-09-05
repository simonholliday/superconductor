"""Run a composition with its logging turned on.

A composition configures no logging, so every `LOG.info` in the adapter — the
link connecting, a setting being asserted to an instrument, a refusal — goes
nowhere.  That is right for playing and wrong for diagnosing, and on 2026-09-04
it cost an evening: the panel's settings appeared dead, and the sentence saying
why was being written to a logger with no handler.

    python tools/play_loudly.py compositions/drm1_grid.py

Identical to running the composition directly, except that it talks.
"""

import logging
import pathlib
import runpy
import sys


def main () -> int:
	"""Configure logging, then run the composition as though it were __main__."""

	if len(sys.argv) < 2:
		print(f"usage: {pathlib.Path(sys.argv[0]).name} <composition.py>")
		return 1

	logging.basicConfig(
		level=logging.INFO,
		format="%(asctime)s %(levelname)-7s %(name)s  %(message)s")

	composition = pathlib.Path(sys.argv[1])

	if not composition.exists():
		print(f"no composition at {composition}")
		return 1

	# Argument vector as the composition would see it if it had been run itself.
	sys.argv = [str(composition), *sys.argv[2:]]

	runpy.run_path(str(composition), run_name="__main__")

	return 0


if __name__ == "__main__":
	raise SystemExit(main())
