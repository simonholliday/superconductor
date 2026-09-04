// Research prototype (transport-ui): JS-side encode/decode cost, node 18 (V8), indicative for Chromium.
const { encode, decode } = require('@msgpack/msgpack');
const cborx = require('cbor-x');
let seed = 1; const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
const grid = (r, c) => Array.from({length: r}, () => Array.from({length: c}, () => rnd() < 0.3));
const snapshot = (r, c) => ({ t: 'snapshot', seq: 12345, ts: 1756800000.123, controls: {
	'drums.grid': { rows: Array.from({length: r}, (_, i) => `voice${i}`), steps: c, cells: grid(r, c) },
	'drums.length': 16, bpm: 124.0 } });
const delta = { t: 'set', seq: 12346, id: 'drums.grid', cell: [3, 7], v: true };
const beat = { t: 'beat', seq: 12347, pulse: 4104, bar: 42, beat: 3, ts: 1756800000.123 };
const enc = {
	json: [o => new TextEncoder().encode(JSON.stringify(o)), b => JSON.parse(new TextDecoder().decode(b))],
	msgpack: [o => encode(o), b => decode(b)],
	'cbor-x': [o => cborx.encode(o), b => cborx.decode(b)],
};
function bench(name, obj) {
	console.log('\n' + name);
	for (const [k, [e, d]] of Object.entries(enc)) {
		const b = e(obj); const n = 5000;
		for (let i = 0; i < 500; i++) { e(obj); d(b); } // warm
		let t0 = process.hrtime.bigint(); for (let i = 0; i < n; i++) e(obj);
		const te = Number(process.hrtime.bigint() - t0) / n / 1000;
		t0 = process.hrtime.bigint(); for (let i = 0; i < n; i++) d(b);
		const td = Number(process.hrtime.bigint() - t0) / n / 1000;
		console.log(`  ${k.padEnd(8)} ${String(b.length).padStart(6)} bytes  encode ${te.toFixed(1).padStart(7)} us  decode ${td.toFixed(1).padStart(7)} us`);
	}
}
bench('snapshot 16x8 (128 cells)', snapshot(8, 16));
bench('snapshot 64x16 (1024 cells)', snapshot(16, 64));
bench('toggle delta', delta);
bench('beat/playhead', beat);
