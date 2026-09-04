/*
 * Superintendent multi-touch research prototype (not product code).
 *
 * A pure, timer-injected gesture recogniser for a step grid and a pad bank,
 * written against the Pointer Events model (one pointerId per contact) so the
 * same code runs with a mouse (one pointer, pointerType "mouse") and with a
 * multi-touch digitiser (many pointers, pointerType "touch" or "pen").
 *
 * The recogniser never asks "is multi-touch available". Every gesture that
 * uses two contacts also has a sequential one-contact form built into the same
 * state machine (hold -> release leaves the edit strip latched), so the page
 * degrades without a mode switch. Capability is observed for diagnostics only.
 *
 * Runs in node (module.exports) and in the browser (window.Gestures).
 */
(function (root, factory) {
	if (typeof module === "object" && module.exports) { module.exports = factory(); }
	else { root.Gestures = factory(); }
}(typeof self !== "undefined" ? self : this, function () {
	"use strict";

	// Timing and distance constants, with the source of each figure.
	const DEFAULTS = {
		holdMs: 400,        // Android ViewConfiguration.DEFAULT_LONG_PRESS_TIMEOUT = 400 ms; iOS UILongPressGestureRecognizer default 0.5 s
		slopPx: 10,         // Android TOUCH_SLOP = 8 dp; rounded up for a 1080p panel at 0.249 mm/px
		latchMs: 3000,      // design choice, unsourced: how long the edit strip stays after the held finger lifts
		defaultVel: 100,    // subsequence.constants.velocity.DEFAULT_VELOCITY (pattern_builder.py:498)
		levels: [40, 70, 100, 127],  // strip levels; the last is the accent (Push "Accent" = 127)
		padVelocityMode: "fixed",    // "fixed" | "vertical" (velocity from y inside the pad)
		padFixedVel: 110,
	};

	// ---------------------------------------------------------------------
	// Capability observer: what the host has actually delivered so far.
	// ---------------------------------------------------------------------
	function CapabilityObserver () {
		this.active = new Map();          // pointerId -> pointerType
		this.peakConcurrentTouch = 0;
		this.seenTypes = new Set();
		this.maxTouchPoints = null;       // filled by the page from navigator.maxTouchPoints, advisory only
	}
	CapabilityObserver.prototype.down = function (id, type) {
		this.active.set(id, type);
		this.seenTypes.add(type);
		const touch = [...this.active.values()].filter(t => t !== "mouse").length;
		if (touch > this.peakConcurrentTouch) this.peakConcurrentTouch = touch;
	};
	CapabilityObserver.prototype.up = function (id) { this.active.delete(id); };
	// "confirmed": two contacts have been seen down at once.  "single": only ever one
	// non-mouse contact at a time.  "mouse": only mouse events seen.  "unknown": nothing yet.
	CapabilityObserver.prototype.state = function () {
		if (this.peakConcurrentTouch >= 2) return "confirmed";
		if (this.peakConcurrentTouch === 1) return "single";
		if (this.seenTypes.has("mouse")) return "mouse";
		return "unknown";
	};

	// ---------------------------------------------------------------------
	// Grid recogniser.
	//
	// Input: down/move/up/cancel with (pointerId, pointerType, cell {row, col} or null, x, y, t ms).
	// Output: a list of actions, each {type, ...}:
	//   {type:"toggle", cell}                      tap on a cell (send set {on: !on})
	//   {type:"paint", cell, on}                   drag across a row: set each cell to the first cell's new state
	//   {type:"editOpen", cells}                   hold reached: strip opens for the held selection
	//   {type:"editSelect", cells}                 selection changed while the strip is open
	//   {type:"editApply", cells, field, value}    a strip level was chosen: set {vel: value} (and on: true) on every selected cell
	//   {type:"editClose"}                         strip closed (tap outside, timeout, or last held finger lifted after an apply)
	//
	// The page's state (which cells are on) is supplied through opts.isOn(cell) so the
	// recogniser can decide paint state and never holds a copy of the grid.
	// ---------------------------------------------------------------------
	function GridGestures (opts) {
		this.o = Object.assign({}, DEFAULTS, opts || {});
		this.isOn = this.o.isOn || (() => false);
		this.pointers = new Map();   // id -> {type, cell, x0, y0, t0, moved, role}
		this.edit = null;            // {cells: Set(key), held: Set(pointerId), latchUntil: ms|null, applied: bool}
		this.cap = new CapabilityObserver();
	}
	const key = c => c.row + ":" + c.col;
	const parse = k => { const [r, c] = k.split(":"); return {row: r, col: Number(c)}; };

	GridGestures.prototype._openEdit = function (cell, id, out) {
		if (!this.edit) {
			this.edit = {cells: new Set([key(cell)]), held: new Set([id]), latchUntil: null, applied: false};
			out.push({type: "editOpen", cells: [...this.edit.cells].map(parse)});
		} else {
			this.edit.cells.add(key(cell));
			this.edit.held.add(id);
			this.edit.latchUntil = null;
			out.push({type: "editSelect", cells: [...this.edit.cells].map(parse)});
		}
	};
	GridGestures.prototype._closeEdit = function (out) {
		if (this.edit) { this.edit = null; out.push({type: "editClose"}); }
	};

	// target: {kind:"cell", cell} | {kind:"level", value} | {kind:"outside"}
	GridGestures.prototype.down = function (id, type, target, x, y, t) {
		const out = [];
		this.cap.down(id, type);
		this.tick(t, out);
		const p = {type, target, x0: x, y0: y, t0: t, moved: false, role: null, lastCell: target.kind === "cell" ? target.cell : null};
		this.pointers.set(id, p);
		if (target.kind === "level") {
			if (this.edit) {
				p.role = "level";
				const cells = [...this.edit.cells].map(parse);
				out.push({type: "editApply", cells, field: "vel", value: target.value});
				this.edit.applied = true;
				// A latched strip closes on apply; a held strip stays for further levels.
				if (this.edit.held.size === 0) this._closeEdit(out);
			}
			return out;
		}
		if (target.kind === "outside") {
			p.role = "outside";
			if (this.edit && this.edit.held.size === 0) this._closeEdit(out);
			return out;
		}
		// A cell. If the strip is open, this contact joins the selection at once
		// (Push: hold several pads to edit them together); otherwise it is a
		// candidate tap/hold/paint and the hold timer decides.
		if (this.edit) {
			p.role = "select";
			this._openEdit(target.cell, id, out);
			return out;
		}
		p.role = "pending";
		return out;
	};

	GridGestures.prototype.move = function (id, target, x, y, t) {
		const out = [];
		const p = this.pointers.get(id);
		if (!p) return out;
		this.tick(t, out);
		const dx = x - p.x0, dy = y - p.y0;
		if (!p.moved && (dx * dx + dy * dy) > this.o.slopPx * this.o.slopPx) p.moved = true;
		if (p.role === "pending" && p.moved) {
			// Became a drag: paint along the row with the state the first cell is taking.
			p.role = "paint";
			p.paintOn = !this.isOn(p.target.cell);
			out.push({type: "paint", cell: p.target.cell, on: p.paintOn});
		}
		if (p.role === "paint" && target.kind === "cell" && target.cell.row === p.target.cell.row) {
			if (!p.lastCell || key(target.cell) !== key(p.lastCell)) {
				p.lastCell = target.cell;
				out.push({type: "paint", cell: target.cell, on: p.paintOn});
			}
		}
		return out;
	};

	GridGestures.prototype.up = function (id, t) {
		const out = [];
		const p = this.pointers.get(id);
		this.cap.up(id);
		if (!p) return out;
		this.tick(t, out);
		this.pointers.delete(id);
		if (p.role === "pending") {
			// Short press without movement: a tap. (Hold was not reached, else role would be "hold".)
			out.push({type: "toggle", cell: p.target.cell});
		} else if (p.role === "hold" || p.role === "select") {
			if (this.edit) {
				this.edit.held.delete(id);
				if (this.edit.held.size === 0) {
					if (this.edit.applied) this._closeEdit(out);       // hardware idiom: lift after choosing a level
					else this.edit.latchUntil = t + this.o.latchMs;     // single-contact form: strip stays latched
				}
			}
		}
		return out;
	};

	GridGestures.prototype.cancel = function (id, t) {
		// pointercancel: the browser took the stream (should never happen under touch-action: none).
		const out = [];
		const p = this.pointers.get(id);
		this.cap.up(id);
		if (!p) return out;
		this.pointers.delete(id);
		if (this.edit) { this.edit.held.delete(id); if (this.edit.held.size === 0 && !this.edit.applied) this.edit.latchUntil = t + this.o.latchMs; }
		out.push({type: "cancelled", cell: p.target.cell || null});
		return out;
	};

	// Called on a timer and before every event: promotes pending presses to holds
	// and expires a latched strip.
	GridGestures.prototype.tick = function (t, out) {
		out = out || [];
		for (const [id, p] of this.pointers) {
			if (p.role === "pending" && !p.moved && t - p.t0 >= this.o.holdMs) {
				p.role = "hold";
				this._openEdit(p.target.cell, id, out);
			}
		}
		if (this.edit && this.edit.held.size === 0 && this.edit.latchUntil !== null && t >= this.edit.latchUntil) {
			this._closeEdit(out);
		}
		return out;
	};

	// ---------------------------------------------------------------------
	// Pad recogniser: no gesture at all. Every contact is a voice.
	//   down -> {type:"fire", pad, on:true, vel}
	//   up   -> {type:"fire", pad, on:false}
	// Velocity: fixed, or from the vertical position inside the pad
	// (top = loud, as Novation's Velocity view and NI's 16 Velocities order levels).
	// ---------------------------------------------------------------------
	function PadGestures (opts) {
		this.o = Object.assign({}, DEFAULTS, opts || {});
		this.voices = new Map();   // pointerId -> pad
		this.cap = new CapabilityObserver();
	}
	PadGestures.prototype.down = function (id, type, pad, yFrac, t) {
		this.cap.down(id, type);
		if (!pad) return [];
		let vel = this.o.padFixedVel;
		if (this.o.padVelocityMode === "vertical") {
			const f = Math.min(1, Math.max(0, 1 - yFrac));   // yFrac 0 at top
			vel = Math.max(1, Math.round(1 + f * 126));
		}
		this.voices.set(id, pad);
		return [{type: "fire", pad, on: true, vel, t}];
	};
	PadGestures.prototype.up = function (id, t) {
		this.cap.up(id);
		const pad = this.voices.get(id);
		if (!pad) return [];
		this.voices.delete(id);
		return [{type: "fire", pad, on: false, t}];
	};
	PadGestures.prototype.cancel = PadGestures.prototype.up;

	return {DEFAULTS, CapabilityObserver, GridGestures, PadGestures};
}));
