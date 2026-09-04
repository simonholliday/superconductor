**Question.** What does #2021's crossing recommendation become once #2025's measurements are carried into it, and what does that leave open?

## Where the documents stood

#2021 is the in-force spike for the one open coupling #2018 names: whether a panel grid set wakes the composition loop for a few-millisecond acknowledgement or waits for the next `reschedule_pulse` or `beat` drain. It is `needs_input`, it is the item Simon actually answers, and before this revision it recommended "**B, with A retained as the automatic fallback** for anything that is not a human's tap — a page-load seed, an algorithm's bulk write, a held paint gesture beyond a rate ceiling". #2025 measured both halves of that fallback and both fail:

- **Bulk is the cheapest traffic there is.** 8192 `set` frames delivered as eight bursts of 1024 cost zero pulses over 1 ms in 1536 and a p99 of 0.034 ms, and a 128-frame burst cost one late pulse, against 36 to 48 late pulses for a tenth of that traffic spread evenly at the paint rate of 25 Hz. The dearest traffic on the clock is the human's tap, which is the one case the fallback exempts.
- **The rate ceiling has nowhere to sit.** A ceiling that caught a held paint gesture would have to sit at or below the gesture's own 16 to 32 frames a second (#1971's paint-along-a-row across a sixteen-column grid in half a second to a second; #1941 for what a browser and a HID digitizer can produce), so it would either never fire or hand the whole stroke to A and put the face a beat behind the finger for the length of the stroke; above the gesture there is nothing left to catch, because 200 and 500 Hz cost no late pulse at all.

#2025 also re-priced one row of #2021's own table. Its "Measured here, isolated taps at 5 Hz" figures for column B — p99 0.168 ms, maximum 0.351 ms, no pulse over 1 ms in 1536 — came from an in-process producer thread calling `call_soon_threadsafe` directly, with no socket read, no frame assembly and no JSON parse. Over a real `websockets` link the same rate costs 4 to 7 late pulses at p99 0.55 to 0.73 ms, which this point reproduced independently at 6 late pulses and p99 0.613 ms on its own quiet block.

Two further things were true of the documents and are the reason this is a design rather than an edit. #2025 leaves five choices in its body and on no task, against the specification's rule that a question for Simon goes on a `needs_input` task: whether the pending flag is replaced by batching at the socket read, whether the bulk fallback is dropped or re-grounded, whether the rate ceiling becomes something else, whether the envelope gains a batched `set`, and whether an engine-side lever is taken. The first three are answered inside #2021's recommendation by this revision, because they are what that spike is for; the fourth and the part of the first that rewrites #1928's rule were on no spike at all and are #2030 and #2031; and #1974 already carried the engine-lever question and needed only a link, which it has.

## What the envelope in force already carries, and what that does to the burst

The first version of this design said that #1916 and #1920 "carry one cell per `set`", and priced a bulk edit as one frame per cell — 128 frames for a "clear row". That is wrong about the contract in force, and it is the premise the whole read-batching case rested on.

#1916's message table defines `set` as "Explicit new value on a leaf, a grid row or a grid cell", and its sub-path paragraph is explicit: "Under a `grid` leaf, `<leaf>/<row id>` addresses a row and `<leaf>/<row id>/<col>` a cell ... a `set` on a row carries a row array that replaces the row, a `set` on a cell carries a partial `cell` merged into it". The worked drum-grid leaf is `{"id": "grid", "kind": "grid", "path": "/subsequence/kit/grid", "value": "cells", "access": "rw", ...}`, and a `cells` value is the whole grid. So under the contract already in force:

- **A row clear or a row fill is one frame**, not sixteen and not 128. The first use-case's grid is sixteen steps by eight parts, so a row is sixteen columns and 128 frames is the whole grid, not a row.
- **A paste or a preset load is one frame** — a leaf `set` carrying a `cells` object, which #1920 measures at under 1 KB and about 12 microseconds to encode for 128 cells.
- **A page-load seed is not inbound at all**: on connect the app sends `manifest` and `snapshot` outbound and the service relays a `snapshot` to the browser (#1916, #1920), and an algorithm's bulk write never leaves the process.

That leaves exactly one inbound burst that the contract in force actually produces: **the reconnect re-send**. #1920 has the client hold each `set` in a pending map and, after a reconnect's snapshot, "re-send every pending `set` with its original `seq`, in order"; a pending set unacknowledged for 5 s reverts, so the backlog is bounded by about five seconds of gesture — of the order of a hundred frames at the paint rate, which is what the 128-frame rows below stand for. It is the honest burst, it happens once per reconnect, and its measured cost on the clock is below.

Everything the first version of this design credited to read-batching turned on a burst the envelope does not produce. What survives is priced below, and it is not enough to carry the recommendation it was carrying.

## What was measured here

The instrument is #2025's, which is `benchmarks/clock_jitter.py`'s: the real `subsequence.sequencer.Sequencer` with `_jitter_log` set, 16 bars at 120 BPM (1536 pulses of 20.833 ms), spin-wait on, no MIDI port opened. One adapter shape per run inside the sequencer process, a separate sender process as the stand-in service, each inbound frame becoming one dict write on the clock loop. Machine: the development workstation (Intel i7-9700K, 8 cores, Ubuntu 6.8.0-138, Python 3.12.3, `websockets` 17.1), single runs, load-gated, indicative only.

**Which probe made these rows.** Every jitter and crossing figure below marked "batched at the socket read" was taken with one long-lived `recv` task probed by three passes of `asyncio.sleep(0)`, which is #2025's shape and the shape in the bench. `asyncio.wait({task}, timeout=0)`, which the trap section below recommends, appears only in the four-burst probe comparison, where the two measured identically. Nothing here was taken with `asyncio.wait_for(ws.recv(), 0)`, which never batches.

Three blocks were run. One was discarded: another research point was running the same bench from the same shared scratchpad copy on the same ports at the same time, and one row came back with a hundred and twenty-eight-frame label and sixteen-frame contents, which is that point's traffic and not this one's. Nothing from it is quoted. Block H runs a private copy of the bench on private ports (9121, 9123, 9124, 9125) and waits both for a one-minute load average at or below 1.10 and for the other point's processes to be absent before every row. Blocks J and K were run for this revision on private ports again (9141, 9143, 9144, 9145) under the same gate, to take the rows the verifiers found missing.

### Block H: rates and bursts

| Shape | Traffic | Messages | Wake-ups | Largest batch | Mean | P99 | Max | Pulses over 1 ms of 1536 | Crossing median | Crossing p99 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline, nothing in the process | none | 0 | 0 | n/a | 0.0013, 0.0016 ms | 0.003, 0.002 ms | 0.003, 0.618 ms | 0, 0 | n/a | n/a |
| Per message | 5 Hz | 170 | 170 | n/a | 0.020 ms | 0.613 ms | 1.254 ms | 6 | 0.067 ms | 0.191 ms |
| Batched at the socket read | 5 Hz | 170 | 170 | 1 | 0.021 ms | 0.625 ms | 1.385 ms | 7 | 0.296 ms | 0.369 ms |
| Pending flag | 128 frames every 2 s | 2176 | 241 | 63, mean 9.0 | 0.007 ms | 0.148 ms | 1.172 ms | 1 | 0.073 ms | 1.103 ms |
| Batched at the socket read | 128 frames every 2 s | 2176 | 17 | 128, mean 128 | 0.004 ms | 0.076 ms | 0.924 ms | 0 | 1.291 ms | 12.62 ms |
| Off the loop, no crossing | 128 frames every 2 s | 2176 | 0 | n/a | 0.004 ms | 0.123 ms | 1.103 ms | 1 | 0.0001 ms | 0.0008 ms |
| Batched at the socket read | 1024 frames every 4 s | 8192 | 8 | 1024, mean 1024 | 0.003 ms | 0.017 ms | 0.568 ms | 0 | 9.40 ms | 20.02 ms |
| Per message | 500 Hz | 14187 | 14187 | n/a | 0.034 ms | 0.455 ms | 0.670 ms | 0 | 0.127 ms | 0.168 ms |
| Batched at the socket read | 500 Hz | 14218 | 14212 | 7, mean 1.001 | 0.043 ms | 0.525 ms | 0.754 ms | 0 | 0.259 ms | 0.336 ms |

Two figures in the baseline row are the block's opening and closing baselines. The load average was between 0.34 and 0.77 for every row, stamped at each row's start and end. Every row applied every frame it received and dropped none. "Crossing" is the interval from the frame leaving the link thread to the write landing on the clock loop; the return leg is not instrumented.

### Block J: the paint rate, every shape, one quiet block

The paint rate is the rate the crossing rule exists for and the dearest traffic on the clock, and block H has no row at it. The figure the first version of this design quoted for the recommended shape — p99 1.216 ms and 38 late pulses — is #2025's block F, whose own baseline logged 25 pulses over 1 ms at p99 1.4775 ms with the load average drifting from 0.99 to 1.65. That row's own load stamps are 0.67 and 0.66, so the row is not itself suspect; what it lacked was a clean baseline to be read against. This block supplies one.

BLOCK_J_TABLE

### Block K: a second panel's tap inside another panel's burst

#1928 gives each app one adapter module with one outbound WebSocket to the service, so every panel's writes reach the app on one connection. A tap from a second panel, or from a laptop browser, can therefore arrive in the middle of another client's burst — and the specification requires that case, deciding that a second panel or a laptop browser must be able to join and that multiple clients see each other's taps. This is the one place the first version's central argument, that read-batching "lengthens the crossing exactly where the traffic is bulk and no cell is waiting on an `ack` a finger can feel", fails: the tap behind the batch does have a finger on it.

The sender injects one frame on a distinct cell half way through each burst, and one in the quiet after it, and their crossings are reported apart from the burst's. `capped` is the same read-batching shape with the inner read loop stopped after 64 frames instead of running until the socket yields nothing.

BLOCK_K_TABLE

## The implementation trap, measured

A read-batching adapter must probe for a further frame without cancelling the read it is probing, and the natural probe silently never batches. `asyncio.wait_for(ws.recv(), 0)` wraps the coroutine in a task, finds it not done — because it has not started — and cancels it, then raises `TimeoutError` (`/usr/lib/python3.12/asyncio/tasks.py:472-520`, the `timeout is not None and timeout <= 0` branch at 507). One long-lived `recv` task probed with `asyncio.wait({task}, timeout=0)` never cancels anything: `_wait` adds a done-callback, waits on a zero-delay timer, and on return removes the callbacks and partitions the futures into done and pending without touching the pending ones (`/usr/lib/python3.12/asyncio/tasks.py:522-563`, the `call_later` at 531, the partition at 557-562). Measured over a real `websockets` link on localhost, four bursts of each size, the two shapes are not close:

| Probe | 16-frame bursts | 128-frame bursts | 1024-frame bursts |
| --- | --- | --- | --- |
| `asyncio.wait_for(ws.recv(), 0)` | 64 crossings for 64 frames, largest batch 1 | 512 for 512, largest batch 1 | 4096 for 4096, largest batch 1 |
| One long-lived `recv` task, `asyncio.wait({task}, timeout=0)` | 4 crossings for 64 frames, largest batch 16 | 4 for 512, largest batch 128 | 4 for 4096, largest batch 1024 |
| One long-lived `recv` task, three passes of `asyncio.sleep(0)` (#2025's shape, and the shape every jitter row above used) | 4 for 64, largest batch 16 | 4 for 512, largest batch 128 | 4 for 4096, largest batch 1024 |

`websockets` documents that "Canceling `recv` is safe. There's no risk of losing data. The next invocation of `recv` will return the next message", so the trap is not lost frames: it is a device that quietly does nothing, in a shape a reviewer would pass. The batches here are larger than the socket bench's because sender and reader share one process, so the reader cannot empty the socket mid-burst; over a real link a 1024-frame burst took three or four crossings in #2025's loaded block, and exactly one per burst in block H.

## The three consequences, and why each is what it is

**The pending flag is dropped.** The flag fires only on frames arriving back to back, and then at about eight or nine to one, not one per burst; at every rate below 500 Hz it schedules exactly one drain per message and adds about 0.05 ms to each crossing for the queue hop, plus a lock and a flag per frame. It is dominated by both of its neighbours and nothing argues for keeping it.

**What replaces it is nothing, not read-batching.** This is the change from the first version of this design, and it follows from the section on the envelope above together with the block J and K rows. At every rate a hand or a browser produces, read-batching *is* per-message crossing: 170 wake-ups for 170 messages at 5 Hz with a largest batch of one, 845 for 845 at 25 Hz with a largest batch of one, six saved in 14218 at 500 Hz. It differs from per-message crossing only on a burst, and there its whole measured advantage on the clock is one late pulse of 1.17 ms in 1536 at 128 frames and none at all at 1024. Against that one pulse it costs a longer crossing on every lone frame, a crossing tail inside a burst measured at a 12.6 ms p99 at 128 frames and 20.0 ms at 1024, another panel's tap held behind the batch, a batch that is unbounded where the queue behind it is not, a bounded drain that can split one bulk edit across a rebuild, and a probe that fails silently. That is not a trade worth making for a burst the envelope produces once per reconnect.

**The bulk fallback to A is dropped rather than re-grounded.** Its clock justification is refuted above. The only other ground available is that a bulk write needs no per-cell `ack` and that A gives the drain a natural batch, and that does not survive either. The `ack` count is unchanged by the choice: #1925 makes the helper append one `ack` and one `changed` per applied write to a single ordered log at the moment of application, which the link thread drains, so N cells produce N acknowledgements under A and under B alike; the only way to batch acknowledgements is to batch the request, and #1916 already batches it — a row `set` or a leaf `set` is one frame, one `seq` and one `ack`. And the traffic the fallback names is largely not inbound at all, for the reasons in the envelope section. What remains is the reconnect re-send, which costs the clock one late pulse without any device at all.

**The rate ceiling is dropped because it buys nothing, not because it would do harm.** The clock cost is not monotonic in message rate. It peaks where wake-ups are frequent enough to catch most pulse sleeps but too sparse to keep the loop's ready queue non-empty, which is at or near one wake-up per pulse — 48 Hz at 120 BPM, 24 Hz at 60 BPM, 72 Hz at 180 BPM — and is gone by 200 Hz, because `EpollSelector.select` rounds a positive timeout up to a whole millisecond and leaves a zero timeout alone (`/usr/lib/python3.12/selectors.py:451-459`) while `BaseEventLoop._run_once` passes zero whenever a callback is already ready (`/usr/lib/python3.12/asyncio/base_events.py:1941-1949`), and the clock's spin margin is 1 ms (`subsequence/sequencer.py:465`, the spin at `1556-1562`).

Two things follow, and the first version of this design overstated both. A limiter is **pointless**: a client stuck at 200 or 500 Hz costs the clock nothing measurable, so what a rate limiter would protect is not the clock. It is not **harmful**: clamping a runaway into the tens of hertz would park it at the peak of that curve, which is where a human's own paint gesture already sits, and this design says elsewhere that those late pulses are about a millisecond each against a 20.833 ms pulse and are worth admitting. So the correct statement is #2025's and no more: if a ceiling is kept it should be a safety valve against a runaway client, set well above any gesture, and not a latency policy. A rate in the tens of hertz is the one band to avoid; above 72 Hz — the peak at the fastest tempo in the stated range — the same measurements say a ceiling is safe at every tempo from 60 to 180 BPM. The overload story that is actually needed is the bounded queue #1928 already specifies, which drops and counts when full, plus a `nack` and a close on sustained overrun.

## Why column C is not in the table below

#2021's third column — the link thread replacing the value on its own thread and never crossing — is not a device inside B and so is not short-listed here, but it is measured in every block above and it wins every column: zero wake-ups, one late pulse at a 128-frame burst and none at 25 Hz, and a crossing of 0.0009 to 0.0001 ms. It is left out of this table for a reason that belongs on the record rather than only in #2021. The engine itself already writes `composition.data` from a non-asyncio thread — the rtmidi callback applies CC input mappings inline "on the stated ground that single dict writes are safe from a non-asyncio thread under CPython's GIL" (`subsequence/sequencer.py:770-772`, the write at `803`) — so C is not exotic. What it costs is #1925's single-writer invariant: its version counter, its one ordered outbound log and its last-writer-wins all rest on every write being applied on the loop, and off the loop there is no order against the algorithm's writes inside the rebuild. Taking C means re-opening #1925, which is why it is an answer to #2021 and not a choice inside B.

## Trade-off table: what replaces the pending flag in the adapter's inbound rule

Column A of #2021 is not in this table; it is another answer to #2021 itself, and under it none of these devices exists. Column C is out for the reason just given. This table is what B becomes.

TRADEOFF_TABLE

A fifth candidate was excluded rather than short-listed: **a timed batching window**, where the link thread waits a fixed few milliseconds before crossing so that a hand's taps merge. It is excluded because the measurements show there is nothing to merge — frames at 25 Hz are 40 ms apart and the loop services a crossing in about 0.05 to 0.09 ms — so a window that merged anything a hand produced would have to be tens of milliseconds wide, and would then add exactly that to the tap-to-face path the whole column exists to shorten. It is the only shape that trades latency for wake-ups, and the wake-ups are not worth buying.

## Short list

SHORT_LIST

RECOMMENDATION

## What this changes elsewhere

CHANGES_ELSEWHERE

## Not covered

NOT_COVERED

## Hardware-gated

Nothing in this design needs the iiyama panel or a graphical host: it is entirely server-side. The figures are the development workstation's and are indicative; re-taking them on the headless server with whichever rule is chosen is #2008, and the one column to add there is messages per wake-up at 25 Hz. The epoll rounding is a CPython property and will be present on the server; what the server changes is how long a wake-up takes to service, and therefore the rate at which any batching device begins to fire. Two further gates stand behind the recommendation: the end-to-end figure a player would feel across the real LAN (#2002), of which only the inbound half is timed anywhere, and the apply step confirmed against a real `StepGrid.apply()` rather than one dict write (#2009), which is what decides how large any drain may safely be.

## Provenance

PROVENANCE
