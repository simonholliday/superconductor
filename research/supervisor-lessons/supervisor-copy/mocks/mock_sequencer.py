#!/usr/bin/env python3
"""Mock sequencer server for dashboard testing."""
import asyncio
import json

import websockets

MANIFEST = {
    "type": "manifest",
    "app": "subsequence",
    "label": "subsequence",
    "color": "#58a6ff",
    "panels": [
        {"id": "subsequence.transport", "name": "Transport", "description": "BPM, bar, beat, section, chord", "default_w": 12, "default_h": 2, "min_w": 6, "min_h": 2},
        {"id": "subsequence.patterns", "name": "Patterns", "description": "Piano roll view", "default_w": 6, "default_h": 6, "min_w": 4, "min_h": 3},
        {"id": "subsequence.signals", "name": "Signals", "description": "Conductor signals", "default_w": 6, "default_h": 4, "min_w": 3, "min_h": 2},
    ],
}

bar = 0


async def handler(ws):
    global bar
    try:
        await ws.send(json.dumps(MANIFEST))
        while True:
            bar += 1
            beat = (bar % 4) + 1
            state = {
                "type": "state",
                "data": {
                    "bpm": 120.0,
                    "key": "E",
                    "chord": "Cmaj7",
                    "section": "Verse",
                    "section_bar": (bar % 8) + 1,
                    "section_bars": 8,
                    "next_section": "Chorus",
                    "global_bar": bar,
                    "global_beat": beat,
                    "playhead_pulse": bar * 96 + (beat - 1) * 24,
                    "pulses_per_beat": 24,
                    "patterns": [
                        {
                            "name": "drums",
                            "muted": False,
                            "length_pulses": 96,
                            "drum_map": {"kick": 36, "snare": 38},
                            "notes": [
                                {"p": 36, "s": 0, "d": 1.0, "v": 100},
                                {"p": 38, "s": 24, "d": 0.5, "v": 90},
                                {"p": 36, "s": 48, "d": 1.0, "v": 80},
                                {"p": 38, "s": 72, "d": 0.5, "v": 95},
                            ],
                        },
                        {
                            "name": "bass",
                            "muted": False,
                            "length_pulses": 96,
                            "drum_map": None,
                            "notes": [
                                {"p": 40, "s": 0, "d": 2.0, "v": 90},
                                {"p": 43, "s": 48, "d": 2.0, "v": 85},
                            ],
                        },
                    ],
                    "signals": {
                        "intensity": 0.5 + 0.3 * (bar % 10) / 10,
                        "density": 0.3,
                        "energy": 0.7,
                    },
                },
            }
            await ws.send(json.dumps(state))
            await asyncio.sleep(0.1)
    except websockets.exceptions.ConnectionClosed:
        pass


async def main():
    async with websockets.serve(handler, "0.0.0.0", 18765):
        print("Mock sequencer on ws://localhost:18765")
        await asyncio.Future()


asyncio.run(main())
