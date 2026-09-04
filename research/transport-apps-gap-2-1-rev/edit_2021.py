"""Surgical edits to #2021's description, applied to the text fetched from the
instance so nothing else in it moves.  Research script, not house style."""

import sys

SRC = "/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad/transport-apps-gap-2-1-rev/2021_desc_current.md"
DST = "/tmp/claude-1000/-home-si/243c6ca9-504c-48de-a06d-eefc5c35da94/scratchpad/transport-apps-gap-2-1-rev/2021_desc_new.md"

EDITS = [
	(
		"Revised 2026-09-03 to carry #2025's measurements, which re-priced the table's B column and refuted both halves of the fallback the recommendation used to carry.",
		"Revised 2026-09-03 to carry #2025's measurements, which re-priced the table's B column and refuted both halves of the fallback the recommendation used to carry. Revised again 2026-09-04 by #2033, which corrected the reading of #1916 that the batching half of the recommendation rested on: the contract in force already carries a `set` on a grid row and on a grid leaf, so a row clear, a paste and a preset load are each one inbound frame, and the burst a batching device would collapse is not one the panel produces. B stands; the device inside it does not.",
	),
	(
		"| | A. Drain only at the sequencer's own hooks | B. Cross onto the loop for each grid set, batching at the socket read | C. Apply off the loop by whole-value replacement, never crossing |",
		"| | A. Drain only at the sequencer's own hooks | B. Cross onto the loop for each grid set, per message | C. Apply off the loop by whole-value replacement, never crossing |",
	),
	(
		"| Measured over a socket, a held paint gesture at 25 Hz | p99 0.065 to 0.136 ms, no pulse over 1 ms | p99 1.09 to 1.30 ms, maximum 1.38 to 1.69 ms, 26 to 48 pulses over 1 ms in 1536 |",
		"| Measured over a socket, a held paint gesture at 25 Hz | p99 0.065 to 0.136 ms, no pulse over 1 ms | p99 0.95 to 1.30 ms, maximum 1.12 to 1.69 ms, 9 to 48 pulses over 1 ms in 1536 across four blocks, with no consistent difference between crossing per message, the pending flag and batching at the socket read |",
	),
	(
		"against 26 to 48 late pulses for a tenth of that traffic spread evenly at 25 Hz",
		"against 18 to 48 late pulses for a tenth of that traffic spread evenly at 25 Hz",
	),
	(
		"and 25 Hz over a socket cost 26 to 48 pulses over 1 ms in 1536. Four times that traffic costs nothing at all.",
		"and 25 Hz over a socket cost 9 to 48 pulses over 1 ms in 1536 across four blocks, whichever crossing shape was used. Four times that traffic costs nothing at all.",
	),
	(
		"**Recommended: B, with batching at the socket read as the adapter's inbound rule.** Cross onto the loop as each grid set arrives, and let the link thread take every frame the connection can hand over without waiting on the network before it crosses.",
		"**Recommended: B, crossing per message, with no batching device in the adapter.** Cross onto the loop as each grid set arrives and apply it there.",
	),
	(
		"What B costs instead is 26 to 48 pulses in 1536 arriving about a millisecond late during a paint gesture",
		"What B costs instead is 9 to 48 pulses in 1536 arriving about a millisecond late during a paint gesture",
	),
	(
		"Five things changed in this recommendation on 2026-09-03, four of them from #2025 and one measured for this revision:",
		"Five things changed in this recommendation on 2026-09-03, four of them from #2025 and one measured for that revision; the first and the third were corrected again on 2026-09-04 and stand here as corrected:",
	),
	(
		"- **The pending flag is dropped and batching at the socket read takes its place.** The flag never fires below 500 Hz, adds about 0.05 ms to every crossing for the queue hop, and on a burst catches about nine frames rather than the burst. Read-batching costs the same nothing at a hand rate and takes a whole burst in one crossing. It is not free either: because the link thread keeps reading before it crosses, a frame early in a burst waits for the rest of it, so on bursts of 128 the crossing median was 1.29 ms with a p99 of 12.6 ms and a maximum of 15.8 ms, against a median of 0.07 ms and a p99 of 1.10 ms for the flag on the same traffic, and between 0.03 and 0.23 ms more than per-message marshalling across the hand-rate rows measured. That is the right trade: it lengthens the crossing only where the traffic is bulk and no cell is waiting on an `ack` a finger can feel, and it is two orders of magnitude inside the beat the drain rule costs.",
		"- **The pending flag is dropped and nothing takes its place.** The flag never fires below 500 Hz, adds about 0.05 ms to every crossing for the queue hop and a lock and a flag per frame, and on a burst catches about nine frames rather than the burst; it is dominated whichever neighbour it is set against. Batching at the socket read was recommended in its place on 2026-09-03 and is not any longer. At every rate a hand or a browser produces it *is* per-message crossing — 170 wake-ups for 170 messages at 5 Hz, 845 for 845 at 25 Hz, both with a largest batch of one — and it differs only on a burst, where its whole measured advantage on the clock is one late pulse of 1.17 ms in 1536 at 128 frames and none at all at 1024. Against that one pulse it costs about 0.2 ms more on every lone crossing, a crossing tail inside the burst measured at a 12.6 ms p99 at 128 frames and 20.0 ms at 1024, a second panel's tap held behind the batch (median 0.030 ms per message against 1.26 ms batched at 128 frames), an unbounded batch in front of #1928's bounded queue, and a probe that fails silently. What decided it is that the burst is largely hypothetical: under #1916 a row clear, a fill, a paste and a preset load are each one frame, so the only inbound burst the envelope produces is #1920's reconnect re-send. The device stays available and is filed as #2030; it is not needed now.",
	),
	(
		"the only genuine inbound bulk is a panel-side bulk edit (clear, fill, paste, load a preset), which read-batching already collapses. If a bulk edit's `ack` traffic is the worry, the fix is a batched `set` frame with one `seq` and one `ack`, which is a contract question and is filed separately.",
		"and a panel-side bulk edit — clear a row, fill it, paste, load a preset — is one frame already, because #1916 defines a `set` on a grid row as a row array replacing the row and on the grid leaf as a whole `cells` object. What is left inbound is #1920's reconnect re-send of pending sets, bounded by its 5 s pending timeout at roughly a hundred frames, which cost the clock one late pulse of about 1.2 ms in 1536 with no device at all. Whether the envelope should also gain a frame naming several paths at once is #2031.",
	),
	(
		"Worse, the cost peaks at about one wake-up per pulse, so a limiter that smooths a runaway client down to a fixed rate in the tens of hertz parks it on the worst point of the curve, and because that peak moves with tempo no fixed rate is safe at every tempo. The valve is therefore the bounded queue #1928 already specifies, which drops and counts when full, plus a `nack` and a close on sustained overrun — never a token bucket clamping to tens of hertz.",
		"So a limiter is pointless rather than harmful: what it would protect is not the clock. One band is worth avoiding, because the cost peaks at about one wake-up per pulse — 24 Hz at 60 BPM, 48 Hz at 120, 72 Hz at 180 — so a limiter clamping a runaway into the tens of hertz would put it where a human's own paint gesture already sits, which this document elsewhere calls worth admitting. Above 72 Hz the same measurements say a fixed ceiling is safe at every tempo in that range. The valve that is actually needed is the bounded queue #1928 already specifies, which drops and counts when full, plus a `nack` and a close on sustained overrun.",
	),
]


def main () -> None:
	s = open(SRC).read()
	for old, new in EDITS:
		if s.count(old) != 1:
			sys.exit(f"MATCHED {s.count(old)} TIMES: {old[:90]!r}")
		s = s.replace(old, new)
	open(DST, "w").write(s)
	print("ok", len(s))


main()
