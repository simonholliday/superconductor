import { h } from 'https://esm.sh/preact@10.19.6';
import htm from 'https://esm.sh/htm@3.1.1';
import { registerPanel } from '../registry.js';
import { AudioPlayer } from '../../components/audio-player.js';

const html = htm.bind(h);

const PITCH_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];

function LibraryPanel({ state, connected, baseUrl }) {
    if (!connected) {
        return html`<div class="panel-disconnected">Sampler not connected</div>`;
    }
    if (!state) {
        return html`<div class="panel-disconnected">Waiting for data\u2026</div>`;
    }

    const lib = state.library || {};
    const used = lib.memory_used_mb || 0;
    const limit = lib.memory_limit_mb || 100;
    const pct = limit > 0 ? (used / limit * 100) : 0;
    const memColor = pct > 80 ? 'var(--color-warning)' : 'var(--color-app-subsample)';
    const recent = lib.recent_samples || [];

    return html`
        <div>
            <div class="panel-kv">
                <span class="panel-kv-label">Samples</span>
                <span class="panel-kv-value">${lib.sample_count || 0}</span>
            </div>

            <div class="panel-gauge">
                <div class="panel-gauge-header">
                    <span class="panel-gauge-label">Memory</span>
                    <span class="panel-gauge-value">${used.toFixed(1)} / ${limit.toFixed(0)} MB</span>
                </div>
                <div class="panel-gauge-track">
                    <div class="panel-gauge-fill" style="width: ${pct.toFixed(0)}%; background: ${memColor}"></div>
                </div>
            </div>

            ${recent.length > 0 ? html`
                <div class="panel-section">Recent Samples</div>
                <table class="panel-table">
                    <thead><tr><th>Name</th><th>Dur</th><th>Pitch</th><th>BPM</th><th></th></tr></thead>
                    <tbody>
                        ${recent.map((s, i) => {
                            const audioSrc = s.path && baseUrl ? `${baseUrl}/audio/${s.path}` : '';
                            return html`
                            <tr key=${i}>
                                <td style="max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap">${s.name}</td>
                                <td>${s.duration != null ? s.duration.toFixed(1) + 's' : '---'}</td>
                                <td>${s.pitch_class >= 0 ? PITCH_NAMES[s.pitch_class] || '?' : '---'}</td>
                                <td>${s.tempo_bpm ? s.tempo_bpm.toFixed(0) : '---'}</td>
                                <td>${audioSrc ? html`<${AudioPlayer} src=${audioSrc} />` : null}</td>
                            </tr>
                        `; })}
                    </tbody>
                </table>
            ` : null}
        </div>
    `;
}

registerPanel('subsample.library', LibraryPanel);
