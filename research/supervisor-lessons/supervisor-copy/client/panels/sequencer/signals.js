import { h } from 'https://esm.sh/preact@10.19.6';
import htm from 'https://esm.sh/htm@3.1.1';
import { registerPanel } from '../registry.js';

const html = htm.bind(h);

function SignalsPanel({ state, connected }) {
    if (!connected) {
        return html`<div class="panel-disconnected">Sequencer not connected</div>`;
    }
    if (!state) {
        return html`<div class="panel-disconnected">Waiting for data\u2026</div>`;
    }

    const signals = state.signals || {};
    const entries = Object.entries(signals);

    if (entries.length === 0) {
        return html`<div class="panel-empty">No signals</div>`;
    }

    return html`
        <div>
            ${entries.map(([name, value]) => {
                const pct = Math.min(100, Math.max(0, value * 100));
                return html`
                    <div class="panel-gauge" key=${name}>
                        <div class="panel-gauge-header">
                            <span class="panel-gauge-label">${name}</span>
                            <span class="panel-gauge-value">${(typeof value === 'number') ? value.toFixed(2) : value}</span>
                        </div>
                        <div class="panel-gauge-track">
                            <div class="panel-gauge-fill" style="width: ${pct.toFixed(0)}%; background: var(--color-app-subsequence)"></div>
                        </div>
                    </div>
                `;
            })}
        </div>
    `;
}

registerPanel('subsequence.signals', SignalsPanel);
