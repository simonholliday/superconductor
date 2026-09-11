# Superconductor

[![Tests](https://github.com/simonholliday/superconductor/actions/workflows/tests.yml/badge.svg)](https://github.com/simonholliday/superconductor/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/superconductor)](https://pypi.org/project/superconductor/)

A touchscreen control surface for music software.

A small service runs beside your music applications, serves one page to a
touchscreen's browser, and holds a single WebSocket to it. Each application
dials the service over a socket of its own and declares what it can be
controlled by; the page draws widgets bound to those declarations. Tapping the
glass changes the music; changing the music changes the glass.

**Nothing in this package knows about your studio.** An application declares its
own controls, and the names in them are yours. MIDI channels, drum note maps and
device names live in your own files, never in here.

## Status

**This is an early release, and it is not polished.** It has been played on real
hardware most days, by one person — its author — and by nobody else. Expect
rough edges, and expect the interface to move: very little here is settled
enough to be promised, and a version that changes how something works is more
likely than one that does not.

**So far it drives Subsequence, and nothing else.** The package itself knows
nothing about any particular music software — an application dials in and
declares what it can be controlled by, and that door is open to anything that
can hold a WebSocket and speak the protocol. But Subsequence, a generative MIDI
sequencer, is the only application anyone has written an adapter for, so today
"an application" means that one. Sampling and radio are intended and not
started.

If you do not already run Subsequence, there is nothing here you can play yet.
The service will start, serve its page, and wait for an application that is not
coming.

What runs today: as many pages as an application declares, holding step grids,
pitched note grids with sub-step timing, an instrument's own settings, stacks of
generators and transforms that contribute to a pattern, a set of notes chosen on
a keyboard, and a transport with a bar-beat-step counter. Blocks are arranged by
dragging, and the arrangement — and, if the application asks, everything made
on the glass — is kept by the application. A generator is wired to
the pattern it builds; a grid that belongs to no instrument, or a set of notes,
is patched into as many places as you like by dragging a cable from its outlet —
and a grid can be made on the glass as well as declared. Everything below
documents one of those.

**One thing to know before you play anything into it.** A pattern you edit on
the glass lives in the running composition, and it is kept across a restart
only if the composition asks for that — see *Keeping what you make* below.
Without it, restarting the composition throws away every note you tapped.
Either way there are two tools in the repository as a safety net, and the habit
is to run the first before restarting anything:

```
python tools/capture_state.py      # before
python tools/restore_state.py      # after
```

A restore puts each grid back exactly: a step the composition seeds on every
start, and that you had taken out, stays out — and the restore says which steps
it took out.

Those two tools live in the repository rather than in the installed package, as
does `compositions/drm1_grid.py` below — the only worked example, and the only
place the application-facing API is written down. Installing from a package
index gets you the service and the page; the examples are worth the clone.

## What it needs

Genuinely required:

- **Python 3.11 or newer** for the service.
- **A browser that delivers Pointer Events and holds a WebSocket.** Any current
  browser does.
- **A network path** between the browser, the service and the applications.
  Loopback is fine if they share a machine.

Everything else is a recommendation with a reason, not a requirement. The
development rig is a Raspberry Pi 5 driving a 22-inch capacitive panel over
Firefox, with the service and the music applications on a separate machine, but
the code assumes none of that: it is where the work was done, not what the
product is for.

## Running it

```
pip install superconductor
superconductor                 # serves on port 8090
superconductor --port 9000     # or wherever you like
```

Then open `http://<that machine>:8090/` on the touchscreen.

The service starts with no configuration at all. A YAML file passed with
`--config` overrides the defaults:

```yaml
host: 0.0.0.0    # the interface to listen on
port: 8090       # anything you like; this one is clear of the ports the
                 # neighbouring applications use
page: grid       # which page to serve
```

**It listens on every interface by default**, because the usual arrangement has
the panel on a different machine from the service. That is a default chosen for
a use, not a recommendation about your network: there is no authentication in
front of it, so anyone who can reach the port can change your music. Set `host`
to `127.0.0.1` if the browser is on the same machine, and keep it off any
network you do not trust.

The page shows nothing until an application dials in and declares something,
which is the expected state on a fresh start rather than a fault.

The corner of the bar shows the version and the build the page was made from.
If the service has newer files than the browser loaded — which happens whenever
you change something while a panel is left open — that readout becomes a button
saying so, and tapping it loads the new page. It never reloads on its own:
somebody may be playing.

## Sizing the grid to your hands

The **size** button on the page sets how big a grid cell is. It starts on *fit
the glass*, which measures your own screen and makes the grid as large as will
fit on it — so a panel nothing here was written against still uses all of
itself. The named sizes override that:

| | |
| --- | --- |
| Compact, 22 px | Half the tested size. Fits twice the music across the same glass, and frees room for whatever else you want beside it. |
| Snug, 32 px | |
| Tested, 44 px | The size the proof of concept was played at, with taps landing where intended. It is the only one with evidence behind it. |
| Large, 60 px | |
| Huge, 96 px | |

None of these is recommended over the others, because the right one depends on
your hands, your panel and how far away it is. Someone who wants the most music
on the glass and someone who needs a larger target are both served by the same
control, and the choice is remembered by the browser that made it — so two
people with their own panels do not have to agree.

The chooser itself never shrinks. Whatever size you pick, the way back is the
same size it always was.

## Pitched patterns

A step grid's cells are on or off. A **note grid**'s cells are notes: one row
per pitch, and a cell that carries its own length and velocity.

Press an empty cell to place a note, and keep dragging right to make it longer —
it grows a step at a time, and each length is sent as it changes, so the bar you
see is never longer than the instrument has agreed to. Press a note to take it
away. Beneath the grid is a velocity lane, one bar to a step, aligned with the
grid above so a column is the same moment in both; drag a bar up or down to set
how hard that note is struck.

Rows are drawn in the order they are declared, so a pitched part lists its
highest note first and a rising line rises. A part that declares `visible_rows`
shows a window onto a pattern taller than itself — two octaves is twenty-five
rows, and a block tall enough for all of them crowds everything else off the
page. Only the pitches scroll: the velocity lane and the playhead stay put,
because a column is a moment in time and scrolling up and down does not change
the time.

A part declares how many `voices` its instrument has, and no more than that many
notes sound at once: one for a monophonic synth, four for a Moog Matriarch in its
four-voice mode, and nothing at all for a part with no limit worth stating.
Placing a note that would exceed the count takes an earlier one away, newest
first, and each one taken is reported so the glass never goes dark unexplained.

That is enforced by the application rather than left to the instrument: a
monophonic synth handed two notes at once chooses between them by its own
note-priority setting, which the panel cannot see — so the glass would show two
notes while one sounded. It is counted by *extent* rather than by starting
position, because a note beginning part-way through another is exactly the case
the instrument would have to arbitrate.

Rows are names, as they are everywhere here. `compositions/drm1_grid.py` builds
them from note names and hands the same list to Subsequence as a note map, so
what the panel calls `C2` and what the synthesiser plays cannot drift apart.

## An instrument's own settings

A **params** control is a block of an instrument's settings, in the three shapes
they come in: a **switch**, a **number** you drag, and a **choice** of named
options. Between them those cover every control-change message a Moog Minitaur
answers to, and probably most other instruments.

Nothing in this package knows that a switch is a MIDI control change. A
composition declares what shape each setting is and what it may hold, and is
given a function to call when one moves — which is where a message gets sent,
if that is what the setting stands for:

```python
superconductor.subsequence_adapter.Params(
    composition,
    parameters=[
        superconductor.subsequence_adapter.Parameter("glide", "switch", label="Glide"),
        superconductor.subsequence_adapter.Parameter("rate", "number", default=24),
        superconductor.subsequence_adapter.Parameter(
            "shape", "choice", options=[("lcr", "LCR"), ("exp", "EXP")]),
    ],
    on_change=send_setting,
)
```

The settings worth putting on glass are usually the ones an instrument has no
knob for at all — reachable otherwise only through editor software. On the
Minitaur that is most of them.

## A set of notes

A **pitch set** is a block holding notes somebody chose, and it sounds nothing by
itself. Drag a cable from its outlet onto a generator that takes pitches — an
arpeggio, a chord — and that generator plays those notes. One set can feed as
many generators as you like, on as many instruments, and each plays it in its own
instrument's register, so the same chord reaches a bass synth and a lead without
being chosen twice.

It is drawn as a keyboard, an octave at a time — thirteen notes, C to C — however
wide the range it offers. Drag the strip beneath the keys to move along it; marks
on the strip show where every chosen note is, including ones out of view. Each C
is labelled with its octave.

The composition says which notes exist and where the view opens:

```python
superconductor.subsequence_adapter.PitchSet(
    composition,
    name="notes",
    pitches={"C2": 36, "C#2": 37, "D2": 38},    # every note it offers, and the MIDI note each sounds
    opens_at="C2",
)
```

Where it opens is yours to say because it depends on your instruments: the
worked example offers a piano's eighty-eight keys and opens at C2, between its
bass synth and its lead.

## Arranging a page

A block's title bar is its handle: drag one and it moves a cell at a time, on
the same lattice the steps themselves sit on — so two patterns on a page line up
step for step rather than nearly. A grid's bottom edge is a handle too: drag it
to show more of its rows or fewer. The grids go on playing throughout; only a
title bar or an edge moves anything.

Any position is allowed, including on top of another block. The last block you
moved is the one on top, which is what makes a busy page workable. Nothing is
ever pushed aside to make room: a block you did not touch does not move.

Because a block can be covered completely, and a title bar is the only handle
it has, the bar lists every block on the page. Tapping a name brings that block
back to the top.

Tap **LAYOUT** in the bar to hold the arrangement still — the padlock closes,
title bars and edges stop moving anything, and the list goes away. That is what
stops a stray finger rearranging a page mid-performance. The browser remembers
which way you left it.

An arrangement is saved when you lift your finger from a block that moved, and
it is saved to the application that declared the page, not to your browser. For a composition using `PageStore` that means a file beside the
composition itself, so a piece and the way you look at it travel together:

```python
link = superconductor.subsequence_adapter.AppLink(
    composition,
    controls=[...],
    pages=[...],
    page_store=superconductor.subsequence_adapter.PageStore(
        pathlib.Path(__file__).with_suffix(".pages.json")),
)
```

Leave `page_store` out and arranging still works — it simply is not kept, and
the panel says so rather than letting you find out at the next reload. Because
the arrangement belongs to the application rather than to one browser, a second
panel sees it too.

## Keeping what you make

Whatever you make on the glass can outlive the composition holding it. Give the
link a `PatternStore` and it keeps every grid's steps and notes, the stacks, the
settings, the set of notes, transpositions, mutes and the grids you made. It
never keeps what a generator played, and never the tempo or a pause:

```python
link = superconductor.subsequence_adapter.AppLink(
    composition,
    controls=[...],
    pattern_store=superconductor.subsequence_adapter.PatternStore.beside(__file__),
)

link.start()

try:
    composition.play()

finally:
    link.stop()      # writes down anything not written yet
```

It is written a moment after your hands stop, never on the thread that keeps
time, and it is read when the composition starts, before any panel sees it. So
after your first edit the composition file is no longer the score: its opening
pattern and opening values apply only where the store holds nothing.

`beside(__file__)` keeps it next to the composition. Give a path instead to keep
it anywhere else — the example rig keeps its own on the machine's own disk,
because its compositions sit on a network share.

The bar says when the store last wrote — **KEPT · 15:32** — and says **STORE ·
TROUBLE** if anything went wrong with it. Tap it for the details, and for
**START AGAIN FROM THE FILE**, which puts every pattern, stack, setting and mute
back as the composition file has them and removes the grids made on the glass.
It asks first. The store is moved aside rather than deleted, so nothing is lost
for good.

If the store cannot be read, it is moved aside untouched, the bar and the log
say where, and the piece starts as its file says. Anything the composition no
longer accepts — an option renamed, a row taken away — is refused on its own
and listed, the rest comes back, and a copy of the store as it was is kept
beside it.

## Variants

A pattern can hold several versions of its notes, and switch between them while
it plays. A grid that has them shows a row of tabs above it — **A B C D**, each
with a **▶** — and the two do different things:

- **Tap a letter** to show that variant and edit it. The music does not change:
  you can write B while A carries the room.
- **Tap its ▶** to play it next. It blinks until the switch happens, which is at
  the end of the pattern's current cycle, and is lit once it has. Tap the
  blinking ▶ again to change your mind.

The lit letter is the one playing and the ringed one is the one you are looking
at. When they differ the row says so — *B — A is playing* — and the grid shows
B's notes without the dots A's generators are placing. An empty variant offers to
**start from** the one playing, and **clear** works on the variant you are
looking at. Which variant you are looking at belongs to your panel; which one
plays belongs to the piece, and every panel sees it.

Only the notes are a variant's. The mute, a pitched pattern's transposition and
the generators that build the pattern stay the pattern's, so switching variant
never changes the key you are in.

A composition says which grids have variants and what they are called, and its
play function asks the grid what to play when the pattern is built — which is
the moment a cued variant lands:

```python
drum_grid = superconductor.subsequence_adapter.StepGrid(
    composition, rows=ROWS, steps=16, pattern="drums",
    variants=("A", "B", "C", "D"))

@composition.pattern(channel=10, steps=16, ...)
def drums (p):
    for row, steps in drum_grid.now(p).items():
        ...
```

`lands_every=2` holds each switch for the end of a two-bar phrase over a one-bar
pattern. A grid given no variants is exactly the grid it always was.

## Connecting an application

`superconductor/subsequence_adapter.py` is the worked example. A composition
builds a link, gives it the controls it wants to offer, and starts it:

```python
link = superconductor.subsequence_adapter.AppLink(
    composition,
    controls=[
        superconductor.subsequence_adapter.StepGrid(composition, rows=ROWS, steps=16),
        superconductor.subsequence_adapter.Transport(composition),
    ],
)
link.start()
```

`compositions/drm1_grid.py` is a complete example driving a Vermona DRM1: it is
the file that holds the MIDI port, the channel and which drum voice sits on
which row, and it is the file you would copy and change for your own rig.

The adapter imports nothing from the application it serves — it is written
against whatever object it is handed. That is deliberate, and it is what keeps
this package free of any dependency on a particular piece of music software.

## Keeping it running

None of this is required. Superconductor is an ordinary process: start it from a
terminal, from your window manager's autostart, from a `tmux` session, or from
whatever you already use. It needs no supervisor, and it does not need systemd
to exist.

If you do want it supervised and you have systemd, there are two shapes and the
difference is real. A **system unit** starts at boot with nobody logged in,
which is what you want on a machine that boots into being a studio. A **user
unit** needs no root and shares your own environment and files, which suits a
machine that is also somebody's desktop — but it starts only when you log in
unless you enable lingering.

Both of these have placeholders in capitals. They will not start until you have
replaced them, which is deliberate: a unit file that half-works with someone
else's paths in it is worse than one that refuses.

A system unit, at `/etc/systemd/system/superconductor.service`:

```ini
[Unit]
Description=Superconductor control surface
After=network-online.target

[Service]
Type=simple
User=REPLACE_WITH_YOUR_USERNAME
ExecStart=/REPLACE/WITH/YOUR/VENV/bin/superconductor
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
```

```
sudo systemctl enable --now superconductor
```

A user unit, at `~/.config/systemd/user/superconductor.service`:

```ini
[Unit]
Description=Superconductor control surface

[Service]
Type=simple
ExecStart=/REPLACE/WITH/YOUR/VENV/bin/superconductor
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
```

```
systemctl --user enable --now superconductor
loginctl enable-linger $USER      # only if it should run before you log in
```

Order never matters. The applications dial the service on a backoff and the
panel reconnects on its own, so any of the three can be started, stopped or
restarted without the others being told.

## Development

From a checkout, rather than from the package index:

```
pip install -e ".[dev]"
pytest --browser firefox
mypy superconductor
```

The suite includes tests that drive the page in a real Firefox, so it needs the
browser and its dependencies once:

```
playwright install firefox
playwright install-deps firefox
```

Firefox rather than all three browsers — it is a third of the packages, and it
is the browser this is built for. `--browser firefox` is not optional: the test
plugin defaults to Chromium.

Two files test the worked example against the sequencer it drives,
`tests/test_composition.py` and `tests/test_generators.py`, so they import
Subsequence and fail without it. If you do not run Subsequence, leave them out
with `--ignore`, as the project's own CI does.

The page is plain ES modules with no build step: Preact and htm are vendored
under `superconductor/client/vendor/`, with their licences recorded there. Edit
the files and reload the browser.

## What is in here

| | |
| --- | --- |
| `superconductor/` | the package — the service, the protocol, the adapter and the page it serves |
| `compositions/` | the worked example, and the only place the application-facing API is written down |
| `tools/` | probes that stand in for a browser, a capture and a restore, and the theme separation check |
| `tests/` | the suite, including the ones that drive a real Firefox |
| `research/` | the probes and raw measurements the design was made from |
| `reviews/` | the code reviews it has been through |
| `licences/` | notices for the vendored face and icons |

`research/` and `reviews/` are provenance: they record what was true on the day
they were written and are deliberately not kept up to date. They still say
*Superintendent*, which is what this was called until September 2026, and they
cite a tracker you cannot reach. They are here because the documents that cite
them should be checkable, not because they describe the code as it stands.

## Licence

Functional Source License 1.1 with an Apache 2.0 future licence
(`FSL-1.1-ALv2`) — see [LICENSE](LICENSE). You may read, run, modify and
redistribute it for any purpose except competing with it, and each version
converts to Apache 2.0 two years after its release.

The libraries it carries keep their own permissive licences, recorded in
`superconductor/client/vendor/README.md`.
