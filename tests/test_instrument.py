"""An instrument, and the patterns that play it (#5219).

An instrument is what a pattern plays: its name, what it is, and its settings, kept
as a settings block's are.  A pattern names the app's pattern and the instruments it
plays.  Both halves are here: what the adapter declares and does, what the service
keeps, and the store taking a renamed control's settings back.
"""

import json
import pathlib
import typing

import pytest

import superconductor.controls
import superconductor.subsequence_adapter as adapter


class Composition:
	"""The little of a composition an instrument and a pattern touch."""

	def __init__ (self) -> None:
		"""Start with nothing kept and no listeners."""

		self.data: dict[str, typing.Any] = {}
		self.listeners: dict[str, typing.Any] = {}

	def on_event (self, name: str, callback: typing.Any) -> None:
		"""Register a callback the way the real composition does."""

		self.listeners[name] = callback


SETTINGS = [
	adapter.Parameter("glide", "switch", default=False, group="glide"),
	adapter.Parameter("rate", "number", default=24, minimum=0, maximum=127, group="glide"),
]


def _instrument (composition: Composition, sent: list[tuple[str, typing.Any]] | None = None,
                 **overrides: typing.Any) -> adapter.Instrument:
	"""A Minitaur with two settings, each one sent where *sent* can see it."""

	said: dict[str, typing.Any] = {
		"name": "minitaur", "parameters": SETTINGS, "title": "Moog Minitaur",
		"about": [("ch", 6)],
		"on_change": (lambda name, value: sent.append((name, value))) if sent is not None else None,
	}
	said.update(overrides)

	return adapter.Instrument(composition, **said)


# --- the adapter ---------------------------------------------------------------

def test_an_instrument_declares_its_settings_as_a_settings_block_does () -> None:
	"""The same fields in the same shapes, under its own kind and in its own words."""

	declared = _instrument(Composition()).declaration()

	assert declared["type"] == "instrument"
	assert [field["name"] for field in declared["fields"]] == ["glide", "rate"]
	assert [field["group"] for field in declared["fields"]] == ["glide", "glide"]
	assert declared["title"] == "Moog Minitaur"
	assert declared["about"] == [{"label": "ch", "value": "6"}]
	assert "configures" not in declared, "an instrument belongs to nothing; patterns play it"


def test_an_instrument_s_settings_are_kept_where_it_is_named_and_reach_it () -> None:
	"""Held in the composition's data under the instrument's name, and sent to it."""

	composition = Composition()
	sent: list[tuple[str, typing.Any]] = []
	instrument = _instrument(composition, sent)

	assert composition.data["minitaur"] == {"glide": False, "rate": 24}

	assert instrument.apply(["rate"], 90) is True
	assert composition.data["minitaur"]["rate"] == 90
	assert sent == [("rate", 90)]

	with pytest.raises(adapter.Refused):
		instrument.apply(["rate"], 400)


def test_an_instrument_with_nothing_to_set_is_a_name_and_nothing_else () -> None:
	"""A drum machine with no settings worth glass still has to be somewhere to play."""

	declared = adapter.Instrument(Composition(), "drm1", title="Vermona DRM1").declaration()

	assert declared["type"] == "instrument"
	assert declared["fields"] == []


def test_a_pattern_names_its_pattern_and_the_instruments_it_plays () -> None:
	"""Declared by the name its grid and stack already use, playing by control name."""

	composition = Composition()
	minitaur = _instrument(composition)
	pattern = adapter.Pattern(composition, "minitaur", plays=[minitaur], title="Bass")

	assert pattern.name == "minitaur_pattern", "the grid is often called by the pattern's own name"
	assert pattern.declaration() == {"type": "pattern", "pattern": "minitaur", "title": "Bass"}
	assert pattern.snapshot() == {"plays": ["minitaur"]}

	by_name = adapter.Pattern(composition, "lead", plays=["minitaur"], name="lead_out")

	assert by_name.name == "lead_out"
	assert by_name.snapshot() == {"plays": ["minitaur"]}


@pytest.mark.parametrize("kind", [adapter.StepGrid, adapter.NoteGrid])
def test_a_grid_declares_the_pattern_it_plays_in_and_one_playing_in_none_says_nothing (
	kind: type) -> None:
	"""The word a panel joins a grid to its pattern by, and so to what the pattern plays.

	**Read from the adapter's own declaration** rather than written into a fixture,
	which is how this was first missed: the page tests said a grid declares `pattern`,
	and nothing in the adapter sent it.
	"""

	composition = Composition()

	playing = kind(composition, rows=["C2"], steps=16, name="bass", pattern="bass").declaration()
	routed = kind(composition, rows=["C2"], steps=16, name="line").declaration()

	assert playing["pattern"] == "bass"
	assert "pattern" not in routed, "a grid with no pattern of its own claimed one"


def test_a_panel_cannot_move_a_pattern_yet_and_is_told_why () -> None:
	"""Refused with a reason until a pattern can be moved while it plays (#5221)."""

	composition = Composition()
	pattern = adapter.Pattern(composition, "minitaur", plays=[_instrument(composition)])

	with pytest.raises(adapter.Refused, match="set in the composition"):
		pattern.apply(["plays"], [])

	assert pattern.snapshot() == {"plays": ["minitaur"]}


@pytest.mark.parametrize("plays", [["nowhere"], ["grid"]])
def test_a_link_refuses_a_pattern_playing_anything_but_an_instrument_it_offers (plays: list[str]) -> None:
	"""A cable to nothing is said at the composition's first line, not drawn on the glass."""

	composition = Composition()

	with pytest.raises(ValueError, match="not an instrument this link offers"):
		adapter.AppLink(composition, controls=[
			_instrument(composition),
			adapter.StepGrid(composition, rows=["kick"], steps=16, name="grid"),
			adapter.Pattern(composition, "drums", plays=plays),
		])


# --- the store ------------------------------------------------------------------

def _start (path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
            controls: list[adapter.Control]) -> adapter.AppLink:
	"""A link over *controls* that puts back what the store at *path* kept, and dials nothing."""

	monkeypatch.setattr(adapter.AppLink, "_run_link", lambda self: None)

	link = adapter.AppLink(controls[0].composition, controls=controls,
	                       pattern_store=adapter.PatternStore(path),
	                       url="ws://127.0.0.1:1/ws/app")
	link.start()

	return link


def _store (path: pathlib.Path, controls: dict[str, typing.Any]) -> None:
	"""A store as an earlier version of the composition wrote it."""

	path.write_text(json.dumps({"format": adapter.PatternStore.FORMAT, "written": "earlier",
	                            "controls": controls}), encoding="utf-8")


def test_a_settings_block_that_became_an_instrument_keeps_what_was_set_on_it (
	tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
	"""Kept as `minitaur_settings`, put back into the instrument, and no trouble said."""

	path = tmp_path / "piece.patterns.json"
	_store(path, {"minitaur_settings": {"glide": True, "rate": 90}})

	composition = Composition()
	link = _start(path, monkeypatch, [_instrument(composition, formerly=["minitaur_settings"])])

	assert composition.data["minitaur"] == {"glide": True, "rate": 90}
	assert link.status is not None
	assert link.status.state["trouble"] is None, link.status.state


def test_a_former_name_still_in_use_is_not_taken (
	tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
	"""A rename never takes what belongs to a control that is still here."""

	path = tmp_path / "piece.patterns.json"
	_store(path, {"minitaur_settings": {"glide": True, "rate": 90}})

	composition = Composition()
	_start(path, monkeypatch, [
		_instrument(composition, formerly=["minitaur_settings"]),
		adapter.Params(composition, parameters=SETTINGS, data_key="old", name="minitaur_settings"),
	])

	assert composition.data["minitaur"] == {"glide": False, "rate": 24}
	assert composition.data["old"] == {"glide": True, "rate": 90}


def test_what_was_kept_under_the_new_name_wins_over_a_former_one (
	tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
	"""Once an instrument has kept settings of its own, the block it was is no longer them."""

	path = tmp_path / "piece.patterns.json"
	_store(path, {"minitaur": {"glide": True, "rate": 90},
	              "minitaur_settings": {"glide": False, "rate": 10}})

	composition = Composition()
	_start(path, monkeypatch, [_instrument(composition, formerly=["minitaur_settings"])])

	assert composition.data["minitaur"] == {"glide": True, "rate": 90}


# --- the service ------------------------------------------------------------------

def _declared () -> dict[str, typing.Any]:
	"""What the adapter declares for one instrument, a grid and the pattern playing it."""

	composition = Composition()
	minitaur = _instrument(composition)
	controls: list[adapter.Control] = [
		minitaur,
		adapter.StepGrid(composition, rows=["kick"], steps=16, name="grid", pattern="bass"),
		adapter.Pattern(composition, "bass", plays=[minitaur]),
	]

	return {control.name: control.declaration() for control in controls}


def test_the_service_keeps_an_instrument_s_settings_as_a_settings_block_s () -> None:
	"""Checked against the declared bounds, and kept by name."""

	declared = _declared()
	state: dict[str, typing.Any] = {}

	superconductor.controls.apply_change(state, declared, "minitaur/rate", 90)
	superconductor.controls.apply_change(state, declared, "minitaur/glide", True)

	assert state["minitaur"] == {"rate": 90, "glide": True}

	with pytest.raises(superconductor.controls.ControlError):
		superconductor.controls.apply_change(state, declared, "minitaur/rate", 400)


def test_the_service_keeps_which_instruments_a_pattern_plays () -> None:
	"""As the app reports it: instruments it declared, in its order."""

	declared = _declared()
	state: dict[str, typing.Any] = {}

	superconductor.controls.apply_change(state, declared, "bass_pattern/plays", ["minitaur"])
	superconductor.controls.apply_change(state, declared, "bass_pattern/plays", [])

	assert state["bass_pattern"] == {"plays": []}


@pytest.mark.parametrize(("path", "value", "reason"), [
	("bass_pattern/plays", "minitaur", "takes a list"),
	("bass_pattern/plays", ["minitaur", "minitaur"], "names one instrument twice"),
	("bass_pattern/plays", ["grid"], "no instrument this app declared"),
	("bass_pattern/plays", ["nowhere"], "no instrument this app declared"),
	("bass_pattern/pattern", ["minitaur"], "names no part of a pattern"),
])
def test_the_service_refuses_a_pattern_playing_anything_but_its_app_s_instruments (
	path: str, value: typing.Any, reason: str) -> None:
	"""A list, of instruments the app declared, none twice, at `plays` and nowhere else.

	**Each for its own reason**, because the checks stand behind one another: a string
	is refused as a name twice over when nothing asks for a list, so a refusal alone
	could not tell which check refused it.
	"""

	with pytest.raises(superconductor.controls.ControlError, match=reason):
		superconductor.controls.apply_change({}, _declared(), path, value)
