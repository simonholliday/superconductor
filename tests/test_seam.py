"""What the adapter puts on the wire, and what the service will accept from it.

**This file exists because both halves of that join were correct by their own
tests and wrong together.**  Clearing a grid sent the adapter's whole snapshot —
rows *and* the mute — down a path named ``control/rows``; the service refused the
frame because ``enabled`` is not a declared row, logged it as a warning and left
its copy of the pattern exactly as it was.  The music went quiet and every panel
went on showing a full grid.

The Python unit tests stopped at the adapter, the page tests stopped at the
outgoing frame, and nothing ran a value the adapter actually produces through the
service the adapter actually talks to.  So the rule here is one assertion, made
for every path a panel can send:

    after a change, the service's copy of a control equals the app's own.

If those two ever disagree, a panel that reloads sees something different from
one that stayed connected — which is this project's most persistent class of
defect, reported three times and found by hand each time.
"""

import typing

import pytest

import superconductor.controls
import superconductor.subsequence_adapter as adapter


class Composition:
	"""The little of a composition a grid uses, and nothing more."""

	def __init__ (self) -> None:
		"""An empty data store and nowhere to send events."""

		self.data: dict[str, typing.Any] = {}
		self.listeners: dict[str, typing.Any] = {}

	def on_event (self, name: str, callback: typing.Any) -> None:
		"""Register a callback the way the real composition does."""

		self.listeners[name] = callback


def _agree (control: typing.Any, rest: list[str], value: typing.Any) -> None:
	"""Cross the join once: apply, report, accept, compare.

	The service's copy starts where a real one does — from the declaration — so
	this is the whole round trip a panel depends on, with nothing in it that the
	running system does not do.
	"""

	name = control.name
	declared = {name: control.declaration()}
	held = {name: control.snapshot()}

	control.apply(rest, value)

	# What the app tells every panel and the service, which for a whole-grid
	# write is not what was asked for.
	wire = control.applied(rest, value)

	superconductor.controls.apply_change(held, declared, "/".join([name, *rest]), wire)

	assert held[name] == control.snapshot(), (
		f"after {rest!r} the service holds {held[name]!r} "
		f"and the app holds {control.snapshot()!r}")


def _steps () -> typing.Any:
	"""A two-row step grid with a pattern already in it."""

	composition = Composition()
	grid = adapter.StepGrid(
		composition, rows=["kick", "snare"], steps=8, beats=2,
		data_key="grid", name="grid")

	composition.data["grid"] = {"kick": [0, 4], "snare": [2]}

	return grid


def _notes () -> typing.Any:
	"""A three-row note grid with one note in it."""

	composition = Composition()
	grid = adapter.NoteGrid(
		composition, rows=["C2", "C#2", "D2"], steps=8, beats=2,
		data_key="bass", name="bass", voices=None)

	composition.data["bass"] = {"C2": {"0": {"length": 1, "velocity": 100}}}

	return grid


@pytest.mark.parametrize(("rest", "value"), [
	(["rows"], {}),
	(["rows"], {"kick": [1, 3, 5]}),
	(["rows"], {"kick": [4, 0, 4], "snare": []}),
	(["kick", "2"], True),
	(["kick", "0"], False),
	(["enabled"], False),
])
def test_a_step_grid_and_the_service_agree_after_every_write (
	rest: list[str], value: typing.Any) -> None:
	"""Every path the panel can send to a step grid, crossed.

	``rows`` with ``{}`` is the clear button, and it is the one that was broken:
	the wire carried the mute inside the rows, the service threw the whole frame
	away, and its copy stayed lit.
	"""

	_agree(_steps(), rest, value)


@pytest.mark.parametrize(("rest", "value"), [
	(["rows"], {}),
	(["rows"], {"C2": {"3": {"length": 2, "velocity": 90}}}),
	(["C#2", "5"], True),
	(["C2", "0"], False),
	(["enabled"], False),
])
def test_a_note_grid_and_the_service_agree_after_every_write (
	rest: list[str], value: typing.Any) -> None:
	"""The same crossing for a pitched pattern, whose cells carry a shape."""

	_agree(_notes(), rest, value)


def test_clearing_a_grid_leaves_the_mute_where_it_was () -> None:
	"""The mute is not one of the rows, so replacing the rows must not take it.

	Both sides had to be told: the service clears the whole state object to make
	a replacement a replacement, and the panel builds a fresh one from the frame.
	Either one dropping `enabled` would silence the switch on a reload only —
	the worst shape of disagreement, because the panel that asked still looks
	right.
	"""

	grid = _steps()

	grid.apply(["enabled"], False)
	assert grid.snapshot()["enabled"] is False

	_agree(grid, ["rows"], {})

	assert grid.snapshot()["enabled"] is False, "clearing the rows turned the grid back on"


CATALOGUE: list[dict[str, typing.Any]] = [
	{
		"name": "chord",
		"summary": "Sound several pitches together.",
		"partial": False,
		"parameters": [
			{"name": "pitches", "label": "pitches", "kind": "pitch", "multiple": True},
			{"name": "velocity", "label": "velocity", "kind": "range",
			 "min": 1, "max": 127, "default": 100},
		],
	},
]


def _stack () -> typing.Any:
	"""A stack with one chord generator on it, the shape #2150 was measured on."""

	recipe = adapter.Recipe(
		Composition(), catalogue=CATALOGUE, pitches=["C2", "E2", "G2"], name="recipe")

	recipe.apply(["layers"], [{"id": "a", "generator": "chord", "params": {}}])

	return recipe


def test_several_pitches_reach_the_service_as_the_app_holds_them () -> None:
	"""The new value shape of 1.15.0, across the join that keeps catching this.

	A list is the first parameter value that is neither a scalar nor a fixed pair,
	and the service copies it rather than keeping the caller's — so "equal" here
	is doing real work rather than comparing an object with itself.
	"""

	_agree(_stack(), ["a", "pitches"], ["G2", "C2"])


def test_a_pitch_pool_the_app_would_refuse_does_not_reach_the_service_either () -> None:
	"""Both halves say no, and this is the assertion that they say it together.

	The adapter is what the panel talks to and the service is what a reloading
	panel reads, so a value one accepts and the other refuses is exactly the
	disagreement this file exists to catch.
	"""

	stack = _stack()

	with pytest.raises(adapter.Refused):
		stack.apply(["a", "pitches"], ["C2", "F#9"])

	with pytest.raises(superconductor.controls.ControlError):
		superconductor.controls.apply_change(
			{"recipe": stack.snapshot()}, {"recipe": stack.declaration()},
			"recipe/a/pitches", ["C2", "F#9"])


class Reporting:
	"""A link that keeps what the app said without being asked."""

	def __init__ (self) -> None:
		"""Start with nothing said."""

		self.reported: list[tuple[str, typing.Any]] = []

	def report (self, path: str, value: typing.Any) -> None:
		"""Keep it, the way a real link would put it on the wire."""

		self.reported.append((path, value))


def test_a_transposed_grid_and_the_service_agree () -> None:
	"""**One press, three frames** — and `_agree` is deliberately not used.

	Transposing changes the offset, the row labels and which rows can sound, and
	the last two travel in their own right because they are a consequence of the
	first rather than part of it.  Anything that replays only the path the panel
	asked for leaves the service holding the offset with the *old* labels — which
	is a panel that reloads being told a pattern sounds at pitches it does not.

	The seam suite found exactly that on this change's first run, which is what
	it is for.
	"""

	grid = _notes()
	link = Reporting()
	grid.attach(typing.cast(typing.Any, link))
	grid.relabel = lambda row, semitones: None if semitones > 3 else f"{row}+{semitones}"

	declared = {grid.name: grid.declaration()}
	held = {grid.name: grid.snapshot()}

	grid.apply(["transpose"], 2)

	# Everything the app put on the wire, in the order it said it.
	superconductor.controls.apply_change(
		held, declared, f"{grid.name}/transpose", grid.applied(["transpose"], 2))

	for path, value in link.reported:
		superconductor.controls.apply_change(held, declared, path, value)

	assert held[grid.name] == grid.snapshot(), (
		f"the service holds {held[grid.name]!r} and the app holds {grid.snapshot()!r}")


def test_a_rows_write_no_longer_carries_off_whatever_sits_beside_them () -> None:
	"""The mute used to be saved and restored here by name.

	Which meant every per-grid field added afterwards had to be added beside it,
	and `transpose` would have been the first to go missing — silently, and only
	for a panel that reloaded.  Nothing is named now: a row is a row because the
	declaration says so, and everything else is kept.
	"""

	grid = _notes()
	declared = {grid.name: grid.declaration()}
	held = {grid.name: grid.snapshot()}

	for rest, value in ((["enabled"], False), (["transpose"], 7)):
		grid.apply(rest, value)
		superconductor.controls.apply_change(
			held, declared, "/".join([grid.name, *rest]), grid.applied(rest, value))

	# And now the clear that used to take them with it.
	grid.apply(["rows"], {})
	superconductor.controls.apply_change(
		held, declared, f"{grid.name}/rows", grid.applied(["rows"], {}))

	assert held[grid.name]["enabled"] is False, "clearing the grid took the mute away"
	assert held[grid.name]["transpose"] == 7, "clearing the grid took the transposition away"


def _settings () -> typing.Any:
	"""An instrument with one ordinary setting and one that holds nothing."""

	return adapter.Params(
		Composition(),
		parameters=[
			adapter.Parameter("glide", "switch", label="Glide"),
			adapter.Parameter("voicing", "action", label="Set voicing",
			                  options=[("one", "1"), ("four", "4")]),
		],
		data_key="moog", name="moog")


def test_an_action_reaches_the_service_by_not_reaching_it () -> None:
	"""The 1.16.0 kind, across the join that keeps catching this file's namesake.

	**Deliberately not written with `_agree`**, because the path is a different
	shape: `apply` reports that nothing changed, so `AppLink` emits no `changed`
	frame, so the service is never told at all. That *is* the mechanism, and
	asserting it is the only way to notice if it ever stops being true — an
	action that started emitting a change would have the service quietly
	remembering a setting nobody can read back, which is exactly what the kind
	exists to prevent (#2179).
	"""

	settings = _settings()
	declared = {"moog": settings.declaration()}
	held = {"moog": settings.snapshot()}

	assert settings.apply(["voicing"], "four") is False, (
		"an action reported a change, so the service would be told about one")

	# And if a frame ever did arrive by another route — an app reporting it, a
	# tool replaying a capture — the service still must not keep it.
	superconductor.controls.apply_change(held, declared, "moog/voicing", "four")

	assert held["moog"] == settings.snapshot()
	assert "voicing" not in held["moog"]


def test_an_ordinary_setting_beside_it_still_crosses_normally () -> None:
	"""So the test above is about the kind rather than about the control."""

	settings = _settings()

	_agree(settings, ["glide"], True)


def test_a_whole_grid_write_is_answered_with_rows_and_not_the_snapshot () -> None:
	"""The fault itself, named.

	`applied` answers the path that was written.  `control/rows` names the rows,
	so the mute must not ride along inside them — the service validates every key
	of that value against the declared row names and refuses the frame entire if
	one is not a row.
	"""

	for grid in (_steps(), _notes()):
		wire = grid.applied(["rows"], {})

		assert "enabled" not in wire, (
			f"{grid.name}'s whole-grid write carries the mute among its rows: {wire!r}")

		# And the service agrees, rather than this being true only by inspection.
		superconductor.controls.apply_change(
			{grid.name: grid.snapshot()}, {grid.name: grid.declaration()},
			f"{grid.name}/rows", wire)


RESHAPING_CATALOGUE: list[dict[str, typing.Any]] = [
	{
		"name": "euclidean", "summary": "A euclidean rhythm.", "partial": False,
		"parameters": [
			{"name": "pitch", "label": "pitch", "kind": "pitch"},
			{"name": "pulses", "label": "pulses", "kind": "number", "step": 1},
		],
	},
]

RESHAPERS: list[dict[str, typing.Any]] = [
	{
		"name": "swing", "summary": "Apply swing feel.", "partial": False,
		"parameters": [
			{"name": "percent", "label": "percent", "kind": "number", "default": 57.0},
			{"name": "strength", "label": "strength", "kind": "number",
			 "min": 0.0, "max": 1.0, "default": 1.0},
		],
	},
	{
		"name": "reverse", "summary": "Flip the pattern backwards.", "partial": False,
		"parameters": [],
	},
]


def _reshaping_stack () -> typing.Any:
	"""A stack that may both add and reshape."""

	return adapter.Recipe(
		Composition(), catalogue=RESHAPING_CATALOGUE, transforms=RESHAPERS,
		pitches=["kick", "snare"], builds="grid", data_key="stack", name="stack")


@pytest.mark.parametrize(("rest", "value"), [
	(["layers"], [{"id": "a", "kind": "transform", "transform": "swing", "params": {}}]),
	(["layers"], [{"id": "a", "kind": "transform", "transform": "reverse", "params": {}}]),
	(["layers"], [
		{"id": "a", "generator": "euclidean", "params": {"pitch": "kick", "pulses": 4}},
		{"id": "b", "kind": "transform", "transform": "swing", "params": {"percent": 62.0}},
	]),
])
def test_a_transform_layer_and_the_service_agree (
	rest: list[str], value: typing.Any) -> None:
	"""#2246, and this is the join that has been wrong four times before.

	A layer kind is declared in one place and accepted in another, and the two
	have drifted apart every time one of them grew: the service dropped a field
	its whitelist did not name, and a panel that reloaded saw something different
	from one that stayed connected.
	"""

	_agree(_reshaping_stack(), rest, value)


def test_moving_one_knob_of_a_transform_crosses_like_any_other () -> None:
	"""The parameter path is addressed by layer and name, and it has to find the
	transform's catalogue rather than the generators' — a lookup in the wrong
	list refuses a parameter that exists."""

	stack = _reshaping_stack()
	stack.apply(["layers"], [
		{"id": "a", "kind": "transform", "transform": "swing", "params": {}}])

	_agree(stack, ["a", "percent"], 64.0)


def test_a_transform_named_as_a_generator_is_refused_by_both () -> None:
	"""The two catalogues are two namespaces, and a name in the wrong field is a
	fault in the panel rather than something to be found helpfully.

	Refused on **both** sides deliberately: the service accepting what the app
	refuses is the seam failure this file was written for, and it has happened
	once already when `choices` was added to one side only.
	"""

	stack = _reshaping_stack()

	with pytest.raises(adapter.Refused):
		stack.apply(["layers"], [{"id": "a", "generator": "swing", "params": {}}])

	declared = {"stack": stack.declaration()}

	with pytest.raises(superconductor.controls.ControlError):
		superconductor.controls.apply_change(
			{"stack": stack.snapshot()}, declared, "stack/layers",
			[{"id": "a", "generator": "swing", "params": {}}])


# --- a rack of grids somebody made (#2226) -----------------------------------

def _rack () -> typing.Any:
	"""A rack over three voices, attached to nothing that sends."""

	class Nowhere:
		"""A link that holds controls and never speaks."""

		def __init__ (self) -> None:
			"""Nothing offered, nothing said."""

			self.controls: dict[str, typing.Any] = {}

		def redeclare (self) -> None:
			"""Say nothing, because there is nowhere to say it."""

	rack = adapter.GridRack(
		Composition(),
		make=lambda spec: adapter.StepGrid(
			Composition(), rows=spec["rows"], steps=spec["steps"],
			beats=spec["steps"] * 0.25,
			data_key=spec["name"], name=spec["name"]),
		rows=["kick", "snare", "hihat_1_closed"], steps=(1, 32),
		data_key="rack", name="rack")

	rack.attach(typing.cast(typing.Any, Nowhere()))

	return rack


@pytest.mark.parametrize("value", [
	[{"id": "a", "rows": ["snare"], "steps": 9}],
	[{"id": "a", "rows": ["kick", "snare"], "steps": 16, "title": "Fill"}],
	[{"id": "a", "rows": ["kick"], "steps": 4},
	 {"id": "b", "rows": ["snare"], "steps": 12}],
	[],
])
def test_a_rack_of_grids_and_the_service_agree (value: typing.Any) -> None:
	"""The fifth kind to cross this join, and the first whose entries become
	controls of their own (#2226).

	The service keeps the list and is never told that a grid on it will appear
	as a declared control — it does not need to be, because an app re-declaring
	is how it has always said its controls changed.  What has to agree is the
	list, and a field the service dropped would be a panel that reloaded seeing
	a grid of a different length from one that stayed connected.
	"""

	_agree(_rack(), ["grids"], value)


def test_a_rack_refuses_at_both_ends_or_at_neither () -> None:
	"""**Every kind offered has to be refused in the same places.**  The app
	checking something the service waves through is how the two come to hold
	different things — and this list is checked twice on purpose, because the
	app knows which rows exist and the service only knows the shape.
	"""

	rack = _rack()
	declared = {"rack": rack.declaration()}
	held: dict[str, typing.Any] = {"rack": rack.snapshot()}

	nameless = [{"rows": ["kick"], "steps": 8}]

	with pytest.raises(adapter.Refused):
		rack.apply(["grids"], nameless)

	with pytest.raises(superconductor.controls.ControlError):
		superconductor.controls.apply_change(held, declared, "rack/grids", nameless)

	twice = [{"id": "a", "rows": ["kick"], "steps": 8},
	         {"id": "a", "rows": ["snare"], "steps": 8}]

	with pytest.raises(adapter.Refused):
		rack.apply(["grids"], twice)

	with pytest.raises(superconductor.controls.ControlError):
		superconductor.controls.apply_change(held, declared, "rack/grids", twice)
