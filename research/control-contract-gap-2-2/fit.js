// Research prototype, not product code and not house style.
// What a page declared at one lattice does on a surface that is not the panel:
// the fit rule, the lattice a different confirmed cell size would give, and the
// widget-interior arithmetic that decides how many step columns a grid shows.

// A page declares {cols, rows, cell}. A surface has a viewport in CSS pixels.
// The page is never re-flowed - widget coordinates keep their meaning - so the
// only free variable is the pixels one lattice cell is drawn at.
//
//   scale = min(1, vw / (cols*cell), vh / (rows*cell))
//
// Capped at 1 so a larger surface leaves surplus rather than magnifying the page
// past the size it was authored at; below 1 the whole page shrinks uniformly,
// which is legible on a laptop and is not a surface to play on.
const PLAYABLE_PX = 44;   // WCAG 2.2 SC 2.5.5 enhanced target size, #1927's preferred figure

function fit(page, viewport) {
	const w = page.cols * page.cell, h = page.rows * page.cell;
	const scale = Math.min(1, viewport.w / w, viewport.h / h);
	const cellPx = page.cell * scale;
	return {
		scale,
		cellPx,
		px: { w: w * scale, h: h * scale },
		surplus: { w: viewport.w - w * scale, h: viewport.h - h * scale },
		playable: cellPx >= PLAYABLE_PX,   // false -> a viewer, not a surface to play on
	};
}

// The lattice a surface offers at a given cell size. The surplus is margin, not
// a partial cell: widget coordinates stay integers.
function latticeFor(viewport, cell) {
	const cols = Math.floor(viewport.w / cell), rows = Math.floor(viewport.h / cell);
	return { cols, rows, cell, surplus: { w: viewport.w - cols * cell, h: viewport.h - rows * cell } };
}

// A widget's interior is NOT lattice-quantised: the lattice places widgets, and
// what a widget draws inside itself is its own layout, at its own pixel sizes.
// #1927's own grid arithmetic is this shape - an 80 px row-label column beside
// step cells that are whatever the remaining width divides into.
function stepCell(spanCols, steps, { cell = 60, gutterPx = 80 } = {}) {
	return (spanCols * cell - gutterPx) / steps;
}

// The inverse: how many steps of at least `min` px fit beside the gutter.
function stepsAtLeast(spanCols, min, { cell = 60, gutterPx = 80 } = {}) {
	return Math.floor((spanCols * cell - gutterPx) / min);
}

module.exports = { fit, latticeFor, stepCell, stepsAtLeast, PLAYABLE_PX };
