"""Research prototype (playhead, revision): error budget for the playing-cell highlight with the
presentation-pipeline term and the app-to-service clock term added.  Terms in ms.  Positive = the
highlight appears after the MIDI note_on left the sequencer."""
server_listener = (0.1, 0.4)   # beat listener after that pulse's note_on send, all tempi (events_*.json)
app_service_c   = (0.0, 0.0)   # #1919 shape C: adapter and service share the host's clock
app_service_b   = (0.1, 1.0)   # #1919 shape B: NTP-style offset over the adapter link, wired LAN asymmetry bound (#1920 ICMP 0.5-1.8 ms)
offset_lan      = (0.1, 1.5)   # browser-to-service offset: loopback sd 0.04 (Chromium) / 0.3 (Firefox); wired LAN asymmetry bound
frame           = (0.0, 16.7)  # wait for the next rAF callback at 60 Hz: uniform
present_1       = (16.7, 16.7) # rAF callback to glass: one vsync (web.dev rvfc article)
present_2       = (16.7, 33.3) # the same when the compositor adds a frame (hardware-gated)
pixel           = (5.0, 5.0)   # 5 ms GTG (#1917 datasheet)
def tot(rows): return sum(r[0] for r in rows), sum(r[1] for r in rows)
for shape, app in (("C co-located", app_service_c), ("B separate host", app_service_b)):
	print(f"\n=== Option B (anchored extrapolation), topology {shape}")
	base = [server_listener, app, offset_lan, frame, pixel]
	b, w = tot(base)
	print(f"  position computed for the presentation time (callback time + one frame): {b:.1f} .. {w:.1f} ms; pipeline depth off by one frame shifts this by +-16.7")
	b1, w1 = tot(base + [present_1])
	print(f"  position computed at callback time, one-vsync pipeline:              {b1:.1f} .. {w1:.1f} ms")
	b2, w2 = tot(base + [present_2])
	print(f"  position computed at callback time, compositor adds a frame:          {b2:.1f} .. {w2:.1f} ms")
	for tempo in (60, 120, 180):
		step = 60000/tempo/4
		print(f"  {tempo} BPM: 16th step {step:.1f} ms; compensated worst {100*w/step:.0f}% of a step, uncompensated one-vsync worst {100*w1/step:.0f}%")
print("\nPanel input lag (signal to pixel) is not carried: unmeasured, hardware-gated.")
print("Option A adds WebSocket one-way 0.4-2.0 ms wired, up to 80 ms Wi-Fi tail (#1920) to every row.")
