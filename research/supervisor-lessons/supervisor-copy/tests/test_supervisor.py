"""Tests for Supervisor dashboard integration.

TestManifest and TestBuildState originated in the SDR Scanner repo and
test the supervisor package code that now lives here.
"""

import json
import time

import pytest

import supervisor.app.subsample
import supervisor.app.substation
import supervisor.core


class TestManifest:

	def test_manifest_structure (self):
		"""Manifest has required protocol fields."""
		m = supervisor.app.substation.MANIFEST
		assert m["type"] == "manifest"
		assert m["app"] == "substation"
		assert isinstance(m["label"], str)
		assert isinstance(m["color"], str)
		assert len(m["panels"]) >= 1

	def test_panel_ids_prefixed (self):
		"""All panel IDs are prefixed with 'substation.'."""
		for w in supervisor.app.substation.MANIFEST["panels"]:
			assert w["id"].startswith("substation."), f"Panel ID {w['id']} missing prefix"

	def test_panel_fields_present (self):
		"""Each panel has all required fields."""
		required = {"id", "name", "description", "default_w", "default_h", "min_w", "min_h"}
		for w in supervisor.app.substation.MANIFEST["panels"]:
			assert required.issubset(w.keys()), f"Panel {w['id']} missing fields: {required - w.keys()}"


class TestBuildState:

	@pytest.fixture
	def sv (self, fake_scanner):
		"""Create a SubstationSupervisor with a fake scanner."""
		return supervisor.app.substation.SubstationSupervisor(fake_scanner, port=9999)

	def test_state_has_required_keys (self, sv):
		"""State contains all top-level keys from the protocol."""
		state = sv.get_state()
		assert "band" in state
		assert "channels" in state
		assert "recordings" in state
		assert "noise_floor_db" in state
		assert "warmup_complete" in state

	def test_band_info (self, sv):
		"""Band section contains correct config values."""
		state = sv.get_state()
		band = state["band"]
		assert isinstance(band["name"], str)
		assert isinstance(band["channel_count"], int)
		assert isinstance(band["freq_start_mhz"], float)
		assert isinstance(band["modulation"], str)

	def test_channels_populated_by_event (self, sv):
		"""Channels are populated when a channel_snr event fires."""
		assert sv.get_state()["channels"] == []

		sv._on_channel_snr(channels=[
			{"index": 1, "frequency_mhz": 446.0, "snr_db": 5.0, "is_active": False},
			{"index": 2, "frequency_mhz": 446.0125, "snr_db": 12.0, "is_active": True},
		])
		state = sv.get_state()
		assert len(state["channels"]) == 2
		assert state["channels"][1]["snr_db"] == 12.0

	def test_noise_floor_from_event (self, sv):
		"""Noise floor is updated by noise_floor events."""
		assert sv.get_state()["noise_floor_db"] == -100.0

		sv._on_noise_floor(noise_floor_db=-85.3, warmup_complete=True)
		state = sv.get_state()
		assert state["noise_floor_db"] == -85.3
		assert state["warmup_complete"] is True

	def test_recordings_structure (self, sv):
		"""Recordings section has active and recent lists."""
		state = sv.get_state()
		assert "active" in state["recordings"]
		assert "recent" in state["recordings"]

	def test_state_is_json_serializable (self, sv):
		"""State can be serialized to JSON without errors."""
		sv._on_channel_snr(channels=[
			{"index": 1, "frequency_mhz": 446.0, "snr_db": 5.0, "is_active": False},
		])
		state = sv.get_state()
		msg = json.dumps({"type": "state", "data": state})
		parsed = json.loads(msg)
		assert parsed["type"] == "state"

	def test_recording_saved_event (self, sv):
		"""recording_saved event adds to recent recordings with relative path."""
		sv._on_recording_saved(band="pmr", index=3, freq=446e6, file_path="/tmp/audio/2026-04-14/pmr/test.wav")
		state = sv.get_state()
		assert len(state["recordings"]["recent"]) == 1
		rec = state["recordings"]["recent"][0]
		assert rec["channel_index"] == 3
		assert rec["filename"] == "test.wav"
		assert rec["path"] == "2026-04-14/pmr/test.wav"
		assert "file_path" not in rec

	def test_recording_started_and_saved (self, sv):
		"""Active recordings track start and clear on save."""
		sv._on_recording_started(band="pmr", index=3, freq=446e6)
		state = sv.get_state()
		assert len(state["recordings"]["active"]) == 1

		sv._on_recording_saved(band="pmr", index=3, freq=446e6, file_path="/tmp/audio/2026-04-14/pmr/test.wav")
		state = sv.get_state()
		assert len(state["recordings"]["active"]) == 0
		assert len(state["recordings"]["recent"]) == 1

	def test_recording_discarded_clears_active (self, sv):
		"""recording_discarded event removes from active list."""
		sv._on_recording_started(band="pmr", index=5, freq=446e6)
		assert len(sv.get_state()["recordings"]["active"]) == 1

		sv._on_recording_discarded(index=5)
		assert len(sv.get_state()["recordings"]["active"]) == 0

	def test_dirty_flag (self, sv):
		"""Events set the dirty flag for throttled broadcasting."""
		assert not sv._dirty
		sv._on_channel_snr(channels=[])
		assert sv._dirty

	def test_is_active_passed_through_from_snr (self, sv):
		"""is_active from channel_snr snapshots is passed through directly."""
		sv._on_channel_snr(channels=[
			{"index": 1, "frequency_mhz": 446.0, "snr_db": 5.0, "is_active": False},
			{"index": 2, "frequency_mhz": 446.0125, "snr_db": 12.0, "is_active": True},
		])
		state = sv.get_state()
		assert state["channels"][0]["is_active"] is False
		assert state["channels"][1]["is_active"] is True

	def test_snr_peak_retention (self, sv):
		"""channel_snr merges peak SNR values between broadcasts."""
		# First snapshot
		sv._on_channel_snr(channels=[
			{"index": 1, "frequency_mhz": 446.0, "snr_db": 5.0, "is_active": False},
			{"index": 2, "frequency_mhz": 446.0125, "snr_db": 20.0, "is_active": False},
		])
		# Second snapshot — ch2 SNR dropped, ch1 rose
		sv._on_channel_snr(channels=[
			{"index": 1, "frequency_mhz": 446.0, "snr_db": 8.0, "is_active": False},
			{"index": 2, "frequency_mhz": 446.0125, "snr_db": 3.0, "is_active": False},
		])
		state = sv.get_state()
		assert state["channels"][0]["snr_db"] == 8.0   # took higher
		assert state["channels"][1]["snr_db"] == 20.0   # retained peak

	def test_after_broadcast_resets_peaks (self, sv):
		"""after_broadcast marks channels for replacement, preserving data until then."""
		sv._on_channel_snr(channels=[
			{"index": 1, "frequency_mhz": 446.0, "snr_db": 10.0, "is_active": False},
		])
		assert len(sv.get_state()["channels"]) == 1

		sv.after_broadcast()
		# Data still available — not cleared until next snapshot arrives
		assert len(sv.get_state()["channels"]) == 1

		# Next snapshot replaces rather than merging peaks
		sv._on_channel_snr(channels=[
			{"index": 1, "frequency_mhz": 446.0, "snr_db": 2.0, "is_active": False},
		])
		assert sv.get_state()["channels"][0]["snr_db"] == 2.0  # replaced, not peak-held

	def test_peak_retention_within_broadcast_cycle (self, sv):
		"""Peaks are retained within a single broadcast cycle."""
		sv._on_channel_snr(channels=[
			{"index": 1, "frequency_mhz": 446.0, "snr_db": 20.0, "is_active": False},
		])
		sv._on_channel_snr(channels=[
			{"index": 1, "frequency_mhz": 446.0, "snr_db": 3.0, "is_active": False},
		])
		assert sv.get_state()["channels"][0]["snr_db"] == 20.0  # peak retained

		# After broadcast, next snapshot replaces
		sv.after_broadcast()
		sv._on_channel_snr(channels=[
			{"index": 1, "frequency_mhz": 446.0, "snr_db": 5.0, "is_active": False},
		])
		assert sv.get_state()["channels"][0]["snr_db"] == 5.0  # fresh cycle


class TestBroadcastServer:

	def test_start_threaded_and_stop (self):
		"""start_threaded runs the server on a daemon thread, stop_threaded shuts it down."""
		manifest = {"type": "manifest", "app": "test", "label": "test", "color": "#fff", "panels": []}
		server = supervisor.core.BroadcastServer(manifest=manifest, port=19876)
		server.start_threaded()
		time.sleep(0.2)  # let the server bind

		# Thread should be alive and have its own event loop
		assert server._threaded_thread.is_alive()
		assert server._threaded_loop.is_running()

		server.stop_threaded()

		# Thread should have stopped
		assert not server._threaded_thread.is_alive()

	def test_start_threaded_creates_daemon_thread (self):
		"""The supervisor thread is a daemon so it won't block process exit."""
		manifest = {"type": "manifest", "app": "test", "label": "test", "color": "#fff", "panels": []}
		server = supervisor.core.BroadcastServer(manifest=manifest, port=19877)
		server.start_threaded()
		time.sleep(0.2)  # let the server bind

		assert server._threaded_thread.daemon is True

		server.stop_threaded()


class TestSubsampleManifest:

	def test_manifest_structure (self):
		"""Manifest has required protocol fields."""
		m = supervisor.app.subsample.MANIFEST
		assert m["type"] == "manifest"
		assert m["app"] == "subsample"
		assert isinstance(m["label"], str)
		assert isinstance(m["color"], str)
		assert len(m["panels"]) >= 1

	def test_panel_ids_prefixed (self):
		"""All panel IDs are prefixed with 'subsample.'."""
		for p in supervisor.app.subsample.MANIFEST["panels"]:
			assert p["id"].startswith("subsample."), f"Panel ID {p['id']} missing prefix"

	def test_panel_fields_present (self):
		"""Each panel has all required fields."""
		required = {"id", "name", "description", "default_w", "default_h", "min_w", "min_h"}
		for p in supervisor.app.subsample.MANIFEST["panels"]:
			assert required.issubset(p.keys()), f"Panel {p['id']} missing fields: {required - p.keys()}"


class TestSubsampleState:

	@pytest.fixture
	def sv (self, fake_player, fake_library, fake_recorder, fake_sampler_cfg):
		"""Create a SubsampleSupervisor with fakes."""
		return supervisor.app.subsample.SubsampleSupervisor(
			player=fake_player,
			instrument_library=fake_library,
			recorder_processor=fake_recorder,
			cfg=fake_sampler_cfg,
			port=19878,
		)

	def test_state_has_required_keys (self, sv):
		"""State contains all top-level keys."""
		state = sv.get_state()
		assert "playback" in state
		assert "library" in state
		assert "recorder" in state

	def test_playback_structure (self, sv):
		"""Playback section has voices, polyphony_limit, cc_state."""
		state = sv.get_state()
		pb = state["playback"]
		assert "voices" in pb
		assert "polyphony_limit" in pb
		assert "cc_state" in pb
		assert pb["polyphony_limit"] == 16

	def test_voice_snapshot (self, sv, fake_player):
		"""Voices are read from the player under its lock."""
		from conftest import FakeVoice
		fake_player._voices = [
			FakeVoice(note=60, channel=0, releasing=False, one_shot=False),
			FakeVoice(note=64, channel=0, releasing=True, one_shot=False),
		]
		state = sv.get_state()
		voices = state["playback"]["voices"]
		assert len(voices) == 2
		assert voices[0]["note"] == 60
		assert voices[0]["releasing"] is False
		assert voices[1]["note"] == 64
		assert voices[1]["releasing"] is True

	def test_cc_event_accumulation (self, sv, fake_player):
		"""CC events accumulate state under the supervisor's lock."""
		fake_player.events.emit('cc', channel=0, cc_number=1, value=64)
		fake_player.events.emit('cc', channel=0, cc_number=11, value=80)
		state = sv.get_state()
		cc = state["playback"]["cc_state"]
		assert cc["0.1"] == 64
		assert cc["0.11"] == 80

	def test_cc_event_overwrites (self, sv, fake_player):
		"""Later CC events overwrite earlier ones for the same controller."""
		fake_player.events.emit('cc', channel=0, cc_number=1, value=64)
		fake_player.events.emit('cc', channel=0, cc_number=1, value=127)
		state = sv.get_state()
		assert state["playback"]["cc_state"]["0.1"] == 127

	def test_library_stats (self, sv):
		"""Library section reads from the library object."""
		state = sv.get_state()
		lib = state["library"]
		assert lib["sample_count"] == 0
		assert lib["memory_used_mb"] == 0.0
		assert isinstance(lib["memory_limit_mb"], float)

	def test_library_stats_with_data (self, fake_player, fake_recorder, fake_sampler_cfg):
		"""Library stats reflect actual values."""
		from conftest import FakeLibrary
		lib = FakeLibrary(count=42, memory_used=50 * 1024 * 1024, memory_limit=100 * 1024 * 1024)
		sv = supervisor.app.subsample.SubsampleSupervisor(
			player=fake_player, instrument_library=lib,
			recorder_processor=fake_recorder, cfg=fake_sampler_cfg, port=19878,
		)
		state = sv.get_state()
		assert state["library"]["sample_count"] == 42
		assert state["library"]["memory_used_mb"] == 50.0
		assert state["library"]["memory_limit_mb"] == 100.0

	def test_recorder_stats (self, sv):
		"""Recorder section reads queue depth and enabled status."""
		state = sv.get_state()
		rec = state["recorder"]
		assert rec["enabled"] is True
		assert rec["queue_depth"] == 0
		assert rec["backlog"] is False

	def test_recorder_backlog (self, fake_player, fake_library, fake_sampler_cfg):
		"""Backlog flag is set when queue depth >= 3."""
		from conftest import FakeRecorder
		recorder = FakeRecorder(queue_depth=3)
		sv = supervisor.app.subsample.SubsampleSupervisor(
			player=fake_player, instrument_library=fake_library,
			recorder_processor=recorder, cfg=fake_sampler_cfg, port=19878,
		)
		state = sv.get_state()
		assert state["recorder"]["backlog"] is True

	def test_sample_captured_event (self, sv):
		"""on_sample_captured extracts fields from analysis objects."""
		import pathlib
		import types
		sv.on_sample_captured(
			filepath=pathlib.PurePosixPath("/tmp/samples/2026-04-15/kick_001.wav"),
			duration=1.5,
			pitch=types.SimpleNamespace(dominant_pitch_hz=110.0, dominant_pitch_class=9),
			rhythm=types.SimpleNamespace(tempo_bpm=120.0),
		)
		state = sv.get_state()
		recent = state["library"]["recent_samples"]
		assert len(recent) == 1
		assert recent[0]["name"] == "kick_001"
		assert recent[0]["filename"] == "kick_001.wav"
		assert recent[0]["path"] == "2026-04-15/kick_001.wav"
		assert recent[0]["duration"] == 1.5
		assert recent[0]["pitch_class"] == 9
		assert recent[0]["tempo_bpm"] == 120.0

	def test_sample_loaded_event (self, sv):
		"""on_sample_loaded extracts fields from SampleRecord with nested analysis."""
		import pathlib
		import types
		record = types.SimpleNamespace(
			name="snare_deep", duration=0.8,
			pitch=types.SimpleNamespace(dominant_pitch_hz=220.0, dominant_pitch_class=9),
			rhythm=types.SimpleNamespace(tempo_bpm=95.0),
			filepath=pathlib.PurePosixPath("/tmp/samples/snare_deep.wav"),
		)
		sv.on_sample_loaded(record=record)
		state = sv.get_state()
		recent = state["library"]["recent_samples"]
		assert len(recent) == 1
		assert recent[0]["name"] == "snare_deep"
		assert recent[0]["pitch_hz"] == 220.0
		assert recent[0]["tempo_bpm"] == 95.0
		assert recent[0]["filename"] == "snare_deep.wav"

	def test_dirty_flag_on_cc (self, sv, fake_player):
		"""CC events set the dirty flag."""
		assert not sv._dirty
		fake_player.events.emit('cc', channel=0, cc_number=1, value=64)
		assert sv._dirty

	def test_dirty_flag_on_sample (self, sv):
		"""Sample events set the dirty flag."""
		import pathlib
		assert not sv._dirty
		sv.on_sample_captured(filepath=pathlib.PurePosixPath("/tmp/samples/test.wav"),
			duration=1.0, pitch=None, rhythm=None)
		assert sv._dirty

	def test_state_is_json_serializable (self, sv, fake_player):
		"""State can be serialized to JSON without errors."""
		import pathlib
		import types
		from conftest import FakeVoice
		fake_player._voices = [FakeVoice(note=60, channel=0)]
		fake_player.events.emit('cc', channel=0, cc_number=1, value=64)
		sv.on_sample_captured(
			filepath=pathlib.PurePosixPath("/tmp/samples/test.wav"),
			duration=1.0,
			pitch=types.SimpleNamespace(dominant_pitch_hz=440.0, dominant_pitch_class=9),
			rhythm=types.SimpleNamespace(tempo_bpm=120.0),
		)
		state = sv.get_state()
		msg = json.dumps({"type": "state", "data": state})
		parsed = json.loads(msg)
		assert parsed["type"] == "state"

	def test_no_player (self, fake_library, fake_recorder, fake_sampler_cfg):
		"""Supervisor works when player is None."""
		sv = supervisor.app.subsample.SubsampleSupervisor(
			player=None, instrument_library=fake_library,
			recorder_processor=fake_recorder, cfg=fake_sampler_cfg, port=19878,
		)
		state = sv.get_state()
		assert state["playback"]["voices"] == []
		assert state["playback"]["cc_state"] == {}
