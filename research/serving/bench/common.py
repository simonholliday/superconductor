"""Shared pieces for the serving-stack prototypes (research prototype, not house style)."""

import json
import os
import random
import time

WWW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "www")
ROWS = 8
COLS = 16
BROADCAST_HZ = float(os.environ.get("BROADCAST_HZ", "20"))


def ensure_www() -> None:
	os.makedirs(WWW, exist_ok=True)
	index = os.path.join(WWW, "index.html")
	if not os.path.exists(index):
		with open(index, "w") as fh:
			fh.write("<!doctype html><title>bench</title><script src=/app.js></script><div id=grid></div>\n")
	blob = os.path.join(WWW, "app.js")
	if not os.path.exists(blob):
		rnd = random.Random(1)
		with open(blob, "w") as fh:
			for _ in range(4000):
				fh.write("// " + "".join(rnd.choice("abcdefghijklmnopqrstuvwxyz ") for _ in range(46)) + "\n")


class Grid:
	def __init__(self) -> None:
		self.cells = [False] * (ROWS * COLS)
		self.version = 0

	def toggle(self, i: int) -> None:
		if 0 <= i < len(self.cells):
			self.cells[i] = not self.cells[i]
			self.version += 1

	def snapshot(self) -> str:
		return json.dumps({"type": "state", "v": self.version, "t": time.time(), "cells": [1 if c else 0 for c in self.cells]})

	def handle(self, raw: str) -> None:
		try:
			msg = json.loads(raw)
		except ValueError:
			return
		if msg.get("type") == "toggle":
			self.toggle(int(msg.get("i", -1)))
