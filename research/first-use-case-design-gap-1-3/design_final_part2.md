
### What the measurement changed

#2018, before this point amended it, listed the coalesced wake-up under Not covered: scheduling one drain per burst rather than one per message "is inferred from the finding's own conclusion that the cost is per wake-up of the clock loop and not per message. It was not itself measured by any point and is named above as an addition to #2008." It is measured now, on the same workstation, and the inference is half right.

The first block, 16 bars at 120 BPM per run, one arm per run, single runs, load average 0.35 to 1.24 across the block:

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

The last three rows ran as the block's load average rose from 0.44 to 1.24, and they carry no contemporaneous baseline; the coalesced row's 91 late pulses against per-message's 70, and its 3.587 ms maximum, coincide exactly with that peak and should not be read as a property of the pending flag. The paired-baseline blocks below exist because of it.

**The 50 Hz rows reproduce #1926.** Per-message p99 1.27 ms with 70 pulses over 1 ms in 1536, against a drained p99 of 0.002 ms and none. The mechanism #1926 identified — CPython's epoll selector rounding every timeout up to a whole millisecond so that a mid-sleep wake-up overshoots the clock's 1 ms spin margin at `sequencer.py:465` — is unchanged on a newer interpreter.

**For an isolated tap the per-message cost did not appear.** One cell set every 200 ms left no pulse over 1 ms in 1536, a p99 of 0.168 ms and a maximum of 0.351 ms. #1926's own 5 Hz rows recorded p99 0.36 to 0.49 ms with two to four late pulses; the two runs are the same order and both sit far below the 50 Hz figures. That is the ground option B stands on, and it is narrower than a single figure suggests: a burst of eight contacts at the same 5 Hz — a chord, a two-handed accent, a reconnect re-send — cost 3 to 7 late pulses per 768 in every per-message run below, one of them 3.73 ms. The specification puts multi-touch in the requirement, so the burst case is not an edge case; what makes it free is read-batching, not the crossing rule.

**The pending flag does not coalesce.** In every arm the loop wake-up count equalled the message count, because the loop services the scheduled drain in microseconds and the flag is clear again before the next message arrives a millisecond later. A pending flag saves a wake-up only when messages arrive closer together than the loop takes to drain. What does collapse a burst is batching at the socket read: the link thread reads every frame the socket has buffered, queues them all and crosses once, which is a property of how the adapter drains its reader rather than of a flag on the crossing.

Measured directly, over three passes with a fresh no-adapter baseline immediately before each arm, 8 bars at 120 BPM (768 pulses), bursts of eight cells about five times a second, load average 0.53 to 1.12 throughout:

| Crossing rule | P99, the three passes | Max | Pulses over 1 ms of 768 | Messages | Loop wake-ups |
| --- | --- | --- | --- | --- | --- |
| Baseline, nothing in the process, nine runs | 0.002 to 0.008 ms | 0.003 to 2.354 ms | 0 in seven runs, 1 in two | 0 | 0 |
| Batched at the read, one crossing per burst | 0.111, 0.291, 0.146 ms | 0.252, 0.328, 0.266 ms | 0, 0, 0 | 712 | 89 |
| Per message | 0.247, 0.896, 0.220 ms | 1.110, 1.195, 1.092 ms | 5, 5, 6 | 712 | 712 |
| Pending-flag coalesced | 0.243, 0.252, 0.211 ms | 1.089, 1.096, 0.975 ms | 3, 4, 0 | 712 | 712 |

Batching at the read turned 712 crossings into 89, one per burst, and left no pulse over 1 ms in any pass, with a maximum of 0.33 ms. The pending flag is identical to per-message on the wake-up count in all three passes, and on the tail it is not consistently better or worse — fewer late pulses in each pass (3, 4 and 0 against 5, 5 and 6) but no separation the block can support, since the baseline's own noise floor produced a late pulse in two of its nine runs. So option B is worth taking on the per-message figure at a human tap rate, and read-batching is what makes a burst free; a flag on the crossing does nothing. That correction is on #2021 and is what #2018's short list overstated.

The off-loop column was then measured the same way, three passes, a fresh baseline before each arm, 8 bars, the same bursts of eight five times a second, load average 0.37 to 0.64 throughout:

| Arm | P99, the three passes | Max | Pulses over 1 ms of 768 | Messages applied | Loop wake-ups |
| --- | --- | --- | --- | --- | --- |
| Baseline, nothing in the process, six runs | 0.002 to 0.029 ms | 0.013 to 0.033 ms | 0 | 0 | 0 |
| Off the loop, whole-value replacement on the link thread | 0.008, 0.022, 0.010 ms | 0.029, 0.039, 0.021 ms | 0, 0, 0 | 720, 712, 712 | 0 |
| Per message, run beside it | 0.924, 0.127, 0.253 ms | 3.730, 1.033, 1.207 ms | 7, 3, 3 | 712, 720, 712 | 712, 720, 712 |

The off-loop arm is indistinguishable from its own paired baseline on every statistic and wakes the loop zero times, which is what the column claims and is the only arm that is free at any arrival rate. The per-message arm beside it produced a 3.73 ms pulse in the pass whose baseline maximum was 0.03 ms, which is the largest single disturbance recorded in this point and belongs on the record beside B's recommendation.

## The scope of the read-only exposures

**What it decides.** Whether #1963, which asks about three engine exposures, is widened to the whole set #2018's engine-change bullet proposes, or the remainder goes to Simon separately.

#1963 asks about the pulse in the `beat` payload, `cycle_start_pulse` in each `live_info()` pattern entry, and a maximum-device-latency property. #2018 also proposes the grid, the drum note map, the device and the mirrors in each `live_info()` entry, from the grid design's small list, and read-only properties for the muted and energy-gated flags, from the state-sync design's revisions.

Checked against the working tree, the remainder is smaller than it reads. `Composition.sequencer` and `Composition.running_patterns` are both public properties (`subsequence/composition.py:1795-1803`), and `running_patterns` hands back the live pattern objects, so:

| Proposed exposure | Reachable today without a private name? | Where |
| --- | --- | --- |
| `device` in `live_info()` | yes | `Pattern.device`, `subsequence/pattern.py:132`, via `Composition.running_patterns` |
| `mirrors` in `live_info()` | yes | `Pattern.mirrors`, `subsequence/pattern.py:133`, via the same |
| A read-only muted flag | yes, as a fact | already in every `live_info()` pattern entry, `subsequence/composition.py:3901` |
| `cycle_start_pulse` in `live_info()` | only after the first reschedule | the second argument of every `pattern_reschedule` event, `subsequence/sequencer.py:1829`; at connect the only route is the private `pattern._cycle_start_pulse`, written at `subsequence/sequencer.py:1795` |
| The pulse in the `beat` payload | yes, with the ambiguity #1963 names | `Sequencer.pulse_count`, `subsequence/sequencer.py:411` |
| The pattern's grid | no | `_default_grid`, `subsequence/composition.py:5970`; `p.grid` exists only inside the builder, `subsequence/pattern_builder.py:197-200` |
| The drum note map | no | `_drum_note_map`, `subsequence/composition.py:5967` |
| The energy-gate flag | no | `_energy_gated`, `subsequence/composition.py:5976` |
| The maximum device latency | no | `_max_device_latency_ms`, `subsequence/sequencer.py:419`; the registry's `max_latency()` is public at `subsequence/midi_utils.py:153` but reachable only through the private `_output_devices` at `sequencer.py:398` |

The connect-time case is why `cycle_start_pulse` stays in the question rather than dropping out of it: #1920 and #1925 both open with a snapshot, and until that pattern's first `pattern_reschedule` — up to a whole cycle — the adapter's only route to the number is the private attribute.

| | A. Widen #1963 in place to the whole set | B. Keep #1963 as filed and file the remainder separately | C. Widen #1963 in place to the corrected set: grid, drum note map, energy gate, maximum device latency, the beat pulse, and `cycle_start_pulse` for the connect snapshot |
| --- | --- | --- | --- |
| Questions Simon answers | one | two | one |
| What is decided | everything the assembly proposes | #1963's three now, the rest later | every fact the adapter cannot otherwise reach, and nothing else |
| What becomes of #1963 | answered as widened | answered as filed, with a second question outstanding | answered as widened; its three items are all inside the corrected set, so nothing is left standing |
| Risk of a half-answered wave | none | the second question can be missed, which is how this gap arose | none |
| The three already-reachable items (`device`, `mirrors`, muted) | decided with the rest, on no evidence that they need deciding | as A | left to the implementer as conveniences that touch no private name, or dropped |
| Terms the decision is stated in | a list of `live_info()` keys | two lists of `live_info()` keys | which private names the first adapter would otherwise read |
| Cost of being wrong | a slightly larger engine edit than needed | a second round trip to Simon | the two conveniences are re-proposed later if wanted |

**Recommended: C.** It is A's single question with A's scope corrected, so nothing the assembly proposes is left unasked, nothing is asked that the code already answers, and #1963 is answered rather than left half-standing. It states the decision in the terms the engine-change list is actually about — which private names the first adapter would read — rather than as a list of dictionary keys. That ground is not #1465's: #1465 sorts rig-specific *values* out of the engine ("would this value be wrong for somebody with different hardware?"), and #1908 records the reading in one line, that #1465 sorts values, not verbs. A read-only accessor for a pattern's grid or its energy gate is neutral under #1465 whichever way it is expressed, so the recommendation rests on encapsulation and on what the adapter would otherwise have to reach into, not on that decision.

One item stays outside this question in every column: the runtime grid setter #2018 proposes is a writer, not a read-only exposure.

## The listen port

**What it decides.** The number the service listens on, which #1929's configuration sketch carries as a placeholder — `port: <chosen by transport-ui and transport-apps; none of 5555, 8080, 8765, 9000 to 9004>` — and which the app-side line `superintendent: {enabled: true, url: ws://127.0.0.1:<port>}` cannot be written without.

The map, re-verified in the trees: 9000 and 9001 are Subsequence's OSC receive and send (`subsequence/osc.py:46-47`), 9002 is Subsample's OSC receive (`subsample/config.py:540`), 5555 is Subsequence's REPL (`subsequence/composition.py:3444`), 8080 and 8765 are the legacy dashboard (`subsequence/web_ui.py:41`), and 9003 and 9004 are the superseded Supervisor adapters (`subsample/config.py:568`, `substation/config.py:598`). Supervisor served its static page on 8000 (`Supervisor/serve.py:7`). Neither 8090 nor 8085 appears anywhere in the four trees.

Two facts #2018 did not have, and one correction to how they are read. In the IANA registry, **8090/tcp is assigned**, as `opsmessaging`, "Vehicle to station messaging"; **8085/tcp is Unassigned**; 9005/tcp is assigned as `golem`; 8000/tcp is `irdmi`; 80/tcp is `http`. RFC 6335 section 6 puts all of these in the User Ports range, 1024-49151, "assigned by IANA" — and section 8.1.2 says those ports "are available for assignment through IANA, and MAY be used as service identifiers upon successful assignment", reserving use without an assignment for the Dynamic Ports alone, which "have been specifically set aside for local and dynamic use and cannot be assigned through IANA". So the registry cannot be cited as permission to take an unassigned User Port, and it is not what decides this: on a private LAN what decides is what the box already has bound, and after that what a person reading the URL expects. The registry entry is a tie-break where two candidates are otherwise equal. Linux's ephemeral range here is 32768-60999 (`/proc/sys/net/ipv4/ip_local_port_range`), so every candidate is clear of it.

The de-facto claims are the substance, and both short-listed candidates carry one from the same vendor: 8090 is Confluence's default connector port and 8085 is Bamboo's default, per Atlassian's own list of the ports its applications use (Jira 8080, Bamboo 8085, Confluence 8090, Crowd 8095).

| | A. 8090 | B. 8085 | C. 80 |
| --- | --- | --- | --- |
| Clear of the project's port map | yes | yes | yes |
| IANA | assigned, `opsmessaging` | Unassigned | assigned, `http` |
| Best-known de-facto claim | Confluence's default connector | Bamboo's default | every web server |
| Reads as | a web UI, beside the familiar 8080 | a web UI, beside the familiar 8080 | the machine's web service |
| What a person types | `http://<server>:8090/` | `http://<server>:8085/` | `http://<server>/` |
| Unit cost | none | none | binding below 1024 as a non-root user needs `AmbientCapabilities=CAP_NET_BIND_SERVICE` |
| Free on the development workstation today | yes | yes | no, 80 is bound |
| Risk | a co-tenant that wants 8090 | a co-tenant that wants 8085 | collides with anything else that wants 80 on that box |

9005 is excluded rather than short-listed: it is IANA-assigned to `golem`, and it reads as the fifth socket in the superseded Supervisor family, which is the wrong thing for the service that replaces them. 8000 is excluded because it is the most contended port on any development machine and it is Supervisor's, which is superseded.

**Recommended: 8090**, configurable in one line of the service's YAML so nothing rests on it, with 8085 as the alternative. The fallback rule #2018 gave — take 8085 if the server hosts anything Atlassian — does not survive the check, because 8085 is Bamboo's: the honest rule is that either is fine on a headless music server that runs neither, and the check that actually decides is which ports that machine has bound, which is gated below. The kiosk's URL lives in an autostart file rather than in anyone's fingers, so the third column's brevity buys little for a capability grant.

## How the three are filed, and what was corrected on them

Each is a `spike` in `needs_input` in project `superintendent`, tagged `question` like the other fifty, titled with its question, and carrying its short list, its figures and its citations in the description, in the shape #1963 and #1968 set. `documents` links: #2018, #1925, #1926 and #1928 to #2021; #2018, #1925 and #1928 to #2019; #2018 and #1929 to #2020. #2021 is linked to #1968 and #2019 to #1963.

Revised after verification, so that what Simon reads is what this document says: #2021's short list now carries the corrected three columns with the off-loop option, the pairing paragraph carries the third pairing, the three focus passes are all reported and the load ranges are the true ones; #2019 carries the corrected line numbers (`composition.py:5970`, `5967` and `5976`), keeps `cycle_start_pulse` in option C for the connect snapshot, says what becomes of #1963 in each column, and no longer rests its recommendation on #1465; #2020 carries the corrected RFC 6335 reading and Bamboo's claim on 8085. A comment on #1968 records that its "both are inside 0.1 s on the LAN" holds only under crossing option B or C. A comment on #2018 records that its own short-list table still labels option B as coalescing a burst into one wake-up, which the measurement above refutes, and points at #2021 for the corrected column.

#2018 is amended in nine places, which is every sentence in it that said these were unfiled: the summary, the port recommendation, the crossing short list's closing paragraph, the engine-change bullet for the exposures, the disagreements table, the question list's opening paragraph, the serving and grid groups in that list, and the Not covered section. The Not covered bullet on the coalesced wake-up is rewritten rather than deleted, because the measurement changes what it says rather than removing the caveat.

## Method

The real `subsequence.sequencer.Sequencer` with `_jitter_log`, driven exactly as `benchmarks/clock_jitter.py` drives it (`benchmarks/clock_jitter.py:36-82`): 120 BPM with pulses of 20.833 ms, spin-wait on, and `output_device_name="SUPERINTENDENT_NO_SUCH_DEVICE"` so `select_output_device` logs the miss and returns nothing rather than opening a port. No MIDI port is opened and no socket is bound. The first block is 16 bars, 1536 pulses per run; the two paired-baseline blocks are 8 bars, 768 pulses per run, with a fresh no-adapter baseline immediately before every arm so each comparison is contemporaneous.

The transport is deliberately absent. #1926 established that the cost is per wake-up of the clock loop and independent of the transport — OSC on the loop, OSC on a thread, a WebSocket link on the loop or on a thread and a TCP link on a thread all landed within noise of each other — so what varies between arms here is the crossing rule alone, with an identical arrival process in each. A producer thread stands in for the link thread and each applied message is one dict write, standing in for a `composition.data` write: on the clock loop in the crossing arms, on the producer thread itself in the off-loop arm. Wake-ups are counted in the process: one per `call_soon_threadsafe` callback that ran, and none in the off-loop arm by construction.

Machine: the development workstation, Intel i7-9700K, 8 cores, Linux 6.8, Python 3.13.11 in a scratchpad venv (#1926's block was Python 3.12.3 on the same machine). Single runs per arm per pass; indicative, not a house benchmark. Load average is recorded before and after every run: 0.35 to 1.24 across the first block, 0.53 to 1.12 across the read-batching block, 0.37 to 0.64 across the off-loop block.

**A second pass of the first matrix is discarded and is reported here rather than dropped.** It ran while other work on the shared workstation took the load average from 1.2 to 8.8, and its own no-adapter baseline degraded to p99 3.27 ms with 189 pulses over 1 ms in 1536 — so the control says the machine, not the crossing rule, is what that pass measured. Every arm in it is unusable and none of its numbers appear above. This is why the paired-baseline design was used for the two later blocks.

Prototypes, not house style: `crossing_bench.py`, `crossing_bench2.py`, `crossing_bench3.py`, `run_matrix.sh`, `run_focus.sh` and `run_direct.sh`, with raw results in `results.jsonl`, `results_focus.jsonl` and `results_direct.jsonl`, under the scratchpad directory for this point. Every run recorded is in those files; nothing measured is unreported.

## Hardware-gated

- **The headless server's occupied ports.** Whether 8090, 8085 or 80 is already bound on the machine the service will run on has not been checked, because that machine is not the one this ran on. On the development workstation today 80 is bound and 8085, 8090 and 9005 are free (`ss -ltn`). This is a one-command check when the server is to hand and it is noted on #2020.
- **The crossing cost on the real server.** Every figure above is the workstation. #2008 already exists for re-measuring the adapter's on-loop cost on the headless server with the transport actually chosen and with whichever crossing rule Simon takes; the read-batching correction and the off-loop arm are additions to it.
- **The tap-to-face figure over the real LAN.** #2002, unchanged: it needs a second host running the service.

Nothing here needs the iiyama panel.

## Not covered

- **A real transport under the read-batching arm.** Those rows model the link thread queueing a whole socket read and crossing once, with a producer thread standing in for the socket. Whether a real `websockets` reader on its own loop delivers a burst in one read often enough to realise the figures was not measured; #1926 established that the transport does not change the per-wake-up cost, but how many wake-ups a real reader produces per burst is a property of the reader, and it belongs with #2008.
- **The off-loop option's effect on ordering was argued, not measured.** The clock cost of option C is measured; its cost to #1925 — the loss of a total order between a panel write and the algorithm's writes inside the rebuild, and of the single ordered outbound log — is read off #1925's stated invariant and #1914's iteration-race row, not demonstrated. If Simon leans towards C, the demonstration belongs with a revision of #1925 rather than here.
- **Whether the beat drain or the reschedule drain binds first for a given pattern.** Under option A the `ack` arrives at whichever of the two hooks comes first, so a pattern whose cycle is shorter than a beat is acknowledged sooner. The one-beat bound quoted is the worst case across patterns and is what the short list uses; the per-pattern distribution was not worked out because it does not change the decision.

## Provenance

Files read in the working trees on 2026-09-03: `/mnt/dev/Apps/2026-02 Sequencer/subsequence/sequencer.py` (350-360, 395-420, 460-470, 755-830, 1415-1435, 1790-1835, and greps for `pulse_count`, `_output_devices`, `_max_device_latency_ms`), `subsequence/composition.py` (1790-1810, 3442-3446, 3895-3905, 5955-5995, and greps for `_drum_note_map`, `_default_grid`, `_energy_gated`), `subsequence/pattern.py` (125-140), `subsequence/pattern_builder.py` (196-202), `subsequence/midi_utils.py` (150-156), `subsequence/osc.py` (44-49), `subsequence/web_ui.py` (39-43), `benchmarks/clock_jitter.py` (36-82); `/mnt/dev/Apps/Subsample/subsample/config.py` (538-542, 566-570); `/mnt/dev/Apps/SDR Scanner/substation/config.py` (596-600); `/mnt/dev/Apps/Supervisor/serve.py` (1-10).

Subroutine read: #2018 in full and in its pre-amendment copy, #1925, #1926, #1914, #1929, #1963, #1968, #1465, #2019, #2020, #2021, and the specification for this research.

URLs: https://www.iana.org/assignments/service-names-port-numbers/service-names-port-numbers.csv (the rows for 8060-8100, 9005; fetched 2026-09-03 into this point's scratchpad); https://www.rfc-editor.org/rfc/rfc6335.txt (sections 6 and 8.1.2, fetched 2026-09-03); https://support.atlassian.com/atlassian-knowledge-base/kb/ports-used-by-atlassian-data-center-applications/ (Bamboo 8085, Confluence 8090, Jira 8080, Crowd 8095; reached by the 301 from the older `confluence.atlassian.com/kb/` URL); https://www.nngroup.com/articles/response-times-3-important-limits/ (Jakob Nielsen, 1993, the 0.1 s limit).

Subroutine items written: #2021, #2019 and #2020 filed as `needs_input` spikes in project `superintendent` and revised after verification; a comment on #1968 and a comment on #2018 recording what each needs to be read with; #2018's body amended.
