
## What this settles for the lookahead short list

#2018's short list for the lookahead has a row "Measured rebuild cost against that slack" reading "105 µs median for a 16-by-8 grid, half a percent of a pulse; but 736 to 757 µs median and 985 µs maximum for a 64-by-16 grid, which is four percent of a pulse and about five percent of the slack". The corrected row, taken from the loop rather than from an offline tight loop, is **0.33 to 2.07 ms for a 16 by 8 grid with 64 notes, 0.54 to 3.41 ms fully filled, and 2.07 to 13.07 ms for a 64 by 16 grid**, the range in each case being the CPU frequency state.

Two other things in that table need correcting. "Slack between the rebuild finishing and the cycle it built starting" — 20.8 ms under one pulse, 500 ms under one beat — is not a quantity the clock cares about, because the rebuild has one pulse interval under every lookahead. And "Floor for a step-count change" does not separate A from C: `_get_schedule_timing` refuses only a lookahead larger than the length (`sequencer.py:885-906`), so a quarter-beat lookahead admits a pattern one sixteenth step long exactly as a one-pulse lookahead does — which #2018's own table already says, giving "one step" for both A and C and "four sixteenth steps" only for B.

What separates the three is the tap window and the displacement measured above.

| | A. `reschedule_lookahead=1/24`, one pulse (recommended) | B. The default, one beat | C. A quarter beat, six pulses |
| --- | --- | --- | --- |
| Window in which a tap waits an extra cycle | one pulse: 20.8 ms at 120 BPM, in practice nothing | one beat: 500 ms, a quarter of a one-bar pattern | a quarter beat: 125 ms, the last cell |
| Where the rebuild block lands | the cycle's last pulse, which carries no note-on on any step grid coarser than one pulse per step | four sixteenth steps before the cycle, on a step | one sixteenth step before the cycle, on a step |
| Notes displaced by the block, measured | **none**: no events at all dispatched on the rebuild pulse, in all three grid shapes | 68, 136 and 64 note-ons late by a median 2.45, 0.75 and 2.43 ms; up to 6.41 ms on a quieter machine at 512 notes | the same note-ons late by a median 0.48, 0.72 and 2.48 ms |
| What the wake-up anomaly costs | the downbeat's own send, late by at most 0.84 ms and usually not at all | a pulse twenty-three before the downbeat, which carries nothing | a pulse five before the downbeat, which carries nothing |
| Whether the block fits inside its pulse | one pulse interval | one pulse interval | one pulse interval |
| Floor for a step-count change | one step | four sixteenth steps | one step |
| Effect on `clock_jitter.py`'s pooled figure | median and p95 at baseline, p99 up to 0.419 ms, at most two pulses over 1 ms in 1536 | the same, indistinguishable | the same, indistinguishable |
| Engine change | none; a composition-file setting | none | none |
| Safe against the form and harmony clocks | yes: those use the maximum of one beat and the pattern lookaheads | yes | yes |

**Recommended: A**, and now on two independent grounds where #2018 had one. The tap window is the first, as before. The second is new and is the one this point was asked to settle: A is the only setting of the three whose rebuild pulse carries nothing to delay, so the block — 0.35 ms or 6.19 ms, it makes no difference — displaces no note at all. Under B and C the same block lands on a step and pushes that step's note-ons late by the whole of it, on every cycle, which at 512 notes was 2.4 to 6.4 ms of flam on a beat boundary. A is not free: the wake-up anomaly puts its cost on the downbeat instead, but that is under a millisecond, intermittent, and an order smaller than what B and C displace every cycle. The thing #2018 named as A's risk ("it puts the rebuild on the cycle's own first pulse and delays that pulse's downbeat MIDI" — that is lookahead zero, and #1943's wording carries the same worry one pulse further out) is, one pulse out, precisely the reason to choose it.

Two caveats belong with the recommendation. It holds for any step grid coarser than one pulse per step, which is every grid the first use-case contemplates; a pattern gated short enough to place a note-off on the cycle's last pulse would put a note-off, not a note-on, into the displaced position, and a late note-off is far less audible. And A does not make a large grid safe: the headroom is identical under all three, and it runs out between 512 and 1024 notes on one rebuild pulse.

## The engine option this opens, and why v1 does not need it

The displacement exists because the loop rebuilds before it dispatches. Under #611 a neighbour's limitation is a change to make rather than a constraint to engineer around, so the order itself is on the table.

| | D. Leave the order as it is (recommended for v1) | E. Dispatch a pulse's own events before rebuilding the patterns due on it |
| --- | --- | --- |
| Change | none | swap `sequencer.py:1484` and `:1485`, with a guard |
| What it buys | nothing under A, where nothing is displaced | removes the displacement under every lookahead, every step grid and every gate |
| Correctness | as today | safe whenever `lookahead_pulses >= 1`, because the rebuilt cycle starts at `cycle_start_pulse >= pulse + 1` and `_process_pulse` only pops events at or before the current pulse (`sequencer.py:1852`); **not** safe at a lookahead of zero, which `_get_schedule_timing` accepts today, where it would push that cycle's first events a whole pulse late |
| Side effects | none | moves the moment a panel write drained at `reschedule_pulse` is applied relative to that pulse's own MIDI, which is exactly what #2021 turns on; and any other listener hung on the rebuild moves with it |
| Cost | none | an engine wave, tests, and a decision about lookahead zero |

**Recommended: D for v1.** With A adopted there is nothing to fix, and E buys its benefit only for settings the recommendation does not use. E is the lever if a pattern ever needs a larger lookahead, if a one-pulse step grid ever exists, or if the drain point moves for other reasons. It is filed as #2036.
