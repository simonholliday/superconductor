"""Research prototype (not house style, tabs but no docstring discipline): the page routes
proposed for the Superintendent Starlette app, with strong ETags, If-Match compare-and-swap,
atomic replace, an id whitelist, a whole-set conditional reorder, and the page_changed frame
recorded through an injected broadcast hook. Exercised by pages_test.py through Starlette's
TestClient, so no port is bound."""
import asyncio, hashlib, json, os, re, tempfile

import starlette.applications
import starlette.requests
import starlette.responses
import starlette.routing
import starlette.staticfiles

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
MAX_PAGE_BYTES = 256 * 1024

class Pages:
	def __init__(self, root: str, broadcast=None) -> None:
		self.root = root
		os.makedirs(root, exist_ok=True)
		self.locks: dict[str, asyncio.Lock] = {}
		self.broadcast = broadcast or (lambda frame: None)

	def path(self, page_id: str) -> str:
		return os.path.join(self.root, page_id + ".json")

	def lock(self, page_id: str) -> asyncio.Lock:
		return self.locks.setdefault(page_id, asyncio.Lock())

	@staticmethod
	def etag(raw: bytes) -> str:
		return '"' + hashlib.sha256(raw).hexdigest()[:32] + '"'

	def read(self, page_id: str) -> tuple[bytes, str] | None:
		try:
			with open(self.path(page_id), "rb") as fh:
				raw = fh.read()
		except FileNotFoundError:
			return None
		return raw, self.etag(raw)

	def write(self, page_id: str, raw: bytes) -> str:
		fd, tmp = tempfile.mkstemp(dir=self.root, prefix="." + page_id, suffix=".tmp")
		try:
			with os.fdopen(fd, "wb") as fh:
				fh.write(raw)
				fh.flush()
				os.fsync(fh.fileno())
			os.replace(tmp, self.path(page_id))
		except BaseException:
			os.unlink(tmp)
			raise
		dirfd = os.open(self.root, os.O_RDONLY)
		try:
			os.fsync(dirfd)
		finally:
			os.close(dirfd)
		return self.etag(raw)

	def listing(self) -> list[dict]:
		"""Every .json file in the directory appears, including one whose name or content the
		service cannot use: a page never vanishes silently from the panel's page bar."""
		out = []
		for name in sorted(os.listdir(self.root)):
			if not name.endswith(".json"):
				continue
			stem = name[:-5]
			try:
				with open(os.path.join(self.root, name), "rb") as fh:
					raw = fh.read()
			except OSError:
				continue
			tag = self.etag(raw)
			if not ID_RE.match(stem):
				# A hand-made or hand-renamed file the id rule refuses. It is listed as
				# unloadable with the name it has, so the panel can say why rather than
				# leaving the person to wonder where their page went.
				out.append({"id": None, "file": name, "label": stem, "order": None,
					"etag": tag, "bytes": len(raw), "error": "bad_id"})
				continue
			try:
				doc = json.loads(raw)
			except ValueError:
				out.append({"id": stem, "label": stem, "order": None,
					"etag": tag, "bytes": len(raw), "error": "not_json"})
				continue
			order = doc.get("order")
			out.append({
				"id": stem,
				"label": doc.get("label", stem),
				"order": order if isinstance(order, int) else None,
				"etag": tag,
				"bytes": len(raw),
			})
		# Declared order first, in order; then everything with no usable order, by name.
		# The rule is stated rather than implied so a page predating `order` has a defined place.
		out.sort(key=lambda p: (p["order"] is None, p["order"] if p["order"] is not None else 0,
			p["id"] or p.get("file")))
		return out

def bad(reason: str, code: int, **extra):
	body = {"error": reason}
	body.update(extra)
	return starlette.responses.JSONResponse(body, status_code=code)

def _client(request) -> str | None:
	return request.headers.get("x-superintendent-client")

async def pages_list(request):
	return starlette.responses.JSONResponse({"pages": request.app.state.pages.listing()})

async def page_read(request):
	page_id = request.path_params["page_id"]
	if not ID_RE.match(page_id):
		return bad("bad_page_id", 400)
	got = request.app.state.pages.read(page_id)
	if got is None:
		return bad("no_such_page", 404)
	raw, tag = got
	if request.headers.get("if-none-match") == tag:
		return starlette.responses.Response(status_code=304, headers={"ETag": tag})
	return starlette.responses.Response(raw, media_type="application/json", headers={"ETag": tag})

async def _body_doc(request, page_id):
	raw = await request.body()
	try:
		doc = json.loads(raw)
	except ValueError:
		return None, bad("not_json", 400)
	if not isinstance(doc, dict) or doc.get("id") != page_id:
		return None, bad("id_mismatch", 400)
	return raw, None

async def page_save(request):
	page_id = request.path_params["page_id"]
	if not ID_RE.match(page_id):
		return bad("bad_page_id", 400)
	raw, err = await _body_doc(request, page_id)
	if err is not None:
		return err
	if_match = request.headers.get("if-match")
	if if_match is None:
		return bad("precondition_required", 428)
	pages = request.app.state.pages
	async with pages.lock(page_id):
		got = pages.read(page_id)
		current = got[1] if got else None
		if current is None:
			return bad("no_such_page", 404)
		if if_match != "*" and current != if_match:
			return bad("stale", 412, etag=current)
		tag = pages.write(page_id, raw)
	pages.broadcast({"t": "page_changed", "id": page_id, "op": "saved", "etag": tag,
		"by": "panel", "client": _client(request)})
	return starlette.responses.JSONResponse({"id": page_id, "etag": tag}, status_code=200,
		headers={"ETag": tag})

async def page_create(request):
	page_id = request.path_params["page_id"]
	if not ID_RE.match(page_id):
		return bad("bad_page_id", 400)
	raw, err = await _body_doc(request, page_id)
	if err is not None:
		return err
	pages = request.app.state.pages
	async with pages.lock(page_id):
		if pages.read(page_id) is not None:
			return bad("exists", 412)
		tag = pages.write(page_id, raw)
	pages.broadcast({"t": "page_changed", "id": page_id, "op": "created", "etag": tag,
		"by": "panel", "client": _client(request)})
	return starlette.responses.JSONResponse({"id": page_id, "etag": tag}, status_code=201,
		headers={"ETag": tag})

async def page_delete(request):
	page_id = request.path_params["page_id"]
	if not ID_RE.match(page_id):
		return bad("bad_page_id", 400)
	pages = request.app.state.pages
	async with pages.lock(page_id):
		got = pages.read(page_id)
		if got is None:
			return bad("no_such_page", 404)
		if_match = request.headers.get("if-match")
		if if_match is None:
			return bad("precondition_required", 428)
		if if_match != "*" and if_match != got[1]:
			return bad("stale", 412, etag=got[1])
		os.unlink(pages.path(page_id))
	pages.broadcast({"t": "page_changed", "id": page_id, "op": "deleted", "etag": None,
		"by": "panel", "client": _client(request)})
	return starlette.responses.Response(status_code=204)

async def pages_reorder(request):
	"""The whole page strip's order in one conditional request, because `order` lives inside
	each page document and moving one page rewrites several. Every named page's ETag must
	still be current; otherwise nothing is written and the stale ones are named."""
	try:
		body = json.loads(await request.body())
	except ValueError:
		return bad("not_json", 400)
	entries = body.get("order") if isinstance(body, dict) else None
	if not isinstance(entries, list) or not entries:
		return bad("bad_order", 400)
	ids = []
	for e in entries:
		if not isinstance(e, dict) or not isinstance(e.get("id"), str) or not ID_RE.match(e["id"]):
			return bad("bad_page_id", 400)
		if not isinstance(e.get("etag"), str):
			return bad("precondition_required", 428)
		ids.append(e["id"])
	if len(set(ids)) != len(ids):
		return bad("duplicate_page_id", 400)
	pages = request.app.state.pages
	# Locks are taken in sorted id order so two reorders in flight cannot deadlock.
	locks = [pages.lock(i) for i in sorted(ids)]
	async with _all(locks):
		staged = []
		stale = []
		for position, e in enumerate(entries):
			got = pages.read(e["id"])
			if got is None:
				stale.append({"id": e["id"], "etag": None})
				continue
			raw, tag = got
			if tag != e["etag"]:
				stale.append({"id": e["id"], "etag": tag})
				continue
			doc = json.loads(raw)
			doc["order"] = position
			staged.append((e["id"], json.dumps(doc, separators=(",", ":")).encode()))
		if stale:
			return bad("stale", 412, stale=stale)
		written = [(page_id, pages.write(page_id, raw)) for page_id, raw in staged]
	pages.broadcast({"t": "pages_reordered", "order": [p for p, _ in written],
		"etags": {p: t for p, t in written}, "by": "panel", "client": _client(request)})
	return starlette.responses.JSONResponse({"order": [p for p, _ in written],
		"etags": {p: t for p, t in written}})

class _all:
	"""Hold several asyncio locks for the body of one request."""
	def __init__(self, locks):
		self.locks = locks

	async def __aenter__(self):
		for lock in self.locks:
			await lock.acquire()

	async def __aexit__(self, *exc):
		for lock in reversed(self.locks):
			lock.release()
		return False

async def route_dispatch_put(request):
	"""One PUT endpoint: If-None-Match: * creates, If-Match: <etag> replaces."""
	if request.headers.get("if-none-match") == "*":
		return await page_create(request)
	return await page_save(request)

def build(root: str, static_dir: str | None = None, broadcast=None):
	routes = [
		starlette.routing.Route("/api/pages", pages_list, methods=["GET"]),
		starlette.routing.Route("/api/pages/order", pages_reorder, methods=["POST"],
			max_body_size=MAX_PAGE_BYTES),
		starlette.routing.Route("/api/pages/{page_id}", page_read, methods=["GET"]),
		starlette.routing.Route("/api/pages/{page_id}", route_dispatch_put, methods=["PUT"],
			max_body_size=MAX_PAGE_BYTES),
		starlette.routing.Route("/api/pages/{page_id}", page_delete, methods=["DELETE"]),
	]
	if static_dir:
		routes.append(starlette.routing.Mount("/", app=starlette.staticfiles.StaticFiles(directory=static_dir, html=True)))
	app = starlette.applications.Starlette(routes=routes)
	app.state.pages = Pages(root, broadcast)
	return app
