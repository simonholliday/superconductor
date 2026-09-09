"""Fetch the page an installed Superconductor serves, and everything it asks for.

Both existing packaging checks read the *source tree* — the globs in
`test_service.py` and the served client in `test_build.py` — and a source tree
has the file whether or not a wheel does.  That is how the bundled face reached
a 404: `client/*` does not reach into `client/fonts/`, and every test passed.
This asks the only question that catches it, of the artefact rather than of the
repository.
"""

import re
import sys
import urllib.request

BASE = "http://127.0.0.1:8099"


def fetch (path: str) -> tuple[int, bytes]:
	"""One asset, by the path the page itself named."""

	with urllib.request.urlopen(BASE + path, timeout=10) as answer:
		return answer.status, answer.read()


status, page = fetch("/")
assert status == 200, f"the page itself answered {status}"

text = page.decode("utf-8")
wanted = sorted({ref for ref in re.findall(r'(?:src|href)="([^"]+)"', text)
                 if ref.startswith("/")})
assert wanted, "the page references no assets at all, which cannot be right"

# A stylesheet's own `url()` references are where the bundled face lives, and
# they are the ones nothing else looks at.
for ref in list(wanted):
	if not ref.split("?")[0].endswith(".css"):
		continue

	_, body = fetch(ref)
	root = ref.rsplit("/", 1)[0]

	for inner in re.findall(r'url\(["\']?([^"\')]+)', body.decode("utf-8")):
		if inner.startswith("data:"):
			continue
		wanted.append(inner if inner.startswith("/") else f"{root}/{inner}")

missing = []

for ref in sorted(set(wanted)):
	try:
		status, body = fetch(ref)
	except urllib.error.HTTPError as complaint:
		missing.append(f"{ref} -> {complaint.code}")
		continue

	if status != 200 or not body:
		missing.append(f"{ref} -> {status}, {len(body)} bytes")
		continue

	print(f"  {ref}  {status}  {len(body):,}b")

assert not missing, "the installed wheel does not serve: " + "; ".join(missing)
print(f"the wheel serves its page and all {len(set(wanted))} assets it asks for")
