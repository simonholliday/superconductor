A real grid-bearing pattern rebuilding on the live clock loop leaves `benchmarks/clock_jitter.py`'s median and p95 at baseline in all eighteen paired runs across 16 by 8 with 64 notes, 16 by 8 full and 64 by 16 with 512 notes at lookaheads of 1/24, 1/4 and 1 beat — but that figure is wake-up lateness for the *next* pulse, so it cannot see in-pulse cost by construction, and sixteen of the eighteen runs put their whole maximum on a rebuild-adjacent pulse. The measurement the lookahead decision needs is the rebuild pulse's own dispatch: the loop rebuilds before it dispatches (`sequencer.py:1484-1485`), so every rebuild delays that pulse's own MIDI by the whole block, on every cycle rather than only on an overrun. Measured, that is a median 0.48 to 2.48 ms under a quarter-beat lookahead and 0.75 to 2.45 ms under one beat, up to 6.41 ms at 512 notes on a quieter machine, against 0.02 ms on every other pulse — and **zero under a one-pulse lookahead, whose rebuild pulse dispatched no events at all**, because a cycle's last pulse can carry a step only on a one-pulse step grid. The block itself costs 0.33 to 2.07 ms at 64 notes, 0.54 to 3.41 ms at 128 and 2.07 to 13.07 ms at 512, three to twenty times #1915's figure because that timed only `on_reschedule()` and timed it in a tight loop at full turbo; the largest single term is the CPU frequency state, which leaves a mostly-sleeping clock process near 800 MHz and makes the same rebuild five to six times dearer. Headroom runs out between 512 and 1024 notes per rebuild pulse at 120 BPM — about 800 at the frequency floor, about 540 at 180 BPM — identically under every lookahead, and patterns sharing a length and lookahead rebuild in one block, so that is a budget for the whole composition's rebuild pulse rather than per pattern. Recommended: `reschedule_lookahead=1/24`, now on two grounds rather than one.

**Question.** What does a real grid-bearing pattern rebuilding on Subsequence's composition loop do to the timing of the music, and at which grid size does a one-pulse reschedule lookahead stop having headroom?

This is the orphan named in #1915 ("Wall-clock effect of the rebuild on `benchmarks/clock_jitter.py`'s figure ... was not measured"), repeated in #1914, and stated plainly in #2018 ("the wall-clock effect of the rebuild on the jitter benchmark was not measured by any point"). #1929 measured the co-located service against the stock benchmark, which drives a bare `Sequencer` with no patterns; #1926's second measurement block scheduled a real `Pattern` but an empty one, so no rebuild work had ever been on the loop while the jitter log was running.

The benchmark's figure turned out to be the wrong yardstick on its own, so this document reports three quantities and keeps them apart: what `clock_jitter.py` measures, what it measures on the pulses that carry a rebuild, and how late the rebuild pulse's own MIDI leaves the sequencer.

## What the jitter benchmark can and cannot see

`benchmarks/clock_jitter.py` passes a list to the sequencer as `_jitter_log` and reports its percentiles (`clock_jitter.py:36-82`). The sequencer appends to that list in exactly one place: after a pulse has been dispatched, after the loop has slept to the *next* pulse's instant, as `time.perf_counter() - next_pulse_time` (`sequencer.py:1567`, inside the non-render branch of `_run_loop_internal_clock`). It is **wake-up lateness for the pulse about to be processed**, not dispatch lateness for the pulse just processed.

Two consequences follow, and both matter here.

- **Work that fits inside a pulse interval is invisible to it by construction.** A rebuild that costs 6 ms at the head of a 20.833 ms pulse simply leaves a 14.8 ms sleep instead of a 20.8 ms one, and the next wake-up is exactly on time. The figure only moves when the work overruns the interval. Reading an unmoved benchmark figure as "the rebuild costs the music nothing" is reading the absence of an overrun as the absence of a delay.
- **Its percentiles are pooled over pulses that mostly contain no rebuild.** A four-beat pattern rebuilds sixteen times in a 16-bar run of 1536 pulses. The p95 covers 77 pulses and the p99 fifteen, so neither can be moved by sixteen samples however late they are.

So the benchmark answers "does a grid rebuild disturb the clock's own cadence" — and the answer is no. It does not answer "does a grid rebuild delay notes", which is the question the lookahead decision actually turns on. That one needed a second measurement.

## How it was measured

**The clock figure**, by `clock_jitter.py`'s own method as #1926's harness drives it: the real `subsequence.sequencer.Sequencer` with a `_jitter_log`, 16 bars at 120 BPM (1536 pulses of 20.833 ms), spin-wait on, and `output_device_name` set to a name that matches nothing, which `select_output_device` turns into a logged `(None, None)` with no port opened (`midi_utils.py:334-377`; the no-match branch is at 372-377). No audio or MIDI device was opened and nothing was written under `/mnt/dev`.

The difference from every earlier run is the pattern. A real `Composition` is constructed, a real `@composition.pattern` decorator declares the grid pattern with its `drum_note_map` and its `reschedule_lookahead`, and `_build_pattern_from_pending` produces the same `_DecoratorPattern` that `Composition._run()` would (`composition.py:5838-5845`); the pattern is then handed to the composition's own sequencer with `schedule_pattern_repeating` (`sequencer.py:1123-1150`). The builder reads a StepGrid-shaped sparse cell map out of `composition.data` — row name to `{step index: {"v": velocity}}`, the v1 cell schema of #1914 — and calls `p.sequence(indices, voice, velocities=..., grid=n)` once per row (`pattern_builder.py:1195-1254`), with `p.set_length(steps * SIXTEENTH)` first. So the loop pays the whole per-cycle cost: `_DecoratorPattern.on_reschedule()` re-running the builder (`composition.py:6118-6124`) and `Sequencer.schedule_pattern()` turning every placed note into a `note_on` and a `note_off` on the event heap (`sequencer.py:957-1050`).

**The dispatch figure**, by wrapping `Sequencer._dispatch_with_compensation` in the same harness and comparing the wall clock of each pulse's first send with `start_time + pulse * seconds_per_pulse`, recording which message types were dispatched on each pulse. With one output device the compensation offset is zero (`_send_offset_seconds`, `sequencer.py:1948-1967`) so the send is synchronous and the timestamp is the send.

Three grid shapes, each at three lookaheads: 16 by 8 with 64 notes (every other step of every row), 16 by 8 full with 128 notes, and 64 by 16 with 512 notes; `reschedule_lookahead` of 1/24 beat (one pulse), 1/4 beat (six pulses) and the default 1 beat. A 16-step sixteenth-note pattern is four beats long and rebuilds sixteen times in a 16-bar run; a 64-step one is sixteen beats long, so the big grid was run for 32 or 64 bars.

**The workstation is shared with other work**, and a first pass was spoiled by a background test suite that took the load average from 0.3 to 8.4 mid-matrix. Every clock-figure row below is therefore paired: a baseline run of the same length was taken immediately before each grid run, and each pair waited for the one-minute load average to fall below 1.2 first. Loads at the start of every accepted run were between 0.29 and 1.14. The harness's own baseline reproduces the stock benchmark exactly (stock at 120 BPM in the same session: median 0.002 ms, p95 0.002 ms, p99 0.015 ms, maximum 0.048 ms).

Machine: the development workstation, Intel Core i7-9700K, 8 cores, Ubuntu on kernel 6.8.0-138, Python 3.12.3 in `~/venvs/subsequence-cookbook`, working tree at `v0.6.6-2-g95c14a7`. `intel_pstate` is in **active mode with HWP**, `scaling_driver` `intel_pstate`, governor `powersave`, `energy_performance_preference` `balance_performance`, range 800 to 4900 MHz, turbo enabled. Indicative only; the headless server is a different and slower machine.

## The clock's own cadence is unmoved

Eighteen runs, nine configurations twice, each against the baseline taken immediately before it. Figures are jitter in milliseconds and the count of pulses over 1 ms out of 1536.

| Grid | Lookahead | Repeat | Baseline: median / p95 / p99 / max, pulses over 1 ms | With the grid pattern: median / p95 / p99 / max, pulses over 1 ms |
| --- | --- | --- | --- | --- |
| 16 by 8, 64 notes | 1/24 | first | 0.002 / 0.003 / 0.003 / 0.133 ms, 0 | 0.001 / 0.004 / 0.018 / 0.643 ms, 0 |
| 16 by 8, 64 notes | 1/4 | first | 0.002 / 0.003 / 0.003 / 0.014 ms, 0 | 0.002 / 0.002 / 0.159 / 0.731 ms, 0 |
| 16 by 8, 64 notes | 1 beat | first | 0.002 / 0.002 / 0.003 / 0.013 ms, 0 | 0.002 / 0.002 / 0.152 / 0.980 ms, 0 |
| 16 by 8 full, 128 notes | 1/24 | first | 0.002 / 0.003 / 0.003 / 0.011 ms, 0 | 0.002 / 0.007 / 0.015 / 0.436 ms, 0 |
| 16 by 8 full, 128 notes | 1/4 | first | 0.002 / 0.002 / 0.003 / 0.014 ms, 0 | 0.002 / 0.002 / 0.010 / 0.313 ms, 0 |
| 16 by 8 full, 128 notes | 1 beat | first | 0.002 / 0.002 / 0.006 / 0.015 ms, 0 | 0.002 / 0.002 / 0.003 / 0.270 ms, 0 |
| 64 by 16, 512 notes | 1/24 | first | 0.002 / 0.003 / 0.003 / 0.012 ms, 0 | 0.002 / 0.002 / 0.003 / 0.583 ms, 0 |
| 64 by 16, 512 notes | 1/4 | first | 0.002 / 0.002 / 0.003 / 0.003 ms, 0 | 0.002 / 0.002 / 0.003 / 0.508 ms, 0 |
| 64 by 16, 512 notes | 1 beat | first | 0.002 / 0.002 / 0.003 / 0.017 ms, 0 | 0.002 / 0.005 / 0.048 / 0.672 ms, 0 |
| 16 by 8, 64 notes | 1/24 | second | 0.002 / 0.002 / 0.003 / 0.008 ms, 0 | 0.002 / 0.002 / 0.008 / 1.595 ms, 1 |
| 16 by 8, 64 notes | 1/4 | second | 0.002 / 0.002 / 0.003 / 0.016 ms, 0 | 0.002 / 0.002 / 0.419 / 1.076 ms, 2 |
| 16 by 8, 64 notes | 1 beat | second | 0.002 / 0.003 / 0.003 / 0.012 ms, 0 | 0.002 / 0.002 / 0.184 / 0.914 ms, 0 |
| 16 by 8 full, 128 notes | 1/24 | second | 0.002 / 0.002 / 0.003 / 0.014 ms, 0 | 0.002 / 0.002 / 0.030 / 0.320 ms, 0 |
| 16 by 8 full, 128 notes | 1/4 | second | 0.002 / 0.003 / 0.005 / 0.025 ms, 0 | 0.002 / 0.002 / 0.051 / 0.399 ms, 0 |
| 16 by 8 full, 128 notes | 1 beat | second | 0.002 / 0.003 / 0.003 / 0.015 ms, 0 | 0.002 / 0.007 / 0.019 / 0.199 ms, 0 |
| 64 by 16, 512 notes | 1/24 | second | 0.002 / 0.006 / 0.009 / 0.078 ms, 0 | 0.002 / 0.017 / 0.107 / 0.723 ms, 0 |
| 64 by 16, 512 notes | 1/4 | second | 0.002 / 0.003 / 0.003 / 0.021 ms, 0 | 0.002 / 0.003 / 0.026 / 0.844 ms, 0 |
| 64 by 16, 512 notes | 1 beat | second | 0.002 / 0.002 / 0.004 / 2.549 ms, 1 | 0.002 / 0.003 / 0.043 / 0.190 ms, 0 |

Reading it precisely, because the pooled figures are not all at baseline. **The median never moves** — 0.002 ms with a grid pattern rebuilding, 0.002 ms without, in every one of the eighteen pairs — and **the p95 is at the baseline too** (grid runs 0.002 to 0.017 ms, baselines 0.002 to 0.006 ms). **The p99 does move**, from at most 0.009 ms on a baseline to at most 0.419 ms with a grid: a rise of up to forty-five times, which is the first sign of the fifteen rebuild pulses the p99 can just reach. The maximum rises from at most 0.133 ms (one baseline reached 2.549 ms under a load transient) to at most 1.595 ms. **Sixteen of the eighteen grid runs put no pulse past 1 ms in 1536; two put one and two.** One baseline put one.

The big grid rebuilds only four times in a 16-bar run, so it was also run for 64 bars, sixteen rebuilds each:

| Grid | Lookahead | Rebuilds in the run | Baseline: median / p95 / p99 / max, over 1 ms | With the grid: median / p95 / p99 / max, over 1 ms |
| --- | --- | --- | --- | --- |
| 64 by 16, 512 notes, 64 bars | 1/24 | 16 | 0.002 / 0.003 / 0.003 / 0.030 ms, 0 of 6144 | 0.002 / 0.002 / 0.028 / 0.842 ms, 0 of 6144 |
| 64 by 16, 512 notes, 64 bars | 1/4 | 16 | 0.002 / 0.003 / 0.011 / 0.026 ms, 0 of 6144 | 0.002 / 0.010 / 0.065 / 1.077 ms, 1 of 6144 |
| 64 by 16, 512 notes, 64 bars | 1 beat | 16 | 0.002 / 0.003 / 0.004 / 0.274 ms, 0 of 6144 | 0.002 / 0.012 / 0.065 / 0.597 ms, 0 of 6144 |

## Conditioned on the rebuild, the picture changes

The harness records the jitter sample belonging to each rebuild, which is the wake-up lateness of the pulse *after* the one that carried the block. Conditioned on that, the same eighteen runs read very differently from their pooled percentiles.

**In sixteen of the eighteen grid runs the run's whole maximum falls on a rebuild-adjacent pulse.** The two exceptions are the 16 by 8, 64-note, one-pulse run of the second pass, whose 1.595 ms maximum has no rebuild near it — the only over-a-millisecond pulse in the primary matrix that is honest machine noise — and the 64 by 16 one-beat run of the second pass, whose maximum is 0.190 ms.

In five of the six 16 by 8, 64-note runs the *median* rebuild-adjacent sample is 0.490 to 0.680 ms, against a pooled median of 0.002 ms in every one of them — two to three hundred times the pooled figure, on more than half the rebuilds in the run — and 0.155 ms in the sixth. The larger grids do not show it consistently (16 by 8 full: medians 0.002 to 0.122 ms; 64 by 16: 0.001 to 0.660 ms).

That ordering is the wrong way round for a cost that scales with the grid, and it is not the block overrunning: a two-millisecond block cannot overrun a 20.833 ms pulse. The revision's own matrix instrumented the sleep arithmetic to find out what it is, recording for every pulse how late the loop was when it went to sleep and what the epoll rounding predicts of the wake-up from there — the loop sleeps to within a millisecond of the target and spins the rest (`sequencer.py:1553-1564`), and CPython rounds an epoll timeout up to a whole millisecond, so the prediction is arithmetic.

**Across 126 rebuilds in nine configurations the rounding predicts zero lateness every time, and the measurement disagrees on a quarter of them.** What it tracks is a narrow band in how long the rebuild pulse held the loop, and it is not monotone in that or in anything else measured here:

| Loop still busy, after that pulse's instant | Rebuild samples | Next wake-up more than 0.3 ms late | Range of the next wake-up |
| --- | --- | --- | --- |
| under 1 ms | 78 | 1 | 0.000 to 0.311 ms |
| 1 to 2 ms | 5 | 1 | 0.001 to 0.439 ms |
| **2 to 3 ms** | **31** | **30** | **0.002 to 1.464 ms** |
| 3 to 5 ms | 9 | 1 | 0.001 to 0.335 ms |
| over 5 ms | 3 | 0 | 0.000 to 0.036 ms |

A block that leaves the loop busy for two to three milliseconds into its pulse costs the next wake-up about 0.75 ms; one that leaves it busy for six milliseconds costs nothing. That is not the sleep arithmetic, it is not an overrun, and it is not monotone in anything measured here. The mechanism was not isolated and is left under Not covered. Its size is what matters for the decision below: **the wake-up lateness passes straight into the next pulse's dispatch**, and under a one-pulse lookahead that next pulse is the cycle's own downbeat. Measured there, the downbeat's first send was late by at most 0.84 ms, against 0.02 ms on an ordinary pulse. Under a quarter-beat or one-beat lookahead the same lateness lands on a pulse five or twenty-three pulses before the downbeat, which on a sixteenth grid carries nothing.

None of this is the number the lookahead decision needs, and it took a second measurement to get that.

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

## What the rebuild block actually costs

"The block" is everything from the `reschedule_pulse` emit (`sequencer.py:1804`) through `on_reschedule()` (`sequencer.py:1815`) to the end of `schedule_pattern()` (`sequencer.py:1823`) — all of it inline on the clock loop, all of it in front of that pulse's dispatch, and all of it inside one pulse's budget. Every rebuild of a single grid pattern from every 120 BPM run in the matrix is pooled here, including the deliberately oversized shapes and the runs that were taken to find the failure point.

| Notes placed per rebuild | Rebuilds sampled | Fastest | Median | 90th percentile | Slowest | Slowest as a share of the 20.833 ms pulse | Microseconds per note, fastest / slowest | Blocks over one pulse |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 64 | 68 | 0.33 ms | 1.67 ms | 1.97 ms | 2.07 ms | 10% | 5.2 / 32.3 | 0 |
| 128 | 85 | 0.54 ms | 1.05 ms | 3.23 ms | 3.41 ms | 16% | 4.2 / 26.7 | 0 |
| 512 | 111 | 2.07 ms | 6.01 ms | 6.82 ms | 13.07 ms | 63% | 4.0 / 25.5 | 0 |
| 1024 | 68 | 4.10 ms | 4.67 ms | 10.14 ms | 25.34 ms | 122% | 4.0 / 24.8 | 2 |
| 2048 | 68 | 8.03 ms | 10.76 ms | 38.92 ms | 46.87 ms | 225% | 3.9 / 22.9 | 12 |

The 1024- and 2048-note rows are a 64-step grid with 32 and 64 rows forced onto a four-beat cycle, run to find the failure point; they are far outside the first use-case. Both pool four runs of seventeen rebuilds each, at all three lookaheads, not the single run an earlier draft of this table used: at 2048 notes that matters, because the worst block actually measured is 46.87 ms rather than 31.66 ms, and the overruns are one, three and five of seventeen at lookaheads 1/24, 1/4 and one beat against three of seventeen in the fourth run. Those per-lookahead differences appear only at 2048 notes and nowhere inside the envelope; they are consistent with a longer lookahead leaving more of the previous cycle's events on the heap when 4096 new ones are pushed, but that was not isolated and is left under Not covered.

**This is several times #1915's figure, for two reasons, and the reasons matter more than the multiple.** #1915's run G reports a median of 104 to 105 µs for the 16 by 8 grid and 736 to 757 µs for the 64 by 16 one. The block's *fastest* sample is about three times each of those, and its slowest about twenty times. First, run G timed `pattern.on_reschedule()` and nothing else (`scratchpad/subsequence-grid/grid_prototype.py:235-238`), and the `schedule_pattern()` that follows it on the same pulse costs about as much again. Second, it timed it in a five-hundred-iteration tight loop, which keeps the core boosted and the caches warm. Re-running run G's own measurement today, on a machine that happened to stay boosted throughout, separates the two:

| Shape | Builder verb | Cadence | Notes | `on_reschedule` median / p95 | `schedule_pattern` median / p95 |
| --- | --- | --- | --- | --- | --- |
| 16 by 8, 64 notes | `hit_steps` | tight loop | 64 | 112 / 115 µs | 151 / 155 µs |
| 16 by 8, 64 notes | `hit_steps` | one call per 32 ms | 64 | 146 / 185 µs | 167 / 206 µs |
| 16 by 8, 64 notes | `sequence` | tight loop | 64 | 125 / 140 µs | 152 / 183 µs |
| 16 by 8 full | `hit_steps` | tight loop | 128 | 202 / 233 µs | 269 / 300 µs |
| 16 by 8 full | `sequence` | one call per 32 ms | 128 | 265 / 326 µs | 294 / 331 µs |
| 64 by 16 | `hit_steps` | tight loop | 512 | 770 / 809 µs | 1279 / 1368 µs |
| 64 by 16 | `sequence` | one call per 32 ms | 512 | 907 / 974 µs | 1347 / 1457 µs |

The tight-loop `hit_steps` rows reproduce run G's 104 to 105 µs and its 736 to 757 µs. The v1 cell schema's `sequence` with per-step velocities costs about 12% more than `hit_steps`, which is not the story. The story is the second column, never counted before, and what is *not* in this table: with the core boosted, moving from a tight loop to the real 32 ms cadence adds only 20 to 30%. An earlier pass of the same script on an idle machine put the same 32 ms rows at 300 to 816 µs and 1436 to 1472 µs — three to six times these. The difference between the two passes is not the cadence, it is which P-state the core was in, and that is the largest term in the whole measurement.

## The CPU frequency state is the largest single term

The per-rebuild costs are bimodal. Sampling the running core's clock immediately after each block (`/proc/self/stat`'s processor field, then that CPU's `scaling_cur_freq`) shows why:

| Grid | Rebuilds at or below 1.5 GHz | Block, median | Rebuilds at or above 4 GHz | Block, median |
| --- | --- | --- | --- | --- |
| 16 by 8, 64 notes | 5 | 1.87 ms | 8 | 0.38 ms |
| 16 by 8 full, 128 notes | 10 | 3.17 ms | 5 | 0.56 ms |

Three consecutive rebuilds from the middle of that first run, block cost against the frequency read at the end of each: 1692.6 µs at 900 MHz, 401.8 µs at 4000 MHz, 1871.3 µs at 800 MHz. The ratio, five to six, is the machine's own 800-to-4900 MHz range. The 512-note grid never sampled a frequency below 4.3 GHz in its own run: its block is long enough to raise the core during it, which is also why the smallest grid, not the largest, produced the only rebuild-adjacent pulse over a millisecond in the primary matrix.

The workstation runs `intel_pstate` in active mode **with HWP**, so the kernel is not choosing the P-state at all: "If the HWP feature has been enabled, `intel_pstate` relies on the processor to select P-states by itself, but still it can give hints to the processor's internal P-state selection logic" (https://www.kernel.org/doc/html/latest/admin-guide/pm/intel_pstate.html). Under the `powersave` governor the driver "will set the processor's Energy-Performance Preference (EPP) knob (if supported) or its Energy-Performance Bias (EPB) knob (otherwise) to whatever value it was previously set to via `sysfs`" — here `balance_performance` — and under `performance` it "will write 0 to the processor's Energy-Performance Preference (EPP) knob (if supported)... which means that the processor's internal P-state selection logic is expected to focus entirely on performance", with the available range "restricted to the upper boundary" (same page). A sequencer process that spins for at most 1 ms of every 20.833 ms pulse (`sequencer.py:465`, `1556-1564`) is exactly the workload such logic parks near the floor, and a 2 ms rebuild burst is over before anything reconsiders.

The practical consequence for `serving` and for whoever configures the headless server: **the frequency state is worth more than the grid size and far more than the lookahead.** Setting the governor to `performance` on the machine that runs the composition removes a factor of five to six from every rebuild. That is a change to the host rather than to any package, so it is asked as #2034 rather than decided here.

## The lookahead chooses which pulse pays, never whether it can pay

`_maybe_reschedule_patterns` is awaited inline from `_advance_pulse` on whichever pulse the lookahead selects (`sequencer.py:1484`, `1690-1833`; the lookahead is converted to pulses at `sequencer.py:885-906` and the next rebuild pulse set at `1821` and `1827`). The rebuild therefore always has exactly one pulse interval to complete in, whether the lookahead is one pulse, six or twenty-four. **The lookahead cannot buy the rebuild more time**; it chooses the pulse, and with it — as the dispatch table shows — whether that pulse has notes on it.

The measurements agree: at every grid size inside the envelope the three lookaheads produce the same block cost within the run-to-run scatter of the frequency state, and the same jitter distribution.

When a block does exceed a pulse, the overrun appears as exactly one late pulse and does not accumulate — the inner `while current_time >= next_pulse_time` fires every overdue pulse back to back and then returns to the absolute schedule (`sequencer.py:1507-1535`), which is the non-accumulating drift the stock benchmark reports. Fourteen overruns were measured across the oversized shapes, and each produced a single late pulse of the block minus one pulse interval plus 0.4 to 1.0 ms: 21.25 ms gave 0.83 ms, 22.42 ms gave 2.02 ms, 25.34 ms gave 4.99 ms, 27.32 ms gave 6.71 ms, 31.66 ms gave 11.25 ms, 39.94 ms gave 19.96 ms, 46.87 ms gave 26.80 ms. In every case the following pulses were back at 0.001 ms.

## Where the headroom runs out

The constraint is that the block must fit inside one pulse: 20.833 ms at 120 BPM, 13.889 ms at 180 BPM.

| Grid | Notes per rebuild | Worst measured block | Share of a 20.833 ms pulse | Blocks over one pulse |
| --- | --- | --- | --- | --- |
| 16 by 8, half filled (the first use-case) | 64 | 2.07 ms | 10% | 0 of 68 |
| 16 by 8, fully filled | 128 | 3.41 ms | 16% | 0 of 85 |
| 64 by 16, half filled | 512 | 13.07 ms | 63% | 0 of 111 |
| 64 by 32, half filled | 1024 | 25.34 ms | 122% | 2 of 68 |
| 64 by 64, half filled | 2048 | 46.87 ms | 225% | 12 of 68 |

**The answer: it stops having headroom between 512 and 1024 notes per rebuild at 120 BPM on this workstation.** Extrapolating from one constant — the per-note cost of the largest shape inside the envelope, 25.5 µs at the frequency floor and 4.0 µs at full clock — the ceiling is about 800 notes at the floor and about 5200 at full clock at 120 BPM, and about 540 and about 3500 at 180 BPM where the pulse is 13.889 ms. The same boundary applies to a quarter-beat lookahead and to the default one-beat lookahead, because the constraint is the pulse and not the lookahead.

For the first use-case, a 16 by 8 drum grid is at most 128 notes and consumed 3% to 16% of a pulse: a margin of six to thirty times.

## Several grid patterns rebuild in one block

Patterns of the same length and lookahead all come due on the same pulse, and `_maybe_reschedule_patterns` rebuilds and requeues them one after another in a single pass (`sequencer.py:1799-1833`), so their costs add on that one pulse. Identical 16 by 8 fully-filled grids, one-pulse lookahead:

| Grid patterns sharing the loop | Notes built on one pulse | Whole block on that pulse, median / max | Baseline: median / p95 / p99 / max, over 1 ms | With the grids: median / p95 / p99 / max, over 1 ms |
| --- | --- | --- | --- | --- |
| 1 | 128 | 1.18 / 3.23 ms | 0.002 / 0.002 / 0.003 / 0.013 ms, 0 | 0.002 / 0.002 / 0.049 / 1.079 ms, 2 |
| 2 | 256 | 5.39 / 7.24 ms | 0.002 / 0.026 / 0.029 / 0.036 ms, 0 | 0.002 / 0.118 / 0.215 / 1.569 ms, 1 |
| 4 | 512 | 6.71 / 6.78 ms | 0.002 / 0.002 / 0.003 / 0.019 ms, 0 | 0.002 / 0.435 / 0.523 / 1.188 ms, 2 |

The block column is the median and the maximum of the *whole* block on each rebuild pulse, taken as the last of the k cumulative samples that pulse produces when k patterns rebuild on it. A verification of this document read the column as silently changing statistic between rows, on the grounds that pooling every cumulative sample gives medians of 3.25 ms and 5.37 ms for two and four patterns; those are medians over partial blocks as well as whole ones, and the column is right as it stands. It is worth saying only because the raw file holds both.

Four grid pages on one pulse is 512 notes and behaves like the single 512-note grid. The headroom figure above should therefore be read as a budget for the whole composition's rebuild pulse, not per pattern, which is what #2035 asks. Staggering lookaheads or lengths across patterns spreads the block across different pulses and costs nothing to do. An eight-pattern run was attempted and not obtained: the harness numbers its patterns from MIDI channel 10 and the eighth is channel 17, which `_resolve_channel` refuses (`composition.py:1591`). Eight grids on one pulse is therefore an extrapolation from the additivity above, not a measurement.

## An incidental clock finding at 130 and 180 BPM

While establishing baselines, the stock benchmark itself was run across tempi with no patterns at all. It is not flat. Eight bars per cell, spin-wait on, the same bare `Sequencer`, run twice: once on the event loop Subsequence gets by default and once on the same loop with a `SelectSelector`.

| Tempo | Default epoll loop: median / p95 / pulses over 1 ms of 768 | `SelectSelector` loop: median / p95 / over 1 ms |
| --- | --- | --- |
| 120 BPM | 0.0006 / 0.0016 ms, 0 | 0.0006 / 0.0022 ms, 0 |
| 130 BPM | 0.0008 / 1.0349 ms, 44 | 0.0006 / 0.0009 ms, 0 |
| 140 BPM | 0.0008 / 0.0023 ms, 0 | 0.0006 / 0.0008 ms, 0 |
| 150 BPM | 0.0017 / 0.0180 ms, 0 | 0.0006 / 0.0020 ms, 0 |
| 160 BPM | 0.0017 / 0.1357 ms, 0 | 0.0006 / 0.0019 ms, 0 |
| 180 BPM | 0.5660 / 1.3963 ms, 154 | 0.0006 / 0.0020 ms, 0 |

At 180 BPM the whole distribution moves: median 0.52 to 0.58 ms and 119 to 300 of every 768 pulses over a millisecond, reproduced in every session it has been run in, including this document's own 180 BPM baseline (median 0.556 ms, 300 of 1536) and with `--no-spin-wait` at 1.33 ms. At 130 BPM the median is session-dependent — 0.38 to 0.42 ms in one session, 0.0008 ms in another — but the tail is there in every one. A `SelectSelector` loop removes both outright.

The cause is the one #1926 identified for adapter wake-ups. CPython's `EpollSelector.select` rounds every timeout up because "epoll_wait() has a resolution of 1 millisecond, round away from zero to wait *at least* timeout seconds" (`timeout = math.ceil(timeout * 1e3) * 1e-3`, https://raw.githubusercontent.com/python/cpython/3.12/Lib/selectors.py, and identically in the interpreter in use at `/usr/lib/python3.12/selectors.py:457-459`), while `SelectSelector` passes the timeout through unrounded. At tempi whose pulse interval leaves the loop asking for a sleep just over a millisecond boundary the rounding costs a whole millisecond; why those tempi and not others was not worked out.

This is a property of the clock at particular tempi, present with no patterns and no adapter, so it does not touch the grid conclusion — the 180 BPM runs with a grid pattern were indistinguishable from the 180 BPM baseline (median 0.557 against 0.556; 314 pulses over 1 ms against 300). It belongs with #1974, which already asks whether a `SelectSelector` loop or a widened spin margin is acceptable in Subsequence: the answer now has a second reason to matter, and it is not about Superintendent at all.

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

## Not covered

- **The headless server.** Everything here is the development workstation. The server is slower, and its own frequency behaviour — the largest term measured here — is unknown; #2008 already asks for the adapter's on-loop cost to be re-measured there and this belongs in the same pass.
- **The mechanism of the wake-up lateness after a rebuild.** When a rebuild leaves the loop busy two to three milliseconds into its pulse, the next wake-up is 0.6 to 1.5 ms late in thirty of thirty-one samples; outside that band, in ninety-five samples, it is late three times. The epoll rounding predicts zero lateness in all 126, so the sleep arithmetic does not explain it, and it is not monotone in the block cost, the frequency or the margin. It matters as up to 0.84 ms on the downbeat under the recommended lookahead, and #2034 would move most rebuilds out of the band by making them faster.
- **The real MIDI write.** No port was opened, so `_send_midi` returns without doing anything for every event (`sequencer.py:2027-2035`). The rtmidi write cost falls on the dispatch pulse, and it therefore adds to the displacement measured above rather than to the rebuild block; a rig-accurate total for a 512-note cycle is not in these figures.
- **What the displacement sounds like.** The dispatch lateness is measured, not judged. Whether 2 to 6 ms of flam on a beat's note-ons is audible on Simon's rig is a listening question, and the recommendation does not rest on it: A displaces nothing at all, so the question only arises under B or C.
- **The per-lookahead differences at 2048 notes.** Only outside the envelope, and consistent with a longer lookahead leaving more of the previous cycle's events on the heap when the next cycle's are pushed, but not isolated.
- **Eight grid patterns on one rebuild pulse.** Attempted and lost to a harness limit (`composition.py:1591`); the additivity below 512 notes is measured, eight is extrapolation.
- **Why 130 and 180 BPM and not other tempi.** The `SelectSelector` comparison localises it to the epoll timeout rounding; the tempo dependence was not worked out.

## Hardware-gated

Nothing here needs the iiyama panel or a graphical host. Three things need a machine that is not this one:

- Re-running `grid_jitter_bench.py` and `dispatch_probe.py` on the headless Ubuntu server to replace the workstation figures, recording that machine's `scaling_driver`, governor, `energy_performance_preference` and frequency range, since the frequency state is the largest term in the rebuild cost. Same trip as #2008.
- Repeating the matrix on a Raspberry Pi if a composition is ever run on one; the per-note cost and the frequency behaviour will both differ.
- Confirming the 130 and 180 BPM clock behaviour on the headless server, since it was measured only on the workstation and is a property of the stock clock with no patterns scheduled.

## Provenance

Working tree `/mnt/dev/Apps/2026-02 Sequencer/` at `v0.6.6-2-g95c14a7` (commit `95c14a7`, 2026-08-28). Read this session: `subsequence/sequencer.py` (460-470, 885-930, 957-1050, 1123-1160, 1470-1580, 1690-1720, 1780-1836, 1840-1900, 1948-2010, 2020-2040), `subsequence/composition.py` (1588-1594, 6112-6132), `subsequence/midi_utils.py` (330-380), `subsequence/pattern.py` (100-135), `subsequence/event_emitter.py` (60-115), `benchmarks/clock_jitter.py` (30-90), `/usr/lib/python3.12/selectors.py` (400-460). Subroutine read this session: #1915 in full, #1943 in full, #2018's timing, conflict-policy and playhead sections.

Machine: Intel Core i7-9700K, 8 cores, kernel 6.8.0-138, `intel_pstate` active with HWP, `scaling_driver` `intel_pstate`, governor `powersave`, `energy_performance_preference` `balance_performance`, 800 to 4900 MHz, turbo enabled; Python 3.12.3 in `~/venvs/subsequence-cookbook`.

Prototypes and raw results (research only, not house style), all under `/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad/`:

- `subsequence-grid/gap11/` — `grid_jitter_bench.py` (the clock harness), `offline_cost.py` (the reproduction of #1915's run G and its extensions), `selector_probe.py`, `table.py`, and runners `run_matrix.sh`, `run_paired.sh`, `run_supp.sh`, `run_final.sh`, `run_overrun.sh`, `run_downbeat.sh`, `run_multi.sh`; raw results in `results/` — `passA.jsonl` (the load-spoiled first pass, kept for the record), `passB.jsonl` and `passC.jsonl` (the paired primary matrix), `supp.jsonl`, `final.jsonl`, `overrun.jsonl`, `downbeat.jsonl`, `multi.jsonl`, and `offline_cost.txt` and `selector_probe.txt` re-run and retained today, the earlier passes of those two having been printed to a terminal and lost.
- `subsequence-grid-gap-1-1/rev2/` — `dispatch_probe.py` (the dispatch-lateness and wake-model probe), `tempo_probe.py`, `run_matrix.sh`, and `results/disp2.jsonl` and `results/tempo_probe.txt`. `subsequence-grid-gap-1-1/dispatch_lateness.py` and `rev/dispatch_lateness2.py` with `rev/disp.jsonl` are the two earlier dispatch passes quoted for corroboration.
- `subsequence-grid/grid_prototype.py` — #1915's own prototype, read for what its run G timed.

URLs: https://raw.githubusercontent.com/python/cpython/3.12/Lib/selectors.py, https://www.kernel.org/doc/html/latest/admin-guide/pm/intel_pstate.html.

Questions for Simon raised by this point are filed as #2034 (the frequency governor on the composition machine), #2035 (a rebuild-pulse budget of about 500 notes) and #2036 (dispatching a pulse's events before rebuilding). #1943 remains the lookahead question and is answered by the short list above.
