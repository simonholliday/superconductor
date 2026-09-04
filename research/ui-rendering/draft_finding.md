**Question.** What does it cost, per frame, to draw a step grid of 128 and 1024 cells with a moving playhead and live cell edits at 1920x1080 in DOM, SVG, Canvas 2D and WebGL, in a desktop browser and under a stand-in for a Raspberry Pi?

## Method

A single prototype page (`/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad/ui-rendering/bench.html`, measurement code, not house style) draws a grid filling a 1920x1080 viewport with 4 px gaps and 6 px corner radii in seven ways:

- `dom`: one `div` per cell in a CSS grid, state as a class; the playhead is a class added to the column's cells and removed from the previous column.
- `domoverlay`: as `dom`, but the playhead is one absolutely positioned element with `will-change: transform` moved by `translateX`.
- `svg`: one `rect` per cell in an inline SVG, class per state, playhead as class flips.
- `svgoverlay`: as `svg`, playhead as one `rect` moved by its `x` attribute.
- `canvas`: Canvas 2D, whole grid cleared and every cell redrawn with `roundRect` each frame.
- `canvasdirty`: Canvas 2D, only changed cells and the two playhead columns repainted.
- `webgl`: WebGL2, one instanced draw of `cols x rows` quads, per-instance state in a `Float32Array` uploaded with `bufferSubData` when dirty, playhead as a uniform.

Two workloads per technique and cell count: the realistic one (`full=0`), where each frame advances the playhead one column and toggles eight random cells, standing in for the algorithm editing the grid; and the worst one (`full=1`), where every cell inverts every frame. 30 warm-up frames, then 240 measured frames per case. Grids: 16x8 (128), 64x16 (1024) and, unthrottled only, 128x32 (4096).

Recorded per case: achieved frames per second and the median, 95th percentile and maximum `requestAnimationFrame` interval; the median and 95th percentile of JavaScript time inside the frame callback; and, in Chromium, the per-frame averages of `RecalcStyleDuration`, `LayoutDuration` and `TaskDuration` from the DevTools `Performance.getMetrics` deltas across the run.

Browsers and modes (`run_bench.py`, `run_bench_firefox.py`, driven by Playwright 1.62):

- Chromium 151.0.7922.34 (Chrome for Testing, Playwright build 1234), headless, with the workstation GPU active (`--enable-gpu --use-angle=gl-egl`; WebGL reported "ANGLE (NVIDIA Corporation, NVIDIA GeForce GTX 1660/PCIe/SSE2, OpenGL ES 3.2)").
  - vsync-capped (default 60 Hz), to see whether 60 fps holds;
  - unthrottled (`--disable-frame-rate-limit --disable-gpu-vsync`), so the frame interval is the whole cost of a frame including style, layout, paint, raster and commit;
  - both again with `Emulation.setCPUThrottlingRate` 6, which "enables CPU throttling to emulate slow CPUs" with `rate` "as a slowdown factor" (https://chromedevtools.github.io/devtools-protocol/tot/Emulation/).
- Chromium 151 with `--disable-gpu --enable-unsafe-swiftshader`, unthrottled: software compositing and software WebGL, as a proxy for a host whose GPU acceleration is off.
- Firefox 153.0 (Playwright build), headless: WebGL2 unavailable in that build, so the WebGL case did not run and no GPU path was exercised. Firefox's timer precision is coarser than Chromium's, so its JavaScript timings are approximate.

The machine: Intel Core i7-9700K, 8 cores, 31 GB, NVIDIA GeForce GTX 1660 (driver 580.173.02), Linux 6.8, no display attached. Everything here is a desktop proxy; the Raspberry Pi and the iiyama panel were not available.

## Anchor for the six-times throttle

Speedometer 2.0 (https://browserbench.org/Speedometer2.0/) run in the same headless Chromium on this workstation (`speedometer.py`) scored 177 ± 11 runs per minute unthrottled and 56.6 ± 1.6 with `Emulation.setCPUThrottlingRate` at 6. CNX Software measured a Raspberry Pi 5 running Raspberry Pi OS Bookworm at 63.5 runs per minute in Chromium on the same benchmark, and reports the Pi 5 at "about double" a Raspberry Pi 4 on CPU work (https://www.cnx-software.com/2023/11/05/raspberry-pi-5-review-raspberry-pi-os-bookworm-benchmarks-power-consumption/). So the six-times throttle puts this machine's main thread slightly below a Pi 5 and about twice a Pi 4 for the JavaScript, style and layout work that Speedometer exercises. It says nothing about the Pi's GPU, raster or compositor path, which is why the SwiftShader run and the hardware-gated list exist. The Pi figure is from November 2023 and Chromium has moved since; the comparison is indicative.

## Results, Chromium with GPU, vsync-capped

Every one of the 28 cases (seven techniques, 128 and 1024 cells, realistic and worst load) held 60.0 fps with a maximum frame interval of 16.8 ms. Per-frame main-thread cost (`TaskDuration`) ranged from 0.45 ms (WebGL) to 5.3 ms (DOM, 1024 cells, every cell changing); style recalculation for that DOM worst case was 2.1 ms a frame. The cap hides every difference between techniques on this machine.

## Results, Chromium with GPU, unthrottled (frame cost)

Median frame interval in milliseconds; the realistic load is playhead plus eight edits per frame, the worst load is every cell changing.

| Technique | 128 realistic | 128 worst | 1024 realistic | 1024 worst | 4096 realistic | 4096 worst |
| --- | --- | --- | --- | --- | --- | --- |
| dom | 0.5 | 0.8 | 1.3 | 3.4 | 2.9 | 10.7 |
| domoverlay | 0.5 | 0.9 | 1.3 | 3.4 | 2.6 | 10.3 |
| svg | 0.4 | 0.8 | 1.3 | 3.5 | 2.2 | 11.1 |
| svgoverlay | 0.5 | 0.9 | 1.0 | 3.9 | 1.9 | 10.9 |
| canvas (full redraw) | 0.3 | 0.3 | 1.0 | 1.2 | 3.7 | 4.1 |
| canvasdirty | 0.1 | 0.3 | 0.1 | 1.2 | 0.2 | 10.5 |
| webgl | 0.1 | 0.1 | 0.1 | 0.1 | 0.1 | 0.1 |

Style recalculation for DOM at 1024 cells worst load was 1.06 ms a frame and at 4096 cells 4.2 ms; layout stayed at zero because nothing changes geometry. Canvas full redraw showed occasional long frames (maximum 129 to 346 ms at 1024 and 4096 cells) that the dirty variant and the other techniques did not; the 95th percentile stayed at 1.4 to 15 ms, so these are rare stalls (garbage collection or raster queueing), noted rather than explained.

## Results, Chromium with GPU, CPU throttled six times

Vsync-capped:

| Technique | 128 realistic | 128 worst | 1024 realistic | 1024 worst |
| --- | --- | --- | --- | --- |
| dom | 60 fps, task 1.7 ms | 60, 3.3 ms | 60, 6.0 ms | **56.5 fps**, p95 frame 33 ms, style 6.7 ms, task 17.8 ms |
| domoverlay | 60, 2.1 ms | 60, 3.5 ms | 60, 5.2 ms | 59.0 fps, max 33 ms, style 6.5 ms, task 16.4 ms |
| svg | 60, 1.5 ms | 60, 3.1 ms | 60, 5.1 ms | 59.0 fps, max 33 ms, style 7.8 ms, task 16.8 ms |
| svgoverlay | 60, 1.9 ms | 59.8, 3.9 ms | 60, 4.7 ms | 59.3 fps, max 33 ms, style 7.5 ms, task 16.7 ms |
| canvas | 60, 1.4 ms | 60, 1.6 ms | 60, 6.5 ms | 60, 6.0 ms |
| canvasdirty | 60, 1.1 ms | 60, 1.5 ms | 60, 1.0 ms | 60, 7.7 ms |
| webgl | 60, 0.6 ms | 60, 0.6 ms | 60, 0.7 ms | 60, 0.8 ms |

Unthrottled under the same six-times CPU slowdown, median frame in milliseconds: dom 1.9 / 3.1 / 5.3 / 16.8; domoverlay 1.4 / 3.2 / 4.9 / 16.7; svg 1.3 / 3.5 / 4.3 / 16.2; svgoverlay 1.3 / 3.2 / 5.0 / 16.4; canvas 1.3 / 1.7 / 5.8 / 6.1; canvasdirty 0.8 / 1.5 / 0.9 / 7.7; webgl 0.5 / 0.6 / 0.6 / 0.9 (columns as in the table). So under a Pi-class CPU the DOM and SVG grids of 1024 cells spend the whole 16.7 ms budget only when every cell changes every frame; the realistic load leaves two thirds of the budget free, and 128 cells leave nine tenths.

## Results, Chromium without GPU (SwiftShader), unthrottled

| Technique | 128 realistic | 128 worst | 1024 realistic | 1024 worst |
| --- | --- | --- | --- | --- |
| dom | 0.9 | 2.1 | 1.8 | 4.9 |
| domoverlay | 0.8 | 2.1 | 1.5 | 4.9 |
| svg | 0.9 | 2.0 | 1.7 | 4.9 |
| svgoverlay | 0.9 | 2.2 | 1.4 | 5.1 |
| canvas | 1.9 | 1.9 | 4.4 | 4.2 |
| canvasdirty | 1.2 | 2.0 | 1.2 | 4.8 |
| webgl | **14.7** | **14.9** | **18.4** | **18.6** |

Without a GPU, WebGL is the slowest technique by an order of magnitude (52 to 66 fps with nothing else on the page, 95th percentile 17 to 23 ms), while DOM, SVG and Canvas stay under 5 ms. This is the single most decision-relevant result: WebGL's advantage exists only where hardware acceleration works, and its failure mode is the whole frame budget.

## Results, Firefox 153 headless (software compositing)

Vsync-capped, all DOM, SVG and Canvas cases held 58 to 60 fps except DOM at 1024 cells with every cell changing (46.9 fps, both variants, 33 ms frames). Unthrottled median frame in milliseconds, columns 128 realistic / 128 worst / 1024 realistic / 1024 worst: dom 13.0 / 16.1 / 13.0 / 21.6; domoverlay 12.0 / 17.2 / 14.0 / 22.5; svg 5.4 / 5.4 / 6.6 / 8.7; svgoverlay 5.4 / 5.4 / 6.5 / 9.0; canvas 2.2 / 3.2 / 5.4 / 5.4; canvasdirty 2.2 / 3.2 / 2.2 / 6.5. In this software-rendered Firefox the DOM grid is the most expensive technique because the whole 1920x1080 layer is re-rasterised on the CPU each frame; SVG and Canvas are two to six times cheaper. Firefox on a real display uses WebRender with the GPU and will not behave like this; the number is recorded as the worst software case seen, not as a Firefox verdict.

## What the numbers mean for the first use-case

- A 16x8 grid is free in every technique, browser and mode measured: the worst single frame at 128 cells with a GPU was 1.2 ms unthrottled, and 3.9 ms of main-thread work under a six-times CPU slowdown.
- A page of a thousand cells is comfortable in every technique with the realistic load (a few edits a frame): under 6 ms a frame under the six-times slowdown, under 1.5 ms on the desktop.
- Only the pathological load (every one of 1024 cells changing every frame) reaches the 16.7 ms budget, and only for DOM and SVG under the six-times slowdown or in software-rendered Firefox. A snapshot that repaints a whole grid happens once per connect or resync, not per frame, so this is a one-frame hitch, not a frame rate.
- Moving the playhead as one overlay element rather than flipping classes on a column made no measurable difference with a GPU (both about 1.3 ms at 1024 cells); it becomes the cheaper path when style recalculation is the bottleneck (six-times throttle: 4.9 versus 5.3 ms realistic at 1024). It is also the simpler code, so it is the shape to keep.
- Dirty-rect Canvas is the cheapest CPU-only technique at every size when few cells change, and WebGL the cheapest of all when a GPU is present. Neither is needed for the first use-case; both remain available for a dense page.

## Hardware-gated

- The same page on a Raspberry Pi 4 and 5 under Raspberry Pi OS Bookworm with labwc, in Chromium and in Firefox, on a real 1920x1080 display; run `bench.html` from the scratchpad through any static server and read `window.__benchResult`. The six-times throttle is a stand-in; forum reports on Pi 5 WebGL range from 60 fps to 7 fps depending on whether acceleration is actually engaged (https://forums.raspberrypi.com/viewtopic.php?t=390106; https://github.com/balena-io-experimental/browser/issues/172).
- Windows with Edge on the iiyama panel, where touch input and compositor behaviour, not raw draw cost, are the unknowns.
- Actual displayed frame pacing: headless Chromium's 60 Hz BeginFrame is a simulation of vsync; a real compositor with a real display may drop or double frames differently.
- Input-to-paint latency of a tap on the panel, which this benchmark does not measure at all.

## Not covered

- Rendering on a Raspberry Pi (no Pi on the network from this workstation).
- Firefox with GPU acceleration (headless Firefox had no WebGL and software compositing).
- Anything drawn with text; the cells here are plain rounded rectangles. Labels add glyph raster cost to the first paint of each technique but not to a class flip or a transform.

## Provenance

Scripts and raw results in `/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad/ui-rendering/`: `bench.html`, `run_bench.py`, `run_bench_firefox.py`, `speedometer.py`, `results_gpu.json`, `results_gpu-unthrottled_cpu1.json`, `results_gpu_cpu6.json`, `results_gpu-unthrottled_cpu6.json`, `results_sw-unthrottled_cpu1.json`, `firefox_log.txt`, `speedometer_log.txt`. External: https://chromedevtools.github.io/devtools-protocol/tot/Emulation/; https://www.cnx-software.com/2023/11/05/raspberry-pi-5-review-raspberry-pi-os-bookworm-benchmarks-power-consumption/; https://browserbench.org/Speedometer2.0/; https://forums.raspberrypi.com/viewtopic.php?t=390106; https://github.com/balena-io-experimental/browser/issues/172.
