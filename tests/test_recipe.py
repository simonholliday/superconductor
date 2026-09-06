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


class Note:
	"""What the sequencer's read-back hands back, reduced to what is read.

	Frozen and hashable, because the difference between two reads is a set
	difference and that is the whole mechanism (#2102).
	"""

	def __init__ (self, position: int, origin: str | None, velocity: int = 100,
	              index: int = 0, primary_unmapped: bool = False) -> None:
		"""One note, where it is, which voice asked for it and how hard."""

		self.position = position
		self.origin = origin
		self.velocity = velocity
		self.index = index
		self.primary_unmapped = primary_unmapped

	def __hash__ (self) -> int:
		"""By everything, so two notes on one pulse stay two notes."""

		return hash((self.position, self.origin, self.velocity,
		             self.index, self.primary_unmapped))

	def __eq__ (self, other: object) -> bool:
		"""By everything, for the same reason."""

		return hash(self) == hash(other)


class Speaker:
	"""A link that writes down what was announced rather than sending it."""

	def __init__ (self, controls: dict[str, typing.Any] | None = None) -> None:
		"""Start with nothing said."""

		self.controls = controls or {}
		self.events: list[tuple[str, dict[str, typing.Any]]] = []

	def happened (self, name: str, **fields: typing.Any) -> None:
		"""Write down one event."""

		self.events.append((name, fields))


class Builder:
	"""A pattern builder that writes down what was called on it, in order."""

	def __init__ (self, places: list[Note] | None = None) -> None:
		"""Start with nothing played, and optionally something already there."""

		self.calls: list[tuple[str, dict[str, typing.Any]]] = []
		self.notes: list[Note] = list(places or [])
		self.lands: list[Note] = []

	def placed (self) -> list[Note]:
		"""What is on this pattern now."""

		return list(self.notes)

	def euclidean (self, **arguments: typing.Any) -> None:
		"""Record a call, and put down whatever this builder was told to."""

		self.calls.append(("euclidean", arguments))
		self.notes.extend(self.lands)

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


def test_a_pitch_parameter_that_takes_several_becomes_a_choices () -> None:
	"""The plural of the join above, and the whole of #2150.

	This shape used to be dropped and its generator marked partial, which cost
	twenty-two of the thirty-three generators a real panel is offered — not a
	random two thirds, but every chord and melody writer in the catalogue, since
	those are exactly the ones that name more than one voice.
	"""

	recipe, _ = _recipe()
	evolve = next(one for one in recipe.declaration()["generators"] if one["name"] == "evolve")
	pitches = evolve["parameters"][0]

	assert evolve["partial"] is False
	assert "undrawn" not in evolve

	assert pitches["kind"] == "choices"
	assert pitches["role"] == "pitch"
	assert [one["value"] for one in pitches["options"]] == ROWS

	# The flag that made it a plural has done its work and does not travel: a
	# panel reads the kind, and a second way of saying the same thing is a second
	# way for the two to disagree.
	assert "multiple" not in pitches


def test_a_composition_with_no_pitches_offers_no_pitch_parameter () -> None:
	"""Rather than an empty menu, which looks like a bug in the panel."""

	recipe = adapter.Recipe(Composition(), catalogue=CATALOGUE, pitches=[])
	euclidean = recipe.declaration()["generators"][0]

	assert euclidean["partial"] is True
	assert [one["name"] for one in euclidean["parameters"]] == ["pulses", "velocity"]


def test_a_generator_says_which_parameters_this_panel_could_not_draw () -> None:
	"""``partial`` alone conflated two different facts.

	It was set both by an app calling its own generator partial and by this
	package failing to draw one of its parameters, and a panel could not tell
	them apart — which matters, because only the second is anything anybody here
	can fix.
	"""

	recipe = adapter.Recipe(Composition(), catalogue=CATALOGUE, pitches=[])

	offered = {one["name"]: one for one in recipe.declaration()["generators"]}

	assert offered["euclidean"]["undrawn"] == ["pitch"]
	assert offered["evolve"]["undrawn"] == ["pitches"]


def test_a_layer_opens_its_pitch_pool_at_one_pitch_rather_than_a_number () -> None:
	"""A required parameter has to open at something the generator can use.

	Falling through to the numeric default gave it ``0``, which is not a list and
	not a pitch — a chord generator on the stack, apparently configured, holding
	a value nothing would accept if it were sent again.  One pitch is the same
	answer a single choice gives, wearing the shape a pool holds.
	"""

	recipe, composition = _recipe()

	recipe.apply(["layers"], [{"id": "a", "generator": "evolve", "params": {}}])

	assert recipe.layers()[0]["params"]["pitches"] == [ROWS[0]]


def test_a_generator_with_nothing_dropped_carries_no_undrawn_at_all () -> None:
	"""An empty list on every generator is a field a reader has to check first,
	and thirty-three of them is noise around the one that matters."""

	recipe, _ = _recipe()

	assert all("undrawn" not in one for one in recipe.declaration()["generators"])


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


def test_a_layer_is_given_a_number_of_its_own () -> None:
	"""Which is what a window is called on the glass: "Euclidean 1" (#2109).

	Per generator rather than across the stack, because the number is read as
	part of a name and "Euclidean 1, Bresenham 2" reads like a mistake.
	"""

	recipe, _ = _recipe()

	recipe.apply(["layers"], [
		{"id": "a", "generator": "euclidean", "params": {}},
		{"id": "b", "generator": "evolve", "params": {}},
		{"id": "c", "generator": "euclidean", "params": {}},
	])

	assert [one["index"] for one in recipe.layers()] == [1, 1, 2]


def test_a_number_does_not_move_when_a_neighbour_is_removed () -> None:
	"""Renumbering under somebody's hand is the surprise this exists to stop.

	A person reaches for the window they read a number on a moment ago.  If
	removing the first layer renamed the second, the thing they reach for is
	something else by the time they get there.
	"""

	recipe, _ = _recipe()

	recipe.apply(["layers"], [
		{"id": "a", "generator": "euclidean", "params": {}},
		{"id": "b", "generator": "euclidean", "params": {}},
		{"id": "c", "generator": "euclidean", "params": {}},
	])

	kept = [one for one in recipe.layers() if one["id"] != "a"]

	recipe.apply(["layers"], kept)

	assert [(one["id"], one["index"]) for one in recipe.layers()] == [("b", 2), ("c", 3)]


def test_a_number_is_never_handed_out_twice () -> None:
	"""So a stack may read 1, 3, 4 — stranger to look at, safer to work with.

	The mark is kept beside the stack rather than worked out from it, because
	the highest number in a stack goes down when the highest layer is removed
	and the next one added would take a name that has just been on the glass.
	"""

	recipe, composition = _recipe()

	recipe.apply(["layers"], [
		{"id": "a", "generator": "euclidean", "params": {}},
		{"id": "b", "generator": "euclidean", "params": {}},
	])

	recipe.apply(["layers"], [one for one in recipe.layers() if one["id"] == "a"])
	recipe.apply(["layers"], recipe.layers() + [
		{"id": "c", "generator": "euclidean", "params": {}}])

	assert [(one["id"], one["index"]) for one in recipe.layers()] == [("a", 1), ("c", 3)]
	assert composition.data["recipe"]["counts"] == {"euclidean": 3}


def test_a_number_a_panel_sends_back_is_the_one_it_keeps () -> None:
	"""Which is what makes ``restore_state`` restore a layout as well as a stack.

	A window's position is saved under a name built from that number, so a
	stack replayed with fresh numbers would come back to a page where nothing
	was where it was left.
	"""

	recipe, _ = _recipe()

	recipe.apply(["layers"], [
		{"id": "a", "generator": "euclidean", "index": 4, "params": {}},
		{"id": "b", "generator": "euclidean", "params": {}},
	])

	assert [one["index"] for one in recipe.layers()] == [4, 5]


def test_a_stack_that_is_refused_hands_out_no_numbers () -> None:
	"""A stack is checked entire before any of it is kept, and the count is part
	of what is kept."""

	recipe, composition = _recipe()

	recipe.apply(["layers"], [{"id": "a", "generator": "euclidean", "params": {}}])

	with pytest.raises(adapter.Refused):
		recipe.apply(["layers"], [
			{"id": "a", "generator": "euclidean", "params": {}},
			{"id": "b", "generator": "nonesuch", "params": {}},
		])

	assert composition.data["recipe"]["counts"] == {"euclidean": 1}


def test_a_stack_may_take_its_notes_from_another_grid () -> None:
	"""A grid belonging to no instrument, routed into several so that two synths
	share a bassline and each add notes of their own (#2108).

	The same mechanism as a generator rather than a second one: a contribution
	is a contribution, and what makes its notes is its own business.
	"""

	composition = Composition()
	played: list[str] = []

	recipe = adapter.Recipe(
		composition, catalogue=CATALOGUE, pitches=ROWS,
		sources={"shared": lambda pattern: played.append("shared")})

	recipe.apply(["layers"], [{"id": "a", "kind": "pattern", "source": "shared"}])
	recipe.build(Builder())

	assert played == ["shared"]
	assert recipe.layers() == [
		{"id": "a", "kind": "pattern", "source": "shared", "index": 1,
		 "bypassed": False, "params": {}}]


def test_a_routed_grid_is_offered_by_name_and_nothing_else () -> None:
	"""What a source is called on the glass is the control's own title, which a
	panel already has.  Saying it twice would be two places for it to be wrong."""

	recipe = adapter.Recipe(
		Composition(), catalogue=CATALOGUE, pitches=ROWS,
		sources={"shared": lambda pattern: None, "other": lambda pattern: None})

	assert recipe.declaration()["sources"] == ["other", "shared"]


def test_a_stack_offering_no_sources_says_so_by_saying_nothing () -> None:
	"""Which is every stack there was before this, and every one a composition
	with nothing worth sharing still wants."""

	recipe, _ = _recipe()

	assert "sources" not in recipe.declaration()


def test_a_route_to_a_grid_this_composition_does_not_offer_is_refused () -> None:
	"""Rather than kept and skipped.  A stack naming a grid nobody has is a
	fault in the panel, and the panel should be told."""

	recipe = adapter.Recipe(
		Composition(), catalogue=CATALOGUE, pitches=ROWS,
		sources={"shared": lambda pattern: None})

	with pytest.raises(adapter.Refused):
		recipe.apply(["layers"], [{"id": "a", "kind": "pattern", "source": "nowhere"}])


def test_a_bypassed_route_is_not_played () -> None:
	"""The same switch as a generator's, because it is the same stack."""

	played: list[str] = []
	recipe = adapter.Recipe(
		Composition(), catalogue=CATALOGUE, pitches=ROWS,
		sources={"shared": lambda pattern: played.append("shared")})

	recipe.apply(["layers"], [
		{"id": "a", "kind": "pattern", "source": "shared", "bypassed": True}])
	recipe.build(Builder())

	assert played == []


def test_a_route_and_a_generator_play_in_the_order_they_are_held () -> None:
	"""The order is musical content whichever kind is in it: a fill told to skip
	where a note already sits depends on what ran before it, and a routed grid
	puts notes there."""

	played: list[str] = []
	recipe = adapter.Recipe(
		Composition(), catalogue=CATALOGUE, pitches=ROWS,
		sources={"shared": lambda pattern: played.append("shared")})

	builder = Builder()

	recipe.apply(["layers"], [
		{"id": "a", "generator": "euclidean", "params": {}},
		{"id": "b", "kind": "pattern", "source": "shared"},
	])
	recipe.build(builder)

	assert played == ["shared"]
	assert [name for name, _ in builder.calls] == ["euclidean"]

	recipe.apply(["layers"], list(reversed(recipe.layers())))
	builder.calls.clear()
	played.clear()
	recipe.build(builder)

	assert played == ["shared"]


def test_a_route_that_will_not_play_is_skipped_rather_than_silencing_the_part () -> None:
	"""One bad contribution must not cost the instrument its bar, which is the
	same argument that already covers a failing generator."""

	def broken (pattern: typing.Any) -> None:
		raise RuntimeError("no")

	builder = Builder()
	recipe = adapter.Recipe(
		Composition(), catalogue=CATALOGUE, pitches=ROWS, sources={"shared": broken})

	recipe.apply(["layers"], [
		{"id": "a", "kind": "pattern", "source": "shared"},
		{"id": "b", "generator": "euclidean", "params": {}},
	])
	recipe.build(builder)

	assert [name for name, _ in builder.calls] == ["euclidean"]


def _watching (places: list[Note] | None = None) -> tuple[adapter.Recipe, Speaker, Builder]:
	"""A stack over a two-voice grid, with somewhere for it to say what it did."""

	grid = adapter.StepGrid(Composition(), rows=["kick", "snare"], steps=16, beats=4, name="grid")
	speaker = Speaker({"grid": grid})

	recipe = adapter.Recipe(
		Composition(), catalogue=CATALOGUE, pitches=ROWS,
		builds="grid", pulses_per_beat=24)
	recipe.attach(typing.cast(typing.Any, speaker))

	return recipe, speaker, Builder(places)


def _weights (cells: dict) -> dict:
	"""A realised report with the velocities alone, for the tests that are about
	the velocities.

	Each cell is ``{"v": ..., "from": ...}`` since contract 1.13.0, because a
	dot has to be able to say which layer put it there — a routed grid's note
	and a generator's wore the same mark and could not be told apart.  Where a
	test is about neither, saying so once here beats repeating the wrapper in
	every assertion.
	"""

	return {row: {step: held["v"] for step, held in steps.items()}
	        for row, steps in cells.items()}


def _sources (cells: dict) -> dict:
	"""The same report with the layers alone."""

	return {row: {step: held["from"] for step, held in steps.items()}
	        for row, steps in cells.items()}


def test_a_stack_says_which_cells_its_generators_realised () -> None:
	"""So the panel can draw them beside the steps somebody tapped (#1925).

	Six pulses to a step here — four beats of sixteen steps at twenty-four
	pulses a beat — so a note at pulse 12 is step 2.
	"""

	recipe, speaker, builder = _watching()

	builder.lands = [Note(0, "kick", 110), Note(12, "snare", 40), Note(90, "kick", 90)]

	recipe.apply(["layers"], [{"id": "a", "generator": "euclidean", "params": {}}])
	recipe.build(builder)

	assert len(speaker.events) == 1
	assert speaker.events[0][0] == "realised"
	assert speaker.events[0][1]["control"] == "grid"

	cells = speaker.events[0][1]["cells"]

	assert _weights(cells) == {"kick": {"0": 110, "15": 90}, "snare": {"2": 40}}

	# And every one of them names the layer that put it there, which is what a
	# dot needs to say whether an algorithm invented it or a route brought it.
	assert _sources(cells) == {"kick": {"0": "a", "15": "a"}, "snare": {"2": "a"}}


def test_what_was_already_there_is_not_reported_as_realised () -> None:
	"""A person's own taps are placed before the stack runs, so the difference
	is exactly what the algorithms added — which is the whole point of reading
	either side rather than reading once."""

	recipe, speaker, builder = _watching([Note(0, "kick"), Note(6, "snare")])

	builder.lands = [Note(12, "kick")]

	recipe.apply(["layers"], [{"id": "a", "generator": "euclidean", "params": {}}])
	recipe.build(builder)

	assert _weights(speaker.events[-1][1]["cells"]) == {"kick": {"2": 100}}


def test_a_generated_note_landing_on_a_tapped_one_is_still_reported () -> None:
	"""The case that made #2102 carry an index.  Two notes with equal fields are
	one member of a set, so a euclidean kick landing on a hand-tapped kick would
	report nothing while two note-ons fire."""

	recipe, speaker, builder = _watching([Note(0, "kick", index=0)])

	builder.lands = [Note(0, "kick", index=1)]

	recipe.apply(["layers"], [{"id": "a", "generator": "euclidean", "params": {}}])
	recipe.build(builder)

	assert _weights(speaker.events[-1][1]["cells"]) == {"kick": {"0": 100}}


def test_a_note_that_will_not_sound_is_not_drawn () -> None:
	"""A hit on the glass that makes no sound is a lie the panel would be
	telling on the app's behalf, which is why #2102 carries the flag."""

	recipe, speaker, builder = _watching()

	builder.lands = [Note(0, "kick", primary_unmapped=True), Note(6, "snare")]

	recipe.apply(["layers"], [{"id": "a", "generator": "euclidean", "params": {}}])
	recipe.build(builder)

	assert _weights(speaker.events[-1][1]["cells"]) == {"snare": {"1": 100}}


def test_a_note_naming_no_row_of_this_grid_is_left_alone () -> None:
	"""A pool may hold voices a grid does not draw, and a note with no named
	voice cannot be matched to a row at all."""

	recipe, speaker, builder = _watching()

	builder.lands = [Note(0, None), Note(6, "clap"), Note(12, "kick")]

	recipe.apply(["layers"], [{"id": "a", "generator": "euclidean", "params": {}}])
	recipe.build(builder)

	assert _weights(speaker.events[-1][1]["cells"]) == {"kick": {"2": 100}}


def test_every_cycle_says_what_it_realised_even_when_it_is_the_same () -> None:
	"""Comparing with the last answer and staying quiet is the obvious saving
	and it is wrong.

	A euclidean layer realises the same cells for ever, so a panel that opened
	after the first cycle would wait for a change that never comes and draw
	nothing.  Found on the rig with four generators playing and a fresh socket
	seeing silence — and nothing keeps these, by design, so there is nowhere for
	a late panel to read them from instead.
	"""

	recipe, speaker, builder = _watching()

	builder.lands = [Note(0, "kick")]

	recipe.apply(["layers"], [{"id": "a", "generator": "euclidean", "params": {}}])

	for _ in range(3):
		builder.notes = []
		recipe.build(builder)

	assert len(speaker.events) == 3, "a panel joining late would never be told"
	assert {name for name, _ in speaker.events} == {"realised"}


def test_a_stack_told_no_pulse_count_says_nothing_at_all () -> None:
	"""Which is every stack before this, and any composition whose sequencer
	cannot be read back.  It is a panel that draws no dots, not an error."""

	grid = adapter.StepGrid(Composition(), rows=["kick"], steps=16, beats=4, name="grid")
	speaker = Speaker({"grid": grid})

	recipe = adapter.Recipe(Composition(), catalogue=CATALOGUE, pitches=ROWS, builds="grid")
	recipe.attach(typing.cast(typing.Any, speaker))

	builder = Builder()
	builder.lands = [Note(0, "kick")]

	recipe.apply(["layers"], [{"id": "a", "generator": "euclidean", "params": {}}])
	recipe.build(builder)

	assert speaker.events == []


def test_a_pattern_that_cannot_be_read_back_is_not_an_error () -> None:
	"""A composition older than the read-back plays exactly as it did; it just
	draws nothing."""

	recipe, speaker, _ = _watching()

	class Old:
		"""A builder from before ``placed()`` existed."""

		def euclidean (self, **arguments: typing.Any) -> None:
			"""Play, and offer no way to read it back."""

	recipe.apply(["layers"], [{"id": "a", "generator": "euclidean", "params": {}}])
	recipe.build(Old())

	assert speaker.events == []


def test_how_hard_a_note_was_played_travels_with_it () -> None:
	"""Simon: "ghost fills appear the same as full-on hits.  This must change."

	They are not the same and never were — a ghost is a quiet note by its whole
	nature, so a panel drawing it at the weight of a full hit says the opposite
	of what it is.
	"""

	recipe, speaker, builder = _watching()

	builder.lands = [Note(0, "kick", 127), Note(6, "kick", 30)]

	recipe.apply(["layers"], [{"id": "a", "generator": "euclidean", "params": {}}])
	recipe.build(builder)

	assert _weights(speaker.events[-1][1]["cells"]) == {"kick": {"0": 127, "1": 30}}


def test_two_contributions_on_one_step_report_the_louder () -> None:
	"""Which is what a person hears: two notes on one drum voice are one sound,
	at the weight of the louder of them."""

	recipe, speaker, builder = _watching()

	builder.lands = [Note(0, "kick", 40), Note(2, "kick", 115)]

	recipe.apply(["layers"], [{"id": "a", "generator": "euclidean", "params": {}}])
	recipe.build(builder)

	assert _weights(speaker.events[-1][1]["cells"]) == {"kick": {"0": 115}}


def test_a_grid_switched_off_contributes_nothing_where_it_is_routed () -> None:
	"""A mute rather than a delete: the route is still there and still drawn, it
	just carries nothing.

	Simon asked for an on/off on every item, and this is what one means for a
	grid with no instrument — there is no pattern of its own to silence, so the
	only thing "off" can say is that it stops contributing.
	"""

	played: list[str] = []
	grid = adapter.StepGrid(Composition(), rows=["kick"], steps=16, beats=4, name="shared")
	speaker = Speaker({"shared": grid})

	recipe = adapter.Recipe(
		Composition(), catalogue=CATALOGUE, pitches=ROWS,
		sources={"shared": lambda pattern: played.append("shared")})
	recipe.attach(typing.cast(typing.Any, speaker))

	recipe.apply(["layers"], [{"id": "a", "kind": "pattern", "source": "shared"}])
	recipe.build(Builder())

	assert played == ["shared"]

	grid.apply(["enabled"], False)
	recipe.build(Builder())

	assert played == ["shared"], "a grid that is off still contributed"

	grid.apply(["enabled"], True)
	recipe.build(Builder())

	assert played == ["shared", "shared"], "switching it back on did not bring it back"
