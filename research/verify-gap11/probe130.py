"""PROTOTYPE (research only). Is the 180 BPM clock jitter the epoll millisecond rounding?"""
import asyncio, logging, selectors, statistics, sys
logging.basicConfig(level=logging.ERROR)
sys.path.insert(0, "/mnt/dev/Apps/2026-02 Sequencer")
import subsequence.sequencer

async def run(bpm, bars, jitter):
	seq = subsequence.sequencer.Sequencer(output_device_name="NO-SUCH-DEVICE-XYZ", initial_bpm=bpm, spin_wait=True, _jitter_log=jitter)
	await seq.start()
	try:
		await asyncio.wait_for(asyncio.shield(seq.task), timeout=(60.0/bpm)*4*bars + 2.0)
	except asyncio.TimeoutError:
		pass
	seq.running = False
	try:
		await asyncio.wait_for(seq.task, timeout=2.0)
	except Exception:
		seq.task.cancel()

def go(bpm, bars, sel):
	jitter = []
	loop = asyncio.SelectorEventLoop(sel()) if sel else asyncio.new_event_loop()
	asyncio.set_event_loop(loop)
	loop.run_until_complete(run(bpm, bars, jitter))
	loop.close()
	ms = sorted(x*1000 for x in jitter[:bars*4*24])
	return statistics.median(ms), ms[int(len(ms)*0.95)], ms[-1], sum(1 for x in ms if x > 1.0), len(ms)

for name, sel in (("default (epoll)", None),):
	for bpm in (130, 140):
		m, p95, mx, over, n = go(bpm, 8, sel)
		print(f"{name:16s} {bpm:3d} BPM  median {m:7.4f} ms  p95 {p95:7.4f} ms  max {mx:7.4f} ms  over 1 ms {over}/{n}")
