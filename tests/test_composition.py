"""The rig's own composition, where an instrument definition meets the panel.

Nothing here tests the Superconductor package — it tests the join a composition
has to make, and it lives in this suite because the join has a trap in it that
would otherwise be found by a chord going silent on a Matriarch.

Importing `compositions/drm1_grid.py` is safe: a Subsequence composition resolves
its devices lazily and opens no MIDI port until `play()`, which nothing here
calls.  The file sorts before `test_page.py`, which matters — Playwright's sync
API holds the main thread's loop for the rest of the session once a page test has
run, and anything after it that wants a loop of its own fails.
"""

import importlib.util
import logging
import random
import re
import sys
import types
import typing

import pytest

import pymidiinstrumentdefs
import pymidiinstrumentdefs.definition
import subsequence.pattern
import subsequence.pattern_builder

import superconductor.service
import superconductor.subsequence_adapter


def _composition () -> typing.Any:
	"""The rig's composition, imported once and shared."""

	if "drm1_grid" not in sys.modules:
		spec = importlib.util.spec_from_file_location(
			"drm1_grid", "compositions/drm1_grid.py")
		assert spec is not None and spec.loader is not None
		module = importlib.util.module_from_spec(spec)
		sys.modules["drm1_grid"] = module
		spec.loader.exec_module(module)

	return sys.modules["drm1_grid"]


@pytest.fixture (scope="module")
def rig () -> typing.Any:
	"""The composition module, loaded but not playing."""

	return _composition()


def test_a_stated_voice_count_is_used_as_it_stands (rig: typing.Any) -> None:
	"""A Minitaur says one voice, and one voice is what the grid enforces."""

	assert rig._voice_count(rig.MINITAUR) == 1
	assert rig.MINITAUR.voice.polyphony == 1


def test_an_unknown_voice_count_is_not_quietly_read_as_unlimited () -> None:
	"""**The trap this guard exists for**, on the instrument it is aimed at.

	`pymidiinstrumentdefs` uses ``polyphony = None`` for *nobody has established
	it*; a note grid uses ``voices = None`` for *as many as you like*.  A
	Matriarch's voicing is a front-panel switch and control change 94 with no
	documented power-on default, so its definition says null — and a pass-through
	would draw a five-note chord on a four-voice instrument and say nothing.
	"""

	rig = _composition()
	matriarch = pymidiinstrumentdefs.load("moog/matriarch")

	assert matriarch.voice.polyphony is None
	assert matriarch.voice.voicing_modes == (1, 2, 4)

	with pytest.raises(ValueError, match="has to be told which to assume"):
		rig._voice_count(matriarch)


def test_a_switchable_instrument_may_be_told_which_mode_to_assume () -> None:
	"""Told, rather than guessed — and only a mode it actually has."""

	rig = _composition()
	matriarch = pymidiinstrumentdefs.load("moog/matriarch")

	assert rig._voice_count(matriarch, when_switchable=4) == 4

	with pytest.raises(ValueError, match="no 3-voice mode"):
		rig._voice_count(matriarch, when_switchable=3)


def test_an_instrument_that_states_nothing_at_all_is_unlimited () -> None:
	"""The only case where None may become None: neither a count nor any modes.

	That is a different fact from "unknown", which is the whole distinction, so
	it gets its own case rather than being assumed to fall out of the others.
	"""

	rig = _composition()
	silent = types.SimpleNamespace(
		model=types.SimpleNamespace(name="Nothing In Particular"),
		voice=types.SimpleNamespace(polyphony=None, voicing_modes=()))

	assert rig._voice_count(silent) is None


def test_a_switch_sends_the_state_the_definition_names_not_the_word_on (
	rig: typing.Any) -> None:
	"""Legato glide is `always` and `legato_only`, and neither is spelled "on".

	A bool has to pick by the *order* the definition gives — ascending, so the
	second is the far end — because mapping True to a literal "on" raises a
	KeyError on the first instrument whose switch is named after what it does.
	"""

	assert rig.MINITAUR.controls["legato_glide"].states == ["always", "legato_only"]

	assert rig._cc_value("legato_glide", False) == 31
	assert rig._cc_value("legato_glide", True) == 95


def test_a_bands_value_is_the_middle_of_the_band_and_not_its_edge (
	rig: typing.Any) -> None:
	"""So a value that drifts by one does not become a different setting."""

	assert rig._cc_value("glide_type", "lcr") == 21
	assert rig._cc_value("glide_type", "lct") == 63
	assert rig._cc_value("glide_type", "exp") == 106


def test_local_control_is_the_specifications_switch_and_takes_0_or_127 (
	rig: typing.Any) -> None:
	"""It is not in the Minitaur's definition, because it is not the Minitaur's.

	Control change 122 means local control on every instrument ever built, so it
	is a specification fact.  Its absence from the corpus is the three-tier split
	working rather than a gap, and it is the one switch with no band to sit in
	the middle of (#2081).
	"""

	assert "local_control" not in rig.BASS_CONTROLS
	assert rig._cc_value("local_control", True) == 127
	assert rig._cc_value("local_control", False) == 0


def test_a_controls_kind_is_derived_from_its_bands_rather_than_declared (
	rig: typing.Any) -> None:
	"""No values means continuous, two a switch, three or more a choice.

	Derived here as well as upstream, so a corrected band table changes what the
	panel draws without this composition being edited at all.
	"""

	drawn = {p.name: p.kind for p in
	         [rig._panel_parameter(*setting) for setting in rig.BASS_SETTINGS]}

	assert drawn["glide"] == "switch"
	assert drawn["glide_type"] == "choice"
	assert drawn["glide_rate"] == "number"


def test_a_range_outside_what_the_instrument_sounds_is_refused_at_import (
	rig: typing.Any) -> None:
	"""The check is at module level, so this asserts the fact it rests on.

	A Minitaur ignores a note above 72 rather than playing it wrong, so a range
	set an octave too high draws a grid that works perfectly and makes no sound.
	"""

	low, high = rig.MINITAUR.voice.note_range

	assert (low, high) == (0, 72)
	assert all(low <= rig.midi_notes.name_to_note(row) <= high for row in rig.BASS_RANGE)


# --- the Matriarch, and the ceiling it is given -----------------------------

def test_the_chord_grid_is_given_the_ceiling_not_an_unlimited_count (
	rig: typing.Any) -> None:
	"""#2172: enforce the most the instrument can do, claim nothing.

	The Matriarch states no polyphony at all, so this is the one instrument on
	the rig where the guard's `when_switchable` is load-bearing rather than
	decorative.
	"""

	assert rig.MATRIARCH.voice.polyphony is None
	assert rig.CHORD_VOICES == 4 == max(rig.MATRIARCH.voice.voicing_modes)

	assert rig.link.controls["chords"].declaration()["voices"] == 4


def test_the_voicing_band_is_paired_with_the_count_it_selects (
	rig: typing.Any) -> None:
	"""An inference the composition makes, so it is worth asserting rather than trusting.

	The definition states the voice counts in `voicing_modes` and names the
	bands of control change 94 separately, and says nowhere which names which.
	Pairing two ascending lists is sound and is still a guess about a format,
	so the wrong pairing should fail here rather than send a Matriarch quietly
	into one-voice mode.
	"""

	assert rig.CHORD_VOICING == {1: "one_voice", 2: "two_voice", 4: "four_voice"}

	voicing = rig.MATRIARCH.controls["paraphony_voice_mode"]

	assert voicing.cc == 94
	assert voicing.value_for(rig.CHORD_VOICING[rig.CHORD_VOICES]) == 106


def test_the_chord_range_is_inside_what_the_matriarch_sounds (rig: typing.Any) -> None:
	"""The same check the bass gets, and it has to be made per instrument.

	A Minitaur stops at note 72 and a Matriarch does not, so the limit is the
	definition's to state and this file's to stay inside.
	"""

	low, high = rig.MATRIARCH.voice.note_range

	assert (low, high) == (0, 127)
	assert all(low <= rig.midi_notes.name_to_note(row) <= high for row in rig.CHORD_RANGE)


def test_a_chord_note_is_placed_in_steps_rather_than_in_sub_steps (
	rig: typing.Any) -> None:
	"""The bass divides a step six ways; the chords do not, and the difference is
	deliberate rather than an oversight.

	A chord wants to land on the beat, and nothing has yet asked for one between
	two of them.  Asserted because `default_length` is counted in this grid's own
	positions, so the two numbers only mean the same thing while divisions is 1.
	"""

	declared = rig.link.controls["chords"].declaration()

	assert declared["divisions"] == 1
	assert declared["default_length"] == rig.CHORD_LENGTH == 2


# --- transposition on the rig's own instruments (#2144) ---------------------

def test_the_label_and_the_player_agree_about_what_can_sound (
	rig: typing.Any) -> None:
	"""**One function decides, so they cannot differ.**

	A row the label calls unreachable and the player sounds anyway would be the
	glass and the ears disagreeing — which is the exact fault transposition was
	designed to prevent, arriving by the back door.
	"""

	named = rig._relabel(rig.BASS_NOTE_MAP, rig.MINITAUR)

	for semitones in (-24, -7, 0, 5, 24):
		for row in rig.BASS_RANGE:
			sounds = rig._sounding(row, semitones, rig.BASS_NOTE_MAP, rig.MINITAUR)

			assert (named(row, semitones) is None) == (sounds is None), (
				f"{row} at {semitones}: the label and the player disagree")


def test_a_bassline_pushed_past_the_minitaurs_ceiling_is_marked_not_played (
	rig: typing.Any) -> None:
	"""The failure this whole design exists to make visible.

	A Minitaur ignores a note above 72 rather than playing it wrong, so a
	transposed bassline goes *silent* with every cell still lit.  The top of
	BASS_RANGE is C3, note 48, so it takes a big move to reach — which is the
	point: it is reachable, and nothing else would say so.
	"""

	named = rig._relabel(rig.BASS_NOTE_MAP, rig.MINITAUR)
	top = rig.BASS_RANGE[-1]

	assert rig.midi_notes.name_to_note(top) == 48
	assert named(top, 24) == "C5", "two octaves up is still inside a Minitaur"
	assert named(top, 25) is None, "a semitone above 72 should sound nothing"
	assert rig._sounding(top, 25, rig.BASS_NOTE_MAP, rig.MINITAUR) is None


def test_a_matriarch_has_no_ceiling_to_reach (rig: typing.Any) -> None:
	"""Which is why the range check has to be per instrument rather than a rule.

	The same transposition that silences a Minitaur is unremarkable here, and
	only the definition knows the difference.
	"""

	named = rig._relabel(rig.CHORD_NOTE_MAP, rig.MATRIARCH)
	top = rig.CHORD_RANGE[-1]

	assert named(top, 24) is not None
	assert rig.MATRIARCH.voice.note_range == (0, 127)


def test_both_pitched_grids_offer_a_transposition (rig: typing.Any) -> None:
	"""And the drum grid does not, because transposing a drum map is nonsense."""

	for name in ("bass", "chords"):
		assert "transpose_range" in rig.link.controls[name].declaration()

	assert "transpose_range" not in rig.link.controls["grid"].declaration()


def test_every_control_this_composition_declares_reaches_a_page (rig: typing.Any) -> None:
	"""A control declared and put on no page is invisible, and nothing says so.

	It is not an error anywhere: the app declares it, the service holds it, the
	panel is told about it, and it is simply never drawn.  The only symptom is
	somebody looking for a block that was there last week.

	The transport is the one exception and is not a part — it is chrome, drawn
	on the header bar whatever page is open, which is why it names no page and
	why this asks for it by type rather than by name.
	"""

	drawn = {name for name, control in rig.link.controls.items()
	         if not isinstance(control, superconductor.subsequence_adapter.Transport)}
	placed = {part for page in rig.link.pages for part in page.parts}

	assert drawn - placed == set(), f"declared and on no page: {sorted(drawn - placed)}"
	assert placed - drawn == set(), f"on a page and never declared: {sorted(placed - drawn)}"


def test_the_page_set_still_fits_the_row_of_named_buttons (rig: typing.Any) -> None:
	"""Past `PAGE_BUTTONS` the client stops drawing page names and offers
	previous-and-next with a counter instead.

	That is correct behaviour and it is also how this rig came to be showing
	"‹ Pattern 1 1/8 ›" — eight pages, no names, on the one control whose whole
	job is saying which page you are on.  A page set is cheap to add to, so the
	limit is worth failing against rather than rediscovering on the glass.

	The number is read out of the client rather than written here, because two
	places holding one number is how they come to disagree.
	"""

	source = (superconductor.service.CLIENT_DIR / "app.js").read_text(encoding="utf-8")
	limit = re.search(r"^const PAGE_BUTTONS = (\d+);$", source, re.MULTILINE)

	assert limit, "the client no longer names a page-button limit"

	assert len(rig.link.pages) <= int(limit.group(1)), (
		f"{len(rig.link.pages)} pages is past {limit.group(1)}, so the panel will"
		f" draw a counter instead of their names")


def _instrument (**controls: typing.Any) -> typing.Any:
	"""A definition holding only *controls*, for a shape no rig instrument has."""

	return types.SimpleNamespace(
		model=types.SimpleNamespace(name="Somebody's Synth"), controls=controls)


def test_a_choice_the_definition_names_no_states_for_is_drawn_as_a_number (
	rig: typing.Any) -> None:
	"""Three of the Matriarch's arpeggiator controls were declared `choice` and
	named no states, until `pymidiinstrumentdefs` 0.1.1 gave them their bands
	(#2203).

	Drawn as declared they came out as three empty rows on the glass: a label,
	and then nothing at all to press.  A definition is a *report* about a
	particular model and reports are wrong in the wild — one written for
	somebody's own synth most of all — so the kind is taken from what is
	actually there rather than from what is claimed.

	No bundled definition has one any more, which is why this builds its own
	rather than finding one: it used to search the Matriarch and assert it found
	something, and that assertion is what said the corpus had moved on.
	"""

	silent = pymidiinstrumentdefs.Control(
		name="arp_mode", label="Arp Mode", cc=30,
		kind_override=pymidiinstrumentdefs.CHOICE)

	assert silent.kind == pymidiinstrumentdefs.CHOICE and silent.states == []

	drawn = rig._panel_parameter("mode", "arp_mode", "Mode", 0,
	                             instrument=_instrument(arp_mode=silent))

	assert drawn.kind == "number", "a choice with nothing to choose draws as nothing"
	assert (drawn.minimum, drawn.maximum) == (0, 127)


def test_the_matriarchs_arpeggiator_offers_the_bands_its_manual_prints (
	rig: typing.Any) -> None:
	"""Mode, pattern and range, from the table at p. 74 of the manual (#2203).

	They were numbers from 0 to 127 while the definition named no states, and
	each opened at `0`.  So each opens now at the band `0` falls in — the same
	setting on the instrument, spelled the way a choice is spelled.
	"""

	drawn = {parameter.name: parameter
	         for parameter in (rig._panel_parameter(*setting, instrument=rig.MATRIARCH)
	                           for setting in rig.CHORD_SETTINGS if setting[0] != "voices")}

	offered = {panel: [value for value, _ in drawn[panel].options]
	           for panel in ("arp_mode", "arp_pattern", "arp_range")}

	assert offered == {
		"arp_mode": ["arp", "seq", "rec"],
		"arp_pattern": ["order", "fw_bw", "random"],
		"arp_range": ["one", "two", "three"],
	}

	for panel in offered:
		assert drawn[panel].kind == "choice"
		assert drawn[panel].default == rig.CHORD_CONTROLS[panel].name_for(0), (
			f"{panel} no longer opens where the Matriarch did")

	# The middle of 0-42, 43-84 and 85-127, as every band is sent.
	assert [rig._cc_value("arp_mode", state, rig.CHORD_CONTROLS)
	        for state in offered["arp_mode"]] == [21, 63, 106]


def test_a_control_whose_manual_prints_exact_values_is_sent_exactly_those (
	rig: typing.Any) -> None:
	"""`choices` rather than bands (#2467): a manual printing `0 = Base, 1 = Both,
	2 = 8va` means 0, 1 and 2, and a number between them means nothing.

	**Reading `values` alone sees no states in one**, so it drew the control as a
	dial from 0 to 127 — and sent a two-state one's `True` as 1, by accident of
	`int()`, where the instrument wanted 64.  `states` names either shape and the
	definition's `value_for` knows which it holds.
	"""

	octave = pymidiinstrumentdefs.Control(
		name="octave", label="Octave", cc=20, choices={"base": 0, "both": 1, "up": 2})
	sync = pymidiinstrumentdefs.Control(
		name="sync", label="Sync", cc=21, choices={"free": 0, "synced": 64})
	synth = _instrument(octave=octave, sync=sync)

	drawn = rig._panel_parameter("octave", "octave", "Octave", "base", instrument=synth)

	assert drawn.kind == "choice"
	assert [value for value, _ in drawn.options] == ["base", "both", "up"]
	assert [rig._cc_value("octave", state, synth.controls)
	        for state in ("base", "both", "up")] == [0, 1, 2]

	assert rig._panel_parameter("sync", "sync", "Sync", None, instrument=synth).kind == "switch"
	assert rig._cc_value("sync", True, synth.controls) == 64
	assert rig._cc_value("sync", False, synth.controls) == 0


def test_a_control_the_instrument_only_transmits_is_refused_at_import (
	rig: typing.Any) -> None:
	"""A definition says which way a control travels (#2469), and one the
	instrument sends but ignores on arrival is a row on the glass that moves
	nothing.

	Refused where a settings table is read, which is at import, because the
	failure it prevents is silent: the panel would draw it, the app would accept
	it, the instrument would drop it, and nobody would be told.
	"""

	fill = pymidiinstrumentdefs.Control(
		name="auto_fill", label="Auto Fill", cc=91,
		direction=pymidiinstrumentdefs.definition.TRANSMITS)

	with pytest.raises(ValueError, match="transmits and does not receive"):
		rig._panel_parameter("fill", "auto_fill", "Fill", None,
		                     instrument=_instrument(auto_fill=fill))

	# And nothing this rig puts on the glass is one — or it would not have imported.
	assert all(control.is_sendable
	           for control in [*rig.BASS_CONTROLS.values(), *rig.CHORD_CONTROLS.values()])


def test_every_pattern_can_be_given_a_generator (rig: typing.Any) -> None:
	"""#2147, and Simon's ask in his own words: all patterns should have "+ Add
	Generator", not just the DRM1 panel.

	**Nothing in the package forbade it and nothing in the package changed.**  The
	panel offers the button on a pattern exactly where some stack declares it
	`builds`, and this composition declared one — so the DRM1 had the button and
	the two Moogs did not, which reads as a missing feature and was a missing
	declaration.  That is #1465's division working: an app offering no stack for a
	pattern is saying that pattern takes no contributions, and this one was saying
	it by accident.

	Asserted against the grids rather than a list of names, so a pattern added
	later fails here rather than quietly arriving without one.
	"""

	grids = {name for name, control in rig.link.controls.items()
	         if isinstance(control, (superconductor.subsequence_adapter.StepGrid,
	                                 superconductor.subsequence_adapter.NoteGrid))}

	built = {control.declaration()["builds"] for control in rig.link.controls.values()
	         if control.declaration().get("type") == "recipe"}

	assert grids, "no grids at all, so this proves nothing"
	assert grids - built == set(), f"these patterns take no contributions: {sorted(grids - built)}"


def test_a_stack_offers_the_pitches_of_the_pattern_it_builds (rig: typing.Any) -> None:
	"""Which is the whole difference between a stack on a kit and one on a bassline.

	A euclidean rhythm on the DRM1 picks between ten voice names; the same
	generator on the Minitaur picks between the notes that grid's rows *are*.  The
	catalogue knows a parameter is a pitch and cannot know which pitches exist —
	only this file knows one grid's rows are a drum machine's and another's are
	notes an instrument can reach (#2085).

	Worth asserting because the failure is quiet and wrong rather than loud: a
	bass stack handed the drum rows would offer `kick` as a pitch for a Minitaur,
	and every value it sent would be refused by a note map that has never heard
	of it.
	"""

	stacks = {name: control for name, control in rig.link.controls.items()
	          if isinstance(control, superconductor.subsequence_adapter.Recipe)}

	assert set(stacks) >= {"drum_recipe", "bass_recipe", "chord_recipe"}

	assert stacks["drum_recipe"].pitches == rig.ROWS
	assert stacks["bass_recipe"].pitches == rig.BASS_ROWS
	assert stacks["chord_recipe"].pitches == rig.CHORD_ROWS

	# And they really are different vocabularies rather than three copies of one.
	assert "kick" in stacks["drum_recipe"].pitches
	assert "kick" not in stacks["bass_recipe"].pitches


def test_every_settings_default_is_the_shape_its_control_derives (rig: typing.Any) -> None:
	"""A kind is derived from the definition's bands and a default is written by
	hand in this file, so the two can disagree — and did.

	`square_lfo_polarity` names two states, which makes it a **switch**, and the
	table opened it at `"bipolar"`: a switch holding a string.  The panel drew it,
	the app stored it, and nothing said a word until a restore refused it with
	*"lfo_polarity is a switch"* — after a composition restart, which is the worst
	moment to find out and the one place it was ever going to show.

	A switch takes a bool and `_cc_value` picks the far end of the definition's
	own ascending pair, so `True` is `bipolar` and the band's name is never
	written here at all.  That is the same rule the Minitaur's `legato_glide`
	already turns on: neither of its states is spelled "on".
	"""

	wrong = []

	for table, instrument in ((rig.BASS_SETTINGS, rig.MINITAUR),
	                          (rig.CHORD_SETTINGS, rig.MATRIARCH)):
		for setting in table:
			panel, named, label, default = setting[0], setting[1], setting[2], setting[3]

			# Not built from this table: an action rather than a setting (#2177).
			if panel == "voices":
				continue

			drawn = rig._panel_parameter(panel, named, label, default,
			                             *setting[4:5], instrument=instrument)

			if default is None:
				continue

			fits = {
				"switch": isinstance(default, bool),
				"choice": isinstance(default, str),
				"number": isinstance(default, (int, float)) and not isinstance(default, bool),
			}[drawn.kind]

			if not fits:
				wrong.append(f"{panel} is a {drawn.kind} opening at {default!r}")

	assert wrong == [], "\n".join(wrong)


# --- two mechanisms side by side (#2228) ------------------------------------

def _built (rig: typing.Any, play: typing.Any, steps: int) -> list[typing.Any]:
	"""Run one play function onto a real pattern and hand back what landed."""

	pattern = subsequence.pattern.Pattern(
		channel=rig.DRUM_CHANNEL, length=steps * rig.STEP_DURATION)

	builder = subsequence.pattern_builder.PatternBuilder(
		pattern=pattern, cycle=0, rng=random.Random(1),
		drum_note_map=rig.drm1.VERMONA_DRM1_DRUM_MAP)

	play(builder)

	return list(builder.placed())


def test_a_lane_of_one_row_lands_on_that_voice_and_nowhere_else (
	rig: typing.Any) -> None:
	"""The whole of "route a lane to one voice", and it is a row name (#2228).

	`_play` walks this rig's ten voices and puts down whatever the grid holds for
	each, so a grid declaring only `snare` holds nothing for the other nine.  No
	mechanism was needed: routing has meant this since #2147 and had only ever
	been exercised with a grid that was the whole kit.
	"""

	landed = _built(rig, lambda p: rig._play(p, {"snare": [0, 4, 8, 12]}), rig.STEPS)

	assert landed, "the lane placed nothing at all"
	assert {note.pitch for note in landed} == {
		rig.drm1.VERMONA_DRM1_DRUM_MAP["snare"]}


def test_the_snare_lane_is_declared_one_row_wide (rig: typing.Any) -> None:
	"""And has no instrument of its own, exactly as the shared grid has none: it
	makes no sound until something routes it, and then it makes that thing's."""

	declared = rig.link.controls["snare_lane"].declaration()

	assert declared["rows"] == ["snare"]
	assert "pattern" not in declared or declared.get("pattern") is None


def test_a_stack_on_a_one_voice_lane_offers_only_that_voice (
	rig: typing.Any) -> None:
	"""A stack's pitches are what make it different, and here there is one.

	A pool that could choose between ten voices would make the lane a kit again —
	a euclidean added to it could put a kick on a grid whose only row is a snare,
	and the grid would show nothing while the DRM1 played it.
	"""

	euclidean = next(one for one in rig.snare_recipe.declaration()["generators"]
	                 if one["name"] == "euclidean")
	pitch = next(one for one in euclidean["parameters"] if one["name"] == "pitch")

	assert [one["value"] for one in pitch["options"]] == ["snare"]


def test_the_nine_runs_against_the_sixteen_rather_than_inside_it (
	rig: typing.Any) -> None:
	"""Subsequence does polyrhythm by independent pattern lengths, so this is a
	pattern of its own rather than a grid routed into the drums — a routed grid
	plays at the destination's resolution and would be a truncated bar.

	2.25 beats against 4: the two coincide every nine bars.
	"""

	nine = rig.link.controls["nine"].declaration()
	drums = rig.link.controls["grid"].declaration()

	assert nine["steps"] == 9
	assert nine["beats"] == 2.25
	assert drums["beats"] == 4

	# Both on the same instrument, which is what makes it one polyrhythm rather
	# than two unrelated parts.
	assert nine["rows"] == drums["rows"]


def test_a_cycle_that_is_not_a_whole_number_of_beats_survives_declaration (
	rig: typing.Any) -> None:
	"""`beats` was an `int` because every grid on this rig had been sixteen
	sixteenths, and `int(16 * 0.25)` is 4 without complaining.  The first cycle
	that is not a whole number of beats is the nine, and truncating it to 2 would
	put its playhead a ninth of a bar out and drift for ever."""

	assert rig.NINE_BEATS == 2.25
	assert isinstance(rig.link.controls["nine"].declaration()["beats"], float)


def test_the_slot_count_is_bounded_and_the_one_measured_in_beats_is_not (
	rig: typing.Any, caplog: pytest.LogCaptureFixture) -> None:
	"""#2413 against the real catalogue, which is the only place it could be seen.

	`grid` is on eight of Subsequence's entries.  Seven mean *how many slots the
	pattern has* and are rightly bounded to this pattern's length; `swing.grid`
	means *grid size in beats* and opens at 0.25, which that bound forbids — and
	a control born outside its own range has every write refused, which freezes
	the whole stack because bypass, reorder, add and remove each write all of it.
	Simon met exactly that and could then toggle nothing on the stack he had
	added a swing to.

	**Nothing on the wire told the two apart until Subsequence declared its
	units**, so the composition now names the unit alongside the parameter and
	the bound reaches only what it was written for.  Asserted here rather than in
	`test_recipe.py` because the fault lives in the *real* catalogue: a hand-built
	one proves the mechanism and this proves the rig.

	**The silence is the half that says it was fixed rather than survived.**  The
	outcome — seven bounded, one not — is what the backstop produced too: notice
	that a bound excludes the parameter's own default and drop it, with a warning.
	So a stack built here must say *nothing at all*, which it can only do if the
	bound never reached swing in the first place.
	"""

	with caplog.at_level(
		logging.WARNING, logger="superconductor.subsequence_adapter"):
		rig._stack_for("grid", "probe_recipe", "Probe")

	dropped = [one.getMessage() for one in caplog.records if "not bounding" in one.getMessage()]

	assert dropped == [], f"a bound still had to be dropped: {dropped}"

	said = rig.drum_recipe.declaration()
	grids = {one["name"]: p
	         for one in said["generators"] + said.get("transforms", [])
	         for p in one["parameters"] if p["name"] == "grid"}

	assert len(grids) > 1, "only one entry has a `grid`, so this proves nothing"

	counted = {name: p for name, p in grids.items() if p.get("unit") == "steps"}
	beaten = {name: p for name, p in grids.items() if p.get("unit") == "beats"}

	assert counted and beaten, f"the collision has gone from the catalogue: {grids}"

	for name, p in counted.items():
		assert p.get("max") == rig.STEPS, f"{name}.grid was not bounded to the pattern"

	for name, p in beaten.items():
		assert "max" not in p, f"{name}.grid was bounded as though it counted slots"
		assert p.get("default") == 0.25, "the app's own opening value moved"


def test_a_stack_is_bounded_by_the_pattern_it_builds (rig: typing.Any) -> None:
	"""Offering sixteen pulses on a nine-step pattern would be offering a control
	whose top half cannot land — the same fault as a filled parameter that means
	*nothing*, arriving from the other direction (#2248).
	"""

	def ceiling (recipe: typing.Any, generator: str, parameter: str) -> typing.Any:
		"""The top of one parameter's range, as the panel is offered it."""

		shape = next(one for one in recipe.declaration()["generators"]
		             if one["name"] == generator)

		return next(one for one in shape["parameters"]
		            if one["name"] == parameter)["max"]

	assert ceiling(rig.nine_recipe, "euclidean", "pulses") == 9
	assert ceiling(rig.drum_recipe, "euclidean", "pulses") == 16


def test_a_grid_the_panel_makes_can_be_routed_the_moment_it_exists (
	rig: typing.Any) -> None:
	"""A grid with no instrument behind it makes no sound until something routes
	it, so a made grid that was not a source would be a block that can never do
	anything (#2226).

	A stack holds the composition's own `sources` mapping rather than a copy of it
	(#2421), so writing the grid into `SHARED` is what makes it routable — and the
	rack asks for a declaration as soon as it has made one, so the two land
	together.

	**The assertion that matters is the third one**, and this test went without it
	from the day it was written: the first two say a grid was made and registered,
	which was true throughout the year this feature did not work.  A stack built at
	import took a copy, so it offered the sources it was born with for ever, and a
	route to a made grid was refused by both halves.
	"""

	before = set(rig.SHARED)
	made = rig._make_grid({"name": "made_grids-x", "rows": ["snare"], "steps": 8})

	assert made.name == "made_grids-x"
	assert set(rig.SHARED) - before == {"made_grids-x"}

	assert "made_grids-x" in rig.drum_recipe.declaration()["sources"], (
		"a stack built at import does not offer a grid the rack made after it")

	# And the source plays what is drawn on it, on the voice its rows name.
	landed = _built(
		rig, lambda p: rig.SHARED["made_grids-x"](p), 8)

	assert landed == [], "an untouched grid placed something"

	rig.composition.data["made_grids-x"]["snare"] = [0, 4]
	landed = _built(rig, lambda p: rig.SHARED["made_grids-x"](p), 8)

	assert {note.pitch for note in landed} == {
		rig.drm1.VERMONA_DRM1_DRUM_MAP["snare"]}

	rig._unmake_grid("made_grids-x")

	assert "made_grids-x" not in rig.SHARED, (
		"a stack would go on offering a cable to a grid nobody can see")

	assert "made_grids-x" not in rig.drum_recipe.declaration()["sources"], (
		"a stack goes on offering a cable to a grid nobody can see")


def test_the_rack_cannot_make_a_grid_longer_than_a_route_can_carry (
	rig: typing.Any) -> None:
	"""A grid patched into a pattern plays at the **destination's** resolution,
	so a twenty-step grid routed into this rig's sixteen would be a truncated bar
	— a control that looks set up and quietly drops four steps.

	A cycle of a different length is the other mechanism and it is a pattern
	rather than a grid (#2228).
	"""

	declared = rig.link.controls["made_grids"].declaration()

	assert declared["type"] == "grids"
	assert declared["max_steps"] == rig.STEPS
	assert declared["rows"] == rig.ROWS


def test_the_note_set_is_a_whole_keyboard_seen_from_c2 (rig: typing.Any) -> None:
	"""Eighty-eight keys, opening on the octave between the bass and the lead (#2389)."""

	declared = rig.notes.declaration()
	midi = [one["midi"] for one in declared["pitches"]]

	assert midi == list(range(21, 109)), "A0 to C8, every key of a piano and nothing else"
	assert declared["opens_at"] == "C2"


def test_every_note_the_old_range_offered_is_still_offered (rig: typing.Any) -> None:
	"""**The range widened and the view narrowed in one change**, or a capture of
	the set as it was — ``C4 G4 C3 G3 D#3 D#4 C5`` on the rig when this changed —
	would be refused on restore.  C3 to C5 was the whole of the range before."""

	offered = set(rig.notes.pitches)
	before = {rig.midi_notes.note_to_name(note) for note in range(48, 73)}

	assert before <= offered, f"a set chosen before #2389 would lose {sorted(before - offered)}"


def _pitched (rig: typing.Any, play: typing.Any, note_map: dict[str, int]) -> list[typing.Any]:
	"""Run a pitched pattern's play function onto a real builder and hand back what landed."""

	pattern = subsequence.pattern.Pattern(
		channel=rig.BASS_CHANNEL, length=rig.STEPS * rig.STEP_DURATION)

	builder = subsequence.pattern_builder.PatternBuilder(
		pattern=pattern, cycle=0, rng=random.Random(1), drum_note_map=note_map)

	play(builder)

	return list(builder.placed())


def test_a_generated_note_moves_with_the_pattern_s_transposition (
	rig: typing.Any, monkeypatch: pytest.MonkeyPatch) -> None:
	"""#2454, Simon's decision of 2026-09-11: transposing a pattern moves the
	notes its generators place as well as the ones tapped in.

	**It was more than a missing feature.**  The row labels have always moved for
	every note (#2144), so a generated note sat on a row naming a pitch it did not
	play.  Here the generated C2 has to sound D2, *and* still be reported on the
	C2 row — whose label at +2 is D2 — or the glass and the ears disagree again."""

	# A stack is handed its link when the link starts, which nothing here does —
	# so it is handed one for the length of the test, with the send caught.
	reported: list[dict[str, typing.Any]] = []
	monkeypatch.setattr(rig.bass_recipe, "link", rig.link)
	monkeypatch.setattr(rig.link, "happened", lambda name, **fields: reported.append(
		{"name": name, **fields}))

	held = rig.composition.data["bass"]
	rig.composition.data["bass"] = {"E2": {"0": {"length": 6, "velocity": 100}}}
	rig.bass_recipe.apply(["layers"], [
		{"id": "made", "generator": "hit_steps", "bypassed": False,
		 "params": {"pitch": "C2", "steps": [4]}}])

	try:
		rig.bass_grid.transpose = 2
		landed = _pitched(rig, rig.bass, rig.BASS_NOTE_MAP)

	finally:
		rig.bass_grid.transpose = 0
		rig.bass_recipe.apply(["layers"], [])
		rig.composition.data["bass"] = held

	assert sorted(note.pitch for note in landed) == [38, 42], (
		"the tapped E2 and the generated C2 should both sound two semitones up")

	cells = [one["cells"] for one in reported if one["name"] == "realised"][-1]

	# In positions rather than steps — this grid divides a step six ways (#2115).
	assert cells.get("C2"), f"the generated note left its row: {cells}"
	assert set(cells) == {"C2"}, f"and nothing else was reported: {cells}"
	assert rig._relabel(rig.BASS_NOTE_MAP, rig.MINITAUR)("C2", 2) == \
		rig.midi_notes.note_to_name(38), "and the row it is drawn on names what it sounds"
