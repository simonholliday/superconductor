import { h } from 'https://esm.sh/preact@10.19.6';
import { useState, useRef } from 'https://esm.sh/preact@10.19.6/hooks';
import htm from 'https://esm.sh/htm@3.1.1';

const html = htm.bind(h);

// Module-level: only one audio plays at a time.
let _activePlayer = null;  // { audio, stop() }

/**
 * Inline audio play button.
 *
 * Props:
 *   src  (string) — URL of the audio file to play
 */
export function AudioPlayer({ src }) {
    const [playing, setPlaying] = useState(false);
    const audioRef = useRef(null);

    function stop() {
        if (audioRef.current) {
            audioRef.current.pause();
            audioRef.current = null;
        }
        if (_activePlayer?.stop === stop) _activePlayer = null;
        setPlaying(false);
    }

    function toggle() {
        if (!src) return;

        if (playing) {
            stop();
        } else {
            // Stop any other player first.
            if (_activePlayer) _activePlayer.stop();

            const audio = new Audio(src);
            audio.onended = () => stop();
            audio.onerror = () => stop();
            audioRef.current = audio;
            _activePlayer = { audio, stop };
            audio.play();
            setPlaying(true);
        }
    }

    return html`
        <button onClick=${toggle}
            style="background: transparent; border: none; cursor: pointer; color: ${playing ? 'var(--color-active)' : 'var(--color-text-muted)'}; font-size: 0.85rem; padding: 0 4px"
            title=${playing ? 'Stop' : 'Play'}
        >${playing ? '\u25A0' : '\u25B6'}</button>
    `;
}
