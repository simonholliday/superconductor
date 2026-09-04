"""Prototype: dump PDF text to files for grepping (research helper, not house style)."""
import sys, pypdf
for src, dst in zip(sys.argv[1::2], sys.argv[2::2]):
	r = pypdf.PdfReader(src)
	with open(dst, "w") as fh:
		for i, p in enumerate(r.pages):
			fh.write(f"\n=== PAGE {i+1} ===\n")
			fh.write(p.extract_text() or "")
	print(dst, len(r.pages), "pages")
