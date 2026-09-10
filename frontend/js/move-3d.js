/* 영상이 없는 동작을 위한 3D 느낌 동작 그림 (M5).
 *
 * 고른 종목·기록 종목은 공식 영상이 없다. 그 자리에 사람이 그 동작을 하는
 * 모습을 띄운다. move-art.js 의 자세(앞 프레임 pose-*, 뒤 프레임 poseb-*)를
 * 그대로 재료로 쓴다 — 34개 동작이 이미 검증돼 있고, 두 프레임 사이를 오가면
 * 그 운동을 하는 것처럼 보인다.
 *
 * 2D 한 색 선 그림은 팔·다리·기구가 겹치면 헷갈린다. 그래서
 *   - 사람은 회색 하나로, 대신 입체 음영으로 알아본다 — 기구·바닥은 더 어두운 회색
 *   - 굵은 캡슐에 그림자·하이라이트를 넣어 입체로
 *   - 발밑에 그림자 타원
 * 진짜 3D 모델이 아니다. 형체만 살린 입체 그림이다. 외부 파일·서버 없이 돈다.
 */
const MOVE_3D = (() => {
  const VIEW = 64;                         // 자세 그림의 viewBox
  // 사람은 회색 하나 — 색으로 나누지 않고 음영으로 알아본다. 기구·바닥은 더
  // 어둡고 가는 회색이라 몸과 구분된다. 그림자와 하이라이트 대비를 키워 둥글게.
  const COLORS = {
    head: { base: '#A9AFB8', dark: '#5C626B', light: '#EEF1F4' },
    body: { base: '#A9AFB8', dark: '#5C626B', light: '#EEF1F4' },
    gear: { base: '#6B717B', dark: '#3E434B', light: '#A3A9B2' },
  };
  const BEAT_MS = 1200;                    // 한 왕복

  /* ---- 자세 읽기: <symbol> 안의 circle · path 를 점들로 ---- */
  function parsePath(d){
    const toks = (d.match(/[MLHVQCZmlhvqcz]|-?\d*\.?\d+/g) || []);
    const lines = [];
    let cur = [], x = 0, y = 0, cmd = null, i = 0;
    const num = () => parseFloat(toks[i++]);
    const flush = () => { if (cur.length >= 2) lines.push(cur); cur = []; };
    while (i < toks.length) {
      const t = toks[i];
      if (/[A-Za-z]/.test(t)) { cmd = t; i++; if (cmd === 'Z' || cmd === 'z') { flush(); continue; } }
      if (cmd === 'M') { flush(); x = num(); y = num(); cur = [[x, y]]; cmd = 'L'; continue; }
      if (cmd === 'L') { x = num(); y = num(); cur.push([x, y]); continue; }
      if (cmd === 'H') { x = num(); cur.push([x, y]); continue; }
      if (cmd === 'V') { y = num(); cur.push([x, y]); continue; }
      if (cmd === 'Q') {                     // 곡선은 몇 점으로 편다
        const cx = num(), cy = num(), ex = num(), ey = num();
        const [sx, sy] = cur.length ? cur[cur.length - 1] : [x, y];
        for (let k = 1; k <= 6; k++) {
          const s = k / 6, a = (1 - s) * (1 - s), b = 2 * (1 - s) * s, c = s * s;
          cur.push([a * sx + b * cx + c * ex, a * sy + b * cy + c * ey]);
        }
        x = ex; y = ey; continue;
      }
      i++;                                   // 모르는 것은 건너뛴다
    }
    flush();
    return lines;
  }

  function readPose(id){
    const sym = document.getElementById(id);
    if (!sym) return null;
    const circles = [...sym.querySelectorAll('circle')].map(c => ({
      x: +c.getAttribute('cx'), y: +c.getAttribute('cy'), r: +c.getAttribute('r') }));
    const lines = [];
    sym.querySelectorAll('path').forEach(p => parsePath(p.getAttribute('d') || '').forEach(l => lines.push(l)));
    return { circles, lines };
  }

  /* ---- 부위 나누기: 머리와 이어진 선은 몸, 떨어진 선은 기구·바닥 ---- */
  function classify(pose){
    const head = pose.circles[0];
    const touchesHead = l => !!head && l.some(([x, y]) => Math.hypot(x - head.x, y - head.y) <= head.r + 2.5);
    const ends = l => [l[0], l[l.length - 1]];
    const body = new Set();
    // 점이 선분에 닿는지 — 팔은 몸통 선의 중간에서 갈라져 나온다. 끝점끼리만
    // 보면 팔이 기구로 잡힌다.
    const nearSeg = ([px, py], [ax, ay], [bx, by]) => {
      const dx = bx - ax, dy = by - ay, len2 = dx * dx + dy * dy || 1;
      const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2));
      return Math.hypot(px - (ax + t * dx), py - (ay + t * dy)) <= 2.2;
    };
    const touches = (l, m) => ends(l).some(pt => m.some((q, k) => k && nearSeg(pt, m[k - 1], q)))
                           || ends(m).some(pt => l.some((q, k) => k && nearSeg(pt, l[k - 1], q)));
    // 머리에 닿는 선에서 시작해, 닿는 선들을 따라간다
    pose.lines.forEach((l, i) => { if (touchesHead(l)) body.add(i); });
    let grew = true;
    while (grew) {
      grew = false;
      pose.lines.forEach((l, i) => {
        if (body.has(i)) return;
        for (const j of body) {
          if (touches(l, pose.lines[j])) { body.add(i); grew = true; return; }
        }
      });
    }
    return pose.lines.map((_, i) => (body.has(i) ? 'body' : 'gear'));
  }

  /* ---- 두 프레임 사이 ---- */
  function lerpPose(a, b, t){
    const same = a.lines.length === b.lines.length && a.lines.every((l, i) => l.length === b.lines[i].length)
      && a.circles.length === b.circles.length;
    if (!same) return t < 0.5 ? a : b;       // 모양이 다르면 그냥 바꿔 보인다
    const L = (p, q) => p + (q - p) * t;
    return {
      circles: a.circles.map((c, i) => ({ x: L(c.x, b.circles[i].x), y: L(c.y, b.circles[i].y), r: L(c.r, b.circles[i].r) })),
      lines: a.lines.map((l, i) => l.map((pt, k) => [L(pt[0], b.lines[i][k][0]), L(pt[1], b.lines[i][k][1])])),
    };
  }

  /* ---- 그리기 ---- */
  function capsule(ctx, l, col, w, s){
    // 그림자 → 바탕 → 하이라이트 순으로 겹쳐 그려 둥글게 보이게 한다
    const passes = [
      { c: col.dark, w: w * 1.0, dx: 1.1, dy: 1.4, alpha: 1 },
      { c: col.base, w: w * 0.84, dx: 0, dy: 0, alpha: 1 },
      { c: col.light, w: w * 0.30, dx: -0.7, dy: -0.9, alpha: 0.95 },
    ];
    passes.forEach(p => {
      ctx.globalAlpha = p.alpha;
      ctx.strokeStyle = p.c; ctx.lineWidth = p.w * s; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
      ctx.beginPath();
      l.forEach(([x, y], k) => { const X = (x + p.dx) * s, Y = (y + p.dy) * s; if (k) ctx.lineTo(X, Y); else ctx.moveTo(X, Y); });
      ctx.stroke();
    });
    ctx.globalAlpha = 1;
  }

  function sphere(ctx, c, col, s){
    const g = ctx.createRadialGradient((c.x - c.r * 0.35) * s, (c.y - c.r * 0.4) * s, c.r * 0.15 * s,
                                       c.x * s, c.y * s, c.r * 1.05 * s);
    g.addColorStop(0, col.light); g.addColorStop(0.55, col.base); g.addColorStop(1, col.dark);
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(c.x * s, c.y * s, c.r * s, 0, Math.PI * 2); ctx.fill();
  }

  function draw(ctx, pose, kinds, size){
    const s = size / VIEW;
    ctx.clearRect(0, 0, size, size);
    // 발밑 그림자 — 가장 낮은 점 아래
    const pts = pose.lines.flat().concat(pose.circles.map(c => [c.x, c.y + c.r]));
    if (pts.length) {
      const low = Math.max(...pts.map(p => p[1]));
      const xs = pts.filter(p => low - p[1] < 6).map(p => p[0]);
      const cx = xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : VIEW / 2;
      ctx.fillStyle = 'rgba(0,0,0,0.13)';
      ctx.beginPath(); ctx.ellipse(cx * s, (low + 1.5) * s, 14 * s, 3 * s, 0, 0, Math.PI * 2); ctx.fill();
    }
    // 기구·바닥을 먼저(뒤), 몸을 나중(앞)
    pose.lines.forEach((l, i) => { if (kinds[i] === 'gear') capsule(ctx, l, COLORS.gear, 3.2, s); });
    pose.lines.forEach((l, i) => { if (kinds[i] === 'body') capsule(ctx, l, COLORS.body, 4.6, s); });
    pose.circles.forEach((c, i) => sphere(ctx, c, i === 0 ? COLORS.head : COLORS.gear, s));
  }

  /* ---- 돌리기 ---- */
  let raf = null;

  function start(canvas, poseId){
    stop();
    if (!canvas || !poseId) return false;
    const a = readPose('pose-' + poseId), b = readPose('poseb-' + poseId) || a;
    if (!a) return false;
    const kinds = classify(a);
    const size = Math.max(160, Math.min(canvas.clientWidth || 320, 480));
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr; canvas.height = size * dpr;
    canvas.style.width = size + 'px'; canvas.style.height = size + 'px';
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const t0 = performance.now();
    const frame = now => {
      const ph = ((now - t0) % BEAT_MS) / BEAT_MS;        // 0→1
      const t = reduce ? 0 : (1 - Math.cos(ph * Math.PI * 2)) / 2;   // 부드럽게 갔다 온다
      draw(ctx, lerpPose(a, b, t), kinds, size);
      if (!reduce) raf = requestAnimationFrame(frame);
    };
    frame(t0);
    return true;
  }

  function stop(){ if (raf) { cancelAnimationFrame(raf); raf = null; } }

  return { start, stop, parsePath, classify, lerpPose, BEAT_MS };
})();
