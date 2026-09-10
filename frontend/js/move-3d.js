/* 영상이 없는 동작을 위한 3D 느낌 동작 그림 (M5).
 *
 * 고른 종목·기록 종목은 공식 영상이 없다. 그 자리에 사람이 그 동작을 하는
 * 모습을 띄운다. move-art.js 의 자세(앞 프레임 pose-*, 뒤 프레임 poseb-*)에서
 * 관절 자리만 가져온다 — 34개 동작이 이미 검증돼 있고, 두 프레임 사이를
 * 오가면 그 운동을 하는 것처럼 보인다.
 *
 * 졸라맨이 아니라 사람 몸이다. 어깨·가슴·허리·골반이 있는 몸통, 위팔·아래팔,
 * 허벅지·종아리가 굵기를 달리하며 이어지고, 관절마다 둥근 자리가 있다.
 * 성별에 따라 실루엣이 다르다 — 남성은 어깨가 넓고, 여성은 골반이 넓고
 * 허리가 들어가며 머리 뒤로 묶은 머리가 있다.
 *
 * 회색 하나. 색이 아니라 낮은 대비의 음영으로 형체를 알아본다. 물결·바닥
 * 같은 배경선은 가는 선으로만 둔다. 진짜 3D 모델이 아니라 형체를 살린 입체
 * 그림이다. 외부 파일·서버 없이 돈다.
 */
const MOVE_3D = (() => {
  const VIEW = 64;                         // 자세 그림의 viewBox
  const SKIN = { base: '#A9AFB8', dark: '#858B94', light: '#CDD2D8' };   // 대비는 낮게
  const HAIR = { base: '#8E949D', dark: '#70767F', light: '#A9AFB8' };
  const GEAR = { base: '#6E747D', dark: '#585D65', light: '#8B9199' };
  const BEAT_MS = 1200;                    // 한 왕복

  /* 성별 실루엣 — viewBox 단위. 남성은 어깨, 여성은 골반이 넓다. */
  const BUILD = {
    M: { shoulder: 9.2, chest: 8.0, waist: 6.4, hip: 6.6, upperArm: 3.4, foreArm: 2.6, thigh: 4.4, calf: 3.2, neck: 2.6, hair: 'short' },
    F: { shoulder: 7.2, chest: 6.8, waist: 4.6, hip: 8.0, upperArm: 2.9, foreArm: 2.2, thigh: 4.0, calf: 2.9, neck: 2.2, hair: 'tied' },
  };

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

  /* ---- 선 나누기: 몸통 · 팔다리 · 기구 · 배경선 ---- */
  const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
  function nearSeg([px, py], [ax, ay], [bx, by]){
    const dx = bx - ax, dy = by - ay, len2 = dx * dx + dy * dy || 1;
    const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2));
    return { d: Math.hypot(px - (ax + t * dx), py - (ay + t * dy)), t };
  }
  const ends = l => [l[0], l[l.length - 1]];

  function classify(pose){
    const head = pose.circles[0];
    const touchesHead = l => !!head && l.some(p => dist(p, [head.x, head.y]) <= head.r + 2.5);
    const touches = (l, m) => ends(l).some(pt => m.some((q, k) => k && nearSeg(pt, m[k - 1], q).d <= 2.2))
                           || ends(m).some(pt => l.some((q, k) => k && nearSeg(pt, l[k - 1], q).d <= 2.2));
    const body = new Set();
    pose.lines.forEach((l, i) => { if (touchesHead(l)) body.add(i); });
    let grew = true;
    while (grew) {
      grew = false;
      pose.lines.forEach((l, i) => {
        if (body.has(i)) return;
        for (const j of body) if (touches(l, pose.lines[j])) { body.add(i); grew = true; return; }
      });
    }
    return pose.lines.map((l, i) => {
      if (body.has(i)) return touchesHead(l) ? 'torso' : 'limb';
      const xs = l.map(p => p[0]), ys = l.map(p => p[1]);
      const w = Math.max(...xs) - Math.min(...xs), h = Math.max(...ys) - Math.min(...ys);
      if ((w >= 24 && h <= 10) || l.length > 2) return 'line';     // 바닥·물결
      return 'gear';                                                  // 바·덤벨·의자
    });
  }

  /* ---- 뼈대: 관절 자리를 뽑는다 ---- */
  function skeleton(pose, kinds){
    const head = pose.circles[0];
    if (!head) return null;
    const torsoIdx = kinds.findIndex(k => k === 'torso');
    let neck, hip;
    if (torsoIdx >= 0) {
      const t = pose.lines[torsoIdx];
      const e = ends(t);
      const first = dist(e[0], [head.x, head.y]) <= dist(e[1], [head.x, head.y]);
      neck = first ? e[0] : e[1]; hip = first ? e[1] : e[0];
    } else {
      neck = [head.x, head.y + head.r]; hip = [head.x, head.y + head.r + 16];
    }
    const along = p => nearSeg(p, neck, hip).t;          // 0 = 목, 1 = 골반
    const arms = [], legs = [];
    pose.lines.forEach((l, i) => {
      if (kinds[i] !== 'limb') return;
      // 몸통에 붙은 쪽이 앞이 되게 뒤집는다
      const a = nearSeg(l[0], neck, hip).d, b = nearSeg(l[l.length - 1], neck, hip).d;
      const pts = a <= b ? l : [...l].reverse();
      (along(pts[0]) < 0.55 ? arms : legs).push(pts);
    });
    return { head, neck, hip, arms, legs };
  }

  /* ---- 두 프레임 사이 ---- */
  function lerpPose(a, b, t){
    const same = a.lines.length === b.lines.length && a.lines.every((l, i) => l.length === b.lines[i].length)
      && a.circles.length === b.circles.length;
    if (!same) return t < 0.5 ? a : b;
    const L = (p, q) => p + (q - p) * t;
    return {
      circles: a.circles.map((c, i) => ({ x: L(c.x, b.circles[i].x), y: L(c.y, b.circles[i].y), r: L(c.r, b.circles[i].r) })),
      lines: a.lines.map((l, i) => l.map((pt, k) => [L(pt[0], b.lines[i][k][0]), L(pt[1], b.lines[i][k][1])])),
    };
  }

  /* ---- 그리기 재료 ---- */
  function shade(ctx, x0, y0, x1, y1, col){
    // 축과 직각으로 밝음 → 바탕 → 어둠. 둥근 통처럼 보인다.
    const dx = x1 - x0, dy = y1 - y0, len = Math.hypot(dx, dy) || 1;
    const nx = -dy / len, ny = dx / len;
    const g = ctx.createLinearGradient(x0 - nx * 6, y0 - ny * 6, x0 + nx * 6, y0 + ny * 6);
    g.addColorStop(0, col.light); g.addColorStop(0.5, col.base); g.addColorStop(1, col.dark);
    return g;
  }

  /* 굵기가 변하는 마디 하나 — 위팔은 굵고 손목 쪽은 가늘다 */
  function segment(ctx, a, b, w0, w1, col, s){
    const dx = b[0] - a[0], dy = b[1] - a[1], len = Math.hypot(dx, dy) || 1;
    const nx = -dy / len, ny = dx / len;
    ctx.fillStyle = shade(ctx, a[0] * s, a[1] * s, b[0] * s, b[1] * s, col);
    ctx.beginPath();
    ctx.moveTo((a[0] + nx * w0 / 2) * s, (a[1] + ny * w0 / 2) * s);
    ctx.lineTo((b[0] + nx * w1 / 2) * s, (b[1] + ny * w1 / 2) * s);
    ctx.lineTo((b[0] - nx * w1 / 2) * s, (b[1] - ny * w1 / 2) * s);
    ctx.lineTo((a[0] - nx * w0 / 2) * s, (a[1] - ny * w0 / 2) * s);
    ctx.closePath(); ctx.fill();
    // 관절·끝은 둥글게 — 마디와 같은 음영이라 구슬처럼 튀지 않고 이음새가 안 보인다
    ctx.beginPath(); ctx.arc(a[0] * s, a[1] * s, w0 / 2 * s, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(b[0] * s, b[1] * s, w1 / 2 * s, 0, Math.PI * 2); ctx.fill();
  }

  function ball(ctx, [x, y], r, col, s){
    const g = ctx.createRadialGradient((x - r * 0.35) * s, (y - r * 0.4) * s, r * 0.15 * s, x * s, y * s, r * 1.05 * s);
    g.addColorStop(0, col.light); g.addColorStop(0.55, col.base); g.addColorStop(1, col.dark);
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(x * s, y * s, r * s, 0, Math.PI * 2); ctx.fill();
  }

  /* 팔·다리 한 벌 — 첫 마디 굵고 끝으로 갈수록 가늘게 */
  function limb(ctx, pts, w0, w1, s){
    const n = Math.max(1, pts.length - 1);
    for (let k = 0; k < n; k++) {
      const a = w0 + (w1 - w0) * (k / n), b = w0 + (w1 - w0) * ((k + 1) / n);
      segment(ctx, pts[k], pts[k + 1], a, b, SKIN, s);
    }
  }

  /* 몸통 — 어깨 · 가슴 · 허리 · 골반 폭이 다른 판. 성별로 실루엣이 갈린다. */
  function torso(ctx, sk, build, s){
    const { neck, hip } = sk;
    const dx = hip[0] - neck[0], dy = hip[1] - neck[1], len = Math.hypot(dx, dy) || 1;
    const nx = -dy / len, ny = dx / len;
    const at = (t, w) => [[neck[0] + dx * t + nx * w / 2, neck[1] + dy * t + ny * w / 2],
                          [neck[0] + dx * t - nx * w / 2, neck[1] + dy * t - ny * w / 2]];
    const S = at(0.12, build.shoulder), C = at(0.38, build.chest), W = at(0.68, build.waist), H = at(1.0, build.hip);
    ctx.fillStyle = shade(ctx, neck[0] * s, neck[1] * s, hip[0] * s, hip[1] * s, SKIN);
    ctx.beginPath();
    ctx.moveTo(S[0][0] * s, S[0][1] * s);
    ctx.quadraticCurveTo(C[0][0] * s, C[0][1] * s, W[0][0] * s, W[0][1] * s);
    ctx.quadraticCurveTo(H[0][0] * s, H[0][1] * s, H[0][0] * s, H[0][1] * s);
    ctx.lineTo(H[1][0] * s, H[1][1] * s);
    ctx.quadraticCurveTo(H[1][0] * s, H[1][1] * s, W[1][0] * s, W[1][1] * s);
    ctx.quadraticCurveTo(C[1][0] * s, C[1][1] * s, S[1][0] * s, S[1][1] * s);
    ctx.closePath(); ctx.fill();
    // 어깨·골반은 둥글게 — 몸통과 같은 음영으로
    [[S[0], build.shoulder * 0.22], [S[1], build.shoulder * 0.22], [H[0], build.hip * 0.2], [H[1], build.hip * 0.2]]
      .forEach(([pt, r]) => { ctx.beginPath(); ctx.arc(pt[0] * s, pt[1] * s, r * s, 0, Math.PI * 2); ctx.fill(); });
    // 목
    segment(ctx, [sk.head.x, sk.head.y], neck, build.neck, build.neck, SKIN, s);
    return { S, H };
  }

  function headAndHair(ctx, sk, build, s){
    const h = sk.head;
    if (build.hair === 'tied') {
      // 묶은 머리 — 머리 뒤로 작은 덩이. 머리보다 살짝 뒤(오른쪽 아래)에 둔다.
      ball(ctx, [h.x + h.r * 0.75, h.y + h.r * 0.35], h.r * 0.42, HAIR, s);
    }
    ball(ctx, [h.x, h.y], h.r, SKIN, s);
    // 머리카락 — 윗머리를 덮는 반원. 남성은 짧게, 여성은 조금 더 내려온다.
    const 덮음 = build.hair === 'tied' ? 0.62 : 0.5;
    ctx.fillStyle = shade(ctx, (h.x - h.r) * s, h.y * s, (h.x + h.r) * s, h.y * s, HAIR);
    ctx.beginPath();
    ctx.arc(h.x * s, h.y * s, h.r * 1.02 * s, Math.PI * (1 + (1 - 덮음) / 2), Math.PI * (2 - (1 - 덮음) / 2));
    ctx.closePath(); ctx.fill();
  }

  function thin(ctx, l, s){
    ctx.globalAlpha = 0.5;
    ctx.strokeStyle = GEAR.base; ctx.lineWidth = 1.3 * s; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.beginPath();
    l.forEach(([x, y], k) => { if (k) ctx.lineTo(x * s, y * s); else ctx.moveTo(x * s, y * s); });
    ctx.stroke();
    ctx.globalAlpha = 1;
  }

  function gear(ctx, l, s){
    for (let k = 1; k < l.length; k++) segment(ctx, l[k - 1], l[k], 2.6, 2.6, GEAR, s);
  }

  function draw(ctx, pose, kinds, size, sex){
    const s = size / VIEW;
    const build = BUILD[sex === 'F' ? 'F' : 'M'];
    ctx.clearRect(0, 0, size, size);
    const sk = skeleton(pose, kinds);
    // 발밑 그림자
    const pts = pose.lines.flat().concat(pose.circles.map(c => [c.x, c.y + c.r]));
    if (pts.length) {
      const low = Math.max(...pts.map(p => p[1]));
      const xs = pts.filter(p => low - p[1] < 6).map(p => p[0]);
      const cx = xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : VIEW / 2;
      ctx.fillStyle = 'rgba(0,0,0,0.10)';
      ctx.beginPath(); ctx.ellipse(cx * s, (low + 1.5) * s, 15 * s, 3 * s, 0, 0, Math.PI * 2); ctx.fill();
    }
    // 배경선 → 기구 → 다리 → 몸통 → 팔 → 머리 (뒤에서 앞으로)
    pose.lines.forEach((l, i) => { if (kinds[i] === 'line') thin(ctx, l, s); });
    pose.lines.forEach((l, i) => { if (kinds[i] === 'gear') gear(ctx, l, s); });
    pose.circles.slice(1).forEach(c => ball(ctx, [c.x, c.y], c.r, GEAR, s));   // 케틀벨 같은 것
    if (!sk) return;
    sk.legs.forEach(l => limb(ctx, l, build.thigh, build.calf, s));
    torso(ctx, sk, build, s);
    sk.arms.forEach(l => limb(ctx, l, build.upperArm, build.foreArm, s));
    headAndHair(ctx, sk, build, s);
  }

  /* ---- 돌리기 ---- */
  let raf = null;

  function start(canvas, poseId, { sex } = {}){
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
      const ph = ((now - t0) % BEAT_MS) / BEAT_MS;
      const t = reduce ? 0 : (1 - Math.cos(ph * Math.PI * 2)) / 2;
      draw(ctx, lerpPose(a, b, t), kinds, size, sex);
      if (!reduce) raf = requestAnimationFrame(frame);
    };
    frame(t0);
    return true;
  }

  function stop(){ if (raf) { cancelAnimationFrame(raf); raf = null; } }

  return { start, stop, parsePath, classify, skeleton, lerpPose, BUILD, BEAT_MS };
})();
