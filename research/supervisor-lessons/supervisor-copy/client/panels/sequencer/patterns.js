import { h } from 'https://esm.sh/preact@10.19.6';
import htm from 'https://esm.sh/htm@3.1.1';
import { registerPanel } from '../registry.js';

const html = htm.bind(h);

const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];

function midiToNote(midi) {
    const octave = Math.floor(midi / 12) - 1;
    return NOTE_NAMES[midi % 12] + octave;
}

function PatternsPanel({ state, connected }) {
    if (!connected) {
        return html`<div class="panel-disconnected">Sequencer not connected</div>`;
    }
    if (!state) {
        return html`<div class="panel-disconnected">Waiting for data\u2026</div>`;
    }

    const patterns = state.patterns || [];
    if (patterns.length === 0) {
        return html`<div class="panel-empty">No active patterns</div>`;
    }

    const playheadPulse = state.playhead_pulse || 0;

    return html`
        <div>
            ${patterns.map((pat, pi) => html`
                <${PatternGrid} key=${pi} pattern=${pat} playheadPulse=${playheadPulse} />
            `)}
        </div>
    `;
}

function PatternGrid({ pattern, playheadPulse }) {
    const { name, muted, length_pulses, drum_map, notes } = pattern;
    if (!notes || notes.length === 0) {
        return html`
            <div style="margin-bottom: 12px">
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px">
                    <span style="font-weight: 600; font-size: 0.85rem">${name}</span>
                    ${muted ? html`<span style="color: var(--color-error); font-size: 0.75rem">MUTED</span>` : null}
                </div>
                <div class="panel-empty" style="padding: 8px 0">Empty pattern</div>
            </div>
        `;
    }

    // Build reverse drum map: pitch -> label
    const pitchLabels = {};
    if (drum_map) {
        for (const [label, pitch] of Object.entries(drum_map)) {
            pitchLabels[pitch] = label;
        }
    }

    // Get unique pitches sorted descending
    const pitches = [...new Set(notes.map(n => n.p))].sort((a, b) => b - a);
    const len = length_pulses || 96;

    // SVG dimensions
    const rowH = 16;
    const labelW = 50;
    const gridW = 300;
    const svgW = labelW + gridW;
    const svgH = pitches.length * rowH;

    // Playhead position within pattern
    const playPos = len > 0 ? ((playheadPulse % len) / len) : 0;
    const noteColor = muted ? 'var(--color-error)' : 'var(--color-active)';

    return html`
        <div style="margin-bottom: 12px">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px">
                <span style="font-weight: 600; font-size: 0.85rem">${name}</span>
                ${muted ? html`<span style="color: var(--color-error); font-size: 0.75rem">MUTED</span>`
                        : html`<span style="color: var(--color-active); font-size: 0.75rem">PLAYING</span>`}
            </div>
            <svg width="100%" viewBox="0 0 ${svgW} ${svgH}" style="display: block; border-radius: 4px; background: var(--color-bg)">
                <!-- Row backgrounds -->
                ${pitches.map((p, i) => html`
                    <rect x=${labelW} y=${i * rowH} width=${gridW} height=${rowH}
                          fill=${i % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'transparent'}
                          key=${'bg-' + p} />
                `)}

                <!-- Pitch labels -->
                ${pitches.map((p, i) => html`
                    <text x=${labelW - 4} y=${i * rowH + rowH * 0.72}
                          fill="var(--color-text-muted)" font-size="10" text-anchor="end" font-family="inherit"
                          key=${'lbl-' + p}>
                        ${pitchLabels[p] || midiToNote(p)}
                    </text>
                `)}

                <!-- Notes -->
                ${notes.map((n, ni) => {
                    const rowIdx = pitches.indexOf(n.p);
                    if (rowIdx < 0) return null;
                    const x = labelW + (n.s / len) * gridW;
                    const dur = n.d != null ? n.d : 1;
                    // Duration: n.d is in beats (each beat = pulses_per_beat pulses)
                    // For display, treat d as fraction of pattern length if < 1, else scale
                    const w = Math.max(2, (dur / len) * gridW * 24);
                    const opacity = n.v != null ? 0.3 + (n.v / 127) * 0.7 : 1;

                    return html`
                        <rect x=${x} y=${rowIdx * rowH + 2} width=${Math.min(w, gridW - (x - labelW))} height=${rowH - 4}
                              fill=${noteColor} opacity=${opacity} rx="2"
                              key=${'n-' + ni} />
                    `;
                })}

                <!-- Playhead -->
                <line x1=${labelW + playPos * gridW} y1="0"
                      x2=${labelW + playPos * gridW} y2=${svgH}
                      stroke="var(--color-accent)" stroke-width="1.5" opacity="0.8" />
            </svg>
        </div>
    `;
}

registerPanel('subsequence.patterns', PatternsPanel);
