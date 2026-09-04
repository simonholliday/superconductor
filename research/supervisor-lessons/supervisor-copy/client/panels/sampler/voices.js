import { h } from 'https://esm.sh/preact@10.19.6';
import htm from 'https://esm.sh/htm@3.1.1';
import { registerPanel } from '../registry.js';

const html = htm.bind(h);

const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];

function midiToNote(midi) {
    const octave = Math.floor(midi / 12) - 1;
    return NOTE_NAMES[midi % 12] + octave;
}

function VoicesPanel({ state, connected }) {
    if (!connected) {
        return html`<div class="panel-disconnected">Sampler not connected</div>`;
    }
    if (!state) {
        return html`<div class="panel-disconnected">Waiting for data\u2026</div>`;
    }

    const playback = state.playback || {};
    const voices = playback.voices || [];
    const limit = playback.polyphony_limit || 16;
    const ccState = playback.cc_state || {};

    return html`
        <div>
            <div class="panel-kv" style="margin-bottom: 8px">
                <span class="panel-kv-label">Polyphony</span>
                <span class="panel-kv-value">${voices.length} / ${limit}</span>
            </div>

            ${voices.length === 0
                ? html`<div class="panel-empty">No active voices</div>`
                : html`<table class="panel-table">
                    <thead><tr><th>Note</th><th>Ch</th><th>Status</th></tr></thead>
                    <tbody>
                        ${voices.map((v, i) => html`
                            <tr key=${i} class="${v.releasing ? 'panel-table-row--dimmed' : 'panel-table-row--active'}">
                                <td>${midiToNote(v.note)}</td>
                                <td>${v.channel + 1}</td>
                                <td>
                                    <span class="panel-status">
                                        <span class="panel-status-dot ${v.releasing ? 'panel-status-dot--warning' : 'panel-status-dot--active'}"></span>
                                        ${v.releasing ? 'Release' : v.one_shot ? 'One-shot' : 'Playing'}
                                    </span>
                                </td>
                            </tr>
                        `)}
                    </tbody>
                </table>`
            }

            ${Object.keys(ccState).length > 0 ? html`
                <div class="panel-section">CC State</div>
                ${Object.entries(ccState).map(([cc, val]) => html`
                    <div class="panel-kv" key=${cc}>
                        <span class="panel-kv-label">CC ${cc}</span>
                        <span class="panel-kv-value">${val}</span>
                    </div>
                `)}
            ` : null}
        </div>
    `;
}

registerPanel('subsample.voices', VoicesPanel);
