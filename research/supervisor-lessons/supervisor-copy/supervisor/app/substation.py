"""
Supervisor dashboard integration for Substation (SDR scanner).

Subscribes to RadioScanner events and broadcasts state to the
Supervisor dashboard via WebSocket.  This module is self-contained:
it accesses the scanner only through its public event API and a few
read-only config attributes for the static band manifest.

"""

import collections
import os
import time
import typing

import supervisor.core

MANIFEST: dict[str, typing.Any] = {
	"type": "manifest",
	"app": "substation",
	"label": "substation",
	"color": "#d2a8ff",
	"panels": [
		{
			"id": "substation.channels",
			"name": "Channels",
			"description": "Channel states, frequencies, SNR levels",
			"default_w": 6, "default_h": 6,
			"min_w": 4, "min_h": 3,
		},
		{
			"id": "substation.recordings",
			"name": "Recordings",
			"description": "Active and recent recordings",
			"default_w": 6, "default_h": 4,
			"min_w": 4, "min_h": 3,
		},
	],
}


class SubstationSupervisor (supervisor.core.BroadcastServer):

	"""Supervisor integration for the Substation SDR scanner.

	Subscribes to scanner events, accumulates state internally,
	and serves it to the dashboard via the BroadcastServer base class.

	Thread safety: _on_channel_snr runs on the scanner's executor thread
	(no loop= parameter), while get_state() runs on the event loop thread.
	A lock protects _channels access across threads.
	"""

	def __init__ (self, scanner: typing.Any, port: int = 9004) -> None:

		audio_dir = os.path.abspath(scanner.audio_output_dir) if hasattr(scanner, 'audio_output_dir') else ''
		self._audio_dir = audio_dir
		super().__init__(manifest=MANIFEST, port=port, serve_dirs=[audio_dir] if audio_dir else [])

		# Static band info from scanner config (read once at init).
		self._band_info: dict[str, typing.Any] = {
			"name": scanner.band_name,
			"freq_start_mhz": scanner.freq_start / 1e6,
			"freq_end_mhz": scanner.freq_end / 1e6,
			"channel_spacing_khz": scanner.band_config.channel_spacing / 1e3,
			"modulation": scanner.modulation,
			"channel_count": scanner.num_channels,
		}

		# State accumulated from events.
		self._channels: list[dict[str, typing.Any]] = []
		self._channels_fresh: bool = False
		self._noise_floor_db: float = -100.0
		self._warmup_complete: bool = False
		self._active_recordings: dict[int, dict[str, typing.Any]] = {}
		self._recent_recordings: collections.deque[dict[str, typing.Any]] = collections.deque(maxlen=20)

		# Subscribe to scanner events.
		scanner.on('channel_snr', self._on_channel_snr)
		scanner.on('noise_floor', self._on_noise_floor)
		scanner.on('recording_started', self._on_recording_started)
		scanner.on('recording_saved', self._on_recording_saved)
		scanner.on('recording_discarded', self._on_recording_discarded)

	@staticmethod
	def _sanitise_channel (ch: dict[str, typing.Any]) -> dict[str, typing.Any]:
		"""Convert numpy types to native Python for JSON serialization."""
		out = {}
		for k, v in ch.items():
			if k == 'duration_active_s':
				continue
			if isinstance(v, float):
				out[k] = float(v)
			elif isinstance(v, (bool,)):
				out[k] = bool(v)
			elif isinstance(v, int):
				out[k] = int(v)
			else:
				# Catch numpy types that don't match Python builtins
				t = type(v).__name__
				if 'float' in t:
					out[k] = float(v)
				elif 'bool' in t:
					out[k] = bool(v)
				elif 'int' in t:
					out[k] = int(v)
				else:
					out[k] = v
		return out

	def _on_channel_snr (self, **kwargs: typing.Any) -> None:
		"""Called from executor thread. Uses atomic reference swap."""
		incoming = [
			self._sanitise_channel(ch)
			for ch in kwargs.get('channels', [])
		]
		prev = self._channels
		if not prev or self._channels_fresh:
			self._channels = incoming
			self._channels_fresh = False
		else:
			# Merge peaks into a new list (don't mutate prev in place).
			merged = []
			for i, ch in enumerate(incoming):
				if i < len(prev) and prev[i].get('snr_db', 0) > ch.get('snr_db', 0):
					merged.append(prev[i])
				else:
					merged.append(ch)
			self._channels = merged  # atomic reference swap
		self.mark_dirty()

	def _on_noise_floor (self, **kwargs: typing.Any) -> None:
		self._noise_floor_db = kwargs.get('noise_floor_db', -100.0)
		self._warmup_complete = kwargs.get('warmup_complete', False)

	def _on_recording_started (self, **kwargs: typing.Any) -> None:
		idx = kwargs.get('index', -1)
		freq = kwargs.get('freq', 0.0)
		self._active_recordings[idx] = {
			"channel_index": idx,
			"frequency_mhz": round(freq / 1e6, 6),
			"start_time": time.time(),
		}
		self.mark_dirty()

	def _on_recording_saved (self, **kwargs: typing.Any) -> None:
		idx = kwargs.get('index', -1)
		freq = kwargs.get('freq', 0.0)
		started = self._active_recordings.pop(idx, None)
		duration = time.time() - started["start_time"] if started else 0.0
		abs_path = kwargs.get('file_path', '')
		rel_path = os.path.relpath(abs_path, self._audio_dir) if abs_path and self._audio_dir else ''
		filename = os.path.basename(abs_path) if abs_path else ''
		self._recent_recordings.appendleft({
			"channel_index": idx,
			"frequency_mhz": round(freq / 1e6, 6),
			"duration_s": round(duration, 1),
			"path": rel_path,
			"filename": filename,
			"band": kwargs.get('band', ''),
		})
		self.mark_dirty()

	def _on_recording_discarded (self, **kwargs: typing.Any) -> None:
		idx = kwargs.get('index', -1)
		self._active_recordings.pop(idx, None)
		self.mark_dirty()

	def get_state (self) -> dict[str, typing.Any]:

		"""Assemble state from internally accumulated event data."""

		now = time.time()
		active = []
		for rec in self._active_recordings.values():
			active.append({
				"channel_index": rec["channel_index"],
				"frequency_mhz": rec["frequency_mhz"],
				"duration_s": round(now - rec["start_time"], 1),
			})

		# Atomic read — _channels is replaced as a whole, never mutated.
		channels = self._channels

		return {
			"band": self._band_info,
			"channels": channels,
			"recordings": {
				"active": active,
				"recent": list(self._recent_recordings),
			},
			"noise_floor_db": self._noise_floor_db,
			"warmup_complete": self._warmup_complete,
		}

	def after_broadcast (self) -> None:
		"""Mark channels for replacement on next snapshot, preserving data until then."""
		self._channels_fresh = True
