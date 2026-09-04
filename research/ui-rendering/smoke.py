import asyncio, playwright.async_api as pa
async def main():
    async with pa.async_playwright() as p:
        b = await p.chromium.launch(executable_path="/home/si/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome", headless=True,
            args=["--enable-gpu","--use-angle=gl-egl","--ignore-gpu-blocklist","--enable-unsafe-swiftshader"])
        pg = await b.new_page()
        print("version", b.version)
        await pg.goto("about:blank")
        r = await pg.evaluate("""() => { const c=document.createElement('canvas'); const gl=c.getContext('webgl2')||c.getContext('webgl'); if(!gl) return 'no webgl'; const d=gl.getExtension('WEBGL_debug_renderer_info'); return d? gl.getParameter(d.UNMASKED_RENDERER_WEBGL)+' | '+gl.getParameter(d.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.RENDERER); }""")
        print("webgl renderer:", r)
        await b.close()
asyncio.run(main())
