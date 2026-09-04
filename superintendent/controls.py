"""What the service understands about the controls an app declares.

The service knows control *kinds* — what a step grid is, and how a value
reaches a cell of one.  It knows nothing about what any particular grid is
for: the rows are names the app chose, and what they mean to a drum machine
somewhere is the app's business and the composition file's.  That separation is
the rule in this project's CLAUDE.md and in Subroutine #1465.
"""

import typing


STEP_GRID = "step_grid"
"""A grid of rows against steps, where a cell is present or absent."""


class ControlError (Exception):
	"""A path or a value that does not name a cell of a declared control."""


def parse_path (path: str) -> tuple[str, str, int]:
	"""Split a cell's address into the control, the row and the step it names.

	Addresses look like ``grid/kick/4`` — the control an app declared, one of
	its rows, and the step within it.
	"""

	parts = path.split("/")

	if len(parts) != 3:
		raise ControlError(f"{path!r} does not name a cell as control/row/step")

	control, row, step = parts

	if not step.isdigit():
		raise ControlError(f"{path!r} does not end in a step number")

	return control, row, int(step)


def apply_change (state: dict[str, typing.Any], controls: dict[str, typing.Any], path: str, value: typing.Any) -> None:
	"""Write a cell's value into an app's state, in place.

	The state this keeps is the service's copy of what the app holds, so that a
	panel arriving late is sent the grid as it stands without waking the app for
	it.  The app remains the authority: this is only ever called for a change the
	app has already applied and reported.
	"""

	control, row, step = parse_path(path)

	declaration = controls.get(control)

	if declaration is None:
		raise ControlError(f"{path!r} names {control!r}, which this app did not declare")

	if declaration.get("type") != STEP_GRID:
		raise ControlError(f"{control!r} is a {declaration.get('type')!r}, which carries no cells")

	if row not in declaration.get("rows", []):
		raise ControlError(f"{control!r} has no row named {row!r}")

	steps = declaration.get("steps", 0)

	if not 0 <= step < steps:
		raise ControlError(f"step {step} is outside {control!r}, which is {steps} steps wide")

	_set_cell(state.setdefault(control, {}), row, step, bool(value))


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
