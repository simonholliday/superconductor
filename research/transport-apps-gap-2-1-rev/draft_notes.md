# Revision plan for #2033 (working notes, not the filed body)

## Verified this session

- #1916 live, version 1: message table `set` = "Explicit new value on a leaf, a grid row or a grid cell";
  sub-paths paragraph: "a `set` on a row carries a row array that replaces the row, a `set` on a cell
  carries a partial `cell` merged into it"; worked drum leaf
  `{"id": "grid", "kind": "grid", "path": "/subsequence/kit/grid", "value": "cells", "access": "rw", ...}`.
  So a whole-grid paste is ONE leaf `set` carrying a `cells` object, and a row clear is ONE row `set`.
- Spec line 93: the grid is "sixteen by eight", so a row is 16 columns and 128 is the whole grid.
- #1920: after a reconnect's snapshot the client "re-sends every pending `set` with its original `seq`,
  in order"; a pending set unacknowledged for 5 s reverts. That is the one genuine inbound burst.
- #1928: "one adapter module in each package, own daemon thread and loop, one outbound WebSocket to the
  service" -> every panel's writes reach one app on one connection.
- #1925: "Every `ack`, `changed` and `cycle` frame enters one ordered log on the loop at the moment of
  application and a link thread drains it."
- #1971 verbatim: "It costs nothing on the wire (one set per cell)".
- CPython 3.12.3: wait_for at tasks.py:472, the `timeout is not None and timeout <= 0` branch at 507;
  `_wait` at 522-563 (call_later 531, add_done_callback 547, remove 555, partition 557-562,
  return 563). NOT 521-561.
- selectors.py:451-459 EpollSelector.select rounding; base_events.py:1941-1949 zero timeout when ready;
  call_soon 785, _call_soon's `self._ready.append` 818, call_soon_threadsafe 838-846 with
  `_write_to_self` 845; selector_events.py _write_to_self 141, `csock.send(b'\0')` 152.
- sequencer.py:465 `self._spin_threshold: float = 0.001`; spin 1556-1562; CC comment 770-772 with the
  write at 803; reschedule_pulse emit 1804; beat emit 1427.
- websockets 17.1 asyncio/connection.py:261 cancellation guarantee; recv 250, recv_streaming 328, no
  timeout parameter on either.
- #2025 raw: ws-coalesce burst 1024 -> wakeups 1299, batch_mean 6.306, batch_max 76 (NOT "about 162").
- #2025 raw: ws-thread 25 Hz over_1ms 36 and 48; ws-coalesce 25 Hz 26 and 35 (so "26 to 48" is wrong for
  the no-device column).
- Block F's baseline itself logged over_1ms 25 at p99 1.4775 with load 0.99->1.65; run_g.sh has no
  `--rate 25` line.

## Consequence

The inbound bulk burst that read-batching collapses is not what the envelope in force produces for the
edits the design named. What remains is the reconnect re-send. Read-batching's whole measured gain over
per-message crossing is one late pulse of about 1.2 ms in 1536; its costs are a longer lone crossing, a
12 to 20 ms crossing tail inside a burst, another panel's tap held behind the batch, an unbounded batch
against a bounded queue, a bounded drain that can split a bulk edit across a rebuild, and a probe that
fails invisibly. So the recommendation becomes option 2, cross per message, with a bounded read batch
named as the device to add if #2008 shows the wake-up count matters on the server.
