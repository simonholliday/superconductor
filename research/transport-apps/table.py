"""Prototype: render results/adapter_bench.jsonl as the Markdown table for the finding."""
import json, sys

LABEL = {
	"baseline": "Baseline, nothing else in the process",
	"osc-loop": "OSC: `AsyncIOOSCUDPServer` on the clock loop (Subsequence's `osc.py` shape), apply inline",
	"osc-thread": "OSC: `BlockingOSCUDPServer` on a daemon thread, `call_soon_threadsafe` per datagram",
	"osc-thread-drain": "OSC: same server on a thread, datagrams queued, drained at the `beat` event",
	"ws-loop": "WebSocket client link on the clock loop, apply inline",
	"ws-thread": "WebSocket client link on a daemon thread with its own loop, `call_soon_threadsafe` per message",
	"tcp-thread": "TCP newline-JSON client link, reader thread, `call_soon_threadsafe` per message",
}
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
print("| Adapter shape inside the sequencer process | Selector | Inbound rate | Median | P95 | P99 | Max | Pulses over 1 ms (of 1536) | Commands applied / frames pushed |")
print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
for r in rows:
	rate = f"{r['rate_hz']:.0f} Hz" if r["rate_hz"] else "none"
	print(f"| {LABEL[r['scenario']]} | {r['selector']} | {rate} | {r['median_ms']:.3f} ms | {r['p95_ms']:.3f} ms | {r['p99_ms']:.3f} ms | {r['max_ms']:.3f} ms | {r['over_1ms']} | {r['applied']} / {r['pushed']} |")
