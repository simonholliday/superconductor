"""Prototype (not house style): construct SubsampleSupervisor the way subsample/cli.py:1750-1756 does and see what get_state() can ever report."""
import sys, threading, json
sys.path.insert(0, "/mnt/dev/Apps/Supervisor")
sys.path.insert(0, "/mnt/dev/Apps/Supervisor/tests")
import supervisor.app.subsample as m
import conftest

# Real caller: player=_player_cell (a one-element list), recorder_processor=None.
player_cell = [None]
sv = m.SubsampleSupervisor(player=player_cell, instrument_library=conftest.FakeLibrary(count=5), recorder_processor=None, cfg=conftest.FakeSamplerConfig(), port=19999)
print("cc handler subscribed in __init__ ?", "no (list has no .events)" if not hasattr(player_cell, "events") else "yes")

# Later, _start_player fills the cell (cli.py:1269) and subscribes cc externally (cli.py:1272).
fp = conftest.FakePlayer()
fp._voices = [conftest.FakeVoice(note=36), conftest.FakeVoice(note=38)]
player_cell[0] = fp
fp.events.on("cc", sv._on_cc)            # what cli.py:1272 does
fp.events.emit("cc", channel=0, cc_number=1, value=99)
st = sv.get_state()
print("voices reported after player exists:", st["playback"]["voices"], "(real player holds 2)")
print("cc_state:", st["playback"]["cc_state"])
print("recorder:", st["recorder"], "(recorder_processor=None so queue_depth is always 0)")

# The test suite's calling convention, for contrast (tests/test_supervisor.py:257-263).
sv2 = m.SubsampleSupervisor(player=fp, instrument_library=conftest.FakeLibrary(), recorder_processor=conftest.FakeRecorder(2), cfg=conftest.FakeSamplerConfig(), port=19998)
print("voices reported when a player is passed directly:", len(sv2.get_state()["playback"]["voices"]))
