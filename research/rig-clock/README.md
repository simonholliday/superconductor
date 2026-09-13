# Timing the rig's rebuilds and the stock clock

**Measured 2026-09-13** for Subroutine #2034, #2035 and #2036 (#2045, brought forward). The conclusions and every table are in **#2532**. Two defects it found were filed with Subsequence as **#2533** (the stock clock is late at some tempos) and **#2534** (a note on a rebuild pulse is sent after the rebuild).

**What these numbers are for:** they describe one development rig. Superconductor runs on whatever hardware its users have, so nothing here is a budget, a default or a requirement (#2049). The clock finding is reported as a mechanism for Subsequence to verify, not as a rule taken from one machine's figures.

Raw per-pulse results stay on the machine they were taken on. They are not in this repository.

## The scripts

None of them change a file in either repository. Subsequence's `Sequencer` is patched in memory, and everything is written to a path you give.

| script | what it does |
| --- | --- |
| `measure_launcher.py` | Runs a composition (by default `compositions/drm1_grid.py`) with each pulse's rebuild and first MIDI send timed. Tempo, MIDI port, duration and output path come from `MEASURE_*` environment variables. Records stay in memory until `play()` returns; nothing is written from the clock loop. |
| `measure_sampler.py` | A separate process that samples which CPU a process's main thread is on, and that CPU's frequency, from `/proc` and `/sys`. |
| `measure_analyse.py` | Summarises a launcher run, optionally with its sampler file: rebuild cost by patterns due, how late pulses were entered, how late the first sends were, and CPU state near rebuilds. |
| `clock_sweep.py` | Runs the stock clock as `benchmarks/clock_jitter.py` does, for a list of tempos or levers (`180:2` for a 2 ms spin margin, `180:1:select` for a `SelectSelector` loop), keeping raw per-pulse lateness. `SWEEP_BARS` sets the length. |
| `sleep_probe.py` | Times the `asyncio.sleep` before each pulse against what was asked, which is what showed the oversleep. |
| `measure_transport.py` | Reads the rig's transport, optionally sets tempo and pause, and counts beats for 3 s. A pause is confirmed by counting beats, never by reading the field (#2446). |
| `dryrun_composition.py` | A throwaway composition for proving the launcher before touching a rig. |

## Running them

**Stopping and restarting a rig follows #2446.** A second sequencer beside a playing rig spoils both. Send MIDI to a loopback port (`*Midi Through*` here) so nothing sounds, and set `PYTHONDONTWRITEBYTECODE=1` so no bytecode is written beside the sources.

```
MEASURE_BPM=180 MEASURE_PORT='*Midi Through*' MEASURE_SECONDS=180 \
MEASURE_OUT=/some/local/run-180.json MEASURE_SEQ="$(git -C <sequencer> log -1 --format=%h)" \
  python measure_launcher.py &
python measure_sampler.py $! /some/local/run-180-sampler.json 0.01

python measure_analyse.py run-180.json run-180-sampler.json --skip-seconds 15

SWEEP_BARS=4 python clock_sweep.py sweep.json $(seq 60 5 200)
python clock_sweep.py levers.json 130 130:2 130:1:select 180 180:2 180:1:select
python sleep_probe.py 125 130 140 180
```

**Measure the clock at several tempos, never 120 alone.** On the rig, 120 and 125 were clean while 130 and 180 were not.
