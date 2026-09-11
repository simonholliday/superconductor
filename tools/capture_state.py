"""Take everything the panel can see and write it somewhere that survives.

A composition given a pattern store keeps what is made on the glass by itself
(#2487), so this is the safety net rather than the routine — the one copy that
is not kept beside the thing being restarted.  Run it before restarting
anything worth keeping.  Every variant of every grid is in what it writes,
because a snapshot carries them all (#2485).

    python tools/capture_state.py [where-to-write.json]

Defaults to /home/si/superconductor-state.json, which is on disk rather than in
tmpfs and so survives a reboot as well as a restart.
"""

import asyncio
import json
import pathlib
import sys
import time

import websockets.asyncio.client

import superconductor.protocol


URL = "ws://127.0.0.1:8090/ws/panel"
WHERE = pathlib.Path("/home/si/superconductor-state.json")
"""Where a capture is written when nothing else is named."""


async def main (url: str = URL, where: pathlib.Path = WHERE) -> None:
	"""Join as a panel, keep the first snapshot of every app, and write it out."""

	held: dict[str, dict] = {}
	spoken: str | None = None

	async with websockets.asyncio.client.connect(url) as socket:
		# Built rather than spelled out, so it cannot go stale. Three tools wrote
		# the contract by hand and drifted three separate ways — two said 1.1.0
		# and two said 1.5.0 against a current 1.13.0 — while CLAUDE.md's own
		# advice for spotting a stale process is to read the contract off a
		# socket. Nothing checks it today, which is exactly why it drifted.
		await socket.send(superconductor.protocol.encode(
			superconductor.protocol.hello("capture", None)))

		deadline = time.monotonic() + 5

		while time.monotonic() < deadline:
			try:
				frame = json.loads(await asyncio.wait_for(socket.recv(), timeout=1.0))

			except asyncio.TimeoutError:
				break

			if frame["t"] == "snapshot":
				held[frame["app"]] = frame["state"]

			# **What the service says it speaks, which is the stamp** (#2501).
			# It arrives with the greeting, before any snapshot.
			elif frame["t"] == "service" and isinstance(frame.get("contract"), str):
				spoken = frame["contract"]

	if spoken is None:
		print("the service never said which contract it speaks, so this capture is "
		      "stamped with none: restore_state.py will convert it as an old one")

	# **Stamped with the contract the service stated, not with this tool's**
	# (#2501).  What a note's two numbers are counted in changed at 1.12.0 and a
	# file cannot say which it means by looking at it: a note at 12 is step 12 in
	# one and two steps in the other, and both are patterns a person might have
	# played.  A file without the stamp is older than it, and restore_state.py
	# converts it (contract 1.12.0).
	#
	# **The tool's own contract is not the rig's.**  This runs from the working
	# tree, which after a pull is ahead of the service it is capturing — so
	# writing `CONTRACT_VERSION` here stamped a capture of a 1.29.0 service as
	# 1.30.0, measured on 2026-09-11.  A capture of a pre-1.12.0 service stamped
	# as new would be restored unconverted, folding every note into the first
	# sixth of its bar with nothing to say so.  It is kept beside the other under
	# `tool`, because knowing what read the rig is worth something and the two
	# are different facts.
	where.write_text(json.dumps(
		{"contract": spoken, "tool": superconductor.protocol.CONTRACT_VERSION, "apps": held},
		indent="\t") + "\n")

	for app, state in held.items():
		for control, value in state.items():
			if isinstance(value, dict) and isinstance(value.get("variants"), dict):
				# A grid with variants: what each holds, and which one plays.
				each = ", ".join(
					f"{name} {sum(1 for row in (one.get('rows') or {}).values() if row)}"
					for name, one in value["variants"].items() if isinstance(one, dict))
				print(f"  {app}/{control}: rows with something in them by variant — {each}; "
				      f"{value.get('playing')} playing")

			elif isinstance(value, dict):
				filled = sum(1 for held_row in value.values() if held_row)
				print(f"  {app}/{control}: {filled} rows or fields with something in them")

	print(f"written to {where}, taken under contract {spoken}")


# Nothing runs on import, so a test can drive `main` against a service of its own
# (#2465 gave restore_state.py the same guard, for the same reason).
if __name__ == "__main__":
	asyncio.run(main(where=pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else WHERE))
