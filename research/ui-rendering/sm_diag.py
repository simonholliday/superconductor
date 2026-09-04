import asyncio, playwright.async_api as pa
CHROME = "/home/si/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
async def main():
    async with pa.async_playwright() as p:
        b = await p.chromium.launch(executable_path=CHROME, headless=True, args=["--enable-gpu","--use-angle=gl-egl","--ignore-gpu-blocklist"])
        pg = await b.new_page()
        r = await pg.goto("https://browserbench.org/Speedometer2.0/?startAutomatically=true", wait_until="load", timeout=60000)
        print("status", r.status if r else None, pg.url)
        await pg.wait_for_timeout(20000)
        info = await pg.evaluate("""() => ({
          hasResult: !!document.getElementById('result-number'),
          resultText: (document.getElementById('result-number')||{}).textContent,
          bodyClass: document.body.className,
          sections: [...document.querySelectorAll('section')].map(s => s.id + ':' + (s.classList.contains('selected')?'sel':'')).join(' '),
          text: document.body.innerText.slice(0,400)
        })""")
        print(info)
        await b.close()
asyncio.run(main())
