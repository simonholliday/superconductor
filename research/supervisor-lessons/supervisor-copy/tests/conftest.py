"""Shared fixtures for Supervisor tests."""

import dataclasses
import threading
import types
import typing

import pytest


# ── Scanner (Substation) fakes ──

class FakeScanner:

	"""Minimal stub providing the interface SubstationSupervisor reads."""

	def __init__ (self) -> None:
		self.band_name = "test_nfm"
		self.freq_start = 446.00625e6
		self.freq_end = 446.09375e6
		self.modulation = "NFM"
		self.num_channels = 8
		self.band_config = types.SimpleNamespace(channel_spacing=12500.0)
		self.audio_output_dir = "/tmp/audio"
		self._handlers: dict[str, list[typing.Callable[..., typing.Any]]] = {}

	def on (self, event: str, handler: typing.Callable[..., typing.Any]) -> None:
		self._handlers.setdefault(event, []).append(handler)


@pytest.fixture
def fake_scanner () -> FakeScanner:
	return FakeScanner()


# ── Sampler (Subsample) fakes ──

@dataclasses.dataclass
class FakeVoice:
	note: int = 60
	channel: int = 0
	releasing: bool = False
	one_shot: bool = False


class FakeEmitter:

	"""Minimal stub matching subsample.events.EventEmitter."""

	def __init__ (self) -> None:
		self._handlers: dict[str, list[typing.Callable[..., typing.Any]]] = {}

	def on (self, event: str, handler: typing.Callable[..., typing.Any]) -> None:
		self._handlers.setdefault(event, []).append(handler)

	def emit (self, event: str, **kwargs: typing.Any) -> None:
		for handler in self._handlers.get(event, []):
			handler(**kwargs)


class FakePlayer:

	"""Minimal stub providing the interface SubsampleSupervisor reads."""

	def __init__ (self) -> None:
		self._voices: list[FakeVoice] = []
		self._voices_lock = threading.Lock()
		self.events = FakeEmitter()


class FakeLibrary:

	"""Minimal stub providing the interface SubsampleSupervisor reads."""

	def __init__ (self, count: int = 0, memory_used: int = 0, memory_limit: int = 100 * 1024 * 1024) -> None:
		self._count = count
		self.memory_used = memory_used
		self.memory_limit = memory_limit

	def __len__ (self) -> int:
		return self._count


class FakeRecorder:

	"""Minimal stub providing the interface SubsampleSupervisor reads."""

	def __init__ (self, queue_depth: int = 0) -> None:
		self._queue_depth = queue_depth

	@property
	def queue_depth (self) -> int:
		return self._queue_depth


class FakeSamplerConfig:

	"""Minimal stub providing the interface SubsampleSupervisor reads."""

	def __init__ (self) -> None:
		self.output = types.SimpleNamespace(directory="/tmp/samples")
		self.player = types.SimpleNamespace(max_polyphony=16)
		self.recorder = types.SimpleNamespace(enabled=True)


@pytest.fixture
def fake_player () -> FakePlayer:
	return FakePlayer()

@pytest.fixture
def fake_library () -> FakeLibrary:
	return FakeLibrary()

@pytest.fixture
def fake_recorder () -> FakeRecorder:
	return FakeRecorder()

@pytest.fixture
def fake_sampler_cfg () -> FakeSamplerConfig:
	return FakeSamplerConfig()
