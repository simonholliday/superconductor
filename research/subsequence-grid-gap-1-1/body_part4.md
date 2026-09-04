
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
