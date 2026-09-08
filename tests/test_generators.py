"""The stack against Subsequence's real generators, rather than a stand-in.

`test_recipe.py` names no generator on purpose — the catalogue is an app's
description of itself and this package must work against any of them.  That
keeps it honest and leaves a join untested, and this suite's sharpest lesson is
about exactly that shape: both halves correct by their own tests, wrong
together.  `test_seam.py` covers the join between the service and an app; this
covers the one between this package and the sequencer an app actually runs.

Importing Subsequence here is a rig arrangement, not a dependency: the package
declares none on any particular app, and the composition suite beside this one
imports it already.
"""

import logging
import random
import typing

import pytest

import subsequence
import subsequence.pattern
import subsequence.pattern_builder

import superintendent.subsequence_adapter as adapter


ROWS = ["C2", "E2", "G2"]

NOTES = {"C2": 36, "E2": 40, "G2": 43}
"""What those rows sound, which is a fact about a rig and never about a package.

Here it stands for a composition's own note map, and it has to be handed to the
builder because Subsequence resolves a named pitch through one.
"""


class Composition:
	"""Just the dict a control touches, as the rest of the suite uses."""

	def __init__ (self) -> None:
		"""Start with nothing in it."""

		self.data: dict[str, typing.Any] = {}


def _recipe () -> adapter.Recipe:
	"""A stack offering everything this Subsequence has, over three notes."""

	return adapter.Recipe(
		Composition(),
		catalogue=subsequence.generators(),
		transforms=subsequence.transforms(),
		pitches=ROWS,
		bounds={"pulses": (0, 16), "grid": (1, 16)},
		name="stack")


def _built (
	recipe: adapter.Recipe,
	layers: list[dict[str, typing.Any]],
	rng: random.Random,
) -> list[tuple[int, int]]:
	"""Play *layers* onto a real pattern and hand back what landed."""

	recipe.apply(["layers"], layers)
	pattern = subsequence.pattern.Pattern(channel=1, length=4.0)
	builder = subsequence.pattern_builder.PatternBuilder(
		pattern=pattern, cycle=0, rng=rng, drum_note_map=NOTES)
	recipe.build(builder)

	return sorted((note.pitch, note.position) for note in builder.placed())


def _thinned (layer_id: str, pitch: str, pulses: int) -> dict[str, typing.Any]:
	"""One euclidean thin enough to have to draw for every pulse."""

	return {
		"id": layer_id,
		"generator": "euclidean",
		"params": {"pitch": pitch, "pulses": pulses, "probability": 0.6},
	}


def _voice (notes: list[tuple[int, int]], pitch: int) -> list[int]:
	"""Where one voice's notes landed."""

	return [position for played, position in notes if played == pitch]


def test_a_layers_notes_do_not_move_when_a_neighbours_knob_does () -> None:
	"""#2233, measured against the generators a person actually stacks.

	Before the fix this was the fault in its plainest form: every layer drew from
	the pattern's one stream in call order, so turning `pulses` from 7 to 3 on
	the layer *above* moved the one below from [0, 18, 36, 54] to [0, 18, 36, 72]
	— a bar that changed for no reason a person could see, on a surface whose
	whole gesture set is arranging what you already have.
	"""

	recipe = _recipe()
	under = _thinned("under", "G2", 5)

	alone = _built(recipe, [under], random.Random(3))
	assert alone, "the layer under test placed nothing at all"
	voice = alone[0][0]

	wide = _built(recipe, [_thinned("above", "C2", 7), under], random.Random(3))
	narrow = _built(recipe, [_thinned("above", "C2", 3), under], random.Random(3))

	assert _voice(wide, voice) == _voice(narrow, voice), (
		"a layer's notes moved because a knob above it did")


def test_a_layers_notes_do_not_move_when_the_one_above_is_bypassed () -> None:
	"""The same fault reached by the other gesture, and the more damning one.

	Bypassing is offered as *listen to this without that*, which is a claim about
	one layer and used to be a change to every layer below it.
	"""

	recipe = _recipe()
	under = _thinned("under", "G2", 5)
	above = _thinned("above", "C2", 7)

	playing = _built(recipe, [above, under], random.Random(3))
	silenced = _built(recipe, [{**above, "bypassed": True}, under], random.Random(3))

	voice = _built(recipe, [under], random.Random(3))[0][0]

	assert _voice(playing, voice) == _voice(silenced, voice), (
		"a layer's notes moved because the one above it was switched off")


def test_a_layer_still_plays_something_new_each_cycle () -> None:
	"""And the fix must not buy that stability by freezing the music.

	Seeding a layer from its identity alone would: `seed=` builds a fresh
	`Random` for that call, so the layer would place the same bar for ever.  The
	stream this package draws its base from advances a cycle at a time, so the
	base moves and the layer moves with it.
	"""

	recipe = _recipe()
	stream = random.Random(3)
	bars = [_built(recipe, [_thinned("one", "G2", 7)], stream) for _ in range(5)]

	assert any(bar != bars[0] for bar in bars[1:]), (
		"five cycles running, the layer placed exactly the same notes")


def test_a_pattern_dealt_the_same_stream_twice_plays_the_same_bar () -> None:
	"""Which is what `lock()` does, and it keeps working without being asked to.

	A locked pattern is re-dealt its stream from a fixed seed every cycle, so the
	base comes out the same and every layer under it lands where it landed.  The
	freeze this package may offer of its own (#2232) is then a question of what
	goes into the key rather than a second mechanism beside this one.
	"""

	recipe = _recipe()
	layers = [_thinned("one", "C2", 7), _thinned("two", "G2", 5)]

	assert _built(recipe, layers, random.Random(11)) == \
		_built(recipe, layers, random.Random(11))


# --- the sweep #2214 asks for -----------------------------------------------

WILL_NOT_RUN = {
	# **A number where the function asked to be told nothing** (#2248, upstream
	# #2249).  `_required` infers what must be filled from parameter order, and a
	# parameter with no default reads identically to one defaulting to `None`.
	"arpeggio": "root", "chord": "root", "strum": "root", "fibonacci": "modulus",

	# **A precondition enforced at run time and never declared** (upstream #2251).
	# The only consumer that could open these at a legal value is one that already
	# knew the answer.
	"duration": "positive", "repeat": "positive", "stretch": "positive",

	# **Partial, and not merely partial** (#2154).  The catalogue drops a
	# parameter this panel cannot draw, and the parameter is required — so the
	# layer can be added and can never run.  `partial` says *you cannot drive all
	# of this*; it does not say *adding this is pointless*, and these need the
	# second thing said.
	"bresenham_poly": "parts", "broken_chord": "chord_obj", "hit": "beats",
	"hit_steps": "steps", "lsystem": "pitch_map", "markov": "transitions",
	"melody": "state", "motif": "m", "phrase": "value", "sequence": "steps",
}
"""Every layer that is offered on the glass and cannot run, and why.

**This is a test rather than a fact the code reads**, which is the difference
between it and a second copy of something Subsequence knows: nothing consults it,
and its whole purpose is to go red when the join moves.  #2214 asks to close by
measurement rather than by argument, and this is the measurement.
"""


def _sweep (caplog: typing.Any) -> dict[str, str]:
	"""Add each offered layer on its own, at its opening values, and see who complains."""

	recipe = _recipe()
	offered = ([(shape, "generator") for shape in recipe.catalogue]
	           + [(shape, "transform") for shape in recipe.transforms])
	broken = {}

	for shape, kind in offered:
		name = str(shape.get("name"))

		# A fresh stack each time: a complaint is made once per generator per
		# stack, so that a rebuilt bar does not flood a log twice a second.
		one = _recipe()
		one.apply(["layers"], [{"id": "l", "kind": kind, kind: name, "params": {}}])

		pattern = subsequence.pattern.Pattern(channel=1, length=4.0)
		builder = subsequence.pattern_builder.PatternBuilder(
			pattern=pattern, cycle=0, rng=random.Random(3), drum_note_map=NOTES)

		# Something for a transform to reshape, or half the catalogue is asked to
		# work on an empty bar and answers honestly that it did nothing.
		builder.euclidean("C2", pulses=5)

		caplog.clear()

		with caplog.at_level(logging.WARNING, logger="superintendent.subsequence_adapter"):
			one.build(builder)

		if caplog.records:
			broken[name] = caplog.records[0].getMessage()

	return broken


# **Upstream is right and it is saying so to the wrong audience.**  A seed reaches
# `cellular_2d` because this package supplies one to every layer that will take
# it, and at the default `initial_state="center"` that seed does nothing — which
# is worth one line in a rig's log the first time somebody adds the layer, and is
# noise in a sweep whose whole job is to call all forty-six.  Named exactly, so
# any other warning still counts: a clean run here is two, both third-party.
@pytest.mark.filterwarnings("ignore:cellular_2d:UserWarning")
def test_the_layers_that_cannot_run_are_the_ones_already_written_down (
	caplog: typing.Any) -> None:
	"""Seventeen of the forty-six offered here are added and then skipped every cycle.

	The sweep #2214 asks for, run as a test rather than by hand.  It fails in both
	directions and both are worth knowing:

	* **Something new will not run.**  A generator was offered and is dead on the
	  glass — a control that looks set up and does nothing, which is the fault
	  #2218, #2246 and #2248 all exist to prevent.
	* **Something stopped failing.**  An upstream fix landed.  Take it out of the
	  list, and if the `root` four or the `positive` three have gone, #2249 or
	  #2251 has landed and #2214 may be able to close.

	The reasons are grouped in the constant above; nothing asserts them, because a
	message is upstream's wording to change and the *name* is the fact.
	"""

	broken = _sweep(caplog)

	assert set(broken) == set(WILL_NOT_RUN), (
		f"newly dead: {sorted(set(broken) - set(WILL_NOT_RUN))}; "
		f"no longer dead: {sorted(set(WILL_NOT_RUN) - set(broken))}")
