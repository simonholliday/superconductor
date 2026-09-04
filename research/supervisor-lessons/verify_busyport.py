"""Verifier prototype (not house style): does a busy port surface as OSError at start_threaded(), as subsample/cli.py:1763 assumes?"""
import socket, sys, time, threading
sys.path.insert(0, "/mnt/dev/Apps/Supervisor")
import supervisor.core
blocker = socket.socket(); blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); blocker.bind(("0.0.0.0", 19996)); blocker.listen(1)
sv = supervisor.core.BroadcastServer(manifest={"type": "manifest"}, port=19996)
seen = []
threading.excepthook = lambda a: seen.append((a.thread.name, type(a.exc_value).__name__, str(a.exc_value)))
try:
    sv.start_threaded()
    print("start_threaded() returned normally on the caller's thread: no OSError raised here")
except OSError as e:
    print("OSError raised on caller's thread:", e)
time.sleep(1.0)
print("daemon thread alive:", sv._threaded_thread.is_alive())
print("exception on daemon thread:", seen)
sv.stop_threaded(); print("stop_threaded() returned")
