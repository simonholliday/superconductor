"""A pattern's step sequencer on the wire: the rule both halves read, the service's copy, and the adapter (#5210).

The designs are #5217 and #5218, Simon's of 2026-10-22.  The sequencer is
Subsequence's ``subsequence.plugins.sequencers``; nothing here imports it, as the
adapter does not (#1465).  The models below are written out in the shape its
descriptions take at ``c614221``, trimmed to what each test needs, and
`test_sequencer_plays.py` plays the real one.
"""

import copy
import typing

import pytest

import superconductor.controls as controls
import superconductor.protocol as protocol
import superconductor.subsequence_adapter as adapter


LANE_A = {"name": "lane_a", "label": "lane a", "kind": "lane", "count": 8,
          "of": {"kind": "number", "min": 0.0, "max": 1.0}, "required": False, "default": [0.0] * 8}
MODE = {"name": "mode", "label": "mode", "kind": "lane", "count": 8,
        "of": {"kind": "choice", "options": [{"value": "normal", "label": "normal"},
                                             {"value": "skip", "label": "skip"},
                                             {"value": "stop", "label": "stop"}]},
        "required": False, "default": ["normal"] * 8}

MODELS = {
	"clock": {"name": "clock", "label": "clock", "stages": 0, "plays": False,
	          "controls": [{"name": "every", "kind": "number", "min": 1, "max": 64, "step": 1, "default": 1}],
	          "inputs": [], "outputs": [{"name": "out", "kind": "trigger"}], "normals": [], "default_patch": []},
	"moog_960": {"name": "moog_960", "label": "moog 960", "stages": 8, "plays": False,
	             "controls": [LANE_A, MODE,
	                          {"name": "range_a", "kind": "choice", "default": "x4",
	                           "options": [{"value": "x1", "label": "x1"}, {"value": "x2", "label": "x2"},
	                                       {"value": "x4", "label": "x4"}]},
	                          {"name": "timing", "kind": "switch", "default": False},
	                          {"name": "longest", "kind": "number", "min": 1, "max": 16, "step": 1, "default": 8}],
	             "inputs": [{"name": "shift", "kind": "trigger"}, {"name": "timing", "kind": "cv"}],
	             "outputs": [{"name": "lane_a", "kind": "cv"}, {"name": "stage1", "kind": "gate"}],
	             "normals": [{"from": "lane_a", "to": "timing", "when": "timing"}], "default_patch": []},
	"midi_out": {"name": "midi_out", "label": "notes", "stages": 0, "plays": True,
	             "controls": [{"name": "lowest", "kind": "pitch", "default": 36}],
	             "inputs": [{"name": "trigger", "kind": "trigger"}, {"name": "pitch", "kind": "cv"}],
	             "outputs": [], "normals": [], "default_patch": []},
}
"""Three models in the shape the sequencers plugin describes them at c614221."""

CABLES = {"rule": "any output may feed any input", "kinds": ["trigger", "gate", "cv"]}
"""The plugin's rule for cables, as c614221 publishes it: no amount's bounds yet."""

PLAYED = {
	"modules": {
		"clock": {"model": "clock", "settings": {"every": 1}},
		"midi": {"model": "midi_out", "settings": {"lowest": 36}},
		"960": {"model": "moog_960", "settings": {"lane_a": [0.0] * 8, "mode": ["normal"] * 8,
		                                          "range_a": "x4", "timing": False, "longest": 8}},
	},
	"patch": [["clock.out", "960.shift", 1.0], ["clock.out", "midi.trigger", 1.0],
	          ["960.lane_a", "midi.pitch", 1.0]],
}
"""What a 960 played at its last build, in the order the sequencer holds its modules."""

DECLARATION = {"type": "sequencer", "pattern": "lead", "models": MODELS, "cables": CABLES}
MODULES = [{"name": "clock", "model": "clock"}, {"name": "midi", "model": "midi_out"},
           {"name": "960", "model": "moog_960"}]


def _state (revision: int, held: dict[str, typing.Any] | None = None, **fields: typing.Any) -> dict[str, typing.Any]:
	"""A sequencer's ``state()`` at *revision*, as the plugin hands it over."""

	return {"revision": revision, "played": copy.deepcopy(PLAYED), "held": held or {},
	        "taken_back": [], "refused": [], "models": copy.deepcopy(MODELS),
	        "cables": copy.deepcopy(CABLES), **fields}


class Composition:
	"""The little of a composition a sequencer control touches: its tweaks and its mute."""

	def __init__ (self, running: bool = True) -> None:
		"""Running, unless asked to be a composition that has not started yet."""

		self.running = running
		self.tweaks: list[tuple[str, dict[str, typing.Any]]] = []
		self.muted: list[str] = []

	def tweak (self, name: str, **kwargs: typing.Any) -> None:
		"""Write a tweak down, refusing as Subsequence does before its patterns run."""

		if not self.running:
			raise ValueError(f"Pattern '{name}' not found. Available: []")

		self.tweaks.append((name, copy.deepcopy(kwargs)))

	def mute (self, name: str) -> None:
		"""Write the mute down."""

		self.muted.append(name)

	def unmute (self, name: str) -> None:
		"""Write the unmute down."""

		self.muted.remove(name)


class Watch:
	"""`sequencers.on_build`, writing down who registered."""

	def __init__ (self) -> None:
		"""Nobody yet."""

		self.callbacks: list[typing.Any] = []

	def __call__ (self, composition: typing.Any, callback: typing.Any) -> None:
		"""Keep the callback, as the plugin keeps its listeners."""

		self.callbacks.append(callback)


class Link:
	"""A link that writes down what it was told instead of saying it."""

	def __init__ (self) -> None:
		"""Nothing said yet."""

		self.reports: list[tuple[str, typing.Any]] = []
		self.events: list[tuple[str, dict[str, typing.Any]]] = []
		self.declared = 0

	def report (self, path: str, value: typing.Any) -> None:
		"""Write down one thing the app did of its own accord."""

		self.reports.append((path, value))

	def happened (self, name: str, **fields: typing.Any) -> None:
		"""Write down one event."""

		self.events.append((name, fields))

	def redeclare (self) -> None:
		"""Count one declaration asked for."""

		self.declared += 1


def _sequencer (running: bool = True) -> tuple[adapter.Sequencer, Composition, Watch, Link]:
	"""A sequencer control for the pattern ``lead``, attached to a link that writes things down."""

	composition = Composition(running)
	watch = Watch()
	link = Link()
	sequencer = adapter.Sequencer(composition, "lead", watch=watch)
	sequencer.attach(typing.cast(adapter.AppLink, link))

	return sequencer, composition, watch, link


# --- the rule both halves read ----------------------------------------------

@pytest.mark.parametrize(("rest", "value"), [
	(["settings", "960", "lane_a", "2"], 0.4),
	(["settings", "960", "mode", "7"], "skip"),
	(["settings", "960", "range_a"], "x2"),
	(["settings", "960", "timing"], True),
	(["settings", "960", "longest"], 4),
	(["settings", "midi", "lowest"], 40),
	(["cords", "960.lane_a", "960.timing"], 0.5),
	(["cords", "960.stage1", "midi.trigger"], -1),
	(["settings", "960", "lane_a", "2"], None),
	(["cords", "clock.out", "960.shift"], 0),
])
def test_a_stage_a_setting_and_a_cord_are_each_one_thing_a_panel_may_set (
	rest: list[str], value: typing.Any) -> None:
	"""Every shape a panel sends, including null, which hands an entry back, and 0, which pulls out the code's cord."""

	assert protocol.sequencer_refusal(DECLARATION, MODULES, rest, value) is None


@pytest.mark.parametrize(("rest", "value", "words"), [
	(["settings", "960", "lane_a"], [0.1] * 8, "is set a stage at a time"),
	(["settings", "960", "range_a", "0"], "x2", "is one value, not a lane"),
	(["settings", "960", "lane_a", "8"], 0.4, "no stage '8'"),
	(["settings", "960", "lane_a", "02"], 0.4, "no stage '02'"),
	(["settings", "960", "lane_a", "2"], 1.5, "is not above 1.0"),
	(["settings", "960", "lane_a", "2"], True, "is a number"),
	(["settings", "960", "lane_a", "2"], float("nan"), "is a number"),
	(["settings", "960", "mode", "2"], "reverse", "no option called 'reverse'"),
	(["settings", "960", "timing"], 1, "takes true or false"),
	(["settings", "midi", "lowest"], 40.5, "a whole number"),
	(["settings", "midi", "lowest"], 128, "is not above 127"),
	(["settings", "962", "lane_a", "0"], 0.1, "no module called '962'"),
	(["settings", "960", "lane_z", "0"], 0.1, "no control called 'lane_z'"),
	(["settings", "960"], 0.1, "is addressed as"),
	(["cords", "960.timing", "960.lane_a"], 1.0, "no output called 'timing'"),
	(["cords", "960.lane_a", "midi.lowest"], 1.0, "no input called 'lowest'"),
	(["cords", "960.lane_a", "midi.pitch"], True, "is a number"),
	(["cords", "960.lane_a"], 1.0, "is addressed as"),
	(["played"], {}, "the rest is the app's to report"),
])
def test_what_a_panel_may_not_set_is_refused_in_words (
	rest: list[str], value: typing.Any, words: str) -> None:
	"""Refused rather than clamped, with a sentence a person holding a knob can read."""

	why = protocol.sequencer_refusal(DECLARATION, MODULES, rest, value)

	assert why is not None and words in why, why


def test_everything_the_glass_holds_is_handed_back_in_one_set () -> None:
	""""Back to the code" (#5218): ``held`` emptied, and only emptied, so a dozen entries
	wake the clock once and the rest is still set an entry at a time (D3)."""

	assert protocol.sequencer_refusal(DECLARATION, MODULES, ["held"], {}) is None

	others: list[typing.Any] = [None, {"patch": []}, {"modules": {"960": {"settings": {"longest": 4}}}}]

	for value in others:
		why = protocol.sequencer_refusal(DECLARATION, MODULES, ["held"], value)

		assert why is not None and "sets the rest an entry at a time" in why, (value, why)

	assert "the rest is the app's to report" in (
		protocol.sequencer_refusal(DECLARATION, MODULES, ["held", "patch"], {}) or "")

	held = protocol.sequencer_hold({}, ["settings", "960", "lane_a", "2"], 0.4)
	held = protocol.sequencer_hold(held, ["cords", "960.lane_a", "960.timing"], 0.5)

	assert protocol.sequencer_hold(held, ["held"], {}) == {}


def test_a_null_must_still_name_something_that_exists () -> None:
	"""A hand-back is checked as an address, so a stage that is not there cannot be handed back."""

	assert "no stage '9'" in (protocol.sequencer_refusal(
		DECLARATION, MODULES, ["settings", "960", "lane_a", "9"], None) or "")


def test_a_cord_s_amount_is_bounded_only_where_the_app_published_bounds () -> None:
	"""c614221 publishes none; the A-list publishes −4 to 4, and then it binds."""

	rest = ["cords", "960.lane_a", "midi.pitch"]
	bounded = {**DECLARATION, "cables": {**CABLES, "amount": {"min": -4.0, "max": 4.0, "default": 1.0}}}

	assert protocol.sequencer_refusal(DECLARATION, MODULES, rest, 12.0) is None
	assert "is not above 4.0" in (protocol.sequencer_refusal(bounded, MODULES, rest, 12.0) or "")
	assert protocol.sequencer_refusal(bounded, MODULES, rest, -4.0) is None


def test_a_stage_and_a_cord_are_held_as_the_sequencer_reads_them () -> None:
	"""A lane's stages keyed by their index, a setting by its name, a cord as [from, to, amount]."""

	held = protocol.sequencer_hold({}, ["settings", "960", "lane_a", "2"], 0.4)
	held = protocol.sequencer_hold(held, ["settings", "960", "range_a"], "x2")
	held = protocol.sequencer_hold(held, ["cords", "960.lane_a", "960.timing"], 0.5)

	assert held == {"modules": {"960": {"settings": {"lane_a": {"2": 0.4}, "range_a": "x2"}}},
	                "patch": [["960.lane_a", "960.timing", 0.5]]}


def test_handing_back_leaves_nothing_empty_behind () -> None:
	"""Unset is an absent key, never an empty one (#2518), so the document comes back to {}."""

	held = protocol.sequencer_hold({}, ["settings", "960", "lane_a", "2"], 0.4)
	held = protocol.sequencer_hold(held, ["cords", "clock.out", "960.shift"], 0)

	held = protocol.sequencer_hold(held, ["settings", "960", "lane_a", "2"], None)
	held = protocol.sequencer_hold(held, ["cords", "clock.out", "960.shift"], None)

	assert held == {}


def test_a_cord_set_again_keeps_its_place_and_the_held_document_is_never_edited () -> None:
	"""The order cords were patched in survives a change of amount, and the caller's copy is untouched."""

	held = {"patch": [["clock.out", "960.shift", 1.0], ["960.lane_a", "midi.pitch", 1.0]]}
	before = copy.deepcopy(held)

	again = protocol.sequencer_hold(held, ["cords", "clock.out", "960.shift"], 0.25)

	assert again["patch"] == [["clock.out", "960.shift", 0.25], ["960.lane_a", "midi.pitch", 1.0]]
	assert held == before


# --- the service's copy -----------------------------------------------------

def _service () -> tuple[dict[str, typing.Any], dict[str, typing.Any]]:
	"""The service's state for an app holding one sequencer, as its declaration left it."""

	state = {"lead": {"modules": copy.deepcopy(MODULES), "played": copy.deepcopy(PLAYED),
	                  "held": {}, "taken_back": [], "refused": [], "enabled": True}}

	return state, {"lead": copy.deepcopy(DECLARATION)}


def test_the_service_places_a_panel_s_setting_where_the_app_holds_it () -> None:
	"""In ``held``, by the same rule the app used, so a late panel is told what the app has."""

	state, declared = _service()

	controls.apply_change(state, declared, "lead/settings/960/lane_a/2", 0.4)
	controls.apply_change(state, declared, "lead/cords/960.lane_a/960.timing", 0.5)

	assert state["lead"]["held"] == {"modules": {"960": {"settings": {"lane_a": {"2": 0.4}}}},
	                                 "patch": [["960.lane_a", "960.timing", 0.5]]}


def test_the_service_keeps_what_only_the_app_writes_whole () -> None:
	"""What played, the modules and the notices, replaced whole and copied."""

	state, declared = _service()
	notice = [{"revision": 4, "entries": {"modules": {"960": {"settings": {"lane_a": {"2": True}}}}}}]

	controls.apply_change(state, declared, "lead/taken_back", notice)
	notice[0]["revision"] = 99

	assert state["lead"]["taken_back"][0]["revision"] == 4


def test_the_service_takes_everything_handed_back_as_the_app_reports_it () -> None:
	"""The app confirms ``held`` emptied at the path the panel set, and the copy follows."""

	state, declared = _service()

	controls.apply_change(state, declared, "lead/settings/960/lane_a/2", 0.4)
	controls.apply_change(state, declared, "lead/held", {})

	assert state["lead"]["held"] == {}


@pytest.mark.parametrize(("path", "value", "words"), [
	("lead/settings/960/lane_a/2", 1.5, "is not above 1.0"),
	("lead/modules", [{"name": "960"}], "its name and its model"),
	("lead/played", [], "takes a dict"),
	("lead/where", 1, "does not name a sequencer's settings"),
])
def test_the_service_refuses_what_the_app_could_not_have_reported (
	path: str, value: typing.Any, words: str) -> None:
	"""In the words the app would have used, where the rule is the shared one."""

	state, declared = _service()

	with pytest.raises(controls.ControlError, match=words):
		controls.apply_change(state, declared, path, value)


# --- the adapter --------------------------------------------------------------

def test_it_listens_once_and_hears_only_its_own_pattern () -> None:
	"""One callback for the composition, and a build of another pattern changes nothing here."""

	sequencer, _, watch, link = _sequencer()

	assert len(watch.callbacks) == 1

	watch.callbacks[0]("bass", _state(1), {"cycle": {}, "modules": {}})

	assert sequencer.snapshot()["modules"] == []
	assert link.declared == 0 and link.events == []


def test_the_first_build_declares_again_with_the_models_it_brought () -> None:
	"""Before it, the declaration is empty, because only a build says what the sequencer is."""

	sequencer, _, watch, link = _sequencer()

	assert sequencer.declaration()["models"] == {}

	watch.callbacks[0]("lead", _state(1), None)

	assert link.declared == 1
	assert sorted(sequencer.declaration()["models"]) == ["clock", "midi_out", "moog_960"]
	assert link.reports == []


def test_a_later_build_reports_only_what_moved () -> None:
	"""What played moved, so it is reported whole; nothing else did, so nothing else is."""

	sequencer, _, watch, link = _sequencer()
	watch.callbacks[0]("lead", _state(1), None)

	moved = _state(2)
	moved["played"]["modules"]["960"]["settings"]["range_a"] = "x2"

	watch.callbacks[0]("lead", moved, None)

	assert link.declared == 1
	assert [path for path, _ in link.reports] == ["lead/played"]


def test_a_build_that_moved_nothing_says_nothing () -> None:
	"""The A-list's plugin sends no state then, and c614221's sends the same one: both are silence."""

	sequencer, _, watch, link = _sequencer()
	watch.callbacks[0]("lead", _state(1), None)

	watch.callbacks[0]("lead", None, None)
	watch.callbacks[0]("lead", _state(1), None)

	assert link.reports == [] and link.declared == 1


def test_where_each_module_was_is_an_event_and_kept_nowhere () -> None:
	"""Once a cycle, as the plugin hands it over (#1965)."""

	sequencer, _, watch, link = _sequencer()
	playing = {"cycle": {"start_beat": 128.0, "steps": 16, "step_beats": 0.25},
	           "modules": {"960": {"positions": {"stage": [None, 0, 0, 1]}}}}

	watch.callbacks[0]("lead", _state(1), playing)

	assert link.events == [("playing", {"control": "lead", **playing})]
	assert "playing" not in sequencer.snapshot() and "playing" not in sequencer.kept()


def test_the_modules_keep_the_sequencer_s_order () -> None:
	"""A list, because the 960's name is an integer-like key and JavaScript would put it first."""

	sequencer, _, watch, _ = _sequencer()
	watch.callbacks[0]("lead", _state(1), None)

	assert [one["name"] for one in sequencer.snapshot()["modules"]] == ["clock", "midi", "960"]


def test_a_change_reaches_the_pattern_whole_with_the_revision_it_was_made_from () -> None:
	"""The whole overlay, every time, and the revision keeps out what the sequencer has taken back."""

	sequencer, composition, watch, _ = _sequencer()
	watch.callbacks[0]("lead", _state(3), None)

	assert sequencer.apply(["settings", "960", "lane_a", "2"], 0.4)
	assert sequencer.apply(["cords", "960.lane_a", "960.timing"], 0.5)

	assert composition.tweaks[-1] == ("lead", {"sequencer": {
		"modules": {"960": {"settings": {"lane_a": {"2": 0.4}}}},
		"patch": [["960.lane_a", "960.timing", 0.5]],
		"revision": 3}})


def test_handing_everything_back_sends_an_empty_overlay () -> None:
	"""Which the sequencer reads as nothing held, and clears its tweak for."""

	sequencer, composition, watch, _ = _sequencer()
	watch.callbacks[0]("lead", _state(3), None)
	sequencer.apply(["settings", "960", "lane_a", "2"], 0.4)

	assert sequencer.apply(["settings", "960", "lane_a", "2"], None)
	assert composition.tweaks[-1] == ("lead", {"sequencer": {"revision": 3}})

	assert not sequencer.apply(["settings", "960", "lane_a", "2"], None)


def test_back_to_the_code_hands_the_pattern_an_empty_overlay_once () -> None:
	"""One tweak for everything, with the revision, and nothing more when nothing is held."""

	sequencer, composition, watch, _ = _sequencer()
	watch.callbacks[0]("lead", _state(3), None)
	sequencer.apply(["settings", "960", "lane_a", "2"], 0.4)
	sequencer.apply(["cords", "960.lane_a", "960.timing"], 0.5)
	told = len(composition.tweaks)

	assert sequencer.apply(["held"], {})
	assert composition.tweaks[told:] == [("lead", {"sequencer": {"revision": 3}})]
	assert sequencer.snapshot()["held"] == {}

	assert not sequencer.apply(["held"], {})
	assert len(composition.tweaks) == told + 1


def test_a_refused_change_is_said_in_the_rule_s_own_words () -> None:
	"""The app and the service refuse with one sentence (#2519)."""

	sequencer, composition, watch, _ = _sequencer()
	watch.callbacks[0]("lead", _state(1), None)
	words = protocol.sequencer_refusal(DECLARATION, MODULES, ["settings", "960", "mode", "2"], "reverse")

	with pytest.raises(adapter.Refused) as refused:
		sequencer.apply(["settings", "960", "mode", "2"], "reverse")

	assert str(refused.value) == words
	assert composition.tweaks == []


def test_what_the_sequencer_still_holds_is_what_the_next_change_is_made_on () -> None:
	"""D3: the code changed stage 2, the sequencer took it back, so the next change does not put it back."""

	sequencer, composition, watch, link = _sequencer()
	watch.callbacks[0]("lead", _state(1), None)
	sequencer.apply(["settings", "960", "lane_a", "2"], 0.4)
	sequencer.apply(["settings", "960", "range_a"], "x2")

	taken = [{"revision": 2, "entries": {"modules": {"960": {"settings": {"lane_a": {"2": True}}}}}}]
	watch.callbacks[0]("lead", _state(2, held={"modules": {"960": {"settings": {"range_a": "x2"}}}},
	                                taken_back=taken), None)

	assert ("lead/taken_back", taken) in link.reports

	sequencer.apply(["settings", "960", "timing"], True)

	assert composition.tweaks[-1] == ("lead", {"sequencer": {
		"modules": {"960": {"settings": {"range_a": "x2", "timing": True}}}, "revision": 2}})


def test_what_is_kept_is_what_the_glass_holds_and_never_what_played () -> None:
	"""A person's settings are intent; what the code played comes back on every start (#1965)."""

	sequencer, _, watch, _ = _sequencer()
	watch.callbacks[0]("lead", _state(1), None)
	sequencer.apply(["settings", "960", "lane_a", "2"], 0.4)

	assert sequencer.kept() == {"held": {"modules": {"960": {"settings": {"lane_a": {"2": 0.4}}}}},
	                            "enabled": True}


def test_a_restored_overlay_waits_for_the_pattern_to_run () -> None:
	"""Subsequence refuses a tweak before `play()`, so it is owed until the patterns start."""

	sequencer, composition, _, _ = _sequencer(running=False)
	held = {"modules": {"960": {"settings": {"lane_a": {"2": 0.4}}}}}

	assert sequencer.restore({"held": held, "enabled": True}) == []
	assert composition.tweaks == []

	composition.running = True
	sequencer.started()

	assert composition.tweaks == [("lead", {"sequencer": held})]

	sequencer.started()

	assert len(composition.tweaks) == 1


def test_a_change_the_pattern_refused_is_handed_over_at_its_next_build () -> None:
	"""A pattern joins the running ones only once its first build is done, so a change made then is owed."""

	sequencer, composition, watch, _ = _sequencer(running=False)
	watch.callbacks[0]("lead", _state(1), None)

	assert sequencer.apply(["settings", "960", "lane_a", "2"], 0.4)
	assert composition.tweaks == []

	composition.running = True
	watch.callbacks[0]("lead", None, None)

	assert composition.tweaks == [("lead", {"sequencer": {
		"modules": {"960": {"settings": {"lane_a": {"2": 0.4}}}}, "revision": 1}})]

	watch.callbacks[0]("lead", None, None)

	assert len(composition.tweaks) == 1


def test_a_store_that_kept_something_else_is_said () -> None:
	"""Never half-taken and never dropped in silence."""

	sequencer, _, _, _ = _sequencer()

	assert sequencer.restore(["not", "a", "sequencer"]) == [
		"lead was kept as something other than a sequencer's settings"]


def test_the_mute_is_the_pattern_s () -> None:
	"""As every control's is: the notes stay and stop being heard."""

	sequencer, composition, _, _ = _sequencer()

	assert sequencer.apply(["enabled"], False)
	assert composition.muted == ["lead"]
	assert sequencer.snapshot()["enabled"] is False


def test_only_the_app_writes_what_played () -> None:
	"""A panel sets settings and cords, and nothing else."""

	sequencer, _, watch, _ = _sequencer()
	watch.callbacks[0]("lead", _state(1), None)

	with pytest.raises(adapter.Refused, match="its app's to report"):
		sequencer.apply(["played"], {})
