"""
Generic WebSocket broadcast server for the Supervisor dashboard.

Provides the shared infrastructure that all app integrations use:
WebSocket server lifecycle, client management, manifest-on-connect,
and throttled state broadcasting.  App-specific modules supply the
manifest and event handlers.

"""

import asyncio
import json
import logging
import mimetypes
import os
import threading
import time
import typing

logger = logging.getLogger(__name__)


class BroadcastServer:

	"""WebSocket server that sends a manifest on connect and broadcasts state.

	Subclass or compose with app-specific event listeners that call
	mark_dirty() when state changes.  The server throttles broadcasts
	to max_hz to avoid flooding clients.
	"""

	def __init__ (self, manifest: dict[str, typing.Any], port: int = 9004, max_hz: float = 2.0, serve_dirs: list[str] | None = None) -> None:

		self._manifest = manifest
		self._port = port
		self._min_interval = 1.0 / max_hz
		self._serve_dirs = [os.path.realpath(d) for d in (serve_dirs or [])]
		self._clients: set[typing.Any] = set()
		self._server: typing.Any = None
		self._broadcast_task: asyncio.Task[None] | None = None
		self._dirty = False
		self._last_broadcast: float = 0.0

	def mark_dirty (self) -> None:
		"""Signal that state has changed and should be broadcast."""
		self._dirty = True

	def get_state (self) -> dict[str, typing.Any]:
		"""Return the current state to broadcast. Override in subclass."""
		return {}

	def after_broadcast (self) -> None:
		"""Called after state is broadcast. Override to reset accumulated data."""
		pass

	async def start (self) -> None:

		"""Start the WebSocket server and broadcast loop."""

		import websockets  # type: ignore[import-untyped]

		self._server = await websockets.serve(  # type: ignore[attr-defined]
			self._handle_client,
			"0.0.0.0",
			self._port,
			process_request=self._process_request if self._serve_dirs else None,
		)

		self._broadcast_task = asyncio.create_task(self._broadcast_loop())
		logger.info(f"Supervisor dashboard server started on ws://0.0.0.0:{self._port}")

	async def stop (self) -> None:

		"""Stop the broadcast loop and close the server."""

		if self._broadcast_task:
			self._broadcast_task.cancel()
			try:
				await self._broadcast_task
			except asyncio.CancelledError:
				pass
			self._broadcast_task = None

		if self._server:
			self._server.close()
			await self._server.wait_closed()
			self._server = None

		logger.info("Supervisor dashboard server stopped")

	def start_threaded (self) -> None:

		"""Start the server on a new daemon thread with its own event loop.

		Use this instead of ``await start()`` when the source app is threaded
		(no existing asyncio event loop).  The thread runs until
		``stop_threaded()`` is called.
		"""

		self._threaded_loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
		self._threaded_thread = threading.Thread(
			target=self._run_threaded_loop,
			daemon=True,
			name="supervisor",
		)
		self._threaded_thread.start()

	def _run_threaded_loop (self) -> None:
		loop = self._threaded_loop
		asyncio.set_event_loop(loop)
		try:
			loop.run_until_complete(self.start())
		except RuntimeError:
			# Loop was stopped before start() completed (early shutdown).
			return
		loop.run_forever()
		# After loop.stop(), clean up the server.
		loop.run_until_complete(self.stop())
		loop.close()

	def stop_threaded (self) -> None:

		"""Stop a server started with ``start_threaded()``."""

		loop = getattr(self, '_threaded_loop', None)
		thread = getattr(self, '_threaded_thread', None)
		if loop and thread:
			loop.call_soon_threadsafe(loop.stop)
			thread.join(timeout=5.0)

	def _process_request (self, connection: typing.Any, request: typing.Any) -> typing.Any:

		"""Serve files from allowed directories via HTTP on the WebSocket port.

		Intercepts requests to /audio/<path>.  Returns a Response to serve the
		file, or None to continue with the WebSocket handshake.
		"""

		if not hasattr(request, 'path') or not request.path.startswith('/audio/'):
			return None

		from websockets.datastructures import Headers  # type: ignore[import-untyped]
		from websockets.http11 import Response  # type: ignore[import-untyped]

		rel_path = request.path[len('/audio/'):]
		if not rel_path:
			return Response(404, 'Not Found', Headers(), b'Not found')

		for base in self._serve_dirs:
			full = os.path.realpath(os.path.join(base, rel_path))
			if not full.startswith(base + os.sep) and full != base:
				continue
			if not os.path.isfile(full):
				continue

			content_type = mimetypes.guess_type(full)[0] or 'application/octet-stream'
			try:
				with open(full, 'rb') as f:
					body = f.read()
				return Response(
					200, 'OK',
					Headers([
						('Content-Type', content_type),
						('Content-Length', str(len(body))),
						('Access-Control-Allow-Origin', '*'),
					]),
					body,
				)
			except OSError:
				return Response(500, 'Internal Server Error', Headers(), b'Read error')

		return Response(404, 'Not Found', Headers(), b'Not found')

	async def _handle_client (self, websocket: typing.Any) -> None:

		"""Send manifest and initial state on connect, then keep alive."""

		self._clients.add(websocket)

		try:
			await websocket.send(json.dumps(self._manifest))

			# Send current state immediately so the client doesn't have
			# to wait for the next dirty-flag cycle.
			try:
				state = self.get_state()
				await websocket.send(json.dumps({"type": "state", "data": state}))
			except Exception:
				pass

			async for _ in websocket:
				pass

		except Exception:
			pass

		finally:
			self._clients.discard(websocket)

	async def _broadcast_loop (self) -> None:

		"""Broadcast state to clients, throttled."""

		_HEARTBEAT_INTERVAL = 5.0

		while True:
			try:
				await asyncio.sleep(0.1)

				if not self._clients:
					self._dirty = False
					continue

				now = time.monotonic()

				if not self._dirty:
					# Send a heartbeat if idle too long so clients
					# know the connection is still alive.
					if now - self._last_broadcast >= _HEARTBEAT_INTERVAL:
						self._last_broadcast = now
						heartbeat = json.dumps({"type": "heartbeat"})
						disconnected = set()
						for client in list(self._clients):
							try:
								await asyncio.wait_for(client.send(heartbeat), timeout=2.0)
							except Exception:
								disconnected.add(client)
						self._clients -= disconnected
					continue

				if now - self._last_broadcast < self._min_interval:
					continue

				self._dirty = False
				self._last_broadcast = now

				try:
					state = self.get_state()
					message = json.dumps({"type": "state", "data": state})
				except Exception:
					logger.debug("Supervisor: failed to build state", exc_info=True)
					continue

				disconnected = set()
				for client in list(self._clients):
					try:
						await asyncio.wait_for(client.send(message), timeout=2.0)
					except Exception:
						disconnected.add(client)

				self._clients -= disconnected
				self.after_broadcast()

			except asyncio.CancelledError:
				raise
			except Exception:
				logger.debug("Broadcast loop error", exc_info=True)
