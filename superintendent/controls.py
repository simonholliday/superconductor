"""What the service understands about the controls an app declares.

The service knows control *kinds* — what a step grid is, what a transport is,
and how a value reaches part of one.  It knows nothing about what any
particular control is for: the rows of a grid are names the app chose, and what
they mean to a drum machine somewhere is the app's business and the composition
file's.  That separation is the rule in this project's CLAUDE.md and in
Subroutine #1465.

A cell or a field is addressed by a path: the control's name, then whatever
that kind of control needs to identify one of its parts — ``grid/kick/4`` for a
cell, ``transport/bpm`` for a field.
"""

import typing


STEP_GRID = "step_grid"
"""A grid of rows against steps, where a cell is present or absent."""

TRANSPORT = "transport"
"""Named fields that say how the app is playing: silenced, tempo."""


class ControlError (Exception):
	"""A path or a value that does not name part of a declared control."""


def parse_path (path: str) -> tuple[str, list[str]]:
	"""Split an address into the control it names and the rest of the way there.

	How many parts follow the control's name depends on the kind of control it
	is, so that is checked where the kind is known rather than here.
	"""

	control, _, rest = path.partition("/")

	if not control or not rest:
		raise ControlError(f"{path!r} does not name a control and something within it")

	return control, rest.split("/")


def apply_change (state: dict[str, typing.Any], controls: dict[str, typing.Any], path: str, value: typing.Any) -> None:
	"""Write a value into an app's state, in place.

	The state this keeps is the service's copy of what the app holds, so that a
	panel arriving late is sent everything as it stands without waking the app
	for it.  The app remains the authority: this is only ever called for a
	change the app has already applied and reported.
	"""

	control, rest = parse_path(path)

	declaration = controls.get(control)

	if declaration is None:
		raise ControlError(f"{path!r} names {control!r}, which this app did not declare")

	kind = declaration.get("type")

	if kind == STEP_GRID:
		_apply_cell(state.setdefault(control, {}), declaration, rest, value, path)

	elif kind == TRANSPORT:
		_apply_field(state.setdefault(control, {}), declaration, rest, value, path)

	else:
		raise ControlError(f"{control!r} is a {kind!r}, which this version does not know")


def _apply_cell (
	grid: dict[str, typing.Any],
	declaration: dict[str, typing.Any],
	rest: list[str],
	value: typing.Any,
	path: str,
) -> None:
	"""Switch one cell of a step grid on or off."""

	if len(rest) != 2 or not rest[1].isdigit():
		raise ControlError(f"{path!r} does not name a cell as control/row/step")

	row, step = rest[0], int(rest[1])

	if row not in declaration.get("rows", []):
		raise ControlError(f"this grid has no row named {row!r}")

	steps = declaration.get("steps", 0)

	if not 0 <= step < steps:
		raise ControlError(f"step {step} is outside a grid {steps} steps wide")

	_set_cell(grid, row, step, bool(value))


def _apply_field (
	fields: dict[str, typing.Any],
	declaration: dict[str, typing.Any],
	rest: list[str],
	value: typing.Any,
	path: str,
) -> None:
	"""Write one named field of a transport."""

	if len(rest) != 1:
		raise ControlError(f"{path!r} does not name a field as control/field")

	field = rest[0]

	if field not in declaration.get("fields", []):
		raise ControlError(f"this transport has no field named {field!r}")

	fields[field] = value


def _set_cell (grid: dict[str, list[int]], row: str, step: int, present: bool) -> None:
	"""Add or remove one step in a row, keeping the row's steps in order.

	A row is held as the list of steps that sound, which is the shape #1914
	calls the index list and #2046 chose for the wire.
	"""

	steps = grid.setdefault(row, [])

	if present and step not in steps:
		steps.append(step)
		steps.sort()

	elif not present and step in steps:
		steps.remove(step)
