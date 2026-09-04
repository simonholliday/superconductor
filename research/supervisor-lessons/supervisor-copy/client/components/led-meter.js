import { h } from 'https://esm.sh/preact@10.19.6';
import htm from 'https://esm.sh/htm@3.1.1';

const html = htm.bind(h);

/**
 * LED level meter — segmented indicator bar.
 *
 * Props:
 *   value     (number)  — current value
 *   min       (number)  — value where all segments are off (default 0)
 *   max       (number)  — value where all segments are on (default 100)
 *   segments  (number)  — number of LED blocks (default 8)
 *   scale     (string)  — 'linear' or 'log' (default 'linear')
 *   direction (string)  — 'horizontal' or 'vertical' (default 'horizontal')
 */
export function LedMeter({ value, min = 0, max = 100, segments = 8, scale = 'linear', direction = 'horizontal' }) {
    // Normalise value to 0–1
    let normalised;
    if (scale === 'log') {
        const range = max - min;
        normalised = range > 0 ? Math.log(Math.max(0, value - min) + 1) / Math.log(range + 1) : 0;
    } else {
        normalised = max > min ? (value - min) / (max - min) : 0;
    }
    normalised = Math.max(0, Math.min(1, normalised));

    const fillLevel = normalised * segments;
    const vertical = direction === 'vertical';

    const segs = [];
    for (let i = 0; i < segments; i++) {
        const segFill = Math.max(0, Math.min(1, fillLevel - i));
        const glowPx = segFill * 4;
        segs.push(html`
            <div class="led-meter-seg" style="opacity: ${0.08 + segFill * 0.92}; box-shadow: 0 0 ${glowPx}px rgba(255,255,255,${segFill * 0.6})" />
        `);
    }

    return html`<div class="led-meter ${vertical ? 'led-meter--vertical' : ''}">${segs}</div>`;
}
