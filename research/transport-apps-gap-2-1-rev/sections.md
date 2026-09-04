# Sections to splice into design_body_rev.md

## BLOCK_J_TABLE

| Shape | Traffic | Messages | Wake-ups | Largest batch | P99 | Max | Pulses over 1 ms of 1536 | Crossing median | Crossing p99 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline, nothing in the process | none | 0 | 0 | n/a | 0.003, PLACEHOLDER ms | 0.024, PLACEHOLDER ms | 0, PLACEHOLDER | n/a | n/a |
| Per message | 25 Hz | 845 | 845 | n/a | 1.029 ms | 1.230 ms | 18 | 0.049 ms | 0.158 ms |
| Pending flag | 25 Hz | 845 | 845 | 1 | 0.947 ms | 1.236 ms | 9 | 0.061 ms | 0.098 ms |
| Batched at the socket read | 25 Hz | 845 | 845 | 1 | 0.991 ms | 1.116 ms | 11 | 0.085 ms | 0.285 ms |
| Off the loop, no crossing | 25 Hz | 839 | 0 | n/a | 0.106 ms | PLACEHOLDER | 0 | 0.0009 ms | 0.0018 ms |

Load 0.36 to 1.34, stamped per row. Nothing dropped.

Reading: at the paint rate the three crossing shapes are one shape. The largest batch is one under both
batching devices, the wake-up count equals the message count under all three, and the late-pulse counts
(18, 9, 11 of 1536) are inside the spread the same shape shows between blocks — #2025 measured the
no-device shape at 36 and 48 and the flag at 26, 34 and 35 on the same bench and the same machine. The
only shape that changes the paint rate's cost is the one that never touches the loop.

## BLOCK_K_TABLE

(fill from rows)

## TRADEOFF_TABLE

## SHORT_LIST

## RECOMMENDATION

## CHANGES_ELSEWHERE

## NOT_COVERED

## PROVENANCE
