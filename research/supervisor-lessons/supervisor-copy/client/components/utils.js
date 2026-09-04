/**
 * Shared utility functions for panel rendering.
 */

/**
 * Map a value to an opacity for visual emphasis.
 *
 * Returns an opacity between `floor` and 1.0, using a square root curve
 * so that low values rise quickly and high values compress. Values at or
 * below `min` return `floor`; values at or above `max` return 1.0.
 *
 *   valueToOpacity(snr, 0, 24)          // SNR in dB
 *   valueToOpacity(velocity, 0, 127)    // MIDI velocity
 *
 * @param {number} value   — the input value
 * @param {number} min     — value at or below which opacity = floor
 * @param {number} max     — value at or above which opacity = 1.0
 * @param {number} [floor] — minimum opacity (default 0.2)
 * @returns {number} opacity between floor and 1.0
 */
export function valueToOpacity(value, min, max, floor = 0.2) {
    const norm = Math.max(0, Math.min(1, (value - min) / (max - min)));
    return floor + (1 - floor) * Math.sqrt(norm);
}
