#!/usr/bin/env python3
"""Mock sampler server for dashboard testing."""
import asyncio
import json
import random

import websockets

MANIFEST = {
    "type": "manifest",
    "app": "subsample",
    "label": "subsample",
    "color": "#3fb950",
    "panels": [
        {"id": "subsample.voices", "name": "MIDI Activity", "description": "Active voices, CC state", "default_w": 6, "default_h": 4, "min_w": 3, "min_h": 3},
        {"id": "subsample.library", "name": "Library", "description": "Sample count, memory, recent", "default_w": 6, "default_h": 4, "min_w": 3, "min_h": 3},
        {"id": "subsample.recorder", "name": "Recorder", "description": "Recording state", "default_w": 4, "default_h": 2, "min_w": 3, "min_h": 2},
    ],
}

SAMPLE_NAMES = ["kick_deep", "snare_bright", "hihat_closed", "pad_warm", "bass_sub", "click_wood"]
tick = 0


async def handler(ws):
    global tick
    try:
        await ws.send(json.dumps(MANIFEST))
        voices = []
        while True:
            tick += 1
            if random.random() < 0.15 and len(voices) < 8:
                voices.append({
                    "note": random.randint(36, 84),
                    "channel": 0,
                    "velocity": random.randint(60, 127),
                    "sample_name": random.choice(SAMPLE_NAMES),
                    "releasing": False,
                })
            if random.random() < 0.2 and voices:
                voices.pop(random.randint(0, len(voices) - 1))

            state = {
                "type": "state",
                "data": {
                    "playback": {
                        "voices": voices,
                        "polyphony_limit": 16,
                        "cc_state": {"1": random.randint(0, 127), "11": 80},
                    },
                    "library": {
                        "sample_count": 342 + tick // 50,
                        "memory_used_mb": round(45.3 + random.uniform(-2, 2), 1),
                        "memory_limit_mb": 100.0,
                        "recent_samples": [
                            {
                                "name": f"sample_{342 + tick // 50 - i}",
                                "duration": round(random.uniform(0.5, 5.0), 2),
                                "pitch_hz": round(random.uniform(80, 800), 1),
                                "pitch_class": random.randint(0, 11),
                                "tempo_bpm": round(random.uniform(80, 160), 1),
                            }
                            for i in range(3)
                        ],
                    },
                    "recorder": {
                        "enabled": True,
                        "queue_depth": random.randint(0, 3),
                        "backlog": False,
                    },
                },
            }
            await ws.send(json.dumps(state))
            await asyncio.sleep(0.1)
    except websockets.exceptions.ConnectionClosed:
        pass


async def main():
    async with websockets.serve(handler, "0.0.0.0", 19003):
        print("Mock sampler on ws://localhost:19003")
        await asyncio.Future()


asyncio.run(main())
