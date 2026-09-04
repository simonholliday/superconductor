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
```

The page shows nothing until an application dials in and declares something,
which is the expected state on a fresh start rather than a fault.

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
