Does the coalesced wake-up the crossing rule depends on cost one wake-up per burst, as the first-use-case design's B column claims, and what does the recommended rule actually cost at the rates a hand produces?

Coalescing was measured on the same harness that produced every other crossing figure, and it does not do what the B column says. At every steady rate a hand or a browser produces — 5 Hz, 25 Hz, 50 Hz, and on up through 200 Hz and 500 Hz — the drain is already finished before the next frame arrives, so **every message gets its own wake-up and coalescing never fires**: 1.000 messages per wake-up, a maximum batch of one, in every block that ran the row (25 Hz and 50 Hz in all four) and again on a machine at load 3 to 6. It fires only on frames arriving back to back, and then at about eight to one rather than one per burst: 128 back-to-back `set` frames cost about sixteen wake-ups and 1024 cost about 162. The recommended rule's cost is therefore exactly the per-message cost, and coalescing neither adds to it nor takes anything off it. That leaves the recommendation intact, because the per-message cost at a held paint gesture is 26 to 48 late pulses in 1536 at a p99 of 1.09 to 1.30 ms, and because the crossing itself — never measured until now — takes 0.13 to 0.20 ms at the median under the recommended rule against 243 to 251 ms under the drain rule.

## What was measured, and how

The harness is `benchmarks/clock_jitter.py`'s, unchanged: the real `subsequence.sequencer.Sequencer` with `_jitter_log` set, 16 bars at 120 BPM (1536 pulses at 20.833 ms), spin-wait on, no MIDI port (`benchmarks/clock_jitter.py:36-82`). One adapter shape per run inside the sequencer process; a separate sender process is the stand-in service, and each inbound frame becomes one dict write on the clock loop, standing in for the helper's `composition.data` write. This is the harness of `scratchpad/transport-apps/revise/ws_drain_bench.py` and its conditions are that file's: asyncio's default epoll selector, the same venv, the same machine. The coalescing shape was added in a copy of that file under this point's own directory rather than in the file itself, which is left untouched because the adapter finding's provenance cites it; `adapter_bench.py` is reused unchanged for the link base, the apply step and the statistics.

Three shapes are compared, all a `websockets` client link on a daemon thread with its own loop, which is what the adapter design recommends:

- **A, drain at the sequencer's own hooks.** Frames queued on the link thread, applied in the `beat` listener. No wake-up at all.
- **B without its coalescing clause.** `loop.call_soon_threadsafe(apply, ...)` per frame. This is the shape the adapter finding measured, reproduced here as the control.
- **B as recommended.** Frames queued on the link thread; a drain is scheduled onto the clock loop with `call_soon_threadsafe` only when one is not already pending. The pending flag is cleared at the *start* of the drain rather than the end, so a frame queued while a drain is running schedules a fresh one — which may find the queue empty, and that empty drain is counted — rather than being left unscheduled.

Two traffic shapes: a steady stream at a named rate, and `N` frames written back to back every `P` seconds, which is what a page-load seed or an algorithm's bulk write looks like on the wire, because the design's envelope carries one cell per `set` frame.

Two things are counted that no earlier run counted. **Wake-ups**: how many times the adapter called `call_soon_threadsafe`, which is one self-pipe byte each (`/usr/lib/python3.12/asyncio/base_events.py:838-847` calls `_write_to_self`, `/usr/lib/python3.12/asyncio/selector_events.py:141-153` sends the byte), so messages per wake-up says directly whether coalescing fired. **Crossing latency**: `perf_counter` taken as the frame leaves the link thread and again as the write lands on the loop. The instrumented rows therefore carry one extra `perf_counter()` and one list append per applied message on the clock loop; that is well under a microsecond and the shapes carry it equally. Every row applied every frame it received and dropped none; three drain-at-`beat` rows show one frame fewer applied than received, which is the frame that arrived after the run's last `beat` and was still queued at teardown.

Machine: the development workstation (Intel i7-9700K, 8 cores, Ubuntu 6.8.0-138, Python 3.12.3, `websockets` 17.1), single runs, indicative only. **The workstation is shared and a first attempt was discarded**: it ran while another job held all eight cores, and under that load even the untouched baseline showed a 0.71 ms maximum and the no-wake-up drain shape showed 234 pulses over 1 ms. The runner now waits for a one-minute load average at or below 1.20 before every row and stamps the load at the row's start and end; every row below was taken between 0.27 and 1.03. The four blocks are A (the full set), B (a repeat of A's key rows), and C and D (the engine-side levers, twice).

## Coalescing never fires at a rate a hand produces

A held paint-along-a-row gesture (#1971) crossing a sixteen-column grid in half a second to a second is 16 to 32 `set` frames a second; the panel's own HID report rate is 100 to 250 Hz where it meets the Windows guideline, and the browser coalesces pointer moves to the frame (#1941, #1917). 25 Hz is the middle of that gesture and is the row the crossing decision turns on.

| Shape | Rate | Messages | Wake-ups | Messages per wake-up | Largest batch |
| --- | --- | --- | --- | --- | --- |
| B without coalescing | 5 Hz | 170, 170 | 170, 170 | 1.000, 1.000 | n/a |
| B as recommended | 5 Hz | 170, 170 | 170, 170 | 1.000, 1.000 | 1 |
| B without coalescing | 25 Hz | 839, 839 | 839, 839 | 1.000, 1.000 | n/a |
| B as recommended | 25 Hz | 839, 839 | 839, 839 | 1.000, 1.000 | 1 |
| B without coalescing | 50 Hz | 1659, 1655 | 1659, 1655 | 1.000, 1.000 | n/a |
| B as recommended | 50 Hz | 1658, 1655 | 1658, 1655 | 1.001, 1.000 | 2 |
| B without coalescing | 200 Hz | 6230 | 6230 | 1.000 | n/a |
| B as recommended | 200 Hz | 6203 | 6203 | 1.000 | 1 |
| B without coalescing | 500 Hz | 14128 | 14128 | 1.000 | n/a |
| B as recommended | 500 Hz | 14087 | 14080 | 1.000 | 2 |

Two figures per cell are the two blocks. The reason is the crossing latency measured below: the clock loop takes about 0.2 ms to service a wake-up and empty the queue, and the next frame in a steady stream is 2 ms away at 500 Hz and 200 ms away at 5 Hz. There is no window in which a second frame can join the first. The same counts were taken again on a machine carrying another job at load 3.2 to 6.1, four bars per row: 5 Hz 50 messages and 50 wake-ups, 25 Hz 246 and 246, 50 Hz 488 and 488 — 1.000 in every case. Contention does not create coalescing either.

This is not a property of this particular implementation. Coalescing can only merge frames that arrive closer together than the loop takes to drain, and any window wide enough to merge frames 40 ms apart is itself 40 ms of added latency, which is the thing the crossing rule exists to avoid.

## What a genuine burst costs, and what coalescing does to it

| Traffic | Shape | Messages | Wake-ups | Messages per wake-up | Largest batch | P99 | Max | Pulses over 1 ms of 1536 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 16 frames back to back every 1 s | B without coalescing | 544 | 544 | 1.000 | n/a | 0.162 ms | 1.195 ms | 1 |
| 16 frames back to back every 1 s | B as recommended | 544 | 107 | 5.084 | 16 | 0.056 ms | 1.198 ms | 2 |
| 128 frames back to back every 2 s | B without coalescing | 2176, 2176 | 2176, 2176 | 1.000, 1.000 | n/a | 0.087, 0.081 ms | 1.187, 1.176 ms | 1, 1 |
| 128 frames back to back every 2 s | B as recommended | 2176, 2176 | 266, 260 | 8.180, 8.369 | 42, 104 | 0.133, 0.100 ms | 1.124, 0.709 ms | 1, 0 |
| 128 frames back to back every 2 s | A, drained at `beat` | 2176 | 0 | n/a | 128 | 0.133 ms | 0.747 ms | 0 |
| 1024 frames back to back every 4 s | B without coalescing | 8192 | 8192 | 1.000 | n/a | 0.034 ms | 0.284 ms | 0 |
| 1024 frames back to back every 4 s | B as recommended | 8192 | 1299 | 6.306 | 76 | 0.026 ms | 0.563 ms | 0 |
| 1024 frames back to back every 4 s | A, drained at `beat` | 8192 | 0 | n/a | 1024 | 0.003 ms | 0.401 ms | 0 |

Coalescing does fire here, and does not do what the column claims. A 128-frame burst costs about sixteen wake-ups, not one; a 1024-frame burst costs about 162. The link thread's loop and the clock loop run concurrently, so by the time the clock loop has been woken and has emptied the queue the link thread has usually taken only a handful of further frames off the socket: the mean batch is 5.1, 8.2, 8.4 and 6.3 frames across the four coalesced burst runs. The distribution has a long tail — one drain in a 128-frame run caught 104 frames and one in the 1024-frame run caught 76 — and a 16-frame burst, the size of one paint stroke arriving in a single flush, was occasionally caught whole. But the typical wake-up carries eight frames, not the burst.

The claim's *conclusion* nevertheless holds, for a reason the column does not give: **a bulk burst is the cheapest traffic there is, coalesced or not**. 8192 messages delivered as eight bursts of 1024 cost zero pulses over 1 ms and a p99 of 0.034 ms under plain per-message marshalling, against 26 to 48 late pulses and a p99 above 1 ms for a tenth of that traffic spread evenly at 25 Hz. A burst lands inside one or two pulses and can only spoil those; a steady stream touches a different pulse each time.

## The clock cost peaks near one wake-up per pulse and falls away above it

| Shape | Rate | Messages per pulse | Mean | Benchmark's own rating | P99 | Max | Pulses over 1 ms of 1536 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline, nothing in the process | none | 0 | 0.002-0.003 ms | Excellent | 0.003-0.023 ms | 0.014-0.228 ms | 0 |
| B without coalescing | 5 Hz | 0.11 | 0.016, 0.022 ms | Excellent | 0.546, 0.714 ms | 1.237, 1.271 ms | 4, 5 |
| B as recommended | 5 Hz | 0.11 | 0.020, 0.021 ms | Excellent | 0.726, 0.606 ms | 1.354, 1.321 ms | 7, 6 |
| B without coalescing | 25 Hz | 0.55 | 0.082, 0.102 ms | Excellent, Very good | 1.086, 1.297 ms | 1.379, 1.693 ms | 36, 48 |
| B as recommended | 25 Hz | 0.55 | 0.081, 0.098 ms | Excellent | 1.136, 1.213 ms | 1.527, 1.557 ms | 26, 35 |
| B without coalescing | 50 Hz | 1.08 | 0.138, 0.162 ms | Very good | 1.256, 1.424 ms | 1.512, 1.603 ms | 57, 67 |
| B as recommended | 50 Hz | 1.08 | 0.159, 0.147 ms | Very good | 1.219, 1.276 ms | 1.417, 1.568 ms | 63, 67 |
| B without coalescing | 200 Hz | 4.06 | 0.028 ms | Excellent | 0.310 ms | 0.573 ms | 0 |
| B as recommended | 200 Hz | 4.04 | 0.038 ms | Excellent | 0.475 ms | 0.670 ms | 0 |
| B without coalescing | 500 Hz | 9.20 | 0.036 ms | Excellent | 0.482 ms | 0.666 ms | 0 |
| B as recommended | 500 Hz | 9.17 | 0.043 ms | Excellent | 0.498 ms | 0.663 ms | 0 |
| A, drained at `beat` | 5 / 25 / 50 Hz | 0.11 / 0.55 / 1.08 | 0.002-0.005 ms | Excellent | 0.010-0.136 ms | 0.171-0.515 ms | 0 |

Two figures are the two blocks. Three things follow.

**Coalescing does not change the jitter at any steady rate**, which it cannot, since at those rates it changes no wake-up count. Where the two B rows differ — 26 and 35 late pulses coalesced against 36 and 48 not, at 25 Hz — the difference is inside the block-to-block spread of the same shape.

**The cost is not monotonic in message rate, and 50 Hz is close to its peak.** Four times the traffic of 50 Hz costs nothing at all. The reading, from the data and the runtime source rather than from instrumentation of the selector, is this. `EpollSelector.select` rounds a positive timeout up to a whole millisecond and leaves a zero timeout alone (`/usr/lib/python3.12/selectors.py:451-459`), and `BaseEventLoop._run_once` passes a timeout of 0 whenever a callback is already ready and the remaining time to the next timer otherwise (`/usr/lib/python3.12/asyncio/base_events.py:1940-1948`). The clock sleeps to within its 1 ms spin margin and then busy-waits (`sequencer.py:1555-1567`, margin at `sequencer.py:465`). At 25 to 50 Hz the loop is typically interrupted exactly once inside a long rounded wait, re-enters with a fresh positive timeout, and the rounding eats the spin margin — the mechanism the adapter finding identified. At 200 Hz and above the ready queue is rarely empty when the loop comes round, the timeout is 0, epoll never rounds, and the clock keeps its deadline. At 5 Hz most pulses see no wake-up at all. So the cost peaks where wake-ups are frequent enough to catch most pulse sleeps but too sparse to keep the loop polling — at or near one per pulse, which at 120 BPM is 48 Hz.

**The benchmark's own rating is applied to the mean, not to a percentile** (`benchmarks/clock_jitter.py:99` computes `mean_ms`; `:131-141` sets the bands from it). Every crossing row measured here has a mean between 0.002 and 0.162 ms, which that scale calls "Excellent" (under 0.1 ms) or "Very good" (under 0.5 ms). The worst single pulse in any run was 1.69 ms, eight percent of a 20.8 ms pulse, against a clock whose own mean jitter is about 3 µs.

## The crossing itself, measured for the first time

From the frame leaving the link thread to the write landing on the clock loop, in milliseconds:

| Shape | Rate | Median | P99 | Max | Applications timed |
| --- | --- | --- | --- | --- | --- |
| B without coalescing | 5 Hz | 0.141, 0.083 | 0.185, 0.195 | 0.342, 0.322 | 170, 170 |
| B as recommended | 5 Hz | 0.192, 0.192 | 0.235, 0.280 | 0.264, 0.354 | 170, 170 |
| B without coalescing | 25 Hz | 0.139, 0.139 | 0.181, 0.181 | 0.358, 2.303 | 839, 839 |
| B as recommended | 25 Hz | 0.186, 0.195 | 0.237, 0.237 | 0.442, 22.95 | 839, 839 |
| B without coalescing | 50 Hz | 0.135, 0.143 | 0.177, 0.184 | 0.316, 0.305 | 1659, 1655 |
| B as recommended | 50 Hz | 0.188, 0.193 | 0.235, 0.235 | 8.061, 0.335 | 1658, 1655 |
| A, drained at `beat` | 5 Hz | 243.2 | 491.7 | 497.3 | 170 |
| A, drained at `beat` | 25 Hz | 249.1, 249.3 | 494.7, 493.6 | 499.9, 498.8 | 839, 838 |
| A, drained at `beat` | 50 Hz | 250.9 | 495.0 | 499.8 | 1659 |

The drain rule's cost was arithmetic in the design and is now a measurement: at 120 BPM the median wait is half a beat and the maximum is a beat, 497 to 500 ms, to three digits. Under the recommended rule the same wait is a fifth of a millisecond at the median and a quarter at p99, coalescing costing about 0.05 ms more at the median for the queue hop. The maximum is not bounded — one 25 Hz run had a single crossing at 23 ms — but that is still twenty times inside a beat.

The design's B cell reads "a few milliseconds: the browser hop ... plus about 1 ms of wire, then a loopback hop to the adapter and one loop wake-up". The loop wake-up term in that sentence is a fifth of a millisecond, not a millisecond: the few milliseconds are all network.

## Both engine-side levers remove the tail, and neither was measured before in a clean block

The C column names the selector or the spin margin as the lever if the workstation figures prove optimistic. Both were run here in the same block as the shapes they modify, each twice. Neither is a code change in the prototype: the spin margin is the instance's own `_spin_threshold` (`sequencer.py:465`), and the selector is an event-loop policy.

| Lever | Shape | Rate | P99 | Max | Pulses over 1 ms of 1536 |
| --- | --- | --- | --- | --- | --- |
| None (default epoll, 1 ms margin) | B without coalescing | 25 Hz | 1.086, 1.297 ms | 1.379, 1.693 ms | 36, 48 |
| Spin margin 2 ms, epoll | baseline | none | 0.003, 0.003 ms | 0.010, 0.013 ms | 0, 0 |
| Spin margin 2 ms, epoll | B without coalescing | 25 Hz | 0.249, 0.142 ms | 0.558, 0.536 ms | 0, 0 |
| Spin margin 2 ms, epoll | B as recommended | 25 Hz | 0.233, 0.143 ms | 0.541, 0.563 ms | 0, 0 |
| Spin margin 2 ms, epoll | B without coalescing | 50 Hz | 0.336, 0.289 ms | 0.530, 0.563 ms | 0, 0 |
| `SelectSelector`, 1 ms margin | baseline | none | 0.030, 0.003 ms | 1.421, 0.013 ms | 1, 0 |
| `SelectSelector`, 1 ms margin | B without coalescing | 25 Hz | 0.002, 0.022 ms | 0.014, 0.029 ms | 0, 0 |
| `SelectSelector`, 1 ms margin | B as recommended | 25 Hz | 0.002, 0.003 ms | 0.054, 0.029 ms | 0, 0 |
| `SelectSelector`, 1 ms margin | B without coalescing | 50 Hz | 0.006, 0.003 ms | 0.013, 0.023 ms | 0, 0 |

The selector lever is the stronger of the two: it puts the per-message crossing back on the baseline, confirming the adapter finding's select rows in a block where the load did not drift. Widening the spin margin does not reach the baseline but does remove every late pulse, at the price of doubling the clock's busy-wait from about 5 to about 10 percent of one core per pulse — which is a real cost on a headless server that also runs the UI service. `select` has its own price: it is O(n) in watched descriptors and "can't accept a FD > FD_SETSIZE (usually around 1024)" (`/usr/lib/python3.12/selectors.py:613`), which is ample for a composition holding a handful of sockets and would not be for a server holding many, so it belongs on the app's loop and not on the service's.

## The crossing short list's B column, corrected

**The recommendation stands: no corrected cell changes which column wins.** What changes is that three cells claimed a mechanism that does not exist, one attributed the benchmark's rating scale to the wrong statistic, and two figures that were arithmetic or inference are now measurements. Cell by cell:

| Cell | As filed in the first-use-case design | Corrected |
| --- | --- | --- |
| B, "Coalescing" | "schedule the drain only when one is not already pending, so a burst costs one wake-up rather than one per message — inferred from the finding's own conclusion that the cost is per wake-up and not per message, and **not itself measured**" | Measured. It never fires at a rate a hand or a browser produces: 1.000 messages per wake-up at 5, 25, 50, 200 and 500 Hz in every block that ran the row, and again on a machine at load 3 to 6. It fires only on frames arriving back to back and then at about eight to one, not one per burst: 128 frames cost about sixteen wake-ups and 1024 about 162. Its effect on the clock at every rate is inside the block-to-block spread of the same shape. Keep the clause — it is two fields and a lock, it bounds nothing today but bounds a future batched frame — but claim nothing for it. |
| B, "Measured clock cost" | "at a realistic 5 Hz tap rate, p99 0.36 to 0.49 ms with a 1.1 ms maximum and 2 to 4 pulses over 1 ms in 1536; at a sustained 50 Hz, p99 1.10 ms and 38 to 57 pulses over 1 ms" | Add the paint rate the rule exists for. At 5 Hz, p99 0.55 to 0.73 ms, maximum 1.24 to 1.35 ms, 4 to 7 pulses over 1 ms in 1536. **At 25 Hz, a held paint gesture: p99 1.09 to 1.30 ms, maximum 1.38 to 1.69 ms, 26 to 48 pulses over 1 ms in 1536.** At 50 Hz, p99 1.22 to 1.42 ms, 57 to 67 late. Above that the cost falls away: at 200 and 500 Hz, no pulse over 1 ms at all. A page-load seed or an algorithm's bulk write is cheaper still: 1024 `set` frames back to back cost zero late pulses and a p99 of 0.034 ms. |
| B, "Tap to `ack`, and therefore to the face" | "a few milliseconds: the browser hop measured 0.8 to 1 ms loopback plus about 1 ms of wire, then a loopback hop to the adapter and one loop wake-up" | Unchanged in its total, but the loop wake-up is now measured and is not a millisecond: 0.13 to 0.20 ms median and 0.18 to 0.28 ms at p99 from the link thread to the write on the loop, coalesced or not, with an unbounded tail seen once at 23 ms. The few milliseconds are network. |
| B, "Musical effect of the cost" | "a late pulse is late by about 1.1 ms ... the jitter benchmark's own scale still rates a 2.0 ms P99 as 'Good'" | The scale is applied to the mean, not to a percentile (`benchmarks/clock_jitter.py:99`, `131-141`). Every row here has a mean of 0.002 to 0.162 ms, which that scale calls "Excellent" or "Very good". The worst single pulse in any run was 1.69 ms. |
| A, "Tap to `ack`" | "up to one beat: 500 ms at 120 BPM ... roughly half that on average" | Confirmed by measurement rather than arithmetic: median 243 to 251 ms, p99 492 to 495 ms, maximum 497 to 500 ms at 120 BPM. |
| C, "Measured clock cost" | "p99 0.001 to 0.018 ms for every per-message shape at 50 Hz" | Confirmed in a block whose load did not drift: `SelectSelector` gives p99 0.002 to 0.022 ms at 25 Hz and 0.003 to 0.006 ms at 50 Hz with no pulse over 1 ms. The second lever is measured for the first time: widening the spin margin from 1 ms to 2 ms also removes every late pulse (p99 0.14 to 0.34 ms) at the price of doubling the clock's busy-wait to about a tenth of a core. |
| The "Not covered" bullet | "**The coalesced wake-up.** ... It was not itself measured by any point and is named above as an addition to #2008." | Delete. It is measured on the workstation and did not need the headless server; what remains for #2008 is what that item already says, the same figures re-taken on the server with the transport actually chosen. |

## Three consequences beyond the column

**The fallback to A for bulk is not needed on clock-cost grounds.** The recommendation is "B, with A retained as the automatic fallback for anything that is not a human's tap — a page-load seed, an algorithm's bulk write, a held paint gesture beyond a rate ceiling". Measured, bulk is the cheapest traffic of all: a 1024-frame seed handed straight to B costs zero late pulses, and a 128-frame seed costs one. The dearest traffic is the human's tap, which is the one case the fallback exempts. The fallback may still be wanted for a reason this measurement does not touch — a bulk write does not need a per-cell `ack` and A gives the drain a natural batch — but it should not be justified by the clock.

**The rate ceiling in that rule has nowhere to sit.** A ceiling that caught a held paint gesture would have to be below 20 Hz, which is below the gesture itself, so it would either never fire or hand the whole gesture to A and put the face a beat behind the finger for the length of the stroke. Above the gesture, at 200 Hz and beyond, there is nothing left to catch. If a ceiling is kept it should be a safety valve against a runaway client, set well above any gesture, and not a latency policy.

**One wake-up per burst is available, but from the envelope, not from the adapter.** The design's client-to-server vocabulary carries one cell per `set` frame, so a seed of a 16-by-8 grid is 128 frames and of a 64-by-16 grid 1024. A batched `set` — one frame carrying a list of cells — would give exactly the one wake-up the B column claims, and would also cut the JSON parsing on the link thread. It is not needed for the clock, which does not care, but it is the only mechanism that delivers what the column says, and the coalescing clause is what would keep the adapter correct if it were added later.

## Not covered

- **Where between 50 Hz and 200 Hz the cost peaks and how sharply it falls.** Rows were taken at 5, 25, 50, 200 and 500 Hz; the peak is at or near one wake-up per pulse (48 Hz at 120 BPM) and is gone by 200 Hz, but no row sits between. Nothing in the design depends on the shape of that curve, since every rate a panel produces is at or below 50 Hz.
- **The selector reading is inferred from the runtime source and the data, not instrumented.** No count was taken of how often `_run_once` chose a zero timeout. The claim that the tail vanishes above 200 Hz is a measurement; the explanation for why is a reading.
- **Tempi other than 120 BPM.** The pulse is 20.833 ms here. At 60 BPM a pulse is 41.7 ms and the peak rate would be about 24 Hz, which is inside the paint gesture; at 180 BPM it is 13.9 ms and 72 Hz. The shape of the argument does not change but the numbers would, and only 120 BPM was run.
- **A real `StepGrid.apply()` in place of the dict write.** The apply step here is one dict write, as in every earlier crossing row. #2008 and #2009 already carry that.

## Hardware-gated

- Nothing in this finding needs the iiyama panel or a graphical host; it is entirely server-side and was run to completion.
- The figures are the development workstation's and remain indicative. Re-taking them on the headless server is #2008, which is unchanged by this work except that the coalescing question is no longer part of it. The epoll rounding is a CPython property and will be present there; the rate at which the cost peaks scales with the pulse interval and so with tempo, not with the machine, but the machine sets how long a wake-up takes to service and therefore whether coalescing ever fires there. On a slower server the drain takes longer, so coalescing would begin to fire at a lower rate than it does here — the first thing to check on the server is the messages-per-wake-up column at 25 Hz, which costs nothing to collect and settles it.

## Provenance

Files read in the working tree: `subsequence/sequencer.py` (315-360, 400-435, 455-475, 1420-1435, 1520-1580, 1798-1835), `subsequence/pattern.py` (99-112), `subsequence/constants/__init__.py` (22), `benchmarks/clock_jitter.py` (30-145). Runtime source read: `/usr/lib/python3.12/selectors.py` (405-466, 613), `/usr/lib/python3.12/asyncio/base_events.py` (838-848, 1910-1975), `/usr/lib/python3.12/asyncio/selector_events.py` (141-153). Prior work read: `scratchpad/transport-apps/adapter_bench.py`, `scratchpad/transport-apps/revise/ws_drain_bench.py`, `scratchpad/transport-apps/revise/run_drain.sh`, `scratchpad/transport-apps/revise/results/ws_drain_bench.jsonl`. Subroutine: #1926, #2018, #1941, #1971, #1917, #2008. Prototype and raw results, all under `scratchpad/transport-apps-gap-1-2/` (not house style, and the original `revise/ws_drain_bench.py` is left untouched because #1926's provenance cites it): `ws_coalesce_bench.py`, runner `run_coalesce.sh`, table and analysis scripts `table.py` and `analyse.py`, raw rows `results/ws_coalesce_bench.jsonl` (50 rows), the loaded-machine wake-up counts `results/loaded_ratio.jsonl`, and the per-row load log `results/run.log`. No URL was relied on; the two runtime facts are cited from the installed CPython 3.12.3 the measurement ran under rather than from a repository copy.
