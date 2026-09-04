# Research artefacts

Everything here was produced while researching Subroutine specification **#1912** between
2026-09-02 and 2026-09-04, on the development workstation. It is kept because filed documents
cite it as provenance, and because several open hardware-gated tasks need to re-run these
measurements on the real hardware.

**The conclusions are not here — they are in Subroutine.** Twenty-four research documents,
six gap documents and the assembled design #2018 hold what was concluded. This directory holds
only the instruments and the raw output. If the two ever disagree, Subroutine is right and this
is stale.

Copies of filed documents were deliberately removed, so nothing here can drift against the
tracker. So were the virtual environments, Playwright browser downloads, mypy caches, PDFs of
cited papers and the SDR IQ captures — all reproducible, none worth carrying across a CIFS
mount.

## What is worth knowing about

| Path | What it is | The task that wants it |
| --- | --- | --- |
| `multi-touch/gesture-probe.html` | Gesture probe: concurrent contacts, hold, latch, painting, the whole v1 gesture set with a readout | #1997, #1998 — run it on the Pi in Firefox |
| `ui-host/touch-probe.html` | Touch probe: `maxTouchPoints`, concurrent `pointerId`s, `pointercancel`, context menu, pinch, edge swipes | #1997 |
| `ui-rendering/` | Frame-time benches for DOM, canvas and WebGL at 128 and 1024 cells | #1996 — run on the Pi |
| `playhead/bench.html`, `playhead/pw_bench.py` | Playhead extrapolation and highlight rendering | #2006 |
| `subsequence-grid/gap11/grid_jitter_bench.py` | Clock jitter with a real grid pattern rebuilding on the live loop | #2045 |
| `subsequence-grid-gap-1-1/rev2/dispatch_probe.py` | Dispatch-level probe: what `clock_jitter.py` cannot see, and the measurement behind #2041 | #2045 |
| `transport-apps/adapter_bench.py` | The adapter's on-loop cost, every crossing shape | #2008 |
| `transport-apps-gap-1-2/ws_coalesce_bench.py` | Coalescing and read-batching over a real socket, behind #2025 and #2043 | #2008 |
| `transport-ui/` | Browser transport bench: WebSocket against SSE and fetch, stalled-server behaviour | #2002 |
| `control-contract-gap-2-2/` | The page-arrangement prototype behind #2040: snap-drag, the Starlette page routes, and their tests | — |
| `serving/` | Starlette, aiohttp and Quart under load, with the CPU figures behind #1929 | #2007 |
| `subsample-substation/` | Subsample MIDI timing and Substation band-restart timing | #2012, #2014 |
| `iana-ports.csv` | The registry evidence behind the port recommendation | #2020 |

## Running any of it

These were written against the development workstation's paths and its throwaway virtual
environments, neither of which came across. Expect to recreate a venv and to fix a path before
anything runs. Each measurement script keeps its own results beside it, usually in a
`results/` directory, so what the numbers were is legible without re-running.
