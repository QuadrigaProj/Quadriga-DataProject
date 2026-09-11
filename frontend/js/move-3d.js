/* 영상이 없는 동작을 위한 3D 마네킹 (M5).
 *
 * 고른 종목·기록 종목은 공식 영상이 없다. 그 자리에 사람 몸 모양의 마네킹이
 * 그 동작을 하는 모습을 띄운다. 졸라맨을 부풀린 게 아니라 진짜 3D — 머리·목·
 * 가슴·골반·위팔·아래팔·손·허벅지·종아리·발이 관절로 이어진 몸을 three.js 로
 * 짓고, 동작마다 두 자세(관절 각도) 사이를 오간다. 빛과 그림자가 있어 형체가
 * 살아난다. 회색 하나. 성별에 따라 실루엣이 다르다 — 남성은 어깨가 넓고,
 * 여성은 골반이 넓고 허리가 들어가며 머리를 뒤로 묶었다.
 *
 * three.js 는 cdnjs 에서 처음 필요할 때 한 번만 받는다. 못 받으면(오프라인 등)
 * 캔버스에 짧은 안내만 적는다.
 */
const MOVE_3D = (() => {
  const THREE_URL = 'https://cdnjs.cloudflare.com/ajax/libs/three.js/0.160.0/three.min.js';
  const BEAT_MS = 1400;                    // 두 자세 사이 한 왕복
  const rad = d => d * Math.PI / 180;

  /* ---- 몸의 치수 (m). 성별로 실루엣이 갈린다 ---- */
  const DIM = {
    M: { hipW: 0.09, shW: 0.20, thigh: 0.44, shin: 0.42, uArm: 0.30, fArm: 0.27,
         rThigh: [0.082, 0.06], rShin: [0.058, 0.04], rUArm: [0.058, 0.044], rFArm: [0.044, 0.034],
         pelvis: [[0, -0.15], [0.12, -0.14], [0.165, -0.05], [0.165, 0.04], [0.15, 0.12], [0.145, 0.15]],
         chest: [[0.145, -0.01], [0.15, 0.05], [0.17, 0.18], [0.185, 0.28], [0.17, 0.37], [0.09, 0.41], [0, 0.42]],
         depth: 0.62, head: [0.105, 0.125, 0.11], neck: 0.10, hair: 'short' },
    F: { hipW: 0.10, shW: 0.17, thigh: 0.42, shin: 0.40, uArm: 0.28, fArm: 0.25,
         rThigh: [0.08, 0.055], rShin: [0.054, 0.037], rUArm: [0.05, 0.038], rFArm: [0.038, 0.03],
         pelvis: [[0, -0.15], [0.13, -0.14], [0.18, -0.05], [0.18, 0.04], [0.15, 0.12], [0.125, 0.15]],
         chest: [[0.125, -0.01], [0.13, 0.05], [0.15, 0.18], [0.165, 0.28], [0.15, 0.37], [0.08, 0.41], [0, 0.42]],
         depth: 0.6, head: [0.10, 0.12, 0.105], neck: 0.09, hair: 'tied', bust: true },
  };

  /* ---- 동작별 자세 ----
   * 각도는 도(°). 앞으로 굽히는 쪽이 +.
   *   rx ry rz : 몸 전체 기울기 (누운 자세는 rx ±90 + rz 90)
   *   spine    : 허리 앞으로 굽힘 / side 옆으로 / turn 비틀기
   *   head     : 고개 숙임 / tilt 갸웃
   *   sh ab rot el : 어깨 앞올림 · 옆벌림 · 팔 비틀기 · 팔꿈치 굽힘 (L/R 붙이면 한쪽만)
   *   hip hpa kn an: 고관절 앞올림 · 옆벌림 · 무릎 굽힘 · 발목 젖힘(발끝 위가 +)
   *   lift     : 바닥에서 띄우기 (점프·벤치)
   *   lean     : 누운 몸을 통째로 기울이기 (+ 면 머리 쪽이 내려가고 골반이 올라간다)
   * 발목(an)을 안 적으면 서 있는 자세에선 발이 바닥에 평평하게 놓이도록 맞춘다. */
  const STAND = { ab: 5, el: 8 };
  const SUPINE = { rx: -90, rz: 90 };    // 바로 눕기 (머리는 왼쪽)
  const PRONE = { rx: 90, rz: 90 };      // 엎드리기
  const SIDE = { rz: 90 };               // 오른쪽으로 눕기
  const LOW = { el: 26, y: 0.45, dist: 4.7 };   // 누운 자세는 조금 위에서 본다
  const P = (a, b, extra = {}) => ({ a: { ...STAND, ...a }, b: { ...STAND, ...b }, ...extra });
  const POSES = {
    'squat':            P({ sh: 35, el: 5 }, { hip: 85, kn: 100, spine: 35, sh: 85, el: 5 }),
    'pushup':           P({ ...PRONE, sh: 90, el: 5, an: 0 }, { ...PRONE, sh: 50, ab: 25, el: 95, an: 0 }, { cam: LOW }),
    'knee-pushup':      P({ ...PRONE, sh: 90, el: 5, hip: 10, kn: 90, an: 0 }, { ...PRONE, sh: 50, ab: 25, el: 95, hip: 10, kn: 90, an: 0 }, { cam: LOW }),
    'lunge':            P({ el: 8 }, { hipL: 85, knL: 90, hipR: -15, knR: 85, anR: -40, spine: 5 }),
    'plank':            P({ ...PRONE, sh: 90, el: 90, an: 0 }, { ...PRONE, sh: 90, el: 90, an: 0, head: 8 }, { cam: LOW }),
    'crunch':           P({ ...SUPINE, hip: 45, kn: 135, an: 0, sh: 150, ab: 30, el: 130, head: 10 },
                          { ...SUPINE, hip: 45, kn: 135, an: 0, sh: 150, ab: 30, el: 130, spine: 35, head: 25 }, { cam: LOW }),
    'bridge':           P({ ...SUPINE, hip: 45, kn: 135, an: 0, ab: 15 }, { ...SUPINE, lean: 25, hip: -5, kn: 110, an: 0, ab: 15 }, { cam: LOW }),
    'burpee':           P({ spine: 50, hip: 115, kn: 130, sh: 95, el: 5, head: -15 }, { sh: 175, ab: 15, el: 5, kn: 10, an: -30, lift: 0.25, head: -10 }, { cam: { y: 1.1, dist: 5.6 } }),
    'bench-press':      P({ ...SUPINE, hip: -25, kn: 50, an: 0, sh: 90, ab: 10, el: 5 },
                          { ...SUPINE, hip: -25, kn: 50, an: 0, sh: 30, ab: 65, el: 95 }, { cam: LOW, gear: 'bench' }),
    'deadlift':         P({ rx: 40, hip: 60, kn: 30, spine: 20, sh: 60, el: 0, head: -20 }, { sh: 0, ab: 3, el: 0 }, { gear: 'barbell' }),
    'barbell-squat':    P({ ab: 70, rot: 90, el: 150 }, { hip: 85, kn: 100, spine: 30, ab: 70, rot: 90, el: 150 }, { gear: 'backbar' }),
    'lat-pulldown':     P({ hip: 90, kn: 90, sh: 165, ab: 25, el: 10, head: -10 }, { hip: 90, kn: 90, sh: 60, ab: 45, el: 110 }, { gear: 'pulldown' }),
    'leg-press':        P({ rx: -50, hip: 110, kn: 110, an: 0, ab: 30, el: 60 }, { rx: -50, hip: 70, kn: 15, an: 0, ab: 30, el: 60 }, { cam: LOW, gear: 'legpress' }),
    'dumbbell-curl':    P({ el: 20, ab: 6 }, { el: 130, ab: 6 }, { gear: 'dumbbells' }),
    'shoulder-press':   P({ ab: 85, rot: 90, el: 95 }, { ab: 165, rot: 90, el: 10 }, { gear: 'dumbbells', cam: { y: 1.05, dist: 5.0 } }),
    'kettlebell-swing': P({ rx: 30, hip: 55, kn: 25, spine: 25, sh: 50, ab: -12, el: 0, head: -15 }, { sh: 90, ab: -12, el: 0 }, { gear: 'kettlebell' }),
    'walk':             P({ hipL: 25, knL: 5, anL: 5, hipR: -15, knR: 25, anR: -10, shL: -20, shR: 25, el: 20 },
                          { hipL: -15, knL: 25, anL: -10, hipR: 25, knR: 5, anR: 5, shL: 25, shR: -20, el: 20 }),
    'run':              P({ hipL: 55, knL: 40, anL: 10, hipR: -25, knR: 85, anR: -20, shL: -35, shR: 45, el: 90, spine: 8, lift: 0.04 },
                          { hipL: -25, knL: 85, anL: -20, hipR: 55, knR: 40, anR: 10, shL: 45, shR: -35, el: 90, spine: 8, lift: 0.04 }),
    'treadmill':        P({ hipL: 40, knL: 30, anL: 5, hipR: -20, knR: 70, anR: -20, shL: -30, shR: 35, el: 90, spine: 6, lift: 0.12 },
                          { hipL: -20, knL: 70, anL: -20, hipR: 40, knR: 30, anR: 5, shL: 35, shR: -30, el: 90, spine: 6, lift: 0.12 }, { gear: 'treadmill' }),
    'cycle':            P({ spine: 35, head: -25, sh: 55, el: 25, hipL: 105, knL: 105, anL: -10, hipR: 45, knR: 25, anR: -10, lift: 0.2 },
                          { spine: 35, head: -25, sh: 55, el: 25, hipR: 105, knR: 105, anR: -10, hipL: 45, knL: 25, anL: -10, lift: 0.2 }, { gear: 'bike' }),
    'rowing':           P({ hip: 110, kn: 120, an: 15, spine: 15, sh: 80, el: 0, head: -10, lift: 0.22 },
                          { hip: 75, kn: 10, an: 30, spine: -15, sh: -25, el: 100, lift: 0.22 }, { gear: 'rower' }),
    'jump-rope':        P({ el: 70, ab: 25, kn: 10 }, { el: 70, ab: 25, kn: 15, an: -25, lift: 0.13 }, { gear: 'rope' }),
    'stair':            P({ hipL: 65, knL: 85, anL: 20, hipR: -10, knR: 5, shL: -15, shR: 25, el: 25, spine: 10 },
                          { hipL: 25, knL: 15, anL: 10, hipR: -25, knR: 60, anR: -30, shL: 20, shR: -15, el: 25, spine: 10 }, { gear: 'steps' }),
    'swim':             P({ ...PRONE, shL: 175, abL: 5, elL: 5, shR: -50, abR: 45, elR: 90, hipL: 12, hipR: -12, kn: 12, an: -60, head: -25 },
                          { ...PRONE, shR: 175, abR: 5, elR: 5, shL: -50, abL: 45, elL: 90, hipR: 12, hipL: -12, kn: 12, an: -60, head: -25 }, { cam: LOW, gear: 'water' }),
    'hamstring-stretch': P({ hip: 90, kn: 5, an: 20, spine: 20, sh: 70, el: 10, head: 10 }, { hip: 90, kn: 5, an: 20, spine: 55, sh: 105, el: 10, head: 20 }, { cam: LOW }),
    'calf-stretch':     P({ ry: -55, hipL: 25, knL: 30, hipR: -25, knR: 0, sh: 80, el: 15, spine: 8 },
                          { ry: -55, hipL: 32, knL: 45, hipR: -32, knR: 0, sh: 85, el: 10, spine: 12 }, { gear: 'wall' }),
    'shoulder-stretch': P({ shL: 85, abL: -25, elL: 5, shR: 40, abR: -10, elR: 110 }, { shL: 85, abL: -40, elL: 5, shR: 40, abR: -10, elR: 115, turn: 10 }),
    'hip-stretch':      P({ hipL: 90, knL: 90, anL: 0, hipR: -10, knR: 90, anR: -90, sh: 40, el: 25, spine: -5 },
                          { hipL: 95, knL: 85, anL: 0, hipR: -28, knR: 90, anR: -90, sh: 40, el: 25, spine: -8 }),
    'twist':            P({ hipL: 90, knL: 5, anL: 20, hipR: 100, knR: 110, anR: 0, shR: 40, abR: -15, elR: 50, shL: -30, abL: 10, elL: 10 },
                          { hipL: 90, knL: 5, anL: 20, hipR: 100, knR: 110, anR: 0, shR: 40, abR: -15, elR: 50, shL: -30, abL: 10, elL: 10, turn: 45 }, { cam: LOW }),
    'neck-stretch':     P({ }, { tilt: 28, shR: 165, abR: 20, rotR: 90, elR: 120 }),
    'deep-breath':      P({ ab: 8, el: 5 }, { ab: 160, el: 5, spine: -8, head: -12 }, { cam: { y: 1.05, dist: 5.0 } }),
    'one-leg':          P({ hipR: 30, knR: 90, anR: -20, ab: 55, el: 5 }, { hipR: 45, knR: 100, anR: -20, ab: 75, el: 5 }),
    'side-plank':       P({ ...SIDE, lean: -12, abR: 90, elR: 90, abL: 90, elL: 0, an: 0 }, { ...SIDE, lean: -12, abR: 90, elR: 90, abL: 90, elL: 0, an: 0, side: 8 }, { cam: LOW }),
    'dead-bug':         P({ ...SUPINE, sh: 90, el: 5, hip: 90, kn: 90, an: 0, head: 10 },
                          { ...SUPINE, shL: 170, elL: 5, shR: 90, elR: 5, hipL: 90, knL: 90, hipR: 25, knR: 10, an: 0, head: 10 }, { cam: LOW }),
  };

  /* 양쪽에 같이 적은 값(sh, el …)을 왼쪽·오른쪽으로 펼친다. 한쪽 값이 있으면 그게 우선. */
  const BOTH = { sh: ['shL', 'shR'], ab: ['abL', 'abR'], rot: ['rotL', 'rotR'], el: ['elL', 'elR'],
                 hip: ['hipL', 'hipR'], hpa: ['hpaL', 'hpaR'], kn: ['knL', 'knR'], an: ['anL', 'anR'] };
  const KEYS = ['rx', 'ry', 'rz', 'spine', 'side', 'turn', 'head', 'tilt', 'lift', 'lean',
                ...Object.values(BOTH).flat()];
  function expand(p){
    const q = {};
    for (const k of KEYS) q[k] = 0;
    for (const [k, v] of Object.entries(p)) if (BOTH[k]) BOTH[k].forEach(kk => { if (p[kk] === undefined) q[kk] = v; });
    for (const [k, v] of Object.entries(p)) if (!BOTH[k] && k in q) q[k] = v;
    // 발목을 안 적었으면 — 서 있는 자세에선 발이 바닥에 평평하게
    for (const s of ['L', 'R']) if (p['an' + s] === undefined && p.an === undefined) {
      q['an' + s] = Math.abs(q.rx) < 60 ? q.rx - q['hip' + s] + q['kn' + s] : 0;
    }
    return q;
  }
  function lerpPose(a, b, t){
    const A = expand(a), B = expand(b), out = {};
    for (const k of KEYS) out[k] = A[k] + (B[k] - A[k]) * t;
    return out;
  }

  /* ---- three.js 받기 (한 번만) ---- */
  let threeLoading = null;
  function loadThree(){
    if (window.THREE) return Promise.resolve(window.THREE);
    if (threeLoading) return threeLoading;
    threeLoading = new Promise((res, rej) => {
      const s = document.createElement('script');
      s.src = THREE_URL; s.async = true;
      s.onload = () => window.THREE ? res(window.THREE) : rej(new Error('three 없음'));
      s.onerror = () => { threeLoading = null; rej(new Error('three 로드 실패')); };
      document.head.appendChild(s);
    });
    return threeLoading;
  }

  /* ---- 몸 짓기 ---- */
  function buildBody(T, sex){
    const D = DIM[sex === 'F' ? 'F' : 'M'];
    const skin = new T.MeshStandardMaterial({ color: 0xB3B8BF, roughness: 0.6, metalness: 0.06 });
    const hairM = new T.MeshStandardMaterial({ color: 0x7F858E, roughness: 0.85, metalness: 0.02 });
    const mesh = (g, m = skin) => { const o = new T.Mesh(g, m); o.castShadow = true; o.receiveShadow = true; return o; };
    const joint = (parent, x, y, z, order) => {
      const g = new T.Group(); g.position.set(x, y, z); if (order) g.rotation.order = order; parent.add(g); return g; };
    const lathe = pts => mesh(new T.LatheGeometry(pts.map(([r, y]) => new T.Vector2(r, y)), 40));
    // 굵기가 변하는 마디 — 관절 쪽이 굵고 끝이 가늘다. 양 끝은 구로 둥글게.
    const limb = (parent, len, [r0, r1]) => {
      const cyl = mesh(new T.CylinderGeometry(r0, r1, len, 24)); cyl.position.y = -len / 2; parent.add(cyl);
      parent.add(mesh(new T.SphereGeometry(r0, 24, 16)));
      const bot = mesh(new T.SphereGeometry(r1, 24, 16)); bot.position.y = -len; parent.add(bot);
    };

    const pivot = new T.Group();                                  // 몸 전체를 기울이는 바깥 축
    const root = new T.Group(); pivot.add(root);                  // 골반 가운데
    const pelvis = lathe(D.pelvis); pelvis.scale.z = D.depth; root.add(pelvis);
    const spine = joint(root, 0, 0.12, 0);
    const chest = lathe(D.chest); chest.scale.z = D.depth; spine.add(chest);
    if (D.bust) [-1, 1].forEach(s => {
      const b = mesh(new T.SphereGeometry(0.055, 24, 16)); b.scale.set(1, 0.85, 0.75);
      b.position.set(s * 0.065, 0.24, 0.085); spine.add(b);
    });
    const neck = joint(spine, 0, 0.40, 0);
    const neckM = mesh(new T.CylinderGeometry(0.045, 0.05, D.neck + 0.04, 20)); neckM.position.y = D.neck / 2; neck.add(neckM);
    const head = joint(neck, 0, D.neck, 0);
    const skull = mesh(new T.SphereGeometry(1, 32, 24)); skull.scale.set(...D.head);
    skull.position.set(0, D.head[1] - 0.01, 0.01); head.add(skull);
    // 머리카락 — 윗머리를 덮는 모자꼴. 여성은 더 내려오고 뒤로 묶었다.
    const cap = mesh(new T.SphereGeometry(1, 32, 16, 0, Math.PI * 2, 0, Math.PI * (D.hair === 'tied' ? 0.6 : 0.52)), hairM);
    cap.scale.set(D.head[0] * 1.04, D.head[1] * 1.04, D.head[2] * 1.04);
    cap.position.set(0, D.head[1], 0.0); cap.rotation.x = D.hair === 'tied' ? -0.5 : -0.4; head.add(cap);
    if (D.hair === 'tied') {
      const bun = mesh(new T.SphereGeometry(0.05, 20, 14), hairM); bun.position.set(0, D.head[1] - 0.01, -0.125); head.add(bun);
      const tail = mesh(new T.CapsuleGeometry(0.028, 0.13, 6, 12), hairM); tail.position.set(0, D.head[1] - 0.11, -0.13); tail.rotation.x = -0.25; head.add(tail);
    }

    const arm = side => {
      const sh = joint(spine, side * D.shW, 0.35, 0, 'XZY');       // 옆벌림 → 앞올림 순
      limb(sh, D.uArm, D.rUArm);
      const el = joint(sh, 0, -D.uArm, 0);
      limb(el, D.fArm, D.rFArm);
      const wr = joint(el, 0, -D.fArm, 0);
      const hand = mesh(new T.SphereGeometry(1, 20, 14)); hand.scale.set(0.04, 0.085, 0.024);
      hand.position.y = -0.075; wr.add(hand);
      return { sh, el, wr, hand };
    };
    const leg = side => {
      const hip = joint(root, side * D.hipW, -0.02, 0, 'XZY');
      limb(hip, D.thigh, D.rThigh);
      const kn = joint(hip, 0, -D.thigh, 0);
      limb(kn, D.shin, D.rShin);
      const an = joint(kn, 0, -D.shin, 0);
      const foot = mesh(new T.CapsuleGeometry(0.038, 0.15, 6, 12)); foot.rotation.x = Math.PI / 2;
      foot.position.set(0, -0.045, 0.06); an.add(foot);
      const heel = mesh(new T.SphereGeometry(0.042, 16, 12)); heel.position.set(0, -0.04, -0.03); an.add(heel);
      return { hip, kn, an, foot, heel };
    };
    const arms = { L: arm(1), R: arm(-1) }, legs = { L: leg(1), R: leg(-1) };
    // 바닥에 닿을 수 있는 자리들 — 가장 낮은 곳이 바닥이 된다
    const contacts = [
      [legs.L.foot, 0.04], [legs.R.foot, 0.04], [legs.L.heel, 0.042], [legs.R.heel, 0.042],
      [legs.L.kn, 0.06], [legs.R.kn, 0.06], [arms.L.hand, 0.03], [arms.R.hand, 0.03],
      [arms.L.el, 0.045], [arms.R.el, 0.045], [arms.L.sh, 0.06], [arms.R.sh, 0.06],
      [root, 0.12], [chest, 0.12], [skull, 0.12],
    ];
    return { D, pivot, root, spine, neck, head, arms, legs, contacts, skin };
  }

  /* 자세를 관절에 넣고, 가장 낮은 곳이 바닥(y=0)에 닿게 몸을 내린다 */
  function applyPose(T, B, p){
    B.root.rotation.set(rad(p.rx), rad(p.ry), rad(p.rz));
    B.spine.rotation.set(rad(p.spine), rad(p.turn), rad(p.side));
    B.head.rotation.set(rad(p.head), 0, rad(p.tilt));
    for (const [s, sign] of [['L', 1], ['R', -1]]) {
      const A = B.arms[s], L = B.legs[s];
      A.sh.rotation.set(-rad(p['sh' + s]), rad(p['rot' + s]) * sign, rad(p['ab' + s]) * sign);
      A.el.rotation.x = -rad(p['el' + s]);
      L.hip.rotation.set(-rad(p['hip' + s]), 0, rad(p['hpa' + s]) * sign);
      L.kn.rotation.x = rad(p['kn' + s]);
      L.an.rotation.x = -rad(p['an' + s]);
    }
    B.pivot.rotation.z = rad(p.lean);
    B.pivot.position.set(0, 0, 0);
    B.pivot.updateMatrixWorld(true);
    const v = B._tmp || (B._tmp = new T.Vector3());
    let lo = Infinity;
    for (const [o, r] of B.contacts) { o.getWorldPosition(v); lo = Math.min(lo, v.y - r); }
    B.pivot.position.y = -lo + (p.lift || 0);
    B.pivot.updateMatrixWorld(true);
  }

  /* ---- 기구 ---- */
  function buildGear(T, name, B, scene){
    const M = new T.MeshStandardMaterial({ color: 0x565B63, roughness: 0.5, metalness: 0.3 });
    const soft = new T.MeshStandardMaterial({ color: 0x6E747D, roughness: 0.9 });
    const mesh = (g, m = M) => { const o = new T.Mesh(g, m); o.castShadow = true; o.receiveShadow = true; return o; };
    const box = (w, h, d, x, y, z, m) => { const b = mesh(new T.BoxGeometry(w, h, d), m); b.position.set(x, y, z); return b; };
    const tube = (a, b, r, m) => {
      const d = b.clone().sub(a), len = d.length();
      const c = mesh(new T.CylinderGeometry(r, r, len, 12), m);
      c.position.copy(a).add(b).multiplyScalar(0.5);
      c.quaternion.setFromUnitVectors(new T.Vector3(0, 1, 0), d.normalize());
      return c;
    };
    const V = (x, y, z) => new T.Vector3(x, y, z);
    const barbell = () => {
      const g = new T.Group();
      const bar = mesh(new T.CylinderGeometry(0.014, 0.014, 1.7, 12)); bar.rotation.z = Math.PI / 2; g.add(bar);
      [-0.62, 0.62].forEach(x => { const pl = mesh(new T.CylinderGeometry(0.16, 0.16, 0.035, 28)); pl.rotation.z = Math.PI / 2; pl.position.x = x; g.add(pl); });
      return g;
    };
    const dumbbell = () => {
      const g = new T.Group();
      const bar = mesh(new T.CylinderGeometry(0.011, 0.011, 0.16, 10)); bar.rotation.z = Math.PI / 2; g.add(bar);
      [-0.075, 0.075].forEach(x => { const d = mesh(new T.CylinderGeometry(0.04, 0.04, 0.035, 20)); d.rotation.z = Math.PI / 2; d.position.x = x; g.add(d); });
      return g;
    };
    const a = new T.Vector3(), b = new T.Vector3();
    // 두 손 사이에 놓는 것 (바벨·케틀벨·풀다운 바)
    const betweenHands = (obj, drop = 0) => {
      B.arms.L.hand.getWorldPosition(a); B.arms.R.hand.getWorldPosition(b);
      obj.position.copy(a).add(b).multiplyScalar(0.5); obj.position.y -= drop;
      obj.quaternion.setFromUnitVectors(new T.Vector3(1, 0, 0), a.sub(b).normalize());
    };
    const add = o => { scene.add(o); return o; };
    switch (name) {
      case 'barbell': { const g = add(barbell()); return { update(){ betweenHands(g); } }; }
      case 'backbar': { const g = barbell(); g.position.set(0, 0.42, -0.07); B.spine.add(g); return {}; }
      case 'bench': {
        const g = add(barbell());
        const bench = add(box(1.2, 0.06, 0.32, -0.3, 0.4, 0, soft));          // 머리 쪽으로 치우쳐 등 전체를 받친다
        const legs = [-0.8, 0.2].map(x => add(box(0.06, 0.4, 0.06, x, 0.2, 0, soft)));
        return { update(){
          betweenHands(g);
          B.root.getWorldPosition(a); const top = a.y - 0.115;        // 등이 닿는 높이
          bench.position.y = top - 0.03; legs.forEach(l => { l.scale.y = Math.max(0.05, top - 0.03) / 0.4; l.position.y = (top - 0.03) / 2; });
        } };
      }
      case 'pulldown': {
        const g = add(barbell()); g.scale.set(0.7, 1, 1);
        const seat = add(box(0.42, 0.06, 0.4, 0, 0.32, 0.02, soft));
        add(box(0.06, 0.32, 0.06, 0, 0.16, 0.02, soft));
        return { update(){ betweenHands(g); B.root.getWorldPosition(a); seat.position.y = a.y - 0.15 - 0.03; } };
      }
      case 'legpress': {
        const back = box(0.46, 0.7, 0.08, 0, 0.22, -0.2, soft); back.rotation.x = 0.15; B.root.add(back);
        const plate = add(box(0.55, 0.55, 0.05, 0, 0, 0, M));
        return { update(){
          B.legs.L.foot.getWorldPosition(a); B.legs.R.foot.getWorldPosition(b);
          plate.position.copy(a).add(b).multiplyScalar(0.5);
          B.legs.L.an.getWorldPosition(b); a.sub(b).normalize();     // 발이 향하는 쪽으로 판을 세운다
          plate.quaternion.setFromUnitVectors(new T.Vector3(0, 0, 1), a);
          plate.position.addScaledVector(a, 0.07);
        } };
      }
      case 'dumbbells': {
        ['L', 'R'].forEach(s => { const d = dumbbell(); d.position.y = -0.075; B.arms[s].wr.add(d); });
        return {};
      }
      case 'kettlebell': {
        const g = new T.Group();
        const ball = mesh(new T.SphereGeometry(0.085, 24, 18)); ball.position.y = -0.11; g.add(ball);
        const handle = mesh(new T.TorusGeometry(0.06, 0.013, 10, 24)); handle.rotation.y = Math.PI / 2; g.add(handle);
        add(g);
        return { update(){
          betweenHands(g);
          B.arms.R.hand.getWorldQuaternion(g.quaternion);            // 손에서 팔 방향으로 늘어진다
        } };
      }
      case 'treadmill': {
        add(box(0.72, 0.12, 1.6, 0, 0.06, 0.1, soft));
        [-0.34, 0.34].forEach(x => add(tube(V(x, 0.12, 0.7), V(x, 1.05, 0.7), 0.02)));
        add(tube(V(-0.34, 1.05, 0.7), V(0.34, 1.05, 0.7), 0.02));
        add(box(0.4, 0.16, 0.05, 0, 1.15, 0.7, M));
        return {};
      }
      case 'bike': {
        [-0.5, 0.52].forEach(z => { const w = mesh(new T.TorusGeometry(0.32, 0.03, 10, 40)); w.rotation.y = Math.PI / 2; w.position.set(0, 0.32, z); add(w); });
        add(tube(V(0, 0.32, -0.5), V(0, 0.9, -0.05), 0.02));          // 뒷바퀴 → 안장
        add(tube(V(0, 0.9, -0.05), V(0, 0.32, 0.02), 0.02));           // 안장 → 크랭크
        add(tube(V(0, 0.9, -0.05), V(0, 0.95, 0.45), 0.02));           // 윗관
        add(tube(V(0, 0.32, 0.02), V(0, 0.95, 0.45), 0.02));           // 아랫관
        add(tube(V(0, 0.95, 0.45), V(0, 0.32, 0.52), 0.02));           // 포크
        add(tube(V(-0.24, 1.0, 0.5), V(0.24, 1.0, 0.5), 0.018));        // 핸들
        add(box(0.12, 0.05, 0.26, 0, 0.92, -0.08, soft));               // 안장
        return {};
      }
      case 'rower': {
        add(box(0.16, 0.08, 1.7, 0, 0.14, 0.2, soft));
        add(box(0.34, 0.05, 0.3, 0, 0.2, -0.1, soft));                  // 시트
        add(box(0.36, 0.3, 0.05, 0, 0.3, 0.95, M));                     // 발판
        const g = add(mesh(new T.CylinderGeometry(0.014, 0.014, 0.44, 10))); g.rotation.z = Math.PI / 2;
        return { update(){ betweenHands(g); g.rotateZ(Math.PI / 2); } };
      }
      case 'rope': {
        const g = new T.Group(); g.position.set(0, 0.95, 0);
        const r = mesh(new T.TorusGeometry(0.95, 0.01, 8, 72)); r.rotation.y = Math.PI / 2; g.add(r); add(g);
        return { update(ms){ g.rotation.x = -(ms / BEAT_MS) * Math.PI * 2; } };   // 계속 돈다
      }
      case 'steps': {
        [0, 1, 2].forEach(i => add(box(0.8, 0.16 * (i + 1), 0.28, 0, 0.08 * (i + 1), 0.28 + i * 0.28, soft)));
        return {};
      }
      case 'wall': {
        const w = add(box(1.4, 2.0, 0.06, 0, 1.0, 0, soft));
        const dir = V(Math.sin(rad(-55)), 0, Math.cos(rad(-55)));
        w.position.copy(dir.multiplyScalar(0.72)); w.position.y = 1.0; w.rotation.y = rad(-55);
        return {};
      }
      case 'water': {
        const w = new T.Mesh(new T.PlaneGeometry(4, 4), new T.MeshStandardMaterial({ color: 0xE1E6EC, transparent: true, opacity: 0.55, roughness: 0.3 }));
        w.rotation.x = -Math.PI / 2; w.position.y = 0.15; w.receiveShadow = true; add(w);
        return {};
      }
    }
    return {};
  }

  /* ---- 무대: 빛 · 그림자 · 카메라 ---- */
  function setup(T, me, P){
    const { canvas } = me;
    const size = Math.max(160, Math.min(canvas.clientWidth || 320, 480));
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const renderer = new T.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setPixelRatio(dpr); renderer.setSize(size, size, false);
    renderer.setClearColor(0x000000, 0);
    renderer.shadowMap.enabled = true; renderer.shadowMap.type = T.PCFSoftShadowMap;
    const scene = new T.Scene();
    scene.add(new T.HemisphereLight(0xffffff, 0x9AA3AD, 1.3));
    const key = new T.DirectionalLight(0xffffff, 2.2); key.position.set(2.5, 4.5, 3); key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024); key.shadow.bias = -0.0004;
    Object.assign(key.shadow.camera, { left: -1.8, right: 1.8, top: 2.6, bottom: -0.6, near: 1, far: 14 });
    scene.add(key);
    const fill = new T.DirectionalLight(0xffffff, 0.7); fill.position.set(-3, 2, -2); scene.add(fill);
    const floor = new T.Mesh(new T.PlaneGeometry(8, 8), new T.ShadowMaterial({ opacity: 0.18 }));
    floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);

    const body = buildBody(T, me.sex);
    scene.add(body.pivot);
    const gear = P.gear ? buildGear(T, P.gear, body, scene) : {};

    const camera = new T.PerspectiveCamera(30, 1, 0.1, 40);
    const cam = { az: 34, el: 15, dist: 4.4, y: 0.9, ...(P.cam || {}) };
    // 움직임 줄이기 설정이면 멈춘 자세. freeze 는 확인용 — 그 자세(0~1)에서 멈춘다.
    const still = me.freeze !== undefined || (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    const placeCamera = ms => {
      const a = rad(cam.az + (still ? 0 : 8 * Math.sin(ms / 1400)));       // 천천히 좌우로 돌며 입체를 보여 준다
      const e = rad(cam.el);
      camera.position.set(Math.sin(a) * Math.cos(e) * cam.dist, cam.y + Math.sin(e) * cam.dist, Math.cos(a) * Math.cos(e) * cam.dist);
      camera.lookAt(0, cam.y, 0);
    };
    const t0 = performance.now();
    const frame = now => {
      if (me.dead) return;
      const ms = now - t0;
      const ph = (ms % BEAT_MS) / BEAT_MS;
      const t = me.freeze !== undefined ? me.freeze : still ? 0.5 : (1 - Math.cos(ph * Math.PI * 2)) / 2;
      applyPose(T, body, lerpPose(P.a, P.b, t));
      if (gear.update) gear.update(ms, t);
      placeCamera(ms);
      renderer.render(scene, camera);
      if (!still || me.freeze !== undefined) me.raf = requestAnimationFrame(frame);
    };
    me.renderer = renderer;
    frame(t0);
  }

  function fallback(canvas){
    const ctx = canvas.getContext && canvas.getContext('2d');
    if (!ctx) return;
    const size = Math.max(160, Math.min(canvas.clientWidth || 320, 480));
    canvas.width = size; canvas.height = size;
    ctx.fillStyle = '#8E949C'; ctx.font = '13px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText('3D 그림을 불러오지 못했어요', size / 2, size / 2);
  }

  /* ---- 돌리기 ---- 캔버스마다 하나씩. stop() 은 전부, stop(canvas) 는 그것만. */
  const actives = new Map();
  function start(canvas, poseId, { sex, freeze } = {}){
    const P = POSES[poseId];
    if (!canvas || !P) return false;
    stop(canvas);
    const me = { canvas, sex, freeze, dead: false, raf: null, renderer: null };
    actives.set(canvas, me);
    loadThree().then(T => { if (!me.dead) setup(T, me, P); })
               .catch(() => { if (!me.dead) fallback(canvas); });
    return true;
  }
  function stop(canvas){
    for (const [c, me] of [...actives]) {
      if (canvas && c !== canvas) continue;
      me.dead = true;
      if (me.raf) cancelAnimationFrame(me.raf);
      if (me.renderer) { me.renderer.dispose(); me.renderer.forceContextLoss(); }
      actives.delete(c);
    }
  }

  return { start, stop, POSES, DIM, BEAT_MS, expand, lerpPose, loadThree };
})();
