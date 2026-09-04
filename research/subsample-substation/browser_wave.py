"""Prototype (not house style): in headless Chromium, time (a) fetch + decodeAudioData of a
16 kHz mono WAV plus a 400-bin min/max envelope in JS and a canvas draw, and (b) decoding a
Subsample preview block (base64 int8 envelopes) and drawing it.  Serves files from ./wav and
./preview on 127.0.0.1:8911 (outside the reserved ports)."""
import http.server, threading, json, pathlib, sys, functools, statistics
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).parent
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8911), handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()

PAGE = """<!doctype html><canvas id=c width=1024 height=256></canvas><script>
async function wavEnvelope(url){
  const t0=performance.now();
  const buf=await (await fetch(url)).arrayBuffer();
  const t1=performance.now();
  const ctx=new OfflineAudioContext(1,16000,16000);
  const ab=await ctx.decodeAudioData(buf.slice(0));
  const t2=performance.now();
  const d=ab.getChannelData(0), bins=400, mn=new Float32Array(bins), mx=new Float32Array(bins);
  const per=d.length/bins;
  for(let b=0;b<bins;b++){let lo=1,hi=-1;const s=Math.floor(b*per),e=Math.floor((b+1)*per);for(let i=s;i<e;i++){const v=d[i];if(v<lo)lo=v;if(v>hi)hi=v;}mn[b]=lo;mx[b]=hi;}
  const t3=performance.now();
  draw(mn,mx);
  const t4=performance.now();
  return {bytes:buf.byteLength, seconds:ab.duration, fetch_ms:t1-t0, decode_ms:t2-t1, envelope_ms:t3-t2, draw_ms:t4-t3};
}
function draw(mn,mx){const c=document.getElementById('c').getContext('2d');c.clearRect(0,0,1024,256);c.fillStyle='#ccc';const w=1024/mn.length;for(let i=0;i<mn.length;i++){const y1=128-mx[i]*127,y2=128-mn[i]*127;c.fillRect(i*w,y1,w,Math.max(1,y2-y1));}}
async function previewBlock(url){
  const t0=performance.now();
  const p=await (await fetch(url)).json();
  const t1=performance.now();
  const dec=s=>{const bin=atob(s);const a=new Int8Array(bin.length);for(let i=0;i<bin.length;i++){a[i]=bin.charCodeAt(i);}return a;};
  const mn=dec(p.envelope_min), mx=dec(p.envelope_max);
  const fmn=Float32Array.from(mn,v=>v/127), fmx=Float32Array.from(mx,v=>v/127);
  const t2=performance.now();
  draw(fmn,fmx);
  const t3=performance.now();
  return {json_bytes:JSON.stringify(p).length, fetch_ms:t1-t0, decode_ms:t2-t1, draw_ms:t3-t2};
}
</script>"""
(ROOT/"page.html").write_text(PAGE)
with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page()
    pg.goto("http://127.0.0.1:8911/page.html")
    print("chromium", b.version)
    for name in sys.argv[1:]:
        runs = [pg.evaluate("u=>wavEnvelope(u)", f"/wav/{name}") for _ in range(10)]
        def med(k): return statistics.median(r[k] for r in runs)
        print(f"WAV {name}: {runs[0]['bytes']} bytes, {runs[0]['seconds']:.2f} s audio; median over 10: fetch {med('fetch_ms'):.2f} ms, decodeAudioData {med('decode_ms'):.2f} ms, envelope {med('envelope_ms'):.2f} ms, draw {med('draw_ms'):.2f} ms")
    runs = [pg.evaluate("u=>previewBlock(u)", "/preview/block.json") for _ in range(10)]
    def med(k): return statistics.median(r[k] for r in runs)
    print(f"preview block: {runs[0]['json_bytes']} bytes; median over 10: fetch {med('fetch_ms'):.2f} ms, base64 decode {med('decode_ms'):.2f} ms, draw {med('draw_ms'):.2f} ms")
    b.close()
srv.shutdown()
