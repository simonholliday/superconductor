"""A screenshot of the running panel under one theme, at the rig's own size.

**#2194's method ends with "then look at it on the glass"**, and every palette
decision Simon has taken was taken from a picture rather than from a table: the
two-column picker was found in a screenshot while every test passed against it.
So this is the last step of adding a theme, and it existed as a throwaway script
twice before being kept.

Needs a service running with an app dialled in, because a picture of an empty
panel says nothing about a palette.  Writes to `/home/si/superintendent-shots/`,
which is disk rather than tmpfs and survives a reboot.

    python tools/theme_shot.py prism
    python tools/theme_shot.py prism --picker

The second opens the theme menu first, which is the only way to see a swatch —
and a swatch is what somebody picks a theme *by*.
"""

import pathlib
import sys

import playwright.sync_api
import typing


WHERE = pathlib.Path("/home/si/superintendent-shots/themes")

SIZE: typing.Any = {"width": 1920, "height": 1080}
"""The development panel's own size.  A palette read at another size is a
different picture, and #2049's own warning is that a fault which does not
reproduce at 1920x1080 is still a fault."""

SERVICE = "http://127.0.0.1:8090/"


def main () -> int:
	"""Take one picture, and say where it went."""

	wanted = [one for one in sys.argv[1:] if not one.startswith("--")]
	picker = "--picker" in sys.argv

	if not wanted:
		print("usage: theme_shot.py <theme key> [--picker]")
		return 2

	key = wanted[0]

	with playwright.sync_api.sync_playwright() as run:
		browser = run.firefox.launch()
		page = browser.new_page(viewport=SIZE)

		page.goto(SERVICE, wait_until="load")

		# The key is the `localStorage` value as well as the selector, so this is
		# the same act as choosing it on the glass (#2194).
		page.evaluate(f"() => localStorage.setItem('superintendent.theme', {key!r})")
		page.reload(wait_until="load")

		page.wait_for_selector(".cell", timeout=15_000)

		if picker:
			page.locator(".bar button", has_text="THEME").click()

		# The fit runs in an effect and again on a resize, so a picture taken the
		# instant the page is drawn is a picture of an intermediate layout.
		page.wait_for_timeout(1200)

		WHERE.mkdir(parents=True, exist_ok=True)
		out = WHERE / f"{key}{'-picker' if picker else ''}.png"
		page.screenshot(path=str(out))

		browser.close()

	print(f"written to {out}")

	return 0


if __name__ == "__main__":
	raise SystemExit(main())
