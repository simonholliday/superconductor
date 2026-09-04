"""A 16-step drum pattern for a Vermona DRM1 MkIV, played from the touchscreen.

This is the first thing Superintendent was built to do (Subroutine #2047).  Run
it beside the Superintendent service and the grid appears on the panel: tapping
a cell switches that step, and a step switched here appears on the glass.

**Everything about this particular studio lives in this file** — which MIDI
port the drum machine is on, which channel it listens to, and which of its
voices sits on which row.  The Superintendent package knows none of it, and
another rig is another copy of this file with different names at the top.

The grid itself is a plain dict on ``composition.data``: rows keyed by voice,
each holding the steps that sound.  The pattern builder reads it and the panel
writes it.  Nothing in the Subsequence package is changed to make this work.
"""

import typing

import subsequence
import subsequence.constants.durations
import subsequence.constants.instruments.vermona_drm1_drums as drm1

import superintendent.subsequence_adapter


# --- This rig -------------------------------------------------------------

MIDI_PORT = "*U6MIDI Pro Port 1*"
"""The interface the DRM1 is plugged into.

A pattern rather than the full name, because ALSA renumbers its clients when
the set of attached devices changes: this port was ``16:0`` before a reboot and
``20:0`` after one, and the exact name stopped matching.  Subsequence matches a
name with wildcards as a glob, so this survives the renumbering.
"""

DRUM_CHANNEL = 10
"""The channel the DRM1 is set to receive on."""

SERVICE_URL = "ws://127.0.0.1:8090/ws/app"
"""The Superintendent service, running on this machine."""

VELOCITY = 100
"""One fixed velocity per hit: a cell is on or off, with no accent (#2046)."""

ROWS = [
	"kick",
	"drum_1",
	"drum_2",
	"multi",
	"snare",
	"clap",
	"hihat_1_closed",
	"hihat_1_open",
	"hihat_2_closed",
	"hihat_2_open",
]
"""Every voice the DRM1 has, one to a row.

Ten rows rather than the machine's eight parts, because each hi-hat has a
separate closed and open note and a cell has no room to carry that choice
while it holds presence alone.  The names are the drum map's own, so nothing
new is invented for the wire.
"""

STEPS = 16
STEP_DURATION = subsequence.constants.durations.SIXTEENTH
BEATS = int(STEPS * STEP_DURATION)
"""Sixteen sixteenth-notes, which is one bar of four beats."""


# --- The pattern the composition starts with ------------------------------

OPENING_PATTERN = {
	"kick": [0, 6, 8, 14],
	"snare": [4, 12],
	"hihat_1_closed": [0, 2, 4, 6, 8, 10, 12, 14],
	"hihat_1_open": [7, 15],
	"clap": [12],
}
"""Something to hear on the first bar, and something to see on the glass.

Every row not named here starts empty.  This is here to be changed from the
panel, which is the whole point of the exercise.
"""


composition = subsequence.Composition(output_device=MIDI_PORT, bpm=120)

composition.data["grid"] = {row: sorted(OPENING_PATTERN.get(row, [])) for row in ROWS}
composition.data["layer"] = {row: [] for row in ROWS}
"""A second pattern over the same drum machine, empty until somebody fills it.

Two patterns driving one instrument belong on one page as stacked blocks rather
than on two pages, which Simon settled as Subroutine #1944.  This is that case
made real: both write the same ten voices on the same channel, and what you hear
is the two laid over each other.
"""


@composition.pattern(
	channel=DRUM_CHANNEL,
	steps=STEPS,
	step_duration=STEP_DURATION,
	drum_note_map=drm1.VERMONA_DRM1_DRUM_MAP,
	reschedule_lookahead=1 / 24,
)
def drums (p: typing.Any) -> None:
	"""Play whatever the grid holds when this bar is built.

	Rebuilt one pulse before each cycle rather than a beat before it, so the
	rebuild lands on a pulse that carries no note of its own and delays
	nothing (Subroutine #2041).  It also means a tap waits at most one pulse —
	about 20 ms at 120 BPM — before it can be heard, rather than a whole beat.
	"""

	_play(p, composition.data["grid"])


@composition.pattern(
	channel=DRUM_CHANNEL,
	steps=STEPS,
	step_duration=STEP_DURATION,
	drum_note_map=drm1.VERMONA_DRM1_DRUM_MAP,
	reschedule_lookahead=1 / 24,
)
def layer (p: typing.Any) -> None:
	"""A second pass over the same machine, built the same way as the first."""

	_play(p, composition.data["layer"])


def _play (p: typing.Any, grid: dict[str, list[int]]) -> None:
	"""Put whatever a grid holds onto the pattern being built."""

	for row in ROWS:
		steps = grid.get(row)

		if steps:
			p.hit_steps(row, list(steps), velocity=VELOCITY)


link = superintendent.subsequence_adapter.AppLink(
	composition,
	controls=[
		superintendent.subsequence_adapter.StepGrid(
			composition, rows=ROWS, steps=STEPS, beats=BEATS,
			data_key="grid", name="grid", title="DRM1 — pattern 1"),
		superintendent.subsequence_adapter.StepGrid(
			composition, rows=ROWS, steps=STEPS, beats=BEATS,
			data_key="layer", name="layer", title="DRM1 — pattern 2"),
		superintendent.subsequence_adapter.Transport(composition),
	],
	pages=[
		superintendent.subsequence_adapter.Page(
			"both", parts=["grid", "layer"], title="Both", columns=2),
		superintendent.subsequence_adapter.Page(
			"pattern_1", parts=["grid"], title="Pattern 1"),
		superintendent.subsequence_adapter.Page(
			"pattern_2", parts=["layer"], title="Pattern 2"),
	],
	url=SERVICE_URL,
)
"""Three views over the same two patterns.

Each pattern appears on two of them — once beside the other, side by side on a
wide panel, and once with the whole glass to itself — which is the case worth having: see how they play
together, then take one on its own to work on it closely.  Nothing keeps the
two views of a pattern in step, because nothing has to: both draw the grid the
composition holds.
"""


if __name__ == "__main__":
	link.start()
	composition.play()
