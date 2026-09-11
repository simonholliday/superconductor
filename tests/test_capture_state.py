"""Writing down what the rig holds, stamped with what the rig speaks.

`tools/capture_state.py` runs from the working tree and reads a service that may
be older than it — after a pull, always is.  What it stamps is what
`restore_state.py` reads to decide whether the file needs converting, so the
stamp has to be the service's word rather than the tool's (#2501).

Driven against a service of this file's own, which is the only way to have one
speaking an older contract on purpose.
"""

import asyncio
import importlib.util
import json
import pathlib
import tempfile
import typing

import websockets.asyncio.server

import superconductor.protocol

# The decorator that keeps an async test off the main thread's loop, which is
# Playwright's for the rest of the session once a page test has run.
import test_hub


# Bound to a name of its own because the rule is enforced by reading the line
# above every `async def test_` in this directory, and it looks for this exact
# spelling (`test_no_test_borrows_the_main_threads_event_loop`).
_on_a_loop_of_its_own = test_hub._on_a_loop_of_its_own


def _tool (name: str) -> typing.Any:
	"""One of the tools in `tools/`, imported as a module — which runs nothing."""

	spec = importlib.util.spec_from_file_location(name, f"tools/{name}.py")
	assert spec is not None and spec.loader is not None

	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)

	return module


async def _captured (where: pathlib.Path, contract: str | None) -> None:
	"""Run the tool against a service that says exactly what it is told to.

	The handler stays open after sending, because the tool reads until a second
	of quiet: a socket closed under it would raise rather than let it finish, and
	the service this is written against never closes one.
	"""

	async def serve (socket: typing.Any) -> None:
		"""Greet, say what is spoken, hand over one snapshot, and wait."""

		await socket.recv()

		if contract is not None:
			await socket.send(json.dumps(
				{"t": "service", "contract": contract, "version": None, "build": None}))

		await socket.send(json.dumps(
			{"t": "snapshot", "app": "subsequence", "state": {"grid": {"kick": [0, 4]}}}))

		await asyncio.sleep(1.5)

	async with websockets.asyncio.server.serve(serve, "127.0.0.1", 0) as server:
		port = server.sockets[0].getsockname()[1]

		await _tool("capture_state").main(url=f"ws://127.0.0.1:{port}/ws/panel", where=where)


@_on_a_loop_of_its_own
async def test_a_capture_is_stamped_with_the_contract_the_service_speaks () -> None:
	"""And not with the tool's own, which is the version of the checkout it runs
	from (#2501).

	Measured on the rig on 2026-09-11: a service on 1.29.0, captured from a tree
	on 1.30.0, came back stamped 1.30.0.  The stamp decides whether a restore
	converts the file, and the one conversion that exists moves a note's position
	and length from steps into positions — so a capture claiming to be newer than
	the service it read is a bar folded into its own first sixth, with nothing to
	say so.
	"""

	with tempfile.TemporaryDirectory() as folder:
		where = pathlib.Path(folder) / "state.json"

		await _captured(where, "1.11.0")

		written = json.loads(where.read_text())

	assert written["contract"] == "1.11.0", "stamped with the tool's own contract"
	assert written["tool"] == superconductor.protocol.CONTRACT_VERSION, (
		"what read the rig is worth keeping, beside what the rig said")
	assert written["apps"]["subsequence"] == {"grid": {"kick": [0, 4]}}


@_on_a_loop_of_its_own
async def test_a_service_that_never_says_leaves_a_capture_the_restore_converts () -> None:
	"""A service too old to say which contract it speaks is exactly the file that
	needs converting, so a capture of one is read as unstamped rather than
	trusted.  Both halves are checked here because the two tools only agree
	about this file through its shape.
	"""

	with tempfile.TemporaryDirectory() as folder:
		where = pathlib.Path(folder) / "state.json"

		await _captured(where, None)

		written = json.loads(where.read_text())
		apps, stamped = _tool("restore_state")._read(where)

	assert written["contract"] is None
	assert stamped is False, "a capture naming no contract must be converted, not trusted"
	assert apps == {"subsequence": {"grid": {"kick": [0, 4]}}}, (
		"the apps are still found under the stamp")
