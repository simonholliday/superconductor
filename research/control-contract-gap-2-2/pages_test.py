"""Research prototype tests for pages_routes.py. Run: ./venv/bin/python pages_test.py"""
import json, os, shutil, tempfile

import starlette.testclient

import pages_routes

PASS = FAIL = 0

def check(name, cond, extra=""):
	global PASS, FAIL
	if cond:
		print("ok   " + name)
		PASS += 1
	else:
		print("FAIL " + name + " " + str(extra))
		FAIL += 1

def page(page_id, label, order=0, widgets=None):
	return {"page_contract": "1.1.0", "id": page_id, "label": label, "order": order,
		"lattice": {"cols": 32, "rows": 18, "cell": 60},
		"widgets": widgets if widgets is not None else []}

FRAMES = []

root = tempfile.mkdtemp(prefix="pages-")
app = pages_routes.build(root, broadcast=FRAMES.append)
c = starlette.testclient.TestClient(app)
HDR = {"X-Superintendent-Client": "panel-7f3a"}

# create
r = c.put("/api/pages/drums", json=page("drums", "Drums"), headers={"If-None-Match": "*", **HDR})
check("create returns 201 with an ETag", r.status_code == 201 and r.headers.get("etag"), r.status_code)
etag1 = r.headers["etag"]
check("create broadcasts page_changed op=created carrying the client",
	FRAMES[-1] == {"t": "page_changed", "id": "drums", "op": "created", "etag": etag1,
		"by": "panel", "client": "panel-7f3a"}, FRAMES[-1])

# create twice
r = c.put("/api/pages/drums", json=page("drums", "Drums"), headers={"If-None-Match": "*"})
check("a second create of the same id is 412", r.status_code == 412, r.status_code)

# read
r = c.get("/api/pages/drums")
check("read returns the document and the same ETag", r.status_code == 200 and r.headers["etag"] == etag1
	and r.json()["label"] == "Drums", r.status_code)

# conditional read
r = c.get("/api/pages/drums", headers={"If-None-Match": etag1})
check("a matching If-None-Match read is 304", r.status_code == 304, r.status_code)

# list
c.put("/api/pages/pads", json=page("pads", "Pads", order=1), headers={"If-None-Match": "*"})
r = c.get("/api/pages")
ids = [p["id"] for p in r.json()["pages"]]
check("list returns both pages in order order", ids == ["drums", "pads"], ids)

# save without a precondition
r = c.put("/api/pages/drums", json=page("drums", "Drums 2"))
check("a save with no If-Match is refused 428", r.status_code == 428, r.status_code)

# a save aimed at a page that does not exist is 404, not a silent create
r = c.put("/api/pages/ghost", json=page("ghost", "Ghost"), headers={"If-Match": etag1})
check("an If-Match save of a page that does not exist is 404", r.status_code == 404, r.status_code)

# save with the right ETag
n_before = len(FRAMES)
r = c.put("/api/pages/drums", json=page("drums", "Drums 2"), headers={"If-Match": etag1, **HDR})
check("a save with the current ETag succeeds 200", r.status_code == 200, r.status_code)
etag2 = r.headers["etag"]
check("the ETag changed with the content", etag2 != etag1, (etag1, etag2))
check("a successful save broadcasts page_changed op=saved with the new ETag",
	len(FRAMES) == n_before + 1 and FRAMES[-1]["op"] == "saved" and FRAMES[-1]["etag"] == etag2,
	FRAMES[-1])

# the two-panel race: panel B still holds etag1
n_before = len(FRAMES)
r = c.put("/api/pages/drums", json=page("drums", "Drums from panel B"), headers={"If-Match": etag1})
check("the second panel's stale save is refused 412", r.status_code == 412, r.status_code)
check("the 412 body carries the current ETag so the panel can reload",
	r.json().get("etag") == etag2, r.text)
check("the loser's content did not land", c.get("/api/pages/drums").json()["label"] == "Drums 2")
check("a refused save broadcasts nothing", len(FRAMES) == n_before, FRAMES[n_before:])

# idempotent re-save of identical bytes keeps the ETag
r = c.put("/api/pages/drums", json=page("drums", "Drums 2"), headers={"If-Match": etag2})
check("re-saving identical bytes yields the same ETag", r.headers["etag"] == etag2, r.headers.get("etag"))

# id discipline
for bad_id, want in [("..", 404), ("../etc/passwd", 404), ("Drums", 400), ("a" * 65, 400),
		(".hidden", 400), ("drums.json", 400)]:
	r = c.get("/api/pages/" + bad_id)
	check("the page id %r is answered %d" % (bad_id, want), r.status_code == want, r.status_code)

r = c.put("/api/pages/drums", json=page("pads", "wrong id inside"), headers={"If-Match": etag2})
check("a body whose id differs from the path is refused 400", r.status_code == 400, r.status_code)

r = c.put("/api/pages/drums", content=b"{not json", headers={"If-Match": etag2, "content-type": "application/json"})
check("a non-JSON body is refused 400", r.status_code == 400, r.status_code)

# oversize body
big = page("big", "Big", widgets=[{"bind": {"app": "x", "path": "/x"}, "pad": "y" * 1000} for _ in range(400)])
r = c.put("/api/pages/big", json=big, headers={"If-None-Match": "*"})
check("a body over the limit is refused 413", r.status_code == 413, r.status_code)

# the whole-strip reorder
c.put("/api/pages/keys", json=page("keys", "Keys", order=2), headers={"If-None-Match": "*"})
tags = {p["id"]: p["etag"] for p in c.get("/api/pages").json()["pages"]}
n_before = len(FRAMES)
r = c.post("/api/pages/order", json={"order": [
	{"id": "keys", "etag": tags["keys"]},
	{"id": "drums", "etag": tags["drums"]},
	{"id": "pads", "etag": tags["pads"]}]}, headers=HDR)
check("a reorder with every current ETag succeeds", r.status_code == 200, r.text)
check("the strip is in the requested order",
	[p["id"] for p in c.get("/api/pages").json()["pages"]] == ["keys", "drums", "pads"],
	[p["id"] for p in c.get("/api/pages").json()["pages"]])
check("a reorder broadcasts one pages_reordered frame naming the whole strip",
	len(FRAMES) == n_before + 1 and FRAMES[-1]["t"] == "pages_reordered"
	and FRAMES[-1]["order"] == ["keys", "drums", "pads"], FRAMES[-1:])

# a reorder built on one stale ETag writes nothing at all
before = [p["id"] for p in c.get("/api/pages").json()["pages"]]
n_before = len(FRAMES)
r = c.post("/api/pages/order", json={"order": [
	{"id": "drums", "etag": tags["drums"]},          # stale: the reorder above rewrote it
	{"id": "keys", "etag": tags["keys"]},
	{"id": "pads", "etag": tags["pads"]}]})
check("a reorder with a stale ETag is refused 412 naming the stale pages",
	r.status_code == 412 and {s["id"] for s in r.json()["stale"]} == {"drums", "keys", "pads"}, r.text)
check("a refused reorder moved nothing",
	[p["id"] for p in c.get("/api/pages").json()["pages"]] == before, before)
check("a refused reorder broadcasts nothing", len(FRAMES) == n_before)

r = c.post("/api/pages/order", json={"order": [{"id": "drums"}]})
check("a reorder with no ETag at all is refused 428", r.status_code == 428, r.status_code)

# the reorder route and a page whose id is literally "order" do not collide
c.put("/api/pages/order", json=page("order", "Order"), headers={"If-None-Match": "*"})
check("a page whose id is 'order' is still readable past the reorder route",
	c.get("/api/pages/order").json()["label"] == "Order", c.get("/api/pages/order").text)
tags = {p["id"]: p["etag"] for p in c.get("/api/pages").json()["pages"] if p.get("id")}
r = c.delete("/api/pages/order", headers={"If-Match": tags["order"]})
check("and it is deletable, because no page route accepts POST and the reorder route accepts nothing else",
	r.status_code == 204, r.status_code)

# delete
r = c.delete("/api/pages/pads")
check("a delete with no If-Match is refused 428", r.status_code == 428, r.status_code)
r = c.get("/api/pages/pads")
n_before = len(FRAMES)
r = c.delete("/api/pages/pads", headers={"If-Match": r.headers["etag"], **HDR})
check("a delete with the current ETag is 204", r.status_code == 204, r.status_code)
check("the deleted page is gone", c.get("/api/pages/pads").status_code == 404)
check("a delete broadcasts page_changed op=deleted with a null ETag, so a second panel's page bar is not stale",
	len(FRAMES) == n_before + 1 and FRAMES[-1]["op"] == "deleted" and FRAMES[-1]["etag"] is None,
	FRAMES[-1])

# a corrupt page file is listed, not hidden
open(os.path.join(root, "broken.json"), "w").write("{not json")
listing = c.get("/api/pages").json()["pages"]
check("a corrupt page file is listed with an error", any(p.get("error") == "not_json" and p["id"] == "broken" for p in listing), listing)

# a hand-made file whose name the id rule refuses is listed too, not silently dropped
open(os.path.join(root, "My Page.json"), "w").write(json.dumps(page("x", "x")))
listing = c.get("/api/pages").json()["pages"]
check("a file whose name breaks the id rule is listed with error bad_id rather than vanishing",
	any(p.get("error") == "bad_id" and p.get("file") == "My Page.json" for p in listing), listing)
check("pages with no usable order sort after those that declare one",
	[p.get("id") or p.get("file") for p in listing] == ["keys", "drums", "My Page.json", "broken"],
	[p.get("id") or p.get("file") for p in listing])

# no partial file is ever left behind
leftovers = [n for n in os.listdir(root) if not n.endswith(".json")]
check("no temporary file is left in the page directory", leftovers == [], leftovers)

shutil.rmtree(root)
print("\n%d passed, %d failed" % (PASS, FAIL))
raise SystemExit(1 if FAIL else 0)
