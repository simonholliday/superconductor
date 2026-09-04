"""Research prototype (transport-ui): smallest non-zero step of performance.now() in headless Chromium and Firefox,
so the loopback tables' minimums can be read correctly. No server needed. Not house style."""
import asyncio, os
import playwright.async_api
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(HERE, "pw-browsers")
JS = """
() => {
	const steps = new Set(); let last = performance.now(); const t0 = last;
	while (performance.now() - t0 < 200) { const n = performance.now(); if (n !== last) { steps.add(Math.round((n - last) * 1e6) / 1e6); last = n; } }
	const xs = [...steps].sort((a, b) => a - b);
	return {smallest_step_ms: xs[0], distinct_steps: xs.length, sample: xs.slice(0, 5)};
}
"""
async def main():
	async with playwright.async_api.async_playwright() as p:
		for name in ("chromium", "firefox"):
			b = await getattr(p, name).launch()
			page = await b.new_page()
			await page.goto("about:blank")
			ua = await page.evaluate("navigator.userAgent")
			print(name, ua)
			for _ in range(3):
				print("  ", await page.evaluate(JS))
			await b.close()
asyncio.run(main())
