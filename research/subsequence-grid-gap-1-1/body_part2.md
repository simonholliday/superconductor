
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
