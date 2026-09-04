"""Prototype probe: construct SubsampleSupervisor exactly as subsample/cli.py:1750-1756 does (player=_player_cell list, recorder_processor=None) and see what the dashboard would receive."""
import sys, types, json
sys.path.insert(0, ".")
import supervisor.app.subsample as m
class Cfg:  # mirrors real subsample.config.Config: has recorder/player/supervisor, no `output`
	player = types.SimpleNamespace(max_polyphony=8)
	recorder = types.SimpleNamespace(enabled=True)
player_cell = [None]
sv = m.SubsampleSupervisor(player=player_cell, instrument_library=None, recorder_processor=None, cfg=Cfg(), port=19898)
print("serve_dirs:", sv._serve_dirs, "audio_dir:", repr(sv._audio_dir))
print("cc subscribed in __init__ (hasattr(list,'events')):", hasattr(player_cell, "events"))
# Simulate the player being created later, as _start_player does at cli.py:1269
class FakePlayer:
	import threading
	_voices_lock = threading.Lock()
	_voices = [types.SimpleNamespace(note=36, channel=9, releasing=False, one_shot=True)]
player_cell[0] = FakePlayer()
st = sv.get_state()
print("voices seen by dashboard after player exists:", st["playback"]["voices"])
print("recorder:", st["recorder"])
