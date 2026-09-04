import { h } from 'https://esm.sh/preact@10.19.6';
import htm from 'https://esm.sh/htm@3.1.1';
import { registerPanel } from '../registry.js';

const html = htm.bind(h);

function RecorderPanel({ state, connected }) {
    if (!connected) {
        return html`<div class="panel-disconnected">Sampler not connected</div>`;
    }
    if (!state) {
        return html`<div class="panel-disconnected">Waiting for data\u2026</div>`;
    }

    const rec = state.recorder || {};
    const enabled = rec.enabled !== false;
    const queue = rec.queue_depth || 0;
    const backlog = rec.backlog || false;

    return html`
        <div>
            <div class="panel-kv">
                <span class="panel-kv-label">Recording</span>
                <span class="panel-kv-value">
                    <span class="panel-status">
                        <span class="panel-status-dot ${enabled ? 'panel-status-dot--active' : 'panel-status-dot--inactive'}"></span>
                        ${enabled ? 'Enabled' : 'Disabled'}
                    </span>
                </span>
            </div>
            <div class="panel-kv">
                <span class="panel-kv-label">Queue</span>
                <span class="panel-kv-value">${queue}</span>
            </div>
            ${backlog ? html`
                <div class="panel-kv">
                    <span class="panel-kv-label">Status</span>
                    <span class="panel-kv-value" style="color: var(--color-warning)">
                        <span class="panel-status">
                            <span class="panel-status-dot panel-status-dot--warning"></span>
                            Backlog
                        </span>
                    </span>
                </div>
            ` : null}
        </div>
    `;
}

registerPanel('subsample.recorder', RecorderPanel);
