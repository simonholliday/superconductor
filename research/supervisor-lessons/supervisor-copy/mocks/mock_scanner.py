#!/usr/bin/env python3
"""Mock scanner server for dashboard testing."""
import asyncio
import json
import random
import time

import websockets

MANIFEST = {
    "type": "manifest",
    "app": "substation",
    "label": "substation",
    "color": "#d2a8ff",
    "panels": [
        {"id": "substation.channels", "name": "Channels", "description": "Channel states, frequencies, SNR levels", "default_w": 6, "default_h": 6, "min_w": 4, "min_h": 3},
        {"id": "substation.recordings", "name": "Recordings", "description": "Active and recent recordings", "default_w": 6, "default_h": 4, "min_w": 4, "min_h": 3},
    ],
}

CHANNELS = [446.00625, 446.01875, 446.03125, 446.04375, 446.05625, 446.06875, 446.08125, 446.09375]


async def handler(ws):
    active = {}
    recent = []
    print(f"Client connected: {ws.remote_address}", flush=True)
    try:
        await ws.send(json.dumps(MANIFEST))
        print("Manifest sent, entering state loop", flush=True)
        while True:
            # Randomly toggle channels
            for freq in list(CHANNELS):
                if freq in active and random.random() < 0.05:
                    recent.insert(0, {
                        "channel_index": CHANNELS.index(freq) + 1,
                        "frequency_mhz": freq,
                        "file_path": f"/audio/recording_{int(time.time())}.wav",
                        "duration_s": round(time.time() - active[freq], 1),
                    })
                    recent = recent[:10]
                    del active[freq]
                elif freq not in active and random.random() < 0.02:
                    active[freq] = time.time()

            channels = []
            active_recs = []
            for i, freq in enumerate(CHANNELS):
                is_active = freq in active
                dur = round(time.time() - active[freq], 1) if is_active else 0
                channels.append({
                    "index": i + 1,
                    "frequency_mhz": freq,
                    "is_active": is_active,
                    "snr_db": round(random.uniform(8, 25), 1) if is_active else round(random.uniform(-20, -5), 1),
                })
                if is_active:
                    active_recs.append({"channel_index": i + 1, "frequency_mhz": freq, "duration_s": dur})

            state = {
                "type": "state",
                "data": {
                    "band": {
                        "name": "PMR446",
                        "freq_start_mhz": 446.0,
                        "freq_end_mhz": 446.1,
                        "channel_spacing_khz": 12.5,
                        "modulation": "NFM",
                        "channel_count": len(CHANNELS),
                    },
                    "channels": channels,
                    "recordings": {"active": active_recs, "recent": recent},
                    "noise_floor_db": round(-85.0 + random.uniform(-2, 2), 1),
                    "warmup_complete": True,
                },
            }
            await ws.send(json.dumps(state))
            await asyncio.sleep(0.5)
    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected", flush=True)
    except Exception as e:
        print(f"Handler error: {e}", flush=True)
        import traceback; traceback.print_exc()


async def main():
    async with websockets.serve(handler, "0.0.0.0", 19004):
        print("Mock scanner on ws://localhost:19004")
        await asyncio.Future()


asyncio.run(main())
