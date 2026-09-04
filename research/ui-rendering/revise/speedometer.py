"""Measurement prototype: runs Speedometer 2.0 in headless Chromium to anchor the CPU-throttle factor against the published Raspberry Pi 5 figure."""
import asyncio, json, sys
import playwright.async_api as pa

CHROME = "/home/si/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"

async def main(rate):
	async with pa.async_playwright() as p:
		b = await p.chromium.launch(executable_path=CHROME, headless=True, args=["--enable-gpu", "--use-angle=gl-egl", "--ignore-gpu-blocklist"])
		ctx = await b.new_context(viewport={"width": 1920, "height": 1080})
		page = await ctx.new_page()
		if rate > 1:
			cdp = await ctx.new_cdp_session(page)
			await cdp.send("Emulation.setCPUThrottlingRate", {"rate": rate})
		await page.goto("https://browserbench.org/Speedometer2.0/", wait_until="load")
		await page.click("text=Start Test")
		await page.wait_for_function("() => { const s=document.getElementById('summarized-results'); const e=document.getElementById('result-number'); return s && s.classList.contains('selected') && e && e.textContent.trim().length>0; }", timeout=3600000)
		score = await page.evaluate("document.getElementById('result-number').textContent")
		err = await page.evaluate("(document.getElementById('confidence-number')||{}).textContent")
		print(json.dumps({"rate": rate, "speedometer20_runs_per_minute": score, "confidence": err, "browser": b.version}), flush=True)
		await b.close()

asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 1))
