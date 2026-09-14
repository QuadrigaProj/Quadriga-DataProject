/* 영상이 없는 동작을 위한 3D 캐릭터 (M5).
 *
 * 고른 종목·기록 종목은 공식 영상이 없다. 그 자리에 회색 마네킹이 실제 사람의
 * 모션캡처로 그 동작을 하는 모습을 띄운다.
 * 몸은 Blender 의 사람 기본형(Human Base Meshes, CC0)을 Mixamo(Adobe) 자동 리깅에
 * 올려 뼈대를 넣은 것이고, 동작은 Mixamo 의 모션캡처를 그 뼈대로 내보낸 것이다.
 * 둘 다 웹용 GLB 로 바꿔 assets/3d 에 두었다 (mannequin-m/-f.glb = 남·여 캐릭터, anim/m|f/*.glb = 동작 하나씩).
 * 파일은 gltfpack(meshopt) 으로 눌러 두어 작다 — 불러올 때 meshopt 디코더가 푼다.
 *
 * 여기서 손보는 것:
 *   - 겉모습: 이음새를 합치고 법선을 다시 계산해 매끈하게, 회색 하나로 칠한다.
 *   - 크기: 파일의 단위가 무엇이든 사람 키(1.75m)로 맞춘다.
 *   - 무릎 푸시업은 푸시업의 다리를 덮어써 만든다 (TWEAKS).
 *   - 모션캡처가 없거나 설명과 다른 22개 동작은 docs/3d-exercise-form-notes.md 의 자세 설명을
 *     세상 기준 방향·손발 목표(IK)로 옮겨 만든다 (PROC).
 *   - 기구가 필요한 동작엔 바벨·덤벨·케틀벨·줄·트레드밀·물을 손과 몸에 붙여 준다 (GEAR).
 *
 * three.js 와 GLTFLoader 는 js/vendor 에 같이 둔다 (import() 는 이 파일 기준 상대경로) —
 * 밖에서 받지 않으니 오프라인 시연에서도 돈다. 처음 필요할 때 한 번만 불러온다.
 */
const MOVE_3D = (() => {
  const BASE = 'assets/3d/';
  const VER = '?v=3';            // 파일을 바꾸면 올린다 — 같은 이름의 옛 파일이 캐시에서 나오지 않게
  const D = Math.PI / 180;

  /* 동작 id → 동작 파일 (anim/<이름>.glb). 같은 파일을 여러 id 가 쓸 수 있다. */
  const CLIPS = {
    'squat': 'squat', 'pushup': 'pushup', 'knee-pushup': 'pushup', 'crunch': 'crunch',
    'burpee': 'burpee', 'barbell-squat': 'barbell-squat', 'dumbbell-curl': 'dumbbell-curl',
    'kettlebell-swing': 'kettlebell-swing', 'jump-rope': 'jump-rope', 'stair': 'stair',
    'shoulder-stretch': 'shoulder-stretch', 'neck-stretch': 'neck-stretch', 'deep-breath': 'deep-breath',
    'treadmill': 'treadmill', 'deadlift': 'deadlift', 'shoulder-press': 'shoulder-press',
    'walk': 'walk', 'run': 'run', 'one-leg': 'one-leg',
  };
  /* 똑같은 동작이 Mixamo 에 없어 비슷한 동작을 손봐서 보여 주는 것 — 화면에 그렇다고 적는다 */
  const APPROX = {
    'knee-pushup': '푸시업 동작의 무릎을 바닥에 붙여 무릎 푸시업으로 손봤어요',
  };
  /* 아직 동작 파일이 없는 것은 기본 자세(idle)만 보여 준다 */
  const GAP_NOTE = '이 동작의 3D 동작은 아직 없어 기본 자세만 보여 줘요';
  const LOADING_NOTE = '3D 동작을 불러오는 중…';
  const FALLBACK_CLIP = 'idle';

  /* ---- 비슷한 동작 손보기 ----
   * base      : 바탕으로 쓸 동작 파일 (없으면 CLIPS 의 것)
   * pitchAtHands : 두 손을 축으로 몸 전체를 기울이기 (도)
   * bones     : 뼈 이름 → { set: [x,y,z] 뼈 기준 각도로 바꿈 | aim: [x,y,z] 세상 기준 이 방향을 가리키게 (함수면 뼈 위치 조회 함수를 받아 방향을 돌려준다),
   *             roll: 그 축으로 비틀기(도), palmTo: 'head' 면 손바닥이 머리 쪽을 보게 비튼다 }
   *             함수면 초 단위 시간을 받아 매 프레임 새로 준다
   * fist      : 손가락을 말아 쥔다 (기구를 잡는 동작) */
  // 무릎 푸시업: 정강이를 바닥에 눕힌다 — 세상 기준으로 '머리 반대쪽(뒤)' 을 향하게 (뼈 기준 각도는 리깅마다 달라 쓰지 않는다)
  const shinBack = p => { const h = p('mixamorig:Hips'), d = p('mixamorig:Head'); return [h.x - d.x, 0, h.z - d.z]; };
  // 허벅지: 엉덩이에서 뒤로 눕혀 무릎이 바닥(관절 높이 0.06)에 닿게 — 엉덩이 높이에 따라 각도가 달라진다
  const thighToFloor = side => p => { const h = p('mixamorig:' + side + 'UpLeg'), b = shinBack(p), bl = Math.hypot(b[0], b[2]) || 1;
    const dy = Math.max(0.05, Math.min(0.42, h.y - 0.06)), dz = Math.sqrt(0.437 * 0.437 - dy * dy); return [b[0] / bl * dz, -dy, b[2] / bl * dz]; };
  const footBack = p => { const b = shinBack(p), l = Math.hypot(b[0], b[2]) || 1; return [b[0] / l * 0.98, 0.21, b[2] / l * 0.98]; };   // 발등을 바닥에 (발끝만 12° 들어 발바닥 굽힘 50° 안)
  const TWEAKS = {
    'knee-pushup': { bones: { 'mixamorig:LeftUpLeg': { aim: thighToFloor('Left') }, 'mixamorig:RightUpLeg': { aim: thighToFloor('Right') },
                              'mixamorig:LeftLeg': { aim: shinBack }, 'mixamorig:RightLeg': { aim: shinBack }, 'mixamorig:LeftFoot': { aim: footBack }, 'mixamorig:RightFoot': { aim: footBack } } },
  };

  /* ---- 학습한 자세로 만든 동작 (PROC) ----
   * 모션캡처가 없거나 설명과 다른 동작은 docs/3d-exercise-form-notes.md 의 자세 설명을 그대로 자세로 옮겼다.
   * 한 항목: { base: 바탕 동작 파일(정하지 않은 뼈·손가락은 이것을 따른다), still: 바탕 동작을 첫 프레임에 멈춘다(손이 꼼지락거리지 않게), period: 한 회(초), gear, fist,
   *            pose(u, C): 0~1 진행도와 조회 도우미 C 를 받아 그 순간의 자세를 돌려준다.
   *              C.pos(뼈) → 세상 위치 Vector3, C.rest(뼈) → T 자세에서 그 뼈가 뻗는 방향 [x,y,z] }
   * 자세: { root: { pos:[x,y,z] 엉덩이 세상 위치 | dpos: 바탕에서 옮길 양, up:[..] 척추 방향, front:[..] 배가 보는 방향 },
   *         bones: { 뼈: [x,y,z] 세상 방향 | 'rest' | { aim, front, roll, palmTo } | { ik:[x,y,z] 손·발이 갈 자리, bend:[x,y,z] 팔꿈치·무릎이 굽는 쪽, palmTo } } }
   *   aim·ik 는 함수여도 된다 — 뼈 위치 조회 함수 p 를 받아 그 순간 계산한다 (mirror 로 뒤집으면 반대쪽 뼈를 보게 된다)
   * 세상 기준: +Y 위, +Z 앞(얼굴 쪽), +X 캐릭터의 왼쪽. 길이는 m (키 1.75m: 서면 엉덩이 1.02, 허벅지 0.44, 정강이 0.47, 위팔 0.3, 아래팔 0.2).
   * 이 리깅의 발목 관절은 바닥에서 0.09 에 있고 발 뼈(발목→발가락 뿌리 0.15)는 평평한 발일 때 N(0,-0.53,0.85) 로 내려간다(정강이와 60°) — 발을 바닥에 둘 땐 발목을 0.09 에.
   * 고관절(UpLeg)은 Hips 뼈보다 0.047 아래(골반 '아래' 쪽)에 있다 — 엉덩이 높이를 정할 때 그만큼 더한다. */
  const N = (x, y, z) => { const l = Math.hypot(x, y, z) || 1; return [x / l, y / l, z / l]; };
  const mix = (a, b, k) => Array.isArray(a) ? a.map((v, i) => v + (b[i] - v) * k) : a + (b - a) * k;
  const sstep = x => { x = Math.max(0, Math.min(1, x)); return x * x * (3 - 2 * x); };
  const ramp = (u, a, b) => sstep((u - a) / (b - a));                     // a 에서 b 사이에 0 → 1
  const hold = (u, a, b, c, d) => ramp(u, a, b) - ramp(u, c, d);          // a~b 올라가 b~c 머물고 c~d 내려온다
  const alt = u => 1 - hold(u, 0.45, 0.55, 0.95, 1);                        // 앞 절반 1, 뒤 절반 0 — 좌우 번갈아 할 때
  const add = (p, d) => [p.x + d[0], p.y + d[1], p.z + d[2]];
  const L = 'mixamorig:Left', R = 'mixamorig:Right';
  const spineAll = (dir, head = dir, front) => {
    const e = front ? { aim: dir, front } : dir, h = front ? { aim: head, front } : head;
    return { 'mixamorig:Spine': e, 'mixamorig:Spine1': e, 'mixamorig:Spine2': e, 'mixamorig:Neck': h, 'mixamorig:Head': h };
  };
  // ik 목표는 함수로 줄 수 있다 — 몸통과 다른 팔이 자리 잡은 뒤(2단계)에 계산된다
  const handsOnHips = (C, y = 0.12, x = 0.18) => ({ [L + 'Arm']: { ik: () => add(C.pos('mixamorig:Hips'), [x, y, 0.03]), bend: [1, -0.2, -0.7] },      // 골반뼈 위(허리)에 — 고관절 높이면 허벅지를 뚫는다
                                                [R + 'Arm']: { ik: () => add(C.pos('mixamorig:Hips'), [-x, y, 0.03]), bend: [-1, -0.2, -0.7] } });
  const STAND = { pos: [0, 1.03, 0], up: [0, 1, 0], front: [0, 0, 1] };
  const LIE = { pos: [0, 0.11, 0], up: [0, 0, -1], front: [0, 1, 0] };     // 바로 누움: 머리는 -Z 쪽, 배는 위
  const both = (up, leg, foot) => ({ [L + 'UpLeg']: up, [L + 'Leg']: leg, [L + 'Foot']: foot, [R + 'UpLeg']: up, [R + 'Leg']: leg, [R + 'Foot']: foot });
  const FLAT = N(0, -0.53, 0.85);                                                    // 평평하게 디딘 발 뼈의 방향
  const kneesUp = both(N(0, 0.85, 0.53), N(0, -0.84, 0.54), FLAT);                   // 누워 무릎 세우기, 발은 바닥에 (발목 0.09)
  // 발이 정강이를 따라가게: 지금 정강이 방향에서 발등 쪽으로 deg 만큼 돌린 방향 (60° 가 중립, 작으면 발끝을 편 것). left 는 캐릭터의 왼쪽 방향
  const footFollow = (side, left = [1, 0, 0], deg = 60) => p => {
    const k = p(side + 'Leg'), a = p(side + 'Foot'); const sh = N(a.x - k.x, a.y - k.y, a.z - k.z);
    const fr = N(sh[1] * left[2] - sh[2] * left[1], sh[2] * left[0] - sh[0] * left[2], sh[0] * left[1] - sh[1] * left[0]);   // 정강이 앞쪽 = 정강이 × 왼쪽
    const c = Math.cos(deg * D), s = Math.sin(deg * D);
    return [sh[0] * c + fr[0] * s, sh[1] * c + fr[1] * s, sh[2] * c + fr[2] * s];
  };
  const swapSide = n => (n.includes('Left') ? n.replace('Left', 'Right') : n.replace('Right', 'Left'));
  const mirrorLookup = p => n => { const q = p(swapSide(n)); return { x: -q.x, y: q.y, z: q.z }; };   // 거울 세상에서 뼈 위치 조회
  const flipX = v => Array.isArray(v) ? [-v[0], v[1], v[2]]
    : (v && typeof v === 'object') ? { ...v, aim: v.aim && (typeof v.aim === 'function' ? (p => flipX(v.aim(mirrorLookup(p)))) : flipX(v.aim)), front: v.front && flipX(v.front), ik: v.ik && (typeof v.ik === 'function' ? (p => flipX(v.ik(mirrorLookup(p)))) : flipX(v.ik)), bend: v.bend && flipX(v.bend), palmTo: Array.isArray(v.palmTo) ? flipX(v.palmTo) : v.palmTo, roll: v.roll && -v.roll } : v;
  const mirror = t => { const o = {}; for (const [k, v] of Object.entries(t)) o[swapSide(k)] = flipX(v); return o; };
  const blend = (a, b, k) => { const o = {}; for (const n of new Set([...Object.keys(a), ...Object.keys(b)])) { const x = a[n], y = b[n]; o[n] = (x === undefined) ? y : (y === undefined) ? x : mixHow(x, y, k); } return o; };
  const asObj = v => Array.isArray(v) ? { aim: v } : v;                     // 방향 배열과 IK 를 섞을 땐 배열을 { aim } 로
  const mixHow = (x, y, k) => {
    if (Array.isArray(x) && Array.isArray(y)) return N(...mix(x, y, k));
    if (x && y && typeof x === 'object' && typeof y === 'object') {
      x = asObj(x); y = asObj(y);
      const o = { ...(k < 0.5 ? x : y) };
      for (const f of ['aim', 'front', 'bend']) if (Array.isArray(x[f]) && Array.isArray(y[f])) o[f] = N(...mix(x[f], y[f], k));
      if (x.ik && y.ik) { const fx = typeof x.ik === 'function' ? x.ik : () => x.ik, fy = typeof y.ik === 'function' ? y.ik : () => y.ik; o.ik = p => mix(fx(p), fy(p), k); }
      if (typeof x.roll === 'number' && typeof y.roll === 'number') o.roll = mix(x.roll, y.roll, k);
      return o;
    }
    return k < 0.5 ? x : y;
  };
  const PROC_NOTE = '자세 설명을 보고 만든 3D 동작이에요';
  // 기구 자리 — 자세와 기구가 같은 숫자를 쓴다
  const BIKE = { crank: [0, 0.28, 0.12], r: 0.17, x: 0.14, bar: [0.2, 1.02, 0.5] };
  const ROWER = { foot: [0.07, 0.27, 0.72], fly: [0, 0.5, 1.15], seatY: 0.37 };
  const LEGPRESS = { dir: N(0.6, 0.8, 0) };                                  // 발판 쪽 (앞·위 53°)
  const WALL_X = 0.56;                                                      // 종아리 스트레칭의 벽 (캐릭터 왼쪽, +X)

  const PROC = {
    // 플랭크(팔꿈치 플랭크): 팔꿈치는 어깨 바로 아래 바닥에, 아래팔은 나란히 앞으로 손바닥 아래. 머리부터 뒤꿈치까지 한 직선(어깨 높이는
    // 위팔 길이만큼, 발목 0.1 — 10~13° 기울기), 발끝을 세워 발볼로 딛는다. 숨 쉬는 만큼만 움직인다. 모션캡처 'Plank' 는 팔을 편 하이 플랭크라 쓰지 않는다.
    'plank': { base: 'lying', period: 4, still: true, pose: (u, C) => {
      const S = C.pos(L + 'Arm'), E = C.pos(L + 'ForeArm'), l1 = Math.hypot(S.x - E.x, S.y - E.y, S.z - E.z);   // 위팔 길이 (남·여가 다르다)
      const hy = 0.006 + l1, sn = Math.max(0.05, Math.min(0.35, (hy - 0.1) / 0.9)), cs = Math.sqrt(1 - sn * sn);   // 엉덩이 높이(팔꿈치가 바닥 위 6cm 에 오게) → 몸 기울기
      const up = [0, sn, -cs], down = [0, -sn, cs], front = [0, -1, 0];
      const arm = side => ({ ik: () => { const P = C.pos(side + 'Arm'); return [P.x, 0.045, P.z - 0.2]; }, bend: [0, -1, 0.2], palmTo: [0, -1, 0] });   // 손은 어깨 앞 바닥에 — 팔꿈치가 어깨 아래에 온다
      return { root: { pos: [0, hy + 0.005 * Math.sin(u * Math.PI * 2), 0], up, front },
        bones: { ...spineAll(up, N(0, sn - 0.1, -cs), front), [L + 'Arm']: arm(L), [R + 'Arm']: arm(R),
          ...both(down, down, N(0, -0.62, 0.78)) } };                                                         // 발끝 세움 (발등 굽힘 30°쯤)
    } },
    // 자유형: 엎드려 뜬 채 팔을 번갈아 — 물속에서 팔꿈치를 높게 두고 손으로 몸 아래를 지나 엉덩이까지 밀고(캐치→풀→푸시),
    // 물 밖으로 팔꿈치를 높게 들어 앞으로 되돌려 다시 넣는다. 되돌리는 팔 쪽 어깨가 올라오게 몸통이 40° 굴러가고, 숨은 왼팔을 되돌릴 때 왼쪽으로.
    // 다리는 뻗은 채 엉덩이에서 작게 찬다(발끝은 뻗고). 모션캡처 'Swimming' 은 평영처럼 보여 쓰지 않는다. (머리는 -Z 쪽, 물은 y 0.15)
    'swim': { base: 'lying', period: 2.4, gear: 'water', still: true, pose: (u, C) => {
      const r = -40 * D * Math.sin(u * Math.PI * 2);                                                                    // 굴림: 왼팔이 물 밖일 때(u 0.5~1) 왼쪽 어깨가 올라온다
      const upv = [Math.sin(r), Math.cos(r), 0], leftv = [-Math.cos(r), Math.sin(r), 0], front = [-Math.sin(r), -Math.cos(r), 0];   // 엎드리면 캐릭터의 왼쪽은 -X
      const PATH = [[0, 0.1, -0.05, -0.5], [0.15, 0.1, -0.25, -0.35], [0.35, 0.05, -0.32, 0], [0.5, 0.15, -0.15, 0.35], [0.62, 0.3, 0.12, 0.3], [0.8, 0.32, 0.15, -0.15], [1, 0.1, -0.05, -0.5]];   // [진행, 바깥, 위, 뒤] 어깨 기준, 세상 축 (엎드리면 왼쪽은 -X)
      const arm = (side, ph, sgn) => {
        ph = ((ph % 1) + 1) % 1; let i = 0; while (PATH[i + 1][0] < ph) i++;
        const a = PATH[i], b = PATH[i + 1], t = sstep((ph - a[0]) / (b[0] - a[0]));
        const x = mix(a[1], b[1], t) * sgn, y = mix(a[2], b[2], t), z = mix(a[3], b[3], t);
        const w = hold(ph, 0.48, 0.58, 0.95, 1);                                                                       // 물 밖(되돌리기)이면 1
        return { ik: () => { const S = C.pos(side + 'Arm'); return [S.x + x, S.y + y, S.z + z]; },
          bend: [sgn, 0.8, 0],                                                                                         // 팔꿈치는 바깥·위(높게)
          palmTo: N(...mix([0, 0, 1], [0, -1, 0], w)) };                                                               // 물속에선 손바닥이 뒤(발 쪽)를 밀고, 물 밖에선 아래를 본다
      };
      const k = Math.sin(u * Math.PI * 4);                                                                              // 발차기 — 한 바퀴에 두 번, 좌우 번갈아
      const leg = (side, sgn) => { const d = Math.max(0, k * sgn); return { [side + 'UpLeg']: N(0, -0.08 - 0.1 * k * sgn, 1), [side + 'Leg']: N(0, -0.05 - 0.25 * d, 1), [side + 'Foot']: { aim: footFollow(side, leftv, 20) } }; };
      const br = hold(u, 0.6, 0.7, 0.85, 0.95), headFront = N(...mix(front, leftv, br));                                 // 숨: 왼팔을 되돌릴 때 얼굴을 왼쪽으로
      return { root: { pos: [0, 0.17, 0], up: [0, 0, -1], front },
        bones: { ...spineAll([0, 0, -1], [0, 0, -1], front), 'mixamorig:Neck': { aim: [0, 0, -1], front: N(...mix(front, headFront, 0.5)) }, 'mixamorig:Head': { aim: N(0, 0.05, -1), front: headFront },
          [L + 'Arm']: arm(L, u, -1), [R + 'Arm']: arm(R, u + 0.5, 1), ...leg(L, 1), ...leg(R, -1) } };                 // 왼팔의 바깥은 -X
    } },
    // 런지: 한 발 앞으로, 양 무릎 90°, 앞 무릎은 발목 위, 뒷무릎은 엉덩이 아래로, 상체는 곧게. 손은 허리
    'lunge': { base: 'idle', period: 3.2, pose: (u, C) => {
      const k = hold(u, 0.1, 0.45, 0.55, 0.9);
      return { root: { pos: mix([0, 1.0, 0], [0, 0.6, 0.12], k), up: [0, 1, 0], front: [0, 0, 1] },
        bones: { ...spineAll([0, 1, 0]), ...handsOnHips(C),
          [L + 'UpLeg']: { ik: mix([0.094, 0.09, 0], [0.094, 0.09, 0.55], k), bend: [0, 0.68, 0.73] }, [L + 'Foot']: FLAT,                    // 앞: 발은 바닥에 고정, 무릎은 발목 위로 앞·위
          [R + 'UpLeg']: { ik: mix([-0.094, 0.09, 0], [-0.094, 0.15, -0.45], k), bend: [0, -0.8, 0.6] }, [R + 'Foot']: mix(FLAT, N(0, -1, 0.05), k) } };   // 뒤: 발을 세워 발끝으로 딛고 무릎은 엉덩이 아래로
    } },
    // 브리지: 누워 무릎 세우고, 뒤꿈치로 밀어 무릎–엉덩이–어깨가 한 직선. 위에서 1~2초 조인다
    'bridge': { base: 'lying', period: 3.6, still: true, pose: u => {
      const k = hold(u, 0.1, 0.4, 0.58, 0.9);
      const up = N(...mix([0, 0, -1], [0, -0.42, -0.91], k)), front = N(...mix([0, 1, 0], [0, 0.91, -0.42], k));   // 어깨는 바닥에 둔 채 엉덩이만 올라간다
      return { root: { pos: mix([0, 0.11, 0], [0, 0.3, -0.02], k), up, front },
        bones: { ...spineAll(up, [0, 0.05, -1]),
          [L + 'UpLeg']: { ik: [0.094, 0.09, 0.4], bend: [0, 1, 0] }, [L + 'Foot']: FLAT,                                  // 발은 엉덩이 가까이 바닥에 고정 — 위에선 무릎이 발목 위(정강이 수직)
          [R + 'UpLeg']: { ik: [-0.094, 0.09, 0.4], bend: [0, 1, 0] }, [R + 'Foot']: FLAT,
          [L + 'Arm']: N(0.35, -0.15, 0.92), [L + 'ForeArm']: { aim: N(0.3, -0.1, 0.95), palmTo: [0, -1, 0] }, [L + 'Hand']: N(0.3, -0.1, 0.95),   // 팔은 옆에 뻗어 손바닥 바닥
          [R + 'Arm']: N(-0.35, -0.15, 0.92), [R + 'ForeArm']: { aim: N(-0.3, -0.1, 0.95), palmTo: [0, -1, 0] }, [R + 'Hand']: N(-0.3, -0.1, 0.95) } };
    } },
    // 데드버그: 누워 팔은 천장, 엉덩이·무릎 90°. 한 팔은 머리 위로, 반대 다리는 앞으로 천천히 — 허리는 바닥에
    'dead-bug': { base: 'lying', period: 5.2, still: true, pose: u => {
      const side = u < 0.5 ? 0 : 1, a = hold(u - side * 0.5, 0.04, 0.24, 0.3, 0.48);
      const neutral = { ...both([0, 1, 0.08], [0, 0.05, 1], N(0, 0.85, 0.53)), [L + 'Arm']: [0.05, 1, 0], [L + 'ForeArm']: [0, 1, 0], [R + 'Arm']: [-0.05, 1, 0], [R + 'ForeArm']: [0, 1, 0] };
      const moved = { [R + 'Arm']: N(-0.15, 0.2, -0.97), [R + 'ForeArm']: N(-0.1, 0.1, -0.99), [L + 'UpLeg']: N(0, 0.35, 0.94), [L + 'Leg']: N(0, 0.2, 0.98), [L + 'Foot']: N(0, 0.95, 0.32) };
      return { root: LIE, bones: { ...spineAll([0, 0, -1]), ...blend(neutral, side ? mirror(moved) : moved, a) } };
    } },
    // 크런치: 머리와 어깨만 말아 올린다 — 허리는 바닥에, 손은 뒤통수(당기지 않는다), 턱은 살짝 당긴 채
    'crunch': { base: 'lying', period: 2.6, still: true, pose: (u, C) => {
      const c = hold(u, 0.1, 0.4, 0.5, 0.85);
      return { root: LIE, bones: { ...kneesUp,
        'mixamorig:Spine': N(...mix([0, 0, -1], [0, 0.12, -0.99], c)), 'mixamorig:Spine1': N(...mix([0, 0, -1], [0, 0.42, -0.9], c)), 'mixamorig:Spine2': N(...mix([0, 0, -1], [0, 0.7, -0.72], c)),
        'mixamorig:Neck': N(...mix([0, 0.05, -1], [0, 0.8, -0.6], c)), 'mixamorig:Head': N(...mix([0, 0.05, -1], [0, 0.85, -0.53], c)),
        [L + 'Arm']: { ik: () => add(C.pos('mixamorig:Head'), [0.11, 0.02, -0.1]), bend: [1, 0.4, 0] }, [R + 'Arm']: { ik: () => add(C.pos('mixamorig:Head'), [-0.11, 0.02, -0.1]), bend: [-1, 0.4, 0] } } };
    } },
    // 데드리프트: 바를 발 가운데 위에, 엉덩이를 뒤로 빼 힌지, 등은 평평, 팔은 곧게 늘어뜨려 잡고 그냥 똑바로 선다
    'deadlift': { base: 'idle', period: 3.4, gear: 'barbell', fist: true, pose: u => {
      const k = hold(u, 0.05, 0.42, 0.52, 0.9);
      const up = N(...mix([0, 1, 0], [0, 0.6, 0.8], k)), front = N(...mix([0, 0, 1], [0, -0.8, 0.6], k));
      return { root: { pos: mix([0, 1.02, 0], [0, 0.88, -0.1], k), up, front },
        bones: { ...spineAll(up, N(...mix([0, 1, 0], [0, 0.8, 0.6], k))),
          ...both(N(...mix([0, -1, 0], [0, -0.64, 0.77], k)), N(...mix([0, -1, 0], [0, -1, -0.05], k)), FLAT),
          [L + 'Arm']: N(0.06, -0.97, 0.24), [L + 'ForeArm']: { aim: N(0.03, -0.97, 0.24), palmTo: [0, 0, -1] },      // 바가 허벅지 앞에 닿는 자리
          [R + 'Arm']: N(-0.06, -0.97, 0.24), [R + 'ForeArm']: { aim: N(-0.03, -0.97, 0.24), palmTo: [0, 0, -1] } } };
    } },
    // 숄더프레스: 덤벨을 어깨 높이에서, 팔꿈치는 살짝 앞(45°), 손바닥은 머리 쪽, 어깨 위로 곧장 밀어 팔꿈치를 편다. 갈비뼈는 내린다
    'shoulder-press': { base: 'idle', period: 2.4, gear: 'dumbbells', fist: true, pose: u => {
      const p = hold(u, 0.05, 0.42, 0.5, 0.92);
      return { bones: { ...spineAll([0, 1, 0]),
        [L + 'Arm']: N(...mix([0.72, -0.35, 0.55], [0.1, 1, 0.02], p)), [L + 'ForeArm']: { aim: N(...mix([0.05, 0.99, 0.08], [0.02, 1, 0], p)), palmTo: 'head' },
        [R + 'Arm']: N(...mix([-0.72, -0.35, 0.55], [-0.1, 1, 0.02], p)), [R + 'ForeArm']: { aim: N(...mix([-0.05, 0.99, 0.08], [-0.02, 1, 0], p)), palmTo: 'head' } } };
    } },
    // 한 발 서기: 손은 허리, 한 발을 바닥에서 든다(무릎 살짝 굽힘), 딛는 무릎은 잠그지 않는다, 시선은 앞
    'one-leg': { base: 'idle', period: 6, pose: (u, C) => ({
      root: { dpos: [-0.04 + 0.01 * Math.sin(u * Math.PI * 4), 0, 0] },
      bones: { ...spineAll([0, 1, 0]), ...handsOnHips(C), [L + 'UpLeg']: N(0.02, -0.94, 0.34), [L + 'Leg']: N(0, -0.8, -0.6), [L + 'Foot']: N(0, -0.7, 0.7) } }) },
    // 복식 호흡: 한 손은 가슴, 한 손은 배 — 들이마실 때 배가 부푼다 (바탕 동작이 숨을 쉰다)
    'deep-breath': { base: 'deep-breath', period: 6, pose: (u, C) => ({
      bones: { [R + 'Arm']: { ik: () => add(C.pos('mixamorig:Spine2'), [-0.04, 0.08, 0.2]), bend: [-0.9, -0.2, -0.4], palmTo: [0, 0, -1] },     // 가슴 위
               [L + 'Arm']: { ik: () => add(C.pos('mixamorig:Spine'), [0.04, -0.05, 0.19]), bend: [0.9, -0.2, -0.4], palmTo: [0, 0, -1] } } }) },   // 배 위
    // 어깨 스트레칭(크로스 바디): 한 팔을 어깨 높이로 가슴 앞을 가로지르고 반대 손으로 팔꿈치 위를 가볍게 당긴다. 어깨는 내린 채. 좌우 번갈아
    'shoulder-stretch': { base: 'idle', period: 10, pose: (u, C) => {
      const wL = hold(u, 0.02, 0.1, 0.42, 0.48), wR = hold(u, 0.52, 0.6, 0.92, 0.98);                                // 앞 절반은 왼팔, 뒤 절반은 오른팔 — 사이엔 두 팔 다 내린다
      const hang = { [L + 'Arm']: { ik: () => add(C.pos('mixamorig:Hips'), [0.26, -0.2, 0.1]), bend: [1, 0, -0.3] }, [R + 'Arm']: { ik: () => add(C.pos('mixamorig:Hips'), [-0.26, -0.2, 0.1]), bend: [-1, 0, -0.3] } };   // 쉬는 손은 엉덩이 옆·앞 (가슴으로 오갈 때 허벅지를 지나지 않게)
      const left = { [L + 'Arm']: { ik: () => add(C.pos(R + 'Arm'), [-0.03, -0.07, 0.28]), bend: [0, -0.7, 0.7] },              // 왼팔: 팔꿈치를 살짝 굽혀 가슴 앞을 가로질러 오른 어깨 앞까지
                     [R + 'Arm']: { ik: () => add(C.pos(L + 'ForeArm'), [0.02, 0.02, 0.08]), bend: [-0.5, -0.85, 0.2] } };   // 오른손은 왼 팔꿈치 위를 잡는다 (팔꿈치는 제 쪽으로)
      const right = { [R + 'Arm']: { ik: () => add(C.pos(L + 'Arm'), [0.03, -0.07, 0.28]), bend: [0, -0.7, 0.7] },
                      [L + 'Arm']: { ik: () => add(C.pos(R + 'ForeArm'), [-0.02, 0.02, 0.08]), bend: [0.5, -0.85, 0.2] } };
      return { bones: { ...spineAll([0, 1, 0]), ...blend(blend(hang, left, wL), right, wR) } };
    } },
    // 목 스트레칭: 귀를 같은 쪽 어깨로 기울이고, 그쪽 손을 머리 반대편에 얹어 무게만 살짝 (누르지 않는다). 좌우 번갈아
    'neck-stretch': { base: 'idle', period: 10, pose: (u, C) => {
      const s = alt(u), upL = 1 - hold(u, 0.44, 0.5, 0.94, 1), upR = hold(u, 0.5, 0.56, 0.88, 0.94);              // 내려오는 손이 먼저, 올라가는 손은 그 다음 — 두 손이 가슴 앞에서 만나지 않게
      const down = side => ({ ik: () => add(C.pos('mixamorig:Hips'), [side === L ? 0.14 : -0.14, 0.05, 0.25]), bend: [side === L ? 0.9 : -0.9, -0.4, -0.2] });   // 쉬는 손은 배 앞에 (머리와 오갈 때 가슴 앞을 지난다)
      const onHead = side => ({ ik: () => add(C.pos('mixamorig:Head'), [side === L ? -0.1 : 0.1, 0.15, 0.06]), bend: [side === L ? 0.7 : -0.7, 0.6, 0.4] });
      const right = { 'mixamorig:Neck': N(-0.15, 0.99, 0), 'mixamorig:Head': N(-0.5, 0.87, 0) };
      const left = { 'mixamorig:Neck': N(0.15, 0.99, 0), 'mixamorig:Head': N(0.5, 0.87, 0) };
      return { bones: { 'mixamorig:Spine': [0, 1, 0], 'mixamorig:Spine1': [0, 1, 0], 'mixamorig:Spine2': [0, 1, 0], ...blend(left, right, s),
        ...blend({ [L + 'Arm']: down(L) }, { [L + 'Arm']: onHead(L) }, upL), ...blend({ [R + 'Arm']: down(R) }, { [R + 'Arm']: onHead(R) }, upR) } };
    } },
    // 고관절 스트레칭(반무릎): 뒷무릎은 엉덩이 아래, 상체는 곧게, 손은 허리. 골반을 말고 2~3cm 앞으로 옮긴다
    'hip-stretch': { base: 'kneel', period: 6, pose: (u, C) => ({
      root: { pos: [0, 0.55, 0.04 * hold(u, 0.15, 0.4, 0.6, 0.85)], up: [0, 1, 0], front: [0, 0, 1] },
      bones: { ...spineAll([0, 1, 0]), ...handsOnHips(C, 0.16, 0.21),
        [L + 'UpLeg']: N(0, 0.04, 1), [L + 'Leg']: N(0, -0.92, 0.39), [L + 'Foot']: FLAT,                           // 앞다리: 고관절·무릎 90° 가까이, 발은 평평
        [R + 'UpLeg']: N(0, -0.99, -0.15), [R + 'Leg']: [0, 0, -1], [R + 'Foot']: N(0, -0.25, -0.97) } }) },      // 뒷다리: 무릎은 바닥, 정강이는 뒤로 눕고 발등이 바닥
    // 햄스트링 스트레칭(선 자세): 한 발 앞에 뒤꿈치, 발끝 위로, 다리는 편 채. 엉덩이를 빼며 등을 평평하게 숙인다
    'hamstring-stretch': { base: 'idle', period: 6, pose: u => {
      const h = hold(u, 0.1, 0.35, 0.65, 0.9);
      const up = N(...mix([0, 0.7, 0.72], [0, 0.5, 0.87], h)), front = N(...mix([0, -0.72, 0.7], [0, -0.87, 0.5], h));
      return { root: { pos: [0, 0.97, -0.1], up, front },
        bones: { ...spineAll(up, N(...mix([0, 0.85, 0.53], [0, 0.72, 0.7], h))),
          [L + 'UpLeg']: N(0, -0.92, 0.39), [L + 'Leg']: N(0, -0.92, 0.39), [L + 'Foot']: N(0, -0.2, 0.98),           // 앞다리 곧게, 뒤꿈치 바닥에 발끝 위로
          [R + 'UpLeg']: N(0, -0.98, -0.2), [R + 'Leg']: N(0, -0.86, 0.51), [R + 'Foot']: FLAT,                       // 뒷다리는 살짝 굽혀 엉덩이 아래
          [L + 'Arm']: N(0.06, -0.85, 0.5), [L + 'ForeArm']: N(...mix([0, -0.8, 0.6], [0, -0.74, 0.67], h)),
          [R + 'Arm']: N(-0.06, -0.85, 0.5), [R + 'ForeArm']: N(...mix([0, -0.8, 0.6], [0, -0.74, 0.67], h)) } };
    } },
    // 종아리 스트레칭(벽): 벽에 손을 대고 한 발을 뒤로. 뒷다리는 곧게, 뒤꿈치는 바닥에. 앞무릎을 굽히며 몸을 앞으로 기울인다
    // (옆에서 보이게 벽은 +X 쪽에 두고 그쪽을 본다)
    'calf-stretch': { base: 'idle', period: 6, gear: 'wall', pose: u => {
      const c = hold(u, 0.1, 0.4, 0.6, 0.9), up = N(0.34, 0.94, 0), flatX = N(0.85, -0.53, 0);                    // 벽(+X) 쪽을 보고 평평하게 디딘 발
      return { root: { pos: [mix(-0.1, -0.16, c), 0.95, 0], up, front: N(0.94, -0.34, 0) },
        bones: { ...spineAll(up, N(0.2, 1, 0), N(0.94, -0.34, 0)),
          [L + 'Arm']: N(0.98, -0.15, 0.12), [L + 'ForeArm']: { aim: N(1, -0.05, 0.05), palmTo: [1, 0, 0] },
          [R + 'Arm']: N(0.98, -0.15, -0.12), [R + 'ForeArm']: { aim: N(1, -0.05, -0.05), palmTo: [1, 0, 0] },
          [L + 'UpLeg']: N(-0.42, -0.91, 0), [L + 'Leg']: N(-0.42, -0.91, 0), [L + 'Foot']: flatX,                    // 뒷다리 곧게 25°, 뒤꿈치 바닥 (발등 굽힘 25°)
          [R + 'UpLeg']: N(0.62, -0.79, 0), [R + 'Leg']: [0, -1, 0], [R + 'Foot']: flatX } };                          // 앞무릎은 발목 위
    } },
    // 누워 허리 비틀기: 팔은 T 자, 한 무릎을 굽혀 반대쪽으로 넘긴다. 양 어깨는 바닥에, 머리는 반대쪽. 좌우 번갈아
    'twist': { base: 'lying', period: 12, still: true, pose: (u, C) => {
      const sideL = u < 0.5, s1 = sideL ? u : u - 0.5;                                                              // 앞 절반은 왼쪽으로, 뒤 절반은 오른쪽으로 — 가운데(무릎 세움)를 지나서
      const wB = hold(s1, 0.0, 0.06, 0.44, 0.5), wT = hold(s1, 0.06, 0.18, 0.38, 0.46);                             // 아래 다리를 먼저 펴고(wB) 위 다리를 넘긴다(wT) — 두 다리가 서로 지나가지 않게
      const arms = { [L + 'Arm']: [1, 0, 0], [L + 'ForeArm']: [1, 0, 0], [R + 'Arm']: [-1, 0, 0], [R + 'ForeArm']: [-1, 0, 0] };
      const center = { ...arms, ...kneesUp, 'mixamorig:Head': { aim: [0, 0.05, -1], front: [0, 1, 0] } };
      const left = { ...arms, [L + 'UpLeg']: N(-0.61, 0.61, 0.51), [L + 'Leg']: N(-0.6, -0.62, 0.5), [L + 'Foot']: { aim: footFollow(L, [1, 0, 0], 55) },   // 위 다리: 무릎을 들어 아래 다리 위를 넘긴다
        [R + 'UpLeg']: [0, 0, 1], [R + 'Leg']: [0, 0, 1], [R + 'Foot']: N(0, 0.7, 0.7),
        [R + 'Arm']: { ik: p => add(p(L + 'Leg'), [0, 0.13, 0]), bend: [0, 1, 0] },                                       // 손은 무릎 살 위에 (거울에선 반대 무릎)
        'mixamorig:Head': { aim: [0, 0.05, -1], front: N(0.7, 0.7, 0) } };
      const P = sideL ? left : mirror(left), top = sideL ? L : R, bottom = sideL ? R : L;
      const legs = side => [side + 'UpLeg', side + 'Leg', side + 'Foot'];
      const sub = (t, keys, not = false) => Object.fromEntries(Object.entries(t).filter(([k]) => keys.includes(k) !== not));
      const other = [...legs(top), ...legs(bottom)];
      return { root: { ...LIE, front: N((sideL ? -0.5 : 0.5) * wT, 0.87, 0) },                                        // 골반도 30° 같이 돈다
        bones: { ...spineAll([0, 0, -1], [0, 0.05, -1], [0, 1, 0]),                                                   // 어깨는 바닥에 — 척추 앞은 계속 위를 본다
          ...blend(sub(center, legs(bottom)), sub(P, legs(bottom)), wB), ...blend(sub(center, legs(top)), sub(P, legs(top)), wT), ...blend(sub(center, other, true), sub(P, other, true), wT) } };
    } },
    // 사이드 플랭크: 팔꿈치는 어깨 바로 아래, 발을 포개고 엉덩이를 들어 머리부터 발까지 한 직선. 윗손은 천장
    // (왼쪽으로 누워 배가 +X 를 본다 — 카메라 쪽. 왼팔로 받친다)
    'side-plank': { base: 'plank', period: 5, pose: u => {
      const up = N(0, 0.31, -0.95), front = [1, 0, 0];                                                              // 머리 쪽이 18° 올라간 한 직선 — 아래 어깨가 팔꿈치 위에 온다
      return { root: { pos: [0, 0.42 + 0.01 * Math.sin(u * Math.PI * 2), 0], up, front },
        bones: { ...spineAll(up, up, front), ...both(N(0, -0.31, 0.95), N(0, -0.31, 0.95), N(0.8, -0.15, 0.58)),   // 포갠 발은 앞(+X)을 본다
          [L + 'Arm']: N(0.3, -0.95, 0), [L + 'ForeArm']: { aim: [1, 0, 0], palmTo: [0, -1, 0] }, [L + 'Hand']: [1, 0, 0],   // 위팔은 바닥으로, 아래팔·손은 앞으로 곧게 눕힌다
          [R + 'Arm']: N(-0.1, 0.99, 0), [R + 'ForeArm']: N(-0.05, 1, 0), [R + 'Hand']: N(-0.05, 1, 0) } };
    } },
    // 벤치프레스: 발은 바닥에, 그립은 아래팔이 수직이 되는 너비, 바는 어깨 위에서 가슴 아래쪽으로 대각선, 팔꿈치 45~60°
    'bench-press': { base: 'lying', period: 2.8, gear: 'bench', fist: true, still: true, pose: u => {
      const p = hold(u, 0.05, 0.4, 0.5, 0.95);
      return { root: { pos: [0, 0.57, 0], up: [0, 0, -1], front: [0, 1, 0] },
        bones: { ...spineAll([0, 0, -1], [0, 0.05, -1]),
          [L + 'UpLeg']: N(0.49, -0.17, 0.85), [L + 'Leg']: N(0, -0.87, -0.49), [L + 'Foot']: N(0.3, -0.5, 0.81),          // 발은 무릎 뒤 바닥에, 허벅지처럼 조금 바깥
          [R + 'UpLeg']: N(-0.49, -0.17, 0.85), [R + 'Leg']: N(0, -0.87, -0.49), [R + 'Foot']: N(-0.3, -0.5, 0.81),
          [L + 'Arm']: N(...mix([0.82, -0.25, 0.5], [0.12, 0.99, 0.05], p)), [L + 'ForeArm']: { aim: N(...mix([-0.05, 0.98, 0.15], [0, 1, 0.02], p)), palmTo: [0, 1, 0] },
          [R + 'Arm']: N(...mix([-0.82, -0.25, 0.5], [-0.12, 0.99, 0.05], p)), [R + 'ForeArm']: { aim: N(...mix([0.05, 0.98, 0.15], [0, 1, 0.02], p)), palmTo: [0, 1, 0] } } };
    } },
    // 랫풀다운: 그립은 어깨의 1.5배, 10~15° 만 기대고 견갑을 내린 뒤 팔꿈치를 엉덩이 쪽으로 — 바는 가슴 윗부분까지
    'lat-pulldown': { base: 'idle', period: 2.8, gear: 'pulldown', fist: true, pose: u => {
      const q = hold(u, 0.05, 0.4, 0.5, 0.95), up = N(0, 0.98, -0.21);
      return { root: { pos: [0, 0.65, 0], up, front: N(0, 0.21, 0.98) },
        bones: { ...spineAll(up, N(0, 0.95, 0.3)), ...both(N(0, -0.1, 0.99), N(0, -1, 0.05), FLAT),
          [L + 'Arm']: N(...mix([0.42, 0.9, 0.1], [0.72, -0.6, 0.15], q)), [L + 'ForeArm']: { aim: N(...mix([0.15, 0.98, 0.1], [-0.3, 0.72, 0.62], q)), palmTo: [0, 0, 1] },
          [R + 'Arm']: N(...mix([-0.42, 0.9, 0.1], [-0.72, -0.6, 0.15], q)), [R + 'ForeArm']: { aim: N(...mix([-0.15, 0.98, 0.1], [0.3, 0.72, 0.62], q)), palmTo: [0, 0, 1] } } };
    } },
    // 레그프레스: 등·머리는 패드에, 발은 어깨너비로 발판 가운데. 무릎 90° 까지 내렸다가 잠그지 않는 데까지 민다 (옆에서 보이게 +X 를 본다)
    'leg-press': { base: 'idle', period: 3.2, gear: 'legpress', fist: true, pose: (u, C) => {
      const e = hold(u, 0.05, 0.45, 0.5, 0.95), up = N(-0.71, 0.7, 0);
      const len = mix(0.7, 0.87, e), P = LEGPRESS.dir;                                                                  // 발목 자리: 엉덩이에서 발판 쪽으로 (아래 0.7 → 위 0.87, 다리 0.9)
      const foot = (side, z) => ({ ik: () => add(C.pos(side + 'UpLeg'), [P[0] * len, P[1] * len, z]), bend: [-0.8, 0.6, z * 0.3] });   // 무릎은 가슴 쪽으로
      return { root: { pos: [-0.1, 0.53, 0], up, front: N(0.7, 0.71, 0) },
        bones: { ...spineAll(up, up, N(0.7, 0.71, 0)), [L + 'UpLeg']: foot(L, -0.14), [R + 'UpLeg']: foot(R, 0.14), [L + 'Foot']: N(-0.36, 0.93, 0), [R + 'Foot']: N(-0.36, 0.93, 0),   // 발판에 평평하게 (캐릭터 왼쪽은 -Z)
          [L + 'Arm']: N(0.6, -0.6, -0.35), [L + 'ForeArm']: N(0.6, -0.7, -0.3), [R + 'Arm']: N(0.6, -0.6, 0.35), [R + 'ForeArm']: N(0.6, -0.7, 0.3) } };   // 팔은 등받이를 따라 내려 의자 옆 손잡이로
    } },
    // 실내 자전거: 안장은 페달이 맨 아래일 때 무릎이 살짝 굽는 높이. 엉덩이에서 힌지해 상체를 살짝 앞으로, 팔꿈치는 부드럽게
    'cycle': { base: 'idle', period: 2.0, gear: 'bike', fist: true, pose: (u, C) => {
      const th = u * Math.PI * 2, up = N(0, 0.92, 0.39);
      const pedal = (side, x, a) => ({ ik: [x, BIKE.crank[1] + BIKE.r * Math.sin(a) + 0.09, BIKE.crank[2] + BIKE.r * Math.cos(a) - 0.03], bend: [x * 0.4, 0.6, 0.8] });   // 발목은 페달 위 9cm
      return { root: { pos: [0, 1.0, -0.05], up, front: N(0, -0.39, 0.92) },
        bones: { ...spineAll(up, N(0, 0.99, 0.15)),
          [L + 'UpLeg']: pedal(L, BIKE.x, th), [R + 'UpLeg']: pedal(R, -BIKE.x, th + Math.PI), [L + 'Foot']: { aim: footFollow(L, [1, 0, 0], 50) }, [R + 'Foot']: { aim: footFollow(R, [1, 0, 0], 50) },
          [L + 'Arm']: { ik: [BIKE.bar[0], BIKE.bar[1], BIKE.bar[2]], bend: [0.3, -1, 0], palmTo: [0, -1, 0] },
          [R + 'Arm']: { ik: [-BIKE.bar[0], BIKE.bar[1], BIKE.bar[2]], bend: [-0.3, -1, 0], palmTo: [0, -1, 0] } } };
    } },
    // 로잉머신: 캐치(정강이 수직, 팔 편 채, 상체 살짝 앞) → 드라이브(다리 → 엉덩이 → 팔, 손잡이는 갈비뼈 아래) → 리커버리는 팔 → 상체 → 다리 순으로 두 배 천천히
    'rowing': { base: 'idle', period: 3.0, gear: 'rower', fist: true, pose: u => {
      const legs = ramp(u, 0, 0.28) - ramp(u, 0.55, 1), body = ramp(u, 0.08, 0.33) - ramp(u, 0.45, 0.85), arms = ramp(u, 0.15, 0.33) - ramp(u, 0.35, 0.6);
      const hz = mix(0.16, -0.2, legs), up = N(...mix([0, 0.985, 0.17], [0, 0.94, -0.34], body)), front = N(up[0], -up[2], up[1]);
      const trunk = N(...mix([0, 0.9, 0.44], [0, 0.92, -0.39], body));                                              // 등은 골반보다 더 앞으로 숙인다(허리 굽힘 15°)
      const hand = mix([0, 0.62, 0.95], [0, ROWER.seatY + 0.35, hz + 0.12], arms);                                  // 캐치에선 무릎 위를 지난다
      const foot = (x, bx) => ({ ik: [x, ROWER.foot[1], ROWER.foot[2]], bend: [bx, 1, 0.2] });
      return { root: { pos: [0, ROWER.seatY, hz], up, front },
        bones: { ...spineAll(trunk), [L + 'UpLeg']: foot(ROWER.foot[0], 0), [R + 'UpLeg']: foot(-ROWER.foot[0], 0), [L + 'Foot']: { aim: footFollow(L, [1, 0, 0], 66) }, [R + 'Foot']: { aim: footFollow(R, [1, 0, 0], 66) },   // 발판 위 발은 발등 쪽으로 살짝
          [L + 'Arm']: { ik: [hand[0] + 0.32, hand[1], hand[2]], bend: [0.9, -0.2, -0.4], palmTo: [0, -1, 0] },          // 팔은 무릎 바깥으로, 팔꿈치도 바깥으로
          [R + 'Arm']: { ik: [hand[0] - 0.32, hand[1], hand[2]], bend: [-0.9, -0.2, -0.4], palmTo: [0, -1, 0] } } };
    } },
  };

  /* ---- 기구 ---- 동작 id → 기구. 손·몸 뼈의 세상 좌표를 따라 매 프레임 옮긴다. (PROC 의 gear 가 우선) */
  const GEAR = {
    'barbell-squat': 'backbar', 'deadlift': 'barbell', 'dumbbell-curl': 'dumbbells', 'shoulder-press': 'dumbbells',
    'kettlebell-swing': 'kettlebell', 'jump-rope': 'rope', 'treadmill': 'treadmill', 'swim': 'water',
    'bench-press': 'bench', 'lat-pulldown': 'pulldown', 'leg-press': 'legpress', 'cycle': 'bike', 'rowing': 'rower', 'calf-stretch': 'wall',
  };

  /* 손잡이 자리: 손 뼈는 손목에서 시작하니 손가락 쪽으로 조금 나간 곳(손바닥 가운데)을 잡는다.
     axis 는 손바닥을 가로지르는 축 — 덤벨·줄넘기 손잡이가 이 축을 따라 눕는다. */
  const GRIP = { along: 0.055, side: 0.0, curl: 75, thumbCurl: 40 };

  /* ---- three.js 불러오기 (한 번만). 'three' 는 index.html 의 importmap 이 js/vendor 로 잇는다 ---- */
  let libP = null;
  function loadLib(){
    if (!libP) {
      libP = Promise.all([import('three'), import('./vendor/loaders/GLTFLoader.js'), import('./vendor/utils/BufferGeometryUtils.js'),
                          import('./vendor/libs/meshopt_decoder.module.js')])
        .then(([T, L, U, M]) => ({ T, GLTFLoader: L.GLTFLoader, U, Meshopt: M.MeshoptDecoder }))
        .catch(e => { libP = null; throw e; });
    }
    return libP;
  }
  function loadGltf(lib, url){
    const loader = new lib.GLTFLoader();
    if (lib.Meshopt) loader.setMeshoptDecoder(lib.Meshopt);           // gltfpack 으로 누른 파일을 푼다
    return new Promise((res, rej) => loader.load(url, res, undefined, rej));
  }
  /* 캐릭터는 성별대로 둘 (mannequin-m / mannequin-f). 동작 파일도 뼈대가 달라 성별 폴더(anim/m, anim/f)에 따로 둔다.
     앱의 성별 값('M'/'F') 을 받는다 — 없으면 남성. */
  const SEX = s => (String(s || '').toUpperCase() === 'F' ? 'f' : 'm');
  const MODEL = s => 'mannequin-' + SEX(s) + '.glb';
  // 캐릭터도 한 번 받으면 기억한다 — 장면마다 새로 파싱하지 않고 뼈대만 복제해 쓴다
  const modelP = new Map();
  function loadModel(lib, sex, file){
    const k = file || MODEL(sex);                                          // file 은 디자인 비교용 — 다른 캐릭터 파일을 바로 띄운다
    if (!modelP.has(k)) modelP.set(k, loadGltf(lib, BASE + k + VER).catch(e => { modelP.delete(k); throw e; }));
    return modelP.get(k);
  }
  /* 미리 받아 두기 — 루틴 화면을 열 때 불러 두면 3D 가 바로 뜬다 */
  function preload(sex){
    return loadLib().then(lib => Promise.all([loadModel(lib, sex), loadClip(lib, FALLBACK_CLIP, sex)])).catch(() => {});
  }
  // 동작은 나눠 쓸 수 있으니 한 번 받으면 기억한다. 캐릭터는 장면마다 새로 읽는다.
  const clipCache = new Map();
  function loadClip(lib, name, sex){
    const key = SEX(sex) + '/' + name;
    if (!clipCache.has(key)) {
      clipCache.set(key, loadGltf(lib, BASE + 'anim/' + key + '.glb' + VER).then(g => g.animations[0])
        .catch(e => { clipCache.delete(key); throw e; }));
    }
    return clipCache.get(key);
  }

  /* 겉모습: 각진 면을 매끈하게(같은 자리 꼭짓점을 합치고 법선을 다시 계산), 회색 하나로 */
  function smoothAndGray(lib, body){
    const { T, U } = lib;
    body.traverse(o => {
      if (!o.isMesh) return;
      const g = o.geometry.clone();
      g.deleteAttribute('normal'); g.deleteAttribute('uv');                 // 텍스처는 안 쓰니 이음새도 합친다
      g.computeBoundingBox();
      const tol = g.boundingBox.getSize(new T.Vector3()).length() * 1e-5;   // 파일 단위가 무엇이든 '같은 자리' 기준은 몸 크기에 비례
      const merged = U.mergeVertices(g, tol); merged.computeVertexNormals();
      o.geometry = merged;
      o.material = new T.MeshStandardMaterial({ color: 0xBCC1C7, roughness: 0.62, metalness: 0.04 });   // 마네킹 회색 하나
      o.castShadow = true; o.frustumCulled = false;
    });
  }

  /* ---- 기구 만들기 ---- */
  function makeGear(T, name, ctx){
    const M = new T.MeshStandardMaterial({ color: 0x565B63, roughness: 0.5, metalness: 0.3 });
    const soft = new T.MeshStandardMaterial({ color: 0x6E747D, roughness: 0.9 });
    const mesh = (g, m = M) => { const o = new T.Mesh(g, m); o.castShadow = true; o.receiveShadow = true; return o; };
    const bar = (len, r, plateR) => {
      const g = new T.Group();
      const b = mesh(new T.CylinderGeometry(r, r, len, 12)); b.rotation.z = Math.PI / 2; g.add(b);
      if (plateR) [-len * 0.37, len * 0.37].forEach(x => { const p = mesh(new T.CylinderGeometry(plateR, plateR, 0.035, 28)); p.rotation.z = Math.PI / 2; p.position.x = x; g.add(p); });
      return g;
    };
    const dumbbell = () => { const g = bar(0.18, 0.012); [-0.075, 0.075].forEach(x => { const d = mesh(new T.CylinderGeometry(0.045, 0.045, 0.035, 20)); d.rotation.z = Math.PI / 2; d.position.x = x; g.add(d); }); return g; };
    const a = new T.Vector3(), b = new T.Vector3(), b2 = new T.Vector3(), q = new T.Quaternion(), X = new T.Vector3(1, 0, 0);
    const _x = new T.Vector3();
    // 손이 쥐는 자리(손바닥 가운데)와 그때의 손 방향
    const grip = (side, out, qOut) => {
      ctx.pos('mixamorig:' + side + 'Hand', out); ctx.quat('mixamorig:' + side + 'Hand', q);
      out.add(b.set(0, GRIP.along, 0).applyQuaternion(q));
      if (ctx.hand[side] && GRIP.side) out.add(b.copy(ctx.hand[side].palm).applyQuaternion(q).multiplyScalar(GRIP.side));   // 손바닥 쪽으로
      if (qOut) qOut.copy(q);
      return out;
    };
    const across = (side, qh) => (ctx.hand[side] ? _x.copy(ctx.hand[side].across) : _x.set(1, 0, 0)).applyQuaternion(qh);   // 손바닥 가로축(세상 기준)
    // 두 손이 같이 쥐는 것: 손잡이 사이 가운데에 놓고 손과 손을 잇는 방향으로 눕힌다
    const betweenHands = (obj, drop = 0) => {
      grip('Left', a); grip('Right', b2);
      obj.position.copy(a).add(b2).multiplyScalar(0.5); obj.position.y -= drop;
      obj.quaternion.setFromUnitVectors(X, a.sub(b2).normalize());
    };
    // 한 손에 하나씩: 손바닥 가운데, 손바닥을 가로지르는 축으로
    const inHand = (obj, side) => {
      grip(side, a, q);
      obj.position.copy(a);
      obj.quaternion.setFromUnitVectors(X, across(side, q));
    };
    const add = o => { ctx.scene.add(o); return o; };
    switch (name) {
      case 'barbell': { const g = add(bar(1.8, 0.014, 0.17)); return { update(){ betweenHands(g); } }; }
      case 'backbar': {
        const g = add(bar(1.8, 0.014, 0.17));
        return { update(){
          ctx.pos('mixamorig:Neck', a); g.position.copy(a); g.position.y -= 0.04; g.position.z -= 0.09;   // 목 뒤 어깨 위
          ctx.pos('mixamorig:LeftShoulder', a); ctx.pos('mixamorig:RightShoulder', b);
          g.quaternion.setFromUnitVectors(X, a.sub(b).normalize());
        } };
      }
      case 'dumbbells': { const L = add(dumbbell()), R = add(dumbbell()); return { update(){ inHand(L, 'Left'); inHand(R, 'Right'); } }; }
      case 'kettlebell': {
        const g = new T.Group();
        const ball = mesh(new T.SphereGeometry(0.085, 24, 18)); ball.position.y = -0.11; g.add(ball);
        const handle = mesh(new T.TorusGeometry(0.06, 0.013, 10, 24)); g.add(handle);
        add(g);
        return { update(){ betweenHands(g, 0.02); } };
      }
      case 'rope': {
        // 두 손잡이를 잇는 줄. 손과 손을 잇는 축을 중심으로 돌며 머리 위 → 앞 → 발밑 → 뒤를 지난다.
        // 뛰어오르는 순간(엉덩이가 가장 높을 때) 줄이 발밑을 지나게 동작 주기에 맞춘다.
        const ropeM = new T.MeshStandardMaterial({ color: 0x3E444C, roughness: 0.8 });
        const handles = [0, 1].map(() => { const h = mesh(new T.CylinderGeometry(0.014, 0.014, 0.14, 10)); return add(h); });
        let tube = null;
        const pts = Array.from({ length: 25 }, () => new T.Vector3());
        const L = new T.Vector3(), R = new T.Vector3(), axis = new T.Vector3(), up = new T.Vector3(0, 1, 0), u = new T.Vector3(), w = new T.Vector3();
        return { update(t, clipT){
          grip('Left', L, q); handles[0].position.copy(L); handles[0].quaternion.setFromUnitVectors(up, across('Left', q));
          grip('Right', R, q); handles[1].position.copy(R); handles[1].quaternion.setFromUnitVectors(up, across('Right', q));
          axis.copy(R).sub(L).normalize();
          u.copy(up).addScaledVector(axis, -up.dot(axis)).normalize();       // 축에 수직인 '위'
          w.crossVectors(u, axis);                                            // 축에 수직인 '앞'
          const jump = ctx.jump || { peak0: 0, period: 0.6 };
          const phi = ((clipT - jump.peak0) / jump.period) * Math.PI * 2 + Math.PI;
          for (let i = 0; i < pts.length; i++) {
            const s = i / (pts.length - 1), bulge = Math.sin(s * Math.PI);
            pts[i].copy(L).lerp(R, s).addScaledVector(u, bulge * Math.cos(phi)).addScaledVector(w, bulge * Math.sin(phi));
          }
          const g = new T.TubeGeometry(new T.CatmullRomCurve3(pts), 48, 0.008, 6, false);
          if (tube) { tube.geometry.dispose(); tube.geometry = g; } else { tube = add(new T.Mesh(g, ropeM)); tube.castShadow = true; }
        } };
      }
      case 'treadmill': {
        const box = (w, h, d, x, y, z, m) => { const o = mesh(new T.BoxGeometry(w, h, d), m); o.position.set(x, y, z); return add(o); };
        box(0.72, 0.04, 1.6, 0, -0.02, 0.1, soft);
        [-0.34, 0.34].forEach(x => box(0.04, 1.0, 0.04, x, 0.5, 0.75));
        box(0.72, 0.04, 0.04, 0, 1.0, 0.75); box(0.4, 0.16, 0.05, 0, 1.12, 0.75);
        return {};
      }
      case 'wall': {
        const wm = new T.MeshStandardMaterial({ color: 0x9AA0A8, roughness: 0.9, transparent: true, opacity: 0.45 });   // 비쳐 보이게 — 몸을 가리지 않는다
        const w = mesh(new T.BoxGeometry(0.1, 2.3, 1.4), wm); w.position.set(WALL_X + 0.05, 1.15, 0); add(w);
        return { pad: 0.2 };
      }
      case 'bench': {
        const bench = mesh(new T.BoxGeometry(0.3, 0.42, 1.25), soft); bench.position.set(0, 0.21, -0.1); add(bench);
        const g = add(bar(1.8, 0.014, 0.17));
        return { pad: 0.5, update(){ betweenHands(g); } };
      }
      case 'pulldown': {
        const seat = mesh(new T.BoxGeometry(0.45, 0.55, 0.45), soft); seat.position.set(0, 0.275, 0.02); add(seat);
        const pad = mesh(new T.BoxGeometry(0.5, 0.08, 0.16), soft); pad.position.set(0, 0.74, 0.32); add(pad);        // 허벅지 패드
        const post = mesh(new T.BoxGeometry(0.08, 2.3, 0.08)); post.position.set(0, 1.15, -0.55); add(post);
        const arm = mesh(new T.BoxGeometry(0.08, 0.08, 1.1)); arm.position.set(0, 2.3, -0.05); add(arm);
        const pulley = mesh(new T.CylinderGeometry(0.06, 0.06, 0.06, 16)); pulley.rotation.z = Math.PI / 2; pulley.position.set(0, 2.3, 0.45); add(pulley);
        const pbar = add(bar(1.1, 0.014)); const top = new T.Vector3(0, 2.3, 0.45); let cable = null;
        return { pad: 0.9, update(){
          betweenHands(pbar);
          const len = Math.max(0.05, pbar.position.distanceTo(top));
          if (cable) { cable.geometry.dispose(); cable.geometry = new T.CylinderGeometry(0.006, 0.006, len, 6); } else cable = add(mesh(new T.CylinderGeometry(0.006, 0.006, len, 6)));
          cable.position.copy(pbar.position).add(top).multiplyScalar(0.5); cable.quaternion.setFromUnitVectors(new T.Vector3(0, 1, 0), top.clone().sub(pbar.position).normalize());
        } };
      }
      case 'legpress': {
        const seat = mesh(new T.BoxGeometry(0.6, 0.12, 0.6), soft); seat.position.set(-0.05, 0.38, 0); add(seat);
        const back = mesh(new T.BoxGeometry(0.12, 0.9, 0.6), soft); back.position.set(-0.54, 0.69, 0); back.rotation.z = 0.72; add(back);   // 몸과 같은 45° 로 등 뒤에
        const pm = new T.MeshStandardMaterial({ color: 0x6E747D, roughness: 0.9, transparent: true, opacity: 0.55 });
        const plate = add(mesh(new T.BoxGeometry(0.9, 0.9, 0.06), pm)); const P = new T.Vector3().fromArray(LEGPRESS.dir);
        return { pad: 0.6, update(){
          ctx.pos('mixamorig:LeftFoot', a); ctx.pos('mixamorig:RightFoot', b);
          plate.position.copy(a).add(b).multiplyScalar(0.5).addScaledVector(P, 0.12);
          plate.quaternion.setFromUnitVectors(new T.Vector3(0, 0, 1), P);
        } };
      }
      case 'bike': {
        const V = (x, y, z) => new T.Vector3(x, y, z);
        const tube = (p, r0 = 0.02) => { const len = p[0].distanceTo(p[1]); const c = mesh(new T.CylinderGeometry(r0, r0, len, 10)); c.position.copy(p[0]).add(p[1]).multiplyScalar(0.5); c.quaternion.setFromUnitVectors(V(0, 1, 0), p[1].clone().sub(p[0]).normalize()); return add(c); };
        const crank = V(...BIKE.crank), saddle = V(0, 0.86, -0.08), head = V(0, 1.0, 0.5), rear = V(0, 0.33, -0.5), frontHub = V(0, 0.33, 0.78);   // 안장은 엉덩이 관절 아래 8cm
        [[crank, saddle], [saddle, head], [crank, head], [rear, saddle], [rear, crank], [head, frontHub]].forEach(p => tube(p));
        [rear, frontHub].forEach(h => { const w = mesh(new T.TorusGeometry(0.33, 0.02, 8, 36)); w.position.copy(h); add(w); });
        const hb = mesh(new T.CylinderGeometry(0.015, 0.015, 0.5, 10)); hb.rotation.z = Math.PI / 2; hb.position.set(0, BIKE.bar[1], BIKE.bar[2]); add(hb);
        const sad = mesh(new T.BoxGeometry(0.14, 0.05, 0.26), soft); sad.position.copy(saddle).add(V(0, 0.04, 0)); add(sad);
        const arms = [0, 1].map(() => add(mesh(new T.BoxGeometry(0.03, 0.03, BIKE.r)))), pedals = [0, 1].map(() => add(mesh(new T.BoxGeometry(0.1, 0.02, 0.08), soft)));
        return { pad: 0.7, update(){
          const th = (ctx.u || 0) * Math.PI * 2;
          [0, 1].forEach(i => {
            const ang = th + i * Math.PI, x = i ? -BIKE.x : BIKE.x;
            const p = V(x, crank.y + BIKE.r * Math.sin(ang), crank.z + BIKE.r * Math.cos(ang));
            pedals[i].position.copy(p);
            arms[i].position.copy(crank).add(p).multiplyScalar(0.5); arms[i].position.x = x * 0.45;   // 크랭크 암은 페달보다 안쪽
            arms[i].quaternion.setFromUnitVectors(V(0, 0, 1), p.clone().sub(crank).setX(0).normalize());
          });
        } };
      }
      case 'rower': {
        const V = (x, y, z) => new T.Vector3(x, y, z);
        const rail = mesh(new T.BoxGeometry(0.08, 0.05, 1.3), soft); rail.position.set(0, ROWER.seatY - 0.13, -0.05); add(rail);   // 레일은 좁게 — 발 사이
        const seat = add(mesh(new T.BoxGeometry(0.32, 0.05, 0.3), soft));
        const fly = mesh(new T.CylinderGeometry(0.26, 0.26, 0.14, 24)); fly.rotation.z = Math.PI / 2; fly.position.fromArray(ROWER.fly); add(fly);
        [1, -1].forEach(s => { const f = mesh(new T.BoxGeometry(0.14, 0.02, 0.3), soft); f.position.set(s * ROWER.foot[0], ROWER.foot[1] - 0.06, ROWER.foot[2] + 0.02); f.rotation.x = -0.9; add(f); });
        const handle = add(bar(0.64, 0.014)); const fp = V(0, ROWER.fly[1], ROWER.fly[2] - 0.12); let cord = null;
        return { pad: 0.5, update(){
          betweenHands(handle);
          ctx.pos('mixamorig:Hips', a); seat.position.set(0, ROWER.seatY - 0.09, a.z);
          const len = Math.max(0.05, handle.position.distanceTo(fp));
          if (cord) { cord.geometry.dispose(); cord.geometry = new T.CylinderGeometry(0.006, 0.006, len, 6); } else cord = add(mesh(new T.CylinderGeometry(0.006, 0.006, len, 6)));
          cord.position.copy(handle.position).add(fp).multiplyScalar(0.5); cord.quaternion.setFromUnitVectors(V(0, 1, 0), fp.clone().sub(handle.position).normalize());
        } };
      }
      case 'water': {
        const w = new T.Mesh(new T.PlaneGeometry(4, 4), new T.MeshStandardMaterial({ color: 0xE1E6EC, transparent: true, opacity: 0.55, roughness: 0.3 }));
        w.rotation.x = -Math.PI / 2; w.position.y = 0.15; w.receiveShadow = true; w.userData.qaSkip = true; add(w);
        return {};
      }
    }
    return {};
  }

  /* 렌더러는 캔버스마다 하나만 — 브라우저는 한 캔버스에 WebGL 컨텍스트를 한 번만 주므로,
     동작을 바꿀 때마다 새로 만들면(옛 것을 잃게 하면) 두 번째부터 아무것도 못 그린다 */
  const renderers = new WeakMap();
  function getRenderer(T, canvas){
    let r = renderers.get(canvas);
    if (!r) {
      r = new T.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });   // 그린 그림을 캔버스에서 꺼낼 수 있게 (비교·공유용)
      r.setClearColor(0x000000, 0);
      r.shadowMap.enabled = true; r.shadowMap.type = T.PCFSoftShadowMap;
      renderers.set(canvas, r);
    }
    return r;
  }

  /* ---- 무대 ---- */
  function setup(lib, me, clip){
    const { T } = lib;
    const { canvas, body, id } = me;
    const size = Math.max(160, Math.min(canvas.clientWidth || 320, 480));
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const renderer = getRenderer(T, canvas);
    renderer.setPixelRatio(dpr); renderer.setSize(size, size, false);
    const scene = new T.Scene(); me.scene = scene;
    scene.add(new T.HemisphereLight(0xffffff, 0x9AA3AD, 1.6));
    const key = new T.DirectionalLight(0xffffff, 2.4); key.position.set(2.5, 4.5, 3); key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024); key.shadow.bias = -0.0004;
    Object.assign(key.shadow.camera, { left: -2, right: 2, top: 3, bottom: -1, near: 1, far: 14 });
    scene.add(key);
    const fill = new T.DirectionalLight(0xffffff, 0.8); fill.position.set(-3, 2, -2); scene.add(fill);
    const floor = new T.Mesh(new T.PlaneGeometry(10, 10), new T.ShadowMaterial({ opacity: 0.18 }));
    floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; floor.userData.qaSkip = true; scene.add(floor);

    // 캐릭터: 크기를 사람 키로 맞추고, 매끈한 회색으로
    // (스킨 메시의 상자는 뼈가 아직 움직이기 전이라 믿을 수 없다 — 묶인 자세의 꼭짓점을 그대로 잰다)
    body.updateMatrixWorld(true);
    let h = 0;
    body.traverse(o => {
      if (!o.isMesh || !o.geometry) return;
      o.geometry.computeBoundingBox();
      const bb = o.geometry.boundingBox.clone().applyMatrix4(o.matrixWorld);
      h = Math.max(h, bb.max.y - bb.min.y);
    });
    if (h > 0 && (h < 1.2 || h > 2.4)) body.scale.setScalar(1.75 / h);   // 파일 단위가 cm 든 뭐든 1.75m 로
    smoothAndGray(lib, body);
    scene.add(body);
    body.updateMatrixWorld(true);
    // GLTFLoader 는 뼈 이름의 ':' 를 지운다(mixamorig:Hips → mixamorigHips). 글자와 숫자만 남겨 맞춘다 —
    // 숫자를 빼면 Spine·Spine1·Spine2 가 한 이름이 돼 척추 위쪽만 움직였다.
    const norm = n => String(n).replace(/[^A-Za-z0-9]/g, '');
    const map = new Map(); const boneList = [];
    body.traverse(o => { if (o.isBone) { map.set(norm(o.name), o); boneList.push(o); } });
    const bones = { get: n => map.get(norm(n)) };
    // 캐릭터 파일에 든 한 프레임짜리 T 자세를 먼저 입힌다 — 리깅 때 팔이 내려간 자세로 묶였어도
    // 아래의 '처음 자세'는 늘 T 자세가 된다
    if (me.tpose) {
      for (const tr of me.tpose.tracks) {
        const [node, prop] = tr.name.split('.'); const b = bones.get(node); if (!b) continue;
        if (prop === 'quaternion') b.quaternion.fromArray(tr.values, 0);
        else if (prop === 'position') b.position.fromArray(tr.values, 0);
        else if (prop === 'scale') b.scale.fromArray(tr.values, 0);
      }
      body.updateMatrixWorld(true);
    }
    // 뼈마다 처음(T 자세) 세상 방향을 기억해 둔다 — aim 은 이 방향에서 얼마나 돌릴지로 계산한다
    const restQ = new Map(); boneList.forEach(b => restQ.set(b, b.getWorldQuaternion(new T.Quaternion())));
    const restLocalQ = new Map(); boneList.forEach(b => restLocalQ.set(b, b.quaternion.clone()));
    // 손의 기준 축 — T 자세에선 손바닥이 아래(-Y)를 본다. 그걸 손 뼈 기준으로 옮겨 두면
    // 손이 어디로 돌아가든 손바닥 방향·손바닥 가로축을 알 수 있다.
    const hand = {};
    for (const side of ['Left', 'Right']) {
      const hb = bones.get('mixamorig:' + side + 'Hand'); if (!hb) continue;
      const inv = restQ.get(hb).clone().invert();
      const palm = new T.Vector3(0, -1, 0).applyQuaternion(inv).normalize();          // 손 기준 손바닥 방향
      const across = new T.Vector3().crossVectors(palm, new T.Vector3(0, 1, 0)).normalize();   // 손가락(Y)·손바닥에 수직 = 손바닥 가로축
      const curl = new T.Vector3().crossVectors(across, new T.Vector3(0, 1, 0)).dot(palm) > 0 ? across.clone() : across.clone().negate();
      hand[side] = { bone: hb, palm, across, curl };
    }

    const mixer = new T.AnimationMixer(body);
    const action = mixer.clipAction(clip); action.play();
    // '움직임 줄이기'(prefers-reduced-motion) 설정이어도 동작은 멈추지 않는다 — 동작 자체가 보여 줄 내용이다.
    // (전엔 이 설정에서 한 프레임만 그려 휴대폰에서 캐릭터가 멈춰 보였다.) 카메라가 좌우로 도는 것만 뺀다.
    const calm = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

    // ---- 손보기 적용 ----
    const tweak = TWEAKS[id];
    const _v1 = new T.Vector3(), _v2 = new T.Vector3(), _v3 = new T.Vector3(), _q1 = new T.Quaternion(), _q2 = new T.Quaternion(), _e = new T.Euler();
    const pitchAtHands = deg => {
      const pivot = bones.get('mixamorig:LeftHand').getWorldPosition(_v1).add(bones.get('mixamorig:RightHand').getWorldPosition(_v2)).multiplyScalar(0.5);
      const rot = _q1.setFromAxisAngle(_v3.set(1, 0, 0), deg * D);
      const hips = bones.get('mixamorig:Hips');
      const hp = hips.getWorldPosition(_v2).sub(pivot).applyQuaternion(rot).add(pivot);
      const hq = hips.getWorldQuaternion(_q2).premultiply(rot);
      hips.position.copy(hips.parent.worldToLocal(hp));
      hips.quaternion.copy(hips.parent.getWorldQuaternion(_q1).invert().multiply(hq));
      hips.updateMatrixWorld(true);
    };
    const aimBone = (bone, dir) => {
      const rest = restQ.get(bone);
      const restDir = _v1.set(0, 1, 0).applyQuaternion(rest);              // 뼈는 자기 Y 축을 따라 뻗는다
      const want = _v2.fromArray(dir).normalize();
      const worldQ = _q1.setFromUnitVectors(restDir, want).multiply(rest);
      bone.quaternion.copy(bone.parent.getWorldQuaternion(_q2).invert().multiply(worldQ));
      bone.updateMatrixWorld(true);
    };
    const posOf = n => { const b = bones.get(n); return b ? b.getWorldPosition(new T.Vector3()) : new T.Vector3(); };
    const applyTweaks = t => {
      if (!tweak) return;
      if (tweak.pitchAtHands) pitchAtHands(tweak.pitchAtHands);
      const table = typeof tweak.bones === 'function' ? tweak.bones(t) : tweak.bones;
      if (!table) return;
      for (const [name, how] of Object.entries(table)) {
        const bone = bones.get(name); if (!bone || !how.set) continue;
        bone.quaternion.setFromEuler(_e.set(how.set[0] * D, how.set[1] * D, how.set[2] * D));
      }
      body.updateMatrixWorld(true);
      // 부모부터 — 자식의 방향은 부모가 정해진 뒤에 맞춘다
      const byBone = new Map(); for (const [name, how] of Object.entries(table)) { const b = bones.get(name); if (b && how.aim) byBone.set(b, how); }
      for (const bone of boneList) if (byBone.has(bone)) {
        const how = byBone.get(bone);
        aimBone(bone, typeof how.aim === 'function' ? how.aim(posOf) : how.aim);
        if (how.roll) { bone.quaternion.multiply(_q1.setFromAxisAngle(_v3.set(0, 1, 0), how.roll * D)); bone.updateMatrixWorld(true); }
        if (how.palmTo) palmToward(bone, how.palmTo);
      }
      alignHinges(byBone);
      if (tweak.fist) fist();
      body.updateMatrixWorld(true);
    };
    // 손바닥이 target 쪽을 보게 이 뼈(아래팔)를 제 축으로 비튼다
    const _v4 = new T.Vector3(), _v5 = new T.Vector3();
    const palmToward = (bone, target) => {
      const side = /Left/.test(bone.name) ? 'Left' : 'Right'; const h = hand[side]; if (!h) return;
      const axis = _v3.set(0, 1, 0).applyQuaternion(bone.getWorldQuaternion(_q1)).normalize();
      const n = _v4.copy(h.palm).applyQuaternion(h.bone.getWorldQuaternion(_q2));                 // 지금 손바닥 방향
      const goal = target === 'head' ? bones.get('mixamorig:Head').getWorldPosition(_v5).sub(h.bone.getWorldPosition(_v1)) : _v5.fromArray(target);
      n.addScaledVector(axis, -n.dot(axis)).normalize(); goal.addScaledVector(axis, -goal.dot(axis)).normalize();
      const ang = Math.atan2(_v1.crossVectors(n, goal).dot(axis), n.dot(goal));
      bone.quaternion.multiply(_q1.setFromAxisAngle(_v3.set(0, 1, 0), ang)); bone.updateMatrixWorld(true);
    };
    // 주먹: 손가락 마디를 처음 자세에서 손바닥 쪽으로 만다 (엄지는 덜)
    const fist = () => {
      for (const bone of boneList) {
        const m = /(Left|Right)Hand(Thumb|Index|Middle|Ring|Pinky)([123])$/.exec(bone.name); if (!m) continue;
        const h = hand[m[1]]; if (!h) continue;
        const deg = (m[2] === 'Thumb' ? GRIP.thumbCurl : GRIP.curl) * (m[3] === '1' ? 0.75 : 1);
        bone.quaternion.copy(restLocalQ.get(bone)).multiply(_q1.setFromAxisAngle(h.curl, deg * D));
      }
    };
    // 기구
    const v = new T.Vector3();
    const ctx = { scene, hand, u: 0, pos: (n, v) => bones.get(n) ? bones.get(n).getWorldPosition(v) : v.set(0, 0, 0), quat: (n, q) => bones.get(n) ? bones.get(n).getWorldQuaternion(q) : q.identity() };
    // ---- 학습한 자세로 만든 동작 적용 ----
    const proc = PROC[id];
    const stillBase = !!(proc && proc.still);                                 // 바탕 동작을 첫 프레임에 멈춘다 (누운 동작의 손 꼼지락거림)
    const restDir = bone => _v1.set(0, 1, 0).applyQuaternion(restQ.get(bone)).toArray();
    const C = { pos: n => posOf(n), rest: n => { const b = bones.get(n); return b ? restDir(b) : [0, 1, 0]; } };
    const _v6 = new T.Vector3(), _m1 = new T.Matrix4(), _m2 = new T.Matrix4();
    // 뼈의 Y(뻗는 방향)와 Z(앞) 를 같이 정한다 — 엉덩이·척추처럼 어느 쪽을 보는지가 중요한 뼈
    const orientBone = (bone, up, front) => {
      const rest = restQ.get(bone);
      const ry = _v1.set(0, 1, 0).applyQuaternion(rest), rz = _v2.set(0, 0, 1).applyQuaternion(rest);
      rz.addScaledVector(ry, -rz.dot(ry)).normalize(); const rx = _v3.crossVectors(ry, rz);
      _m1.makeBasis(rx, ry, rz);
      const y = _v4.fromArray(up).normalize(), z = _v5.fromArray(front); z.addScaledVector(y, -z.dot(y)).normalize(); const x = _v6.crossVectors(y, z);
      _m2.makeBasis(x, y, z);
      _m1.transpose(); _m2.multiply(_m1);                                   // 처음 축을 원하는 축으로 돌리는 회전
      const worldQ = _q1.setFromRotationMatrix(_m2).multiply(rest);
      bone.quaternion.copy(bone.parent.getWorldQuaternion(_q2).invert().multiply(worldQ));
      bone.updateMatrixWorld(true);
    };
    const setWorldPos = (bone, p) => { bone.position.copy(bone.parent.worldToLocal(_v1.fromArray(p))); bone.updateMatrixWorld(true); };
    // 두 마디 IK: a 에서 목표까지, 마디 길이 l1·l2, 굽는 쪽 bend → 가운데 관절 자리
    const ik2 = (a, target, l1, l2, bend) => {
      const d = target.clone().sub(a); let dist = d.length(); const n = d.normalize();
      dist = Math.max(Math.abs(l1 - l2) + 1e-4, Math.min(l1 + l2 - 1e-4, dist));
      const cosA = (l1 * l1 + dist * dist - l2 * l2) / (2 * l1 * dist), sinA = Math.sqrt(Math.max(0, 1 - cosA * cosA));
      const b = bend.clone().addScaledVector(n, -bend.dot(n));
      if (b.lengthSq() < 1e-8) b.set(0, 1, 0).addScaledVector(n, -n.y);      // 굽는 쪽이 애매하면 위로
      b.normalize();
      return a.clone().addScaledVector(n, l1 * cosA).addScaledVector(b, l1 * sinA);
    };
    // 경첩 맞추기: 사람의 팔꿈치·무릎은 한 방향(위팔의 '앞', 허벅지의 '뒤')으로만 굽는다. 아래팔·정강이가 다른 쪽으로 굽어 있으면
    // 실제로는 어깨·고관절이 돌아간 것이므로, 위팔·허벅지를 제 축으로 돌려 경첩 방향을 굽는 쪽에 맞추고 아래팔·정강이는 세상 방향을 그대로 둔다.
    // 우리가 방향을 정한 뼈에만 한다 (모션캡처는 사람이 한 것이라 그대로). docs/3d-joint-kinematics.md
    const HINGES = [['LeftArm', 'LeftForeArm', [0, 0, 1]], ['RightArm', 'RightForeArm', [0, 0, 1]], ['LeftUpLeg', 'LeftLeg', [0, 0, -1]], ['RightUpLeg', 'RightLeg', [0, 0, -1]]];
    const _q3 = new T.Quaternion(), _q4 = new T.Quaternion(), _v7 = new T.Vector3(), _v8 = new T.Vector3(), _v9 = new T.Vector3();
    const alignHinges = table => {
      for (const [pn, cn, flex0] of HINGES) {
        const p = bones.get('mixamorig:' + pn), c = bones.get('mixamorig:' + cn); if (!p || !c) continue;
        if (table && !table.has(p) && !table.has(c)) continue;
        const g = c.children.find(x => x.isBone); if (!g) continue;
        const axis = _v7.subVectors(c.getWorldPosition(_v1), p.getWorldPosition(_v2)).normalize();          // 위팔·허벅지 축
        const bend = _v8.subVectors(g.getWorldPosition(_v1), c.getWorldPosition(_v2)).normalize();          // 아래팔·정강이 방향
        bend.addScaledVector(axis, -bend.dot(axis));                                                         // 축에 수직인 성분 = 굽는 쪽
        if (bend.length() < 0.17) {                                                                          // 거의 곧게 편 팔다리는 굽는 쪽이 없다 (10° 미만)
          if (flex0[2] > 0) continue;                                                                        //   팔은 그대로
          const gg = g.children.find(x => x.isBone); if (!gg) continue;                                      //   다리는 발끝 반대쪽을 '뒤'로 — 무릎이 발끝을 본다
          bend.subVectors(gg.getWorldPosition(_v1), g.getWorldPosition(_v2)).normalize().negate();
          bend.addScaledVector(axis, -bend.dot(axis));
          if (bend.length() < 0.17) continue;
        }
        bend.normalize();
        p.getWorldQuaternion(_q1); _q3.copy(restQ.get(p)).invert(); _q1.multiply(_q3);                       // 처음 자세에서 지금까지의 회전
        const hinge = _v9.fromArray(flex0).applyQuaternion(_q1);                                             // 지금 경첩이 굽는 방향
        hinge.addScaledVector(axis, -hinge.dot(axis)).normalize();
        const angle = Math.atan2(_v1.crossVectors(hinge, bend).dot(axis), hinge.dot(bend));
        if (Math.abs(angle) < 0.02) continue;
        c.getWorldQuaternion(_q4);
        p.quaternion.multiply(_q1.setFromAxisAngle(_v2.set(0, 1, 0), angle)); p.updateMatrixWorld(true);   // 제 축으로 돌린다
        c.quaternion.copy(p.getWorldQuaternion(_q2).invert().multiply(_q4)); c.updateMatrixWorld(true);    // 아래팔·정강이(와 그 아래)는 그대로
        // 아래팔·정강이는 위팔·허벅지에 대해 비틀리지 않게 — 경첩 축(굽는 방향 × 뼈 축)을 부모와 나란히. 손바닥 방향을 정한 아래팔은 그대로 둔다
        const hc = table && table.get(c), hp = table && table.get(p);
        if ((hc && (hc.palmTo || hc.roll)) || (hp && hp.ik && hp.palmTo)) continue;
        const axis0 = _v1.set(0, 1, 0).applyQuaternion(restQ.get(p)), h0 = _v2.fromArray(flex0).cross(axis0);      // 처음 자세의 경첩 축
        const hpar = _v9.copy(h0).applyQuaternion(_q1.copy(p.getWorldQuaternion(_q2)).multiply(_q3));                // 부모의 지금 경첩 축 (_q3 = 처음 자세의 역)
        const cax = _v7.subVectors(g.getWorldPosition(_v8), c.getWorldPosition(_v1)).normalize();                     // 아래팔·정강이 축
        const hch = _v8.copy(h0).applyQuaternion(_q1.copy(c.getWorldQuaternion(_q2)).multiply(_q4.copy(restQ.get(c)).invert()));   // 자식의 지금 경첩 축
        hpar.addScaledVector(cax, -hpar.dot(cax)); hch.addScaledVector(cax, -hch.dot(cax));
        if (hpar.lengthSq() < 0.05 || hch.lengthSq() < 0.05) continue;
        hpar.normalize(); hch.normalize();
        const tw = Math.atan2(_v1.crossVectors(hch, hpar).dot(cax), hch.dot(hpar));
        if (Math.abs(tw) < 0.02) continue;
        g.getWorldQuaternion(_q4);
        c.quaternion.multiply(_q1.setFromAxisAngle(_v2.set(0, 1, 0), tw)); c.updateMatrixWorld(true);
        g.quaternion.copy(c.getWorldQuaternion(_q2).invert().multiply(_q4)); g.updateMatrixWorld(true);    // 손·발(과 그 아래)은 그대로
        // 손·발도 아래팔·정강이에 대해 비틀리지 않게 — 옆으로 누운 자세에서 발바닥이 바닥을 보는 식으로 돌아가지 않는다
        const gax = _v7.set(0, 1, 0).applyQuaternion(g.getWorldQuaternion(_q2)).normalize();
        const hc2 = _v9.copy(h0).applyQuaternion(_q1.copy(c.getWorldQuaternion(_q2)).multiply(_q4.copy(restQ.get(c)).invert()));
        const hg2 = _v8.copy(h0).applyQuaternion(_q1.copy(g.getWorldQuaternion(_q2)).multiply(_q3.copy(restQ.get(g)).invert()));
        hc2.addScaledVector(gax, -hc2.dot(gax)); hg2.addScaledVector(gax, -hg2.dot(gax));
        if (hc2.lengthSq() < 0.05 || hg2.lengthSq() < 0.05) continue;
        hc2.normalize(); hg2.normalize();
        const tw2 = Math.atan2(_v1.crossVectors(hg2, hc2).dot(gax), hg2.dot(hc2));
        if (Math.abs(tw2) < 0.02) continue;
        g.quaternion.multiply(_q1.setFromAxisAngle(_v2.set(0, 1, 0), tw2)); g.updateMatrixWorld(true);
      }
    };
    const ka = new T.Vector3(), km = new T.Vector3(), ke = new T.Vector3(), kt = new T.Vector3(), kb = new T.Vector3();
    const applyProc = t => {
      if (!proc) return;
      const u = (((t % proc.period) + proc.period) % proc.period) / proc.period;
      ctx.u = u;
      const pose = proc.pose(u, C) || {};
      const hips = bones.get('mixamorig:Hips');
      if (pose.root && hips) {
        const r = pose.root;
        if (r.pos) setWorldPos(hips, r.pos);
        else if (r.dpos) { hips.getWorldPosition(_v2); setWorldPos(hips, [_v2.x + r.dpos[0], _v2.y + r.dpos[1], _v2.z + r.dpos[2]]); }
        if (r.up) orientBone(hips, r.up, r.front || [0, 0, 1]);
      }
      body.updateMatrixWorld(true);
      const table = new Map();
      for (const [n, how] of Object.entries(pose.bones || {})) { const b = bones.get(n); if (b && how) table.set(b, how); }
      const aimPass = () => {                                                 // 방향 — 부모부터 (aim 이 함수면 뼈 위치 조회 함수를 받아 방향을 돌려준다)
        for (const bone of boneList) {
          const how = table.get(bone); if (!how || how.ik) continue;
          const aim = (Array.isArray(how) || how === 'rest') ? how : how.aim;
          if (aim) { const dir = aim === 'rest' ? restDir(bone) : (typeof aim === 'function' ? aim(posOf) : aim); if (how.front) orientBone(bone, dir, how.front); else aimBone(bone, dir); }
          if (how.roll) { bone.quaternion.multiply(_q1.setFromAxisAngle(_v3.set(0, 1, 0), how.roll * D)); bone.updateMatrixWorld(true); }
        }
        for (const bone of boneList) {                                          // 손바닥 방향은 손 방향까지 다 정한 뒤에 (아래팔을 비트니 손도 같이 돈다)
          const how = table.get(bone); if (how && !how.ik && how.palmTo) palmToward(bone, how.palmTo);
        }
      };
      aimPass();                                                              // 1) 방향
      const ikPass = () => {                                                  // 손·발 목표 — 두 마디를 한 번에
        for (const bone of boneList) {
          const how = table.get(bone); if (!how || !how.ik) continue;
          const mid = bone.children.find(c => c.isBone), end = mid && mid.children.find(c => c.isBone); if (!end) continue;
          bone.getWorldPosition(ka); mid.getWorldPosition(km); end.getWorldPosition(ke); kt.fromArray(typeof how.ik === 'function' ? how.ik(posOf) : how.ik); kb.fromArray(how.bend || [0, 0, 1]);
          const joint = ik2(ka, kt, ka.distanceTo(km), km.distanceTo(ke), kb);
          aimBone(bone, joint.sub(ka).toArray());
          mid.getWorldPosition(km); aimBone(mid, kt.clone().sub(km).toArray());
          if (how.palmTo) palmToward(mid, how.palmTo);
        }
      };
      ikPass(); ikPass();                                                     // 2) 두 번 — 다른 팔의 팔꿈치를 잡는 손은 그 팔이 자리 잡은 뒤에
      aimPass();                                                              // 3) IK 로 움직인 팔다리 끝에 달린 손·발은 부모가 정해진 뒤 다시 맞춘다
      alignHinges(table);                                                     // 4) 팔꿈치·무릎이 굽는 쪽에 위팔·허벅지의 비틀림을 맞춘다
      if (pose.fist || proc.fist) fist();
      body.updateMatrixWorld(true);
    };
    const cycle = proc ? proc.period : clip.duration;                       // 한 바퀴 — 카메라·줄넘기 박자가 이것을 본다
    // 믹서는 값이 안 바뀐 프레임엔 뼈를 다시 쓰지 않는다. 그래서 우리가 덮어쓴 엉덩이(root.dpos, pitchAtHands)를
    // 다음 프레임 전에 '믹서가 마지막에 준 값'으로 되돌려 둔다 — 처음 자세로 되돌리면 엉덩이 높이가 일정한
    // 동작(무릎꿇기 등)에서 믹서가 안 써서 몸이 떠 버리고, 안 되돌리면 dpos 가 쌓인다.
    const hipsBone = bones.get('mixamorig:Hips');
    const hipsMixed = hipsBone ? hipsBone.position.clone() : null, hipsMixedQ = hipsBone ? hipsBone.quaternion.clone() : null;
    const restoreHips = () => { if (hipsBone) { hipsBone.position.copy(hipsMixed); hipsBone.quaternion.copy(hipsMixedQ); } };
    const rememberHips = () => { if (hipsBone) { hipsMixed.copy(hipsBone.position); hipsMixedQ.copy(hipsBone.quaternion); } };
    const poseAt = t => { restoreHips(); mixer.setTime(stillBase ? 0 : t % clip.duration); rememberHips(); body.updateMatrixWorld(true); applyTweaks(t); applyProc(t); };
    if (GEAR[id] === 'rope') {
      const hips = bones.get('mixamorig:Hips'); const N = 60, ys = [];
      for (let i = 0; i < N; i++) { poseAt(clip.duration * i / N); ys.push(hips.getWorldPosition(v).y); }
      const peaks = []; for (let i = 0; i < N; i++) { const pv = ys[(i + N - 1) % N], c = ys[i], nx = ys[(i + 1) % N]; if (c > pv && c >= nx) peaks.push(i); }
      ctx.jump = { peak0: peaks.length ? clip.duration * peaks[0] / N : 0, period: peaks.length ? clip.duration / peaks.length : 0.6 };
    }
    const gearName = (proc && proc.gear) || GEAR[id];
    const gear = gearName ? makeGear(T, gearName, ctx) : {};

    // 카메라는 이 동작이 한 바퀴 도는 동안 뼈대가 차지하는 상자 전체에 맞춘다 —
    // 서 있다가 엎드리는 동작도 처음부터 끝까지 화면에 다 들어오고, 흔들리지 않는다
    const camera = new T.PerspectiveCamera(30, 1, 0.1, 60);
    const lo = new T.Vector3(Infinity, Infinity, Infinity), hi = new T.Vector3(-Infinity, -Infinity, -Infinity);
    for (let i = 0; i <= 24; i++) {
      poseAt(cycle * i / 24);
      for (const b of boneList) { b.getWorldPosition(v); lo.min(v); hi.max(v); }
    }
    poseAt(0);
    if (!isFinite(lo.x)) { lo.set(-0.5, 0, -0.5); hi.set(0.5, 1.8, 0.5); }
    const target = lo.clone().add(hi).multiplyScalar(0.5);
    const dist = (Math.max(hi.x - lo.x, hi.y - lo.y + 0.3, hi.z - lo.z, 1.2) + (gear.pad || 0)) * 1.9 + 0.8;   // 머리·손끝·기구 여유
    const place = ms => {
      const a = (34 + (calm ? 0 : 8 * Math.sin(ms / 1400))) * D;       // 천천히 좌우로 돌며 입체를 보여 준다
      const e = 14 * D;
      camera.position.set(target.x + Math.sin(a) * Math.cos(e) * dist, target.y + Math.sin(e) * dist, target.z + Math.cos(a) * Math.cos(e) * dist);
      camera.lookAt(target);
    };

    const clock = new T.Clock();
    const frame = () => {
      if (me.dead) return;
      restoreHips();
      const dt = clock.getDelta(); mixer.update(stillBase ? 0 : dt);
      rememberHips();
      body.updateMatrixWorld(true);
      applyTweaks(clock.elapsedTime);
      applyProc(clock.elapsedTime);
      if (gear.update) gear.update(clock.elapsedTime, action.time);
      place(clock.elapsedTime * 1000);
      renderer.render(scene, camera);
      me.raf = requestAnimationFrame(frame);
    };
    me.renderer = renderer;
    // ---- 검사용 손잡이 (docs/3d/qa_sample.js) — 동작을 멈춰 세우고 원하는 순간의 관절·기구 자리를 뽑아
    //      관절이 사람처럼 꺾였는지, 몸·기구가 서로 뚫고 지나가지 않는지 검사한다. 앱 화면에서는 쓰지 않는다.
    const bodyMeshes = new Set(); body.traverse(o => { if (o.isMesh) bodyMeshes.add(o); });
    me.qa = {
      cycle,
      pause(){ if (me.raf) cancelAnimationFrame(me.raf); me.raf = null; },
      seek(t){ poseAt(t); if (gear.update) gear.update(t, action.time); place(0); renderer.render(scene, camera); },
      joints(){ const o = {}; for (const b of boneList) { b.getWorldPosition(v); b.getWorldQuaternion(_q1); o[b.name] = [v.x, v.y, v.z, _q1.x, _q1.y, _q1.z, _q1.w].map(x => +x.toFixed(5)); } return o; },
      rest(){ const o = {}; for (const b of boneList) { const q = restQ.get(b); o[b.name] = [q.x, q.y, q.z, q.w].map(x => +x.toFixed(5)); } return o; },
      // 뼈마다 살 두께 — 묶인 자세에서 그 뼈에 가장 많이 붙은 꼭짓점들이 뼈 축에서 얼마나 떨어져 있나 (80% 지점)
      radii(){
        const out = {}, sc = body.scale.x;
        body.traverse(o => {
          if (!o.isSkinnedMesh) return;
          const g = o.geometry, pos = g.attributes.position, si = g.attributes.skinIndex, sw = g.attributes.skinWeight, sk = o.skeleton;
          const heads = sk.bones.map((b, i) => new T.Vector3().setFromMatrixPosition(_m1.copy(sk.boneInverses[i]).invert()));
          const tails = sk.bones.map((b, i) => { const c = b.children.find(x => x.isBone); const j = c ? sk.bones.indexOf(c) : -1; return j >= 0 ? heads[j] : null; });
          const dist = sk.bones.map(() => [[], [], []]);                  // [축에서의 거리, 옆(X) 거리, 앞뒤(Z) 거리]
          const p = new T.Vector3(), d = new T.Vector3(), e = new T.Vector3();
          for (let i = 0; i < pos.count; i++) {
            let best = 0, bw = -1; for (let k = 0; k < 4; k++) { const w = sw.getComponent(i, k); if (w > bw) { bw = w; best = si.getComponent(i, k); } }
            p.fromBufferAttribute(pos, i).applyMatrix4(o.bindMatrix);
            const a = heads[best], t = tails[best]; if (!a) continue;
            if (t) { d.subVectors(t, a); const L2 = d.lengthSq(); const s = L2 > 0 ? Math.max(0, Math.min(1, e.subVectors(p, a).dot(d) / L2)) : 0; e.copy(a).addScaledVector(d, s); }
            else e.copy(a);
            dist[best][0].push(p.distanceTo(e)); dist[best][1].push(Math.abs(p.x - e.x)); dist[best][2].push(Math.abs(p.z - e.z));
          }
          const pct = ds => { ds.sort((x, y) => x - y); return +(ds[Math.floor(ds.length * 0.8)] * sc).toFixed(4); };
          sk.bones.forEach((b, i) => { const ds = dist[i]; if (ds[0].length < 8) return; out[b.name] = ds.map(pct); });
        });
        return out;
      },
      // 기구: 상자는 자리·크기(OBB), 나머지는 꼭짓점 몇 개를 세상 좌표로
      gear(){
        const out = [];
        scene.traverse(o => {
          if (!o.isMesh || bodyMeshes.has(o) || o.userData.qaSkip) return;
          o.updateMatrixWorld(true); const g = o.geometry; const it = { kind: g.type, pts: [] };
          if (g.type === 'BoxGeometry') { g.computeBoundingBox(); it.obb = { m: o.matrixWorld.toArray().map(x => +x.toFixed(5)), min: g.boundingBox.min.toArray(), max: g.boundingBox.max.toArray() }; }
          else { const pos = g.attributes.position; const step = Math.max(1, Math.floor(pos.count / 300)); for (let i = 0; i < pos.count; i += step) { const q = new T.Vector3().fromBufferAttribute(pos, i).applyMatrix4(o.matrixWorld); it.pts.push([+q.x.toFixed(4), +q.y.toFixed(4), +q.z.toFixed(4)]); } }
          out.push(it);
        });
        return out;
      },
    };
    frame();
  }

  /* 스킨 메시가 든 장면 복제 — 뼈를 새로 잇고 스킨을 새 뼈에 다시 묶는다 (three 의 SkeletonUtils.clone 과 같은 일) */
  function cloneRig(lib, src){
    const { T } = lib;
    const out = src.clone(true);
    const srcNodes = [], outNodes = [];
    src.traverse(n => srcNodes.push(n)); out.traverse(n => outNodes.push(n));
    const pair = new Map(srcNodes.map((n, i) => [n, outNodes[i]]));
    out.traverse(n => {
      if (!n.isSkinnedMesh) return;
      const s = srcNodes[outNodes.indexOf(n)];
      const bones = s.skeleton.bones.map(b => pair.get(b) || b);
      n.bind(new T.Skeleton(bones, s.skeleton.boneInverses.map(m => m.clone())), n.bindMatrix);
    });
    return out;
  }

  function fallbackText(canvas, text){
    const ctx = canvas.getContext && canvas.getContext('2d');
    if (!ctx) return;
    const size = Math.max(160, Math.min(canvas.clientWidth || 320, 480));
    canvas.width = size; canvas.height = size;
    ctx.fillStyle = '#8E949C'; ctx.font = '13px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText(text, size / 2, size / 2);
  }

  /* ---- 돌리기 ---- 캔버스마다 하나씩. stop() 은 전부, stop(canvas) 는 그것만. */
  const actives = new Map();
  function start(canvas, id, { onNote, sex, model } = {}){
    if (!canvas || !id) return false;
    stop(canvas);
    const clipName = (TWEAKS[id] && TWEAKS[id].base) || (PROC[id] && PROC[id].base) || CLIPS[id] || FALLBACK_CLIP;
    const note = APPROX[id] || (PROC[id] ? PROC_NOTE : (CLIPS[id] ? '' : GAP_NOTE));
    if (onNote) onNote(LOADING_NOTE);
    const me = { canvas, id, dead: false, raf: null, renderer: null, scene: null, body: null, tpose: null };
    actives.set(canvas, me);
    loadLib()
      .then(lib => Promise.all([lib, loadModel(lib, sex, model), loadClip(lib, clipName, sex)]))
      .then(([lib, gltf, clip]) => {
        if (me.dead) return;
        me.body = lib.T.SkeletonUtils ? lib.T.SkeletonUtils.clone(gltf.scene) : cloneRig(lib, gltf.scene);
        me.tpose = (gltf.animations || []).find(a => a.duration < 0.05) || null;   // 한 프레임짜리 T 자세
        setup(lib, me, clip);
        if (onNote) onNote(note);
      })
      .catch(err => {
        console.warn('3D 동작을 못 불러왔어요', err);
        if (me.dead) return;
        if (onNote) onNote('3D 동작을 불러오지 못했어요'); else fallbackText(canvas, '3D 동작을 불러오지 못했어요');
      });
    return true;
  }
  function stop(canvas){
    for (const [c, me] of [...actives]) {
      if (canvas && c !== canvas) continue;
      me.dead = true;
      if (me.raf) cancelAnimationFrame(me.raf);
      // 장면의 GPU 자원은 돌려주되 렌더러(컨텍스트)는 캔버스에 남겨 둔다 — 다음 동작이 같은 캔버스에 그린다
      if (me.scene) me.scene.traverse(o => { if (o.geometry) o.geometry.dispose(); if (o.material) [].concat(o.material).forEach(m => m.dispose()); });
      if (me.renderer) { me.renderer.renderLists.dispose(); me.renderer.clear(); }
      actives.delete(c);
    }
  }

  const qa = canvas => { const me = actives.get(canvas); return me && me.qa; };   // 검사용 (docs/3d/qa_sample.js)
  return { start, stop, preload, qa, CLIPS, APPROX, TWEAKS, PROC, PROC_NOTE, GEAR, GRIP, GAP_NOTE, LOADING_NOTE, FALLBACK_CLIP, BASE, MODEL, SEX };
})();
