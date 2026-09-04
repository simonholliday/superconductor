**Question.** What runs the UI service on the headless Ubuntu server, and how is it deployed alongside the music apps?

## What the siblings do today, which the service should match

None of the three apps ships a systemd unit, an installer, or a config-directory convention; each is started from a terminal in a project directory. Verified on 2026-09-02 by searching every tracked file and the gitignored `README-AGENTS.md` of all three trees for `systemd` and `.service` (no hits). What they do share:

- **Configuration** is `config.yaml` in the current working directory, deep-merged over a `config.yaml.default` shipped as package data. Substation resolves `--config` first, then `./config.yaml`, then defaults alone (`/mnt/dev/Apps/SDR Scanner/substation/config.py:702-727`, `:832-859`); Subsample states the same rule in its config module docstring (`/mnt/dev/Apps/Subsample/subsample/config.py:1-5`). Both scaffold the file with `--init`, all-or-nothing and never overwriting (`/mnt/dev/Apps/Subsample/subsample/cli.py:215-225`; `/mnt/dev/Apps/SDR Scanner/substation/cli.py:323`). Subsequence has no config file at all: the composition script is the configuration.
- **Logging** is `logging.basicConfig` to stderr with a timestamped format (`/mnt/dev/Apps/Subsample/subsample/cli.py:1398-1403`; `/mnt/dev/Apps/SDR Scanner/substation/cli.py:267-270`; `/mnt/dev/Apps/2026-02 Sequencer/subsequence/__main__.py:9`).
- **Optional integrations fail soft.** The Supervisor hook is a lazy import inside a try, warning and continuing when the package is absent, and Subsample also swallows a bind failure so a busy port cannot abort startup (`/mnt/dev/Apps/Subsample/subsample/cli.py:1747-1769`; `/mnt/dev/Apps/SDR Scanner/substation/cli.py:240-252`).
- **Packaging** is identical across the three: `setuptools>=77` plus `setuptools-scm>=8`, `dynamic = ["version"]`, SPDX `license = "AGPL-3.0-or-later"`, `py.typed` and data files as package data, a console script, strict mypy (`/mnt/dev/Apps/2026-02 Sequencer/pyproject.toml`, `/mnt/dev/Apps/Subsample/pyproject.toml`, `/mnt/dev/Apps/SDR Scanner/pyproject.toml`). Release is a `v*` tag push: `pipx run build`, `twine check`, then `pypa/gh-action-pypi-publish` under PyPI Trusted Publishing with `id-token: write` (`/mnt/dev/Apps/2026-02 Sequencer/.github/workflows/publish.yml:1-46`; `/mnt/dev/Apps/SDR Scanner/.github/workflows/publish.yml:1-48`). Subsequence 0.6.6 and Substation 0.5.1 are live on PyPI under that flow (https://pypi.org/pypi/subsequence/json, https://pypi.org/pypi/substation/json). Subsequence ships its dashboard HTML inside the wheel as package data (`subsequence = ["py.typed", "assets/web/*.html"]`), which is the precedent for shipping Superintendent's client the same way.
- **Serving precedent.** `web_ui.py` serves one HTML file from stdlib `http.server` on a daemon thread and runs `websockets.asyncio.server.serve` on the composition's own loop, broadcasting with `websockets.broadcast` (`/mnt/dev/Apps/2026-02 Sequencer/subsequence/web_ui.py:87-129`, `:157-167`, `:196`). Supervisor put both on one port by answering `/audio/<path>` from `process_request` with a realpath guard, and ran the loop on its own thread for threaded hosts (`/mnt/dev/Apps/Supervisor/supervisor/core.py:131-172`, `:91-119`). Its development mode was one mock WebSocket server per app plus a static `serve.py` (`/mnt/dev/Apps/Supervisor/mocks/mock_sequencer.py:1-87`; `/mnt/dev/Apps/Supervisor/serve.py:1-23`; `README.md:61-62`, `:524-527`).

## The candidate stacks, checked on 2026-09-02

All versions and licences from PyPI metadata; `py.typed` and installed sizes measured in a fresh CPython 3.13.11 venv on the workstation; import time is the best of five cold `python -c "import ..."` runs; RSS is `ru_maxrss` after import.

| Stack | Version | Licence | WebSocket | Static files | Typing | Import / RSS | Installed | Python floor | aarch64 wheels |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| stdlib `http.server` + `asyncio` (reference only) | 3.13 | PSF | none | yes, with the docs' warning "not recommended for production" | stdlib | 57 ms / 21 MB | 0 | any | n/a |
| `websockets` alone, HTTP via `process_request` | 17.1 | BSD-3-Clause | native | one-shot responses only (closes the socket after each reply, no keep-alive; see below) | `py.typed` | 67 ms / 25 MB | 1 pkg, 1 MB | 3.11 (16.1 was the last for 3.10) | yes |
| Starlette + uvicorn | 1.6.0 / 0.52.4 | BSD-3-Clause / BSD-3-Clause | `WebSocketRoute`; uvicorn uses `websockets` if importable, else `wsproto`, else refuses WebSocket | `StaticFiles(html=True)` | both `py.typed` | 87 ms / 29 MB | 6 pkgs, 4 MB (anyio, h11, click, websockets) | 3.10 | yes |
| FastAPI + uvicorn | 0.141.1 | MIT | as Starlette | as Starlette | `py.typed` | 246 ms / 43 MB | 13 pkgs, 14 MB (adds pydantic, pydantic-core) | 3.10 | yes |
| aiohttp | 3.14.3 | Apache-2.0 AND MIT | `WebSocketResponse`, plus a WebSocket client in the same package | `web.static`, docs recommend a reverse proxy "in production" but call it "very convenient" for development | `py.typed` | 135 ms / 37 MB | 9 pkgs, 10 MB (C extensions: multidict, yarl, frozenlist, propcache) | 3.10 | yes |
| Quart + Hypercorn | 0.23.1 / 0.18.0 | MIT / MIT | `@app.websocket`, one coroutine per socket so send and receive need separate tasks | Flask-style `static_folder` | both `py.typed` | 184 ms / 39 MB | 16 pkgs, 7 MB (Flask, Werkzeug, Jinja2, h2, wsproto) | **3.13** for 0.23; 0.22.0 is what resolves on 3.12 | yes |

Sources: https://pypi.org/pypi/websockets/json, https://pypi.org/pypi/starlette/json, https://pypi.org/pypi/uvicorn/json, https://pypi.org/pypi/fastapi/json, https://pypi.org/pypi/aiohttp/json, https://pypi.org/pypi/quart/json, https://pypi.org/pypi/hypercorn/json; the websockets changelog for the 13.0 asyncio implementation, the 14.0 deprecation of the legacy one and the 17.0 Python floor (https://websockets.readthedocs.io/en/stable/project/changelog.html); the websockets FAQ that HTTP and WebSocket "have widely different operational characteristics" and that `process_request` is for "simple cases" (https://websockets.readthedocs.io/en/stable/faq/server.html); Starlette's `StaticFiles` and `WebSocket` docs (https://raw.githubusercontent.com/Kludex/starlette/master/docs/staticfiles.md, https://raw.githubusercontent.com/Kludex/starlette/master/docs/websockets.md); aiohttp's static-file and deployment pages (https://docs.aiohttp.org/en/stable/web_advanced.html, https://docs.aiohttp.org/en/stable/deployment.html); Quart's WebSocket guide (https://quart.palletsprojects.com/en/latest/how_to_guides/websockets.html); Hypercorn's protocol list (https://hypercorn.readthedocs.io/en/latest/); Python's `http.server` warning (https://docs.python.org/3/library/http.server.html). The uvicorn selection order is in its installed source: `websockets` first, then `wsproto`, else no WebSocket protocol (`uvicorn/protocols/websockets/auto.py:6-21`), and `uvloop` whenever importable (`uvicorn/loops/auto.py:7-16`), so `uvicorn[standard]` silently runs on uvloop (dual MIT / Apache-2.0, https://pypi.org/pypi/uvloop/json); pass `loop="asyncio"` to keep the stdlib loop. The aarch64 column is a `uv pip install --dry-run --only-binary :all: --python-platform aarch64-manylinux_2_28 --python-version 3.11` resolution of all seven packages, which succeeded, so a Raspberry Pi install needs no compiler.

**Two facts the table cannot show.** Under `mypy --check-untyped-defs --warn-return-any --strict-equality` the four prototypes produced no error attributable to any library; the only two errors were in the prototype code itself (each library's hints are complete enough for the house configuration). And the `websockets`-only server answers a plain HTTP request correctly but then closes the TCP connection without a `Connection: close` header: a keep-alive client's next request on that socket fails with `RemoteDisconnected` (measured with `http.client`, alternating success and failure; the three framework servers served three requests on one connection). Browsers recover, but it confirms the FAQ's own position that this is not an HTTP server.

**Python floors that matter.** Ubuntu 24.04 ships Python 3.12.3 (https://packages.ubuntu.com/noble/python3), Ubuntu 22.04 ships 3.10.6 (https://packages.ubuntu.com/jammy/python3), Debian trixie and therefore Raspberry Pi OS trixie ship 3.13.5 (https://packages.debian.org/trixie/python3, https://www.raspberrypi.com/news/trixie-the-new-version-of-raspberry-pi-os/). `websockets` 17 needs 3.11, so a 22.04 server would pin `websockets<17`; current Quart needs 3.13, which excludes the 24.04 system interpreter outright. Subsequence and Substation declare `>=3.10`, Subsample `>=3.12`.

## Measured cost to a co-located Subsequence clock

**Method.** `benchmarks/clock_jitter.py` from the Subsequence tree, unmodified, run as a separate process for 32 bars at 120 BPM (3072 pulses at 20.833 ms) with `--device` naming a non-existent port, so the engine runs its documented no-port path and nothing opens a real MIDI device (`/mnt/dev/Apps/2026-02 Sequencer/subsequence/midi_utils.py:351-354`); jitter is `perf_counter() - next_pulse_time` per pulse (`subsequence/sequencer.py:1566-1567`). Each candidate stack was a minimal but complete server (static `index.html` plus a 200 KB `app.js`, one WebSocket endpoint sending a 16 by 8 grid snapshot on connect and rebroadcasting it at a fixed rate, inbound toggles applied) running on the same host, driven by a load generator also on the same host: `idle` is one connected client and a 20 Hz broadcast; `panel` is four clients each sending a toggle at 10 Hz, 20 Hz broadcast, and 20 static fetches a second; `stress` is eight clients toggling at 20 Hz, a 100 Hz broadcast, and 50 fetches a second. Server CPU is `psutil` per-process percent of one core sampled every 0.5 s; the load generator's own CPU is reported because it too competed with the clock. Machine: the development workstation, Intel i7-9700K, 8 cores, 31 GB, Ubuntu kernel 6.8.0-138, CPython 3.13.11, no pinning, ordinary desktop background load. Each scenario ran once; the two baselines bracket the matrix and show the workstation's own noise. Scripts and raw JSON are under `/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad/serving/bench/` (`driver.py`, `srv_*.py`, `load.py`, `full.json`); they are prototypes, not house style.

| Scenario | Jitter mean | median | p95 | p99 | max | Server CPU mean / max | Server RSS | Load-gen CPU | Delivered |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline, nothing else running | 1 µs | 1 µs | 2 µs | 2 µs | 0.12 ms | | | | |
| baseline repeated at the end | 1 µs | 1 µs | 1 µs | 1 µs | 1.59 ms | | | | |
| `websockets` idle | 11 µs | 1 µs | 2 µs | 339 µs | 3.38 ms | 0.5 % / 4 % | 28 MB | 0.4 % | 19.9 msg/s |
| `websockets` panel | 2 µs | 1 µs | 2 µs | 9 µs | 0.70 ms | 4.8 % / 8 % | 29 MB | 3.6 % | 78 msg/s, 1358 fetches |
| `websockets` stress | 2 µs | 1 µs | 2 µs | 2 µs | 0.58 ms | 16.6 % / 26 % | 30 MB | 14.6 % | 716 msg/s, 3380 fetches |
| Starlette + uvicorn idle | 2 µs | 2 µs | 2 µs | 6 µs | 1.38 ms | 0.9 % / 4 % | 38 MB | 0.5 % | 19.8 msg/s |
| Starlette + uvicorn panel | 2 µs | 2 µs | 2 µs | 2 µs | 0.06 ms | 8.9 % / 14 % | 40 MB | 4.1 % | 80 msg/s, 1357 fetches |
| Starlette + uvicorn stress | 2 µs | 2 µs | 2 µs | 10 µs | 0.08 ms | 27.7 % / 40 % | 41 MB | 16.2 % | 768 msg/s, 3380 fetches |
| aiohttp idle | 2 µs | 2 µs | 2 µs | 13 µs | 0.05 ms | 0.7 % / 2 % | 41 MB | 0.5 % | 19.8 msg/s |
| aiohttp panel | 2 µs | 2 µs | 2 µs | 3 µs | 0.06 ms | 7.4 % / 12 % | 42 MB | 4.0 % | 78 msg/s, 1357 fetches |
| aiohttp stress | 2 µs | 1 µs | 2 µs | 2 µs | 0.97 ms | 22.0 % / 32 % | 43 MB | 14.8 % | 718 msg/s, 3378 fetches |
| Quart + Hypercorn idle | 3 µs | 2 µs | 5 µs | 14 µs | 1.87 ms | 1.1 % / 4 % | 43 MB | 0.6 % | 19.7 msg/s |
| Quart + Hypercorn panel | 1 µs | 1 µs | 2 µs | 2 µs | 0.08 ms | 40.0 % / 64 % | 46 MB | 6.0 % | 79 msg/s, 1357 fetches |
| Quart + Hypercorn stress | 3 µs | 1 µs | 1 µs | 2 µs | 2.80 ms | 50.5 % / 74 % | 49 MB | 11.0 % | 763 msg/s, 3295 fetches |
| FastAPI + uvicorn panel | 2 µs | 2 µs | 2 µs | 3 µs | 1.62 ms | 8.7 % / 14 % | 53 MB | 4.0 % | 80 msg/s, 1357 fetches |
| hostile: a busy loop on every core, no server | 419 µs | 1 µs | 2.30 ms | 3.49 ms | 18.9 ms | | | | |

**What the numbers say.** With any of the four stacks co-located and under any of the three loads, the clock's mean jitter stays at 1 to 3 µs and its p99 within 14 µs, against a baseline of 1 to 2 µs; the one exception, a p99 of 339 µs in the `websockets` idle run, is a single cluster that did not recur under the heavier loads of the same server and so is not attributable to it. The maxima (0.05 to 3.4 ms) are scattered across scenarios with no relation to load, and the empty second baseline produced 1.59 ms on its own, so they are the workstation's background, not the service. The service's cost is CPU rather than jitter: 5 to 9 % of one core for the plausible panel load on the three light stacks, 40 % for Quart, and 17 to 51 % under a stress load no panel produces. The hostile run marks where that would start to matter: only when every core is busy does the clock degrade (mean 0.42 ms, p99 3.5 ms, max 19 ms), which the spin-wait scheduler cannot prevent; a service holding a tenth of one core on an eight-core host is two orders of magnitude from that. On a four-core Raspberry Pi the margin shrinks and the matrix should be re-run there before co-locating on one.

## Trade-offs

| | Starlette + uvicorn | aiohttp | `websockets` alone | Quart + Hypercorn | FastAPI + uvicorn |
| --- | --- | --- | --- | --- | --- |
| WebSocket and static in one process | yes | yes | WebSocket yes; static is a one-shot responder with no keep-alive | yes | yes |
| Client side for reaching the apps | `websockets` client (already a dependency) or `httpx`; OSC via `python-osc` on the same loop | its own WebSocket and HTTP client | its own client | none built in | as Starlette |
| House-style fit (`import x`, fully-qualified, strict mypy) | typed, small surface, declarative routes | typed, larger surface, more C extensions | typed, smallest surface, hand-rolled HTTP | typed, Flask idioms and globals (`quart.websocket`) | typed, but pydantic models are the idiom |
| Footprint | 4 MB, 6 packages, 29 MB RSS | 10 MB, 9 packages, 37 MB RSS | 1 MB, 1 package, 25 MB RSS | 7 MB, 16 packages, 39 MB RSS | 14 MB, 13 packages, 43 MB RSS |
| Jitter and CPU under load | mean 2 µs, p99 2 to 10 µs; 8.9 % of a core at panel load, 27.7 % at stress | mean 2 µs, p99 2 to 13 µs; 7.4 % at panel load, 22 % at stress | mean 2 to 11 µs, p99 2 to 339 µs; 4.8 % at panel load, 16.6 % at stress (lightest) | mean 1 to 3 µs, p99 2 to 14 µs; 40 % at panel load, 50.5 % at stress (heaviest) | mean 2 µs, p99 3 µs; 8.7 % at panel load (as Starlette) |
| Python floor today | 3.10 (3.11 with `websockets` 17) | 3.10 | 3.11 | 3.13 | 3.10 |
| Licence | BSD-3 / BSD-3 | Apache-2.0 AND MIT | BSD-3 | MIT / MIT | MIT |
| Risk | uvicorn's `auto` picks uvloop when present; pin `loop="asyncio"` or drop the `standard` extra | reverse-proxy posture in its own docs; heaviest native-extension set to rebuild on a new Python | grows a hand-written HTTP layer as soon as the client needs more than a few files | the newest release abandons 3.12; the most CPU for the same work | pays for request validation the surface does not use (WebSocket payloads are not validated by FastAPI) |

## Short list

- **Starlette on uvicorn, with `websockets` as the WebSocket implementation and the stdlib loop.** Two BSD packages plus anyio, h11 and click; typed; `StaticFiles(html=True)` and `WebSocketRoute` are the whole HTTP surface the first use-case needs. FastAPI can be layered on later without changing the server or the routes if REST endpoints with validation ever appear.
- **aiohttp.** One package that is both the server and the client, which matters if `transport-apps` chooses WebSocket to the apps; the cost is 10 MB of C extensions and a documentation posture that treats standalone static serving as a development convenience.
- **`websockets` alone with `process_request` static serving.** The Supervisor and `web_ui.py` shape, one dependency Subsequence already carries, and the lightest process; acceptable only while the client is a handful of files, because it is not an HTTP server and its own FAQ says so.

Quart with Hypercorn is excluded from the short list because its current release requires Python 3.13 while the likely server interpreter is 3.12, and because it cost the most CPU for identical work in the measurements; FastAPI is excluded because it is Starlette plus 10 MB of pydantic for validation the surface does not exercise, and it remains reachable from the first option.

## Recommendation

**Starlette on uvicorn, `loop="asyncio"`, `ws="websockets"`**, run programmatically from the package's own console script so the unit file is one `ExecStart`. Reason: it is the smallest fully typed stack that serves the page and the socket from one process, it reuses the `websockets` library Subsequence already depends on, the measured cost to a co-located clock is not measurable (mean 2 µs and p99 within 10 µs at every load, against a 1 to 2 µs baseline) for under a tenth of one core at panel load, and it leaves both the REST direction (FastAPI) and the reverse-proxy direction (a TLS terminator in front, for `security-later`) open without rewriting anything.

## Deployment shape

**Process model.** One process, one asyncio loop: uvicorn serves the static client and the browser WebSocket; the same loop hosts whatever client the `transport-apps` point chooses (OSC via `python-osc`, or a `websockets` client per app). A `lifespan` context starts and stops the app connections. Nothing in the service touches audio or MIDI hardware unless `subsample-substation` puts pad MIDI in it, in which case the unit needs the `audio` group like the apps do.

**systemd unit.** Two candidates, and the difference is who owns the process:

| | System unit (`/etc/systemd/system/superintendent.service`) | User unit (`~/.config/systemd/user/superintendent.service` with `loginctl enable-linger`) |
| --- | --- | --- |
| Starts at boot with no login | yes | yes, once linger is enabled: "a user manager is spawned for the user at boot and kept around after logouts" |
| Runs as | `User=` set explicitly, no access to the user's session bus or ALSA seat by default | the same account that runs the music apps today, so the same venv, `~/.config` and ALSA permissions |
| Install without root | no | yes |
| Fits how the apps run today (a user's venv in a project directory) | needs `WorkingDirectory=` and `ExecStart=` pointing into that user's venv | naturally |

Recommend the **user unit**, because it matches the sibling apps' single-user, venv-in-a-directory deployment and because the same shape works unchanged when the apps themselves are given units later. Sketch, with every claim from `systemd.service(5)`, `systemd.exec(5)` and `systemd.unit(5)`:

```
[Unit]
Description=Superintendent control surface
After=network-online.target
Wants=network-online.target

[Service]
Type=exec
WorkingDirectory=%h/studio/superintendent
ExecStart=%h/studio/superintendent/.venv/bin/superintendent --config %h/studio/superintendent/config.yaml
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
```

`Type=exec` marks the unit started "immediately after the main service binary has been executed"; `Restart=on-failure` restarts "when the process exits with a non-zero exit code, is terminated by a signal ... and when the configured watchdog timeout is triggered", and `RestartSec` "defaults to 100ms" so a value is set to avoid a tight crash loop; `ExecStart` must be "an absolute path to an executable" (https://man7.org/linux/man-pages/man5/systemd.service.5.html). User units load from `$XDG_CONFIG_HOME/systemd/user` or `~/.config/systemd/user` (https://man7.org/linux/man-pages/man5/systemd.unit.5.html); linger from `loginctl enable-linger` (https://man7.org/linux/man-pages/man1/loginctl.1.html). `Type=notify` with `WatchdogSec=` is the upgrade path if the service ever needs liveness supervision: `READY=1` and `WATCHDOG=1` are single datagrams to `$NOTIFY_SOCKET`, which needs no libsystemd binding (https://man7.org/linux/man-pages/man3/sd_notify.3.html); not recommended for v1 because a restart under systemd is already what the browser's reconnect (`transport-ui`) is designed to survive.

**Configuration file.** Two candidates:

| | YAML `config.yaml`, deep-merged over a bundled `config.yaml.default`, scaffolded by `--init` | TOML in `$XDG_CONFIG_HOME/superintendent/config.toml` |
| --- | --- | --- |
| Precedent | exactly Subsample's and Substation's mechanism, including the "never overwrite" `--init` | none in the stack |
| Library | PyYAML, already a dependency of all three apps | `tomllib` in the stdlib since 3.11, read-only ("This module does not support writing TOML") |
| Location | the working directory, which under systemd is `WorkingDirectory=`, plus `--config` | `$XDG_CONFIG_HOME` defaulting to `$HOME/.config` (https://specifications.freedesktop.org/basedir-spec/latest/) |
| Comments and self-documentation | the shipped default is the documentation, as in the siblings | comments survive but the bundled-default merge has to be reimplemented |

Recommend **YAML with the sibling mechanism**, and add an XDG fallback only if a config-less start turns out to be wanted: the same file resolution order as Substation (`--config`, then `./config.yaml`, then defaults), so a user who knows one app knows all four. The `pages:` that `control-contract` defines are user data, not service configuration, and belong in `$XDG_DATA_HOME` or the working directory rather than in this file.

**App discovery.** Three ways, of which v1 needs one:

| | Static table in `config.yaml` | Registration (apps connect out to the service) | mDNS (`zeroconf`) |
| --- | --- | --- | --- |
| Works when apps are on other hosts | yes, by hostname | yes | same L2 segment only |
| Extra dependency | none | none | `zeroconf` 0.151.3, LGPL-2.1-or-later (https://pypi.org/pypi/zeroconf/json), GPLv3-compatible per the FSF (https://www.gnu.org/licenses/license-list.en.html) |
| Handles an app restarting | reconnect loop with backoff in the service | the app reconnects | re-announce |
| Who decides | `topology` and `transport-apps` | same | same |

Recommend the **static table** for v1, with entries defaulting to today's port map (Subsequence OSC 9000/9001, Subsample OSC 9002, Supervisor-style adapters 9003/9004) so an empty section still finds co-located apps, and a reconnect loop per app so a missing app is a greyed page, not a failed service. The service's own ports must not be any of 5555, 8080, 8765, 9000 to 9004; the prototypes used 18801 to 18805.

**Logging.** Log to stderr through `logging`, as the siblings do; under systemd stdout and stderr go to the journal by default (`DefaultStandardOutput=journal`, https://manpages.ubuntu.com/manpages/noble/en/man5/systemd-system.conf.5.html), which timestamps every line, so the service should drop `%(asctime)s` from its format when `$JOURNAL_STREAM` is set, the variable systemd sets when "the standard output or standard error output of the executed processes are connected to the journal" (https://manpages.debian.org/stretch/systemd/systemd.exec.5.en.html). uvicorn's access log is off (`access_log=False`) because a 20 Hz WebSocket is not an access-log workload, and its own logging config is replaced by the package's so there is one format.

**Packaging.** Copy the sibling `pyproject.toml` and `publish.yml` verbatim in shape: `setuptools>=77`, `setuptools-scm>=8`, `dynamic = ["version"]`, `license = "AGPL-3.0-or-later"`, `requires-python = ">=3.11"` (the `websockets` 17 floor; `>=3.10` is possible only by pinning `websockets<17`), dependencies `starlette`, `uvicorn`, `websockets`, `pyyaml`, `python-osc` if OSC is the app transport; a `dev` extra with mypy and pytest; the client's HTML, CSS, JS and every vendored library as package data under `superintendent/assets/web/` so `pip install` is the whole deployment and the surface works with no internet (the Supervisor CDN lesson). The release flow is the tag push under Trusted Publishing, which PyPI describes as short-lived OIDC tokens instead of long-lived API tokens (https://docs.pypi.org/trusted-publishers/). **The name `superintendent` is taken on PyPI** by an unrelated MIT-licensed labelling tool at 0.6.0 since 2022 (https://pypi.org/pypi/superintendent/json), so the distribution name has to differ from the project name.

**Development mode.** Two layers, both cheap: mock app endpoints in the Supervisor manner (`mocks/mock_*.py` speaking the `transport-apps` protocol with canned state, one file per app), and the real Subsequence engine with no hardware, which already works: the clock runs and logs "not found" when the named output device does not exist, by documented design (`/mnt/dev/Apps/2026-02 Sequencer/subsequence/midi_utils.py:351-354`), and `render()` exists for offline runs (`composition.py:5427`). A `superintendent --dev` flag that starts the service against `mocks/` on a non-standard port, with uvicorn's `reload` for the static files, is enough; Supervisor's warning that `.pyc` caching on network mounts served stale code (`README.md:540-545`) argues for `PYTHONDONTWRITEBYTECODE=1` in that mode.

## Not covered

- The measurements were made on the development workstation, not the headless server, and with a synthetic load generator on the same host rather than a browser on the network; the numbers are indicative and the method is reproducible with the scripts under `/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad/serving/bench/`.
- Whether the service should share the apps' host at all is `topology`'s question; this document only establishes what sharing costs.

## Hardware-gated

Nothing here needs the iiyama panel or a graphical host. Two measurements are gated on machines rather than the panel: the jitter matrix should be re-run on the actual headless server (unknown CPU and Ubuntu release), and on a Raspberry Pi if the service is ever to run on one, using the same driver.

## Provenance

Files read: `/mnt/dev/Apps/2026-02 Sequencer/pyproject.toml`, `subsequence/web_ui.py`, `subsequence/__main__.py`, `subsequence/midi_utils.py`, `subsequence/sequencer.py`, `subsequence/composition.py`, `subsequence/helpers/network.py`, `benchmarks/clock_jitter.py`, `.github/workflows/publish.yml`; `/mnt/dev/Apps/Subsample/pyproject.toml`, `subsample/cli.py`, `subsample/config.py`; `/mnt/dev/Apps/SDR Scanner/pyproject.toml`, `substation/cli.py`, `substation/config.py`, `.github/workflows/publish.yml`; `/mnt/dev/Apps/Supervisor/pyproject.toml`, `serve.py`, `supervisor/core.py`, `supervisor/app/subsample.py`, `mocks/mock_sequencer.py`, `README.md`; installed `uvicorn/config.py`, `uvicorn/protocols/websockets/auto.py`, `uvicorn/loops/auto.py`. Subroutine: #1465, #1464, #1461, #613, #611, #1478, #384, #397. URLs: as cited inline.
