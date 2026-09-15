"""Putting a restarted rig's tempo and pause back, and believing the pause only from the clock.

The pattern store keeps what is made on the glass and neither the pause nor the
tempo (#2487), so a restarted rig comes back playing at whatever its composition
declares.  `tools/restore_transport.py` is the routine half of a restart (#2446):
it sends both from a capture, and a pause is proven by counting beats, because a
composition whose clock is held and one whose clock has not started read alike.

Driven against a service of this file's own, which is the only way to have a clock
that ignores a pause on purpose.
"""

import asyncio
import contextlib
import io
import json
import pathlib
import tempfile
import typing

import websockets.asyncio.server
import websockets.exceptions

import test_capture_state
import test_hub


# Bound to a name of its own because the rule is enforced by reading the line
# above every `async def test_` in this directory, and it looks for this exact
# spelling (`test_no_test_borrows_the_main_threads_event_loop`).
_on_a_loop_of_its_own = test_hub._on_a_loop_of_its_own


MANIFEST: dict[str, typing.Any] = {
	"subsequence": {
		"grid": {"type": "step_grid", "rows": ["kick"], "steps": 16},
		# Named for what it is on this rig and nothing else: the tool finds a
		# transport by its kind, as a panel does.
		"clock": {"type": "transport", "fields": ["paused", "bpm"], "tempo_range": [40.0, 240.0]},
	},
}


def _tool () -> typing.Any:
	"""The tool, imported as a module, which runs nothing."""

	return test_capture_state._tool("restore_transport")


def test_the_tempo_goes_back_before_the_pause () -> None:
	"""**Tempo first and pause last**, so the rig ends held whatever happens between
	the two; and only a field the transport declares, found by its kind rather than
	its name, because a composition names its own controls (#1465)."""

	held = {"subsequence": {"clock": {"paused": True, "bpm": 130.0}, "grid": {"kick": {"0": {}}}},
	        "absent": {"transport": {"paused": False, "bpm": 90.0}}}

	assert _tool()._asks(held, MANIFEST) == [
		("subsequence", "clock/bpm", 130.0), ("subsequence", "clock/paused", True)]

	# A transport that cannot pause is not asked to.
	tempo_only = {"subsequence": {**MANIFEST["subsequence"],
	                              "clock": {"type": "transport", "fields": ["bpm"]}}}

	assert _tool()._asks(held, tempo_only) == [("subsequence", "clock/bpm", 130.0)]


def test_a_capture_from_before_it_was_stamped_is_read_too () -> None:
	"""The bare mapping of app to state that captures held before 1.12.0."""

	with tempfile.TemporaryDirectory() as folder:
		where = pathlib.Path(folder) / "old.json"
		where.write_text(json.dumps({"subsequence": {"clock": {"paused": True}}}))

		assert _tool()._read(where) == {"subsequence": {"clock": {"paused": True}}}


async def _restored (
	held: dict[str, typing.Any],
	honours_the_pause: bool = True,
	refuses: str | None = None,
) -> tuple[int, list[str], str]:
	"""Run the tool against a service whose clock beats until it is paused — or not.

	Answers each set as an app answers a tap, refusing *refuses*, and beats every
	50 ms.  Says what the tool returned, every path it was asked for in order, and
	what it printed.
	"""

	asked: list[str] = []

	async def serve (socket: typing.Any) -> None:
		"""Greet with the manifest, then answer sets and beat."""

		await socket.recv()
		await socket.send(json.dumps({"t": "manifest", "contract": "1.42.0", "apps": MANIFEST}))

		held_clock = False

		async def beating () -> None:
			"""Beat until held, as a running composition does."""

			beat = 0

			while True:
				await asyncio.sleep(0.05)

				if not held_clock:
					beat += 1
					await socket.send(json.dumps({"t": "event", "app": "subsequence", "name": "beat",
					                              "beat": beat, "ts": 0.0, "interval": 0.05}))

		ticking = asyncio.create_task(beating())

		try:
			async for raw in socket:
				frame = json.loads(raw)

				if frame.get("t") != "set":
					continue

				asked.append(frame["path"])

				if frame["path"] == refuses:
					await socket.send(json.dumps({"t": "nack", "app": "subsequence", "path": frame["path"],
					                              "seq": frame["seq"], "reason": "not today"}))
					continue

				if frame["path"].endswith("/paused") and honours_the_pause:
					held_clock = bool(frame["v"])

				await socket.send(json.dumps({"t": "ack", "app": "subsequence", "path": frame["path"],
				                              "seq": frame["seq"], "ver": len(asked)}))

		except websockets.exceptions.ConnectionClosed:
			pass

		finally:
			ticking.cancel()

	with tempfile.TemporaryDirectory() as folder:
		where = pathlib.Path(folder) / "capture.json"
		where.write_text(json.dumps({"contract": "1.42.0", "apps": held}))

		async with websockets.asyncio.server.serve(serve, "127.0.0.1", 0) as server:
			port = server.sockets[0].getsockname()[1]
			printed = io.StringIO()

			with contextlib.redirect_stdout(printed):
				said = await _tool().main(url=f"ws://127.0.0.1:{port}/ws/panel", where=where, window=0.5)

	return said, asked, printed.getvalue()


@_on_a_loop_of_its_own
async def test_a_held_clock_is_believed_only_once_it_stops_beating () -> None:
	"""Both values go back, in order, and the tool counts no beats after the pause."""

	said, asked, printed = await _restored({"subsequence": {"clock": {"paused": True, "bpm": 130.0}}})

	assert asked == ["clock/bpm", "clock/paused"]
	assert said == 0, printed


@_on_a_loop_of_its_own
async def test_a_pause_the_clock_ignores_is_said_rather_than_believed () -> None:
	"""**Acknowledged is not held.**  The field reads `true` for a clock that took the
	pause and for one that did not, so only the beats can say; the tool fails."""

	said, _, printed = await _restored({"subsequence": {"clock": {"paused": True, "bpm": 130.0}}},
	                                   honours_the_pause=False)

	assert said == 1
	assert "beats arrived" in printed, printed


@_on_a_loop_of_its_own
async def test_a_playing_capture_expects_beats_and_a_refusal_is_said () -> None:
	"""A rig captured playing is checked the other way round, and a value the app
	would not take fails the run with the app's reason."""

	said, asked, printed = await _restored({"subsequence": {"clock": {"paused": False, "bpm": 300.0}}},
	                                       refuses="clock/bpm")

	assert asked == ["clock/bpm", "clock/paused"]
	assert said == 1
	assert "refused clock/bpm: not today" in printed, printed
	assert "beats arrived" not in printed and "no beats" not in printed, (
		"a clock captured playing and still playing was reported as wrong")
