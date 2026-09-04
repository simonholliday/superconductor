# Superintendent

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

A working proof of concept, not a release. What runs today is one page holding
one step grid and a transport, driving a drum machine from a step pattern in
[Subsequence](https://github.com/simonholliday/subsequence). It has been played
on real hardware; it has not been used by anyone but its author.

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
pip install -e ".[dev]"
superintendent                 # serves on port 8090
superintendent --port 9000     # or wherever you like
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

## Arranging a page

Tap **ARRANGE** in the bar. While it is latched the grids stop responding and
each block's title bar becomes its handle: drag one and it moves a cell at a
time, on the same lattice the steps themselves sit on — so two patterns on a
page line up step for step rather than nearly.

Any position is allowed, including on top of another block. The last block you
moved is the one on top, which is what makes a busy page workable. Nothing is
ever pushed aside to make room: a block you did not touch does not move.

Because a block can be covered completely, and a title bar is the only handle
it has, the bar lists every block on the page while you are arranging. Tapping
a name brings that block back to the top.

Tap **DONE** to leave. Outside the latch every touch is a control again, which
is what stops a stray finger rearranging a page mid-performance.

Leaving is also when the arrangement is saved — once, rather than on every
nudge — and it is saved to the application that declared the page, not to your
browser. For a composition using `PageStore` that means a file beside the
composition itself, so a piece and the way you look at it travel together:

```python
link = superintendent.subsequence_adapter.AppLink(
    composition,
    controls=[...],
    pages=[...],
    page_store=superintendent.subsequence_adapter.PageStore(
        pathlib.Path(__file__).with_suffix(".pages.json")),
)
```

Leave `page_store` out and arranging still works — it simply is not kept, and
the panel says so rather than letting you find out at the next reload. Because
the arrangement belongs to the application rather than to one browser, a second
panel sees it too.

## Connecting an application

`superintendent/subsequence_adapter.py` is the worked example. A composition
builds a link, gives it the controls it wants to offer, and starts it:

```python
link = superintendent.subsequence_adapter.AppLink(
    composition,
    controls=[
        superintendent.subsequence_adapter.StepGrid(composition, rows=ROWS, steps=16),
        superintendent.subsequence_adapter.Transport(composition),
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

None of this is required. Superintendent is an ordinary process: start it from a
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

A system unit, at `/etc/systemd/system/superintendent.service`:

```ini
[Unit]
Description=Superintendent control surface
After=network-online.target

[Service]
Type=simple
User=REPLACE_WITH_YOUR_USERNAME
ExecStart=/REPLACE/WITH/YOUR/VENV/bin/superintendent
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
```

```
sudo systemctl enable --now superintendent
```

A user unit, at `~/.config/systemd/user/superintendent.service`:

```ini
[Unit]
Description=Superintendent control surface

[Service]
Type=simple
ExecStart=/REPLACE/WITH/YOUR/VENV/bin/superintendent
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
```

```
systemctl --user enable --now superintendent
loginctl enable-linger $USER      # only if it should run before you log in
```

Order never matters. The applications dial the service on a backoff and the
panel reconnects on its own, so any of the three can be started, stopped or
restarted without the others being told.

## Development

```
pytest
mypy superintendent
```

The page is plain ES modules with no build step: Preact and htm are vendored
under `superintendent/client/vendor/`, with their licences recorded there. Edit
the files and reload the browser.

## Licence

Functional Source License 1.1 with an Apache 2.0 future licence
(`FSL-1.1-ALv2`) — see [LICENSE](LICENSE). You may read, run, modify and
redistribute it for any purpose except competing with it, and each version
converts to Apache 2.0 two years after its release.

The libraries it carries keep their own permissive licences, recorded in
`superintendent/client/vendor/README.md`.
