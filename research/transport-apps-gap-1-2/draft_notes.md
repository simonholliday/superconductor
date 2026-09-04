# Draft notes (not the deliverable)

## Claims to settle with the data

1. Steady 5 / 25 / 50 Hz: msgs per wake-up == 1.000, batch_max == 1. Coalescing is a no-op.
2. Where does coalescing start to bite: 200 Hz? 500 Hz? Record msgs/wake-up there.
3. Back-to-back burst of 128: msgs/wake-up ~7-8, batch_max ~32-42. NOT one wake-up.
4. Burst jitter is cheaper than steady jitter at the same message count: cost is per
   disturbed pulse, not per wake-up.
5. Crossing latency: B per-message ~0.06 ms median; B coalesced ~0.17 ms median;
   A median ~250 ms, p99 ~496 ms, max ~500 ms at 120 BPM (one beat, exactly).
6. Levers: 2 ms spin margin and SelectSelector.

## Corrections to #2018 to state

- Coalescing row of the B column: the inferred claim is wrong on its mechanism and
  irrelevant at the rates it exists for.
- Measured clock cost row: add 25 Hz.
- Musical effect row: `benchmarks/clock_jitter.py:99` computes `mean_ms` and
  `:131-141` applies the rating bands to the MEAN, not the P99. The cell says the
  scale "rates a 2.0 ms P99 as Good".
- Not-covered bullet: replace; it is measured now and does not need #2008.

## Design consequences

- The envelope's `set` frame is one cell (`#2018` wire vocabulary), so a page-load
  seed or a bulk write is N frames. If bulk must cost one wake-up, the lever is a
  batched set frame, not adapter-side coalescing.
- The fallback's "held paint gesture beyond a rate ceiling": any ceiling that
  catches a 20-30 Hz paint gesture sits below the gesture rate, so it either never
  fires or turns the whole gesture into A.
