"""Prototype probe: which implementation does websockets.serve resolve to, and what does process_request receive."""
import asyncio, inspect, warnings, websockets
print("websockets", websockets.__version__)
warnings.simplefilter("always")
with warnings.catch_warnings(record=True) as w:
	serve = websockets.serve
	print("serve ->", serve.__module__, getattr(serve, "__qualname__", serve))
	for x in w: print("WARN:", x.category.__name__, str(x.message)[:120])
received = {}
def pr(*args):
	received["args"] = [type(a).__name__ for a in args]
	received["has_path"] = hasattr(args[-1], "path") if args else None
	return None
async def main():
	async with websockets.serve(lambda ws: ws.wait_closed(), "127.0.0.1", 19899, process_request=pr) as srv:
		try:
			async with websockets.connect("ws://127.0.0.1:19899/audio/x.wav") as c:
				pass
		except Exception as e:
			print("client err:", type(e).__name__, str(e)[:100])
	print("process_request got:", received)
asyncio.run(main())
