
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
