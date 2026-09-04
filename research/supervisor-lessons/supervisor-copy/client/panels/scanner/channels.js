import { h } from 'https://esm.sh/preact@10.19.6';
import htm from 'https://esm.sh/htm@3.1.1';
import { registerPanel } from '../registry.js';
import { LedMeter } from '../../components/led-meter.js';
import { valueToOpacity } from '../../components/utils.js';

const html = htm.bind(h);

function ChannelsPanel({ state, connected }) {
    if (!connected) {
        return html`<div class="panel-disconnected">Scanner not connected</div>`;
    }
    if (!state) {
        return html`<div class="panel-disconnected">Waiting for data\u2026</div>`;
    }

    const channels = state.channels || [];
    if (channels.length === 0) {
        return html`<div class="panel-empty">No channels configured</div>`;
    }

    const band = state.band || {};

    return html`
        <div>
            <div style="margin-bottom: 8px; font-size: 0.85rem">
                <div><span class="panel-kv-label">Band: </span>${band.name || '---'}</div>
                <div><span class="panel-kv-label">Range: </span>${band.freq_start_mhz || '?'} \u2013 ${band.freq_end_mhz || '?'} MHz ${band.modulation ? `(${band.modulation})` : ''}</div>
                <div><span class="panel-kv-label">Noise floor: </span>${state.noise_floor_db != null ? state.noise_floor_db.toFixed(1) + ' dB' : '---'}</div>
            </div>
            <table class="panel-table">
                <thead><tr>
                    <th>#</th><th>Frequency</th><th>Status</th><th>SNR</th>
                </tr></thead>
                <tbody>
                    ${channels.map(ch => {
                        const snr = Math.max(0, ch.snr_db != null ? ch.snr_db : 0);
                        const rowOpacity = valueToOpacity(snr, 0, 24);
                        return html`
                        <tr key=${ch.index} class="${ch.is_active ? 'panel-table-row--active' : ''}" style="opacity: ${rowOpacity.toFixed(2)}">
                            <td>${ch.index ?? ''}</td>
                            <td>${ch.frequency_mhz != null ? ch.frequency_mhz.toFixed(3) + ' MHz' : '---'}</td>
                            <td><span class="panel-status">
                                <span class="panel-status-dot ${ch.is_active ? 'panel-status-dot--active' : 'panel-status-dot--inactive'}"></span>
                                ${ch.is_active ? 'Active' : 'Idle'}
                            </span></td>
                            <td style="white-space: nowrap"><${LedMeter} value=${snr} min=${0} max=${24} segments=${10} />${' '}${ch.snr_db != null ? snr.toFixed(1) + ' dB' : '---'}</td>
                        </tr>
                    `; })}
                </tbody>
            </table>
        </div>
    `;
}

registerPanel('substation.channels', ChannelsPanel);
