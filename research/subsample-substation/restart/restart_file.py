"""Prototype (not house style).  Substation band switch by constructing a fresh
RadioScanner in the same process, driven with the package's own FileDevice on
a synthesised IQ WAV so no SDR is needed.

Measures, on this machine:
  - interpreter start to imports done
  - RadioScanner.__init__
  - scan() called to first _process_samples call (device open, _setup_sdr,
    _precompute_fft_params, first slice)
  - scan() called to warm-up complete (NOISE_FLOOR_WARMUP_SLICES slices; with
    a file device the slices arrive as fast as they are processed, so this is
    processing-bound, not the 2 s a live device takes)
  - the switch: _signal_stream_end() on scanner A, await A.scan(), construct B,
    B.scan(), first slice of B, warm-up of B
  - mean _process_samples duration
  - which recording events fired when A was stopped with a recording active

Nothing under /mnt/dev is touched: PYTHONPATH points at the working tree,
recordings go under the scratchpad (restart_config.yaml).
"""
import time
T_START = time.perf_counter()
import os as _os

import asyncio
import collections
import datetime
import os
import logging
import pathlib
import struct
import sys
import wave

import numpy

sys.path.insert(0, "/mnt/dev/Apps/SDR Scanner")
import substation.config
import substation.scanner
import substation.constants

T_IMPORTS = time.perf_counter()

HERE = pathlib.Path(__file__).resolve().parent
IQ_KIND = os.environ.get("IQ_KIND", "tone")
WAV = HERE / {"fm": "iq_probe_fm.wav", "fm3": "iq_probe_fm3.wav"}.get(IQ_KIND, "iq_probe.wav")
CONFIG = HERE / "restart_config.yaml"
FS = 1_024_000
CENTER = 446.1e6
DURATION_S = 8.0
TONE_OFFSET_HZ = 446.14375e6 - CENTER      # PMR channel index 11
N_BEFORE_SWITCH = int(os.environ.get("N_BEFORE_SWITCH", "14"))                        # slices processed before we switch (warm-up is 10)

logging.basicConfig(level=logging.INFO, filename=str(HERE / "restart_file.log"), filemode="w",
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("restart_file")


def make_wav():
    if WAV.exists():
        return
    n = int(FS * DURATION_S)
    rng = numpy.random.default_rng(1)
    noise = 0.01 / numpy.sqrt(2) * (rng.standard_normal(n) + 1j * rng.standard_normal(n))
    if IQ_KIND == "fm":
        # NFM carrier on the channel, 1 kHz audio tone at 2.5 kHz deviation,
        # made with Substation's own test generator (tests/iq_generators.py).
        import tests.iq_generators
        sig = 0.1 * tests.iq_generators.generate_fm_iq(1000.0, 2500.0, FS, DURATION_S, carrier_offset=TONE_OFFSET_HZ)
    elif IQ_KIND == "fm3":
        # NFM carrier with a three-tone audio signal at 4 kHz peak deviation:
        # dense sidebands fill the 10.5 kHz channel the way voice does, and the
        # demodulated audio is not spectrally flat.
        t = numpy.arange(n) / FS
        m = (numpy.sin(2*numpy.pi*300*t) + numpy.sin(2*numpy.pi*700*t) + numpy.sin(2*numpy.pi*1500*t)) / 3.0
        phase = 2*numpy.pi*(TONE_OFFSET_HZ*t + numpy.cumsum(4000.0*m)/FS)
        sig = 0.5 * numpy.exp(1j*phase)
    else:
        t = numpy.arange(n) / FS
        sig = 0.1 * numpy.exp(2j * numpy.pi * TONE_OFFSET_HZ * t)
    iq = (noise + sig).astype(numpy.complex64)
    pcm = numpy.empty(2 * n, dtype=numpy.int16)
    pcm[0::2] = numpy.clip(iq.real * 32767, -32768, 32767).astype(numpy.int16)
    pcm[1::2] = numpy.clip(iq.imag * 32767, -32768, 32767).astype(numpy.int16)
    with wave.open(str(WAV), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(FS)
        w.writeframes(pcm.tobytes())


class Probe:
    """Instruments one RadioScanner instance without changing the package."""

    def __init__(self, config, band):
        self.band = band
        self.t = {}
        self.slices = 0
        self.proc_ms = []
        self.events = collections.Counter()
        self.t["construct_start"] = time.perf_counter()
        clock = None
        if os.environ.get("USE_VCLOCK"):
            # VirtualClock advances with sample position, so hold times and
            # recording timestamps follow the file rather than wall time.
            clock = substation.scanner.VirtualClock(datetime.datetime(2026, 9, 3, 12, 0, 0), float(FS))
        self.scan = substation.scanner.RadioScanner(
            config=config, band_name=band, device_type="file", clock=clock,
            device_kwargs={"file_path": str(WAV), "center_freq": CENTER},
        )
        self.t["construct_done"] = time.perf_counter()
        orig = self.scan._process_samples

        def wrapped(samples, loop):
            t0 = time.perf_counter()
            if self.slices == 0:
                self.t["first_slice"] = t0
            self.slices += 1
            orig(samples, loop)
            self.proc_ms.append((time.perf_counter() - t0) * 1000.0)

        self.scan._process_samples = wrapped

        def on_noise_floor(*a, **kw):
            if kw.get("warmup_complete") and "warm" not in self.t:
                self.t["warm"] = time.perf_counter()

        self.scan.on("noise_floor", on_noise_floor)
        for name in ("channel_state", "recording_started", "recording_saved", "recording_discarded"):
            self.scan.on(name, (lambda name: (lambda *a, **kw: self.events.update([name])))(name))

    async def run_until(self, n_slices):
        self.t["scan_called"] = time.perf_counter()
        task = asyncio.create_task(self.scan.scan())
        deadline = time.perf_counter() + 60
        while self.slices < n_slices and not task.done():
            if time.perf_counter() > deadline:
                raise RuntimeError("timeout waiting for slices")
            await asyncio.sleep(0.002)
        if task.done():
            raise RuntimeError(f"scan() ended early after {self.slices} slices; see restart_file.log")
        self.t["switch_requested"] = time.perf_counter()
        self.scan._signal_stream_end()          # on the loop thread, as the adapter's call_soon_threadsafe would land
        await task
        self.t["scan_returned"] = time.perf_counter()
        return task

    def report(self, t_ref):
        r = self.t
        ms = lambda a, b: (r[b] - r[a]) * 1000.0
        lines = [
            f"[{self.band}] RadioScanner.__init__: {ms('construct_start','construct_done'):.1f} ms",
            f"[{self.band}] scan() -> first _process_samples (device open, _setup_sdr, FFT params, first slice): {ms('scan_called','first_slice'):.1f} ms",
        ]
        if "warm" in r:
            lines.append(f"[{self.band}] scan() -> warm-up complete ({substation.constants.NOISE_FLOOR_WARMUP_SLICES} slices, file device at full speed): {ms('scan_called','warm'):.1f} ms")
        lines.append(f"[{self.band}] _process_samples: n={len(self.proc_ms)} mean {numpy.mean(self.proc_ms):.1f} ms max {numpy.max(self.proc_ms):.1f} ms")
        lines.append(f"[{self.band}] switch requested -> scan() returned (drain, cancel read, _cleanup_sdr incl. recordings): {ms('switch_requested','scan_returned'):.1f} ms")
        lines.append(f"[{self.band}] events: {dict(self.events)}")
        if t_ref is not None:
            lines.append(f"[{self.band}] previous switch requested -> this first slice: {(r['first_slice'] - t_ref) * 1000.0:.1f} ms" +
                         (f"; -> this warm-up complete: {(r['warm'] - t_ref) * 1000.0:.1f} ms" if "warm" in r else ""))
        return "\n".join(lines)


async def main():
    config = substation.config.load_config(CONFIG)
    out = [f"interpreter+imports (numpy, substation.scanner, substation.config): {(T_IMPORTS - T_START) * 1000.0:.0f} ms (perf_counter from script top; interpreter start itself is outside)"]
    bands = ["probe_a", "probe_b", "probe_a"]
    prev_switch = None
    for band in bands:
        p = Probe(config, band)
        await p.run_until(N_BEFORE_SWITCH)
        out.append(p.report(prev_switch))
        prev_switch = p.t["switch_requested"]
    print("\n".join(out))


if __name__ == "__main__":
    make_wav()
    asyncio.run(main())
