# Tools

Everything here runs beside a service rather than inside it. None is part of the
package: they speak the same protocol a panel speaks, over the same socket, so
what they measure or move is what a panel would.

## Probes

Stand-ins for the glass, for measuring the loop without a browser or a finger.

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
they found it. `probe_panel.py` finds its own target: the first step grid any
connected app declares, and the first row of it. It used to name a control and a
voice of one particular drum machine, which made it a probe for one composition
while saying it was a probe for any.

## Keeping a pattern across a restart

**A pattern edited on the glass does not survive restarting the composition it
belongs to.** It lives in `composition.data` and nothing writes it down
(Subroutine #2067). That has cost real work more than once, and it will keep
costing it until #2067 is settled — so until then these two exist, and the habit
is to run the first before restarting anything.

| File | What it does |
| --- | --- |
| `capture_state.py` | Joins as a panel, keeps the first snapshot of every connected app, and writes it out. Defaults to `/home/si/superintendent-state.json` — on disk rather than in tmpfs, so it survives a reboot as well as a restart. |
| `restore_state.py` | Replays that file through the panel's own socket, every value as an ordinary `set`. Nothing reaches into a composition, so a restore is exactly as legitimate as a tap. |

```
python tools/capture_state.py [where-to-write.json]
python tools/restore_state.py [what-to-read.json]
```

Two things to know about a restore. **It is additive and cannot clear**, so a
composition that seeds an opening pattern comes back with that pattern *plus*
whatever was captured. And **a capture carries the contract it was taken under**:
a file older than 1.12.0 is converted by reading the live manifest, because a
note at position 12 meant step 12 in the old shape and two steps in the new one,
and both look like a pattern.

## Running a composition that talks

| File | What it does |
| --- | --- |
| `play_loudly.py` | Runs a composition with logging configured, so every `LOG.info` in the adapter — the link connecting, a setting asserted to an instrument, a refusal — is printed instead of going nowhere. |

```
python tools/play_loudly.py compositions/drm1_grid.py
```

Identical to running the composition directly, except that it talks. A
composition configures no logging of its own, which is right for playing and
wrong for diagnosing: it once cost an evening, with the panel's settings
appearing dead and the sentence saying why being written to a logger that had no
handler.
