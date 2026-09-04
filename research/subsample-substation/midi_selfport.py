"""Prototype (not house style): can one process open a mido output into its own
virtual ALSA input port, and what does the hop cost?  Mirrors Subsample's
player.run(): mido.open_input(name, virtual=True, callback=...)."""
import mido, time, statistics, sys, threading
NAME = "Superintendent Probe Virtual MIDI"
got = []
ev = threading.Event()
def cb(msg):
    got.append((time.perf_counter(), msg))
    ev.set()
inp = mido.open_input(NAME, virtual=True, callback=cb)
time.sleep(0.2)
names = mido.get_output_names()
print("output names containing probe:", [n for n in names if "Probe" in n])
out = mido.open_output(NAME)          # same process, by bare name (ALSA client/port suffix omitted)
print("opened output:", out.name)
lat = []
for i in range(2000):
    ev.clear()
    t0 = time.perf_counter()
    out.send(mido.Message("note_on", note=36, velocity=100, channel=9))
    if not ev.wait(1.0):
        print("timeout"); sys.exit(1)
    lat.append((got[-1][0] - t0) * 1000.0)
    out.send(mido.Message("note_off", note=36, channel=9))
    ev.clear(); ev.wait(1.0)
    time.sleep(0.001)
lat.sort()
print(f"n={len(lat)} send->callback ms: median {statistics.median(lat):.3f} p95 {lat[int(len(lat)*0.95)]:.3f} p99 {lat[int(len(lat)*0.99)]:.3f} max {lat[-1]:.3f} min {lat[0]:.3f}")
print("last msg:", got[-1][1])
out.close(); inp.close()
