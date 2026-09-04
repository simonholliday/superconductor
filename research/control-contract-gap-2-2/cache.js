// Research prototype, not product code and not house style.
// The browser half of the page model: what localStorage holds, what the panel
// draws before the network answers, and which precondition a save carries when
// it was built on a cached copy. The service half is pages_routes.py; this is
// the client side of the same compare-and-swap.

// One key per concern. #1916 caches "the last-open page" only, so the document
// cache holds exactly one page; the strip cache holds only what the page bar
// needs to draw, never the documents.
const KEY_PAGE = 'superintendent.page';    // {id, etag, doc, dirty}
const KEY_STRIP = 'superintendent.strip';  // {pages: [{id, label, order, etag}], at}

// Boot. The panel draws the cached page immediately - nothing waits on the LAN -
// and then reconciles. `res` is what GET /api/pages/{id} answered, or {net: false}
// when the service could not be reached at all.
function reconcile(cached, res) {
	if (!cached) {
		if (!res || res.net === false) return { draw: null, state: 'offline-empty', cache: null };
		if (res.status === 200) return { draw: res.doc, state: 'loaded', cache: { id: res.id, etag: res.etag, doc: res.doc, dirty: false } };
		return { draw: null, state: 'picker', cache: null };
	}
	if (!res || res.net === false) {
		// Draw from the cache and say so. Saving is still allowed: the ETag the
		// cache holds is a precondition the service will judge, not a claim.
		return { draw: cached.doc, state: cached.dirty ? 'offline-unsaved' : 'offline', cache: cached };
	}
	if (res.status === 304) return { draw: cached.doc, state: 'current', cache: cached };
	if (res.status === 200) {
		if (cached.dirty) {
			// The page moved under unsaved local work. Never discard silently.
			return { draw: cached.doc, state: 'conflict', server: res.doc, cache: { ...cached, serverEtag: res.etag } };
		}
		return { draw: res.doc, state: 'loaded', cache: { id: res.id, etag: res.etag, doc: res.doc, dirty: false } };
	}
	if (res.status === 404) {
		// Deleted on another panel. Local work is not thrown away: it becomes a
		// create, which the service answers 412 if the id has been taken again.
		return cached.dirty
			? { draw: cached.doc, state: 'recreate', cache: { ...cached, etag: null } }
			: { draw: null, state: 'picker', cache: null };
	}
	return { draw: cached.doc, state: 'error', cache: cached };
}

// The precondition a save carries. There is always exactly one: the service
// refuses an unconditional write with 428.
function saveRequest(cached) {
	if (!cached) return null;
	return cached.etag
		? { method: 'PUT', id: cached.id, headers: { 'If-Match': cached.etag }, body: cached.doc }
		: { method: 'PUT', id: cached.id, headers: { 'If-None-Match': '*' }, body: cached.doc };
}

// What the panel does with the service's answer to that save.
function afterSave(cached, res) {
	if (res.status === 200 || res.status === 201) {
		return { state: 'saved', cache: { ...cached, etag: res.etag, dirty: false } };
	}
	if (res.status === 412) {
		// Somebody else saved first. The 412 body carries the current ETag; the
		// panel offers take-theirs or keep-mine and never drops the arrangement.
		return { state: 'refused', theirEtag: res.etag || null, cache: { ...cached, dirty: true } };
	}
	if (res.net === false) return { state: 'unsent', cache: { ...cached, dirty: true } };
	return { state: 'rejected', cache: { ...cached, dirty: true } };
}

// "Keep mine" is the same document re-sent against the ETag the 412 named. It is
// a deliberate overwrite, never an automatic retry.
function keepMine(cached, theirEtag) {
	return saveRequest({ ...cached, etag: theirEtag });
}

// The page bar draws from the strip cache and is corrected by page_changed and
// pages_reordered frames, so a second panel's create or delete is not missed.
function applyFrame(strip, frame) {
	const pages = (strip && strip.pages ? strip.pages : []).slice();
	if (frame.t === 'page_changed') {
		const i = pages.findIndex(p => p.id === frame.id);
		if (frame.op === 'deleted') { if (i >= 0) pages.splice(i, 1); return { pages, refetch: false }; }
		if (i >= 0) { pages[i] = { ...pages[i], etag: frame.etag }; return { pages, refetch: false }; }
		// A page created on another panel: the bar knows the id but not its label
		// or order, so this is the one frame that costs a GET /api/pages.
		return { pages, refetch: true };
	}
	if (frame.t === 'pages_reordered') {
		const by = new Map(pages.map(p => [p.id, p]));
		const next = frame.order.map(id => by.get(id)).filter(Boolean)
			.map((p, i) => ({ ...p, order: i, etag: frame.etags[p.id] || p.etag }));
		return { pages: next, refetch: next.length !== frame.order.length };
	}
	return { pages, refetch: false };
}

module.exports = { KEY_PAGE, KEY_STRIP, reconcile, saveRequest, afterSave, keepMine, applyFrame };
