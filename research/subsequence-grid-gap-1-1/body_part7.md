
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
