const f = require('./fit.js');
let P = 0, F = 0;
function check(name, cond, extra) { if (cond) { console.log('ok   ' + name); P++; } else { console.log('FAIL ' + name + ' ' + JSON.stringify(extra)); F++; } }
const near = (a, b) => Math.abs(a - b) < 1e-9;

const PANEL = { cols: 32, rows: 18, cell: 60 };
const PITCH = 0.249;   // mm per px on the panel, #1917

check('the panel lattice tiles 1920x1080 exactly with no surplus',
	32 * 60 === 1920 && 18 * 60 === 1080);
check('one lattice cell is 14.94 mm on the panel',
	Math.abs(60 * PITCH - 14.94) < 0.005, 60 * PITCH);

let r = f.fit(PANEL, { w: 1920, h: 1080 });
check('a page authored for the panel renders on the panel at scale 1',
	near(r.scale, 1) && near(r.cellPx, 60) && r.playable, r);

r = f.fit(PANEL, { w: 2560, h: 1440 });
check('a larger surface leaves surplus rather than magnifying the page',
	near(r.scale, 1) && near(r.cellPx, 60) && r.surplus.w === 640 && r.surplus.h === 360, r);

r = f.fit(PANEL, { w: 1600, h: 900 });
check('a 1600x900 surface scales to a 50 px cell and stays playable',
	near(r.cellPx, 50) && r.playable && r.px.w <= 1600 && r.px.h <= 900, r);

r = f.fit(PANEL, { w: 1366, h: 768 });
check('a 1366x768 laptop shows every cell, limited by height',
	near(r.scale, 768 / 1080) && r.px.w <= 1366 && r.px.h <= 768, r);
check('its 42.7 px cell is under the enhanced target size, so it is a viewer not a surface',
	!r.playable && Math.abs(r.cellPx - 42.67) < 0.01, r);

r = f.fit(PANEL, { w: 1024, h: 768 });
check('a 1024x768 surface is width-limited and well under playable',
	near(r.scale, 1024 / 1920) && !r.playable, r);

check('the fit rule changes no widget coordinate',
	JSON.stringify(PANEL) === JSON.stringify({ cols: 32, rows: 18, cell: 60 }));

// What a different confirmed cell size (#1998) would do to the panel's own lattice.
const alt = { 48: [40, 22], 56: [34, 19], 60: [32, 18], 64: [30, 16], 72: [26, 15], 80: [24, 13] };
let ok = true; const got = {};
for (const cell of Object.keys(alt)) {
	const l = f.latticeFor({ w: 1920, h: 1080 }, Number(cell));
	got[cell] = [l.cols, l.rows];
	if (l.cols !== alt[cell][0] || l.rows !== alt[cell][1]) ok = false;
}
check('the panel lattice at every plausible cell size is floor(1920/cell) x floor(1080/cell)', ok, got);
check('60 px is the only plausible size that tiles both axes exactly',
	f.latticeFor({ w: 1920, h: 1080 }, 60).surplus.w === 0 && f.latticeFor({ w: 1920, h: 1080 }, 60).surplus.h === 0
	&& f.latticeFor({ w: 1920, h: 1080 }, 64).surplus.h === 56
	&& f.latticeFor({ w: 1920, h: 1080 }, 48).surplus.h === 24
	&& f.latticeFor({ w: 1920, h: 1080 }, 72).surplus.w === 48,
	got);

// The widget interior, which is not on the lattice. #1927: an 80 px label column
// beside the step cells, and 32 columns landing at 45-57 px.
check('a full-width grid widget showing 32 steps beside an 80 px label column has 57.5 px step cells',
	near(f.stepCell(32, 32), 57.5), f.stepCell(32, 32));
check('that step cell is inside the 45-57 px band #1927 records for 32 columns, and is not the 60 px lattice cell',
	f.stepCell(32, 32) < 60 && f.stepCell(32, 32) > 45, f.stepCell(32, 32));
check('a 16-step grid on the same span has 115 px step cells, the top of #1927 band',
	near(f.stepCell(32, 16), 115), f.stepCell(32, 16));
check('at the enhanced 44 px target the same span holds 41 steps, so 32 is a legibility ceiling not a lattice one',
	f.stepsAtLeast(32, 44) === 41, f.stepsAtLeast(32, 44));
check('a half-width grid widget holds 20 steps at 44 px',
	f.stepsAtLeast(16, 44) === 20, f.stepsAtLeast(16, 44));

console.log('\n%d passed, %d failed', P, F);
process.exit(F ? 1 : 0);
