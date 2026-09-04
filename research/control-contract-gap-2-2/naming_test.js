// Research prototype tests, not house style. node naming_test.js
const N = require('./naming.js');
let pass = 0, fail = 0;
function t(n, f) { try { f(); console.log('ok   ' + n); pass++; } catch (e) { console.log('FAIL ' + n + ': ' + e.message); fail++; } }
function eq(a, b) { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(JSON.stringify(a) + ' != ' + JSON.stringify(b)); }
function ok(v, m) { if (!v) throw new Error(m || 'falsy'); }

const ID_RE = /^[a-z0-9][a-z0-9_-]{0,63}$/;

t('a generated id from a candidate matches the service id rule', () => {
	const id = N.candidateId({ app: 'subsequence', group: 'Kit' });
	eq(id, 'subsequence-kit');
	ok(ID_RE.test(id));
});

t('awkward labels still yield a legal id', () => {
	for (const label of ['Drums / Kit #1', '  ', '---', '808 & 909', 'Ünïcödé', 'x'.repeat(200)]) {
		const id = N.slug(label);
		ok(ID_RE.test(id), label + ' -> ' + id);
		ok(id.length <= N.ID_MAX);
	}
});

t('an empty or punctuation-only label falls back to page', () => {
	eq(N.slug('   '), 'page');
	eq(N.slug('///'), 'page');
});

t('a duplicate id is suffixed and stays legal and unique', () => {
	const existing = ['subsequence-kit', 'subsequence-kit-2'];
	const id = N.uniqueId(existing, 'subsequence-kit');
	eq(id, 'subsequence-kit-3');
	ok(ID_RE.test(id));
});

t('a suffix on a maximum-length id does not overflow', () => {
	const base = N.slug('x'.repeat(200));
	eq(base.length, N.ID_MAX);
	const id = N.uniqueId([base], base);
	ok(id.length <= N.ID_MAX, id.length);
	ok(ID_RE.test(id));
});

t('the key grid fits the panel at a 60 px cell', () => {
	const f = N.keyGridFootprint(60);
	eq(f.cols, 14); eq(f.rows, 5);
	ok(f.px.w <= 1920 && f.px.h <= 1080, JSON.stringify(f));
	eq(f.px, { w: 840, h: 300 });
});

t('keys accumulate a label with shift, backspace and space', () => {
	let s = { label: '', shift: false };
	for (const k of ['shift', 'd', 'r', 'u', 'm', 's', 'space', '1', 'back']) s = N.applyKey(s, k);
	eq(s.label, 'Drums ');
});

t('cancel and done are states, not text', () => {
	let s = N.applyKey({ label: 'x', shift: false }, 'cancel');
	ok(s.cancelled); eq(s.label, 'x');
	s = N.applyKey({ label: 'x', shift: false }, 'done');
	ok(s.done);
});

t('a label is bounded so it cannot grow without limit', () => {
	let s = { label: '', shift: false };
	for (let i = 0; i < 100; i++) s = N.applyKey(s, 'a');
	eq(s.label.length, 40);
});

t('a hardware keystroke drives the same state machine as a drawn key', () => {
	let s = { label: '', shift: false };
	for (const ev of [{ key: 'K' }, { key: 'i' }, { key: 't' }, { key: ' ' }, { key: 'B' }])
		s = N.applyEventKey(s, N.keyFromEvent(ev));
	eq(s.label, 'Kit B');
	s = N.applyEventKey(s, N.keyFromEvent({ key: 'Backspace' }));
	eq(s.label, 'Kit ');
	ok(N.applyEventKey(s, N.keyFromEvent({ key: 'Enter' })).done);
	ok(N.applyEventKey(s, N.keyFromEvent({ key: 'Escape' })).cancelled);
});

t('modified and non-text keystrokes are ignored rather than typed', () => {
	for (const ev of [{ key: 'a', ctrlKey: true }, { key: 'F5' }, { key: 'ArrowLeft' }, { key: '/' }])
		eq(N.keyFromEvent(ev), null, JSON.stringify(ev));
	const s = { label: 'Kit', shift: false };
	eq(N.applyEventKey(s, N.keyFromEvent({ key: 'F5' })).label, 'Kit');
});

console.log('\n' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
