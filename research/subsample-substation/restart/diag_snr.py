"""Prototype diagnostic: what SNR does the scanner compute per channel for iq_probe.wav?"""
import asyncio, sys, time, datetime, collections
sys.path.insert(0, "/mnt/dev/Apps/SDR Scanner")
import substation.config, substation.scanner
import logging; logging.basicConfig(level=logging.WARNING)
import restart_file as rf
async def main():
    cfg = substation.config.load_config(rf.CONFIG)
    sc = substation.scanner.RadioScanner(config=cfg, band_name="probe_a", device_type="file",
        clock=substation.scanner.VirtualClock(datetime.datetime(2026,9,3,12,0,0), float(rf.FS)),
        device_kwargs={"file_path": str(rf.WAV), "center_freq": rf.CENTER})
    snr_max = collections.defaultdict(lambda: -999.0); nf = []; states = []
    def on_snr(*a, **kw):
        for ch in kw.get("channels", []) if isinstance(kw.get("channels"), list) else []:
            snr_max[(ch.get("index"), ch.get("frequency_mhz"))] = max(snr_max[(ch.get("index"), ch.get("frequency_mhz"))], float(ch.get("snr_db", -999)))
        if not kw.get("channels"):
            print("channel_snr kwargs keys:", list(kw.keys()))
    sc.on("channel_snr", on_snr)
    sc.on("noise_floor", lambda *a, **kw: nf.append(kw))
    sc.on("channel_state", lambda *a, **kw: states.append(kw))
    n = [0]; orig = sc._process_samples
    def w(s, loop):
        n[0] += 1; orig(s, loop)
    sc._process_samples = w
    task = asyncio.create_task(sc.scan())
    while n[0] < 30 and not task.done(): await asyncio.sleep(0.005)
    sc._signal_stream_end(); await task
    print("slices:", n[0]); print("noise_floor sample:", nf[-1] if nf else None)
    print("max snr per channel:", sorted(snr_max.items())[:20])
    print("channel_state events:", states[:5])
    print("center_freq used:", sc.center_freq, "sample_rate:", sc.sample_rate, "channels:", sc.channels[:3], "...", len(sc.channels))
asyncio.run(main())
