**Question.** The first-use-case assembly names three questions in prose that no `needs_input` task carries — the thread-to-loop crossing rule, the scope of the read-only engine exposures, and the service's listen port — so how are they filed, and what short list does each carry?

They are now filed as #2021 (the crossing rule), #2019 (the exposure scope) and #2020 (the listen port), each linked to #2018 and to the documents it rests on, and #2018 is amended everywhere it said they were unfiled — nine lines, from the summary to the Not covered section — so that its question list names all fifty-three. Checking the three before filing changed two of them. The coalescing that makes the crossing rule affordable in #2018's own table does not coalesce, and the per-message cost it was there to avoid does not appear at a human tap rate anyway. The exposure set #2018 proposes widening #1963 to is six items, of which three are already reachable without touching a private name. The port recommendation survives, with one alternative it did not weigh.

## Why these three and not the other fifty

The fifty filed spikes (#1942 to #1991) were each raised by a research point and filed with it. These three were raised by the assembly itself, when two points that had never been read against each other turned out to disagree, when an engine-change bullet turned out wider than the question filed for it, and when a number no point had been asked for had to be written down. Nothing in the process filed them, and #2018 says so under Not covered: "they should be filed before the list is put in front of Simon."

The first of them is not a loose end. #2018 calls it "the design's one open coupling", and it gates the grid decision, one of the seven the specification requires the assembly to put to Simon. The seven-decision list was incomplete at the point where it matters most.

## The crossing rule

**What it decides.** Whether the Subsequence adapter, holding an inbound `set` frame on its own daemon thread, crosses onto the composition's asyncio loop at once or waits for the sequencer's own hooks.

**Why it was never asked.** Each of the two points that touch it assumed the other's answer. The state-sync design prices tap-to-`ack` at "a few milliseconds" on the assumption that the helper marshals each panel write onto the loop promptly; the adapter concurrency finding measured that call at about 1.1 ms at p99 on the clock and moved the crossing into a queue drained at the sequencer's hooks at no measurable cost. Both are right about what they measured, and the combination was never priced. `beat` fires once every 24 pulses (`subsequence/sequencer.py:1427`, with `pulses_per_beat` set from `MIDI_QUARTER_NOTE` at `sequencer.py:357`) and `reschedule_pulse` once per pattern cycle (`sequencer.py:1804`), so under the drain rule a tap waits up to one beat to be applied, and the `ack` that moves the cell's face leaves at application: 500 ms at 120 BPM, 1000 ms at 60 BPM, 333 ms at 180 BPM.

**What does not move.** Tap to sound is the same in every column. The `reschedule_pulse` drain is awaited immediately before the rebuild that consumes the grid — `await self.events.emit_async("reschedule_pulse", pulse, patterns)` at `sequencer.py:1804`, ahead of the `on_reschedule()` loop at `sequencer.py:1810-1829` — so a queued tap still makes the cycle it was going to make. What the rule moves is the face.

| | A. Drain only at the sequencer's own hooks | B. Wake the loop for a grid set, coalescing a burst into one wake-up | C. B plus the engine-side selector lever |
| --- | --- | --- | --- |
| Tap to `ack`, and so to the face | up to one beat: 500 ms at 120 BPM, 1000 ms at 60 BPM, 333 ms at 180 BPM, about half that on average | a few milliseconds: about 1 ms of browser hop, about 1 ms of wire, a loopback hop to the adapter and one loop wake-up | as B |
| Against the 0.1 s instantaneous threshold | over it by up to ten times | inside it | inside it |
| Clock cost measured by #1926 at 50 Hz | p99 0.001 to 0.002 ms against a 0.002 ms baseline | p99 1.10 ms, 38 to 57 pulses over 1 ms in 1536 | p99 0.001 to 0.018 ms for every per-message shape |
| Clock cost measured by #1926 at a 5 Hz tap rate | as above | p99 0.36 to 0.49 ms, maximum 1.1 ms, 2 to 4 pulses over 1 ms in 1536 | as above |
| Clock cost measured here at a 5 Hz tap rate | p99 0.019 ms drained at `beat`, 69 wake-ups for 1352 messages | p99 0.168 ms, maximum 0.351 ms, **no pulse over 1 ms in 1536** | not run |
| Engine change | none | none | the clock's selector or its 1 ms spin margin (`sequencer.py:465`), which is #1974 |
| Musical effect of the cost | none | a late pulse is late by about 1.1 ms, five percent of a 20.8 ms pulse at 120 BPM | none |
| Tap to sound | unchanged: the cycle | unchanged | unchanged |

**Recommended: B, with A retained as the automatic fallback** for anything that is not a human's tap — a page-load seed, an algorithm's bulk write, a held paint gesture beyond a rate ceiling — and C named as the lever if the real headless server is worse than the workstation. The reason is the specification's own decided table: a step tap's transport latency is irrelevant because it is heard on the next cycle by design, *and the cell should light at once*. Under the recommended pending look the face is the server's value, so the `ack` is the face, and a face up to one beat behind the finger fails that outright. This is #2018's recommendation and the measurement below strengthens it rather than changing it.

**This must be answered with #1968.** The two coherent pairings are B with the ring — nothing on a face is speculative and the face follows within milliseconds — or A with the optimistic face, where the cell flips locally on the finger and the server's value corrects it up to a beat later, which is what makes A survivable. A with the ring is the combination to avoid, and it is the combination the points as filed would have produced.

### What the measurement changed

#2018 lists the coalesced wake-up under Not covered: scheduling one drain per burst rather than one per message "is inferred from the finding's own conclusion that the cost is per wake-up of the clock loop and not per message. It was not itself measured by any point." It is measured now, on the same workstation, and the inference is half right.

| Crossing rule | Arrivals | Median | P95 | P99 | Max | Pulses over 1 ms of 1536 | Messages | Loop wake-ups |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline, nothing in the process | none | 0.001 ms | 0.015 ms | 0.026 ms | 0.050 ms | 0 | 0 | 0 |
| Per message | one every 200 ms | 0.002 ms | 0.002 ms | 0.168 ms | 0.351 ms | 0 | 169 | 169 |
| Pending-flag coalesced | one every 200 ms | 0.002 ms | 0.003 ms | 0.137 ms | 0.259 ms | 0 | 169 | 169 |
| Per message | eight 1 ms apart, five times a second | 0.001 ms | 0.014 ms | 0.924 ms | 1.114 ms | 11 | 1352 | 1352 |
| Pending-flag coalesced | as above | 0.002 ms | 0.002 ms | 0.273 ms | 1.141 ms | 10 | 1360 | 1360 |
| Drained at the `beat` hook | as above | 0.002 ms | 0.009 ms | 0.019 ms | 2.063 ms | 2 | 1352 | 69 |
| Per message | one every 20 ms | 0.002 ms | 0.930 ms | 1.274 ms | 1.295 ms | 70 | 1699 | 1699 |
| Pending-flag coalesced | one every 20 ms | 0.001 ms | 1.033 ms | 1.403 ms | 3.587 ms | 91 | 1699 | 1699 |
| Drained at the `beat` hook | one every 20 ms | 0.001 ms | 0.002 ms | 0.002 ms | 0.136 ms | 0 | 1699 | 69 |

Three readings.

**The 50 Hz rows reproduce #1926.** Per-message p99 1.27 ms with 70 pulses over 1 ms in 1536, against a drained p99 of 0.002 ms and none. The mechanism #1926 identified — CPython's epoll selector rounding every timeout up to a whole millisecond so that a mid-sleep wake-up overshoots the clock's 1 ms spin margin at `sequencer.py:465` — is unchanged on a newer interpreter.

**At a human tap rate the per-message cost did not appear at all.** One cell set every 200 ms left no pulse over 1 ms in 1536, a p99 of 0.168 ms and a maximum of 0.351 ms. #1926's own 5 Hz rows recorded p99 0.36 to 0.49 ms with two to four late pulses; the two runs are the same order and both sit far below the 50 Hz figures. Option B is affordable on the per-message figure alone, which is the honest ground to recommend it on.

**The pending flag does not coalesce.** In every arm the loop wake-up count equalled the message count, because the loop services the scheduled drain in microseconds and the flag is clear again before the next message arrives a millisecond later. A pending flag saves a wake-up only when messages arrive closer together than the loop takes to drain. What does collapse a burst is batching at the socket read: the link thread reads every frame the socket has buffered, queues them all and crosses once, which is what a multi-contact chord or a reconnect re-send looks like on the wire, and is a property of how the adapter drains its reader rather than of a flag on the crossing.

That was then measured directly, over two passes with a fresh no-adapter baseline immediately before each arm, 8 bars at 120 BPM (768 pulses), bursts of eight cells about five times a second, load average 0.53 to 1.12 throughout:

| Crossing rule | Pass | P99 | Max | Pulses over 1 ms of 768 | Messages | Loop wake-ups |
| --- | --- | --- | --- | --- | --- | --- |
| Baseline, nothing in the process | both, six runs | 0.002 to 0.008 ms | 0.013 to 2.354 ms | 0, except one run with 1 | 0 | 0 |
| Batched at the read, one crossing per burst | first | 0.111 ms | 0.252 ms | 0 | 712 | 89 |
| Batched at the read, one crossing per burst | second | 0.291 ms | 0.328 ms | 0 | 712 | 89 |
| Per message | first | 0.247 ms | 1.110 ms | 5 | 712 | 712 |
| Per message | second | 0.896 ms | 1.195 ms | 5 | 712 | 712 |
| Pending-flag coalesced | first | 0.243 ms | 1.089 ms | 3 | 712 | 712 |
| Pending-flag coalesced | second | 0.252 ms | 1.096 ms | 4 | 712 | 712 |

Batching at the read turned 712 crossings into 89, one per burst, and left no pulse over 1 ms in either pass, with a maximum of 0.33 ms. The pending flag is indistinguishable from per-message in both passes, on the wake-up count and on the tail. So option B is worth taking on the per-message figure at a human tap rate, and read-batching is what makes a burst free — not a flag on the crossing. That correction is on #2021 and is the one thing #2018's short list overstates.

## The scope of the read-only exposures

**What it decides.** Whether #1963, which asks about three engine exposures, is widened to the whole set #2018's engine-change bullet proposes, or the remainder goes to Simon separately.

#1963 asks about the pulse in the `beat` payload, `cycle_start_pulse` in each `live_info()` pattern entry, and a maximum-device-latency property. #2018 also proposes the grid, the drum note map, the device and the mirrors in each `live_info()` entry, from the grid design's small list, and read-only properties for the muted and energy-gated flags, from the state-sync design's revisions.

Checked against the working tree, the remainder is smaller than it reads. `Composition.sequencer` and `Composition.running_patterns` are both public properties (`subsequence/composition.py:1795-1803`), and `running_patterns` hands back the live pattern objects, so:

| Proposed exposure | Reachable today without a private name? | Where |
| --- | --- | --- |
| `device` in `live_info()` | yes | `Pattern.device`, `subsequence/pattern.py:132`, via `Composition.running_patterns` |
| `mirrors` in `live_info()` | yes | `Pattern.mirrors`, `subsequence/pattern.py:133`, via the same |
| A read-only muted flag | yes, as a fact | already in every `live_info()` pattern entry, `subsequence/composition.py:3901` |
| `cycle_start_pulse` in `live_info()` | yes, except at connect | the second argument of every `pattern_reschedule` event, `subsequence/sequencer.py:1829` |
| The pulse in the `beat` payload | yes, with the ambiguity #1963 names | `Sequencer.pulse_count`, `subsequence/sequencer.py:411` |
| The pattern's grid | no | `_default_grid`, `subsequence/composition.py:5969`; `p.grid` exists only inside the builder, `subsequence/pattern_builder.py:198-200` |
| The drum note map | no | `_drum_note_map`, `subsequence/composition.py:5966` |
| The energy-gate flag | no | `_energy_gated`, `subsequence/composition.py:5975` |
| The maximum device latency | no | `_max_device_latency_ms`, `subsequence/sequencer.py:419`; the registry's `max_latency()` is public at `subsequence/midi_utils.py:153` but reachable only through the private `_output_devices` at `sequencer.py:398` |

| | A. Widen #1963 in place to the whole set | B. Keep #1963 as filed and file the remainder separately | C. One question over the corrected set: grid, drum note map, energy gate, maximum device latency, and the beat pulse |
| --- | --- | --- | --- |
| Questions Simon answers | one | two | one |
| What is decided | everything the assembly proposes | #1963's three now, the rest later | every fact the adapter cannot otherwise reach, and nothing else |
| Risk of a half-answered wave | none | the second question can be missed, which is how this gap arose | none |
| The three already-reachable items | decided with the rest, on no evidence that they need deciding | as A | left to the implementer as conveniences that touch no private name, or dropped |
| Terms the decision is stated in | a list of `live_info()` keys | two lists of `live_info()` keys | which private names the adapter would otherwise read, which is what #1465 cares about |
| Cost of being wrong | a slightly larger engine edit than needed | a second round trip to Simon | the two conveniences are re-proposed later if wanted |

**Recommended: C.** It is A's single question with A's scope corrected, so nothing the assembly proposes is left unasked and nothing is asked that the code already answers. It also states the decision in the terms the governing decision cares about — which private names the first adapter would read — rather than as a list of dictionary keys, which is the form in which Simon can weigh it.

One item stays outside this question in every column: the runtime grid setter #2018 proposes is a writer, not a read-only exposure.

## The listen port

**What it decides.** The number the service listens on, which #1929's configuration sketch carries as a placeholder — `port: <chosen by transport-ui and transport-apps; none of 5555, 8080, 8765, 9000 to 9004>` — and which the app-side line `superintendent: {enabled: true, url: ws://127.0.0.1:<port>}` cannot be written without.

The map, re-verified in the trees: 9000 and 9001 are Subsequence's OSC receive and send (`subsequence/osc.py:46-47`), 9002 is Subsample's OSC receive (`subsample/config.py:540`), 5555 is Subsequence's REPL (`subsequence/composition.py:3444`), 8080 and 8765 are the legacy dashboard (`subsequence/web_ui.py:41`), and 9003 and 9004 are the superseded Supervisor adapters (`subsample/config.py:568`, `substation/config.py:598`). Supervisor served its static page on 8000 (`Supervisor/serve.py:7`). Neither 8090 nor 8085 appears anywhere in the four trees.

Two facts #2018 did not have. In the IANA registry, **8090/tcp is assigned**, as `opsmessaging`, "Vehicle to station messaging"; **8085/tcp is Unassigned**; 9005/tcp is assigned as `golem`; 8000/tcp is `irdmi`; 80/tcp is `http`. And RFC 6335 puts all of these in the User Ports range 1024-49151, assigned by IANA but usable without an assignment — so a registration is a tie-break against de-facto collisions, not a rule. The largest single de-facto claim on 8090 is Confluence's default connector port. Linux's ephemeral range here is 32768-60999, so every candidate is clear of it.

| | A. 8090 | B. 8085 | C. 80 |
| --- | --- | --- | --- |
| Clear of the project's port map | yes | yes | yes |
| IANA | assigned, `opsmessaging` | Unassigned | assigned, `http` |
| Best-known de-facto claim | Confluence's default connector | none dominant | every web server |
| Reads as | a web UI, beside the familiar 8080 | a web UI, beside the familiar 8080 | the machine's web service |
| What a person types | `http://<server>:8090/` | `http://<server>:8085/` | `http://<server>/` |
| Unit cost | none | none | binding below 1024 as a non-root user needs `AmbientCapabilities=CAP_NET_BIND_SERVICE` |
| Free on the development workstation today | yes | yes | no, 80 is bound |
| Risk | a co-tenant that wants 8090 | none known | collides with anything else that wants 80 on that box |

9005 is excluded rather than short-listed: it is IANA-assigned to `golem`, and it reads as the fifth socket in the superseded Supervisor family, which is the wrong thing for the service that replaces them. 8000 is excluded because it is the most contended port on any development machine and it is Supervisor's, which is superseded.

**Recommended: 8090**, configurable in one line of the service's YAML so nothing rests on it, with 8085 named as the equal alternative if the server already hosts anything in the Atlassian or Tomcat-alternate family. The kiosk's URL lives in an autostart file rather than in anyone's fingers, so the third column's brevity buys little for a capability grant. This is #2018's recommendation, and the registry check gives it a real second option rather than a token one.

## How the three are filed

Each is a `spike` in `needs_input` in project `superintendent`, tagged `question` like the other fifty, titled with its question, and carrying its short list, its figures and its citations in the description, in the shape #1963 and #1968 set. #2021 also records that it must be answered with #1968 and names the two coherent pairings; #2019 is linked to #1963, which it either widens or leaves alone; #2020 records that the headless server's occupied ports are unchecked.

`documents` links: #2018, #1925, #1926 and #1928 to #2021; #2018, #1925 and #1928 to #2019; #2018 and #1929 to #2020.

#2018 is amended in nine places, which is every sentence in it that said these were unfiled: the summary, the port recommendation, the crossing short list's closing paragraph, the engine-change bullet for the exposures, the disagreements table, the question list's opening paragraph, the serving and grid groups in that list, and the Not covered section. The Not covered bullet on the coalesced wake-up is rewritten rather than deleted, because the measurement above changes what it says rather than removing the caveat.

## Method

The real `subsequence.sequencer.Sequencer` with `_jitter_log`, driven exactly as `benchmarks/clock_jitter.py` drives it (`benchmarks/clock_jitter.py:36-82`): 120 BPM with pulses of 20.833 ms, spin-wait on, and `output_device_name="SUPERINTENDENT_NO_SUCH_DEVICE"` so `select_output_device` logs the miss and returns nothing rather than opening a port. No MIDI port is opened and no socket is bound. The first block is 16 bars, 1536 pulses per run; the paired-baseline block that carries the batch rows is 8 bars, 768 pulses per run.

The transport is deliberately absent. #1926 established that the cost is per wake-up of the clock loop and independent of the transport — OSC on the loop, OSC on a thread, a WebSocket link on the loop or on a thread and a TCP link on a thread all landed within noise of each other — so what varies between arms here is the crossing rule alone, with an identical arrival process in each. A producer thread stands in for the link thread and each applied message is one dict write on the clock loop, standing in for a `composition.data` write. Wake-ups are counted in the process: one per `call_soon_threadsafe` callback that ran.

Machine: the development workstation, Intel i7-9700K, 8 cores, Linux 6.8, Python 3.13.11 in a scratchpad venv (#1926's block was Python 3.12.3 on the same machine). Single runs, load average 0.35 to 0.9 across the block reported above.

The paired-baseline block that carries the batch rows ran a fresh no-adapter baseline immediately before every arm, at 8 bars each, so each comparison is contemporaneous rather than resting on one baseline taken at the start.

**A second pass of the first matrix is discarded and is reported here rather than dropped.** It ran while other work on the shared workstation took the load average from 1.2 to 8.8, and its own no-adapter baseline degraded to p99 3.27 ms with 189 pulses over 1 ms in 1536 — so the control says the machine, not the crossing rule, is what that pass measured. Every arm in it is unusable and none of its numbers appear above. This is also why the paired-baseline design was used for the second block.

Prototypes, not house style: `crossing_bench.py`, `crossing_bench2.py`, `run_matrix.sh` and `run_focus.sh` with raw results in `results.jsonl` and `results_focus.jsonl`, under the scratchpad directory for this point.

## Hardware-gated

- **The headless server's occupied ports.** Whether 8090, 8085 or 80 is already bound on the machine the service will run on has not been checked, because that machine is not the one this ran on. What is recorded above is the development workstation, where 80 is bound and 8090, 8085 and 9005 are free. This is a one-command check when the server is to hand and it is noted on #2020.
- **The crossing cost on the real server.** Every figure above is the workstation. #2008 already exists for re-measuring the adapter's on-loop cost on the headless server with the transport actually chosen and with whichever crossing rule Simon takes; the coalescing correction above is an addition to it.
- **The tap-to-face figure over the real LAN.** #2002, unchanged: it needs a second host running the service.

Nothing here needs the iiyama panel.

## Not covered

- **A real transport under the batch arm.** The batch rows model the link thread queueing a whole socket read and crossing once, with a producer thread standing in for the socket. Whether a real `websockets` reader on its own loop delivers a burst in one read often enough to realise those figures was not measured; #1926 established that the transport does not change the per-wake-up cost, but how many wake-ups a real reader produces per burst is a property of the reader, and it belongs with #2008.
- **Whether the beat drain or the reschedule drain binds first for a given pattern.** Under option A the `ack` arrives at whichever of the two hooks comes first, so a pattern whose cycle is shorter than a beat is acknowledged sooner. The one-beat bound quoted is the worst case across patterns and is what the short list uses; the per-pattern distribution was not worked out because it does not change the decision.

## Provenance

Files read in the working trees on 2026-09-03: `/mnt/dev/Apps/2026-02 Sequencer/subsequence/sequencer.py` (350-360, 395-420, 460-470, 481-500, 1415-1435, 1795-1835, and greps for `pulse_count`, `current_bpm`, `_output_devices`, `_max_device_latency_ms`), `subsequence/composition.py` (1795-1812, 3868-3930, 5940-6040, and greps for `_running_patterns`, `_muted`, `energy`, `live`), `subsequence/pattern.py` (105-165, and a grep for `_default_grid`, `drum_note_map`, `mirrors`, `_cycle_start_pulse`), `subsequence/pattern_builder.py` (grep for `_default_grid`, `_drum_note_map`, and the `grid` property at 198-200), `subsequence/midi_utils.py` (135-165), `subsequence/osc.py` (1-50), `subsequence/web_ui.py` (41), `benchmarks/clock_jitter.py` (1-95), `pyproject.toml` (1-40); `/mnt/dev/Apps/Subsample/subsample/config.py` (535-575), `subsample/osc.py` (47); `/mnt/dev/Apps/SDR Scanner/substation/config.py` (593-602); `/mnt/dev/Apps/Supervisor/serve.py` (1-10).

Subroutine read: #2018 in full, #1925, #1926, #1928, #1929, #1963, #1968, and the specification for this research.

URLs: https://www.iana.org/assignments/service-names-port-numbers/service-names-port-numbers.csv (fetched 2026-09-03, the rows for 80, 7000, 8000, 8081, 8085, 8090, 8091, 9005, 9006); https://www.rfc-editor.org/rfc/rfc6335.txt (section 6, the three port ranges); https://confluence.atlassian.com/spaces/DOC/pages/165823/Change+listen+port+for+Confluence (Confluence's default connector port).

Prototypes and raw results, under this point's scratchpad directory: `crossing_bench.py`, `crossing_bench2.py`, `run_matrix.sh`, `run_focus.sh`, `results.jsonl`, `results_focus.jsonl`.

Subroutine items written: #2021, #2019 and #2020 filed as `needs_input` spikes in project `superintendent` with `documents` links from #2018, #1925, #1926, #1928 and #1929 as each rests on them, a `relates_to` link from #2021 to #1968 and from #2019 to #1963; #2018's body amended twice and a comment recorded against it saying what changed.
