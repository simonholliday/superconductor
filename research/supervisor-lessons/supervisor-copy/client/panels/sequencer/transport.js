import { h } from 'https://esm.sh/preact@10.19.6';
import htm from 'https://esm.sh/htm@3.1.1';
import { registerPanel } from '../registry.js';

const html = htm.bind(h);

function TransportPanel({ state, connected }) {
    if (!connected) {
        return html`<div class="panel-disconnected">Sequencer not connected</div>`;
    }
    if (!state) {
        return html`<div class="panel-disconnected">Waiting for data\u2026</div>`;
    }

    let sectionStr = state.section || '---';
    if (state.section && state.section_bars) {
        sectionStr = '[' + state.section + ' ' + state.section_bar + '/' + state.section_bars;
        if (state.next_section) sectionStr += ' \u2192 ' + state.next_section;
        sectionStr += ']';
    }

    return html`
        <div style="display: flex; flex-wrap: wrap; gap: 0 24px">
            <div class="panel-kv" style="min-width: 80px">
                <span class="panel-kv-label">BPM</span>
                <span class="panel-kv-value" style="color: var(--color-app-subsequence)">${state.bpm ? state.bpm.toFixed(1) : '---'}</span>
            </div>
            ${state.key ? html`
                <div class="panel-kv" style="min-width: 60px">
                    <span class="panel-kv-label">Key</span>
                    <span class="panel-kv-value" style="color: var(--color-app-subsequence)">${state.key}</span>
                </div>
            ` : ''}
            <div class="panel-kv" style="min-width: 70px">
                <span class="panel-kv-label">Bar</span>
                <span class="panel-kv-value" style="color: var(--color-app-subsequence)">${state.global_bar || 0}.${state.global_beat || 0}</span>
            </div>
            <div class="panel-kv" style="min-width: 180px">
                <span class="panel-kv-label">Section</span>
                <span class="panel-kv-value" style="color: var(--color-app-subsequence)">${sectionStr}</span>
            </div>
            <div class="panel-kv" style="min-width: 80px">
                <span class="panel-kv-label">Chord</span>
                <span class="panel-kv-value" style="color: var(--color-app-subsequence)">${state.chord || '---'}</span>
            </div>
        </div>
    `;
}

registerPanel('subsequence.transport', TransportPanel);
