/* 3D 동작 검사 1단계 — 헤드리스 크롬으로 앱을 열어 동작마다(남·여) 한 바퀴를 잘게 나눠
 * 관절 자리·기구 자리를 JSON 으로, 화면 몇 장을 JPEG 로 뽑는다. 검사는 qa_check.py 가 한다.
 *
 *   node docs/3d/qa_sample.js <출력폴더> [앱주소=http://127.0.0.1:8390/] [동작id,동작id,...]
 *
 * 크롬은 C:\Program Files\Google\Chrome (Windows) 기준. Node 22 이상(내장 WebSocket·fetch).
 * 앱의 MOVE_3D.qa(canvas) 손잡이(move-3d.js 끝)를 쓴다. */
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const OUT = process.argv[2]; const URL_ = process.argv[3] || 'http://127.0.0.1:8390/'; const ONLY = process.argv[4] ? process.argv[4].split(',') : null;
const PORT = 9334, FRAMES = 24, IMAGES = 8;
if (!OUT) { console.error('출력 폴더를 주세요'); process.exit(1); }
fs.mkdirSync(OUT, { recursive: true });
const CHROME = process.platform === 'win32' ? 'C:/Program Files/Google/Chrome/Application/chrome.exe' : 'google-chrome';
const chrome = spawn(CHROME, ['--headless=new', '--remote-debugging-port=' + PORT, '--user-data-dir=' + path.join(OUT, 'chrome-profile'),
  '--window-size=600,700', '--hide-scrollbars', '--no-first-run', '--no-default-browser-check', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  let ws;
  for (let i = 0; i < 60 && !ws; i++) { try { const t = await fetch(`http://127.0.0.1:${PORT}/json`).then(r => r.json()); const p = t.find(x => x.type === 'page'); if (p) ws = p.webSocketDebuggerUrl; } catch (e) {} if (!ws) await sleep(300); }
  if (!ws) throw new Error('크롬에 붙지 못했다');
  const sock = new WebSocket(ws); await new Promise((res, rej) => { sock.onopen = res; sock.onerror = rej; });
  let id = 0; const waits = new Map();
  sock.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && waits.has(m.id)) { waits.get(m.id)(m); waits.delete(m.id); } };
  const send = (method, params = {}) => new Promise(res => { const i = ++id; waits.set(i, res); sock.send(JSON.stringify({ id: i, method, params })); });
  const evaluate = async expr => { const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }); if (r.result && r.result.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails.exception)); return r.result && r.result.result && r.result.result.value; };
  await send('Page.enable'); await send('Runtime.enable');
  await send('Page.navigate', { url: URL_ }); await sleep(4000);
  // 검사용 캔버스 하나를 화면에 붙인다
  await evaluate(`(() => { const c = document.createElement('canvas'); c.id = 'qaCanvas'; c.width = c.height = 320; c.style.cssText = 'width:320px;height:320px;position:fixed;left:0;top:0;z-index:99999;background:#2c4b3e'; document.body.appendChild(c); return 'ok'; })()`);
  const ids = ONLY || await evaluate(`[...new Set([...Object.keys(MOVE_3D.PROC), ...Object.keys(MOVE_3D.CLIPS)])]`);
  console.log('동작', ids.length, '개');
  for (const sex of ['M', 'F']) {
    for (const mid of ids) {
      const t0 = Date.now();
      const r = await evaluate(`(async () => {
        const c = document.getElementById('qaCanvas');
        MOVE_3D.start(c, ${JSON.stringify(mid)}, { sex: ${JSON.stringify(sex)} });
        let qa = null; for (let i = 0; i < 300 && !qa; i++) { await new Promise(r => setTimeout(r, 100)); qa = MOVE_3D.qa(c); }
        if (!qa) return { error: 'qa 손잡이가 안 생겼다 (불러오기 실패?)' };
        qa.pause();
        const out = { id: ${JSON.stringify(mid)}, sex: ${JSON.stringify(sex)}, cycle: qa.cycle, rest: qa.rest(), radii: qa.radii(), frames: [], images: [] };
        const N = ${FRAMES}, M = ${IMAGES};
        for (let k = 0; k < N; k++) {
          const t = qa.cycle * k / N; qa.seek(t);
          out.frames.push({ t: +t.toFixed(4), joints: qa.joints(), gear: qa.gear() });
          if (k % (N / M) === 0) out.images.push(c.toDataURL('image/jpeg', 0.85));
        }
        return out;
      })()`);
      if (r.error) { console.log(sex, mid, 'ERR', r.error); continue; }
      const imgs = r.images; delete r.images;
      fs.writeFileSync(path.join(OUT, `${sex}_${mid}.json`), JSON.stringify(r));
      imgs.forEach((d, i) => fs.writeFileSync(path.join(OUT, `${sex}_${mid}_${i}.jpg`), Buffer.from(d.split(',')[1], 'base64')));
      console.log(sex, mid, r.frames.length + ' frames', (Date.now() - t0) + 'ms');
    }
  }
  sock.close(); chrome.kill();
})().catch(e => { console.error('ERR', e.message); chrome.kill(); process.exit(1); });
