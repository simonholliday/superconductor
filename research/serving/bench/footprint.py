"""Cold import time and RSS after import, per stack. Prototype."""
import json, resource, subprocess, sys, time
PY = sys.executable
STACKS = {
 "stdlib only (http.server, asyncio)": "import asyncio, http.server, json",
 "websockets": "import websockets.asyncio.server",
 "starlette + uvicorn": "import starlette.applications, starlette.staticfiles, starlette.websockets, uvicorn",
 "fastapi + uvicorn": "import fastapi, uvicorn",
 "aiohttp": "import aiohttp.web",
 "quart + hypercorn": "import quart, hypercorn.asyncio",
}
for name, imp in STACKS.items():
    times = []; rss = None
    for _ in range(5):
        t0 = time.perf_counter()
        out = subprocess.run([PY, "-c", imp + "; import resource, sys; sys.stdout.write(str(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss))"], capture_output=True, text=True)
        times.append(time.perf_counter() - t0)
        rss = int(out.stdout.strip()) / 1024
    print(json.dumps({"stack": name, "import_wall_ms_min": round(min(times)*1000), "maxrss_after_import_mb": round(rss, 1)}))
