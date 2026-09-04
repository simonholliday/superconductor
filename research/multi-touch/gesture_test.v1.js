/* Research prototype tests for gesture.js. Run: node gesture_test.js */
"use strict";
const assert = require("assert");
const G = require("./gesture.js");

const cell = (row, col) => ({kind: "cell", cell: {row, col}});
const level = v => ({kind: "level", value: v});
const outside = {kind: "outside"};
const types = a => a.map(x => x.type);

function grid (on) {
	const state = new Set(on || []);
	const g = new G.GridGestures({isOn: c => state.has(c.row + ":" + c.col)});
	return g;
}

let passed = 0;
function test (name, fn) { fn(); passed++; console.log("ok  " + name); }

test("tap toggles (touch)", () => {
	const g = grid();
	assert.deepStrictEqual(g.down(11, "touch", cell("kick", 4), 100, 100, 0), []);
	const out = g.up(11, 120);
	assert.deepStrictEqual(out, [{type: "toggle", cell: {row: "kick", col: 4}}]);
});

test("tap toggles (mouse, pointerId 1 as Chromium, 0 as Firefox)", () => {
	for (const id of [1, 0]) {
		const g = grid();
		g.down(id, "mouse", cell("kick", 4), 100, 100, 0);
		assert.deepStrictEqual(types(g.up(id, 150)), ["toggle"]);
		assert.strictEqual(g.cap.state(), "mouse");
	}
});

test("hold opens edit strip and does not toggle; release latches; level applies and closes (single contact form)", () => {
	const g = grid();
	g.down(11, "touch", cell("snare", 2), 0, 0, 0);
	assert.deepStrictEqual(types(g.tick(399)), []);
	const o1 = g.tick(400);
	assert.deepStrictEqual(o1, [{type: "editOpen", cells: [{row: "snare", col: 2}]}]);
	const o2 = g.up(11, 600);
	assert.deepStrictEqual(o2, []);                       // no toggle, strip stays (latched)
	const o3 = g.down(12, "touch", level(127), 0, 0, 900);
	assert.deepStrictEqual(o3, [
		{type: "editApply", cells: [{row: "snare", col: 2}], field: "vel", value: 127},
		{type: "editClose"},
	]);
	assert.strictEqual(g.cap.state(), "single");
});

test("latched strip expires after latchMs with no action", () => {
	const g = grid();
	g.down(11, "touch", cell("snare", 2), 0, 0, 0);
	g.tick(400); g.up(11, 500);
	assert.deepStrictEqual(g.tick(3499), []);
	assert.deepStrictEqual(g.tick(3500), [{type: "editClose"}]);
});

test("hold-and-tap with two fingers: held cell edited, second finger picks a level, strip stays until the hold lifts", () => {
	const g = grid();
	g.down(11, "touch", cell("hat", 6), 0, 0, 0);
	assert.deepStrictEqual(types(g.tick(400)), ["editOpen"]);
	const o = g.down(12, "touch", level(127), 500, 900, 700);   // second finger on the accent level
	assert.deepStrictEqual(o, [{type: "editApply", cells: [{row: "hat", col: 6}], field: "vel", value: 127}]);
	assert.deepStrictEqual(g.up(12, 760), []);
	assert.deepStrictEqual(g.up(11, 900), [{type: "editClose"}]);
	assert.strictEqual(g.cap.state(), "confirmed");
});

test("multi-hold: cells touched while the strip is open join the selection and one level edits all", () => {
	const g = grid();
	g.down(11, "touch", cell("hat", 0), 0, 0, 0);
	g.tick(400);
	assert.deepStrictEqual(g.down(12, "touch", cell("hat", 4), 0, 0, 450), [{type: "editSelect", cells: [{row: "hat", col: 0}, {row: "hat", col: 4}]}]);
	assert.deepStrictEqual(g.down(13, "touch", cell("hat", 8), 0, 0, 500)[0].cells.length, 3);
	const o = g.down(14, "touch", level(70), 0, 0, 600);
	assert.strictEqual(o[0].type, "editApply");
	assert.strictEqual(o[0].cells.length, 3);
	assert.strictEqual(o[0].value, 70);
	g.up(14, 650); g.up(12, 700); g.up(13, 720);
	assert.deepStrictEqual(g.up(11, 800), [{type: "editClose"}]);
});

test("single-contact multi-select: hold, lift, tap more cells (they select, not toggle), pick level", () => {
	const g = grid();
	g.down(11, "touch", cell("kick", 0), 0, 0, 0); g.tick(400); g.up(11, 450);
	const o1 = g.down(11, "touch", cell("kick", 8), 0, 0, 900);
	assert.deepStrictEqual(types(o1), ["editSelect"]);
	assert.deepStrictEqual(g.up(11, 950), []);               // no toggle
	const o2 = g.down(11, "touch", level(40), 0, 0, 1200);
	assert.deepStrictEqual(o2[0].cells, [{row: "kick", col: 0}, {row: "kick", col: 8}]);
	assert.deepStrictEqual(types(o2), ["editApply", "editClose"]);
});

test("tap outside closes a latched strip; ignored while a finger still holds", () => {
	const g = grid();
	g.down(11, "touch", cell("kick", 0), 0, 0, 0); g.tick(400);
	assert.deepStrictEqual(g.down(12, "touch", outside, 0, 0, 500), []);
	g.up(12, 520);
	g.up(11, 600);
	assert.deepStrictEqual(g.down(12, "touch", outside, 0, 0, 700), [{type: "editClose"}]);
});

test("drag paints along the row with the first cell's new state and never toggles on release", () => {
	const g = grid(["kick:2"]);   // col 2 is on, so painting from it clears
	g.down(11, "touch", cell("kick", 2), 100, 100, 0);
	assert.deepStrictEqual(g.move(11, cell("kick", 2), 105, 100, 30), []);          // inside slop
	const o1 = g.move(11, cell("kick", 3), 140, 100, 60);
	assert.deepStrictEqual(o1, [{type: "paint", cell: {row: "kick", col: 2}, on: false}, {type: "paint", cell: {row: "kick", col: 3}, on: false}]);
	assert.deepStrictEqual(g.move(11, cell("kick", 3), 150, 100, 80), []);          // same cell, no repeat
	assert.deepStrictEqual(g.move(11, cell("snare", 4), 180, 200, 100), []);        // other row ignored
	assert.deepStrictEqual(g.move(11, cell("kick", 4), 190, 100, 120), [{type: "paint", cell: {row: "kick", col: 4}, on: false}]);
	assert.deepStrictEqual(g.up(11, 900), []);                                      // long drag, no hold, no toggle
});

test("slow press that moves beyond slop before holdMs is a paint, not a hold", () => {
	const g = grid();
	g.down(11, "touch", cell("kick", 0), 0, 0, 0);
	g.move(11, cell("kick", 1), 40, 0, 300);
	assert.deepStrictEqual(g.tick(500), []);
	assert.strictEqual(g.edit, null);
});

test("pointercancel discards the contact without a toggle", () => {
	const g = grid();
	g.down(11, "touch", cell("kick", 0), 0, 0, 0);
	assert.deepStrictEqual(g.cancel(11, 50), [{type: "cancelled", cell: {row: "kick", col: 0}}]);
	assert.deepStrictEqual(g.up(11, 60), []);
});

test("pads: each contact is a voice; chords are concurrent fires; fixed velocity", () => {
	const p = new G.PadGestures();
	const a = p.down(21, "touch", "kicks", 0.5, 0);
	const b = p.down(22, "touch", "snares", 0.5, 12);
	assert.deepStrictEqual(a, [{type: "fire", pad: "kicks", on: true, vel: 110, t: 0}]);
	assert.deepStrictEqual(b, [{type: "fire", pad: "snares", on: true, vel: 110, t: 12}]);
	assert.strictEqual(p.cap.state(), "confirmed");
	assert.deepStrictEqual(p.up(21, 200), [{type: "fire", pad: "kicks", on: false, t: 200}]);
	assert.deepStrictEqual(p.up(22, 210), [{type: "fire", pad: "snares", on: false, t: 210}]);
	assert.deepStrictEqual(p.up(22, 220), []);
});

test("pads: vertical velocity mode maps top to 127 and bottom to 1", () => {
	const p = new G.PadGestures({padVelocityMode: "vertical"});
	assert.strictEqual(p.down(1, "mouse", "kicks", 0.0, 0)[0].vel, 127);
	p.up(1, 1);
	assert.strictEqual(p.down(1, "mouse", "kicks", 1.0, 2)[0].vel, 1);
	p.up(1, 3);
	assert.strictEqual(p.down(1, "mouse", "kicks", 0.5, 4)[0].vel, 64);
});

test("capability observer: mouse only, then one touch, then two", () => {
	const c = new G.CapabilityObserver();
	assert.strictEqual(c.state(), "unknown");
	c.down(1, "mouse"); assert.strictEqual(c.state(), "mouse"); c.up(1);
	c.down(5, "touch"); assert.strictEqual(c.state(), "single"); c.up(5);
	c.down(6, "touch"); c.down(7, "pen"); assert.strictEqual(c.state(), "confirmed");
});

console.log(passed + " tests passed");
