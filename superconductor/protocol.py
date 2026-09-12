"""The frame vocabulary spoken over every Superconductor socket.

One JSON object per frame, in UTF-8, named by its ``t`` field.  The panel and
each app speak the same vocabulary, so a frame crossing the service is usually
forwarded rather than translated.

The full vocabulary is Subroutine document #2018.  What appears here is the
subset the first proof-of-concept (#2047) needs.  Frames that design names but
this build does not use — ``fire``, ``telemetry`` and the page frames — are
absent rather than stubbed, so nothing claims to work that has never run.
"""

import json
import math
import typing


CONTRACT_VERSION = "1.34.0"
"""Bumped when a frame changes shape.  Both ends send it and neither guesses.

1.1.0 adds ``service``, which an older panel ignores as it ignores any frame it
does not know — so the minor number, not the major one.  1.2.0 adds ``pages`` to
``declare`` and to ``manifest``: an app that sends none, and a panel that reads
none, both behave exactly as they did.  1.3.0 adds ``arrange``, which an app
that cannot save one answers with a ``nack`` like any other refusal.  1.4.0 adds
the ``recipe`` control kind and the ``range`` parameter shape; a service too old
for either marks the control unsupported and says so on the glass, which is the
mechanism that already exists for exactly this.

1.5.0 renames ``arrange`` to ``layout``.  The frame is unchanged in every
other respect; the word was the problem.  *Arrangement* is a musical term in a
package that talks to a sequencer, and it was being used here for where a block
sits on a screen — a collision worth the rename while there is one app and one
panel to keep in step.

1.6.0 gives a layer an ``index``: the number a person sees on its window, held
by that layer for the whole of its life and never handed out twice.  A panel too
old to read it draws the stack exactly as it did; an app too old to send one
leaves every layer at zero, which is what a panel shows when it has not been
told a number.

1.7.0 adds two things a panel may draw and neither end acts on.  A control may
carry ``about``: a list of ``{label, value}`` facts shown beside its name.  It
exists because the package may not hold a MIDI channel or an instrument's name
(#1465), so a composition that wants those on the glass has to be the one saying
them.  And a parameter may carry ``role``, which says what a shape was before it
became a shape — a ``choice`` with ``role: "pitch"`` is a pitch the composition
resolved into the voices it has.  A panel too old for either ignores it as it
ignores any field it does not know.

1.8.0 lets a layer of a stack be a ``pattern`` as well as a ``generator``: a grid
belonging to no instrument, routed into several so that two synths share a
bassline and each add notes of their own (#2108).  It names a ``source`` where a
generator names a ``generator``, and the stack declares the ``sources`` it may
take from.  A service too old refuses the layer rather than dropping it, which is
the right way round: the app would play a route the service was not holding.

1.9.0 adds the ``realised`` event: which cells of a grid the algorithms put
there this cycle, as ``control`` and ``cells``.  1.10.0 makes each row's cells a
map of step to velocity rather than a list of steps, because how hard a
generated note is played is the thing that tells a ghost fill from a full hit,
and a panel drawing them the same weight says the opposite of what they are.  **An event and never a change**,
which is the whole of #1965 — a change is intent and is kept, and these notes are
not intent.  Nothing applies one to any control's state, a panel draws them as
dots beside the steps somebody tapped, and a person's taps remain the only thing
anything stores.  Sent only when the answer differs from the cycle before, so a
deterministic stack is silent.

1.11.0 gives a grid an ``enabled`` flag beside its rows, set at
``control/enabled``.  A mute in the sense a mixer means it: the notes stay where
they are and stop being heard.  What "off" does is the app's business — a grid
that drives a pattern mutes that pattern, a grid that only feeds routes stops
contributing — and neither the service nor the panel interprets it.  Absent means
on, which is what every grid was before there was a switch.

1.12.0 lets a ``note_grid`` declare ``divisions``: how many addressable
positions make up one drawn cell.  Absent means one, which is what every grid
was before there was a number — a position is a step, and nothing changes.
A composition that wants to place a note between two steps says so here, and
then a note's position and its length are both counted in those finer
positions rather than in steps.

**The unit belongs to the composition, not to this package.**  ``composition
.data`` is the app's own dict, read by its own pattern builder, so a panel that
re-keyed it to a resolution of its choosing would be dictating to the app it
serves.  Instead the app names the resolution it keeps and the panel offers
what that can hold: a grid left at one division snaps to whole steps because
that is the only place it could store anything else.  A panel too old to read
the field draws a step per position, which is wrong on a grid that declares
more than one — so a service that does not know the field refuses the control
rather than drawing it, as 1.8.0 does for the same reason.

1.19.0 lets a layer of a stack be a ``transform``: a named function of the app's
that **reshapes what the layers above it put there** rather than adding notes of
its own.  A stack declares the ``transforms`` it may take beside the
``generators`` it already declares, and a layer names one in ``transform`` where
a generator names one in ``generator``.

**Two catalogues rather than one longer one, and that is the whole of the
decision.**  The two are reached identically — a name, and parameters in the
same shapes, which are `PARAMETER_KINDS` — so merging them would work and would
be shorter.  It would
also draw a transform as a generator, and then the order of a stack would stop
meaning anything: a generator invents notes and a transform acts on everything
above it, so *which came first* is the only thing that says what a stack does.
Two kinds of connection must not look alike (#2119), and this is the third time
that rule has decided something here.

1.20.0 adds ``build`` to ``declare`` — a hash of the Python the app loaded when
it started.  Additive in the ordinary way: an app that sends none says nothing,
and the service checks nothing, which is what every app did before.

**It exists because a contract version cannot see this** (#2220).  A page knows
when it is behind, because its build is stamped on the script URL; a service is
caught by this very number.  An app is caught by neither: it runs the package
inside its own process, so a fix *behind* the wire moves no frame and the
contract goes on agreeing while a composition executes code from before lunch.
That is most of what an adapter is, and it cost a round trip an hour after the
contract check was built to prevent the same class of thing.

**The app sends what it loaded and never what is on disk**, and the service
compares it against what *it* loaded rather than against the files — so the
statement is *these two are not running the same code*, which on a shared
filesystem means one of them wants restarting.  Reading the disk here would say
which one, and would put a CIFS read inside a socket handler to do it; the
weaker question is free and cannot take the service off the air.

1.21.0 lets a part of a ``layout`` carry ``rows``: how tall somebody has pulled
that block, in lattice cells.  Additive in both directions — a panel that sends
none says the block has never been resized, and it opens at the height its
control declares, which is what every block did before.

**A height is an arrangement and not a declaration** (#2227).  How many rows a
grid *has* is the app's fact and does not move; how many of them you want to see
at once is the person's, changes with what they are working on, and belongs
beside the x and y that already travel this way.  So ``visible_rows`` stops being
a fixed height and becomes an opening one.

1.22.0 adds the ``grids`` control kind: a **rack**, whose value is an ordered
list of grids somebody made from the glass (#2226).  Parallel to ``recipe`` in
every respect that matters — an ordered list, an id per entry that lives as long
as the entry does, and adding, removing and reordering all being one write to
the list.

**And no frame was needed for "make me a control".**  An app re-declaring on the
socket it already holds is how it has always said its controls changed, so a
grid a person asks for arrives as an ordinary declared control on the next
declaration.  The service keeps the rack's list and is not told that the two
facts are related, because it does not need to be.

Naming the function in its own field is what lets an older panel behave well: it
finds no ``generator`` on such a layer and draws nothing, rather than drawing it
as an ordinary one.  A service too old for the kind refuses the layer, which is
right for the same reason 1.8.0's route is refused rather than dropped — the app
would otherwise play something the service was not holding.

**A transform acts on the whole pattern, including notes tapped by hand**, and
nothing in the contract says otherwise because nothing can: what a layer reaches
is the app's business.  A panel that draws a transform should say so.

1.18.0 lets a settings control say what it belongs to and how it is divided up.
A ``params`` control may declare ``configures``, naming the pattern whose
instrument these settings are; a field in one may declare ``group``, naming the
section of the instrument it sits in.  Both are additive and both are for the
same problem: **a settings panel with thirty-six controls on it**, which is
unreadable ungrouped and cannot be left standing beside its pattern for ever.

Neither means anything to the service, which forwards a control's declaration
whole.  An app that sends neither, and a panel that reads neither, behave exactly
as they did — a settings control with no ``configures`` is a block of its own, as
every one of them was, and fields with no ``group`` are one flat list.

1.17.0 lets a note grid be transposed.  It declares ``transpose_range`` and its
state carries ``transpose`` in semitones, plus two fields the app alone can fill:
``labels``, what each row is called at the current offset, and ``unreachable``,
the rows that will not sound at it.

**The sound moves and the drawing does not.**  The notes stay where they were
put, so the shape a person made stays a stable thing to read and keep editing,
and the change is undone by putting the number back.  What follows the offset is
the row labels — which is what stops the glass lying about pitch, and is the only
way to mark a row pushed past an instrument's ceiling.  A Moog Minitaur ignores
anything above note 72 and goes *silent* rather than wrong, so a transposed
bassline can vanish with every cell still lit and nothing to say why.

The panel cannot compute any of it: it knows a row is called ``C2`` and nothing
else, and that ``C2`` is a pitch is a fact about a studio (#1465).  So the app
sends the words and the panel prints them.

1.16.0 adds ``action``: a parameter that **does something and holds nothing**.
It names options as a ``choice`` does and a press is checked against them, but no
value is kept anywhere — not by the app, not by the service, and not on the glass,
where no button is ever drawn as chosen.

It exists because some settings cannot honestly be displayed.  A Moog Matriarch's
voicing is a front-panel switch *as well as* control change 94, and moving that
switch changes what the instrument does with no message of any kind — measured on
the rig, where a mode set over MIDI was overridden by a hand and a mode set by
hand was overridden over MIDI, last writer winning either way (#2177).  Any state
a panel showed for it would be wrong within seconds, and a panel joining late
would be handed a confident lie.

So the service returns without writing its copy, and ``apply`` reports that
nothing changed while still telling the composition something happened: the press
is acked, and no ``changed`` frame follows it, because a ``changed`` is precisely
the service's cue to remember a value.  A panic button is the same shape — there
is no state after "all notes off" either.

1.15.0 adds ``choices`` to a parameter's kinds: several of a pool, held as a list
in the order the panel sent, where ``choice`` is one of it.  It is a kind of its
own rather than a flag on ``choice``, on the same reasoning that makes ``range``
a kind rather than a ``number`` carrying a pair — a kind settles the shape of a
value, and one meaning a string here and a list there settles nothing.

It is worth a version because of what it was costing: a pitch parameter taking
*several* pitches had nowhere to go, so the adapter dropped it and marked its
generator partial, and **twenty-two of thirty-three generators arrived that
way** — not a random two thirds but every chord and melody writer in the
catalogue (#2150).  A panel too old to draw the kind refuses the control rather
than guessing, as 1.8.0 does for the same reason.

The same version stops ``partial`` conflating two different facts.  It was set
both by an app calling its own generator partial and by this package failing to
draw a parameter, and a panel could not tell them apart; the parameters this
package could not draw are now named in ``undrawn``, and only the second is
anything anybody here can fix.

1.14.0 replaces a note grid's ``mono`` flag with ``voices``, a count of how many
notes the instrument sounds at once — ``null`` for as many as you like, ``1`` for
what ``mono`` meant.  Voicing is not a boolean and never was: of the fourteen
instruments measured in #2125 one is switchable between 1, 2 and 4 voices *from
the glass*, and another drops from 32 notes to 16 when an effect is on.  Nothing
on the panel ever read ``mono`` — the rule is the app's and is enforced there —
so this costs a panel nothing and gives one something to say when a part is full.

1.13.0 makes each realised cell an object rather than a velocity: ``{"v": 100,
"from": "l7x2"}``, where ``from`` is the id of the stack layer that put the note
there.  A routed grid's notes and a generator's arrived under the same mark and
could not be told apart, so a person looking for the generator behind a note
found none — because there was none, and the note had come from a pattern routed
in.  The panel already holds the layers, so it reads the *kind* from those and
this only has to say which one; a second copy of the kind on the wire is a second
copy that could disagree.  The adapter now reads the pattern once per layer
rather than twice per cycle, which is one list copy each on a stack four deep.

A stack is added to and reordered by setting a path like any other control,
which was the point of choosing absolute sets: adding a generator from the
glass needed no new frame, only a value that happens to be a list (#2085).
1.24.0 renames a stack layer's ``pattern`` kind to ``route``.  It was the wrong
word twice over — everywhere else here a *pattern* is the thing that makes a
sound, and this is a layer merging somebody else's grid into one — and it was
renamed before a fourth layer kind could arrive and make it expensive (#2403).
**The old spelling is still read and never written**, so a capture taken before
the rename restores, and restoring it converts it.

1.25.0 gives ``null`` a meaning as a parameter's value: **put this parameter
back to unset**.  It was refused by every kind before, so nothing that used to
be accepted changes; what changes is that a parameter which *opened* unset can
be returned there.  A service too old for it answers a ``nack`` naming the
parameter, which is the ordinary refusal path and says so on the glass rather
than in a log (#2381).

1.26.0 adds the ``stalled`` event: which layers of a stack did not run this
cycle, and the app's own words for why (#2368).  A panel too old for it ignores
an event name it does not know, exactly as it ignores any frame it does not
know — which is why this is a minor number, on 1.1.0's precedent.  **It is
`stalled` and not `failed` because the glass already has a `failed`**, meaning a
set the app refused: two concepts must not share a word at a layer where both
readings are plausible (#2403).

1.27.0 adds ``duplicated`` to ``manifest``: the app names that more than one
connection is currently using, and how many (#2133).  A panel too old for it
ignores a key it does not know.  **An app name is unique by design** — Simon,
2026-09-10: more than one Substation or Subsample is wanted, more than one
Subsequence is not, and an app that wants two of itself declares two names.  So
this is not a refusal and never becomes one; it says on the glass that a name is
being shared, because the harm of an accidental second copy is outside the
service entirely and only a person can end it.

1.28.0 lets a parameter carry ``unit`` — see ``UNIT`` below (#2435).

1.29.0 lets a ``pitch_set`` carry ``opens_at``: the pitch a panel's view begins
on when it shows less than the whole pool (#2389).  A drawing hint the service
keeps and never reads; a panel too old for it opens where it always did.

1.30.0 adds the ``store`` control kind: where an app keeps what a person made on
the glass, drawn in the bar with the transport rather than as a block (#2487).
Its fields say when it last wrote and whether anything went wrong, and it offers
``start_again`` — back to the composition as its file has it.  A service too old
for the kind marks it unsupported, as it would any kind it does not know.

1.31.0 lets a step grid or a note grid declare ``variants`` — versions of its
notes a person switches between while it plays — and ``lands_every`` (#2485).
Such a grid's state is ``{variants: {A: {rows}}, playing, cue}`` beside its mute,
its cells are ``grid/variants/B/rows/kick/3``, a panel asks with ``cue`` and only
the app writes ``playing``, at a build.  **One address per cell**: the old
spelling is refused on a grid with variants rather than read as the one playing.
A grid declaring none is unchanged in every respect, so this is additive — but a
panel too old for it would draw a variant grid empty and have its taps refused,
which the contract check on its own bar is for (#2164).

1.32.0 answers a note placed on a note grid with the **shape it was kept with**
rather than with ``true`` (#2503).  A note ends inside its pattern, so one
placed too near the end for the default length is given the room there is — and
only the app works that out, so the service and every panel keep the shape they
are told instead of rebuilding it from ``default_length``.  The ask is still
``true``, and an app still answering ``true`` gets the default as before; a
panel too old for this draws such a note a whole default long, off the end of
the grid, which is what Simon found.

1.33.0 answers **every request an app accepted**, including the ones that change
nothing (#2502).  An app sends an ``ack`` naming the path where it applied a set
and nothing moved — an action, which keeps nothing at all (#2179), or a value
already held — and the service passes it to the panel that asked.  ``ack`` now
carries ``path`` for that reason, since no ``changed`` frame accompanies it.  A
panel too old ignores the field and lets the request expire as it always did; an
app too old sends nothing and the service ignores what it never sends.

1.34.0 lets a layer of a stack be **locked at the stream it was dealt**, so a
generated bar somebody liked keeps playing while its neighbours move on (#2263).
A layer carries ``dealt``: absent, it follows the pattern's stream as every layer
always has; ``true`` is a panel asking to be locked at *the bar it is hearing*,
and only the app can say which number that is, so it substitutes the base it last
built with and answers with the integer.  Asking again rerolls it.  A routed grid
is refused one, having no stream of its own to lock.  Additive in
both directions: a stack stored before this reads exactly as it did, an app too
old never sends the field, and a panel too old neither sends it nor draws it.
"""

UNIT = "unit"
"""What a value is measured in, said by the app that owns the meaning (#2435).

A **free string in the app's own words** — `beats`, `steps`, `MIDI velocity`,
`semitones`, `Hz` — carried beside `min`, `max` and `step` on a parameter, and
absent where a parameter has no natural unit.  Nothing here enumerates them, and
nothing here converts between them: a table of units would be this package
knowing what a hertz is, which is the same mistake as knowing what a drum voice
is (#1465).

**It is read as well as drawn, and exactly one place may read it.**  Simon's
decision of 2026-09-10 (#2435): *there is no central vocabulary; each producing
app commits to a closed set of unit words, pinned by that app's own test, and
this package may switch on them.*  The place that switches is **the adapter for
the app that declared it** — `subsequence_adapter.py` knows Subsequence's words
and nothing else does.  By the time a value reaches this module, `controls.py`
or the glass, the unit has already become a shape the contract carries: a bound,
a set of choices, a word beside a number.

So the rule for everything downstream of an adapter is the one `about` has
(#2071): **shown, never interpreted.**  The reason the field is named here at all
is that both halves have to agree it exists and rides through untouched.

*"Shown, never read" is what this said until 2026-09-10*, and it was already
false: #2411's `kind: "position"` declares a unit that says which axis its values
count along, and no panel can offer them without knowing.
"""

PARAMETER_KINDS = ("switch", "number", "choice", "range", "choices", "action")
"""What a parameter can be, and so what a panel knows how to draw.

**It lives here because both halves have to agree on it**, and the two that must
are as far apart as this package gets: `subsequence_adapter.offerable` decides
what an app offers, and `controls.py` decides what the service will keep.  A
second copy of a vocabulary is how two ends come to disagree, which is the fault
this project has been bitten by three times, so there is one.

**A kind outside this tuple is not drawn, it is reported `undrawn`** (#2379).
Nothing used to check, and the fall-through at both ends was *it is a number* —
so the first kind Subsequence invented that this package had never seen came
through as an unbounded dial opening at zero, on a parameter that wanted a chord.
Refusing to draw what we cannot draw is the honest answer and is already the
contract: `undrawn` says so, and `partial` follows from it.

A range is two numbers with an order between them, held as ``[low, high]``.  It
is the shape an algorithm's parameters ask for that an instrument's did not: a
velocity given as ``(30, 50)`` means a fresh draw between the two on every hit,
which is most of what makes a generated layer sound played rather than typed.

``choices`` is several of a pool where ``choice`` is one of it, held as a list in
the order the panel sent.  **It is a kind of its own rather than a flag on
``choice``**, on the same reasoning that makes ``range`` a kind rather than a
``number`` that carries a pair: a kind settles the shape of a value, and one that
means a string here and a list there has stopped settling anything — every reader
would then have to check a second field before it knew what it was holding.

The order is kept because it can matter: the pitches of a chord are not a set,
and a generator handed a root first is entitled to use that.  Duplicates are
refused, because two of one pitch in a pool says nothing a single one does not.

``action`` is the odd one and the only kind that **holds nothing**.  It names
options like a choice and a press is checked against them, but no value is kept
by the app, the service or the glass, because the thing it sets cannot be read.
A Moog Matriarch's voicing is the case it was built for: a front-panel switch
changes it undetectably, so any state that was remembered would be wrong the
moment a hand moved that switch, and a panel arriving late would be told a
confident lie (#2179, #2172).  A panic button is the same shape — there is no
state after "all notes off" either.

``pitch`` is not in here, and that is deliberate: it never reaches a panel.  An
app declares one and `offerable` turns it into a ``choice`` or a ``choices`` of
the pitches a composition actually has, because which pitches exist is the
composition's to know and never the app's (#1465).
"""


def may_be_unset (field: dict[str, typing.Any]) -> bool:
	"""Whether a parameter that opened unset can be put back to unset.

	**A parameter that opens unset can be returned to unset, and that is the
	whole rule.**  It is #2249's sentence read as a permission: ``required``
	false with an explicit ``default`` of ``null`` means *leave this alone*, so
	leaving it alone has to stay reachable after somebody has touched it.

	**It lives here for the reason `PARAMETER_KINDS` does.**  The half that
	decides a value may be cleared is `subsequence_adapter`, and the half that
	decides the service will drop it is `controls`; measured on 2026-09-10, 42
	parameters across 21 of the sequencer's 46 catalogue entries answer true, so
	two copies of this would be two copies of something load-bearing.

	**The `default` key has to be present, not merely null when read.**  An
	instrument's settings declare no ``default`` at all — `Parameter.declaration`
	never emits one — so ``field.get("default") is None`` is true of every switch
	and every dial on a Matriarch, and would have offered a CC an *unset* it has
	no way to be.  A catalogue says ``"default": null`` on purpose; a settings
	block says nothing, and the difference between the two is the whole check.
	"""

	return (not field.get("required")
	        and "default" in field
	        and field["default"] is None)


CONTROL_KINDS = ("step_grid", "note_grid", "params", "recipe",
                 "transport", "grids", "pitch_set", "store")
"""Every kind of control there is, in the words the wire uses.

**It lives here for the reason `PARAMETER_KINDS` does**, and it took longer to
get here than that did.  `subsequence_adapter` never imports `controls`, so the
half that *declares* a kind and the half that *keeps* one had no word in common:
the adapter carried each name as a bare literal and the service carried a tuple,
and nothing tied the two.  An eighth kind added on one side went red nowhere.

What each kind *means to the service* is documented in `controls.py`, beside the
branch that keeps it.  This is only the vocabulary — the list both halves and the
client have to agree on, and which `tests/test_client.py` now checks across all
three.
"""

LAYER_KINDS = ("generator", "route", "transform")
"""What a layer of a stack may be.

``route`` was named before it existed, so that adding it would be an addition
rather than a rewrite.  It was.  ``transform`` followed the same way (#2246).

**A layer names its function in a different field for each kind** — `generator`,
`source`, `transform` — which is what tells them apart on the wire and what lets
a panel too old for a kind draw nothing rather than drawing it wrongly.
"""


PATCHED = "from"
"""The key that makes a parameter's value a reference rather than a literal.

``{"from": "control", "id": "notes"}`` on a parameter says *take this from that
control every cycle*, where a bare value says *use this*.  The service keeps the
reference and never resolves it: what a source is worth is the app's to work out,
on the clock, at the moment it builds — the same division as everywhere else here.

The envelope is deliberately wider than the one source it carries today, because
#2232 wants the same shape for a number driven by a signal, a cycle count or a
bar.  A parameter holding a source is one mechanism with two payloads, and
building it twice is how the two would come to disagree.

**It lives here rather than in `controls.py` for the reason `PARAMETER_KINDS`
does.**  The adapter spelled the same four characters by hand five times while
the service had a name for them, which is a second copy of a wire word.
"""

PATCH_INPUTS: dict[tuple[str, str], tuple[str, str]] = {
	("choices", "pitch"): ("pitch_set", "a set of pitches"),
}
"""What may be plugged into what: a parameter's (kind, role) against its source.

**One table, because this is a policy and not an arithmetic.**  It was written
twice — once in `controls._readable_patch` and once in
`subsequence_adapter.checked_value` — and the two disagreed: the service checked
that the source had been declared and was a set of pitches, and the app checked
only that the id was a string.  Measured on 2026-09-10, the app accepted a cable
from a transport and from a control that did not exist, and the service refused
both; `hub.change_reported` logs the refusal and forwards the frame anyway, so a
connected panel drew the cable and a reloading one did not.

The value is the source's control kind and **the words to refuse in**.  A refusal
is read on the glass by somebody holding a lead, so it has to say what the socket
wants rather than name a type: *"which is a transport rather than a set of
pitches"* is the sentence, and the second half of it lives here.

**A parameter not named here takes no patch at all**, which is what makes adding
a source a matter of adding a row.  Modulators — a number driven by a source
(#2232) — are one row and no new mechanism, because the envelope above already
knows nothing about pitch.
"""


def is_patch (value: typing.Any) -> bool:
	"""Whether a value is a reference to a source rather than a literal.

	Asked before a kind is checked, everywhere, because a reference satisfies no
	kind: left to fall through it is refused as *not a number*, which is true and
	tells nobody anything (#2374).
	"""

	return isinstance(value, dict) and PATCHED in value


def patch_refusal (
	name: str,
	value: dict[str, typing.Any],
	source_kind: str | None,
	kind: str | None,
	role: str | None,
) -> str | None:
	"""Why this source may not feed this parameter, or ``None`` if it may.

	A reason rather than an exception, so each half raises its own — the app
	refuses with `Refused` and the service with `ControlError`, and both now say
	the same sentence, which they did not before.

	``source_kind`` is what the named control declared itself to be, or ``None``
	where nothing of that name was declared.  **A caller that cannot answer that
	question passes ``None`` and every patch is refused**, which is the safe way
	round: an instrument's settings are resolved by nothing (only `Recipe` reads
	an envelope), so a cable landing in one would be stored, reported, and worth
	nothing for ever.
	"""

	source = value.get(PATCHED)

	if source != "control":
		return f"{name!r} is patched from {source!r}, which this version does not know"

	named = value.get("id")

	if not isinstance(named, str) or not named:
		return f"{name!r} is patched from nothing this app declared"

	if source_kind is None:
		return f"{name!r} is patched from {named!r}, which this app did not declare"

	wants = PATCH_INPUTS.get((str(kind), str(role)))

	if wants is None:
		return f"{name!r} takes no patch, so nothing can be plugged into it"

	if source_kind != wants[0]:
		return (f"{name!r} is patched from {named!r}, which is a "
		        f"{source_kind} rather than {wants[1]}")

	return None


Frame = dict[str, typing.Any]


class ProtocolError (Exception):
	"""A frame that could not be understood, named by what was wrong with it."""


def contract_gap (spoken: object) -> str | None:
	"""How a version spoken on the wire differs from this build's, if it does.

	**Both ends have always sent this and neither has ever read it** (#2164).
	The contract went 1.13.0 to 1.17.0 in two days with a panel open throughout
	and nothing said a word, because the client's frame dispatch has no
	``default:`` — an unknown frame kind is ignored, which is the right choice on
	its own and, without this, means the two can disagree indefinitely and only
	misbehave.

	The dangerous case is not an unknown kind. It is a **known kind whose shape
	changed**: 1.13.0 made a realised cell ``{v, from}`` where it had been a bare
	velocity, so an old panel drew every dot at one size — wrong, and silent.

	``None`` when the two agree.  Otherwise:

	- ``"major"`` — the first numbers differ, so a frame either end already knows
	  may have changed shape underneath it. This is the one that corrupts rather
	  than degrades.
	- ``"older"`` / ``"newer"`` — the other side is behind or ahead within the
	  same major, which by this project's own numbering means additive: whichever
	  is behind is missing something rather than misreading it.
	- ``"unreadable"`` — not a version at all. Reported rather than ignored,
	  because something is speaking and it is not this protocol.

	The direction is the *other* side's, so a caller says what it found rather
	than working out whose fault it is.
	"""

	if spoken == CONTRACT_VERSION:
		return None

	parts = str(spoken).split(".") if isinstance(spoken, str) else []

	if len(parts) != 3 or not all(part.isdigit() for part in parts):
		return "unreadable"

	theirs = tuple(int(part) for part in parts)
	ours = tuple(int(part) for part in CONTRACT_VERSION.split("."))

	if theirs[0] != ours[0]:
		return "major"

	return "older" if theirs < ours else "newer"


def encode (frame: Frame) -> str:
	"""Render a frame as the compact JSON that goes on the wire."""

	return json.dumps(frame, separators=(",", ":"))


def decode (raw: str | bytes) -> Frame:
	"""Read a frame off the wire, refusing anything that is not a named object."""

	try:
		parsed = json.loads(raw)

	except json.JSONDecodeError as error:
		raise ProtocolError(f"not JSON: {error}") from error

	if not isinstance(parsed, dict):
		raise ProtocolError(f"expected an object, got {type(parsed).__name__}")

	if not isinstance(parsed.get("t"), str):
		raise ProtocolError("frame has no 't' naming its kind")

	return typing.cast(Frame, parsed)


def whole (frame: Frame, name: str, fallback: int) -> int:
	"""One field of a frame as a whole number, refusing anything that is not one.

	`decode` guarantees a frame is an object carrying a string ``t`` and says
	nothing about any other field, so everything else is whatever the sender
	chose to put there.  Three fields were coerced with a bare ``int()`` or
	``float()`` inside a ``try`` that catches only a disconnection and a
	`ProtocolError` — so ``{"t": "set", ..., "seq": "oops"}`` took the socket
	down with a traceback rather than through the careful path this module has
	for exactly "a frame that could not be read".

	A float that happens to be whole is accepted: JSON has one number type, and
	refusing ``2.0`` for a sequence number would be pedantry about an encoding
	rather than about the value.
	"""

	held = frame.get(name, fallback)

	if isinstance(held, bool) or not isinstance(held, (int, float)):
		raise ProtocolError(f"{name!r} is a whole number, and {held!r} is not one")

	if isinstance(held, float) and (not math.isfinite(held) or held != int(held)):
		raise ProtocolError(f"{name!r} is a whole number, and {held!r} is not one")

	return int(held)


def number (frame: Frame, name: str, fallback: float) -> float:
	"""One field of a frame as a number, refusing anything that is not one.

	Infinities and NaN are refused as well as strings: they survive JSON in
	some encoders, and a timestamp of NaN would come back through a pong and
	poison the panel's own clock arithmetic.
	"""

	held = frame.get(name, fallback)

	if isinstance(held, bool) or not isinstance(held, (int, float)) or not math.isfinite(held):
		raise ProtocolError(f"{name!r} is a number, and {held!r} is not one")

	return float(held)


def hello (client: str, page: str | None, versions: dict[str, int] | None = None) -> Frame:
	"""The panel introducing itself, with the version it last saw for each app.

	``page`` is the page this panel is showing, or null when it has not chosen
	one — a panel that has never been set, or whose browser cannot remember.
	Nothing is served differently for it; it is there so a service can say which
	panel is looking at what.

	``token`` is carried and ignored.  It costs nothing now and its absence
	would force a protocol change the day the panel is reached from off the
	local network.
	"""

	return {
		"t": "hello",
		"contract": CONTRACT_VERSION,
		"client": client,
		"page": page,
		"ver": versions or {},
		"token": None,
	}


def declare (app: str, controls: Frame, state: Frame, version: int,
             pages: list[Frame] | None = None, build: str | None = None) -> Frame:
	"""An app introducing itself and saying what it can be controlled by.

	``pages`` is how a composition offers several views over those controls
	(#2075).  It is optional in both directions: an app with nothing to say
	about arrangement sends none, and a panel then shows everything declared,
	which is what every panel did before pages existed.

	``build`` is the package this app *loaded*, taken once as it started (#2220).
	It is not what is on disk, and the difference is the entire point — see the
	1.20.0 note above.
	"""

	return {
		"t": "declare",
		"contract": CONTRACT_VERSION,
		"app": app,
		"controls": controls,
		"state": state,
		"ver": version,
		"pages": pages or [],
		"build": build,
	}


def manifest (apps: dict[str, Frame], page: Frame, pages: list[Frame] | None = None,
              duplicated: dict[str, int] | None = None) -> Frame:
	"""What the panel should draw: every dialled-in app and the controls it offers.

	Sent again whenever an app arrives or goes, so a panel that was already
	open when an app started still learns what it can now reach — and so a page
	set arrives on a panel that was open before its composition started.

	``pages`` is every page every connected app declared, each carrying the app
	that declared it.  The service assembles the list and owns none of it: a
	page set belongs to the composition that sent it, and is never read from
	disk here (#2075).

	``duplicated`` names each app that more than one connection is using right
	now, and how many there are (#2133).  **It is a live fact rather than a
	record of one**: it appears when a second connection declares a name that is
	already taken and goes when that connection closes, so killing the stray copy
	clears it and nobody has to dismiss anything.  Carried on the manifest
	because this is the frame a panel is handed when it joins, and somebody who
	was not watching at the moment it happened is exactly who needs telling.
	"""

	return {"t": "manifest", "contract": CONTRACT_VERSION, "apps": apps,
	        "page": page, "pages": pages or [],
	        **({"duplicated": duplicated} if duplicated else {})}


def layout (app: str, page: str, parts: list[Frame], client: str, seq: int) -> Frame:
	"""A panel handing back where a page's parts sit, for the app to keep.

	``parts`` is every part on that page as ``{name, x, y}``, in the order they
	are stacked — first drawn to last drawn, so the last entry is the one on
	top.  Positions are in lattice cells and no size is sent: a part's footprint
	follows its contents at whatever size the panel is drawn at, and a layout
	that carried pixels would be one person's screen imposed on another's
	(#2078).

	Sent when a drag ends rather than while it is going on, so a layout in
	motion is never half-saved (#2075).  It used to be sent on leaving a mode,
	which did the same job more coarsely and needed the mode to exist.
	"""

	return {"t": "layout", "app": app, "page": page, "parts": parts,
	        "client": client, "seq": seq}


def service (version: str | None, build: str | None) -> Frame:
	"""Which Superconductor the panel has reached, sent whenever it says hello.

	The panel compares ``build`` against the one stamped on the page it is
	actually running.  A difference means the service has newer files than the
	browser loaded, which no other signal on the glass would reveal (#2056).

	Both fields may be null.  A version that could not be derived and a client
	directory that is not there are both real states, and saying so is better
	than sending a number that means neither.
	"""

	return {"t": "service", "contract": CONTRACT_VERSION, "version": version, "build": build}


def snapshot (app: str, state: Frame, version: int) -> Frame:
	"""One app's whole state, sent on every connect rather than on a version miss.

	A grid this size is well under a kilobyte, and always sending it means there
	is no version-comparison path that can be wrong.
	"""

	return {"t": "snapshot", "app": app, "state": state, "ver": version}


def set_frame (app: str, path: str, value: typing.Any, client: str, seq: int) -> Frame:
	"""A request to make *path* hold *value*, absolutely rather than by toggling.

	An absolute value is what makes a re-send after a reconnect safe: applying
	it twice reaches the same state as applying it once.
	"""

	return {"t": "set", "app": app, "path": path, "v": value, "client": client, "seq": seq}


def changed (
	app: str,
	path: str,
	value: typing.Any,
	version: int,
	by: str,
	client: str | None = None,
	seq: int | None = None,
) -> Frame:
	"""A value that has actually been applied, sent to every panel.

	``by`` says whose hand it was — ``panel`` or ``app`` — and a panel write
	carries the client and sequence number that asked for it, which is what
	lets the asking panel clear its ring.
	"""

	frame: Frame = {"t": "changed", "app": app, "path": path, "v": value, "ver": version, "by": by}

	if client is not None:
		frame["client"] = client

	if seq is not None:
		frame["seq"] = seq

	return frame


def ack (app: str, client: str, seq: int, version: int, path: str | None = None) -> Frame:
	"""Confirmation that a named request has been applied.

	**The path is carried since 1.33.0** (#2502), because an ack now arrives on
	its own: an app answers a request that changed nothing with one, and there is
	no `changed` frame beside it naming the cell.  A panel keeps what it asked for
	by path, so an ack without one could only be matched by hunting for its
	sequence number.
	"""

	frame: Frame = {"t": "ack", "app": app, "client": client, "seq": seq, "ver": version}

	if path is not None:
		frame["path"] = path

	return frame


def nack (app: str, path: str, client: str, seq: int, reason: str) -> Frame:
	"""Refusal of a named request, saying why and naming the cell it was for.

	The path is carried so the panel can clear the mark on exactly the cell the
	finger landed on, rather than searching for it.
	"""

	return {"t": "nack", "app": app, "path": path, "client": client, "seq": seq, "reason": reason}


def event (app: str, name: str, **fields: typing.Any) -> Frame:
	"""Something the app reports that no one asked for — a beat, or a rebuild."""

	return {"t": "event", "app": app, "name": name, **fields}


def app_presence (app: str, up: bool) -> Frame:
	"""Whether an app is dialled in, so the panel can grey out what it cannot reach."""

	return {"t": "app", "app": app, "up": up}


def pong (sent_at: float) -> Frame:
	"""The panel's own timestamp echoed back.

	The round trip is what the playhead uses to place the service's clock
	against the browser's, so the highlight sits where the sound is.
	"""

	return {"t": "pong", "ts": sent_at}
