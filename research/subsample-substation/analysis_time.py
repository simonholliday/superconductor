"""Prototype (not house style): time Subsample's own sidecar+preview generation on a Substation
recording, and the bare 400-bin envelope alone, and render_svg size/time."""
import sys, time, pathlib, json, shutil, statistics
import numpy, soundfile
import subsample.cache, subsample.preview
for name in sys.argv[1:]:
    src = pathlib.Path("wav")/name
    work = pathlib.Path("work"); work.mkdir(exist_ok=True)
    dst = work/name
    times=[]
    for i in range(3):
        for p in work.glob(name+"*"):
            p.unlink()
        shutil.copy(src, dst)
        t0=time.perf_counter()
        assets = subsample.cache.ensure_sample_assets(dst, with_preview=True)
        times.append(time.perf_counter()-t0)
    sidecar = dst.with_name(dst.name+".analysis.json")
    png = dst.with_name(dst.name+".preview.png")
    d=json.load(open(sidecar))
    audio, sr = soundfile.read(dst, dtype="float32", always_2d=True)
    mono = audio.mean(axis=1)
    t0=time.perf_counter()
    for _ in range(20):
        env = subsample.preview._compute_waveform_envelope(mono)
    env_ms=(time.perf_counter()-t0)/20*1000
    pdata = subsample.preview.deserialize_from_sidecar(d["preview"])
    t0=time.perf_counter()
    for _ in range(20):
        svg = subsample.preview.render_svg(pdata, 800, 200)
    svg_ms=(time.perf_counter()-t0)/20*1000
    print(f"{name}: {dst.stat().st_size} bytes, {d['duration']:.2f} s @ {sr} Hz; ensure_sample_assets(with_preview=True) x3: {', '.join(f'{t*1000:.0f}' for t in times)} ms; "
          f"sidecar {sidecar.stat().st_size} B (preview block {len(json.dumps(d['preview'],separators=(',',':')))} B), png {png.stat().st_size} B; "
          f"bare 400-bin envelope {env_ms:.2f} ms; render_svg(800x200) {svg_ms:.2f} ms -> {len(svg)} B")
