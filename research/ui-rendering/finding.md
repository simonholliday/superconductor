**Question.** What does it cost, per frame, to draw a step grid of 128 and 1024 cells with a moving playhead in DOM, SVG, Canvas 2D and WebGL, and to redraw a Subsample-style waveform, on a desktop browser and on something standing in for a Raspberry Pi?

## Method

A research prototype (not house style) at `/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad/ui-rendering/bench.html`, driven by `run_bench.py` through Playwright in a venv created there. Browser: Playwright's Chromium build, `Google Chrome for Testing 151.0.7922.34`, headless, viewport 1920x1080, WebGL renderer reported as `ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero)))`, so there is no GPU anywhere in these numbers: compositing and rasterisation are software. Machine: Intel Core i7-9700K (8 cores, 3.6 GHz), 31 GiB, Linux 6.8, a development workstation with no display attached.

Each scenario renders a 1920x1080 stage. Grids are 16x8 (128 cells) or 32x32 (1024 cells) with a 2 px gap and 3 px corner radius, 30 percent of cells lit. Every frame the playhead column advances by one and four random cells toggle. Two update modes: `incremental` rewrites only the two affected columns and the toggled cells (what a well-written surface does); `full` rewrites every cell every frame (what a naive virtual-DOM re-render or a full canvas repaint does). Each run is 60 warm-up frames then 300 measured frames under `requestAnimationFrame`. Two metrics: `js` is `performance.now()` around the render call; for DOM and SVG a second pass forces style and layout synchronously (`offsetHeight` and `getComputedStyle`) so the `js+style+layout` figure includes those phases. `interval` is the gap between consecutive `requestAnimationFrame` timestamps; frames over 20 ms are counted as `long`. Paint and raster run on other threads and are not in `js`; when they overrun they show up as long intervals.

Renderers: DOM is a CSS grid of `div`s with class toggles (`.cell`, `.on`, `.ph`); SVG is one `<rect>` per cell with `fill` attribute changes; Canvas 2D uses `roundRect` fills, clearing the whole canvas in `full` mode and overdrawing only changed cells in `incremental`; WebGL 2 draws all cells in one instanced draw call with a per-instance colour buffer uploaded each frame. Two further scenarios: a waveform of 400 min/max bins, the exact shape Subsample's `PreviewData` carries (`/mnt/dev/Apps/Subsample/subsample/preview.py:153-201`) and `render_svg` draws as an 800-point polygon (`preview.py:783-809`), redrawn every frame at 1920x256 as an SVG `points` rewrite or as a canvas path fill; and a mixed page of four 16x8 DOM grids (512 cells, incremental), eight faders moved by `transform`, and one canvas waveform redrawn every frame, with style and layout forced.

CPU throttling uses Chrome DevTools `Emulation.setCPUThrottlingRate` at 2x, 4x and 6x. It slows the renderer's main thread only. As a stand-in for a Pi it is indicative at best: Raspberry Pi's own Geekbench 6.2 single-core figures are 764 for Pi 5 and 340 for Pi 4, with Speedometer 2.1 at 62.5 and 20.5 respectively (https://www.raspberrypi.com/news/benchmarking-raspberry-pi-5/); no primary-source figure for this workstation's CPU could be fetched in this session (four benchmark sites refused automated access), so the ratio is not calibrated. `performance.now()` in this browser is coarsened to 0.1 ms, which is why sub-millisecond means carry more precision than any single sample.

## Results

Mean and p95 of `js` per frame in milliseconds; `+sl` is the run with style and layout forced (DOM and SVG only). Interval mean is the rAF cadence; `long` is frames over 20 ms out of 300.

| Technique | Cells | Mode | Desktop js (p95) | Desktop +sl (p95) | 2x js (p95) | 4x js (p95) | 4x +sl (p95) | 6x js (p95) | 6x +sl (p95) | Long frames (desktop / 4x / 6x) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DOM | 128 | incremental | 0.02 (0.1) | 0.14 (0.3) | 0.03 (0.1) | 0.04 (0.2) | 0.17 (0.5) | 0.05 (0.3) | 0.23 (0.7) | 0 / 0 / 0 |
| DOM | 128 | full | 0.06 (0.2) | 0.11 (0.2) | 0.05 (0.2) | 0.07 (0.3) | 0.19 (0.5) | 0.08 (0.3) | 0.23 (0.7) | 0 / 0 / 0 |
| DOM | 1024 | incremental | 0.06 (0.2) | 0.31 (0.6) | 0.07 (0.2) | 0.09 (0.3) | 0.48 (0.9) | 0.07 (0.3) | 0.64 (1.3) | 0 / 0 / 0 |
| DOM | 1024 | full | 0.27 (0.5) | 0.51 (1.0) | 0.23 (0.5) | 0.29 (0.7) | 0.84 (1.2) | 0.39 (1.0) | 1.21 (1.8) | 0 / 0 / 0 |
| SVG | 128 | incremental | 0.04 (0.1) | 0.17 (0.3) | 0.04 (0.2) | 0.04 (0.2) | 0.21 (0.6) | 0.05 (0.3) | 0.28 (0.9) | 0 / 0 / 0 |
| SVG | 128 | full | 0.09 (0.2) | 0.21 (0.5) | 0.10 (0.3) | 0.10 (0.3) | 0.33 (0.7) | 0.13 (0.5) | 0.38 (1.0) | 0 / 0 / 0 |
| SVG | 1024 | incremental | 0.09 (0.2) | 0.41 (0.8) | 0.07 (0.2) | 0.10 (0.3) | 0.66 (1.0) | 0.10 (0.4) | 0.94 (1.5) | 0 / 0 / 0 |
| SVG | 1024 | full | 0.61 (1.1) | 0.92 (1.9) | 0.66 (0.9) | 1.04 (1.4) | 1.75 (2.2) | 1.58 (2.1) | 2.56 (3.2) | 0 / 0 / 0 |
| Canvas 2D | 128 | incremental | 0.11 (0.2) | n/a | 0.06 (0.2) | 0.08 (0.3) | n/a | 0.09 (0.4) | n/a | 0 / 0 / 0 |
| Canvas 2D | 128 | full | 0.35 (0.7) | n/a | 0.19 (0.4) | 0.35 (0.8) | n/a | 0.50 (1.1) | n/a | 0 / 0 / 0 |
| Canvas 2D | 1024 | incremental | 0.23 (0.4) | n/a | 0.11 (0.3) | 0.15 (0.4) | n/a | 0.21 (0.7) | n/a | 0 / 0 / 0 |
| Canvas 2D | 1024 | full | 1.56 (2.4) | n/a | 1.64 (1.8) | 3.22 (3.7) | n/a | 5.02 (5.8) | n/a | 0 / 0 / 81 |
| WebGL 2 | 128 | incremental | 0.03 (0.1) | n/a | 0.03 (0.1) | 0.06 (0.3) | n/a | 0.13 (1.0) | n/a | 49 / 1 / 76 |
| WebGL 2 | 128 | full | 0.02 (0.1) | n/a | 0.04 (0.2) | 0.07 (0.4) | n/a | 0.13 (0.9) | n/a | 5 / 0 / 68 |
| WebGL 2 | 1024 | incremental | 0.02 (0.1) | n/a | 0.05 (0.3) | 0.09 (0.6) | n/a | 0.12 (1.0) | n/a | 6 / 80 / 153 |
| WebGL 2 | 1024 | full | 0.04 (0.1) | n/a | 0.06 (0.3) | 0.11 (0.7) | n/a | 0.22 (1.2) | n/a | 3 / 77 / 158 |

Waveform and mixed page, `js` mean (p95) in ms, style and layout forced where DOM is involved:

| Scenario | Desktop | 2x | 4x | 6x | Long frames (desktop / 4x / 6x) |
| --- | --- | --- | --- | --- | --- |
| SVG polygon, 400 bins, 1920x256, rewritten every frame | 1.15 (1.5) | 0.57 (1.0) | 0.83 (1.2) | 1.30 (1.9) | 0 / 0 / 0 |
| Canvas path fill, same data | 0.11 (0.2) | 0.05 (0.2) | 0.06 (0.2) | 0.09 (0.3) | 0 / 0 / 0 |
| Mixed page: 512 DOM cells incremental, 8 transform faders, 1 canvas waveform | 0.47 (1.0) | 0.45 (0.6) | 0.81 (1.1) | 1.23 (1.7) | 0 / 0 / 0 |

The full per-run output, including p50, p99 and max, is in `results_<label>.json` beside the prototype. The first desktop run (before the waveform and page scenarios were added) gave the same picture within noise: DOM 1024 full 0.30 ms js, 0.60 ms with style and layout; Canvas 1024 full 1.74 ms; SVG 1024 full 0.71 ms.

## What the numbers say

- At this scale nothing is expensive on the desktop. A 1024-cell grid rewritten in full through the DOM, with style and layout, is about 0.5 ms; the frame budget at 60 Hz is 16.7 ms. A 128-cell grid is noise. The first use-case's 16x8 grid is not a rendering problem on any technique.
- Incremental updates are what keep the Pi in reach. Rewriting only the playhead columns and the toggled cells costs 0.3 ms with style and layout at 1024 cells on the desktop, under 0.5 ms at 4x throttling and 0.6 ms at 6x; a full rewrite is about twice that (1.2 ms at 6x). The rule "change only what changed" is worth more than the choice of technique.
- Canvas 2D is the cheapest for a few cells and the most expensive for a whole grid. A full redraw of 1024 rounded rectangles is 1.6 ms on the desktop, 3.2 ms at 4x and 5.0 ms at 6x, where it was also the only non-WebGL scenario to drop frames (81 of 300 over 20 ms, the rAF cadence falling to about 21 ms), because each cell is a path and the whole 1920x1080 surface is repainted; dirty-rectangle redraws bring it to the DOM's level (0.2 ms at 6x). Canvas wins outright for the waveform: a full redraw at 1920x256 is 0.1 ms against 1.2 to 1.3 ms for the equivalent SVG `points` rewrite at every throttle level.
- SVG behaves like DOM for cell fills and is the wrong tool for anything rewritten per frame; a `points` attribute of 800 coordinates is serialised and reparsed every frame.
- WebGL's JavaScript cost is flat and negligible at both sizes, but it was the technique that dropped frames here: 49 of 300 on the desktop at 128 cells, about 80 of 300 at 4x throttling at 1024 cells, and 68 to 158 of 300 at 6x at every size (rAF cadence 20 to 25 ms, so 40 to 50 fps). Under SwiftShader the per-frame buffer upload and rasterisation of a 1920x1080 WebGL surface land on the throttled thread; on a Pi whose Chromium has fallen back to software GL the same would happen. With a working GPU it would be the fastest path, which is the wrong bet for a surface that must work on whatever Chromium the Pi image ships.
- The mixed page (512 live cells, eight animated faders, one redrawn waveform) costs under 1 ms of main-thread time per frame at 4x throttling and 1.2 ms at 6x, and never missed a frame at any level. A realistic Superintendent page is not near the budget on the main thread; if it misses frames on a Pi it will be paint and raster, which this harness cannot throttle and which only the hardware can measure.
- The 2x throttled run is indistinguishable from unthrottled for sub-millisecond work at 0.1 ms timer resolution; treat the 4x and 6x columns as the informative ones.

## Hardware-gated

- Real frame intervals on a Raspberry Pi 4 and 5 in Chromium under labwc at 1920x1080, with `chrome://gpu` recorded, for the recommended DOM-plus-canvas page. This harness cannot throttle paint, raster or compositing, and could not use a GPU at all.
- The same on the Windows host, where the GPU path will be different.
- Touch-to-paint latency of a cell toggle on the panel (belongs with the latency point but needs this page).

## Provenance

Files read: `/mnt/dev/Apps/Subsample/subsample/preview.py:153-201,704-742,783-809,910-935`; Supervisor and `web_ui` client files as listed in the companion design document. Prototype and raw results under `/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad/ui-rendering/` (`bench.html`, `run_bench.py`, `results_desktop.json`, `results_throttle2x.json`, `results_throttle4x.json`, `results_throttle6x.json`, `log_*.txt`). URLs: https://www.raspberrypi.com/news/benchmarking-raspberry-pi-5/ (Pi Geekbench and Speedometer figures); https://web.dev/articles/stick-to-compositor-only-properties-and-manage-layer-count and https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API/Tutorial/Optimizing_canvas (the compositor-only and dirty-region guidance the prototype follows).
