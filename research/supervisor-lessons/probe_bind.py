"""Prototype probe: does a port-in-use failure inside BroadcastServer.start_threaded() surface to the caller as OSError (as subsample/cli.py:1763 assumes)?"""
import sys, socket, time, threading
sys.path.insert(0, ".")
import supervisor.core
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(("0.0.0.0", 19897)); s.listen()
m = {"type": "manifest", "app": "t", "label": "t", "color": "#fff", "panels": []}
sv = supervisor.core.BroadcastServer(manifest=m, port=19897)
caught = None
excs = []
threading.excepthook = lambda a: excs.append((a.exc_type.__name__, str(a.exc_value)[:80]))
try:
	sv.start_threaded()
except OSError as e:
	caught = e
time.sleep(0.5)
print("caller caught OSError:", caught is not None)
print("thread alive:", sv._threaded_thread.is_alive())
print("uncaught exceptions on daemon thread:", excs)
print("server object:", sv._server)
s.close()
