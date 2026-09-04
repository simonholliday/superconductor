// Research prototype, not product code and not house style.
// The keyboardless naming path: a generated id and label from a candidate page,
// and the layout of a page-drawn key grid that needs no focusable input.

const ID_MAX = 64;

// The same shape the service's ID_RE enforces: [a-z0-9][a-z0-9_-]{0,63}
function slug(text) {
	let s = String(text).toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '');
	s = s.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
	if (!s) s = 'page';
	if (!/^[a-z0-9]/.test(s)) s = 'p' + s;
	return s.slice(0, ID_MAX);
}

// A candidate from #1916's rule carries {app, group, label}. The generated id is
// app-group, so two apps' "kit" groups do not collide.
function candidateId(candidate) {
	const parts = [candidate.app, candidate.group].filter(Boolean).map(slug);
	return slug(parts.join('-'));
}

function uniqueId(existingIds, base) {
	const taken = new Set(existingIds);
	if (!taken.has(base)) return base;
	for (let n = 2; ; n++) {
		const suffix = '-' + n;
		const cand = base.slice(0, ID_MAX - suffix.length) + suffix;
		if (!taken.has(cand)) return cand;
	}
}

// The page-drawn key grid. No <input>, no focus, no OS keyboard: each key is a
// cell of the same widget the grid already draws, pressed with the same recogniser.
const KEY_ROWS = [
	'1234567890'.split(''),
	'qwertyuiop'.split(''),
	'asdfghjkl'.split('').concat(['-']),
	['shift'].concat('zxcvbnm'.split('')).concat(['back', 'space']),
	['cancel', 'done'],
];

// Wide keys span more than one lattice cell.
const KEY_SPAN = { shift: 2, back: 2, space: 3, cancel: 3, done: 3 };
function keySpan(k) { return KEY_SPAN[k] || 1; }

function keyGridFootprint(cell) {
	const cols = Math.max(...KEY_ROWS.map(r => r.reduce((a, k) => a + keySpan(k), 0)));
	return { cols, rows: KEY_ROWS.length, px: { w: cols * cell, h: KEY_ROWS.length * cell } };
}

// The label is what the user types or accepts; the id is derived once, at create
// time, and never changes afterwards, so a rename never moves the file.
function applyKey(state, key) {
	const s = { ...state };
	if (key === 'back') s.label = s.label.slice(0, -1);
	else if (key === 'space') s.label = s.label + ' ';
	else if (key === 'shift') s.shift = !s.shift;
	else if (key === 'cancel') { s.cancelled = true; }
	else if (key === 'done') { s.done = true; }
	else { s.label = s.label + (s.shift ? key.toUpperCase() : key); s.shift = false; }
	s.label = s.label.slice(0, 40);
	return s;
}

// A physical keyboard needs no focusable element, so it is inside the suppression set, which
// forbids focusable text inputs and says nothing about keystrokes. A document-level keydown
// listener maps a real key onto the same applyKey the drawn grid drives, so on the two hosts
// that have a keyboard (a Windows desktop with the panel as a second monitor, a laptop) a name
// is typed, and on the panel it is tapped, through one state machine.
function keyFromEvent(ev) {
	if (ev.ctrlKey || ev.altKey || ev.metaKey) return null;
	switch (ev.key) {
		case 'Backspace': return 'back';
		case 'Enter': return 'done';
		case 'Escape': return 'cancel';
		case ' ': return 'space';
	}
	if (ev.key.length !== 1) return null;
	const lower = ev.key.toLowerCase();
	if (!/^[a-z0-9-]$/.test(lower)) return null;
	return { key: lower, upper: ev.key !== lower };
}

// Apply whatever keyFromEvent returned; an upper-case keystroke carries its own shift.
function applyEventKey(state, mapped) {
	if (mapped === null) return state;
	if (typeof mapped === 'string') return applyKey(state, mapped);
	return applyKey({ ...state, shift: mapped.upper }, mapped.key);
}

module.exports = { slug, candidateId, uniqueId, KEY_ROWS, KEY_SPAN, keySpan, keyGridFootprint,
	applyKey, keyFromEvent, applyEventKey, ID_MAX };
