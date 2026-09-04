Discarded first measurement block (tag G), 2026-09-03.

Another research point was running the same bench from the shared copy at
scratchpad/transport-apps-gap-1-2/ on the shared ports (9111, 9113, 9114, 9115)
at the same time, so a sender's bind lost the race and an adapter connected to
the other point's server.  One row proves it: it is labelled "burst 128 every
2.0s" and carries 544 messages with a largest batch of 16, which is that point's
traffic, not this one's.

Nothing from this block is quoted anywhere.  The block that replaced it (tag H,
in ../results/) runs a private copy of the bench on ports 9121, 9123, 9124 and
9125 and waits for the other point's processes to be absent before every row.
