"""Prototype probe: with the default threading.excepthook, does a bind failure inside start_threaded() print a traceback to stderr?"""
import sys, socket, time
sys.path.insert(0, ".")
import supervisor.core
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(("0.0.0.0", 19898)); s.listen()
m = {"type": "manifest", "app": "t", "label": "t", "color": "#fff", "panels": []}
sv = supervisor.core.BroadcastServer(manifest=m, port=19898)
caught = None
try:
	sv.start_threaded()
except OSError as e:
	caught = e
time.sleep(0.5)
print("caller caught OSError:", caught is not None)
print("thread alive:", sv._threaded_thread.is_alive())
print("server object:", sv._server)
s.close()
