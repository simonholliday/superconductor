"""
Supervisor dashboard integration.

Provides a WebSocket server that broadcasts application events to the
Supervisor dashboard for real-time display.  Each application provides
an app module (e.g. supervisor.app.substation) that defines its manifest
and event listeners.  The core module provides the shared WebSocket
server infrastructure.
"""
