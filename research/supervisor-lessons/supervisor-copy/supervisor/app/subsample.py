"""
Supervisor dashboard integration for Subsample (sampler).

Subscribes to sampler events and reads thread-safe state to broadcast
to the Supervisor dashboard via WebSocket.  Uses start_threaded() /
stop_threaded() since the sampler has no asyncio event loop.

Thread safety model:
- Voices: read directly under player._voices_lock (already exists)
- CC state: accumulated from 'cc' events under our own lock
  (player._cc_state has no lock — unsafe to read cross-thread)
- Library stats: read directly (InstrumentLibrary locks internally)
- Recent samples: accumulated from events under our own lock
- Recorder: read queue_depth directly (thread-safe property)

"""

import collections
import os
import threading
import typing

import supervisor.core

MANIFEST: dict[str, typing.Any] = {
	"type": "manifest",
	"app": "subsample",
	"label": "subsample",
	"color": "#3fb950",
	"panels": [
		{
			"id": "subsample.voices",
			"name": "MIDI Activity",
			"description": "Active voices, note triggers, CC state",
			"default_w": 6, "default_h": 4,
			"min_w": 3, "min_h": 3,
		},
		{
			"id": "subsample.library",
			"name": "Library",
			"description": "Sample count, memory usage, recent samples",
			"default_w": 6, "default_h": 4,
			"min_w": 3, "min_h": 3,
		},
		{
			"id": "subsample.recorder",
			"name": "Recorder",
			"description": "Recording state and analysis queue",
			"default_w": 4, "default_h": 2,
			"min_w": 3, "min_h": 2,
		},
	],
}


class SubsampleSupervisor (supervisor.core.BroadcastServer):

	"""Supervisor integration for the Subsample sampler.

	Reads state from the sampler's player, library, and recorder
	components.  Event handlers accumulate CC and sample data under
	a local lock; other state is read directly from thread-safe APIs.
	"""

	def __init__ (
		self,
		player: typing.Any,
		instrument_library: typing.Any,
		recorder_processor: typing.Any,
		cfg: typing.Any,
		port: int = 9003,
	) -> None:

		audio_dir = os.path.abspath(cfg.output.directory) if hasattr(cfg, 'output') and hasattr(cfg.output, 'directory') else ''
		self._audio_dir = audio_dir
		super().__init__(manifest=MANIFEST, port=port, serve_dirs=[audio_dir] if audio_dir else [])

		self._player = player
		self._library = instrument_library
		self._recorder = recorder_processor
		self._cfg = cfg

		# State accumulated from events (protected by _lock).
		self._lock = threading.Lock()
		self._cc_state: dict[str, int] = {}
		self._recent_samples: collections.deque[dict[str, typing.Any]] = collections.deque(maxlen=20)

		# Subscribe to player events (player.events is an EventEmitter instance).
		if player and hasattr(player, 'events'):
			player.events.on('cc', self._on_cc)

	def on_sample_captured (self, **kwargs: typing.Any) -> None:
		"""Handle sample_captured event from app_events emitter.

		Receives full analysis objects as kwargs (filepath, pitch, rhythm,
		duration, etc).  Extracts the fields the dashboard needs.
		"""
		filepath = kwargs.get('filepath')
		abs_path = str(filepath) if filepath else ''
		rel_path = os.path.relpath(abs_path, self._audio_dir) if abs_path and self._audio_dir else ''
		filename = filepath.stem if hasattr(filepath, 'stem') else os.path.basename(abs_path) if abs_path else ''
		pitch = kwargs.get('pitch')
		rhythm = kwargs.get('rhythm')
		with self._lock:
			self._recent_samples.appendleft({
				"name": filename,
				"duration": round(float(kwargs.get('duration', 0)), 2),
				"pitch_hz": round(float(getattr(pitch, 'dominant_pitch_hz', 0)), 1) if pitch else 0.0,
				"pitch_class": int(getattr(pitch, 'dominant_pitch_class', -1)) if pitch else -1,
				"tempo_bpm": round(float(getattr(rhythm, 'tempo_bpm', 0)), 1) if rhythm else 0.0,
				"path": rel_path,
				"filename": os.path.basename(abs_path) if abs_path else '',
			})
		self.mark_dirty()

	def on_sample_loaded (self, **kwargs: typing.Any) -> None:
		"""Handle sample_loaded event from app_events emitter.

		Receives a SampleRecord as record kwarg.  Nested analysis results
		live on record.pitch and record.rhythm.
		"""
		record = kwargs.get('record')
		if record is None:
			return
		pitch = getattr(record, 'pitch', None)
		rhythm = getattr(record, 'rhythm', None)
		filepath = getattr(record, 'filepath', None)
		abs_path = str(filepath) if filepath else ''
		rel_path = os.path.relpath(abs_path, self._audio_dir) if abs_path and self._audio_dir else ''
		with self._lock:
			self._recent_samples.appendleft({
				"name": getattr(record, 'name', ''),
				"duration": round(float(getattr(record, 'duration', 0)), 2),
				"pitch_hz": round(float(getattr(pitch, 'dominant_pitch_hz', 0)), 1) if pitch else 0.0,
				"pitch_class": int(getattr(pitch, 'dominant_pitch_class', -1)) if pitch else -1,
				"tempo_bpm": round(float(getattr(rhythm, 'tempo_bpm', 0)), 1) if rhythm else 0.0,
				"path": rel_path,
				"filename": os.path.basename(abs_path) if abs_path else '',
			})
		self.mark_dirty()

	def _on_cc (self, **kwargs: typing.Any) -> None:
		"""Accumulate CC state from player events."""
		channel = kwargs.get('channel', 0)
		cc_number = kwargs.get('cc_number', 0)
		value = kwargs.get('value', 0)
		key = f"{channel}.{cc_number}"
		with self._lock:
			self._cc_state[key] = int(value)
		self.mark_dirty()

	def get_state (self) -> dict[str, typing.Any]:

		"""Assemble state from player, library, recorder, and accumulated events."""

		# Voice snapshot — read under the player's own lock.
		voices: list[dict[str, typing.Any]] = []
		if self._player and hasattr(self._player, '_voices_lock'):
			with self._player._voices_lock:
				for v in self._player._voices:
					voices.append({
						"note": v.note,
						"channel": v.channel,
						"releasing": v.releasing,
						"one_shot": v.one_shot,
					})

		# CC state and recent samples — read under our own lock.
		with self._lock:
			cc_snapshot = dict(self._cc_state)
			recent_snapshot = list(self._recent_samples)

		# Polyphony limit from config.
		polyphony_limit = 8
		if self._cfg and hasattr(self._cfg, 'player') and hasattr(self._cfg.player, 'max_polyphony'):
			polyphony_limit = self._cfg.player.max_polyphony

		# Library stats — read directly (thread-safe).
		sample_count = 0
		memory_used_mb = 0.0
		memory_limit_mb = 0.0
		if self._library:
			sample_count = len(self._library)
			if hasattr(self._library, 'memory_used'):
				memory_used_mb = round(self._library.memory_used / (1024 * 1024), 1)
			if hasattr(self._library, 'memory_limit'):
				memory_limit_mb = round(self._library.memory_limit / (1024 * 1024), 1)

		# Recorder stats — read directly (thread-safe).
		recorder_enabled = False
		queue_depth = 0
		if self._cfg and hasattr(self._cfg, 'recorder') and hasattr(self._cfg.recorder, 'enabled'):
			recorder_enabled = self._cfg.recorder.enabled
		if self._recorder and hasattr(self._recorder, 'queue_depth'):
			queue_depth = self._recorder.queue_depth

		return {
			"playback": {
				"voices": voices,
				"polyphony_limit": polyphony_limit,
				"cc_state": cc_snapshot,
			},
			"library": {
				"sample_count": sample_count,
				"memory_used_mb": memory_used_mb,
				"memory_limit_mb": memory_limit_mb,
				"recent_samples": recent_snapshot,
			},
			"recorder": {
				"enabled": recorder_enabled,
				"queue_depth": queue_depth,
				"backlog": queue_depth >= 3,
			},
		}
