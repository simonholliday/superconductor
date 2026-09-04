// Research prototype, not product code and not house style.
// A bespoke snap-drag layout engine on a fixed lattice, for the Superintendent
// page-arrangement question. Pure functions plus one small state machine, so it
// runs under node with injected pointer events and in a browser unchanged.
//
// Model: the page is a fixed lattice of COLS x ROWS cells of CELL px. A widget
// occupies an integer rectangle. Overlap is refused rather than resolved: no
// widget ever moves because another one was dragged.

const CELL = 60;
const COLS = 32;
const ROWS = 18;

function rect(w) { return { x: w.x, y: w.y, w: w.w, h: w.h }; }

function overlaps(a, b) {
	return !(a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y);
}

function inBounds(r, cols, rows) {
	return r.x >= 0 && r.y >= 0 && r.x + r.w <= cols && r.y + r.h <= rows;
}

// Is this placement legal for widget `id` given every other widget?
function legal(layout, id, r, cols = COLS, rows = ROWS) {
	if (!inBounds(r, cols, rows)) return false;
	for (const w of layout) {
		if (w.id === id) continue;
		if (overlaps(r, w)) return false;
	}
	return true;
}

// Which widget is under a page-pixel point? Last one wins (draw order).
function hitTest(layout, px, py, cell = CELL) {
	const cx = Math.floor(px / cell), cy = Math.floor(py / cell);
	let found = null;
	for (const w of layout) {
		if (cx >= w.x && cx < w.x + w.w && cy >= w.y && cy < w.y + w.h) found = w;
	}
	return found;
}

class Arranger {
	// mode: 'play' | 'edit'. In play mode the arranger sees nothing: the caller
	// does not route pointers here at all. Kept as a flag so the tests can assert it.
	constructor(layout, opts = {}) {
		this.layout = layout.map(w => ({ ...w }));
		this.cell = opts.cell || CELL;
		this.cols = opts.cols || COLS;
		this.rows = opts.rows || ROWS;
		this.mode = 'play';
		this.drag = null;      // {id, kind:'move'|'resize', pointerId, grabDx, grabDy, ghost, valid}
		this.selected = null;  // id selected for tap-to-place, the no-drag entry point
		this.commits = [];     // committed layouts, for the tests
	}

	setMode(m) { this.mode = m; if (m === 'play') { this.drag = null; this.selected = null; } }

	// Tap-to-place: the second entry point into the same legal()-and-commit engine, for a host
	// that delivers no usable drag and for anyone who would rather not drag. select() latches a
	// widget; place() moves its top-left corner to the tapped cell, refusing an illegal landing
	// exactly as a drop does. Nothing here has a timer or a slop threshold.
	select(px, py) {
		if (this.mode !== 'edit' || this.drag) return null;
		const w = hitTest(this.layout, px, py, this.cell);
		this.selected = w ? w.id : null;
		return this.selected;
	}

	place(px, py) {
		if (this.mode !== 'edit' || this.drag || !this.selected) return null;
		const w = this.layout.find(v => v.id === this.selected);
		const r = { x: Math.floor(px / this.cell), y: Math.floor(py / this.cell), w: w.w, h: w.h };
		if (!legal(this.layout, w.id, r, this.cols, this.rows)) return { committed: false, id: w.id };
		w.x = r.x; w.y = r.y;
		this.commits.push(this.layout.map(v => ({ ...v })));
		const id = this.selected;
		this.selected = null;
		return { committed: true, id, rect: rect(w) };
	}

	// pointerdown at page pixels (px,py). `corner` says the press landed on the
	// resize handle of the widget it hit.
	down(pointerId, px, py, corner = false) {
		if (this.mode !== 'edit') return null;      // play mode never reaches here
		if (this.drag) return null;                 // one drag at a time; extra contacts are ignored
		const w = hitTest(this.layout, px, py, this.cell);
		if (!w) return null;
		this.drag = {
			id: w.id,
			kind: corner ? 'resize' : 'move',
			pointerId,
			grabDx: px - w.x * this.cell,
			grabDy: py - w.y * this.cell,
			ghost: rect(w),
			valid: true,
		};
		return this.drag;
	}

	move(pointerId, px, py) {
		const d = this.drag;
		if (!d || d.pointerId !== pointerId) return null;   // a second finger changes nothing
		const w = this.layout.find(v => v.id === d.id);
		if (d.kind === 'move') {
			const gx = Math.round((px - d.grabDx) / this.cell);
			const gy = Math.round((py - d.grabDy) / this.cell);
			d.ghost = { x: gx, y: gy, w: w.w, h: w.h };
		} else {
			const gw = Math.max(1, Math.round(px / this.cell) - w.x);
			const gh = Math.max(1, Math.round(py / this.cell) - w.y);
			d.ghost = { x: w.x, y: w.y, w: gw, h: gh };
		}
		d.valid = legal(this.layout, d.id, d.ghost, this.cols, this.rows);
		return d;
	}

	up(pointerId) {
		const d = this.drag;
		if (!d || d.pointerId !== pointerId) return null;
		this.drag = null;
		if (!d.valid) return { committed: false, id: d.id };   // snaps back
		const w = this.layout.find(v => v.id === d.id);
		w.x = d.ghost.x; w.y = d.ghost.y; w.w = d.ghost.w; w.h = d.ghost.h;
		this.commits.push(this.layout.map(v => ({ ...v })));
		return { committed: true, id: d.id, rect: rect(w) };
	}

	cancel(pointerId) {
		const d = this.drag;
		if (!d || d.pointerId !== pointerId) return null;
		this.drag = null;
		return { committed: false, id: d.id, cancelled: true };
	}
}

module.exports = { CELL, COLS, ROWS, Arranger, hitTest, legal, overlaps, inBounds };
