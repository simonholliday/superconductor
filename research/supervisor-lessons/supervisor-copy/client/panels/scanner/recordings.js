import { h } from 'https://esm.sh/preact@10.19.6';
import htm from 'https://esm.sh/htm@3.1.1';
import { registerPanel } from '../registry.js';
import { AudioPlayer } from '../../components/audio-player.js';

const html = htm.bind(h);

function RecordingsPanel({ state, connected, baseUrl }) {
    if (!connected) {
        return html`<div class="panel-disconnected">Scanner not connected</div>`;
    }
    if (!state) {
        return html`<div class="panel-disconnected">Waiting for data\u2026</div>`;
    }

    const recordings = state.recordings || {};
    const active = recordings.active || [];
    const recent = recordings.recent || [];

    if (active.length === 0 && recent.length === 0) {
        return html`<div class="panel-empty">No recordings</div>`;
    }

    return html`
        <div>
            <div class="panel-section">Active Recordings</div>
            ${active.length === 0
                ? html`<div class="panel-empty" style="padding: 8px 0">None</div>`
                : html`<table class="panel-table">
                    <thead><tr><th>Ch</th><th>Frequency</th><th>Duration</th></tr></thead>
                    <tbody>
                        ${active.map((r, i) => html`
                            <tr class="panel-table-row--active" key=${i}>
                                <td>${r.channel_index ?? ''}</td>
                                <td>${r.frequency_mhz != null ? r.frequency_mhz.toFixed(3) + ' MHz' : '---'}</td>
                                <td>${r.duration_s != null ? r.duration_s.toFixed(1) + 's' : '---'}</td>
                            </tr>
                        `)}
                    </tbody>
                </table>`
            }

            <div class="panel-section">Recent Recordings</div>
            ${recent.length === 0
                ? html`<div class="panel-empty" style="padding: 8px 0">None</div>`
                : html`<ul class="panel-log">
                    ${recent.map((r, i) => {
                        const filename = r.filename || 'recording';
                        const audioSrc = r.path && baseUrl ? `${baseUrl}/audio/${r.path}` : '';
                        return html`
                            <li class="panel-log-item" key=${i}>
                                <span class="panel-log-time">Ch ${r.channel_index}</span>
                                ${audioSrc ? html`<${AudioPlayer} src=${audioSrc} />` : null}
                                <span class="panel-log-message">${filename} (${r.duration_s != null ? r.duration_s.toFixed(1) + 's' : '---'})</span>
                            </li>
                        `;
                    })}
                </ul>`
            }
        </div>
    `;
}

registerPanel('substation.recordings', RecordingsPanel);
