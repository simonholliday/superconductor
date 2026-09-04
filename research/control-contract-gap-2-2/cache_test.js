const c = require('./cache.js');
let P = 0, F = 0;
function check(name, cond, extra) { if (cond) { console.log('ok   ' + name); P++; } else { console.log('FAIL ' + name + ' ' + JSON.stringify(extra)); F++; } }

const doc = { page_contract: '1.1.0', id: 'drums', label: 'Drums', order: 0, lattice: { cols: 32, rows: 18, cell: 60 }, widgets: [] };
const clean = { id: 'drums', etag: '"aaa"', doc, dirty: false };
const dirty = { ...clean, dirty: true };

check('a cold boot with no service and no cache shows nothing and says so',
	c.reconcile(null, { net: false }).state === 'offline-empty');
check('a cold boot with a reachable service loads and caches the document',
	c.reconcile(null, { status: 200, id: 'drums', etag: '"aaa"', doc }).cache.etag === '"aaa"');
check('a warm boot with an unreachable service draws the cached page rather than a blank panel',
	(r => r.draw === doc && r.state === 'offline')(c.reconcile(clean, { net: false })));
check('a warm boot with unsaved work and no service says the work is unsaved',
	c.reconcile(dirty, { net: false }).state === 'offline-unsaved');
check('a 304 confirms the cache without redrawing anything',
	(r => r.state === 'current' && r.draw === doc)(c.reconcile(clean, { status: 304 })));
check('a 200 on a clean cache replaces the cached document and its ETag',
	(r => r.state === 'loaded' && r.cache.etag === '"bbb"')(c.reconcile(clean, { status: 200, id: 'drums', etag: '"bbb"', doc: { ...doc, label: 'Theirs' } })));
check('a 200 on unsaved work is a conflict, and the local arrangement is not discarded',
	(r => r.state === 'conflict' && r.draw === doc && r.server.label === 'Theirs')(c.reconcile(dirty, { status: 200, id: 'drums', etag: '"bbb"', doc: { ...doc, label: 'Theirs' } })));
check('a 404 on a clean cache drops it and opens the picker',
	(r => r.state === 'picker' && r.cache === null)(c.reconcile(clean, { status: 404 })));
check('a 404 on unsaved work turns the save into a create',
	(r => r.state === 'recreate' && r.cache.etag === null)(c.reconcile(dirty, { status: 404 })));

check('a save built on a cached copy carries If-Match with the cached ETag',
	c.saveRequest(clean).headers['If-Match'] === '"aaa"', c.saveRequest(clean));
check('a save with no ETag at all is a create, never an unconditional write',
	c.saveRequest({ ...clean, etag: null }).headers['If-None-Match'] === '*');
check('no save the panel can build is unconditional, so 428 is unreachable from the panel',
	['If-Match', 'If-None-Match'].some(h => h in c.saveRequest(clean).headers)
	&& ['If-Match', 'If-None-Match'].some(h => h in c.saveRequest({ ...clean, etag: null }).headers));

check('a 200 clears the dirty flag and adopts the new ETag',
	(r => r.state === 'saved' && r.cache.dirty === false && r.cache.etag === '"ccc"')(c.afterSave(dirty, { status: 200, etag: '"ccc"' })));
check('a 412 keeps the work, marks it unsaved and remembers their ETag',
	(r => r.state === 'refused' && r.cache.dirty === true && r.theirEtag === '"bbb"')(c.afterSave(clean, { status: 412, etag: '"bbb"' })));
check('an unsent save keeps the work and marks it unsaved',
	c.afterSave(clean, { net: false }).cache.dirty === true);
check('keep-mine re-sends the same document against the ETag the 412 named',
	(r => r.headers['If-Match'] === '"bbb"' && r.body === doc)(c.keepMine(clean, '"bbb"')));

const strip = { pages: [{ id: 'drums', label: 'Drums', order: 0, etag: '"a"' }, { id: 'pads', label: 'Pads', order: 1, etag: '"b"' }] };
check('a page_changed for a known page updates its ETag with no refetch',
	(r => r.refetch === false && r.pages[0].etag === '"z"')(c.applyFrame(strip, { t: 'page_changed', id: 'drums', op: 'saved', etag: '"z"' })));
check('a delete on another panel removes the page from the bar',
	(r => r.pages.length === 1 && r.pages[0].id === 'drums')(c.applyFrame(strip, { t: 'page_changed', id: 'pads', op: 'deleted', etag: null })));
check('a create on another panel is the one frame that costs a listing refetch',
	c.applyFrame(strip, { t: 'page_changed', id: 'keys', op: 'created', etag: '"k"' }).refetch === true);
check('a reorder frame reorders the bar in place with no refetch',
	(r => r.refetch === false && r.pages.map(p => p.id).join() === 'pads,drums')(c.applyFrame(strip, { t: 'pages_reordered', order: ['pads', 'drums'], etags: { pads: '"b2"', drums: '"a2"' } })));
check('a reorder naming a page the bar has never seen forces a refetch',
	c.applyFrame(strip, { t: 'pages_reordered', order: ['pads', 'drums', 'keys'], etags: {} }).refetch === true);

console.log('\n%d passed, %d failed', P, F);
process.exit(F ? 1 : 0);
