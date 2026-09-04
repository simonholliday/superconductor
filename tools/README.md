# Probes

Stand-ins for the glass, for measuring the loop without a browser or a finger.
They speak the real protocol over a real socket, so what they measure is what a
panel would experience.

Every timing figure quoted in Subroutine for the first use-case came from these:
tap-to-acknowledgement, the beat cadence, and the pause and resume behaviour that
#2054 was tested against.

| File | What it answers |
| --- | --- |
| `probe_panel.py` | Does a tap reach the app and come back, and how long does it take? Connects, reads the manifest and snapshot, switches one cell on and off again, and times each acknowledgement. |
| `probe_transport.py` | Does the transport hold the clock, and does resuming dump the beats it held? Pauses, counts beats while held, resumes and counts them again, then exercises the tempo including a value it should refuse. |

Run either against a service with an app dialled in:

```
python tools/probe_panel.py
python tools/probe_transport.py
```

Both assume `ws://127.0.0.1:8090/ws/panel`, and both leave the composition as
they found it.
