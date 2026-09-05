"""A stack of generators: what it offers, what it keeps, and what it plays.

The panel picks a generator out of a catalogue the app describes itself with
(#2085), so nothing here names one either — the catalogue below is a stand-in
with the same shape Subsequence's own has, which is what keeps this test honest
about the rule it is testing.
"""

import typing

import pytest

import superintendent.subsequence_adapter as adapter


CATALOGUE: list[dict[str, typing.Any]] = [
	{
		"name": "euclidean",
		"summary": "Generate a Euclidean rhythm.",
		"partial": False,
		"parameters": [
			{"name": "pitch", "label": "pitch", "kind": "pitch"},
			{"name": "pulses", "label": "pulses", "kind": "number", "step": 1},
			{"name": "velocity", "label": "velocity", "kind": "range",
			 "min": 1, "max": 127, "default": 100},
		],
	},
	{
		"name": "evolve",
		"summary": "Loop a pitch sequence that gradually mutates.",
		"partial": False,
		"parameters": [
			{"name": "pitches", "label": "pitches", "kind": "pitch", "multiple": True},
			{"name": "drift", "label": "drift", "kind": "number",
			 "min": 0.0, "max": 1.0, "default": 0.0},
		],
	},
]

ROWS = ["kick", "snare", "hihat_1_closed"]


class Composition:
	"""Just the dict the real one carries, which is all a control touches."""

	def __init__ (self) -> None:
		"""Start with nothing in it."""

		self.data: dict[str, typing.Any] = {}


class Builder:
	"""A pattern builder that writes down what was called on it, in order."""

	def __init__ (self) -> None:
		"""Start with nothing played."""

		self.calls: list[tuple[str, dict[str, typing.Any]]] = []

	def euclidean (self, **arguments: typing.Any) -> None:
		"""Record a call."""

		self.calls.append(("euclidean", arguments))

	def evolve (self, **arguments: typing.Any) -> None:
		"""Record a call."""

		self.calls.append(("evolve", arguments))


def _recipe () -> tuple[adapter.Recipe, Composition]:
	"""A stack over a composition with three drum voices."""

	composition = Composition()

	return adapter.Recipe(composition, catalogue=CATALOGUE, pitches=ROWS,
	                      data_key="recipe", name="recipe"), composition


def test_a_pitch_becomes_the_voices_this_composition_actually_has () -> None:
	"""The app says *this is a pitch*; only the composition knows which ones.

	This is the join the whole arrangement rests on, so it is worth a test
	rather than a comment (#1465).
	"""

	recipe, _ = _recipe()
	euclidean = recipe.declaration()["generators"][0]
	pitch = euclidean["parameters"][0]

	assert pitch["kind"] == "choice"
	assert [one["value"] for one in pitch["options"]] == ROWS


def test_a_parameter_this_panel_cannot_draw_marks_its_generator_partial () -> None:
	"""A pool of pitches wants a multiple choice, which is not drawn yet.

	Saying the generator is not fully drivable is better than offering a
	control that cannot be completed — the same courtesy the app pays upstream.
	"""

	recipe, _ = _recipe()
	evolve = next(one for one in recipe.declaration()["generators"] if one["name"] == "evolve")

	assert evolve["partial"] is True
	assert [one["name"] for one in evolve["parameters"]] == ["drift"]


def test_a_composition_with_no_pitches_offers_no_pitch_parameter () -> None:
	"""Rather than an empty menu, which looks like a bug in the panel."""

	recipe = adapter.Recipe(Composition(), catalogue=CATALOGUE, pitches=[])
	euclidean = recipe.declaration()["generators"][0]

	assert euclidean["partial"] is True
	assert [one["name"] for one in euclidean["parameters"]] == ["pulses", "velocity"]


def test_a_new_layer_opens_at_the_generators_own_defaults () -> None:
	"""So the stack the panel draws and the call this makes are the same thing.

	A parameter left out would be filled in by the generator anyway, invisibly,
	and the glass would then be showing less than is playing.
	"""

	recipe, composition = _recipe()

	recipe.apply(["layers"], [{"id": "a", "generator": "euclidean", "params": {"pulses": 4}}])

	assert composition.data["recipe"]["layers"][0]["params"] == {
		"pitch": "kick", "pulses": 4, "velocity": [100, 100]}


def test_a_scalar_default_widens_into_a_range () -> None:
	"""``euclidean`` opens at velocity 100, not at a pair.

	A range that could not start from one number could not carry the default
	its own author chose, so both ends together means *exactly this*.
	"""

	recipe, _ = _recipe()

	recipe.apply(["layers"], [{"id": "a", "generator": "euclidean", "params": {}}])

	assert recipe.layers()[0]["params"]["velocity"] == [100, 100]


def test_one_knob_moves_without_disturbing_its_neighbours () -> None:
	"""Which is the whole reason a parameter has an address of its own."""

	recipe, _ = _recipe()

	recipe.apply(["layers"], [
		{"id": "a", "generator": "euclidean", "params": {"pulses": 3}},
		{"id": "b", "generator": "euclidean", "params": {"pulses": 5}},
	])
	recipe.apply(["a", "pulses"], 7)

	assert [layer["params"]["pulses"] for layer in recipe.layers()] == [7, 5]


def test_a_stack_plays_in_the_order_it_is_held () -> None:
	"""The order is musical content: a fill depends on what ran before it."""

	recipe, _ = _recipe()
	builder = Builder()

	recipe.apply(["layers"], [
		{"id": "a", "generator": "euclidean", "params": {"pitch": "kick", "pulses": 4}},
		{"id": "b", "generator": "euclidean", "params": {"pitch": "snare", "pulses": 2}},
	])
	recipe.build(builder)

	assert [call[1]["pitch"] for call in builder.calls] == ["kick", "snare"]


def test_a_bypassed_layer_is_not_played () -> None:
	"""Bypass is how a person hears what a layer was contributing."""

	recipe, _ = _recipe()
	builder = Builder()

	recipe.apply(["layers"], [
		{"id": "a", "generator": "euclidean", "bypassed": True, "params": {}},
		{"id": "b", "generator": "euclidean", "params": {}},
	])
	recipe.build(builder)

	assert [call[1]["pitch"] for call in builder.calls] == ["kick"]


def test_a_range_reaches_the_generator_as_a_pair_not_a_list () -> None:
	"""JSON has no tuple, and ``int | (int, int)`` reads a list as neither."""

	recipe, _ = _recipe()
	builder = Builder()

	recipe.apply(["layers"], [{"id": "a", "generator": "euclidean", "params": {}}])
	recipe.apply(["a", "velocity"], [30, 50])
	recipe.build(builder)

	assert builder.calls[0][1]["velocity"] == (30, 50)


def test_a_layer_that_will_not_run_is_skipped_rather_than_silencing_the_part () -> None:
	"""One bad layer must not cost the whole pattern its cycle, every bar.

	Subsequence survives a failing rebuild by design, but for an instrument
	that is the wrong failure: the part goes quiet with the reason in a log.
	"""

	recipe, composition = _recipe()

	class Breaks (Builder):
		def euclidean (self, **arguments: typing.Any) -> None:
			"""Fail the way a generator changed under a stored stack would."""

			raise TypeError("unexpected keyword argument")

	builder = Breaks()

	recipe.apply(["layers"], [
		{"id": "a", "generator": "euclidean", "params": {}},
		{"id": "b", "generator": "evolve", "params": {}},
	])
	recipe.build(builder)

	assert [call[0] for call in builder.calls] == ["evolve"]


def test_a_failing_layer_is_complained_about_once_not_once_a_bar (
	caplog: typing.Any) -> None:
	"""A pattern is rebuilt twice a second; a warning a cycle is a flood."""

	recipe, _ = _recipe()

	class Breaks (Builder):
		def euclidean (self, **arguments: typing.Any) -> None:
			"""Always fail."""

			raise ValueError("no")

	recipe.apply(["layers"], [{"id": "a", "generator": "euclidean", "params": {}}])

	with caplog.at_level("WARNING"):
		for _ in range(20):
			recipe.build(Breaks())

	assert len([one for one in caplog.records if "euclidean" in one.getMessage()]) == 1


@pytest.mark.parametrize("stack", [
	"not a list",
	[{"generator": "euclidean"}],                              # no id
	[{"id": "a", "generator": "invented"}],                    # no such generator
	[{"id": "a", "generator": "euclidean", "params": {"nope": 1}}],
	[{"id": "a", "generator": "euclidean", "params": {"velocity": [200, 300]}}],
	[{"id": "a", "generator": "euclidean"}, {"id": "a", "generator": "euclidean"}],
])
def test_a_stack_that_could_not_be_played_is_refused_with_a_reason (
	stack: typing.Any) -> None:
	"""The person who tapped is told, rather than watching a control not move."""

	recipe, _ = _recipe()

	with pytest.raises(adapter.Refused):
		recipe.apply(["layers"], stack)


def test_a_refused_stack_leaves_the_one_that_was_playing_alone () -> None:
	"""Checked entire before any of it is kept, so nothing is ever half-new."""

	recipe, _ = _recipe()

	recipe.apply(["layers"], [{"id": "a", "generator": "euclidean", "params": {}}])

	with pytest.raises(adapter.Refused):
		recipe.apply(["layers"], [
			{"id": "a", "generator": "euclidean", "params": {}},
			{"id": "b", "generator": "invented", "params": {}},
		])

	assert [layer["id"] for layer in recipe.layers()] == ["a"]


def test_setting_a_stack_to_what_it_already_holds_changes_nothing () -> None:
	"""An absolute set is re-sendable after a reconnect, so it must be idempotent."""

	recipe, _ = _recipe()
	stack = [{"id": "a", "generator": "euclidean", "params": {"pulses": 3}}]

	assert recipe.apply(["layers"], stack) is True
	assert recipe.apply(["layers"], stack) is False


UNBOUNDED: list[dict[str, typing.Any]] = [
	{
		"name": "euclidean",
		"summary": "Generate a Euclidean rhythm.",
		"partial": False,
		"parameters": [
			{"name": "pulses", "label": "pulses", "kind": "number", "step": 1},
			{"name": "duration", "label": "duration", "kind": "number", "default": 0.1},
		],
	},
]


def test_a_number_the_app_gave_no_bounds_for_gets_none_invented () -> None:
	"""Most of a generator's numbers have none, so a made-up range is the
	ordinary case rather than the rare one.

	A duration in beats and a control change have nothing in common, and 0 to
	127 is right for one of them.
	"""

	recipe = adapter.Recipe(Composition(), catalogue=UNBOUNDED, pitches=ROWS)
	duration = recipe.declaration()["generators"][0]["parameters"][1]

	assert "min" not in duration and "max" not in duration


def test_an_unbounded_number_accepts_what_the_generator_would () -> None:
	"""The app judges its own argument, and now clamps its own bounds."""

	recipe = adapter.Recipe(Composition(), catalogue=UNBOUNDED, pitches=ROWS)

	recipe.apply(["layers"], [{"id": "a", "generator": "euclidean", "params": {}}])
	recipe.apply(["a", "duration"], 4.0)

	assert recipe.layers()[0]["params"]["duration"] == 4.0


def test_a_composition_may_narrow_what_the_app_could_not_know () -> None:
	"""How many pulses make sense depends on how many steps the pattern has,
	and the pattern belongs to the composition rather than to the app."""

	recipe = adapter.Recipe(
		Composition(), catalogue=UNBOUNDED, pitches=ROWS, bounds={"pulses": (0, 16)})
	pulses = recipe.declaration()["generators"][0]["parameters"][0]

	assert (pulses["min"], pulses["max"]) == (0, 16)

	recipe.apply(["layers"], [{"id": "a", "generator": "euclidean", "params": {}}])

	with pytest.raises(adapter.Refused):
		recipe.apply(["a", "pulses"], 40)


def test_what_is_reported_is_what_was_kept_not_what_was_asked_for () -> None:
	"""A layer is stored with every parameter its generator has, filled from
	that generator's own defaults — so the request and the result differ here in
	a way they do nowhere else.

	Reporting the request would leave the service's copy, and every panel,
	holding a layer with nothing in it while the app played one that was full.
	"""

	recipe, _ = _recipe()
	asked = [{"id": "a", "generator": "euclidean", "params": {"pulses": 4}}]

	recipe.apply(["layers"], asked)

	reported = recipe.applied(["layers"], asked)

	assert reported[0]["params"] == {"pitch": "kick", "pulses": 4, "velocity": [100, 100]}
	assert reported == recipe.layers()


def test_a_parameter_reports_the_value_that_was_stored () -> None:
	"""Which for a range is a list, whatever shape it arrived in."""

	recipe, _ = _recipe()

	recipe.apply(["layers"], [{"id": "a", "generator": "euclidean", "params": {}}])
	recipe.apply(["a", "velocity"], (30, 50))

	assert recipe.applied(["a", "velocity"], (30, 50)) == [30, 50]


OPTIONAL: list[dict[str, typing.Any]] = [
	{
		"name": "ghost_fill",
		"summary": "Fill with probability-biased ghost notes.",
		"partial": False,
		"parameters": [
			{"name": "pitch", "label": "pitch", "kind": "pitch"},
			{"name": "density", "label": "density", "kind": "number",
			 "min": 0.0, "max": 1.0, "default": 0.3},
			{"name": "grid", "label": "grid", "kind": "number", "step": 1},
		],
	},
]


def test_a_parameter_the_generator_decides_for_itself_is_left_out () -> None:
	"""And filling it in silenced the layer while it looked perfectly set up.

	``grid`` has no default in the catalogue because its default is ``None`` —
	*use the pattern's own grid*.  A required parameter with no default arrives
	looking exactly the same, so filling both with a number meant handing
	``ghost_fill`` a grid of no steps, which places nothing and says nothing.
	"""

	recipe = adapter.Recipe(Composition(), catalogue=OPTIONAL, pitches=ROWS)

	recipe.apply(["layers"], [{"id": "a", "generator": "ghost_fill", "params": {}}])

	assert recipe.layers()[0]["params"] == {"pitch": "kick", "density": 0.3}


def test_a_parameter_the_generator_cannot_do_without_is_filled_in () -> None:
	"""Everything before the first defaulted parameter, which is how Python
	orders a signature and the only signal the catalogue carries."""

	recipe = adapter.Recipe(Composition(), catalogue=CATALOGUE, pitches=ROWS)

	recipe.apply(["layers"], [{"id": "a", "generator": "euclidean", "params": {}}])

	held = recipe.layers()[0]["params"]

	assert held["pitch"] == "kick", "a required choice takes its first option"
	assert held["pulses"] == 0, "a required number is filled rather than omitted"


def test_a_parameter_left_out_is_not_passed_to_the_generator () -> None:
	"""Leaving it out of the call is what tells the generator to decide."""

	recipe = adapter.Recipe(Composition(), catalogue=OPTIONAL, pitches=ROWS)
	builder = Builder()

	setattr(builder, "ghost_fill", lambda **arguments: builder.calls.append(("ghost_fill", arguments)))

	recipe.apply(["layers"], [{"id": "a", "generator": "ghost_fill", "params": {}}])
	recipe.build(builder)

	assert "grid" not in builder.calls[0][1]
