"""Research prototype (playhead): error budget for the playing-cell highlight, from measured inputs.
Terms are in ms.  Positive = highlight later than the sound at the drum machine's MIDI input.
Sound reference: the MIDI note_on leaving the sequencer (device latency compensation shifts every
device by max_latency - device_latency, so the panel offset should include max_latency)."""
import json
def show(title, rows):
	print(f"\n{title}")
	for name, typ, best, worst in rows: print(f"  {name:58s} {typ:9s} {best:>8} {worst:>8}")
# Measured on the workstation (this session) and by #1920:
server_listener = (0.1, 0.4)        # beat listener after ideal pulse, 120 BPM spin-wait; 1.4 at 180 BPM
ws_oneway_lan   = (0.4, 2.0)        # #1920: 0.41 ms loopback median, +~1 ms wired LAN; p99 0.8 loopback
ws_oneway_wifi  = (2.0, 80.0)       # #1920: Wi-Fi tail 50-80 ms (NSDI 26 Law paper), ordinary 2-10 ms
frame           = (0.0, 16.7)       # 60 Hz frame quantisation: uniform 0..16.7, mean 8.3
panel_response  = (5.0, 5.0)        # 5 ms GtG (vendor spec via resellers); pixel transition
offset_est      = (0.1, 1.5)        # NTP-style over WS: sd 0.04 ms Chromium / 0.3 ms Firefox loopback; asymmetry up to rtt/2 on LAN
for tempo in (60, 120, 180):
	step = 60000/tempo/4  # 16th note step length
	pulse = 60000/tempo/24
	print(f"\n=== {tempo} BPM: 16th step {step:.1f} ms, pulse {pulse:.1f} ms")
	# A. server-pushed beat event, client extrapolates the 4 steps inside the beat from tempo
	rows = [("server beat listener after MIDI send", "fixed", *server_listener),
		("WebSocket one-way, wired LAN", "jitter", *ws_oneway_lan),
		("frame quantisation (60 Hz)", "jitter", *frame),
		("panel pixel response", "fixed", *panel_response)]
	tot_b = sum(r[2] for r in rows); tot_w = sum(r[3] for r in rows)
	show("A: server-pushed beat + in-beat extrapolation (steps 2-4 inherit the beat's arrival error)", rows)
	print(f"  {'total, wired LAN':58s} {'':9s} {tot_b:8.1f} {tot_w:8.1f}   as % of step: {100*tot_b/step:.0f}% .. {100*tot_w/step:.0f}%")
	print(f"  {'total, Wi-Fi tail':58s} {'':9s} {'':8} {tot_w - ws_oneway_lan[1] + ws_oneway_wifi[1]:8.1f}")
	# B. client extrapolation from anchor (pulse, server time) + offset estimate; network jitter removed
	rows = [("server timestamp taken in listener (after MIDI send)", "fixed", *server_listener),
		("clock offset estimate error", "slow", *offset_est),
		("frame quantisation (60 Hz)", "jitter", *frame),
		("panel pixel response", "fixed", *panel_response)]
	tot_b = sum(r[2] for r in rows); tot_w = sum(r[3] for r in rows)
	show("B: anchored extrapolation (server time on each beat, offset from ping/pong): network jitter drops out", rows)
	print(f"  {'total':58s} {'':9s} {tot_b:8.1f} {tot_w:8.1f}   as % of step: {100*tot_b/step:.0f}% .. {100*tot_w/step:.0f}%")
	print(f"  drift between anchors if tempo changes unannounced: 1 BPM at {tempo} over one beat = {abs(60000/tempo - 60000/(tempo+1)):.1f} ms")
	# C. server-pushed pulse events (24/beat), no extrapolation
	rows = [("server pulse listener after MIDI send", "fixed", 0.1, 1.1),
		("WebSocket one-way, wired LAN", "jitter", *ws_oneway_lan),
		("frame quantisation (60 Hz)", "jitter", *frame),
		("panel pixel response", "fixed", *panel_response)]
	print(f"  C: per-pulse push would add 24 frames/beat = {24*tempo/60:.0f} msg/s per client and quantise to {pulse:.1f} ms; same budget as A minus in-beat extrapolation error, which is zero at fixed tempo anyway")
	# legacy: 100 ms polling
	print(f"  legacy web_ui 100 ms tick: position error uniform 0..100 ms = {100/step:.1f} steps at this tempo")
