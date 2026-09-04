// Research prototype tests, not house style. node snapdrag_test.js
const S = require('./snapdrag.js');
let pass = 0, fail = 0;
function t(name, fn) {
	try { fn(); console.log('ok   ' + name); pass++; }
	catch (e) { console.log('FAIL ' + name + ': ' + e.message); fail++; }
}
function eq(a, b, m) { const x = JSON.stringify(a), y = JSON.stringify(b); if (x !== y) throw new Error((m || '') + ' ' + x + ' != ' + y); }
function ok(v, m) { if (!v) throw new Error(m || 'expected truthy'); }

const base = () => [
	{ id: 'grid', x: 0, y: 0, w: 12, h: 6 },
	{ id: 'fader', x: 14, y: 0, w: 2, h: 6 },
	{ id: 'meter', x: 0, y: 8, w: 6, h: 2 },
];

t('lattice tiles the panel exactly', () => {
	eq(1920 / S.CELL, S.COLS); eq(1080 / S.CELL, S.ROWS);
});

t('play mode routes nothing to the arranger', () => {
	const a = new S.Arranger(base());
	eq(a.down(1, 30, 30), null);
});

t('a press in edit mode grabs the widget under the finger', () => {
	const a = new S.Arranger(base()); a.setMode('edit');
	const d = a.down(1, 30, 30);
	eq(d.id, 'grid'); eq(d.kind, 'move');
});

t('a press on empty lattice grabs nothing', () => {
	const a = new S.Arranger(base()); a.setMode('edit');
	eq(a.down(1, 20 * S.CELL, 12 * S.CELL), null);
});

t('a move snaps the ghost to whole cells', () => {
	const a = new S.Arranger(base()); a.setMode('edit');
	a.down(1, 30, 30);
	const d = a.move(1, 30 + 20, 30 + 10 * S.CELL - 20);   // 20 px rounds down, -20 px rounds up
	eq(d.ghost, { x: 0, y: 10, w: 12, h: 6 });
	ok(d.valid);
});

t('a drop commits the snapped rectangle', () => {
	const a = new S.Arranger(base()); a.setMode('edit');
	a.down(1, 30, 30); a.move(1, 30 + 20, 30 + 10 * S.CELL - 20);
	const r = a.up(1);
	ok(r.committed); eq(r.rect, { x: 0, y: 10, w: 12, h: 6 });
	eq(a.commits.length, 1);
});

t('an overlapping drop is refused and the widget snaps back', () => {
	const a = new S.Arranger(base()); a.setMode('edit');
	a.down(1, 30, 30);
	const d = a.move(1, 30 + 3 * S.CELL, 30);   // grid 3..15 would cover fader at 14
	ok(!d.valid);
	const r = a.up(1);
	ok(!r.committed);
	eq(a.layout.find(w => w.id === 'grid'), { id: 'grid', x: 0, y: 0, w: 12, h: 6 });
	eq(a.commits.length, 0);
});

t('a drag off the lattice edge is refused', () => {
	const a = new S.Arranger(base()); a.setMode('edit');
	a.down(1, 30, 30);
	const d = a.move(1, 30 + 21 * S.CELL, 30);  // x=21, 21+12=33 > 32
	ok(!d.valid);
});

t('no widget is displaced by another widget being dragged', () => {
	const a = new S.Arranger(base()); a.setMode('edit');
	a.down(1, 30, 30); a.move(1, 30, 30 + 10 * S.CELL); a.up(1);
	eq(a.layout.find(w => w.id === 'meter'), { id: 'meter', x: 0, y: 8, w: 6, h: 2 });
});

t('a second contact during a drag changes nothing and does not stall it', () => {
	const a = new S.Arranger(base()); a.setMode('edit');
	a.down(1, 30, 30);
	eq(a.down(2, 14 * S.CELL + 10, 10), null);        // second finger grabs nothing
	eq(a.move(2, 900, 900), null);                    // and moves nothing
	const d = a.move(1, 30 + 2 * S.CELL, 30 + 8 * S.CELL);
	eq(d.ghost, { x: 2, y: 8, w: 12, h: 6 });         // the first finger still drives
	ok(!d.valid);                                      // it would cover the meter
});

t('a resize from the corner grows to whole cells and refuses an overlap', () => {
	const a = new S.Arranger(base()); a.setMode('edit');
	a.down(1, 12 * S.CELL - 5, 6 * S.CELL - 5, true);
	let d = a.move(1, 13 * S.CELL, 7 * S.CELL);
	eq(d.ghost, { x: 0, y: 0, w: 13, h: 7 }); ok(d.valid);
	d = a.move(1, 15 * S.CELL, 7 * S.CELL);
	eq(d.ghost, { x: 0, y: 0, w: 15, h: 7 }); ok(!d.valid);   // reaches the fader at 14
	ok(!a.up(1).committed);
});

t('a pointercancel abandons the drag with no commit', () => {
	const a = new S.Arranger(base()); a.setMode('edit');
	a.down(1, 30, 30); a.move(1, 30 + 3 * S.CELL, 30 + 8 * S.CELL);
	const r = a.cancel(1);
	ok(r.cancelled); eq(a.commits.length, 0);
	eq(a.layout.find(w => w.id === 'grid').x, 0);
});

t('leaving edit mode mid-drag abandons it', () => {
	const a = new S.Arranger(base()); a.setMode('edit');
	a.down(1, 30, 30); a.move(1, 30 + 3 * S.CELL, 30 + 8 * S.CELL);
	a.setMode('play');
	eq(a.drag, null);
	eq(a.layout.find(w => w.id === 'grid').x, 0);
});

t('hit test picks the later widget where two are stacked', () => {
	const l = [{ id: 'under', x: 0, y: 0, w: 4, h: 4 }, { id: 'over', x: 2, y: 2, w: 4, h: 4 }];
	eq(S.hitTest(l, 2.5 * S.CELL, 2.5 * S.CELL).id, 'over');
	eq(S.hitTest(l, 0.5 * S.CELL, 0.5 * S.CELL).id, 'under');
});

t('tap-to-place moves a selected widget to the tapped cell with no drag at all', () => {
	const a = new S.Arranger(base()); a.setMode('edit');
	eq(a.select(30, 30), 'grid');
	const r = a.place(18 * S.CELL + 5, 10 * S.CELL + 5);
	ok(r.committed);
	eq(a.layout.find(w => w.id === 'grid').x, 18);
	eq(a.layout.find(w => w.id === 'grid').y, 10);
	eq(a.selected, null, 'the selection clears on a committed place');
});

t('tap-to-place refuses an overlap and an off-lattice landing, and keeps the selection', () => {
	const a = new S.Arranger(base()); a.setMode('edit');
	a.select(0, 8 * S.CELL);                            // meter, 6x2 at (0,8)
	eq(a.place(13 * S.CELL, 0).committed, false);       // would overlap fader at x=14
	eq(a.place(30 * S.CELL, 0).committed, false);       // 6 wide from x=30 runs off a 32 lattice
	eq(a.selected, 'meter');
	eq(a.layout.find(w => w.id === 'meter').x, 0);
	eq(a.commits.length, 0);
});

t('tap-to-place is inert in play mode and after a select on empty lattice', () => {
	const a = new S.Arranger(base());
	eq(a.select(30, 30), null, 'play mode selects nothing');
	eq(a.place(0, 0), null);
	a.setMode('edit');
	eq(a.select(20 * S.CELL, 12 * S.CELL), null, 'empty lattice selects nothing');
	eq(a.place(0, 0), null);
});

console.log('\n' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
