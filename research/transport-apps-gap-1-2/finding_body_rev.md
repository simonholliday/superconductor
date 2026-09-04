Summary: The pending flag that the first-use-case assembly's crossing rule calls "coalescing" never fires at any rate a hand or a browser produces — exactly 1.000 messages per wake-up at 5, 25, 50 and 200 Hz, a largest batch of one, in every block that ran the row and again on a machine at load 3 to 6 — because the clock loop finishes the drain about 0.2 ms after the wake-up and the next frame is milliseconds away. It fires only on frames arriving back to back, and then at about eight to one, not one per burst. Batching at the socket read, which #2021 measured with an in-process producer and which is measured here over a real WebSocket, behaves the same way at a hand rate (1.000 messages per wake-up at 25 Hz) and takes a whole burst in one crossing, so it is the device that delivers what the assembly's cell claimed and the flag does not. The recommendation to cross promptly stands: the crossing itself is 0.14 to 0.20 ms at the median under the pending flag and 0.05 to 0.15 ms per message, against the drain rule's 243 to 251 ms median and 497 to 500 ms maximum, which #2018 had as arithmetic and is now a measurement. The clock cost of crossing is not monotonic in message rate: it peaks near one wake-up per pulse — 48 Hz at 120 BPM — at 57 to 67 late pulses in 1536, and is gone by 200 Hz. This agrees with #2021, which is in force and reached the same conclusion about the flag before this work; the one disagreement is at 5 Hz, where a real socket link costs four to five late pulses and #2021's in-process producer cost none.

Does the pending flag the first-use-case assembly calls coalescing cost one wake-up per burst, as its crossing table claims, and what does the recommended rule actually cost at the rates a hand produces?

## What this adds to #2021, which already answers the coupling

#2021 is in force, was revised twice on 2026-09-03, and already carries the answer: "**The coalescing #2018 describes does not coalesce.** Scheduling a drain only when none is pending left the loop wake-up count equal to the message count in every run", and "What does save them is batching at the socket read". #2023 records that the short list changed with it — it "gains an off-loop column and loses its coalescing" — so the in-force short list for this coupling is #2021's, whose C column is now applying off the loop by whole-value replacement and whose selector lever has become a row (#1974). #2018's own body still carries the older three-column table verbatim and still names the coalescing under Not covered, in a bullet rewritten while #2021 was filed; the corrections below are to that table, because it is still the text a reader of #2018 meets.

This work was done from #2018's table and reaches the same conclusion about the flag independently. What it adds, all on a real `websockets` link rather than #2021's in-process producer:

- **A rate sweep** — 5, 25, 50, 200 and 500 Hz — which locates where the flag begins to fire at all (500 Hz, and then barely) and where the clock cost peaks (near one wake-up per pulse) and vanishes (200 Hz and above). #2021 has three rates and no sweep.
- **A burst-size sweep** — 16, 128 and 1024 frames back to back — which prices a page-load seed and separates the flag (about eight frames per crossing) from read-batching (the whole burst).
- **Read-batching and the off-loop shape over a socket.** #2021's figures for both come from a producer thread that calls `call_soon_threadsafe` directly; here the frames arrive on a real WebSocket, which is what an adapter faces, and the socket read turns out to matter.
- **The crossing stopwatch**, which neither #2021 nor #1926 carries: link thread to the write landing on the loop, and therefore the drain rule's beat as a measurement rather than the arithmetic #2018 says it is.
- **Both engine-side levers in one block** with contemporaneous baselines, and what each costs in production rather than in the prototype.

## What was measured, and how

The harness is `benchmarks/clock_jitter.py`'s, unchanged: the real `subsequence.sequencer.Sequencer` with `_jitter_log` set, 16 bars at 120 BPM (1536 pulses at 20.833 ms), spin-wait on, no MIDI port (`benchmarks/clock_jitter.py:36-82`). One adapter shape per run inside the sequencer process; a separate sender process is the stand-in service, and each inbound frame becomes one dict write on the clock loop, standing in for the helper's `composition.data` write. This is the harness of `scratchpad/transport-apps/revise/ws_drain_bench.py` and its conditions are that file's: asyncio's default epoll selector, the same venv, the same machine. The new shapes were added in copies under this point's own directory rather than in that file, which is left untouched because #1926's provenance cites it; `adapter_bench.py` is reused unchanged for the link base, the apply step and the statistics.

Five shapes are compared, all a `websockets` client link on a daemon thread with its own loop, which is what #1928 recommends:

- **A, drain at the sequencer's own hooks.** Frames queued on the link thread, applied in the `beat` listener. No wake-up at all.
- **B without its pending flag.** `loop.call_soon_threadsafe(apply, ...)` per frame. This is the shape #1926 measured, reproduced here as the control.
- **B as the assembly recommends it.** Frames queued on the link thread; a drain is scheduled with `call_soon_threadsafe` only when one is not already pending. The flag is cleared at the *start* of the drain rather than the end, so a frame queued while a drain is running schedules a fresh one — which may find the queue empty, and that empty drain is counted — rather than being left unscheduled.
- **Read-batching.** The link thread takes the frame that woke it and then keeps taking frames for as long as the connection can hand one over without waiting on the network, and only then crosses once. No timer and no added delay: a lone frame crosses as soon as the loop can take it. This is #2021's "the link thread reads every frame the socket has buffered, queues them all, and crosses once", over a socket.
- **Off the loop.** The link thread writes the value itself and never wakes the loop. The engine's own precedent is the rtmidi callback applying CC input mappings inline, on the stated ground that "Single dict writes are safe from a non-asyncio thread under CPython's GIL" (`sequencer.py:771-772`, the write at `803`). This is #2021's C column.

Two traffic shapes: a steady stream at a named rate, and `N` frames written back to back every `P` seconds, which is what a page-load seed or an algorithm's bulk write looks like on the wire, because #2018's envelope carries one cell per `set` frame.

Two things are counted that #1926 did not count. **Wake-ups**: how many times the adapter called `call_soon_threadsafe`, which is one self-pipe byte each (`/usr/lib/python3.12/asyncio/base_events.py:838-847` calls `_write_to_self`, `/usr/lib/python3.12/asyncio/selector_events.py:141-153` sends the byte), so messages per wake-up says directly whether anything coalesced. **Crossing latency**: `perf_counter` taken as the frame leaves the link thread and again as the write lands. This is the inbound half only; the outbound leg — the loop handing an `ack` back to the link thread and out of the socket — is not instrumented, and the harness pushes one frame per beat (69 per run) whatever the inbound rate, so it carries no per-tap outbound path to time.

Machine: the development workstation (Intel i7-9700K, 8 cores, Ubuntu 6.8.0-138, Python 3.12.3, `websockets` 17.1), single runs, indicative only. #2021's block ran under Python 3.13.11, which is one candidate explanation for the 5 Hz disagreement below. **The workstation is shared**, and a first attempt was discarded because it ran while another job held the cores; the runner truncates its own output, so that attempt's rows were overwritten and no figure from it is citable or quoted here. The runner waits for a one-minute load average at or below 1.20 before every row and stamps the load at the row's start and end. The blocks are A (the full set), B (a repeat of A's key rows), C and D (the engine-side levers, twice), E (the 1024-frame bursts) and F (the revision block, which adds read-batching and the off-loop shape). F was stopped after ten of its twenty rows when the workstation's load average rose above 8 and the gate stopped admitting rows; its first two rows had already drifted from 0.99 to 1.65 and from 1.18 to 2.35 during the run and are not quoted, and the eight that follow held between 0.55 and 1.01. The burst rows F did not reach were then taken as **counts only** on the loaded machine, since a wake-up count is a count and not a timing; they are marked as such where they appear, and no jitter figure is taken from them.

Every row applied every frame it received and dropped none; two rows drained at `beat` show one frame fewer applied than received, which is the frame that arrived after the run's last `beat` and was still queued at teardown.

## Coalescing never fires at a rate a hand produces, whichever device is used

A held paint-along-a-row gesture (#1971) crossing a sixteen-column grid in half a second to a second is 16 to 32 `set` frames a second. The panel's own HID report rate is unmeasured — #1917 records that no figure exists in iiyama's datasheet — and the Windows guideline it would meet bounds it at 100 to 250 Hz (#1941); the browser aligns continuous input events to the animation frame, so a stroke is capped at the display's frame rate, which #1941 states from Chrome's own page that discrete events "will be dispatched right away" and only continuous ones are aligned. 25 Hz is the middle of that gesture and is the row the crossing decision turns on.

| Shape | Rate | Messages | Wake-ups | Messages per wake-up | Largest batch |
| --- | --- | --- | --- | --- | --- |
| B without the flag | 5 Hz | 170, 170 | 170, 170 | 1.000, 1.000 | n/a |
| B as recommended | 5 Hz | 170, 170 | 170, 170 | 1.000, 1.000 | 1, 1 |
| B without the flag | 25 Hz | 839, 839 | 839, 839 | 1.000, 1.000 | n/a |
| B as recommended | 25 Hz | 839, 839 | 839, 839 | 1.000, 1.000 | 1, 1 |
| Read-batching | 25 Hz | 838 | 838 | 1.000 | 1 |
| Off the loop | 25 Hz | 842 | 0 | n/a | n/a |
| B without the flag | 50 Hz | 1659, 1655 | 1659, 1655 | 1.000, 1.000 | n/a |
| B as recommended | 50 Hz | 1658, 1655 | 1658, 1655 | 1.000, 1.000 | 1, 1 |
| Read-batching | 50 Hz | 1668 | 1668 | 1.000 | 1 |
| Off the loop | 50 Hz | 1664 | 0 | n/a | n/a |
| B without the flag | 200 Hz | 6230 | 6230 | 1.000 | n/a |
| B as recommended | 200 Hz | 6203 | 6203 | 1.000 | 1 |
| B without the flag | 500 Hz | 14128 | 14128 | 1.000 | n/a |
| B as recommended | 500 Hz | 14087 | 14080 | 1.000 | 7 |

Two figures per cell are the two blocks that ran the row. The 25 Hz flagged row ran in all of A, B, C, D and F — under the engine's own settings and under each of the two levers; the 50 Hz flagged row ran in A, B and F, all under the engine's own settings, and never under a lever. The read-batching and off-loop rows are F's, which ran once.

The result is exact at every rate below 500 Hz: **every message gets its own wake-up and the largest batch any drain ever saw was one**. At 500 Hz the flag fires for the first time and saves seven wake-ups out of 14087, one drain catching seven frames; that is the only steady-rate row in the whole set where the wake-up count is lower than the message count, and it is a fifth of a percent.

The reason is the crossing latency measured below: the clock loop takes about 0.2 ms to service a wake-up and empty the queue, and the next frame in a steady stream is 2 ms away at 500 Hz and 200 ms away at 5 Hz. There is no window in which a second frame can join the first. The same counts were taken again on a machine carrying another job at load 3.2 to 6.1, four bars per row: 5 Hz 50 messages and 50 wake-ups, 25 Hz 246 and 246, 50 Hz 488 and 488 — 1.000 in every case. Contention does not create coalescing either.

**Read-batching behaves the same way at a hand rate**, and this is the result that matters for the recommendation. At 25 Hz it took 838 wake-ups for 838 messages and at 50 Hz 1668 for 1668, each with a largest batch of one, because there is nothing buffered on the socket to batch. Neither adapter-side device buys anything at the rate the crossing rule exists for. This is not a property of these particular implementations: any device can only merge frames that arrive closer together than the loop takes to service one, and any window wide enough to merge frames 40 ms apart is itself 40 ms of added latency, which is the thing the crossing rule exists to avoid.

**Only the off-loop shape removes the wake-up at a hand rate**, because it never crosses: 842 messages at 25 Hz and 1664 at 50 Hz, no wake-up at either, the link thread writing the value itself. The four shapes ran back to back in one block at each rate, and at 50 Hz the whole block held a load average between 0.55 and 1.01:

| Shape | Rate | Wake-ups for the messages | P99 | Max | Pulses over 1 ms of 1536 | Crossing median |
| --- | --- | --- | --- | --- | --- | --- |
| B without the flag | 50 Hz | 1663 for 1663 | 1.286 ms | 1.577 ms | 69 | 0.066 ms |
| B as recommended | 50 Hz | 1658 for 1658 | 1.289 ms | 1.503 ms | 51 | 0.178 ms |
| Read-batching | 50 Hz | 1668 for 1668 | 1.259 ms | 1.511 ms | 51 | 0.097 ms |
| Off the loop | 50 Hz | 0 for 1664 | 0.003 ms | 0.463 ms | 0 | no crossing |
| B as recommended | 25 Hz | 839 for 839 | 1.272 ms | 1.532 ms | 34 | 0.139 ms |
| Read-batching | 25 Hz | 838 for 838 | 1.216 ms | 1.530 ms | 38 | 0.271 ms |
| Off the loop | 25 Hz | 0 for 842 | 0.046 ms | 1.929 ms | 1 | no crossing |

The three crossing shapes are indistinguishable from each other and the off-loop shape is on the baseline. Its "crossing median" is not a crossing at all — the stopwatch starts and stops on the same thread a few instructions apart, at 0.3 to 0.4 µs — and that is the point of the column. This reproduces #2021's C column over a socket, and #2021 states what it costs elsewhere: #1925's single-writer invariant, whose version counter, ordered outbound log and last-writer-wins all rest on every write being applied on the loop. The one pulse over 1 ms in the off-loop 25 Hz row is a 1.93 ms outlier in a row whose p99 is 0.046 ms, taken at a load average of 0.66 to 0.75.

## What a genuine burst costs, and what each device does to it

| Traffic | Shape | Messages | Wake-ups | Messages per wake-up | Largest batch | P99 | Max | Pulses over 1 ms of 1536 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 16 frames back to back every 1 s | B without the flag | 544 | 544 | 1.000 | n/a | 0.162 ms | 1.195 ms | 1 |
| 16 frames back to back every 1 s | B as recommended | 544 | 107 | 5.084 | 16 | 0.056 ms | 1.198 ms | 2 |
| 128 frames back to back every 2 s | B without the flag | 2176, 2176 | 2176, 2176 | 1.000, 1.000 | n/a | 0.087, 0.081 ms | 1.187, 1.176 ms | 1, 1 |
| 128 frames back to back every 2 s | B as recommended | 2176, 2176 | 266, 260 | 8.180, 8.369 | 42, 104 | 0.133, 0.100 ms | 1.124, 0.709 ms | 1, 0 |
| 128 frames back to back every 2 s | A, drained at `beat` | 2176 | 0 | n/a | 128 | 0.133 ms | 0.747 ms | 0 |
| 1024 frames back to back every 4 s | B without the flag | 8192 | 8192 | 1.000 | n/a | 0.034 ms | 0.284 ms | 0 |
| 1024 frames back to back every 4 s | B as recommended | 8192 | 1299 | 6.306 | 76 | 0.026 ms | 0.563 ms | 0 |
| 1024 frames back to back every 4 s | A, drained at `beat` | 8192 | 0 | n/a | 1024 | 0.003 ms | 0.401 ms | 0 |

The pending flag does fire here, and does not do what #2018's cell claims. A 128-frame burst costs about sixteen wake-ups, not one; a 1024-frame burst costs about 162. The link thread's loop and the clock loop run concurrently, so by the time the clock loop has been woken and has emptied the queue the link thread has usually taken only a handful of further frames off the socket: the mean batch is 5.1, 8.2, 8.4 and 6.3 frames across the four flagged burst runs. The distribution has a long tail — one drain in a 128-frame run caught 104 frames — but the typical wake-up carries eight, not the burst. On a loaded machine the ratio is the same shape: 1280 messages in bursts of 128 cost 173 wake-ups, 7.4 to one.

**Read-batching is the device that delivers the cell's claim.** The wake-up count is a count and not a timing, so it survives a busy machine; these rows were taken at a load average of 8.7 to 9.0, four bars each, and only their counts are quoted.

| Traffic | Shape | Messages | Wake-ups | Messages per wake-up | Largest batch |
| --- | --- | --- | --- | --- | --- |
| 16 frames back to back every 0.5 s | B as recommended | 320 | 99 | 3.2 | 16 |
| 16 frames back to back every 0.5 s | Read-batching | 320 | 29 | 11.0 | 16 |
| 128 frames back to back every 1 s | B as recommended | 1280 | 87 | 14.7 | 128 |
| 128 frames back to back every 1 s | Read-batching | 1280 | 12 | 106.7 | 128 |
| 1024 frames back to back every 2 s | B as recommended | 4096 | 438 | 9.4 | 277 |
| 1024 frames back to back every 2 s | Read-batching | 4096 | 14 | 292.6 | 762 |

Ten bursts of 128 cost twelve crossings and four bursts of 1024 cost fourteen: at 128 frames that is one crossing per burst, and at 1024 it is three or four, because a burst that large takes long enough to arrive that the reader occasionally empties the socket mid-burst. On a quiet machine it is tighter still — a two-bar shakedown at 128 frames every half second took 12 wake-ups for 1536 messages with a mean and a maximum batch of 128, one crossing per burst exactly. Against the flag's 87 and 438 for the same traffic, this is the difference between an order of magnitude and nothing.

The claim's *conclusion* about the clock nevertheless holds for a reason #2018's cell does not give: **a bulk burst is the cheapest traffic there is, batched or not**. 8192 messages delivered as eight bursts of 1024 cost zero pulses over 1 ms and a p99 of 0.034 ms under plain per-message marshalling, against 26 to 48 late pulses and a p99 above 1 ms for a tenth of that traffic spread evenly at 25 Hz. A burst lands inside one or two pulses and can only spoil those; a steady stream touches a different pulse each time. So read-batching is worth taking for the wake-ups it saves and for the socket work it avoids, not because the clock needs it.

## The clock cost peaks near one wake-up per pulse and falls away above it

| Shape | Rate | Messages per pulse | Mean | Benchmark's own rating | P99 | Max | Pulses over 1 ms of 1536 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline, nothing in the process | none | 0 | 0.002-0.003 ms | Excellent | 0.003-0.023 ms | 0.014-0.228 ms | 0 |
| B without the flag | 5 Hz | 0.11 | 0.016, 0.022 ms | Excellent | 0.546, 0.714 ms | 1.237, 1.271 ms | 4, 5 |
| B as recommended | 5 Hz | 0.11 | 0.020, 0.021 ms | Excellent | 0.726, 0.606 ms | 1.354, 1.321 ms | 7, 6 |
| B without the flag | 25 Hz | 0.55 | 0.082, 0.102 ms | Excellent, Very good | 1.086, 1.297 ms | 1.379, 1.693 ms | 36, 48 |
| B as recommended | 25 Hz | 0.55 | 0.081, 0.098 ms | Excellent | 1.136, 1.213 ms | 1.527, 1.557 ms | 26, 35 |
| B without the flag | 50 Hz | 1.08 | 0.138, 0.162 ms | Very good | 1.256, 1.424 ms | 1.512, 1.603 ms | 57, 67 |
| B as recommended | 50 Hz | 1.08 | 0.159, 0.147 ms | Very good | 1.219, 1.276 ms | 1.417, 1.568 ms | 63, 67 |
| B without the flag | 200 Hz | 4.06 | 0.028 ms | Excellent | 0.310 ms | 0.573 ms | 0 |
| B as recommended | 200 Hz | 4.04 | 0.038 ms | Excellent | 0.475 ms | 0.670 ms | 0 |
| B without the flag | 500 Hz | 9.20 | 0.036 ms | Excellent | 0.482 ms | 0.666 ms | 0 |
| B as recommended | 500 Hz | 9.17 | 0.043 ms | Excellent | 0.498 ms | 0.663 ms | 0 |
| A, drained at `beat` | 5 / 25 / 50 Hz | 0.11 / 0.55 / 1.08 | 0.002-0.005 ms | Excellent | 0.010-0.136 ms | 0.171-0.515 ms | 0 |

Two figures are the two blocks. Four things follow.

**The flag does not change the jitter at any steady rate**, which it cannot, since at those rates it changes no wake-up count. Where the two B rows differ — 26 and 35 late pulses flagged against 36 and 48 not, at 25 Hz — the difference is inside the block-to-block spread of the same shape, which at 50 Hz is 57 against 67 for the identical unflagged shape.

**The cost is not monotonic in message rate, and 50 Hz is close to its peak.** Four times the traffic of 50 Hz costs nothing at all. The reading, from the data and the runtime source rather than from instrumentation of the selector, is this. `EpollSelector.select` rounds a positive timeout up to a whole millisecond and leaves a zero timeout alone (`/usr/lib/python3.12/selectors.py:451-459`), and `BaseEventLoop._run_once` passes a timeout of 0 whenever a callback is already ready and the remaining time to the next timer otherwise (`/usr/lib/python3.12/asyncio/base_events.py:1941-1949`). The clock sleeps to within its 1 ms spin margin and then busy-waits (`sequencer.py:1556-1562`, margin at `sequencer.py:465`). At 25 to 50 Hz the loop is typically interrupted exactly once inside a long rounded wait, re-enters with a fresh positive timeout, and the rounding eats the spin margin — the mechanism #1926 identified. At 200 Hz and above the ready queue is rarely empty when the loop comes round, the timeout is 0, epoll never rounds, and the clock keeps its deadline. At 5 Hz most pulses see no wake-up at all. So the cost peaks where wake-ups are frequent enough to catch most pulse sleeps but too sparse to keep the loop polling — at or near one per pulse, which at 120 BPM is 48 Hz.

**The benchmark's own rating is applied to the mean, not to a percentile** (`benchmarks/clock_jitter.py:100` computes `mean_ms`; `:132-141` sets the bands from it). That is worth knowing because #2018's cell invokes the scale on a percentile, which the scale never sees. It is not itself a reassurance, and it should not be used as one: a mean of 0.162 ms is compatible with the 67 late pulses measured in the same row, which is exactly why a mean-based rating is the wrong statistic for a jitter tail. The figures that price the musical effect are the late-pulse count and the worst pulse, and the worst single pulse in any run here was 1.69 ms, eight percent of a 20.8 ms pulse, against a clock whose own mean jitter is about 3 µs.

**At 5 Hz these rows disagree with #2021 and agree with #1926.** #2021 reports the per-message shape at one message every 200 ms as "p99 0.168 ms, maximum 0.351 ms, no pulse over 1 ms in 1536". Here the same rate costs 4 and 5 late pulses at p99 0.55 and 0.71 ms; #1926's WebSocket row at 5 Hz on this machine costs 4 late pulses at p99 0.361 ms. The two socket-based measurements agree with each other and #2021's does not, and the difference between them is that #2021's arrivals came from an in-process producer thread that called `call_soon_threadsafe` directly, with no socket read, no `websockets` frame assembly and no JSON parse on the link thread. The interpreter differs too (3.13.11 there, 3.12.3 here). Whichever it is, the figure a real adapter should be priced at is the socket one: an isolated tap does cost a handful of late pulses in 1536, not none. At 50 Hz the three agree in shape — #1926's 38 against 57 and 67 here, with this block's extra `perf_counter` and list append per applied message — and all of them are far above the drained rows.

## The crossing itself, and the drain rule's beat

From the frame leaving the link thread to the write landing on the clock loop, in milliseconds. This is the inbound half of the tap-to-`ack` path only.

| Shape | Rate | Median | P99 | Max | Applications timed |
| --- | --- | --- | --- | --- | --- |
| B without the flag | 5 Hz | 0.141, 0.083 | 0.185, 0.195 | 0.342, 0.322 | 170, 170 |
| B as recommended | 5 Hz | 0.192, 0.192 | 0.235, 0.280 | 0.264, 0.354 | 170, 170 |
| B without the flag | 25 Hz | 0.139, 0.139 | 0.181, 0.181 | 0.358, 2.303 | 839, 839 |
| B as recommended | 25 Hz | 0.186, 0.195 | 0.237, 0.237 | 0.442, 22.95 | 839, 839 |
| B without the flag | 50 Hz | 0.135, 0.143 | 0.177, 0.184 | 0.316, 0.305 | 1659, 1655 |
| B as recommended | 50 Hz | 0.188, 0.193 | 0.235, 0.235 | 8.061, 0.335 | 1658, 1655 |
| B without the flag | 200 Hz | 0.138 | 0.177 | 15.386 | 6230 |
| B as recommended | 200 Hz | 0.192 | 0.229 | 1.491 | 6203 |
| B without the flag | 500 Hz | 0.132 | 0.169 | 17.747 | 14128 |
| B as recommended | 500 Hz | 0.176 | 0.220 | 15.496 | 14087 |
| A, drained at `beat` | 5 Hz | 243.2 | 491.7 | 497.3 | 170 |
| A, drained at `beat` | 25 Hz | 249.1, 249.3 | 494.7, 493.6 | 499.9, 498.8 | 838, 838 |
| A, drained at `beat` | 50 Hz | 250.9 | 495.0 | 499.8 | 1658 |

The drain rule's cost was arithmetic in #2018, which says of it "the drain rule's one-beat bound is arithmetic, not measurement", and is now a measurement: at 120 BPM the median wait is half a beat and the maximum is a beat, 497 to 500 ms, to three digits. Under prompt crossing the same wait is a tenth to a fifth of a millisecond at the median and a quarter at p99: across the eighteen per-message steady rows the median runs 0.05 to 0.15 ms and the p99 0.17 to 0.20 ms, and across the fourteen flagged rows the median runs 0.14 to 0.20 ms and the p99 0.22 to 0.28 ms, the flag costing about 0.05 ms for the queue hop.

**The tail is systematic, not an outlier.** Ten of the forty-three rows that cross at all recorded a maximum above 7 ms — in all three crossing shapes and under both levers, the largest being 22.95 ms flagged at 25 Hz and 17.75 ms per-message at 500 Hz — and four of those recorded at least one crossing over 10 ms. A tap that lands in that tail is still twenty times inside a beat, so it does not change which column wins, but the crossing is not bounded and should not be quoted as though it were.

#2018's B cell reads "a few milliseconds: the browser hop ... plus about 1 ms of wire, then a loopback hop to the adapter and one loop wake-up". The loop wake-up term in that sentence is a fifth of a millisecond, not a millisecond: the few milliseconds are all network. The cell's subject is the round trip, and only its inbound half is priced here.

## Both engine-side levers remove the late pulses, and neither is free in production

#2018's C column names the selector or the spin margin as the lever if the workstation figures prove optimistic; #2021 makes it a row and files it as #1974. Both were run here in the same block as the shapes they modify, each twice.

| Lever | Shape | Rate | P99 | Max | Pulses over 1 ms of 1536 |
| --- | --- | --- | --- | --- | --- |
| None (default epoll, 1 ms margin) | B without the flag | 25 Hz | 1.086, 1.297 ms | 1.379, 1.693 ms | 36, 48 |
| Spin margin 2 ms, epoll | baseline | none | 0.003, 0.003 ms | 0.010, 0.013 ms | 0, 0 |
| Spin margin 2 ms, epoll | B without the flag | 25 Hz | 0.249, 0.142 ms | 0.558, 0.536 ms | 0, 0 |
| Spin margin 2 ms, epoll | B as recommended | 25 Hz | 0.233, 0.143 ms | 0.541, 0.563 ms | 0, 0 |
| Spin margin 2 ms, epoll | B without the flag | 50 Hz | 0.336, 0.289 ms | 0.530, 0.563 ms | 0, 0 |
| `SelectSelector`, 1 ms margin | baseline | none | 0.030, 0.003 ms | 1.421, 0.013 ms | 1, 0 |
| `SelectSelector`, 1 ms margin | B without the flag | 25 Hz | 0.002, 0.022 ms | 0.014, 0.029 ms | 0, 0 |
| `SelectSelector`, 1 ms margin | B as recommended | 25 Hz | 0.002, 0.003 ms | 0.054, 0.029 ms | 0, 0 |
| `SelectSelector`, 1 ms margin | B without the flag | 50 Hz | 0.006, 0.003 ms | 0.013, 0.023 ms | 0, 0 |

Every row carrying traffic under either lever left no pulse over 1 ms. The `SelectSelector` rows put the per-message crossing back on the baseline, confirming #1926's select rows in a block whose load did not drift. **One row spoils the clean sweep and is not explained**: one of the two `SelectSelector` baselines, with no traffic at all and a load average of 0.44 to 0.48, recorded a 1.42 ms maximum and one pulse over 1 ms — worse than every `SelectSelector` row that carried traffic. Its twin in the other block was clean at 0.013 ms. So "removes the tail" is what nine of the ten lever rows show and one baseline contradicts; a lever that is going to be relied on should be re-measured on the server rather than taken from this block.

Neither lever is free where it would actually be applied.

- **The spin margin has no public setter.** The prototype writes `seq._spin_threshold` directly (`sequencer.py:465`); the only public control over spin behaviour is `disable_spin_wait()` (`sequencer.py:602`), which turns it off rather than widening it. Taking this lever means either an adapter reaching into engine privates or a small engine API addition, which is a change #1465 and #1461 govern.
- **The selector cannot be confined to one loop by a policy.** `asyncio.set_event_loop_policy` is process-wide, and `composition.play()` runs the clock with `asyncio.run(self._run())` (`composition.py:5421`) with no way to pass a loop in, so a policy that gives the clock a `SelectSelector` gives the adapter's own link loop one too. Confining it needs the engine to accept a loop or a selector. That matters because `select` is O(n) in watched descriptors and "can't accept a FD > FD_SETSIZE (usually around 1024)" (`/usr/lib/python3.12/selectors.py:613`), which is ample for a composition holding a handful of sockets and would not be for a service holding many.
- **The spin margin's price is CPU, and it is measured.** The clock busy-waits for the last `_spin_threshold` of each pulse (`sequencer.py:1556-1562`), so the arithmetic is 1 ms of every 20.833 ms pulse at 120 BPM, 4.8 percent of one core per millisecond of margin. Measured as the whole process's user CPU over a four-bar run (384 pulses, 8 s of clock), two runs at each of the first two margins: 0.44 and 0.45 s at the default 1 ms, 0.67 and 0.67 s at 2 ms, 1.40 s at 4 ms — 5.5, 8.4 and 17.5 percent of one core. The increments are smaller than the arithmetic predicts (0.22 s measured against 0.38 s for the first extra millisecond) because these runs were taken at a load average of 8.7, where the spin loop is preempted and so consumes less CPU than its wall-clock window; they are a lower bound on a quiet machine. Either way, taking this lever roughly doubles the clock's CPU on a server that also runs the UI service.

## #2018's crossing table, corrected

**No corrected cell changes which column wins.** What changes is that one cell claims a mechanism that does not work, one attributes the benchmark's rating scale to the wrong statistic, and two figures that were arithmetic or inference are now measurements. #2018's table is the older one; the in-force short list is #2021's, and the last row below says what carries across.

| Cell | As it stands in #2018 | Corrected |
| --- | --- | --- |
| B, "Coalescing" | "schedule the drain only when one is not already pending, so a burst costs one wake-up rather than one per message — inferred from the finding's own conclusion that the cost is per wake-up and not per message, and **not itself measured**" | Measured, here and in #2021. The flag never fires at a rate a hand or a browser produces: 1.000 messages per wake-up and a largest batch of one at 5, 25, 50 and 200 Hz in every block that ran the row, and again on a machine at load 3 to 6; at 500 Hz it saves seven wake-ups in 14087. It fires on frames arriving back to back and then at about eight to one, not one per burst: 128 frames cost about sixteen wake-ups and 1024 about 162. Its effect on the clock at every rate is inside the block-to-block spread of the same shape. **Replace the flag with batching at the socket read**, which costs the same nothing at a hand rate (1.000 messages per wake-up at 25 Hz) and takes a whole burst in one crossing. |
| B, "Measured clock cost" | "at a realistic 5 Hz tap rate, p99 0.36 to 0.49 ms with a 1.1 ms maximum and 2 to 4 pulses over 1 ms in 1536; at a sustained 50 Hz, p99 1.10 ms and 38 to 57 pulses over 1 ms" | Add the paint rate the rule exists for. At 5 Hz, p99 0.55 to 0.73 ms, maximum 1.24 to 1.35 ms, 4 to 7 pulses over 1 ms in 1536. **At 25 Hz, a held paint gesture: p99 1.09 to 1.30 ms, maximum 1.38 to 1.69 ms, 26 to 48 pulses over 1 ms in 1536.** At 50 Hz, p99 1.22 to 1.42 ms, 57 to 67 late. Above that the cost falls away: at 200 and 500 Hz, no pulse over 1 ms at all. A page-load seed or an algorithm's bulk write is cheaper still: 1024 `set` frames back to back cost zero late pulses and a p99 of 0.034 ms. |
| B, "Tap to `ack`, and therefore to the face" | "a few milliseconds: the browser hop measured 0.8 to 1 ms loopback plus about 1 ms of wire, then a loopback hop to the adapter and one loop wake-up" | Unchanged in its total, but the loop wake-up is now measured and is not a millisecond: 0.05 to 0.15 ms median per message and 0.14 to 0.20 ms with the flag, 0.17 to 0.28 ms at p99, from the link thread to the write on the loop. The tail is not bounded: ten of forty-three crossing rows recorded a maximum above 7 ms and the largest was 23 ms. Only the inbound half is measured; the return leg is not. |
| B, "Musical effect of the cost" | "a late pulse is late by about 1.1 ms ... the jitter benchmark's own scale still rates a 2.0 ms P99 as 'Good'" | The scale is applied to the mean, not to a percentile (`benchmarks/clock_jitter.py:100`, `:132-141`), so the sentence prices the cost with a statistic the benchmark never computes on a percentile. Nor should the mean replace it: the 50 Hz row's mean of 0.162 ms sits in the same row as 67 pulses over 1 ms. The honest figures are the late-pulse counts above and the worst single pulse, which in any run here was 1.69 ms. |
| A, "Tap to `ack`" | "up to one beat: 500 ms at 120 BPM ... roughly half that on average" | Confirmed by measurement rather than arithmetic: median 243 to 251 ms, p99 492 to 495 ms, maximum 497 to 500 ms at 120 BPM. |
| C, "Measured clock cost" | "p99 0.001 to 0.018 ms for every per-message shape at 50 Hz" | Confirmed in a block whose load did not drift: `SelectSelector` gives p99 0.002 to 0.022 ms at 25 Hz and 0.003 to 0.006 ms at 50 Hz with no pulse over 1 ms, though one `SelectSelector` baseline with no traffic showed a 1.42 ms pulse and is unexplained. The second lever is measured for the first time: widening the spin margin from 1 ms to 2 ms also removes every late pulse (p99 0.14 to 0.34 ms). Neither lever is free where it would be applied — see the levers above. |
| The "Not covered" bullet | Already rewritten while #2021 was filed, and correct as it stands. | Leave it. Add only that the pending flag was re-measured over a socket at five rates and three burst sizes here, and that read-batching's whole-burst crossing is confirmed on a real WebSocket. |
| The hardware-gated sentence, "One further measurement is added by this assembly and is not filed: whether the coalesced wake-up ... costs what the per-message measurement predicts, which folds into #2008." | Still in #2018's body. | Strike it. It is measured twice now, on the workstation, and did not need the headless server. What remains for #2008 is what that item already says, plus one column: the messages-per-wake-up count at 25 Hz, because a slower machine takes longer to drain and could make coalescing begin to fire where it does not here. |

What carries into #2021's table, which is the in-force one: its B column's burst row ("712 crossings for 712 messages, or 89 when the reader hands the link thread a whole burst in one read") is confirmed over a real socket and at larger bursts; its "Measured here, isolated taps at 5 Hz" B row understates the cost of a socket link and should be read against #1926's and this block's four to five late pulses; and its C column's off-loop figures are reproduced here over a socket.

## Consequences beyond the table

**The fallback to A for bulk is not needed on clock-cost grounds.** #2021's recommendation is "B, with A retained as the automatic fallback for anything that is not a human's tap — a page-load seed, an algorithm's bulk write, a held paint gesture beyond a rate ceiling". Measured, bulk is the cheapest traffic of all: a 1024-frame seed handed straight to B costs zero late pulses, and a 128-frame seed costs one. The dearest traffic is the human's tap, which is the one case the fallback exempts. The fallback may still be wanted for a reason this measurement does not touch — a bulk write does not need a per-cell `ack` and A gives the drain a natural batch — but it should not be justified by the clock, and with read-batching in place a bulk burst is one crossing anyway.

**The rate ceiling in that rule has nowhere to sit.** A ceiling that caught a held paint gesture would have to be below 20 Hz, which is below the gesture itself, so it would either never fire or hand the whole gesture to A and put the face a beat behind the finger for the length of the stroke. Above the gesture, at 200 Hz and beyond, there is nothing left to catch. If a ceiling is kept it should be a safety valve against a runaway client, set well above any gesture, and not a latency policy.

**One wake-up per burst comes from the adapter, not from the envelope.** #2018's client-to-server vocabulary carries one cell per `set` frame, so a seed of a 16-by-8 grid is 128 frames and of a 64-by-16 grid 1024. A batched `set` — one frame carrying a list of cells — would also give one wake-up, and would cut the JSON parsing on the link thread, so it remains worth having on wire-size grounds. But it is not needed for the wake-up: read-batching delivers that inside the adapter with no change to the contract, which is the cheaper of the two places to fix it.

**Read-batching's price is crossing latency on a burst, not on a tap.** Because the link thread keeps reading before it crosses, a frame early in a burst waits for the rest of it: the crossing median was 1.21 ms at 128 frames and 6.36 ms at 1024, against 0.33 and 0.63 ms for the flag on the same traffic. At a hand rate the price is about 0.13 ms at the median over per-message marshalling, from the passes that probe for a further frame — 0.271 ms against 0.139 ms at 25 Hz. Neither figure is near a beat, and the shape is the right trade: it lengthens the crossing exactly where the traffic is bulk and no cell is waiting on an `ack` a finger can feel, and leaves a lone tap crossing at once.

## Not covered

- **Where between 50 Hz and 200 Hz the cost peaks and how sharply it falls.** Rows were taken at 5, 25, 50, 200 and 500 Hz; the peak is at or near one wake-up per pulse (48 Hz at 120 BPM) and is gone by 200 Hz, but no row sits between. Nothing in the design depends on the shape of that curve, since every rate a panel produces is at or below 50 Hz.
- **The return leg of the crossing.** Only link-thread-to-loop is timed. The loop handing an `ack` back to the link thread and out of the socket is not instrumented, and the harness pushes one frame per beat whatever the inbound rate, so #2018's "tap to `ack`" cell is corrected on its inbound term alone. The end-to-end figure is #2002.
- **The `SelectSelector` baseline that showed a late pulse.** One of two, at a load average under 0.5, unexplained and not chased.
- **Half of the revision block.** F was stopped at ten of twenty rows when the workstation's load rose above 8. What it did not reach on a quiet machine: read-batching and the off-loop shape on bursts with their jitter figures (the counts were taken under load instead), and the flagged shape at 50 Hz under each engine-side lever. Nothing above rests on those rows, and the runner is filed so they can be re-taken.
- **Read-batching under either engine-side lever, and off the loop under either.** Neither combination was run; there is no reason to expect a surprise, since the lever acts on the wake-up and the off-loop shape has none.
- **The selector reading is inferred from the runtime source and the data, not instrumented.** No count was taken of how often `_run_once` chose a zero timeout. The claim that the tail vanishes above 200 Hz is a measurement; the explanation for why is a reading.
- **Tempi other than 120 BPM.** The pulse is 20.833 ms here. At 60 BPM a pulse is 41.7 ms and the peak rate would be about 24 Hz, which is inside the paint gesture; at 180 BPM it is 13.9 ms and 72 Hz. The shape of the argument does not change but the numbers would, and only 120 BPM was run.
- **A real `StepGrid.apply()` in place of the dict write.** The apply step here is one dict write, as in every earlier crossing row. #2008 and #2009 already carry that.

## Hardware-gated

- Nothing in this finding needs the iiyama panel or a graphical host; it is entirely server-side. What was not finished was stopped by the workstation's own load, not by missing hardware, and is named under Not covered.
- The figures are the development workstation's and remain indicative. Re-taking them on the headless server is #2008. The epoll rounding is a CPython property and will be present there; the rate at which the cost peaks scales with the pulse interval and so with tempo, not with the machine, but the machine sets how long a wake-up takes to service and therefore whether anything coalesces there. On a slower server the drain takes longer, so batching would begin to fire at a lower rate than it does here — the first thing to check on the server is the messages-per-wake-up column at 25 Hz, which costs nothing to collect and settles it. That column is an addition to #2008 and is the one part of the coalescing question the workstation cannot close.

## Provenance

Files read in the working tree on 2026-09-03: `subsequence/sequencer.py` (355-360, 460-470, 596-625, 765-805, 1424-1432, 1550-1575, 1800-1832), `subsequence/composition.py` (5405-5426), `subsequence/pattern.py` (145-150), `subsequence/constants/__init__.py` (20-24), `benchmarks/clock_jitter.py` (36-45, 95-145). Runtime source read from the installed CPython 3.12.3 the measurement ran under: `/usr/lib/python3.12/selectors.py` (448-462, 608-618), `/usr/lib/python3.12/asyncio/base_events.py` (836-850, 1936-1952), `/usr/lib/python3.12/asyncio/selector_events.py` (139-155). Prior work read: `scratchpad/transport-apps/adapter_bench.py`, `scratchpad/transport-apps/revise/ws_drain_bench.py`, `scratchpad/transport-apps/revise/run_drain.sh`. Subroutine read: #2021, #2018, #2023, #1926, #1941, #1917. No URL was relied on.

Prototypes and raw results, all under `scratchpad/transport-apps-gap-1-2/` (not house style; the original `revise/ws_drain_bench.py` is left untouched because #1926's provenance cites it): `ws_coalesce_bench.py` with runner `run_coalesce.sh` for blocks A to D; `ws_coalesce_bench2.py` with runner `run_coalesce_2.sh` for block F, which adds the read-batching and off-loop shapes; table and analysis scripts `table.py`, `analyse.py` and `analyse2.py`. Raw rows: `results/ws_coalesce_bench.jsonl` (50 rows, blocks A to E) and `results/ws_coalesce_bench2.jsonl` (F's ten completed rows). Wake-up counts taken on a loaded machine: `results/loaded_ratio.jsonl` (the steady rates and one 128-frame burst) and `results/loaded_ratio2.jsonl` (the read-batching and flagged burst rows). The spin-margin CPU figures are `results/spin_cpu.txt`. Per-row load logs: `results/run.log` and `results/run2.log`.

Two gaps in that trail are named rather than papered over. Block E's three 1024-frame rows in the first file were run by hand and have no entry in `run.log`, so their load is attested only by the `loadavg_start` and `loadavg_end` fields on the rows themselves (0.31 to 0.50); `run_coalesce_2.sh` carries those invocations so they can be re-taken under a logged runner, and F was stopped before it reached them. And `msgs_per_wakeup` in the raw rows is computed from a later read of the shared inbound counter than the `inbound` field beside it (`ws_coalesce_bench.py`, the result dict against the ratio computed after it), so a row can print 1658 messages, 1658 wake-ups and a ratio of 1.001; the counts are the figures to read, and the ratios above are computed from them.
