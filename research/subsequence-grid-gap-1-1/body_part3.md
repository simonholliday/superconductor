
## The rebuild pulse's own MIDI is late by the whole block

The rebuild does not run beside the pulse, it runs **in front of it**. `_advance_pulse` awaits `_maybe_reschedule_patterns(self.pulse_count)` and then `_process_pulse(self.pulse_count)` (`sequencer.py:1484-1485`), and `_process_pulse` sends each due event through `_dispatch_with_compensation` (`sequencer.py:1874`), which with one output device has a zero offset and calls `_send_midi` synchronously (`sequencer.py:1948-1967`, `1969-2000`). So whatever a rebuild costs is paid by that pulse's own notes, on every cycle, not only when the block overruns the pulse. That is the quantity the lookahead decision turns on, and it is the one `clock_jitter.py` cannot report.

Measured by wrapping the dispatcher: how late the first send of each pulse is against `start_time + pulse * seconds_per_pulse`. Nine configurations, one run each, 16 bars at 120 BPM for the 16-step grids (rebuild pulses 95, 90 and 72 of a 96-pulse cycle) and 32 bars for the 64-step one (383, 378 and 360 of 384).

| Grid | Lookahead | Rebuild lands on | Events dispatched on the rebuild pulses | Dispatch lateness there, median / p95 | Dispatch lateness on every other pulse, median / p95 | Block, median / p95 |
| --- | --- | --- | --- | --- | --- | --- |
| 16 by 8, 64 notes | 1/24 | pulse 95, no step | **none** | nothing to delay | 0.021 / 0.031 ms | 0.35 / 1.09 ms |
| 16 by 8, 64 notes | 1/4 | pulse 90, step 15 | 68 note_on | 0.48 / 1.25 ms | 0.021 / 0.033 ms | 0.35 / 1.09 ms |
| 16 by 8, 64 notes | 1 beat | pulse 72, step 12 | 68 note_on | 2.45 / 5.38 ms | 0.074 / 0.115 ms | 1.85 / 4.95 ms |
| 16 by 8 full, 128 notes | 1/24 | pulse 95, no step | **none** | nothing to delay | 0.022 / 0.082 ms | 0.59 / 3.28 ms |
| 16 by 8 full, 128 notes | 1/4 | pulse 90, step 15 | 136 note_on | 0.72 / 0.86 ms | 0.022 / 0.033 ms | 0.59 / 0.71 ms |
| 16 by 8 full, 128 notes | 1 beat | pulse 72, step 12 | 136 note_on | 0.75 / 3.95 ms | 0.022 / 0.082 ms | 0.61 / 3.33 ms |
| 64 by 16, 512 notes | 1/24 | pulse 383, no step | **none** | nothing to delay | 0.024 / 0.112 ms | 2.32 / 6.19 ms |
| 64 by 16, 512 notes | 1/4 | pulse 378, step 63 | 64 note_on | 2.48 / 3.24 ms | 0.023 / 0.074 ms | 2.31 / 3.03 ms |
| 64 by 16, 512 notes | 1 beat | pulse 360, step 60 | 64 note_on | 2.43 / 2.60 ms | 0.024 / 0.090 ms | 2.27 / 2.39 ms |

Two things are in that table.

**The displacement is the block, every cycle.** Lateness on a rebuild pulse tracks that run's block cost to within 0.15 to 0.6 ms of overhead, against 0.02 to 0.07 ms on the 528 to 1049 pulses that carry notes and no rebuild — a factor of twenty to a hundred. It is not an overrun phenomenon and it is not rare: it is every cycle. Two earlier passes with the same probe on a quieter machine, where far more rebuilds ran at the CPU frequency floor, give the same shape with larger numbers — a median 2.005 ms displacement at 64 notes under a one-beat lookahead and 6.410 ms at 512 notes — so 6 to 7 ms on a beat's note-ons is inside the measured range, not a worst case invented for the argument.

**Under a one-pulse lookahead there is nothing on that pulse to delay.** In all three shapes the rebuild pulse dispatched **no events at all**, so a 6.19 ms block displaced nothing. That is arithmetic, not luck. The rebuild fires at `cycle_start_pulse + length_pulses - lookahead_pulses` (`sequencer.py:1789-1790`, `1821`), so with a one-pulse lookahead it lands on the cycle's last pulse, `length_pulses - 1`. Steps land on multiples of `step_pulses`, and `step_pulses` divides `length_pulses` because a cycle is a whole number of steps; for it to divide `length_pulses - 1` as well it would have to divide 1, which means a step grid of one pulse per step — 96 steps to a 4/4 bar. **On any step grid coarser than that, the pulse before a cycle starts carries no note-on.** A quarter-beat lookahead is exactly one sixteenth step, and a one-beat lookahead exactly four, so both land squarely on a step and both pay. This is what #1915 anticipated from the code ("one pulse earlier there is normally no `note_on` on a 16th-note grid, only `note_off`s"); measured, with the builder's default gate there were no note-offs there either, because the last step's note ends on the next cycle's first pulse.

What A does pay, it pays on the downbeat and it is small. The wake-up anomaly above lands on the pulse after the rebuild, which under a one-pulse lookahead is the cycle's first pulse, and it passes into that pulse's dispatch: measured across the three one-pulse runs, the downbeat's first send was late by at most 0.84 ms — 0.832 ms at 128 notes and 0.837 ms at 512 — against 0.022 to 0.024 ms on an ordinary pulse, and on most cycles it was not late at all. Under a quarter-beat or one-beat lookahead that same lateness lands five or twenty-three pulses before the downbeat, where a sixteenth grid has nothing, and the block's own two to six milliseconds lands on a step instead.

So the risk #1943 names — "it moves the rebuild to one pulse before the downbeat" — is measured, and it comes out the other way: one pulse before the downbeat is the only place in the cycle where the block itself costs the music nothing, and what it does cost the downbeat is under a millisecond and intermittent, against two to six milliseconds on every cycle from the other two.
