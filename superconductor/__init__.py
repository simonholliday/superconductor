"""Superconductor — a touchscreen control surface for Simon's music software.

The service serves one HTML page to a touchscreen's browser and holds a single
WebSocket to it, while each music app dials in over a WebSocket of its own and
declares what it can be controlled by.  Nothing in this package knows about a
particular studio: an app's declaration names its own controls, and a page binds
widgets to those names.

The design this implements is Subroutine document #2018; the research behind it
is #1912 and the sixteen points it names.
"""
