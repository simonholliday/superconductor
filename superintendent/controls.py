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

NOTE_GRID = "note_grid"
"""A grid whose cells are notes rather than presence alone.

A cell that is on carries a length in steps and a velocity, so a row is a pitch
and a note is a bar drawn from where it starts.  The service knows that much and
no more: which pitch a row names, and whether the instrument can sound two at
once, are the app's business as they are for every other kind.
"""


PARAMS = "params"
"""Named settings of an instrument: a switch, a number, a choice of names.

The three shapes an instrument's parameters come in, which between them cover
every control-change message a Moog Minitaur answers to (#2081) and, very
likely, most other instruments.

Deliberately carrying no MIDI in it at all.  A panel draws a switch; whether
that switch is control-change 65 on channel 6 is the composition's business and
never this package's, which is the same rule the rows of a grid follow.
"""

PARAMETER_KINDS = ("switch", "number", "choice", "range")
"""What a parameter can be, and so what a panel knows how to draw.

A range is two numbers with an order between them, held as ``[low, high]``.  It
is the shape an algorithm's parameters ask for that an instrument's did not: a
velocity given as ``(30, 50)`` means a fresh draw between the two on every hit,
which is most of what makes a generated layer sound played rather than typed.
"""


RECIPE = "recipe"
"""An ordered stack of generators that build a pattern, with their parameters.

A pattern is made by calling one generator after another, and the order is
musical rather than incidental: a fill told to skip where a note already sits
depends entirely on what ran before it.  So a recipe is a *list*, and the order
of that list is part of its value rather than a presentation detail.

Which generators exist, and what parameters each takes, is declared by the app
out of its own description of itself.  Nothing in this package names one, which
is the same rule that keeps drum voices and control-change numbers out of it.
"""


GENERATOR = "generator"
"""A contribution that makes its notes from parameters."""

PATTERN = "pattern"
"""A contribution that takes its notes from another grid.

A grid belonging to no instrument, routed into several, so that two synths can
share a bassline and each add notes of their own (#2108).  Simon settled that
this is the same mechanism as a generator rather than a second one — a
contribution is a contribution, and what makes its notes is its own business.

Which grids a stack may take from is declared by the app, for the same reason
the generators are: this package does not know that a grid exists, let alone
which of them belongs to an instrument and which belongs to nobody.
"""

CONTRIBUTIONS = (GENERATOR, PATTERN)
"""What a layer of a stack may be.

The second was named here before it existed, so that adding it would be an
addition rather than a rewrite.  It was.
"""


KINDS = (STEP_GRID, NOTE_GRID, PARAMS, RECIPE, TRANSPORT)
"""Every kind of control this version of the service understands.

An app may declare one this service has never heard of — it is older than the
app, or the app is newer than it.  That has to be visible rather than logged:
a control the service cannot place is one whose state it silently stops
keeping, and a panel then shows a face that stops moving for no stated reason.
"""


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

	elif kind == NOTE_GRID:
		_apply_note(state.setdefault(control, {}), declaration, rest, value, path)

	elif kind == PARAMS:
		_apply_parameter(state.setdefault(control, {}), declaration, rest, value, path)

	elif kind == RECIPE:
		_apply_recipe(state.setdefault(control, {}), declaration, rest, value, path)

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
	"""Switch one cell of a step grid on or off, or replace the whole grid.

	``control/rows`` carries the grid entire, which is how it is cleared and how
	one could later be pasted in.  A cell at a time would mean a hundred and
	sixty frames to empty a drum pattern, and a clear that is half-applied when
	something goes wrong is worse than one that is not applied at all.
	"""

	if rest == ["rows"]:
		# Checked entire before a single row is touched. Clearing first and
		# validating afterwards left the grid empty when the new one was
		# refused, which is the half-applied state this shape exists to avoid.
		kept = _readable_rows(declaration, value, path)

		grid.clear()
		grid.update(kept)
		return

	if len(rest) != 2 or not rest[1].isdigit():
		raise ControlError(f"{path!r} does not name a cell as control/row/step")

	row, step = rest[0], int(rest[1])

	if row not in declaration.get("rows", []):
		raise ControlError(f"this grid has no row named {row!r}")

	steps = declaration.get("steps", 0)

	if not 0 <= step < steps:
		raise ControlError(f"step {step} is outside a grid {steps} steps wide")

	_set_cell(grid, row, step, bool(value))


def _readable_rows (
	declaration: dict[str, typing.Any],
	value: typing.Any,
	path: str,
) -> dict[str, list[int]]:
	"""A whole step grid, checked before any of it replaces what is there."""

	if not isinstance(value, dict):
		raise ControlError(f"{path!r} takes a grid of rows, and {value!r} is not one")

	rows = declaration.get("rows", [])
	steps = declaration.get("steps", 0)
	kept: dict[str, list[int]] = {}

	for row, held in value.items():
		if row not in rows:
			raise ControlError(f"this grid has no row named {row!r}")

		if not isinstance(held, list):
			raise ControlError(f"row {row!r} takes a list of steps, and {held!r} is not one")

		for step in held:
			if isinstance(step, bool) or not isinstance(step, int):
				raise ControlError(f"a step is a whole number, and {step!r} is not one")

			if not 0 <= step < steps:
				raise ControlError(f"step {step} is outside a grid {steps} steps wide")

		if held:
			kept[row] = sorted(set(held))

	return kept


def _within (field: dict[str, typing.Any], value: float, name: str) -> None:
	"""Refuse a number outside whatever bounds were declared for it, if any.

	A generator's parameters often carry no bound at all — a duration in beats,
	a spacing, the time step of a chaotic system — and 27 of the generators
	Subsequence describes have at least one.  Inventing a range for those would
	be a guess with a MIDI accent: 0 to 127 is right for a control change and
	meaningless for a duration.  So where the app declared no bound none is
	checked, and the app is left to judge its own argument.
	"""

	low, high = field.get("min"), field.get("max")

	if low is not None and value < low:
		raise ControlError(f"{name!r} is not below {low}, and {value!r} is")

	if high is not None and value > high:
		raise ControlError(f"{name!r} is not above {high}, and {value!r} is")


def _apply_parameter (
	settings: dict[str, typing.Any],
	declaration: dict[str, typing.Any],
	rest: list[str],
	value: typing.Any,
	path: str,
) -> None:
	"""Write one named setting, refusing anything the app did not offer.

	Checked against the declaration rather than taken on trust, because this is
	the service's copy of what the app holds and a value it could not have
	reported would make the two disagree silently.
	"""

	if len(rest) != 1:
		raise ControlError(f"{path!r} does not name a setting as control/name")

	name = rest[0]
	field = next((one for one in declaration.get("fields", []) if one.get("name") == name), None)

	if field is None:
		raise ControlError(f"this app offers no setting called {name!r}")

	kind = field.get("kind")

	if kind == "switch":
		if not isinstance(value, bool):
			raise ControlError(f"{name!r} is a switch and takes true or false, not {value!r}")

	elif kind == "number":
		if isinstance(value, bool) or not isinstance(value, (int, float)):
			raise ControlError(f"{name!r} is a number, and {value!r} is not one")

		_within(field, value, name)

	elif kind == "choice":
		if value not in [one.get("value") for one in field.get("options", [])]:
			raise ControlError(f"{name!r} has no option called {value!r}")

	elif kind == "range":
		if (not isinstance(value, (list, tuple)) or len(value) != 2
				or any(isinstance(one, bool) or not isinstance(one, (int, float)) for one in value)):
			raise ControlError(f"{name!r} is a range and takes two numbers, not {value!r}")

		if value[0] > value[1]:
			raise ControlError(f"{name!r} is two numbers in order, and {value!r} is not")

		_within(field, value[0], name)
		_within(field, value[1], name)

		# Kept as a list whatever arrived, so the service's copy matches what
		# the same value becomes after a trip through JSON.  A tuple here and a
		# list on the wire would compare unequal and never say why.
		value = [value[0], value[1]]

	else:
		raise ControlError(f"{name!r} is a {kind!r}, which this version does not know")

	settings[name] = value


def _offered (declaration: dict[str, typing.Any], generator: typing.Any) -> dict[str, typing.Any]:
	"""What one generator of a declared catalogue takes, as a parameter declaration.

	Shaped so that a layer's parameters can go through ``_apply_parameter``
	unchanged: a generator's parameter and an instrument's setting are the same
	four shapes, and validating them twice in two places is how the two would
	come to disagree.
	"""

	if not isinstance(generator, str):
		raise ControlError(f"a layer names no generator, and {generator!r} is not one")

	for offered in declaration.get("generators", []):
		if offered.get("name") == generator:
			return {"fields": offered.get("parameters", [])}

	raise ControlError(f"this app offers no generator called {generator!r}")


def _apply_recipe (
	recipe: dict[str, typing.Any],
	declaration: dict[str, typing.Any],
	rest: list[str],
	value: typing.Any,
	path: str,
) -> None:
	"""Rewrite the whole stack, or change one parameter of one layer.

	Two shapes of address, and the length of the path says which.  ``recipe/
	layers`` carries the stack entire — which is how a layer is added, removed,
	bypassed or moved, since all four change the list rather than a value in it.
	``recipe/<layer>/<parameter>`` changes one parameter of one layer, which is
	what turning a knob does and is by far the commoner of the two.

	The split is worth the second shape.  A whole-stack set for every change
	would mean two people turning different knobs overwrote each other, while a
	structural change is rare and genuinely is about the list.
	"""

	if rest == ["layers"]:
		recipe["layers"] = _readable_layers(declaration, value, path)
		return

	if len(rest) != 2:
		raise ControlError(
			f"{path!r} names neither a stack as control/layers "
			f"nor a parameter as control/layer/name")

	layer = next((one for one in recipe.get("layers", []) if one.get("id") == rest[0]), None)

	if layer is None:
		raise ControlError(f"this stack has no layer called {rest[0]!r}")

	_apply_parameter(
		layer.setdefault("params", {}), _offered(declaration, layer.get("generator")),
		rest[1:], value, path)


def _readable_layers (
	declaration: dict[str, typing.Any],
	value: typing.Any,
	path: str,
) -> list[dict[str, typing.Any]]:
	"""Check a whole stack before any of it is kept.

	Every layer is validated and only then does the stack replace what was
	there, so a bad entry half way down cannot leave the service holding a
	stack that is partly old and partly new.

	Strict rather than forgiving, deliberately.  A panel asking to set a
	parameter no generator has is a fault in the panel and should be told so.
	Forgiveness belongs where a *stored* recipe is read back, which is a
	different path and the app's own business: a file written before a
	generator changed is somebody's work, and a panel's bad request is not.
	"""

	if not isinstance(value, list):
		raise ControlError(f"{path!r} takes a list of layers, and {value!r} is not one")

	layers: list[dict[str, typing.Any]] = []
	seen: set[str] = set()

	for entry in value:
		if not isinstance(entry, dict):
			raise ControlError(f"a layer is named by an object, and {entry!r} is not one")

		name = entry.get("id")

		if not isinstance(name, str) or not name:
			raise ControlError(f"a layer needs an id of its own, and {name!r} is not one")

		if name in seen:
			raise ControlError(f"two layers both call themselves {name!r}")

		seen.add(name)

		kind = entry.get("kind", GENERATOR)

		if kind not in CONTRIBUTIONS:
			raise ControlError(f"a layer is a {kind!r}, which this version does not know")

		layer: dict[str, typing.Any] = {
			"id": name,
			"kind": kind,
			"bypassed": bool(entry.get("bypassed", False)),
		}

		if kind == PATTERN:
			source = entry.get("source")

			if source not in (declaration.get("sources") or []):
				raise ControlError(f"this stack cannot take from a pattern called {source!r}")

			# A routed grid has nothing to tune: what it plays is what is drawn
			# on it, which is why the same mechanism serves both kinds without
			# either of them growing the other's furniture.
			layer["source"] = source
			layer["params"] = {}

		else:
			generator = entry.get("generator")
			offered = _offered(declaration, generator)
			held = entry.get("params")
			kept: dict[str, typing.Any] = {}

			for parameter, setting in (held if isinstance(held, dict) else {}).items():
				_apply_parameter(kept, offered, [parameter], setting, f"{path}/{name}/{parameter}")

			layer["generator"] = generator
			layer["params"] = kept

		# The number the app gave this layer, which is what a person reads on
		# its window. Held and never checked: it is the app's to hand out and
		# nothing here has an opinion about it.
		#
		# **Kept rather than rebuilt, because this list is a whitelist.** A field
		# the service does not name is dropped, and a dropped field is not
		# missing anywhere a panel can see until that panel reloads — until then
		# it is reading the `changed` frame, which carries what the app actually
		# said. So the fault hides: the numbers appeared, and came back without
		# them. Anything added to a layer has to be added here too.
		number = entry.get("index")

		if isinstance(number, int) and not isinstance(number, bool) and number > 0:
			layer["index"] = number

		layers.append(layer)

	return layers


NOTE_FIELDS = ("length", "velocity")
"""What a note carries besides being there at all."""


def _apply_note (
	grid: dict[str, typing.Any],
	declaration: dict[str, typing.Any],
	rest: list[str],
	value: typing.Any,
	path: str,
) -> None:
	"""Place, remove, or reshape one note of a note grid.

	Two shapes of address, and the length of the path says which: ``row/step``
	puts a note there or takes it away, and ``row/step/field`` changes one that
	is already there.  A field written to a cell holding no note is refused
	rather than quietly creating one, because a length without a note is not a
	state the app could have reported.
	"""

	if rest == ["rows"]:
		kept = _readable_notes(declaration, value, path)

		grid.clear()
		grid.update(kept)
		return

	if len(rest) not in (2, 3) or not rest[1].isdigit():
		raise ControlError(f"{path!r} does not name a note as control/row/step or control/row/step/field")

	row, step = rest[0], rest[1]

	if row not in declaration.get("rows", []):
		raise ControlError(f"this grid has no row named {row!r}")

	steps = declaration.get("steps", 0)

	if not 0 <= int(step) < steps:
		raise ControlError(f"step {step} is outside a grid {steps} steps wide")

	notes = grid.setdefault(row, {})

	if len(rest) == 2:
		if value:
			notes.setdefault(step, {
				"length": declaration.get("default_length", 1),
				"velocity": declaration.get("default_velocity", 100)})

		else:
			notes.pop(step, None)

			if not notes:
				grid.pop(row, None)

		return

	field = rest[2]

	if field not in NOTE_FIELDS:
		raise ControlError(f"a note has no field named {field!r}")

	if step not in notes:
		raise ControlError(f"{path!r} shapes a note that is not there")

	notes[step][field] = value


def _readable_notes (
	declaration: dict[str, typing.Any],
	value: typing.Any,
	path: str,
) -> dict[str, dict[str, typing.Any]]:
	"""A whole pitched grid, checked before any of it replaces what is there."""

	if not isinstance(value, dict):
		raise ControlError(f"{path!r} takes a grid of rows, and {value!r} is not one")

	rows = declaration.get("rows", [])
	steps = declaration.get("steps", 0)
	kept: dict[str, dict[str, typing.Any]] = {}

	for row, held in value.items():
		if row not in rows:
			raise ControlError(f"this grid has no row named {row!r}")

		if not isinstance(held, dict):
			raise ControlError(f"row {row!r} takes notes by step, and {held!r} does not")

		placed: dict[str, typing.Any] = {}

		for step, note in held.items():
			if not str(step).isdigit() or not 0 <= int(step) < steps:
				raise ControlError(f"step {step!r} is outside a grid {steps} steps wide")

			if not isinstance(note, dict):
				raise ControlError(f"a note is an object, and {note!r} is not one")

			placed[str(step)] = {
				field: note[field] for field in NOTE_FIELDS if field in note}

		if placed:
			kept[row] = placed

	return kept


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
