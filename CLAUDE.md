# Superintendent

<!--
  This file holds only what is true of THIS project. General Python conventions
  (coding style, dev loop, code-review methodology) come from the si-python
  plugin and must not be duplicated here.
-->

## Project overview

- **What this is:** a touchscreen control surface for Simon's three music apps. A Python service runs beside those apps, serves one HTML page to a touchscreen's browser, and holds a single WebSocket to it. Each music app dials the service over a WebSocket of its own and declares what it can be controlled by; a page binds widgets to those declared names. The first use-case is a step grid that drives a drum pattern in Subsequence, which plays hardware over MIDI.
- **User-facing interface:** a browser page on a touch panel, plus a YAML config file for the service. There is no CLI beyond starting the service.
- **Audience:** Simon today; other musicians after an open-source release. Write user-facing text for someone who owns a different rig and has never seen this one — that is the audience the project is aimed at, and the reason for the rule below.
- **Architecture:** the design is **Subroutine #2018** (project `superintendent`). Read it before changing anything structural; it carries a short list, a trade-off table and a recommendation for each of the seven decisions, and the sixteen research points behind it are #1914 to #1941.

**Nothing in this package may know about a particular studio.** An app declares its own controls; a page names them. Rig-specific values — MIDI channels, drum note maps, device names — live in the user's composition file or in a page definition, never here. This mirrors Subsequence's own rule, Subroutine #1465.

## Recommend, never mandate

**Superintendent is headed for an open-source release, and the people who arrive already own an OS, a server, a monitor and a browser.** It may recommend those. It may not require them. The full rule and its consequences are Subroutine **#2049**; the test is one question:

> Would the code fail, or behave wrongly, without it?

**Yes** — it is a dependency, so declare it plainly and narrowly (the browser must deliver Pointer Events and a WebSocket; the service needs asyncio). **No** — it is a recommendation, so it belongs in the README with its reason attached, never in code, never in a hard default that fails elsewhere, never in an error message calling a setup unsupported.

The development rig below is fixed and known, and that is exactly why this needs stating: **it is where the work is done, not what the product is for.** Every measurement in the research was taken on it and none of it is a requirement.

This is not a licence to build abstraction nobody asked for. The proof-of-concept runs on one rig and grows no plugin layer, driver model or hardware settings screen. The rule bites when something is about to be *written down as required* — not before. Two known offenders are already filed: the 1920-by-1080 page lattice (#2050, worth fixing before a page format exists) and the README-and-config pass (#2051).

## Environment

- **Interpreter:** a venv named `superintendent`, held outside this mount because the mount is shared. On `nuc14`, where the music apps run, it is `/home/si/venvs/superintendent`; on the workstation it is `/mnt/hom/si/venvs/superintendent`. It carries the package editable, the dev extras, and `subsequence` editable from `/mnt/dev/Apps/2026-02 Sequencer` — the last is a rig arrangement so one interpreter can run the service, the adapter and the composition together, **not** a dependency of this package, which must never declare one on a particular app. If no such venv exists on this machine, stop and ask — do not create one silently.
- **Package:** `superintendent` (used for `mypy superintendent`). Tests live in `tests/`.
- **Python floor:** 3.11.
- **This directory is a CIFS mount** shared between machines. Do not put a venv, build output or anything with absolute paths baked in here. It is not a git repository yet; `git init` is Simon's call. CIFS cannot hold symlinks, so anything that wants one belongs elsewhere.
- **Subroutine** is where every decision and open question lives. `.subroutine` at the root names connection `hpz2g4`, workspace `projects`, project `superintendent`. That connection must exist on this machine too — if the `subroutine_*` tools are missing or every call fails, read the `subroutine` skill before diagnosing, and pass on what `claude mcp list` says rather than guessing.

## The neighbours

All three are AGPL-3.0, all share one maintainer, and a limitation in one is a change to make rather than something to engineer around (#611).

| App | Path | Package |
| --- | --- | --- |
| Subsequence | `/mnt/dev/Apps/2026-02 Sequencer/` | `subsequence` — generative MIDI sequencer |
| Subsample | `/mnt/dev/Apps/Subsample/` | `subsample` — sampler |
| Substation | `/mnt/dev/Apps/SDR Scanner/` | `substation` — SDR scanner |
| Supervisor | `/mnt/dev/Apps/Supervisor/` | superseded prior art — read, do not extend (#1923) |

Subsequence's `web_ui.py` is legacy and **must be left alone**. Superintendent is entirely separate from it.

## The proof-of-concept being built now

One page, one instrument, one MIDI channel. A Vermona DRM1 MkIV driven by a 16-step pattern in Subsequence. Simon settled four things on 2026-09-04; they are recorded as Subroutine **#2046**.

1. **No changes to the Subsequence package.** The grid is a plain dict in `composition.data`, read by the pattern builder and written by the adapter. The `StepGrid` helper that #1914 recommends is deliberately not built yet — a plain dict migrates to it later, and the loop should be proven first. The composition file lives in `compositions/`.
2. **A tap crosses per message, and the cell shows a ring until it is confirmed.** The adapter wakes the composition loop for each `set`, costing about 1 ms at p99 (#2033, #2025, #2043). A cell's face is always the server's value; an unconfirmed tap draws a ring that clears on `ack`. Nothing on a face is ever speculative. This answers #2021 and #1968 together, as #2018 requires.
3. **The grid is 16 by 10, not 16 by 8.** The DRM1 has eight parts but ten notes, because each hi-hat has a separate closed and open note. Every note gets its own row: kick 36, drum_1 45, drum_2 50, multi 56, snare 38, clap 39, hihat_1_closed 44, hihat_1_open 46, hihat_2_closed 49, hihat_2_open 51. The map is `subsequence.constants.instruments.vermona_drm1_drums.VERMONA_DRM1_DRUM_MAP`.
4. **A cell is on or off, with no velocity.** One fixed velocity per hit. The gesture set is a single tap. The hold-for-velocity gesture (#1927), the accent question (#1969), the lock (#1966) and painting (#1971) all stay out.

Taken from #2018's recommendations without further asking, because each is the recommended option and none is expensive to revisit: `reschedule_lookahead=1/24` on the grid pattern (#2041 gives two independent reasons); Starlette on plain uvicorn; vendored Preact plus htm with no build step; the grid drawn as DOM cells; the tap acting on press rather than on release; the apps dialling the service rather than the reverse; listen port 8090 (#2020, still Simon's to confirm).

## The panel host, which exists

Reported by Simon on 2026-09-04 and written up as **#2048**. This is #1921's recommended option A in every respect but the browser.

| | |
| --- | --- |
| Host | Raspberry Pi 5, 4 GB |
| Panel | iiyama ProLite T2252MSC-B2 |
| OS | Raspberry Pi OS 64-bit, latest — presumed Trixie, confirm with `cat /etc/os-release` |
| Browser | **Firefox**, by Simon's preference |
| Network | Same LAN as the machine running the music apps |
| Multi-touch | Configured at the OS and seen working in a browser |
| Position | Tested at eye height and flat like a table; the Pi is mounted on the stand so the whole assembly moves as one |
| Light | A room with no ceiling lights, so reflections do not arise despite the -B2's glossy oleophobic glass (#1959) |

The Pi runs a browser and nothing else — no Python, no music app, no part of this service. **This is the development target, not a requirement** — see the rule above.

Simon expects to keep moving the panel around the room and testing angles. A surface that is sometimes read like a monitor and sometimes flat like a table is worth remembering when the page is laid out, because the two are read at very different angles.

**Firefox, not Chromium, and the measurement agrees with the preference.** #1941 timed Chromium's touch path delivering `pointerdown` 0.5 to 18 ms after the event and input-to-commit at 17 to 34 ms, against 0 to 20 ms for Firefox on both. So Firefox is the better-measured choice for a touch surface. The consequence is that **#1921's kiosk mechanics do not transfer**: they are `chromium --kiosk --ozone-platform=wayland` with a relaunch loop that resets Chromium's `Preferences` crash flags. Firefox needs `firefox --kiosk`, the same loop, and its own way of suppressing the session-restore prompt after a hard kill — through the profile, and unverified. Wayland should mean `MOZ_USE_XINPUT2` is unnecessary (#1918 needed it only on X11); worth checking rather than assuming. The page-side suppression set is browser-independent.

That multi-touch works already disposes in practice of Pi OS's one known trap, labwc shipping touch mouse emulation on, and of the unverified controller identity in #1917 — the panel binds and reports contacts. The rest of the probe (#1997) is still worth running on Firefox: ten concurrent `pointerId`s, no `pointercancel` under `touch-action: none`, no context menu on long press, no pinch zoom, no edge-swipe system UI.

## research/

The probes, measurement runners, prototypes and raw results from the research, carried over from
the workstation they were made on because filed documents cite them as provenance and because
most of the hardware-gated tasks are *re-run this, here* — `research/README.md` maps each one to
the task that wants it. Two matter first: `research/multi-touch/gesture-probe.html` and
`research/ui-host/touch-probe.html`, which are what #1997 and #1998 ask you to open on the Pi.

**The conclusions are not in there — they are in Subroutine.** Copies of filed documents were
removed on purpose so nothing can drift against the tracker. Venvs, browser downloads, caches,
cited PDFs and SDR captures were dropped as reproducible.

## What is not settled

**51 questions are open as `needs_input` spikes** in Subroutine project `superintendent`. Six are answered: #1958, #1960, #1961 and #1990 by the rig, and #2021 with #1968 by the proof-of-concept's crossing decision. The rest run #1942 to #1991, #2019, #2020, #2030, #2031, #2034 to #2039, #2042 and #2044 and **27 hardware-gated checks** are open tasks (#1992 to #2017, #2045). The proof-of-concept deliberately sidesteps most of them. Do not answer one by inference from the code — ask Simon, or leave it open.

Two the proof-of-concept touches but does not settle: **#1942**, where a `StepGrid` helper would live if one is built, and **#2044**, whether a v1 cell carries velocity.

## Conventions specific to this project

- **Extra code-review dimensions:** *clock safety* — anything that runs on, or wakes, Subsequence's composition loop is on the path that generates MIDI timing, and its cost belongs in the review. The measured figures are in #1926, #2025, #2033 and #2043. *Touch reachability* — a control that cannot be worked with one finger on glass, with no keyboard attached, is a defect.
