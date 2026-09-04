"""Verifier prototype: compare className-rewrite-to-same-value against a real every-cell change."""
import json, pathlib, sys
import playwright.sync_api
HERE = pathlib.Path(__file__).parent
PAGE = (HERE / "invert.html").resolve().as_uri()
CHROME = "/home/si/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
with playwright.sync_api.sync_playwright() as p:
	b = p.chromium.launch(executable_path=CHROME, headless=True, args=["--window-size=1920,1080"])
	page = b.new_page(viewport={"width": 1920, "height": 1080})
	page.goto(PAGE)
	cdp = page.context.new_cdp_session(page)
	for rate in (1, 6):
		cdp.send("Emulation.setCPUThrottlingRate", {"rate": rate})
		for mode in ("same", "invert", "snapshot"):
			r = page.evaluate("([m]) => window.run(m)", [mode])
			print(rate, json.dumps(r))
	b.close()
