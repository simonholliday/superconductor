**Question.** How is the Superintendent surface drawn in the browser, with which framework (or none), from which widget and waveform sources, in which fonts and icons, and is every candidate compatible with AGPL-3.0 and vendorable so the panel works with no internet?

## What is on the ground

Both existing front ends are Preact 10.19.6 plus htm 3.1.1 loaded from esm.sh with no build step (`/mnt/dev/Apps/Supervisor/client/app.js:1-3`; `/mnt/dev/Apps/2026-02 Sequencer/subsequence/assets/web/index.html:163-166`). Supervisor also pulled JetBrains Mono from Google Fonts (`client/index.html:7-9`) while vendoring Gridstack locally (`client/index.html:10-12`, `client/lib/gridstack-all.js`). Both draw everything with the DOM: Supervisor's LED meter is a row of `div`s whose opacity and `box-shadow` carry the level (`client/components/led-meter.js:31-40`), its piano roll is one inline SVG with `rect` notes and a `line` playhead re-rendered through Preact on every state message (`client/panels/sequencer/patterns.js:82-121`, driven from `app.js:259-278`); `web_ui` positions absolutely placed `div.note-rect` elements and a 1 px `div.playhead` by percentage `left` (`assets/web/index.html:148-156`, `:242-243`, `:256`, `:268`) from a `playhead_pulse` pushed every 100 ms (`web_ui.py:214`, `:225`). Neither handles touch. Supervisor's theme is a dozen CSS custom properties on `:root` (`client/style.css:1-22`), which is the right shape to keep.

Subsample already computes the waveform data a panel needs: a 400-bin int8 min/max envelope, four per-band strata, onsets, beat times and an accent colour, serialised under `preview` in each sample's `.analysis.json` with the envelopes base64-packed by `serialize_for_sidecar` (`/mnt/dev/Apps/Subsample/subsample/preview.py:63-70`, `:152-207`, `:910-930`), and `render_svg(data, width, height)` returns a standalone SVG string written for a Supervisor consumer that never arrived (`preview.py:1-15`, `:704-741`).

## Rendering technique

The measurements are in the companion finding (rendering measurements). The facts that decide the choice, measured on the development workstation in Chromium 151 at 1920x1080:

- With a GPU, every technique holds 60 fps at 128 and 1024 cells even when every cell changes every frame. The vsync cap hides all differences; only unthrottled frame cost separates them: at 1024 cells with a moving playhead and eight cell edits per frame, DOM costs about 1.3 ms a frame, SVG 1.0 to 1.3 ms, Canvas 2D full redraw 1.0 ms (dirty-rect 0.1 ms), WebGL 0.1 ms.
- With the CPU throttled six times (which puts the workstation just below a Raspberry Pi 5 on Speedometer 2.0, see the finding for the anchor) and 1024 cells all changing every frame, DOM and SVG drop to 56 to 59 fps with 33 ms worst frames and 6.5 to 7.8 ms of style recalculation per frame; Canvas 2D holds 60 fps at about 6 ms; WebGL holds 60 fps at under 1 ms. At 128 cells everything holds 60 fps with margin under the same throttle. The realistic load (playhead plus a few edits per frame) never breaks 60 fps in any technique at either cell count.
- Without a GPU (Chromium `--disable-gpu`, SwiftShader), DOM, SVG and Canvas still draw a 1024-cell frame in 1.2 to 5 ms; WebGL collapses to 15 to 19 ms a frame (52 to 66 fps with nothing else on the page). WebGL is the only technique whose worst case depends on the host having working GPU acceleration, which on Raspberry Pi OS is exactly the thing that keeps going wrong: a Pi 5 user measured 10 fps in a WebGL test until acceleration was fixed, and another measured 7 to 8 fps on the WebGL Aquarium at 500 fish with acceleration reportedly on (https://forums.raspberrypi.com/viewtopic.php?t=390106, https://github.com/balena-io-experimental/browser/issues/172).
- Headless Firefox 153 (no WebGL2 in that build, so no GPU path was exercised) held 60 fps for all DOM, SVG and Canvas cases except DOM at 1024 cells with every cell changing every frame (47 fps).

| | DOM cells + CSS (playhead as one transformed overlay) | SVG `rect` cells | Canvas 2D (dirty-rect redraw) | WebGL instanced quads |
| --- | --- | --- | --- | --- |
| Frame cost, 1024 cells, realistic load, desktop GPU | 1.3 ms | 1.0 to 1.3 ms | 0.1 to 1.0 ms | 0.1 ms |
| Worst case measured, 6x CPU throttle, 1024 cells all changing | 56 fps, 33 ms frames | 59 fps, 33 ms frames | 60 fps, 6 to 8 ms | 60 fps, under 1 ms |
| Without GPU acceleration | fine | fine | fine | 15 to 19 ms a frame |
| Hit testing and per-contact pointer capture | free: one element per cell, `pointerdown` carries `pointerId` | free, same | manual: map coordinates to cell, track `pointerId`s yourself | manual, same |
| Text, labels, focus, accessibility | native | native | drawn by hand | drawn by hand |
| Theming | CSS custom properties, `:hover`/`:active` states, transitions for free | same (`fill` from CSS) | read custom properties in JS and repaint | same, plus shader uniforms |
| Crisp knobs, arcs, waveform paths | via inline SVG inside the cell or widget | native | native | needs geometry code |
| Code size for a grid | smallest | small | medium | largest (the prototype is about 70 lines of GL setup before drawing anything) |
| Risk | style recalculation scales with cells changed per frame; keep the hot path out of the virtual DOM | same, plus SVG DOM is heavier per node | canvas resize and devicePixelRatio handling; no CSS states | GPU availability on the Pi; context loss handling |

Short list:

1. **DOM cells styled by CSS, one element per cell, playhead as a single overlay element moved by `transform`; inline SVG for vector glyphs (knob arcs, fader caps, small waveforms).** Recommended. It is the cheapest to write, gets hit testing, `pointerId` tracking, CSS states, labels and theming for nothing, and never fell below 56 fps in any measured condition including the six-times-throttled worst case that the first use-case will not approach (a 16x8 grid changes a handful of cells a frame, not 1024). Two rules make it safe: the grid widget owns its cell elements and mutates classes directly (no virtual-DOM diff on the hot path), and the playhead is one element with `will-change: transform`, never a class flip across a column.
2. **Canvas 2D with dirty-rect redraw for the dense widgets (large grids, waveforms, meters), DOM for everything else.** The fallback if a page ever needs thousands of cells or a Pi measurement shows DOM style recalculation exceeding budget. Costs its own hit testing and pointer bookkeeping, loses CSS states, and must repaint on theme change. Subsample's 400-bin envelope draws in a few dozen lines either as canvas or as a static SVG path, so the waveform can go either way.
3. **SVG as the grid** is not listed separately: it measured the same as DOM, brings nothing the DOM cannot do for rectangles, and costs more per node. It stays as the vector glyph layer inside option one.

WebGL is excluded as the fourth: fastest with a GPU and worst without one, the most code, and the one whose behaviour on the intended cheap host is least predictable.

## Framework or none

The constraints from the decisions table hold: no build step (as both existing front ends), every file vendored so the panel works with no internet (Supervisor's CDN imports are the lesson), free and redistributable under AGPL-3.0. Import maps let a vendored `preact` resolve from a bare specifier without a bundler and have been Baseline across Chrome, Firefox and Safari since March 2023 (https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/script/type/importmap).

| | Vanilla ES modules + Web Components | Preact + htm | Lit | Vue 3 | Svelte 5 |
| --- | --- | --- | --- | --- | --- |
| Licence | none needed | MIT (https://github.com/preactjs/preact/blob/main/LICENSE) + Apache-2.0 for htm (https://github.com/developit/htm/blob/master/LICENSE) | BSD-3-Clause (https://github.com/lit/lit/blob/main/LICENSE) | MIT (https://github.com/vuejs/core/blob/main/LICENSE) | MIT (https://github.com/sveltejs/svelte/blob/main/LICENSE.md) |
| AGPL-3.0 compatible | n/a | yes; Apache-2.0 is compatible with GPLv3 one way (https://www.apache.org/licenses/GPL-compatibility.html) | yes | yes | yes |
| Runs with no build step | yes | yes, documented "no build tools route" with htm tagged templates (https://preactjs.com/guide/v10/getting-started/) | yes, via the published single-file bundles `lit-core.min.js` / `lit-all.min.js` (https://lit.dev/docs/getting-started/); npm source needs bare-specifier resolution (https://lit.dev/docs/tools/requirements/) | global or ESM browser build yes; Single File Components no (https://vuejs.org/guide/quick-start.html) | no: Svelte "uses a compiler" to turn components into JavaScript (https://svelte.dev/docs/svelte/overview) |
| Vendored size, min+gzip | 0 | 4.9 KB + 0.7 KB (https://bundlephobia.com/api/size?package=preact@10.29.6, https://bundlephobia.com/api/size?package=htm@3) | 6.0 KB (https://bundlephobia.com/api/size?package=lit@3) | 46 KB (https://bundlephobia.com/api/size?package=vue@3) | compiler output only |
| Widget boundary | custom element per control type | component per control type; hot path via `ref` | custom element per control type, shadow DOM scoping | component | component |
| Already in Simon's code | no | yes, Supervisor and web_ui | no | no | no |

Short list:

1. **Preact + htm, vendored, loaded through an import map.** Recommended. It is what both existing front ends use, so Supervisor's LED meter, audio player and connection manager carry over with their CDN imports rewritten to bare specifiers; it is the smallest option with a reactive model; and the one thing it must not do (diff a 1024-cell grid every beat) is avoided by giving the grid widget a `ref` and letting it mutate its own cells, which is how the measured prototype works.
2. **Lit, vendored bundle.** The natural fit if the control contract's "control type" is to become a literal custom element (`<si-grid>`, `<si-fader>`) that a page assembles by tag name from an app's declaration. Comparable size, no build, permissive licence. Shadow DOM scopes widget CSS; custom properties still pierce it for theming.
3. **Vanilla ES modules with hand-written custom elements.** No dependency at all, no licence table entry, and the hot path is direct DOM in any case. Costs re-implementing the small reactive layer that Preact gives for the chrome (page tabs, settings, connection state).

Vue is excluded as the fourth: nine times the size and its component format needs a build; Svelte cannot run without one.

## Widget sources

| Source | What it offers | Renders with | Licence | AGPL-3.0 | Touch | Status |
| --- | --- | --- | --- | --- | --- | --- |
| webaudio-controls | `webaudio-knob`, `-slider`, `-switch`, `-param`, `-keyboard` as custom elements, one script tag, MIDI-learn context menu | sprite images and DOM | Apache-2.0 (https://github.com/g200kg/webaudio-controls/blob/master/LICENSE) | yes (one-way, ASF statement above) | "iOS and Android touch devices compatible", multi-touch on the keyboard (https://g200kg.github.io/webaudio-controls/docs/) | pushed 2025-10-04 (https://api.github.com/repos/g200kg/webaudio-controls) |
| NexusUI 2.2.0 | Button, Dial, Envelope, Meter, Multislider, Number, Oscilloscope, Pan, Pan2D, Piano, Position, RadioButton, Select, Sequencer, Slider, Spectrogram, TextButton, Tilt, Toggle (https://api.github.com/repos/nexus-js/ui/contents/lib/interfaces) | SVG elements (`svg.create('rect')` per sequencer cell, circles and arc paths for the dial; https://raw.githubusercontent.com/nexus-js/ui/master/lib/interfaces/sequencer.js, .../dial.js) | MIT (package.json, https://raw.githubusercontent.com/nexus-js/ui/master/package.json) | yes | touch events but single contact only: it reads `targetTouches[0]` and keeps one `currentElement` | "Maintainers Wanted" badge (https://raw.githubusercontent.com/nexus-js/ui/master/README.md); pushed 2025-07-03 |
| Open Stage Control 1.31.1 | the richest OSC widget set (matrices, faders, knobs, pads, xy) | its own client tied to its server and editor | GPL-3.0 (https://framagit.org/jean-emmanuel/open-stage-control/-/raw/master/package.json) | yes: AGPL-3.0 section 13 permits combining with GPLv3 work, each part keeping its licence (https://opensource.org/license/agpl-v3) | yes | GitHub repository archived 2025-12-17 and moved to Framagit (https://github.com/jean-emmanuel/open-stage-control) |
| Faust UI (`@shren/faust-ui` 1.1.16) | vgroup/hgroup/tgroup, button, checkbox, sliders, nentry, bargraphs, knob/menu/radio/led styles | DOM | GPL-3.0-or-later (https://raw.githubusercontent.com/grame-cncm/faust-ui/master/package.json) | yes, as above | not stated | built to consume Faust's compiled JSON UI descriptor (https://github.com/grame-cncm/faust-ui) |
| Interface.js 0.3.0 | knobs, sliders, xy, multi-touch focused | canvas (not verified this session) | MIT (https://raw.githubusercontent.com/charlieroberts/interface.js/master/package.json) | yes | designed for touch | last push 2022-10-04 (https://api.github.com/repos/charlieroberts/interface.js) |
| p5.js | a drawing library, no widgets | canvas | LGPL-2.1 (https://api.github.com/repos/processing/p5.js/license) | yes | n/a | not a widget source |
| Tone.js | "a Web Audio framework"; no UI at all (https://tonejs.github.io/) | n/a | MIT | yes | n/a | not a widget source |
| PixiJS 8 | 2D WebGL/WebGPU scene graph | WebGL | MIT (https://github.com/pixijs/pixijs/blob/dev/LICENSE) | yes | yes | 258 KB gzip (https://bundlephobia.com/api/size?package=pixi.js@8); excluded with WebGL |
| Gridstack | drag-and-resize page layout, already vendored in Supervisor | DOM | MIT (https://github.com/gridstack/gridstack.js/blob/master/LICENSE) | yes | yes | candidate for the page editor, not for controls |

Short list for controls:

1. **Write the widgets.** Recommended. The v1 control set is a toggle grid, a pad bank, a fader, a knob, a selector and a text or meter display; each is a small DOM component with CSS states and, for knob and fader, one inline SVG arc or track. The hardware conventions below give the visual rules. Nothing in the table gives multi-touch pads or a bidirectional grid; every library would be bent to fit the control contract rather than the other way round.
2. **webaudio-controls for knob, slider and switch**, vendored as one file. Apache-2.0, custom elements, no build, touch, and MIDI-learn already there. Its look is sprite-driven, so it either sets the visual language or gets reskinned.
3. **NexusUI as a code quarry**, not a dependency: lift the dial arc mathematics and the sequencer's SVG cell layout under MIT attribution, rewrite the input layer on Pointer Events so that more than one contact works.

Open Stage Control is excluded as the fourth despite being licence-compatible: its widgets assume its server, editor and session model, and the project has left GitHub; it stays prior art for conventions, as the decisions table says.

Short list for waveforms:

1. **Draw Subsample's envelope directly.** Recommended. 400 min/max int8 pairs (`preview.py:67-70`) are a single SVG `path` or a 400-iteration canvas loop; `render_svg` (`preview.py:704-741`) can even be served as-is by the service for a static thumbnail. No dependency, no licence entry, and the same silhouette the file manager shows.
2. **wavesurfer.js 7** if a page needs playback-synchronised scrubbing or regions: BSD-3-Clause (https://github.com/katspaugh/wavesurfer.js/blob/main/LICENSE), 12 KB gzip (https://bundlephobia.com/api/size?package=wavesurfer.js@7), renders to canvas and accepts `peaks: Array<Float32Array | number[]>` plus `duration` so it renders "when peaks and duration are provided" without decoding audio (https://raw.githubusercontent.com/katspaugh/wavesurfer.js/main/src/wavesurfer.ts). Subsample's int8 envelope maps to it as `value / 127`.
3. **peaks.js** is excluded: LGPL-3.0 (https://github.com/bbc/peaks.js/blob/master/COPYING) is compatible, but it needs Konva (MIT, https://raw.githubusercontent.com/konvajs/konva/master/LICENSE) and waveform-data.js and expects BBC `audiowaveform` data or Web Audio decoding (https://github.com/bbc/peaks.js), none of which matches what Subsample already has. Substation has no waveform data at all, which `subsample-substation` must cover.

## A visual language for music hardware on glass

What the hardware does, from the vendors' own documents:

- Ableton Push 3 drum step sequencer: gray is an empty step, the clip colour is a step with a note, "higher velocities are indicated by brighter pads", a lighter clip colour is a muted note, green is the currently playing step (red when recording), white is the selected step; the loop-length row uses unlit/gray/white/green/red for outside the loop, inside but not visible, visible, playing, recording (https://www.ableton.com/en/push/manual/).
- Novation Launchpad Pro MK3: colours are a palette indexed 0 to 127 by note or CC value, or RGB with 0 to 127 per channel over SysEx; flashing alternates two colours at 50 % duty with a period of one beat, pulsing fades between dark and full over two beats, both synchronised to MIDI clock and defaulting to 120 BPM (https://fael-downloads-prod.focusrite.com/customer/prod/s3fs-public/downloads/LPP3_prog_ref_guide_200415.pdf; https://www.manualslib.com/manual/1830110/Novation-Launchpad-Pro-Mk3.html?page=11).
- Elektron Digitakt: note trigs are red `[TRIG]` keys, lock trigs yellow, empty steps unlit (Digitakt II manual, https://www.manualslib.com/manual/3436437/Elektron-Digitakt-Ii.html?page=41); "the active step is shown with a green [TRIG] key that double-blinks" and a fully lit page LED marks the active pattern page (https://www.manualslib.com/manual/2166470/Elektron-Digitakt.html?page=30; https://www.manualslib.com/manual/3436437/Elektron-Digitakt-Ii.html?page=42).
- Akai MPC One: pads light "ranging from yellow at a low velocity to red at the highest velocity", customisable (https://manuals.plus/akai/mpc-one-manual).

What transfers to glass:

- A cell has at most four visible states at once, encoded on separate channels so they compose: set/unset on hue (unset is a dim neutral, never black, so the grid reads as a grid), velocity or accent on brightness within the hue, kind of content on a second hue (Elektron's red note versus yellow lock maps to note versus parameter or probability), and "playing now" as a sweep in a reserved colour (green on Push and Elektron) that overlays whatever the cell is. Selected is white. Muted is desaturated, not removed.
- Time-synchronous animation is expressed in beats, not seconds: flash at one beat and pulse at two beats like the Launchpad, driven by the same clock the playhead uses, so a pending or unacknowledged cell can pulse without a second timer.
- Page and loop position are shown as a row of small indicators with the Push loop-row vocabulary (outside, inside, visible, playing).
- Per-instrument colour comes from the app declaration (the drum voice or pattern), never from the widget, so a page assembled from several apps stays legible.

Readability and touch size: WCAG 2.2 asks for 4.5:1 text contrast (3:1 for large text), 3:1 for non-text UI components against adjacent colours, and pointer targets of at least 24 by 24 CSS pixels (https://www.w3.org/TR/WCAG22/; https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html). A 16x8 grid on a 1920x1080 panel gives cells around 110 by 130 px, so target size is never the issue; labels are. Dobres, Chahine and Reimer (Applied Ergonomics 60, 2017) measured glance-like reading and found legibility thresholds "were highest for the negative polarity configurations under dark ambient illumination", that is light-on-dark text is slowest to read in the dark, with the effect largest at small sizes (https://jdobr.es/pdf/Dobres-etal-2017-Ambient.pdf). The surface is lights on a dark ground by nature, so the consequence is for text: labels large (the 3 mm size was the bad case), high contrast, no thin weights, tabular numerals, and a global brightness control so the panel can be dimmed in a dark studio and brightened under daylight rather than fixed at one luminance.

Fonts, all OFL-1.1, which permits bundling with software under another licence and web embedding via `@font-face`, with the font itself staying OFL and Reserved Font Names respected if modified (https://openfontlicense.org/ofl-faq/):

1. **Inter** (https://github.com/rsms/inter): variable, `tnum` tabular figures and `zero` slashed zero (https://rsms.me/inter/). The neutral choice for chrome and labels.
2. **B612 and B612 Mono** (https://github.com/polarsys/b612): "designed and tested to be used on aircraft cockpit screens" by Airbus with ENAC and Intactile Design, Regular/Bold/Italic in both proportional and mono. The instrument-panel choice; legibility at a glance was its design brief.
3. **JetBrains Mono** (https://github.com/JetBrains/JetBrainsMono): what Supervisor already used for data; fixed-width numerals for BPM and step counters.

Atkinson Hyperlegible (OFL-1.1 on the Google Fonts release, https://github.com/googlefonts/atkinson-hyperlegible) is the fourth, excluded only because its letterform distinctions target low vision rather than glance reading; it is a fine substitute for Inter if Simon prefers it.

Icons:

1. **Lucide**: 1,798 icons, 24 px grid, 2 px stroke, "released under the ISC License" with the Feather-derived subset under MIT (https://lucide.dev/; https://raw.githubusercontent.com/lucide-icons/lucide/main/LICENSE).
2. **Tabler Icons**: over 6,150 icons on a 24 px grid with a 2 px stroke, MIT, SVG and webfont (https://tabler.io/icons; https://github.com/tabler/tabler-icons/blob/main/LICENSE).
3. **Phosphor**: six weights including Fill and Duotone, MIT (https://github.com/phosphor-icons/core/blob/main/LICENSE).

Material Symbols (Apache-2.0, https://github.com/google/material-design-icons/blob/master/LICENSE) is the excluded fourth: compatible, but a system font of thousands of glyphs is the wrong shape for a panel that needs perhaps thirty transport and edit icons inlined as SVG.

## Licence summary for everything named above

| Licence | Used by | AGPL-3.0 combination | Obligation when vendored |
| --- | --- | --- | --- |
| MIT | Preact, NexusUI, Interface.js, Vue, Svelte, PixiJS, Gridstack, Konva, Tone.js, Tabler, Phosphor | permissive, compatible | keep the copyright and licence text |
| BSD-3-Clause | Lit, wavesurfer.js | permissive, compatible | keep the notice; no endorsement with the authors' names |
| ISC | Lucide | permissive, compatible | keep the notice |
| Apache-2.0 | htm, webaudio-controls, Material Symbols | compatible with GPLv3-family licences one way: "Apache 2 software can therefore be included in GPLv3 projects" (https://www.apache.org/licenses/GPL-compatibility.html) | keep LICENSE and NOTICE, state changes |
| LGPL-2.1 / LGPL-3.0 | p5.js / peaks.js | compatible; the library part stays LGPL | ship the library's source or an offer; keep it replaceable |
| GPL-3.0 | Open Stage Control, Faust UI | permitted by AGPL-3.0 section 13: "you have permission to link or combine any covered work with a work licensed under version 3 of the GNU General Public License into a single combined work" (https://opensource.org/license/agpl-v3) | the GPL part stays GPL; the combination is distributable |
| OFL-1.1 | Inter, B612, JetBrains Mono, Atkinson Hyperlegible | bundling with software under another licence is the stated intent (https://openfontlicense.org/ofl-faq/) | keep the OFL text; rename if modified |

The `licence-audit` point should re-verify each entry against the vendored file at the version pinned.

## Recommendation

Draw cells as DOM elements styled by CSS custom properties with a single transformed overlay for the playhead, use inline SVG for vector glyphs and Subsample's own envelope for waveforms, render the chrome with vendored Preact and htm behind an import map with no build step, keep the grid's hot path outside the virtual DOM, and write the v1 widgets ourselves following the Push, Launchpad and Elektron colour conventions in Inter or B612 with Lucide icons. Everything on that path is MIT, Apache-2.0, ISC or OFL-1.1, all AGPL-3.0-compatible and vendorable. Canvas 2D is the named fallback for any widget that a Pi measurement shows exceeding budget; WebGL and the widget libraries are excluded for the reasons given.

## Hardware-gated

- Frame times on the real host: a Raspberry Pi 4 or 5 running Chromium under labwc (the official kiosk tutorial uses labwc autostart with `chromium --kiosk`, https://www.raspberrypi.com/tutorials/how-to-use-a-raspberry-pi-in-kiosk-mode/), a Windows machine with Edge, and Firefox with WebRender on a real display. The workstation numbers are a desktop proxy; the six-times CPU throttle is anchored to a Pi 5 Speedometer score in the finding but emulates only the CPU, not the Pi GPU and compositor.
- The iiyama panel's colour, brightness and glare under studio lighting, which decide the palette's dim and bright presets.
- Whether the Pi's Chromium reports Canvas and WebGL as hardware accelerated out of the box on the chosen OS image (Bookworm desktop reports it after a clean profile, https://forums.raspberrypi.com/viewtopic.php?t=390106; Lite with X11 did not by default, https://forums.raspberrypi.com/viewtopic.php?t=379739).

## Not covered

- Interface.js's rendering backend and touch model were not read this session (only its licence and last activity); it is out of the short list on maintenance grounds regardless.
- The GNU licence list itself was unreachable (rate-limited) on the day; the compatibility statements above cite the ASF, the AGPL text and the OFL FAQ instead.

## Provenance

Files read: `/mnt/dev/Apps/Supervisor/client/app.js`, `client/index.html`, `client/style.css`, `client/components/led-meter.js`, `client/components/audio-player.js`, `client/panels/registry.js`, `client/panels/sequencer/patterns.js`; `/mnt/dev/Apps/2026-02 Sequencer/subsequence/web_ui.py`, `subsequence/assets/web/index.html`; `/mnt/dev/Apps/Subsample/subsample/preview.py`. Prototype and scripts: `/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad/ui-rendering/bench.html`, `run_bench.py`, `run_bench_firefox.py`, `speedometer.py`. URLs are cited inline.
