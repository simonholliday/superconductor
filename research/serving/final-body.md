Summary: Five Python stacks were installed and four of them prototyped as the same static-plus-WebSocket service and load-tested beside Subsequence's own `clock_jitter.py` benchmark on the development workstation. Starlette on uvicorn is recommended (BSD-3, ASGI, typed, explicit route table, ETag static serving, seven runtime packages with plain uvicorn, 27 to 32 MB RSS, 5 to 19 percent of one core under a sixteen-client load); aiohttp is the equally complete alternative and websockets plus a hand-written static handler the lean one; FastAPI and Quart are excluded with reasons. Beside any loaded service Subsequence's median jitter stayed at 1 to 2 microseconds and its mean within 15 microseconds of a 1 to 3 microsecond baseline; the P99 rose to 0.35 and 0.57 ms in two of eighteen loaded runs and stayed within 11 microseconds in the other sixteen, including two repeats of each of those two conditions, so the tail excursions did not reproduce; only pinning service and sequencer to one core moved the whole distribution (P99 2.0 ms). Deployment is a system or user systemd unit with `Type=notify` via a ten-line stdlib `sd_notify`, `Restart=on-failure`, stdout to journald, uvicorn's access log switched off explicitly, a YAML config found by `--config`, then the working directory, then XDG, then `/etc`, app discovery by registration as #1919 recommends (each app dials the service at one address and the config names the apps expected), packaging on setuptools-scm with PEP 639 and no direct-URL dependencies, and a development mode that runs a real Subsequence with no MIDI device and mocks only Subsample and Substation.

**Question.** What Python stack runs the Superintendent UI service on the headless Ubuntu server, and how is it deployed, configured, discovered, logged, packaged and developed alongside the three music apps?

## What the sibling apps already do

The three apps set the conventions the service should match rather than invent.

- **Packaging.** All three build with `setuptools>=77` and `setuptools-scm>=8.0`, declare `dynamic = ["version"]`, carry a PEP 639 SPDX `license = "AGPL-3.0-or-later"`, ship `py.typed`, and expose a console script (`/mnt/dev/Apps/2026-02 Sequencer/pyproject.toml`, `/mnt/dev/Apps/Subsample/pyproject.toml`, `/mnt/dev/Apps/SDR Scanner/pyproject.toml`). Substation alone caps `setuptools<81` because setuptools 81 removed `pkg_resources`, which some of its runtime dependencies still import (`/mnt/dev/Apps/SDR Scanner/pyproject.toml:2-5`). Subsequence ships its legacy dashboard HTML as package data, `subsequence = ["py.typed", "assets/web/*.html"]` (`pyproject.toml:53-54`), which is the precedent for shipping static UI files inside the wheel. Substation's `pyproject.toml` records that PyPI rejects any distribution whose dependencies are direct URLs, so Supervisor is not an extra there (comment block at `pyproject.toml:70-72`); the same rule binds Superintendent.
- **Configuration.** Subsample and Substation both look for `./config.yaml` in the working directory, accept `--config PATH`, and scaffold a fully commented default with `--init` (`/mnt/dev/Apps/Subsample/subsample/cli.py:145-157` for `--config`, `:167-176` for `--init`; `/mnt/dev/Apps/SDR Scanner/substation/cli.py:286-290` for `--config`, `:322-327` for `--init` with `init_config()` at `:71`, the `./config.yaml` lookup at `substation/config.py:706-724`, `INSTALL.md:221`). Substation validates with pydantic (`config.py:581-598`); Subsample deep-merges a user file over a shipped `config.yaml.default` (`subsample/config.py:3-5`). Neither has a systemd unit or any daemonisation guidance in the tree (a grep of both READMEs, `INSTALL.md` and both packages for `systemd`, `ExecStart` and `WantedBy` returns nothing).
- **Adapter enabling.** Both apps switch their optional Supervisor adapter on with an `enabled:` flag and a `port:` (`substation/config.py:597-598`, default 9004; `subsample/config.py:564-568`, default 9003). Their failure paths differ: Subsample catches both `ImportError` and `OSError`, so a missing package or a busy port degrades to a warning (`subsample/cli.py:1747-1769`); Substation's `_start_supervisor` catches `ImportError` only (`substation/cli.py:240-252`) and both call sites then `await sv.start()` unguarded (`cli.py:158-161`, `224-227`), so a busy port there raises. The bind-failure path is one of the costs of any design that adds a listening socket to an app (see Discovery).
- **Python floors.** Subsequence `>=3.10`, Substation `>=3.10`, Subsample `>=3.12` (each `pyproject.toml`, `requires-python`). Ubuntu 24.04 ships Python 3.12.3 (https://packages.ubuntu.com/noble/python3), 22.04 ships 3.10.6 (https://packages.ubuntu.com/jammy/python3), 26.04 ships 3.14.3 (https://packages.ubuntu.com/resolute/python3).
- **The websockets floor.** Subsequence declares `websockets>=12.0` (`pyproject.toml:23`) yet `web_ui.py:21` imports `websockets.asyncio.server`, which arrived in websockets 13.0 (https://websockets.readthedocs.io/en/stable/project/changelog.html). Supervisor pins `>=13.0` (`/mnt/dev/Apps/Supervisor/pyproject.toml:12`). A shared venv with Superintendent pulls websockets 17.x (requires Python >=3.11), which satisfies both.
- **Supervisor's shape.** `BroadcastServer` ran `websockets.serve` on `0.0.0.0` and served `GET /audio/<path>` through `process_request` with a realpath guard (`/mnt/dev/Apps/Supervisor/supervisor/core.py:56-70`, `131-172`); the static page came from `http.server.SimpleHTTPRequestHandler` in a separate process on port 8000 (`serve.py:1-23`); development ran against `mocks/mock_sequencer.py`, a websockets server emitting a fixed manifest and a synthetic state every 100 ms (`mocks/mock_sequencer.py:8-87`; the manifest at 8, the sleep at 76, `websockets.serve` at 82, `asyncio.run` at 87).

## The stack

### Candidates as installed on 2026-09-03

Each candidate was installed into its own Python 3.12 venv under the scratchpad (FastAPI into a 3.13 venv) and, for four of them, the same prototype written against it: one static directory, one WebSocket endpoint broadcasting a 128-cell grid state at 30 Hz and echoing every tap to every client. Package versions and licences are from PyPI JSON metadata fetched on the day. Import time is the minimum of three warm `python -c` runs of the imports the prototype needs; RSS is `ru_maxrss` after import; both measured in the same way for every column on 2026-09-03 (a first cold run is two to three times slower and 5 to 17 MB larger for every stack).

| | Starlette + uvicorn | aiohttp | websockets + stdlib HTTP | Quart + Hypercorn | FastAPI + uvicorn |
| --- | --- | --- | --- | --- | --- |
| Versions, licence | starlette 1.6.0 BSD-3 (2026-08-08); uvicorn 0.52.4 BSD-3 (2026-08-19) | 3.14.3, Apache-2.0 AND MIT (2026-07-23) | 17.1 BSD-3 (2026-08-26) | quart 0.23.1 MIT (requires Python >=3.13; 0.22.0 resolves on 3.12); hypercorn 0.18.0 MIT | 0.141.1 MIT (2026-07-29) |
| Python floor | >=3.10 | >=3.10 (cp314 wheels) | >=3.11 | >=3.13 for the current release | >=3.10 |
| Runtime distributions installed | 7 with plain uvicorn (starlette, uvicorn, websockets, anyio, click, h11, idna); 12 with `uvicorn[standard]` (adds uvloop, httptools, watchfiles, python-dotenv, pyyaml); one more, typing-extensions, on Python 3.12 | 9 (aiohttp, attrs, multidict, yarl, frozenlist, aiosignal, aiohappyeyeballs, propcache, idna), of which 5 carry C extensions (aiohttp, multidict, yarl, frozenlist, propcache) | 1 | 16 (quart, hypercorn, flask, werkzeug, jinja2, markupsafe, itsdangerous, blinker, click, aiofiles, h11, h2, hpack, hyperframe, priority, wsproto) | the Starlette set plus fastapi, pydantic, pydantic-core, annotated-types, annotated-doc, typing-inspection and typing-extensions |
| `py.typed` shipped | starlette, uvicorn and every dependency | aiohttp and every dependency | websockets | quart, hypercorn, flask, werkzeug and the rest | yes |
| mypy --strict on the prototype | only the prototype's own untyped lines flagged; library types resolve | same | same | same | not prototyped |
| Warm import time / peak RSS | 0.072 s / 27 MB (standard extra); 0.071 s / 27 MB (plain uvicorn) | 0.141 s / 35 MB | 0.054 s / 24 MB | 0.157 s / 37 MB | 0.196 s / 43 MB on Python 3.13, where Starlette alone is 0.063 s / 28 MB |
| WebSocket API | `starlette.websockets.WebSocket` with `accept`, `receive_json`, `send_json`, `iter_text`, `close`; `WebSocketRoute` (https://raw.githubusercontent.com/encode/starlette/master/docs/websockets.md) | `aiohttp.web.WebSocketResponse` with `prepare`, `async for msg in ws`, `send_str` (https://docs.aiohttp.org/en/stable/web_quickstart.html) | `websockets.asyncio.server.serve`, `websockets.broadcast` (https://websockets.readthedocs.io/en/stable/reference/asyncio/server.html) | `@app.websocket`, `websocket.receive/send`, CancelledError on disconnect (https://quart.palletsprojects.com/en/latest/how_to_guides/websockets.html) | Starlette's |
| Fan-out to N browsers | `send_text` awaits uvicorn's `send`, which waits on a `writable` event that the transport clears when a client's write buffer passes the high-water mark (`uvicorn/protocols/websockets/websockets_sansio_impl.py:165-175`, `432-433` in the installed 0.52.4), so a sequential `for c in clients: await c.send_text()` stalls on one slow client; a per-client bounded queue drained by its own task is required work (see Short list) | `send_str` awaits the transport's drain likewise; same per-client queue needed | `broadcast()` never awaits and skips connections that are not open; there is no backpressure, so a slow client's buffer grows until `ping_interval`/`ping_timeout` close it (docstring, `websockets/asyncio/connection.py:1149-1207` in 17.1, and the URL above) | one coroutine per socket; same queue pattern | Starlette's |
| Static serving | `starlette.staticfiles.StaticFiles(directory, packages, html)`; ETag and `If-None-Match` handled (`staticfiles.py:205-213` in the installed 1.6.0) | `web.static(prefix, path)`; the docs recommend a reverse proxy for static files in production and call `web.static` convenient for development, which is a throughput note, not a functional gap for one panel (https://docs.aiohttp.org/en/stable/web_advanced.html) | none; `process_request` may return a `Response`, and the FAQ says providing an HTTP server is out of scope (https://websockets.readthedocs.io/en/stable/faq/server.html) | `send_from_directory` | Starlette's |
| House-style fit (`import x` only, fully-qualified names, tabs) | Explicit route table, `starlette.routing.WebSocketRoute(...)`, no decorators required; `uvicorn.Server(uvicorn.Config(...)).serve()` runs on an existing loop (`uvicorn/server.py:58-79`) | Explicit `app.add_routes([...])`; fits | Plain functions; fits | Flask-shaped module-level `app` and decorators; fits less well | decorator-first; fits, but its value (request validation, OpenAPI) is not used by a WebSocket service |
| Service CPU under load, prototype (see measurements) | 4 to 6 percent of a core with the standard extra; 9 and 19 percent in two `load16` runs on plain uvicorn | 2 to 5 percent | 2 to 14 percent across four loaded runs | 36 percent under Hypercorn | not load-tested |

uvicorn's `auto` WebSocket implementation is `websockets-sansio` when `websockets` is importable and `wsproto` otherwise (`uvicorn/protocols/websockets/auto.py` in the installed 0.52.4); the older `websockets` implementation imports `websockets.legacy` and carries a deprecation warning (`websockets_impl.py:12`, `40-45`). websockets 14.0 deprecated the legacy implementation and 17.1 still ships it (changelog URL above), so nothing in the recommended stack depends on it. `auto` also picks uvloop for the loop and httptools for HTTP whenever they are importable (`uvicorn/loops/auto.py`, `uvicorn/protocols/http/auto.py`), so `uvicorn[standard]` silently runs on uvloop and plain `uvicorn` on the stdlib loop with h11. uvicorn[standard]'s uvloop and httptools both have manylinux aarch64 and cp314 wheels (https://pypi.org/pypi/uvloop/0.22.1/json, https://pypi.org/pypi/httptools/0.8.0/json); plain `uvicorn` is pure Python and is enough for this service (https://raw.githubusercontent.com/encode/uvicorn/master/README.md).

### Short list

| Option | For | Against |
| --- | --- | --- |
| **Starlette + uvicorn** | One ASGI app carries static files, WebSocket and any later HTTP endpoint (asset serving in the Supervisor `/audio/` manner, a health route); ASGI means the server and any middleware (auth, TLS termination for a remote mode) are interchangeable later; the explicit route table reads in the house style; fully typed; ETag-aware static handler; uvicorn runs programmatically on the service's own loop, so app adapters and the browser socket share one loop without a thread | Seven runtime packages with plain uvicorn, twelve with the standard extra, against aiohttp's nine and websockets' one; two projects to track instead of one; fan-out needs a per-client bounded queue (drain task per client, drop-oldest or coalesce-to-latest for state frames) so one stalled Wi-Fi panel cannot hold the 30 Hz broadcast to the others |
| **aiohttp** | One package with its own server and client (the client half can talk to app adapters if `transport-apps` chooses HTTP or WebSocket); also fully typed with `web.static`, WebSockets and arbitrary routes, so it is complete for everything this service serves; lowest CPU in the load test; mature | Its API is aiohttp's own rather than ASGI, so middleware and servers are not interchangeable later; five of its nine dependencies are C extensions; the same per-client queue is needed for fan-out |
| **websockets + a hand-written static handler** | One dependency already in Subsequence's and Supervisor's trees; smallest footprint (24 MB RSS, 0.054 s import); `broadcast()` is a non-awaiting fan-out with no work to do | The maintainers say HTTP is out of scope; static serving through `process_request` means writing MIME, ETag, range and traversal handling by hand (Supervisor's `core.py:131-172` is the size of it); every later HTTP need is more hand-written code; `broadcast()`'s lack of backpressure means a stalled client's memory grows until the keepalive closes it, so `ping_interval` and `ping_timeout` must be set low |

**Excluded.** FastAPI is Starlette plus pydantic request validation and OpenAPI generation; a WebSocket-first service exercises neither, its footprint is the largest of the five (0.196 s, 43 MB against Starlette's 0.063 s, 28 MB in the same 3.13 venv), and the declaration schema from `control-contract` can be validated with pydantic directly if wanted (Substation already depends on `pydantic>=2.0`). Quart is Flask on ASGI: sixteen packages, the current release needs Python 3.13, and the decorator style pushes module-level state. The Quart prototype's 24.5 CPU-seconds under both load levels (the other three used 1.2 to 3.8) is a Hypercorn result, since Quart is an ASGI app that its own deployment page says also runs on uvicorn and Daphne (https://quart.palletsprojects.com/en/latest/tutorials/deployment.html); the cause is unexplained and it is not a ground against Quart, which the other three grounds exclude on their own.

**Recommendation: Starlette on uvicorn.** Starlette and aiohttp are both fully typed and both complete for page, socket and assets, and aiohttp is slightly cheaper in CPU; the choice for Starlette rests on ASGI (server and middleware interchangeable when a remote mode needs TLS or authentication), the ETag-aware static handler, and the route table that reads in the house style. Take plain `uvicorn` plus `websockets` rather than `uvicorn[standard]`: it is pure Python, seven packages, and the plain variant was measured beside the sequencer (below) with the same result as the standard extra. Fan-out must be written as one bounded queue per browser client, drained by that client's own task, so a stalled panel drops frames rather than delaying the others.

## Measured impact on a co-located Subsequence

**Method.** `benchmarks/clock_jitter.py` (`/mnt/dev/Apps/2026-02 Sequencer/benchmarks/clock_jitter.py:36-82`) was run from the working tree for 32 bars at 120 BPM (3072 pulses, 68 s) with `PYTHONPATH` pointing at the tree, `PYTHONDONTWRITEBYTECODE=1`, and `--device SUPERINTENDENT_NO_SUCH_DEVICE` so that `select_output_device` logged the miss and returned `(None, None)` without opening any port (`subsequence/midi_utils.py:369-377`, consumed at `sequencer.py:718-722`). The benchmark constructs a bare `Sequencer` with nothing scheduled (`clock_jitter.py:53-59`): no `Composition`, no patterns, no per-cycle rebuilds, no OSC and no MIDI events, so what is measured is the clock loop alone (`sequencer.py:1489-1571`, jitter logged at `1566-1567`), which is the yardstick the specification names. Each candidate service ran as a separate process on 127.0.0.1 in three conditions: idle with no clients; `load4`, four WebSocket clients receiving the 30 Hz state and each sending a tap at 10 Hz that the server echoes to all, plus one HTTP client fetching a 270 KB page at 10 requests per second; `load16`, sixteen such clients (about 2400 echoed messages per second). Service CPU is utime plus stime from `/proc/<pid>/stat` before and after; RSS from `/proc/<pid>/status`. Machine: the development workstation, Intel i7-9700K, 8 cores, 32 GB, Ubuntu with systemd 255, load average 0.4 to 0.6 at start, Python 3.12.3. Scripts are under the scratchpad `serving/proto/` (`run_matrix.sh`, `run_repeats.sh`, `srv_*.py`, `load.py`, `cpu.py`) and are prototypes, not house style; raw output in `serving/results.txt` and `serving/results-repeats.txt`.

First matrix, one run per condition:

| Condition | Mean | Median | P95 | P99 | Max | Service CPU of one core | Service RSS |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline, no service | 3 us | 1 us | 2 us | 3 us | 2.455 ms | | |
| Starlette idle | 1 us | 1 us | 2 us | 3 us | 0.021 ms | 0.4 % | 37 MB |
| Starlette load4 | 11 us | 1 us | 2 us | 0.351 ms | 2.638 ms | 4.3 % | 40 MB |
| Starlette load16 | 1 us | 1 us | 1 us | 1 us | 0.015 ms | 5.6 % | 41 MB |
| aiohttp idle | 5 us | 1 us | 1 us | 2 us | 1.519 ms | 0.2 % | 39 MB |
| aiohttp load4 | 1 us | 1 us | 1 us | 16 us | 0.473 ms | 1.9 % | 39 MB |
| aiohttp load16 | 3 us | 1 us | 1 us | 2 us | 1.630 ms | 4.7 % | 41 MB |
| websockets idle | 4 us | 1 us | 1 us | 16 us | 1.494 ms | 0.2 % | 27 MB |
| websockets load4 | 2 us | 1 us | 1 us | 1 us | 1.619 ms | 1.7 % | 27 MB |
| websockets load16 | 15 us | 1 us | 1 us | 0.568 ms | 2.906 ms | 5.5 % | 27 MB |
| Quart idle | 2 us | 2 us | 2 us | 3 us | 0.046 ms | 0.5 % | 42 MB |
| Quart load4 | 1 us | 1 us | 2 us | 7 us | 0.046 ms | 36 % | 42 MB |
| Quart load16 | 1 us | 1 us | 2 us | 4 us | 1.023 ms | 36 % | 46 MB |
| Starlette load16, service and Subsequence pinned to the same core | 116 us | 2 us | 0.916 ms | 2.049 ms | 3.212 ms | | |

Repeats, run afterwards on the same machine (load average 0.36 at start), for the two loaded conditions whose single-run P99 had moved, two more baselines to bracket them, and the plain-uvicorn variant the recommendation names:

| Condition | Mean | Median | P95 | P99 | Max | Service CPU of one core | Service RSS |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline, no service, second run | 1 us | 2 us | 2 us | 3 us | 0.064 ms | | |
| Starlette load4, second run | 2 us | 1 us | 2 us | 3 us | 0.635 ms | 5.8 % | 39 MB |
| websockets load16, second run | 1 us | 1 us | 2 us | 3 us | 0.338 ms | 7.9 % | 26 MB |
| Starlette on plain uvicorn (stdlib loop, h11), idle | 1 us | 1 us | 1 us | 5 us | 0.028 ms | 0.2 % | 29 MB |
| Starlette on plain uvicorn, load16 | 1 us | 1 us | 2 us | 2 us | 0.026 ms | 9.2 % | 32 MB |
| Baseline, no service, third run | 1 us | 1 us | 2 us | 2 us | 0.020 ms | | |
| Starlette load4, third run | 1 us | 1 us | 3 us | 9 us | 0.091 ms | 4.8 % | 39 MB |
| websockets load16, third run | 2 us | 1 us | 2 us | 6 us | 0.558 ms | 14.1 % | 26 MB |
| Starlette on plain uvicorn, load16, second run | 2 us | 1 us | 5 us | 11 us | 0.028 ms | 18.9 % | 32 MB |

**Reading.** Across three baselines and eighteen loaded runs of the three light stacks (twelve conditions in the first matrix plus six repeats), the median never left 1 to 2 us and the mean stayed within 15 us of the baseline's 1 to 3 us. The P99 rose to 0.351 ms (Starlette load4) and 0.568 ms (websockets load16) in two of those eighteen runs and stayed within 11 us in the other sixteen, including both repeats of each of those two conditions; the maxima of 0.3 to 2.9 ms are scattered across loaded and unloaded runs alike (the first baseline produced 2.455 ms on its own). The two tail excursions therefore did not reproduce and cannot be attributed to the service, but with single-digit repeats they cannot be ruled out either: the honest statement is that a co-located service costs the clock nothing at the median or mean and an occasional sub-millisecond P99 that two repeats each failed to reproduce. The plain-uvicorn variant (stdlib loop, h11) behaved the same as the standard extra on jitter (P99 2 and 11 us under load16) at 29 to 32 MB RSS against 37 to 41 MB. The one condition that changed the whole distribution was forcing both processes onto one core: mean 116 us, P95 0.9 ms, P99 2.0 ms, which the benchmark's own scale still rates "Good" but is a genuine degradation. So co-location is free at the median on any machine with a spare core, costs a sub-millisecond tail in a minority of runs, and on a small server the unit file's `CPUAffinity=` (or leaving Subsequence its own core) is the lever. The service's own cost is CPU rather than jitter, and it varied more between runs than the jitter did: for sixteen clients the three light stacks used 4.7 to 7.9 percent of one core in most runs, but the last two runs of the repeat pass came in at 14.1 percent (websockets) and 18.9 percent (Starlette on plain uvicorn, against 9.2 percent in its first run), with the broadcast latency in those same two runs also the highest recorded (1.1 to 1.3 ms median), which points at other activity on the workstation rather than the stacks; the plain-uvicorn variant is nonetheless expected to cost more CPU than the standard extra, since it runs the stdlib loop and h11 instead of uvloop and httptools. None of that reached the clock.

**Broadcast latency.** One-way latency from the service's broadcast timestamp to the receiving client, measured inside the host under `load16`, was 0.64 to 0.95 ms median and 2.0 to 3.5 ms P99 across Starlette, aiohttp and websockets in the first matrix, and 0.65 to 1.3 ms median and 3.9 to 7.9 ms P99 in the repeats (0.32 to 0.70 ms median and 0.56 to 2.6 ms P99 under `load4`; 2.36 ms median and 8.1 ms P99 with the service pinned to the sequencer's core). The receiver is one asyncio process running all sixteen clients, JSON-decoding every frame, beside a thread fetching 270 KB ten times a second, so its own scheduling delay is inside the number: it is an upper bound on the service's contribution, which `transport-ui` and `latency` can use as such.

**Caveats.** This is the workstation, not the headless server; the sequencer had no MIDI port open and no composition loaded; and the service ran on 127.0.0.1 so no NIC interrupt load was present. The figures are indicative and the run should be repeated on the server before the budgets in `latency` are frozen.

## Running as a systemd service

Ubuntu's systemd defaults already do most of the work; the service needs only to be a foreground process that logs to stdout.

- **Unit type.** `Type=simple` is enough; `Type=notify` lets the manager know the socket is listening before dependents start, and needs only `READY=1` sent to `$NOTIFY_SOCKET` (https://man7.org/linux/man-pages/man5/systemd.service.5.html). The `sd_notify(3)` page carries a standalone Python implementation in its Notes, so no `systemd-python` (LGPL, needs libsystemd headers) or `sdnotify` (last released 2017) dependency is required (https://man7.org/linux/man-pages/man3/sd_notify.3.html, https://pypi.org/pypi/sdnotify/json, https://pypi.org/pypi/systemd-python/json). The whole of it in the house style is one function: open `socket.AF_UNIX, socket.SOCK_DGRAM`, replace a leading `@` in `NOTIFY_SOCKET` with `\0`, `sendto(b"READY=1", path)`. Add `WATCHDOG=1` from the broadcast loop if `WatchdogSec=` is set, so a hung loop is restarted rather than silently dead.
- **Restart policy.** `Restart=on-failure` is the man page's recommended choice for long-running services; `RestartSec=` defaults to 100 ms, and two or three seconds is kinder to a browser that is reconnecting with backoff.
- **Ordering.** No `After=` or `Requires=` on the music apps. The apps are not units today, may live on another host, and `topology` (#1919) requires the service to tolerate any app being absent or restarting; under registration it is the app adapters that reconnect to the service with backoff, and the service shows an expected app as offline until it does.
- **System unit or user unit.** A system unit in `/etc/systemd/system/superintendent.service` with `User=` set runs at boot regardless of logins and can use `ConfigurationDirectory=superintendent` (creates `/etc/superintendent`) and `StateDirectory=superintendent` (creates `/var/lib/superintendent`) (https://man7.org/linux/man-pages/man5/systemd.exec.5.html). A user unit in `~/.config/systemd/user/` needs `loginctl enable-linger` to start at boot without a login (https://man7.org/linux/man-pages/man1/loginctl.1.html) and sees the same user's venv and files as the apps, which today are started by hand from a shell. Either works; the consequence of each is above, and which one follows how the apps themselves end up being run.
- **Hardening that costs nothing for v1.** `NoNewPrivileges=yes`, `PrivateTmp=yes`, `ProtectSystem=strict` with `ReadWritePaths=` for the state directory, `ProtectHome=read-only` unless the config lives in `$HOME`. `security-later` can tighten further.
- **Sketch.**

```
[Unit]
Description=Superintendent touch surface service

[Service]
Type=notify
ExecStart=/opt/superintendent/venv/bin/superintendent --config /etc/superintendent/config.yaml
Restart=on-failure
RestartSec=2
WatchdogSec=30
User=music
ConfigurationDirectory=superintendent
StateDirectory=superintendent
NoNewPrivileges=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
```

`ExecStart=` must be an absolute path or a bare name (systemd.service man page), so the venv path is written in full.

## Configuration file

| Option | For | Against |
| --- | --- | --- |
| **YAML, as the siblings** | Same reader (`pyyaml`, MIT) and same `--config` / `--init` shape as Subsample and Substation; comments in the scaffolded default; page definitions from `control-contract` are nested and read well in YAML | Not in the standard library; a shared definitions YAML already exists, so two YAML files must not be confused |
| TOML | `tomllib` is in the standard library since 3.11 (https://docs.python.org/3/library/tomllib.html); unambiguous types | Read-only in the stdlib, so `--init` and any page save need `tomli-w` or `tomlkit`; the siblings do not use it |
| JSON | Stdlib read and write | No comments, so no self-documenting default |

**Recommendation: YAML**, one file, scaffolded by `superintendent --init`, validated at load into typed objects (pydantic as Substation does, or dataclasses as Subsample does). **Location**, in order: `--config PATH`; `./superintendent.yaml` in the working directory (the siblings' habit for hand runs); `$XDG_CONFIG_HOME/superintendent/config.yaml` (default `~/.config`, https://specifications.freedesktop.org/basedir/latest/); `/etc/superintendent/config.yaml` for a system unit. Saved pages, if pages persist server-side (see `control-contract`), go under `$XDG_STATE_HOME/superintendent` or the unit's `StateDirectory`, never in the config file, so a redeployed config does not lose a page.

**Shape.** The file carries the service's own listen address and the list of apps it expects, and nothing about where the apps are, because under registration the apps come to the service:

```yaml
listen:
  host: 0.0.0.0        # the browser and the apps both reach this address
  port: <chosen by transport-ui and transport-apps; none of 5555, 8080, 8765, 9000 to 9004>
apps:
  - name: subsequence
    enabled: true
  - name: subsample
    enabled: true
  - name: substation
    enabled: false
    # dial: {host: 192.168.1.20, port: NNNN}   # fallback only, for an app that cannot dial out
```

Each app's side is the siblings' existing `supervisor:` block with the direction reversed: `superintendent: {enabled: true, url: ws://127.0.0.1:<port>}` (the transport and scheme are `transport-apps`' choice), defaulting to loopback so the co-located case needs no edit anywhere.

## Discovery of app endpoints

#1919 (`topology`) recommends registration, apps dialling the service, and this document adopts it; the table records why, with the costs of the static list that a service-dials-apps design carries.

| Option | For | Against |
| --- | --- | --- |
| **Registration: each app dials the service at one address and declares itself on connect** (recommended, as #1919) | No new listening socket in any app, so the port map and the exposure recorded for `security-later` do not grow; the one address every app holds is the same address, loopback by default, so the co-located default is zero-configuration; a moved app edits its own config, not the service's; the service learns the app's name and its `control-contract` declaration in the same handshake; the same client code serves the mock apps in development | Every app must know the service address; an app started before the service must retry with backoff (a reconnect loop in each adapter, which `transport-apps` owns); the service needs the expected-apps list above to show "absent" rather than "unknown" |
| Static list in the service config (service dials the apps) | Mirrors the apps' own `enabled: / port:` pattern (`substation/config.py:597-598`, `subsample/config.py:564-568`); deterministic; works across hosts | Each app grows a listening socket: three more ports to clear against the port map, three more exposures for `security-later`, and a bind-failure path in every app that Subsample handles and Substation does not (`subsample/cli.py:1761-1769`, `substation/cli.py:240-252`); a moved app means editing the service and reloading |
| mDNS advertisement by each app, browsed by the service | Zero configuration on one LAN; `zeroconf` 0.151.3 is LGPL-2.1-or-later, requires Python >=3.10, and offers `AsyncZeroconf` and `AsyncServiceBrowser` (https://pypi.org/pypi/zeroconf/0.151.3/json, https://python-zeroconf.readthedocs.io/en/latest/api.html) | An LGPL dependency in every app, shipped as compiled `cp3xx` wheels (an optional Cython extension with a pure-Python fallback; no `py3-none-any` wheel); multicast does not cross subnets or VPNs, so a remote mode falls back to configuration anyway; browsers cannot consume the advertisement (#1919); a fourth optional dependency in Subsequence's engine |

**Recommendation: registration for v1**, with the `dial:` fallback kept in the config shape for an app that cannot dial out, and mDNS a documented later addition that nothing in the shape prevents. Whether the app-facing endpoint is a second `WebSocketRoute` on the same Starlette app and port or a separate listener is `transport-apps`' decision; either fits the unit file and the config above.

## Logging

Python `logging` to stderr with a plain formatter and no timestamp; under systemd both stdout and stderr default to the journal (`DefaultStandardOutput=` defaults to `journal`, local `man systemd.exec` on systemd 255, https://man7.org/linux/man-pages/man5/systemd.exec.5.html), which adds timestamps, unit name and rotation. `journalctl -u superintendent -f` is the log viewer. Neither `systemd-python` (LGPL-2.1+, libsystemd headers) nor `cysystemd` (Apache-2.0, also needs headers, https://pypi.org/pypi/cysystemd/json) is needed; the standard library has no journald handler (https://docs.python.org/3/library/logging.handlers.html) and none is required. A `--log-level` flag and a per-connection debug logger for the wire (one line per message when enabled) cover development. uvicorn's access log is **on by default** when run programmatically (`access_log: bool = True`, `uvicorn/config.py:211` in 0.52.4), so the service must pass `uvicorn.Config(..., access_log=False)` explicitly, or every static fetch and WebSocket handshake lands in the journal; the prototype was quiet only because it passed `log_level="warning"`. Pass `log_config=None` as well so uvicorn does not apply its own `dictConfig` over the service's logging setup.

## Packaging

- `pyproject.toml` in the siblings' shape: `setuptools>=77`, `setuptools-scm>=8.0`, `dynamic = ["version"]`, `license = "AGPL-3.0-or-later"`, `[tool.setuptools_scm]`, versions from `vX.Y.Z` tags with `{next}.dev{distance}+g{hash}` between tags (https://raw.githubusercontent.com/pypa/setuptools-scm/main/docs/usage.md). Substation's `<81` cap is not needed here: none of starlette, uvicorn, websockets, anyio, click, h11, idna or pyyaml imports `pkg_resources` (a grep of the installed venv finds the name only in click's changelog note that it switched to `importlib.metadata` in 8.0), so `setuptools>=77` uncapped, as Subsequence and Subsample have it.
- `requires-python = ">=3.12"`: Ubuntu 24.04's interpreter, Subsample's floor, and above websockets 17's `>=3.11`. The consequence: a 22.04 server's system interpreter (3.10) is excluded and would need a venv on a newer interpreter (uv-managed or deadsnakes); which Ubuntu the server runs is not recorded in the specification.
- Runtime dependencies: `starlette`, `uvicorn`, `websockets`, `pyyaml`, plus whatever `transport-apps` needs to talk to the apps (`python-osc` if OSC). No direct-URL dependency of any kind, or PyPI refuses the upload with "Can't have direct dependency" (https://github.com/pypi/warehouse/issues/9404; Substation's pyproject comment records the same lesson).
- Static UI files as package data following Subsequence's `assets/web/*.html`. Starlette's `StaticFiles(packages=[...])` looks for a directory named `statics` inside a package given as a bare name, and takes a `(package, directory)` tuple to name another (`starlette/staticfiles.py:44`, `71-81` in 1.6.0), so either ship `superintendent = ["py.typed", "statics/**/*"]` and pass `packages=["superintendent"]`, or ship `static/**/*` and pass `packages=[("superintendent", "static")]`. An installed wheel then serves itself and nothing is fetched from the internet at runtime (Supervisor's CDN lesson). Every vendored JavaScript and font file is in scope for `licence-audit`.
- Console script `superintendent = "superintendent.cli:main"` with `--config`, `--init`, `--mock`, `--log-level`.
- Release by pushing a tag with a GitHub Actions workflow and a PyPI pending trusted publisher (short-lived OIDC tokens, no stored secret; a pending publisher does not reserve the name until first publish, https://docs.pypi.org/trusted-publishers/, https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

## Development mode

Supervisor's mocks were standalone websockets servers emitting canned state (`mocks/mock_sequencer.py`), and its adapter tests used a different calling convention from the real caller, which hid two wiring defects (spec §Supervisor). Two changes on that pattern:

- **Run a real Subsequence instead of a sequencer mock.** With no MIDI hardware present, or an `output_device` that matches nothing, `select_output_device` logs the miss and returns `(None, None)` and playback continues (`midi_utils.py:351-354`, `369-377`); the benchmark run above is exactly that. A small example composition under the service's `examples/` with the Superintendent adapter enabled dials the service like any production app, exercises the real adapter code path, and `composition.render()` (`composition.py:5427`) gives offline runs for tests.
- **Mock only what needs hardware.** Subsample needs an audio device and Substation an SDR, so `superintendent --mock` starts in-process fakes that dial the service's app-facing endpoint exactly as the real adapters do, speak the protocol from `transport-apps`, and emit the declarations from `control-contract`: a pad bank that acknowledges hits, a band selector with canned channel states. Because they are clients of the same registration contract the real apps use, the tests exercise the real caller.
- The mock flag also makes a development laptop self-sufficient: browser, service and a real Subsequence on one machine, no server.

## Not covered

- The jitter measurement was made on the workstation with a bare clock loop, not on the headless server with a composition; see Hardware-gated.
- `Type=notify` and `WatchdogSec=` are verified against the protocol documentation, not by running the unit under systemd in this session.
- PyPI name availability for `superintendent` is unchecked.
- The per-client queue fan-out pattern is named as required work, not prototyped; the prototypes used a sequential awaited loop (Starlette, aiohttp) or `broadcast()` (websockets).
- Quart's flat 24.5 CPU-second figure under Hypercorn is unexplained.

## Hardware-gated

- Repeat `benchmarks/clock_jitter.py` beside the running service on the headless server itself, with a composition loaded, a real MIDI port open and the panel's browser connected over the LAN, to replace the workstation figures; note the server's core count, since the same-core case is the only one that degraded the whole distribution.
- Install the unit on the server and confirm `READY=1`, restart on failure, and journald capture.

## Provenance

Files read: `/mnt/dev/Apps/2026-02 Sequencer/pyproject.toml`, `benchmarks/clock_jitter.py:36-82`, `subsequence/web_ui.py:21`, `subsequence/sequencer.py:718-722, 1489-1571`, `subsequence/midi_utils.py:349-378`, `subsequence/composition.py:5410-5427`; `/mnt/dev/Apps/Subsample/pyproject.toml`, `subsample/cli.py:143-178, 1739-1772`, `subsample/config.py:1-6, 560-570`, `subsample/data/config.yaml.default:25-36`; `/mnt/dev/Apps/SDR Scanner/pyproject.toml`, `INSTALL.md:219-223`, `substation/config.py:578-600, 706-724`, `substation/config.yaml.default:24-31`, `substation/cli.py:150-165, 220-255`; `/mnt/dev/Apps/Supervisor/pyproject.toml`, `serve.py`, `supervisor/core.py:56-70, 131-172`, `mocks/mock_sequencer.py`. Installed-package inspection in the scratchpad venvs: `uvicorn/protocols/websockets/{auto,websockets_impl,websockets_sansio_impl}.py`, `uvicorn/loops/auto.py`, `uvicorn/protocols/http/auto.py`, `uvicorn/config.py`, `uvicorn/server.py`, `starlette/staticfiles.py`, `starlette/websockets.py`, `websockets/asyncio/connection.py`. Subroutine items read: #1919. URLs: listed inline. Measurement scripts and raw results: scratchpad `serving/proto/`, `serving/results.txt`, `serving/results-repeats.txt`. Revised on 2026-09-03 after verification: discovery aligned with #1919; the `StaticFiles(packages=)` directory name, the Substation failure path, the zeroconf wheel form, the package counts, the broadcast-latency and CPU ranges, the line citations and the uvicorn access-log default were corrected against the installed code and the sources; the fan-out row, the plain-uvicorn measurement, the repeat runs and the uniform footprint measurement were added.
