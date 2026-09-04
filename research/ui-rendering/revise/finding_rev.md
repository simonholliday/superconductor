Headless Chromium 151 on an i7-9700K workstation with a GeForce GTX 1660 measured DOM, SVG, Canvas 2D and WebGL grids of 128 and 1024 cells with a moving playhead, both through SwiftShader (software compositing and raster, standing for a host whose Chromium has lost acceleration) and through the GPU, unthrottled and at 6x and 16x CPU throttling; Speedometer 2.0 in the same browser puts the 6x throttle at a Raspberry Pi 5-class main thread and the 16x throttle at a Pi 4-class one. Incremental updates (a playhead move and four toggles) cost under 1 ms per frame in every technique at 6x and 0.3 to 2 ms at 16x; a transform-moved playhead overlay costs 30 to 45 percent less than class toggles on two columns; a genuine every-cell change of 1024 DOM cells costs 2.8 ms unthrottled, 8.6 ms at 6x and 22.8 ms at 16x (SVG about 25 percent more), while a whole-canvas repaint costs 1.3, 3.9 and 10.5 ms of JavaScript but is raster-bound without a GPU (66 of 300 frames dropped at 6x, none with the GPU); a Preact re-render of the 1024-cell grid costs six to seven times the imperative incremental path; WebGL is the cheapest technique with the GPU and the only one that dropped frames at every throttle without it; a 400-bin waveform is ten times cheaper as a canvas fill than as an SVG polygon rewrite; and a realistic mixed page never missed a frame at any throttle. Real Pi frame times, `chrome://gpu` status and Firefox with acceleration need the hardware.

**Question.** What does it cost, per frame, to draw a step grid of 128 and 1024 cells with a moving playhead in DOM, SVG, Canvas 2D and WebGL, and to redraw a Subsample-style waveform, on a desktop browser with and without GPU acceleration and under CPU throttles standing in for a Raspberry Pi?

## Method

Two research prototypes (not house style) under `/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad/ui-rendering/`, driven by Playwright from a venv created there. `bench.html` with `run_bench.py` is the researcher's harness; `revise/bench2.html` with `revise/run_bench2.py` is the reviser's, using the same geometry, CSS and metrics and adding the scenarios the first harness lacked (a genuine every-cell change, a half-grid change, a transform-moved playhead overlay, and a Preact re-render). An earlier harness of 2026-09-02 (rows in `bench_log.txt` and `firefox_log.txt`, results in `results_gpu*.json` and `results_sw-unthrottled_cpu1.json`) used different geometry (64x16 for 1024 cells, 4 px gaps, 6 px radius, eight toggles per frame, 240 frames) and different metrics (frames per second, frame interval, DevTools `TaskDuration` and `RecalcStyleDuration`); its rows are summarised separately below and never mixed into the final tables.

Browser: Playwright's Chromium build, `Google Chrome for Testing 151.0.7922.34`, headless, viewport 1920x1080. Machine: Intel Core i7-9700K (8 cores, 3.6 GHz), 31 GiB, NVIDIA GeForce GTX 1660 (driver 580.173.02), Linux 6.8, a development workstation with no display attached. Two GPU conditions were run. Without flags, headless Chromium reports the WebGL renderer as `ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero)))`: compositing, raster and WebGL are all software, which stands for a host whose Chromium has fallen back from hardware acceleration. With `--enable-gpu --use-angle=gl-egl --ignore-gpu-blocklist` it reports `ANGLE (NVIDIA Corporation, NVIDIA GeForce GTX 1660/PCIe/SSE2, OpenGL ES 3.2)`, which stands for a desktop with working acceleration. The SwiftShader condition was chosen, not forced.

Each scenario renders a 1920x1080 stage. Grids are 16x8 (128 cells) or 32x32 (1024 cells) with a 2 px gap and 3 px corner radius, 30 percent of cells lit at the start. Change models per frame: `incremental` advances the playhead one column and toggles four random cells, rewriting only the two affected columns and the toggled cells; `rewrite-all` (called `full` in `bench.html`) rewrites every cell's `className` or `fill` but the state still differs by the same four toggles plus two playhead columns, so about 70 of 1024 cells actually change and Blink invalidates style only for those, which makes it a measure of rewrite cost and not of change cost; `half` changes each cell with probability one half, as a reconnect snapshot might; `every-cell` inverts every cell. Canvas cost does not depend on how many cells changed when the whole canvas is repainted. Each run is 60 warm-up frames then 300 measured frames under `requestAnimationFrame`. Metrics: `js` is `performance.now()` around the render call; `+sl` forces style and layout synchronously after the mutation (`offsetHeight` and `getComputedStyle`) so the figure includes those phases (every `bench2` row is `+sl`; for canvas the forced layout is trivially cheap and the figure is the draw-call cost); `interval` is the gap between consecutive `requestAnimationFrame` timestamps; frames over 20 ms are counted as `long`. Paint and raster run on other threads and are not in `js`; when they overrun they show up as long intervals. `performance.now()` is coarsened to 0.1 ms, so sub-millisecond means carry more precision than any single sample.

Renderers: DOM is a CSS grid of `div`s with class toggles (`.cell`, `.on`, `.ph`); the overlay variant carries the playhead as one absolutely positioned column `div` with `will-change: transform` moved by `translateX`; SVG is one `<rect>` per cell with `fill` attribute changes; Canvas 2D uses `roundRect` fills, clearing the whole canvas for a whole repaint and overdrawing only changed cells otherwise; WebGL 2 draws all cells in one instanced draw call with a per-instance colour buffer uploaded each frame; the Preact scenario renders the whole grid as 1024 `htm` vnodes through `render()` each frame using the vendored `htm/preact/standalone.module.js` (13,194 bytes). Two further scenarios: a waveform of 400 min/max bins, the exact shape Subsample's `PreviewData` carries (`/mnt/dev/Apps/Subsample/subsample/preview.py:153-201`) and `render_svg` draws as an 800-point polygon (`preview.py:783-809`), redrawn every frame at 1920x256 as an SVG `points` rewrite or as a canvas path fill; and a mixed page of four 16x8 DOM grids (512 cells, incremental), eight faders moved by `transform`, and one canvas waveform redrawn every frame, with style and layout forced.

CPU throttling uses Chrome DevTools `Emulation.setCPUThrottlingRate`; it slows the renderer's main thread only. The throttle is anchored: Speedometer 2.0 (https://browserbench.org/Speedometer2.0/) in this same Chromium build scored 177 ± 11 runs per minute unthrottled and 56.6 ± 1.6 at 6x (`speedometer.py`, `speedometer_log.txt`). Raspberry Pi's own figures on Speedometer 2.1 are 62.5 for Pi 5 and 20.5 for Pi 4, with Geekbench 6.2 single-core 764 and 340 (https://www.raspberrypi.com/news/benchmarking-raspberry-pi-5/); CNX Software measured a Pi 5 at 63.5 on Speedometer 2.0 in Chromium against 21 for a Pi 4 at 2.0 GHz (https://www.cnx-software.com/2023/11/05/raspberry-pi-5-review-raspberry-pi-os-bookworm-benchmarks-power-consumption/). So the 6x column is a Pi 5-class main thread, about ten percent under; a Pi 4 is a further 2.7 to 3x slower. Speedometer 2.0 at 16x in the same browser scored 20.1 ± 0.45 (`revise/speedometer16.txt`), against the Pi 4's 20.5 on 2.1 and 21 on 2.0, so the 16x column is a Pi 4-class main thread, measured rather than extrapolated. Two caveats: Speedometer 2.0 and 2.1 score differently, and the throttle is not a clean multiplier for sub-millisecond work (DOM incremental with style and layout goes from 0.31 ms to 0.64 ms between 1x and 6x, while the every-cell change goes 2.8, 8.6, 22.8 ms at 1x, 6x, 16x, close to proportional). The 2x throttled run is indistinguishable from unthrottled at 0.1 ms timer resolution and is omitted from the tables below; it is in `results_throttle2x.json`.

## Results, SwiftShader, researcher's harness

Mean and p95 of `js` per frame in milliseconds; `+sl` is the run with style and layout forced (DOM and SVG only). `long` is frames over 20 ms out of 300. The `rewrite-all` rows change about 70 cells; see the next table for genuine whole-grid changes.

| Technique | Cells | Mode | 1x js (p95) | 1x +sl (p95) | 4x js (p95) | 4x +sl (p95) | 6x js (p95) | 6x +sl (p95) | Long frames (1x / 4x / 6x) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DOM | 128 | incremental | 0.02 (0.1) | 0.14 (0.3) | 0.04 (0.2) | 0.17 (0.5) | 0.05 (0.3) | 0.23 (0.7) | 0 / 0 / 0 |
| DOM | 128 | rewrite-all | 0.06 (0.2) | 0.11 (0.2) | 0.07 (0.3) | 0.19 (0.5) | 0.08 (0.3) | 0.23 (0.7) | 0 / 0 / 0 |
| DOM | 1024 | incremental | 0.06 (0.2) | 0.31 (0.6) | 0.09 (0.3) | 0.48 (0.9) | 0.07 (0.3) | 0.64 (1.3) | 0 / 0 / 0 |
| DOM | 1024 | rewrite-all | 0.27 (0.5) | 0.51 (1.0) | 0.29 (0.7) | 0.84 (1.2) | 0.39 (1.0) | 1.21 (1.8) | 0 / 0 / 0 |
| SVG | 128 | incremental | 0.04 (0.1) | 0.17 (0.3) | 0.04 (0.2) | 0.21 (0.6) | 0.05 (0.3) | 0.28 (0.9) | 0 / 0 / 0 |
| SVG | 128 | rewrite-all | 0.09 (0.2) | 0.21 (0.5) | 0.10 (0.3) | 0.33 (0.7) | 0.13 (0.5) | 0.38 (1.0) | 0 / 0 / 0 |
| SVG | 1024 | incremental | 0.09 (0.2) | 0.41 (0.8) | 0.10 (0.3) | 0.66 (1.0) | 0.10 (0.4) | 0.94 (1.5) | 0 / 0 / 0 |
| SVG | 1024 | rewrite-all | 0.61 (1.1) | 0.92 (1.9) | 1.04 (1.4) | 1.75 (2.2) | 1.58 (2.1) | 2.56 (3.2) | 0 / 0 / 0 |
| Canvas 2D | 128 | incremental (dirty cells) | 0.11 (0.2) | n/a | 0.08 (0.3) | n/a | 0.09 (0.4) | n/a | 0 / 0 / 0 |
| Canvas 2D | 128 | whole repaint | 0.35 (0.7) | n/a | 0.35 (0.8) | n/a | 0.50 (1.1) | n/a | 0 / 0 / 0 |
| Canvas 2D | 1024 | incremental (dirty cells) | 0.23 (0.4) | n/a | 0.15 (0.4) | n/a | 0.21 (0.7) | n/a | 0 / 0 / 0 |
| Canvas 2D | 1024 | whole repaint | 1.56 (2.4) | n/a | 3.22 (3.7) | n/a | 5.02 (5.8) | n/a | 0 / 0 / 81 |
| WebGL 2 | 128 | incremental | 0.03 (0.1) | n/a | 0.06 (0.3) | n/a | 0.13 (1.0) | n/a | 49 / 1 / 76 |
| WebGL 2 | 128 | rewrite-all | 0.02 (0.1) | n/a | 0.07 (0.4) | n/a | 0.13 (0.9) | n/a | 5 / 0 / 68 |
| WebGL 2 | 1024 | incremental | 0.02 (0.1) | n/a | 0.09 (0.6) | n/a | 0.12 (1.0) | n/a | 6 / 80 / 153 |
| WebGL 2 | 1024 | rewrite-all | 0.04 (0.1) | n/a | 0.11 (0.7) | n/a | 0.22 (1.2) | n/a | 3 / 77 / 158 |

## Results, genuine whole-grid changes, playhead overlay and Preact, 1024 cells

Reviser's harness, `js` with style and layout forced, mean (p95) in milliseconds, then long frames out of 300. SW is SwiftShader, GPU is the GTX 1660 through ANGLE.

| Scenario | Change model | SW 1x | SW 6x | SW 16x | GPU 1x | GPU 6x |
| --- | --- | --- | --- | --- | --- | --- |
| DOM incremental, playhead as class toggles on two columns | 4 toggles | 0.40 (0.7), 0 | 0.66 (1.3), 0 | 2.06 (4.4), 9 | 0.43 (0.8), 0 | 0.54 (1.3), 0 |
| DOM incremental, playhead as one overlay moved by `transform` | 4 toggles | 0.28 (0.5), 0 | 0.47 (1.1), 0 | 1.13 (4.0), 3 | 0.31 (0.6), 0 | 0.33 (1.0), 0 |
| DOM rewrite-all (about 70 cells change) | 4 toggles | 0.58 (1.0), 0 | 1.23 (1.8), 0 | 3.83 (6.7), 24 | 0.72 (1.2), 0 | 1.04 (1.7), 0 |
| DOM half the grid changes | half | 1.67 (3.5), 0 | 5.08 (5.7), 0 | 14.18 (16.8), 286 | 1.32 (1.9), 0 | 4.78 (5.6), 0 |
| DOM every cell changes | every-cell | 2.80 (7.1), 0 | 8.60 (9.6), 14 | 22.78 (25.3), 300 | 2.20 (3.2), 0 | 8.17 (9.2), 3 |
| SVG half the grid changes | half | 2.18 (4.4), 0 | 7.13 (7.9), 0 | 19.91 (23.3), 294 | 1.68 (2.4), 0 | 6.66 (7.8), 0 |
| SVG every cell changes | every-cell | 2.91 (3.7), 0 | 10.89 (12.7), 14 | 28.71 (33.6), 300 | 2.50 (4.0), 0 | 10.20 (12.1), 4 |
| Canvas incremental (dirty cells and two columns) | 4 toggles | 0.21 (0.4), 0 | 0.16 (0.5), 0 | 0.31 (1.4), 0 | 0.17 (0.4), 0 | 0.12 (0.5), 0 |
| Canvas whole repaint | every-cell | 1.30 (2.0), 0 | 3.88 (4.8), 66 | 10.47 (13.1), 300 | 1.34 (2.3), 0 | 3.48 (4.1), 0 |
| Preact re-render of 1024 vnodes through `render()` | 4 toggles | 2.61 (3.6), 0 | 2.84 (3.8), 0 | 7.51 (9.8), 0 | 2.24 (4.2), 0 | 2.76 (3.7), 0 |

Mean frame intervals where frames were dropped at SW 16x: DOM every-cell 46.5 ms (about 21 fps), DOM half 33.6 ms, SVG every-cell 46.6 ms, SVG half 35.2 ms, canvas whole repaint 57.3 ms.

## Results, GPU, researcher's harness

The same scenarios as the first table with the GTX 1660 active, `js` mean (p95) and long frames out of 300.

| Technique | Cells | Mode | GPU 1x js (p95) | GPU 1x +sl (p95) | GPU 6x js (p95) | GPU 6x +sl (p95) | Long frames (1x / 6x) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DOM | 128 | incremental | 0.06 (0.2) | 0.25 (0.4) | 0.03 (0.1) | 0.19 (0.7) | 0 / 0 |
| DOM | 1024 | incremental | 0.09 (0.2) | 0.43 (0.8) | 0.06 (0.3) | 0.51 (1.2) | 0 / 0 |
| DOM | 1024 | rewrite-all | 0.32 (0.7) | 0.61 (1.2) | 0.34 (0.9) | 1.08 (1.7) | 0 / 0 |
| SVG | 1024 | incremental | 0.10 (0.2) | 0.36 (0.6) | 0.11 (0.5) | 0.80 (1.6) | 0 / 0 |
| SVG | 1024 | rewrite-all | 0.60 (1.4) | 0.87 (1.7) | 1.39 (2.0) | 2.23 (3.0) | 0 / 0 |
| Canvas 2D | 1024 | incremental (dirty cells) | 0.23 (0.4) | n/a | 0.18 (0.7) | n/a | 0 / 0 |
| Canvas 2D | 1024 | whole repaint | 1.71 (4.0) | n/a | 4.53 (5.4) | n/a | 0 / 0 |
| WebGL 2 | 128 | incremental | 0.05 (0.1) | n/a | 0.03 (0.1) | n/a | 0 / 0 |
| WebGL 2 | 1024 | incremental | 0.05 (0.1) | n/a | 0.02 (0.1) | n/a | 0 / 0 |
| WebGL 2 | 1024 | rewrite-all | 0.08 (0.2) | n/a | 0.05 (0.2) | n/a | 0 / 0 |

## Results, waveform and mixed page

`js` mean (p95) in milliseconds, style and layout forced where DOM is involved; long frames out of 300 were zero in every cell of this table.

| Scenario | SW 1x | SW 4x | SW 6x | GPU 1x | GPU 6x |
| --- | --- | --- | --- | --- | --- |
| SVG polygon, 400 bins, 1920x256, `points` rewritten every frame | 1.15 (1.5) | 0.83 (1.2) | 1.30 (1.9) | 0.64 (1.2) | 1.11 (1.7) |
| Canvas path fill, same data | 0.11 (0.2) | 0.06 (0.2) | 0.09 (0.3) | 0.08 (0.2) | 0.06 (0.3) |
| Mixed page: 512 DOM cells incremental, 8 `transform` faders, 1 canvas waveform | 0.47 (1.0) | 0.81 (1.1) | 1.23 (1.7) | 0.62 (1.1) | 0.90 (1.6) |

## Results, earlier harness (different geometry; summarised, not comparable cell for cell)

- Chromium with the GPU, vsync-capped: all 28 cases (seven techniques, 128 and 1024 cells, realistic and every-cell load) held 60.0 fps with a maximum frame interval of 16.8 ms; the cap hides every difference on this machine.
- Chromium with the GPU, unthrottled, median frame interval at 1024 cells: DOM 1.3 ms realistic and 3.4 ms every-cell; SVG 1.3 and 3.5; canvas whole repaint 1.0 and 1.2; dirty canvas 0.1 and 1.2; WebGL 0.1 and 0.1.
- Chromium with the GPU at 6x, vsync-capped: DOM 1024 every-cell 56.5 fps with 17.8 ms of task time and 6.7 ms of style recalculation per frame; every other case 59 to 60 fps; WebGL 0.6 to 0.8 ms of task time.
- Chromium under SwiftShader, unthrottled, median frame interval: WebGL 14.7 to 18.6 ms at every size and load (52 to 66 fps with nothing else on the page) against under 5 ms for DOM, SVG and canvas. Without a GPU, WebGL is the slowest technique by an order of magnitude.
- Firefox 153.0 (Playwright build), headless, software compositing, no WebGL 2: vsync-capped, every DOM, SVG and canvas case held 58 to 60 fps except DOM at 1024 cells with every cell changing (46.9 fps for class-toggled and 46.2 fps for overlay playheads, 33 ms frames) while canvas held 60 fps at 6 to 7 ms of JavaScript; unthrottled median frame at 1024 cells realistic load: DOM 13.0 ms, SVG 6.6 ms, canvas 5.4 ms, dirty canvas 2.2 ms. In software-rendered Firefox the DOM grid was the most expensive technique because the whole layer is re-rasterised on the CPU each frame. Firefox with WebRender and a GPU was not measured.

## What the numbers say

- Incremental updates are cheap in every technique, browser and condition measured. A playhead move plus four toggles at 1024 cells costs under 1 ms of main-thread time at the Pi 5-class throttle in DOM (0.5 to 0.7 ms with style and layout), SVG (0.9 ms) and canvas (0.2 ms), and 0.3 to 2 ms at the 16x throttle. The first use-case's 16x8 grid is noise everywhere. The rule "change only what changed" is worth more than the choice of technique.
- The `rewrite-all` mode of the first harness measured rewrite cost, not change cost, and understated whole-grid changes by a factor of six to seven. A genuine every-cell change of 1024 DOM cells costs 2.8 ms unthrottled, 8.6 ms at 6x (14 of 300 frames dropped) and 22.8 ms at 16x (every frame dropped, about 21 fps); half the grid costs 1.7, 5.1 and 14.2 ms. SVG is about 25 percent dearer at every level. A reconnect snapshot or a page switch that changes most of a 1024-cell grid is therefore one dropped frame on a Pi 5-class host and two to three on a Pi 4-class host; as a per-frame load it is unaffordable on either.
- Dirty-cell canvas is the cheapest incremental path measured (0.1 to 0.3 ms at every throttle, with or without a GPU), below DOM incremental with style and layout (0.4 to 0.7 ms at 1x and 6x). The difference is immaterial at this scale and does not decide between them. A whole-canvas repaint is the cheapest way to change every cell on the main thread (1.3, 3.9 and 10.5 ms) but the only case whose dropped frames come from raster rather than JavaScript: 66 of 300 at 6x and every frame at 16x under SwiftShader, none with the GPU. Without a GPU, a full-screen canvas repaint depends on software raster speed; a DOM change depends on main-thread speed.
- Moving the playhead as one overlay with `transform` costs 30 to 45 percent less than toggling classes on two columns (0.28 against 0.40 ms unthrottled, 0.47 against 0.66 at 6x, 1.13 against 2.06 at 16x), and its median at 16x was 0.2 ms against 2.2 ms: the four toggled cells are the whole cost, the move itself touches neither style nor layout.
- A Preact re-render of the whole 1024-cell grid with four changes costs 2.6 ms unthrottled, 2.8 ms at 6x and 7.5 ms at 16x, six to seven times the imperative incremental path at 1x and 6x. It never dropped a frame on its own, but at Pi 4 class it is close to half the budget before anything else is drawn. The grid's hot path must bypass the virtual DOM; the framework renders chrome and infrequent state.
- WebGL's main-thread cost is flat and negligible, and with the GPU it held 60 fps with no long frames at every size, load and throttle. Under SwiftShader it dropped frames at every throttle level (49 of 300 unthrottled at 128 cells against 3 to 6 at 1024, which is software-GL readback noise rather than a size effect; about 80 of 300 at 4x and 68 to 158 at 6x), the only technique to do so on the realistic load. It is the fastest path where acceleration works and the worst where it does not.
- SVG behaves like DOM for cell fills and is the wrong tool for anything rewritten per frame: the 800-coordinate `points` attribute costs 0.6 to 1.3 ms against 0.1 ms for the same polygon as a canvas fill.
- The mixed page (512 live cells, eight animated faders, one redrawn waveform) costs under 1.3 ms per frame at 6x and never missed a frame in any condition. A realistic Superintendent page is nowhere near the budget on the main thread; if it misses frames on a Pi it will be paint, raster or compositing, which these harnesses cannot throttle and only the hardware can measure.
- The one shipping-browser case in which a DOM grid missed frames was software-rendered headless Firefox with every cell changing every frame; its realistic load held 60 fps. Firefox on a real display with WebRender was not measured.

## Hardware-gated

- Real frame intervals on a Raspberry Pi 4 and 5 in Chromium under labwc at 1920x1080, with `chrome://gpu` recorded, for the recommended DOM-plus-canvas page; the throttled figures here calibrate the main thread only, not paint, raster or compositing.
- The same in Firefox on the Pi and on a Windows desktop with a GPU, where the compositor path differs from both conditions measured here.
- Touch-to-paint latency of a cell toggle on the panel (belongs with the latency point but needs this page).

## Not covered

- Text labels inside cells; every cell here is a plain rounded rectangle. Labels add glyph raster to a first paint but not to a class flip or a transform.
- Firefox with GPU acceleration, and any browser at 2x device pixel ratio.
- 4096-cell grids in the final harness (the earlier harness put DOM every-cell at 10.7 ms unthrottled with the GPU; nothing in the brief needs that size).

## Provenance

Files read: `/mnt/dev/Apps/Subsample/subsample/preview.py:153-201,704-742,783-809,910-935`; Supervisor and `web_ui` client files as listed in the companion design document. Prototypes and raw results under `/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad/ui-rendering/`: `bench.html`, `run_bench.py`, `results_desktop.json`, `results_throttle{2,4,6}x.json`, `log_*.txt`, `speedometer.py`, `speedometer_log.txt`, `bench_log.txt`, `firefox_log.txt`, `results_gpu*.json`, `results_sw-unthrottled_cpu1.json`; and under `revise/`: `bench2.html`, `run_bench2.py`, `results2_sw.json`, `results2_gpu.json`, `results_gpu.json`, `results_gpu6x.json`, `log_*.txt`, `speedometer16.txt`, `vendor/standalone.module.js` (htm 3.1.1 with Preact, fetched from unpkg for the measurement only). URLs: https://www.raspberrypi.com/news/benchmarking-raspberry-pi-5/ (Pi Geekbench and Speedometer figures); https://www.cnx-software.com/2023/11/05/raspberry-pi-5-review-raspberry-pi-os-bookworm-benchmarks-power-consumption/ (Speedometer 2.0 on Pi 5 and Pi 4); https://browserbench.org/Speedometer2.0/; https://chromedevtools.github.io/devtools-protocol/tot/Emulation/ (`setCPUThrottlingRate`); https://web.dev/articles/stick-to-compositor-only-properties-and-manage-layer-count and https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API/Tutorial/Optimizing_canvas (the compositor-only and dirty-region guidance the prototypes follow).
