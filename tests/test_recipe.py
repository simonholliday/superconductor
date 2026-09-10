"""A stack of generators: what it offers, what it keeps, and what it plays.

The panel picks a generator out of a catalogue the app describes itself with
(#2085), so nothing here names one either — the catalogue below is a stand-in
with the same shape Subsequence's own has, which is what keeps this test honest
about the rule it is testing.
"""

import logging
import random
import typing

import pytest

import superconductor.controls as controls
import superconductor.subsequence_adapter as adapter


# **Shaped like a catalogue a real app sends, which since 2026-09-09 means every
# parameter says whether it is required.**  These carried no such flag while the
# adapter inferred it from parameter order, and a fake that lags the wire is how
# two halves come to pass their own tests and fail together — the reason
# `tests/conftest.py` keeps one `FakeApp` rather than letting each file build
# frames by hand.  A parameter that is `required: False` with `"default": None`
# is the case the flag exists for: it must be left out, not filled with a zero.
CATALOGUE: list[dict[str, typing.Any]] = [
	{
		"name": "euclidean",
		"summary": "Generate a Euclidean rhythm.",
		"partial": False,
		"parameters": [
			{"name": "pitch", "label": "pitch", "kind": "pitch", "required": True},
			{"name": "pulses", "label": "pulses", "kind": "number", "step": 1,
			 "required": True},
			{"name": "velocity", "label": "velocity", "kind": "range",
			 "min": 1, "max": 127, "default": 100, "required": False},
		],
	},
	{
		"name": "evolve",
		"summary": "Loop a pitch sequence that gradually mutates.",
		"partial": False,
		"parameters": [
			{"name": "pitches", "label": "pitches", "kind": "pitch",
			 "multiple": True, "required": True},
			{"name": "drift", "label": "drift", "kind": "number",
			 "min": 0.0, "max": 1.0, "default": 0.0, "required": False},
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


def test_a_parameter_kind_this_panel_has_never_heard_of_is_not_drawn () -> None:
	"""An app may be newer than this package, and a kind is how that shows.

	Everything that was not a pitch used to pass straight through, and the
	fall-through at both ends of the adapter is *it is a number* — so a kind
	nobody here had heard of arrived on the glass as an unbounded dial opening at
	zero, and would have handed that zero back to the generator as if somebody
	had chosen it.  Measured against Subsequence's ``kind: "chord"`` on the day
	it was written (#2379).

	`undrawn` is the honest answer and already means exactly this.  A panel is
	told the parameter exists and that this package could not draw it, which is
	the one thing a person could act on.
	"""

	catalogue: list[dict[str, typing.Any]] = [{
		"name": "arpeggio",
		"summary": "Play a chord one note at a time.",
		"partial": False,
		"parameters": [
			{"name": "chord", "label": "chord", "kind": "chord", "required": True},
			{"name": "spacing", "label": "spacing", "kind": "number",
			 "default": 0.25, "required": False},
		],
	}]

	recipe = adapter.Recipe(Composition(), catalogue=catalogue, pitches=ROWS)
	offered = recipe.declaration()["generators"][0]

	assert offered["undrawn"] == ["chord"]
	assert offered["partial"] is True
	assert [one["name"] for one in offered["parameters"]] == ["spacing"]

	# **And it is gone from every other answer, not only from the drawing.**
	# `offerable` is the one choke point the opening value, the validation map
	# and the declaration all read through, so refusing it once refuses it
	# everywhere — which is the whole reason the guard lives there.
	recipe.apply(["layers"], [{"id": "a", "generator": "arpeggio", "params": {}}])

	assert recipe.layers()[0]["params"] == {"spacing": 0.25}

	with pytest.raises(adapter.Refused):
		recipe.apply(["layers", "a", "params", "chord"], 0)


def test_the_drawable_kinds_are_the_ones_the_service_keeps () -> None:
	"""One vocabulary, read by the half that offers and the half that keeps.

	A tuple naming the same six kinds in two files is two rules holding one fact,
	which is how the two ends of this package have come to disagree three times.
	``pitch`` is the one addition and never reaches a panel: it is turned into a
	choice of the pitches a composition actually has, so it has to be let through
	to be converted.
	"""

	assert set(adapter.DRAWABLE) == set(controls.PARAMETER_KINDS) | {"pitch"}


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
			{"name": "pitch", "label": "pitch", "kind": "pitch", "required": True},
			{"name": "density", "label": "density", "kind": "number",
			 "min": 0.0, "max": 1.0, "default": 0.3, "required": False},
			# The whole case this file exists to hold: optional, and its default
			# really is `None`, which the catalogue now publishes as `null`
			# rather than by leaving the key out.
			{"name": "grid", "label": "grid", "kind": "number", "step": 1,
			 "required": False, "default": None},
		],
	},
]


def test_a_parameter_the_generator_decides_for_itself_is_left_out () -> None:
	"""And filling it in silenced the layer while it looked perfectly set up.

	``grid`` defaults to ``None`` — *use the pattern's own grid*.  It used to
	arrive looking exactly like a required parameter with no default, because the
	catalogue left the key out for both, so filling both with a number handed
	``ghost_fill`` a grid of no steps, which places nothing and says nothing.
	The catalogue says which is which now (upstream #2249), and this holds that
	the optional one is still left alone.
	"""

	recipe = adapter.Recipe(Composition(), catalogue=OPTIONAL, pitches=ROWS)

	recipe.apply(["layers"], [{"id": "a", "generator": "ghost_fill", "params": {}}])

	assert recipe.layers()[0]["params"] == {"pitch": "kick", "density": 0.3}


def test_a_parameter_the_generator_cannot_do_without_is_filled_in () -> None:
	"""A parameter the catalogue marks `required` is opened at something; the
	app says which, and nothing here infers it from parameter order."""

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


def test_a_parameter_that_opened_unset_can_be_put_back_to_unset () -> None:
	"""And before this it could not, which is what made #2381 unrecoverable.

	``root`` and ``count`` on an arpeggio apply to the chord form alone, so
	moving either one beside a pitch list kills the layer — and **zero does not
	undo it, only absence does**.  The panel drew steppers that could reach zero
	and could not reach absent, so a layer was one press from silence with no
	gesture that returned it; it took the panel's own socket to give Simon his
	arpeggio back on 2026-09-10.

	The value that says so is ``null``, and what it leaves behind is **no key at
	all** rather than a stored ``None``: leaving the argument out of the call is
	the whole mechanism by which a generator is told to decide for itself, and
	`test_a_parameter_left_out_is_not_passed_to_the_generator` above is the other
	half of that sentence.
	"""

	recipe = adapter.Recipe(Composition(), catalogue=OPTIONAL, pitches=ROWS)

	recipe.apply(["layers"], [{"id": "a", "generator": "ghost_fill", "params": {}}])

	assert "grid" not in recipe.layers()[0]["params"], "it opens unset"

	assert recipe.apply(["a", "grid"], 4) is True
	assert recipe.layers()[0]["params"]["grid"] == 4

	assert recipe.apply(["a", "grid"], None) is True, "and it goes back"
	assert "grid" not in recipe.layers()[0]["params"]

	assert recipe.apply(["a", "grid"], None) is False, "which is not a change twice"


def test_unsetting_a_parameter_stops_it_reaching_the_generator () -> None:
	"""The point of the gesture, rather than the shape of what it stores.

	A zero is refused by the generators this exists for exactly as any other
	number is, so a test asserting only that the *key* went would pass against a
	panel that had put the layer back to silence.
	"""

	recipe = adapter.Recipe(Composition(), catalogue=OPTIONAL, pitches=ROWS)
	builder = Builder()

	setattr(builder, "ghost_fill",
	        lambda **arguments: builder.calls.append(("ghost_fill", arguments)))

	recipe.apply(["layers"], [{"id": "a", "generator": "ghost_fill", "params": {}}])
	recipe.apply(["a", "grid"], 4)
	recipe.build(builder)

	assert builder.calls[0][1]["grid"] == 4

	recipe.apply(["a", "grid"], None)
	builder.calls.clear()
	recipe.build(builder)

	assert "grid" not in builder.calls[0][1], "the generator decides again"


def test_a_parameter_that_has_to_hold_something_refuses_to_be_unset () -> None:
	"""Because absence means *you decide* and this one has nothing to decide with.

	`density` opens at 0.3 and `pitch` must be supplied, so neither has an unset
	to return to; a panel sending one is told so by name rather than having a
	`None` quietly handed to the generator.
	"""

	recipe = adapter.Recipe(Composition(), catalogue=OPTIONAL, pitches=ROWS)

	recipe.apply(["layers"], [{"id": "a", "generator": "ghost_fill", "params": {}}])

	for parameter in ("density", "pitch"):
		with pytest.raises(adapter.Refused, match=parameter):
			recipe.apply(["a", parameter], None)


def test_a_whole_stack_carrying_a_null_leaves_that_parameter_out () -> None:
	"""The two ways in have to agree, and one of them is how a capture comes back.

	A stack arrives entire when a layer is added, removed, bypassed or moved, so
	a stack sent while a parameter is unset carries the null — and it has to
	reach the same place a single set does, or a restore would put back a layer
	holding a `None` that no gesture had asked for.
	"""

	recipe = adapter.Recipe(Composition(), catalogue=OPTIONAL, pitches=ROWS)

	recipe.apply(["layers"], [
		{"id": "a", "generator": "ghost_fill", "params": {"grid": None, "density": 0.5}}])

	held = recipe.layers()[0]["params"]

	assert "grid" not in held
	assert held["density"] == 0.5


def test_an_instruments_setting_has_no_unset_to_go_back_to () -> None:
	"""A CC always holds a number and a switch is on or off.

	The permission is read off a *catalogue's* own entry, and a composition
	building a settings panel declares no `default` key at all — so a looser test
	than `protocol.may_be_unset`'s would have offered every dial on a Matriarch
	an "auto" it has no way to be, and refused nothing when a panel sent one.
	"""

	for kind, default in (("number", None), ("switch", None), ("choice", None)):
		parameter = adapter.Parameter("cutoff", kind, default=default)

		assert parameter.may_be_unset is False

		with pytest.raises(adapter.Refused, match="cutoff"):
			adapter.checked_value(parameter, None)


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

	recipe.apply(["layers"], [{"id": "a", "kind": "route", "source": "shared"}])
	recipe.build(Builder())

	assert played == ["shared"]
	assert recipe.layers() == [
		{"id": "a", "kind": "route", "source": "shared", "index": 1,
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
		recipe.apply(["layers"], [{"id": "a", "kind": "route", "source": "nowhere"}])


def test_a_bypassed_route_is_not_played () -> None:
	"""The same switch as a generator's, because it is the same stack."""

	played: list[str] = []
	recipe = adapter.Recipe(
		Composition(), catalogue=CATALOGUE, pitches=ROWS,
		sources={"shared": lambda pattern: played.append("shared")})

	recipe.apply(["layers"], [
		{"id": "a", "kind": "route", "source": "shared", "bypassed": True}])
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
		{"id": "b", "kind": "route", "source": "shared"},
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
		{"id": "a", "kind": "route", "source": "shared"},
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

	recipe.apply(["layers"], [{"id": "a", "kind": "route", "source": "shared"}])
	recipe.build(Builder())

	assert played == ["shared"]

	grid.apply(["enabled"], False)
	recipe.build(Builder())

	assert played == ["shared"], "a grid that is off still contributed"

	grid.apply(["enabled"], True)
	recipe.build(Builder())

	assert played == ["shared", "shared"], "switching it back on did not bring it back"


def test_a_note_grid_is_reported_in_its_own_positions_not_in_steps () -> None:
	"""#2219, and it drew a bar's worth of generator in the first three cells.

	The Minitaur's bassline divides each of sixteen steps into six, so it is
	ninety-six positions wide and a position is one pulse — and the panel maps
	what arrives to a cell by dividing by ``divisions``.  Reported in *steps*,
	eleven notes spread evenly across the bar arrive as 0, 1, 3, 4, 6, 7 … and
	are drawn in cells 0, 0, 0, 1, 1, 1: the whole rhythm compressed into the
	first sixth of the pattern.

	It sounded correct throughout, which is why it read as a generator that had
	stopped early rather than as a dot in the wrong place.
	"""

	grid = adapter.NoteGrid(
		Composition(), rows=["kick", "snare"], steps=16, beats=4,
		divisions=6, name="bass")
	speaker = Speaker({"bass": grid})

	recipe = adapter.Recipe(
		Composition(), catalogue=CATALOGUE, pitches=ROWS,
		builds="bass", pulses_per_beat=24)
	recipe.attach(typing.cast(typing.Any, speaker))

	# One pulse to a position here, so a note's pulse is its position — and the
	# last of them is at pulse 90, which is a position this grid has and a step
	# it does not.
	builder = Builder()
	builder.lands = [Note(0, "kick", 110), Note(12, "snare", 40), Note(90, "kick", 90)]

	recipe.apply(["layers"], [{"id": "a", "generator": "euclidean", "params": {}}])
	recipe.build(builder)

	cells = speaker.events[0][1]["cells"]

	assert _weights(cells) == {"kick": {"0": 110, "90": 90}, "snare": {"12": 40}}


def test_a_note_grid_reports_a_note_the_last_step_could_not_hold () -> None:
	"""The other half of #2219: the bound is the grid's own count of places.

	A note at pulse 95 is the ninety-sixth position of ninety-six and the last
	moment of the bar.  Bounded by ``steps`` it is outside the pattern and is
	dropped, so the fault took the far end of every generated phrase as well as
	crowding what remained.
	"""

	grid = adapter.NoteGrid(
		Composition(), rows=["kick"], steps=16, beats=4, divisions=6, name="bass")
	speaker = Speaker({"bass": grid})

	recipe = adapter.Recipe(
		Composition(), catalogue=CATALOGUE, pitches=ROWS,
		builds="bass", pulses_per_beat=24)
	recipe.attach(typing.cast(typing.Any, speaker))

	builder = Builder()
	builder.lands = [Note(95, "kick", 70), Note(96, "kick", 70)]

	recipe.apply(["layers"], [{"id": "a", "generator": "euclidean", "params": {}}])
	recipe.build(builder)

	cells = speaker.events[0][1]["cells"]

	assert _weights(cells) == {"kick": {"95": 70}}, "a note past the bar was drawn"


def test_a_route_that_leads_back_to_its_own_stack_plays_once () -> None:
	"""#2230, and it took the rig down.

	A stack is drawn wherever its pattern is drawn (#2211), so a grid and the
	stack that feeds it sit on one page and a cable has two plausible ends.
	Dragged to the wrong one, the route's play function builds the very stack
	that is playing it.

	**The recursion is not the damage.**  `RecursionError` is an `Exception`, so
	`_complain` catches it and every level unwinds — a millisecond of work.  What
	costs is that each level *reports what it landed*, so one cycle emitted 498
	`realised` events, and the link loop drowned in frames scheduled from the
	clock thread (#2242).

	Asserted on the event count rather than on the hang, because the count is
	the thing that can be proved here: the offline harness never reproduced a
	process actually becoming unresponsive.
	"""

	grid = adapter.StepGrid(Composition(), rows=["kick"], steps=16, beats=4, name="shared")
	speaker = Speaker({"shared": grid})

	recipe = adapter.Recipe(
		Composition(), catalogue=CATALOGUE, pitches=ROWS,
		builds="shared", pulses_per_beat=24, name="shared_recipe")
	recipe.attach(typing.cast(typing.Any, speaker))

	# Assigned after construction because the play function has to name the
	# recipe, which is exactly the knot the composition ties: `_play_shared`
	# runs `shared_recipe.build(p)`, and the recipe declares `shared` a source.
	recipe.sources = {"shared": lambda pattern: recipe.build(pattern)}
	recipe.apply(["layers"], [{"id": "a", "kind": "route", "source": "shared"}])

	recipe.build(Builder())

	assert len(speaker.events) == 1, (
		f"a looping route reported {len(speaker.events)} times in one cycle")


def test_a_stack_already_building_says_so_rather_than_failing_silently (
	caplog: pytest.LogCaptureFixture,
) -> None:
	"""The guard has to be audible, because the cable looks connected.

	A route refused with nothing said is a cable a person can see, drawn between
	two blocks, carrying nothing — and #2164's whole lesson is that the one
	symptom of a silent fault is somebody reporting the feature as broken.
	"""

	grid = adapter.StepGrid(Composition(), rows=["kick"], steps=16, beats=4, name="shared")
	speaker = Speaker({"shared": grid})

	recipe = adapter.Recipe(
		Composition(), catalogue=CATALOGUE, pitches=ROWS,
		builds="shared", pulses_per_beat=24, name="shared_recipe")
	recipe.attach(typing.cast(typing.Any, speaker))

	recipe.sources = {"shared": lambda pattern: recipe.build(pattern)}
	recipe.apply(["layers"], [{"id": "a", "kind": "route", "source": "shared"}])

	with caplog.at_level(logging.WARNING, logger="superconductor.subsequence_adapter"):
		recipe.build(Builder())

	said = " ".join(record.getMessage() for record in caplog.records)

	assert said, "a refused route said nothing at all"

	# **Named for what it is, not for how it failed.**  Before the guard this
	# complained about a recursion limit, which is true and useless: a person
	# reading it on the glass has to work out that the number describes their
	# cable.  Asserting the wording is what makes this test fail against the
	# previous commit rather than passing on the `RecursionError` by accident.
	assert "recursion" not in said.lower(), f"complained about the mechanism: {said}"
	assert "shared" in said, f"the complaint did not name the route: {said}"


def test_a_guard_that_has_been_tripped_does_not_stay_tripped () -> None:
	"""The next cycle must play normally, or one bad drag silences a part for ever.

	`try`/`finally` rather than clearing at the end of the body: a generator that
	raises inside the stack would otherwise leave the flag set, and the block
	would go quiet with nothing to say why.
	"""

	grid = adapter.StepGrid(Composition(), rows=["kick"], steps=16, beats=4, name="shared")
	speaker = Speaker({"shared": grid})

	recipe = adapter.Recipe(
		Composition(), catalogue=CATALOGUE, pitches=ROWS,
		builds="shared", pulses_per_beat=24, name="shared_recipe")
	recipe.attach(typing.cast(typing.Any, speaker))
	recipe.sources = {"shared": lambda pattern: recipe.build(pattern)}

	recipe.apply(["layers"], [{"id": "a", "kind": "route", "source": "shared"}])
	recipe.build(Builder())

	# The cable is unplugged and an ordinary generator put in its place.
	recipe.apply(["layers"], [{"id": "b", "generator": "euclidean", "params": {}}])

	builder = Builder()
	recipe.build(builder)

	assert [name for name, _ in builder.calls] == ["euclidean"], (
		"the stack stayed shut after the loop was removed")


class Stream (Builder):
	"""A builder with a random stream of its own, as a real pattern has.

	The two generators differ in one thing only, and it is the thing under test:
	``euclidean`` names ``seed`` in its signature and ``evolve`` does not.  That
	is exactly how this package tells them apart, because the catalogue leaves
	``seed`` out on purpose — a seed is a machine's parameter, so it is supplied
	and never offered.

	**And each draws the way a real generator draws**: from the stream it was
	handed if it was handed one, and from the pattern's own if it was not.  A
	fake that never touched the stream would pass the test below against the
	very code it exists to catch.
	"""

	def __init__ (self, rng: random.Random) -> None:
		"""A builder over *rng*, which stands for the pattern's own stream."""

		super().__init__()
		self.rng = rng

	def euclidean (self, seed: int | None = None, **arguments: typing.Any) -> None:
		"""A layer that draws, and will take a stream of its own."""

		self.calls.append(("euclidean", {**arguments, "seed": seed}))
		(random.Random(seed) if seed is not None else self.rng).random()
		self.notes.extend(self.lands)

	def evolve (self, **arguments: typing.Any) -> None:
		"""A layer that draws, and will not."""

		self.calls.append(("evolve", arguments))
		self.rng.random()


def _played (
	recipe: adapter.Recipe,
	layers: list[dict[str, typing.Any]],
	rng: random.Random,
) -> list[int | None]:
	"""Play *layers* on *rng* and hand back the seed each was given, in order."""

	recipe.apply(["layers"], layers)
	builder = Stream(rng)
	recipe.build(builder)

	return [arguments.get("seed") for _, arguments in builder.calls]


def _stack (*ids: str) -> list[dict[str, typing.Any]]:
	"""A stack of euclideans, one per id."""

	return [{"id": one, "generator": "euclidean", "params": {}} for one in ids]


def test_a_layer_draws_the_same_wherever_it_sits_in_the_stack () -> None:
	"""The whole of #2233, in one line.

	Every layer used to draw from the pattern's one stream in call order, so a
	layer's notes depended on how many numbers its neighbours had taken first.
	Measured against real generators before the fix: turning ``pulses`` from 7 to
	3 on the layer *above* moved the one below from [0, 18, 36, 54] to
	[0, 18, 36, 72].  Reorder, bypass and knob are the whole gesture set of a
	rack, and all three did this.

	The same stream is dealt to both builds, which is what isolates the variable:
	the only difference between them is what sits above the layer under test.
	"""

	recipe, _ = _recipe()

	alone = _played(recipe, _stack("two"), random.Random(7))
	below = _played(recipe, _stack("one", "two"), random.Random(7))

	assert alone[0] is not None, "no layer was given a stream of its own"
	assert below[1] == alone[0], "a layer's stream moved when a neighbour appeared"
	assert below[0] != below[1], "two layers were dealt the same stream"


def test_the_shared_stream_is_drawn_from_once_whatever_the_stack_holds () -> None:
	"""The property that makes the fix a fix rather than a rearrangement.

	One draw before any layer runs, so nothing a person does to the stack can
	move it.  If the base were taken per layer, or if the layers still drew from
	the shared stream themselves, adding one would shift every other.
	"""

	recipe, _ = _recipe()

	def left (layers: list[dict[str, typing.Any]]) -> float:
		"""Where the shared stream stands once this stack has played."""

		stream = random.Random(7)
		_played(recipe, layers, stream)

		return stream.random()

	assert left(_stack("a")) == left(_stack("a", "b", "c", "d"))


def test_a_layer_still_moves_from_one_cycle_to_the_next () -> None:
	"""Because the obvious fix freezes it, and a frozen rack is not a sequencer.

	Seeding a layer from its id alone — which is what #2233 proposed — hands
	``seed=`` a constant, and Subsequence builds a fresh ``Random(seed)`` for
	that call: measured over three cycles, the same bar every time.  The base is
	drawn from the pattern's stream instead, so it moves as the music does.
	"""

	recipe, _ = _recipe()
	stream = random.Random(7)

	first = _played(recipe, _stack("one"), stream)
	second = _played(recipe, _stack("one"), stream)

	assert first[0] is not None
	assert first != second, "a layer was dealt the same stream two cycles running"


def test_a_pattern_dealt_the_same_stream_twice_lands_in_the_same_place () -> None:
	"""Which is what ``lock()`` is, and it keeps working without being asked to.

	A locked pattern is re-dealt its stream from a fixed seed every cycle.  So
	the base comes out the same, so every layer under it does — and a freeze
	gesture of our own (#2232) becomes a question of what goes in the key rather
	than a second mechanism beside this one.
	"""

	recipe, _ = _recipe()

	first = _played(recipe, _stack("one", "two"), random.Random(11))
	second = _played(recipe, _stack("one", "two"), random.Random(11))

	assert first[0] is not None
	assert first == second


def test_a_layer_that_will_not_take_a_stream_is_not_handed_one () -> None:
	"""Twenty of the forty-six offered here will not, and that is not a fault.

	Fourteen of them draw no random numbers at all, so no neighbour can disturb
	them; the other six cannot be called from a panel at all today, which is a
	separate defect of the same family as #2248.  What matters is that this
	package asks rather than assumes: a generator handed a keyword it does not
	have raises, and a stack that raises is a block that goes quiet.
	"""

	recipe, _ = _recipe()
	recipe.apply(["layers"], [{"id": "one", "generator": "evolve", "params": {}}])

	builder = Stream(random.Random(7))
	recipe.build(builder)

	assert [name for name, _ in builder.calls] == ["evolve"]
	assert "seed" not in builder.calls[0][1]


def test_a_pattern_with_no_stream_of_its_own_is_left_exactly_as_it_was () -> None:
	"""A composition older than this, or a pattern object that is something else.

	Not an error and not a warning: it is a stack that behaves the way every
	stack behaved before, which is the same courtesy the read-back pays a
	sequencer too old to be asked what it is holding.
	"""

	recipe, _ = _recipe()
	recipe.apply(["layers"], _stack("one"))

	builder = Builder()
	recipe.build(builder)

	assert [name for name, _ in builder.calls] == ["euclidean"]
	assert "seed" not in builder.calls[0][1]
