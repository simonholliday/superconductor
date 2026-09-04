"""Verifier prototype (transport-ui): does a fetch POST to a SIGSTOPped server fail fast? Not house style."""
import asyncio, os, signal, subprocess, sys, time
import playwright.async_api
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(HERE, "pw-browsers")
BASE = "http://127.0.0.1:8902"
JS = """
async ({url, wait}) => {
	const t0 = performance.now();
	const ctl = new AbortController();
	const timer = setTimeout(() => ctl.abort(), wait);
	try {
		const r = await fetch(url, {method:'POST', body:'{}', signal: ctl.signal});
		await r.text();
		return {outcome: 'responded', ms: performance.now() - t0};
	} catch (e) {
		return {outcome: 'error:' + e.name, ms: performance.now() - t0};
	} finally { clearTimeout(timer); }
}
"""
async def main():
	srv = subprocess.Popen([sys.executable, os.path.join(HERE, "server.py")])
	await asyncio.sleep(1.0)
	try:
		async with playwright.async_api.async_playwright() as p:
			b = await p.chromium.launch()
			page = await b.new_page()
			await page.goto(BASE + "/")
			print("warm:", await page.evaluate(JS, {"url": BASE + "/cmd", "wait": 5000}))
			srv.send_signal(signal.SIGSTOP)
			await asyncio.sleep(0.2)
			print("after SIGSTOP (30 s cap):", await page.evaluate(JS, {"url": BASE + "/cmd", "wait": 30000}))
			srv.send_signal(signal.SIGCONT)
			await b.close()
	finally:
		if srv.poll() is None:
			srv.send_signal(signal.SIGCONT); srv.kill()
asyncio.run(main())
