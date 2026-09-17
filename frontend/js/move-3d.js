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
    'barbell-squat': '스쿼트 동작에 바를 쥔 손만 맞췄어요',
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
  // 발등을 바닥에: 정강이는 앞면이 바닥을 보고 누워 있고, 발은 선 자세에서 정강이 선보다 앞(= 누우면 아래)으로 58° 나와 있다. 발바닥 굽힘 45° 면
  // 정강이 선보다 13° '아래'다 — 예전엔 12° '위'로 두었는데 그건 발바닥 굽힘 70° 라 사람 발목이 못 간다 (각도 검사는 부호를 못 봤다)
  const footBack = p => { const b = shinBack(p), l = Math.hypot(b[0], b[2]) || 1; return [b[0] / l * 0.974, -0.225, b[2] / l * 0.974]; };
  // 달리기: 동작 파일은 팔꿈치를 옆으로 35° 넘게 벌리고 뛴다(덩치 큰 캐릭터용) — 어깨선 기준으로 위팔의 '바깥' 성분과 아래팔의 '안쪽' 성분을
  // 줄여 팔을 몸 가까이 붙인다. 앞뒤로 흔드는 움직임은 그대로다 (리뷰: 러닝도 팔이 이상해)
  const tuck = (side, from, to, keep, inward) => p => {
    const a = p('mixamorig:' + side + from), b = p('mixamorig:' + side + to), l = p('mixamorig:LeftArm'), r = p('mixamorig:RightArm');
    const sgn = (side === 'Left' ? 1 : -1) * (inward ? -1 : 1), out = N((l.x - r.x) * sgn, (l.y - r.y) * sgn, (l.z - r.z) * sgn);   // 줄일 쪽: 위팔은 바깥, 아래팔은 안쪽
    const d = N(b.x - a.x, b.y - a.y, b.z - a.z), c = d[0] * out[0] + d[1] * out[1] + d[2] * out[2];
    return c > 0 ? d.map((x, i) => x - out[i] * c * (1 - keep)) : d;
  };
  const runArms = { 'mixamorig:LeftArm': { aim: tuck('Left', 'Arm', 'ForeArm', 0.55) }, 'mixamorig:RightArm': { aim: tuck('Right', 'Arm', 'ForeArm', 0.55) },          // 더 붙이면 여성은 손이 허벅지를 스친다 (검사)
                    'mixamorig:LeftForeArm': { aim: tuck('Left', 'ForeArm', 'Hand', 0.8, true) }, 'mixamorig:RightForeArm': { aim: tuck('Right', 'ForeArm', 'Hand', 0.8, true) } };
  const TWEAKS = {
    'run': { bones: runArms },
    'knee-pushup': { bones: { 'mixamorig:LeftUpLeg': { aim: thighToFloor('Left') }, 'mixamorig:RightUpLeg': { aim: thighToFloor('Right') },
                              'mixamorig:LeftLeg': { aim: shinBack }, 'mixamorig:RightLeg': { aim: shinBack }, 'mixamorig:LeftFoot': { aim: footBack }, 'mixamorig:RightFoot': { aim: footBack },
                              'mixamorig:LeftToeBase': { rest: true }, 'mixamorig:RightToeBase': { rest: true } } },   // 발끝으로 버티던 푸시업의 젖혀진 발가락을 편다
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
  // 골반뼈 위(허리)에 — 고관절 높이면 허벅지를 뚫는다. 손가락은 앞·아래로 허리를 감싸고 손바닥은 몸 쪽 —
  // 예전엔 손이 아래팔 방향 그대로 이어져 허리 앞에 떠 보였다 (리뷰)
  // 손목은 골반뼈 옆·살짝 뒤, 손가락은 앞·안쪽·아래로 골반 앞을 감싸고(몸의 곡면을 따라 안쪽으로 꺾인다) 손바닥은 척추 쪽 —
  // 손가락이 앞으로만 뻗으면 손이 배 앞에 떠 보였다 (런지, 리뷰)
  const handsOnHips = (C, y = 0.12, x = 0.18, hand = true) => ({ [L + 'Arm']: { ik: () => add(C.pos('mixamorig:Hips'), [x, y, -0.01]), bend: [1, -0.2, -0.7] },
                                                [R + 'Arm']: { ik: () => add(C.pos('mixamorig:Hips'), [-x, y, -0.01]), bend: [-1, -0.2, -0.7] },
                                                ...(hand ? { [L + 'Hand']: { aim: N(-0.5, -0.45, 0.74), palm: [-0.8, 0.1, -0.6] }, [R + 'Hand']: { aim: N(0.5, -0.45, 0.74), palm: [0.8, 0.1, -0.6] } } : {}) });   // (선 자세 기준 — 숙인 자세는 끈다)
  const STAND = { pos: [0, 1.03, 0], up: [0, 1, 0], front: [0, 0, 1] };
  const LIE = { pos: [0, 0.11, 0], up: [0, 0, -1], front: [0, 1, 0] };     // 바로 누움: 머리는 -Z 쪽, 배는 위
  const both = (up, leg, foot) => ({ [L + 'UpLeg']: up, [L + 'Leg']: leg, [L + 'Foot']: foot, [R + 'UpLeg']: up, [R + 'Leg']: leg, [R + 'Foot']: foot });
  const FLAT = N(0, -0.53, 0.85);                                                    // 평평하게 디딘 발 뼈의 방향
  // 뒤통수 받치기: 머리 관절은 두개골 밑(목 위)이라, 머리 축(목→머리)으로 9cm 올라간 머리 가운데의 뒤쪽 7.5cm 가 뒤통수다.
  // 손목은 그 양옆 7.5cm, 손가락은 가운데로 감싼다. sgn 은 왼손 +1 / 오른손 -1 (바로 누운 몸의 왼쪽은 +X)
  const occiput = (C, sgn) => {
    const h = C.pos('mixamorig:Head'), n = C.pos('mixamorig:Neck');
    const up = N(h.x - n.x, h.y - n.y, h.z - n.z), front = N(0, -up[2], up[1]);                          // 좌우로 기울지 않은 머리: 앞 = 왼쪽(+X) × 위
    const o = [h.x + up[0] * 0.09 - front[0] * 0.075, h.y + up[1] * 0.09 - front[1] * 0.075, h.z + up[2] * 0.09 - front[2] * 0.075];
    const wrist = [o[0] + sgn * 0.075, o[1] + front[1] * 0.01, o[2] + front[2] * 0.01];
    return { wrist, hand: [o[0] - sgn * 0.03 - wrist[0], o[1] + up[1] * 0.03 - wrist[1], o[2] + up[2] * 0.03 - wrist[2]],
             palm: [h.x + up[0] * 0.09 - wrist[0], h.y + up[1] * 0.09 - wrist[1], h.z + up[2] * 0.09 - wrist[2]] };   // 손바닥은 머리 가운데를 본다
  };
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
    : (v && typeof v === 'object') ? { ...v, aim: v.aim && (typeof v.aim === 'function' ? (p => flipX(v.aim(mirrorLookup(p)))) : flipX(v.aim)), front: v.front && flipX(v.front), ik: v.ik && (typeof v.ik === 'function' ? (p => flipX(v.ik(mirrorLookup(p)))) : flipX(v.ik)), bend: v.bend && flipX(v.bend), palmTo: Array.isArray(v.palmTo) ? flipX(v.palmTo) : v.palmTo, palm: Array.isArray(v.palm) ? flipX(v.palm) : (typeof v.palm === 'function' ? (p => flipX(v.palm(mirrorLookup(p)))) : v.palm), roll: v.roll && -v.roll } : v;
  const mirror = t => { const o = {}; for (const [k, v] of Object.entries(t)) o[swapSide(k)] = flipX(v); return o; };
  const blend = (a, b, k) => { const o = {}; for (const n of new Set([...Object.keys(a), ...Object.keys(b)])) { const x = a[n], y = b[n]; o[n] = (x === undefined) ? y : (y === undefined) ? x : mixHow(x, y, k); } return o; };
  const asObj = v => Array.isArray(v) ? { aim: v } : v;                     // 방향 배열과 IK 를 섞을 땐 배열을 { aim } 로
  const mixHow = (x, y, k) => {
    if (Array.isArray(x) && Array.isArray(y)) return N(...mix(x, y, k));
    if (x && y && typeof x === 'object' && typeof y === 'object') {
      x = asObj(x); y = asObj(y);
      const o = { ...(k < 0.5 ? x : y) };
      for (const f of ['aim', 'front', 'bend', 'palmTo', 'palm']) {                                                    // 손바닥 방향도 섞는다 — 절반에서 홱 뒤집히지 않게
        const a = x[f], b = y[f], dir = v => Array.isArray(v) || typeof v === 'function';
        if (Array.isArray(a) && Array.isArray(b)) o[f] = N(...mix(a, b, k));
        else if (dir(a) && dir(b)) o[f] = p => N(...mix(typeof a === 'function' ? a(p) : a, typeof b === 'function' ? b(p) : b, k));   // 뼈 자리를 보고 정하는 방향(함수)도
      }
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
  const BACKBAR = [0, -0.005, -0.08];                                        // 등에 멘 바: 목 관절에서 등(Spine2) 기준 뒤·아래 — 승모근 위
  const LEGPRESS = { dir: N(0.6, 0.8, 0) };                                  // 발판 쪽 (앞·위 53°)
  const WALL_X = 0.56;                                                      // 종아리 스트레칭의 벽 (캐릭터 왼쪽, +X)

  const PROC = {
    // 플랭크(팔꿈치 플랭크): 팔꿈치는 어깨 바로 아래 바닥에, 아래팔은 나란히 앞으로 손바닥 아래. 머리부터 뒤꿈치까지 한 직선(어깨 높이는
    // 위팔 길이만큼, 발목 0.1 — 10~13° 기울기), 발끝을 세워 발볼로 딛는다. 숨 쉬는 만큼만 움직인다. 모션캡처 'Plank' 는 팔을 편 하이 플랭크라 쓰지 않는다.
    'plank': { base: 'lying', period: 4, still: true, pose: (u, C) => {
      const S = C.pos(L + 'Arm'), E = C.pos(L + 'ForeArm'), Hd = C.pos(L + 'Hand');
      const l1 = Math.hypot(S.x - E.x, S.y - E.y, S.z - E.z), l2 = Math.hypot(E.x - Hd.x, E.y - Hd.y, E.z - Hd.z);   // 위팔·아래팔 길이 (남·여가 다르다)
      // 팔꿈치가 바닥(살 두께 4cm)에 놓이려면 어깨가 정확히 (위팔 길이 + 4cm) 높이에, 손은 팔꿈치에서 아래팔 길이만큼 앞에 있어야 한다.
      // 어깨는 엉덩이에서 척추 축으로 0.37 위, 배 쪽으로 0.04 벗어나 있어 몸 기울기(sn = (hy-0.1)/0.9)에 따라 엉덩이보다 0.37·sn - 0.04 높다 —
      // 그 식을 hy 로 풀었다. 예전엔 엉덩이를 위팔 길이로 둬 팔꿈치가 바닥에서 3cm 떠 아래팔이 기울었다 (리뷰)
      const hy = Math.max(0.2, (l1 + 0.04 + 0.039 + 0.37 * 0.1 / 0.9) / (1 + 0.37 / 0.9));
      const sn = Math.max(0.05, Math.min(0.35, (hy - 0.1) / 0.9)), cs = Math.sqrt(1 - sn * sn);                     // 엉덩이 높이 → 몸 기울기
      const up = [0, sn, -cs], down = [0, -sn, cs], front = [0, -1, 0];
      // 손은 어깨 앞 아래팔 길이만큼, 바닥에 — 팔꿈치가 어깨 바로 아래 바닥에 온다. 손 방향은 아래에서 통째로 정하니 여기에 palmTo 를 또 주지 않는다:
      // IK 단계의 palmTo 는 '그 전에 놓인 손'을 보고 아래팔을 돌리는데, 손은 곧 다시 놓이므로 아래팔만 엉뚱하게 100° 돌아가 오른 손목이 170° 꼬였다 (리뷰: 플랭크 손목)
      const arm = side => ({ ik: () => { const P = C.pos(side + 'Arm'); return [P.x, 0.045, P.z - l2]; }, bend: [0, -1, 0.2] });
      return { root: { pos: [0, hy + 0.005 * Math.sin(u * Math.PI * 2), 0], up, front },
        bones: { ...spineAll(up, N(0, sn - 0.1, -cs), front), [L + 'Arm']: arm(L), [R + 'Arm']: arm(R), [L + 'Hand']: { aim: [0, 0, -1], palm: [0, -1, 0] }, [R + 'Hand']: { aim: [0, 0, -1], palm: [0, -1, 0] },   // 손은 앞으로 뻗고 손바닥은 바닥에 (리뷰)
          ...both(down, down, N(0, -0.62, 0.78)) } };                                                         // 발끝 세움 (발등 굽힘 30°쯤)
    } },
    // 자유형: 엎드려 뜬 채 팔을 번갈아 — 물속에서 팔꿈치를 높게 두고 손으로 몸 아래를 지나 엉덩이까지 밀고(캐치→풀→푸시),
    // 물 밖으로 팔꿈치를 높게 들어 앞으로 되돌려 다시 넣는다. 되돌리는 팔 쪽 어깨가 올라오게 몸통이 40° 굴러가고, 숨은 왼팔을 되돌릴 때 왼쪽으로.
    // 다리는 뻗은 채 엉덩이에서 작게 찬다(발끝은 뻗고). 모션캡처 'Swimming' 은 평영처럼 보여 쓰지 않는다. (머리는 -Z 쪽, 물은 y 0.15)
    'swim': { base: 'lying', period: 2.4, gear: 'water', still: true, pose: (u, C) => {
      const r = -40 * D * Math.sin(u * Math.PI * 2);                                                                    // 굴림: 왼팔이 물 밖일 때(u 0.5~1) 왼쪽 어깨가 올라온다
      const upv = [Math.sin(r), Math.cos(r), 0], leftv = [-Math.cos(r), Math.sin(r), 0], front = [-Math.sin(r), -Math.cos(r), 0];   // 엎드리면 캐릭터의 왼쪽은 -X
      const PATH = [[0, 0.1, -0.05, -0.5], [0.15, 0.1, -0.25, -0.35], [0.35, 0.05, -0.32, 0], [0.5, 0.15, -0.15, 0.35], [0.62, 0.3, 0.12, 0.3], [0.8, 0.32, 0.15, -0.15], [1, 0.1, -0.05, -0.5]];   // [진행, 바깥, 위, 뒤] 어깨 기준. 되돌리기는 팔꿈치를 높게 — 팔을 편 되돌리기로 바꿨다가 예전이 낫다고 해 되돌렸다 (리뷰)
      const arm = (side, ph, sgn) => {
        ph = ((ph % 1) + 1) % 1; let i = 0; while (PATH[i + 1][0] < ph) i++;
        const a = PATH[i], b = PATH[i + 1], t = sstep((ph - a[0]) / (b[0] - a[0]));
        const x = mix(a[1], b[1], t) * sgn, y = mix(a[2], b[2], t), z = mix(a[3], b[3], t);
        return { ik: () => { const S = C.pos(side + 'Arm'); return [S.x + x, S.y + y, S.z + z]; },
          bend: [sgn, 0.8, 0] };                                                                                       // 팔꿈치는 바깥·위(높게)
        // 손바닥 방향은 따로 정하지 않는다 — 아래팔을 위팔에 대해 비틀지 않은 채(경첩 맞추기) 팔꿈치만 높게 두면 손바닥은 저절로 뻗을 땐 아래·바깥,
        // 당길 땐 뒤(발 쪽 — 물을 민다), 밀어 끝낼 땐 뒤·위, 되돌릴 땐 뒤·아래를 본다. 전엔 '물속 = 뒤, 물 밖 = 아래'를 palmTo 로 주었는데, 다 밀어 팔이
        // 뒤로 뻗는 순간 목표(뒤)가 아래팔과 나란해져 비틀 각이 ±180° 를 오가며 아래팔이 한 프레임에 90~200° 뒤집혔다 (리뷰 3차 떨림 측정)
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
    // 바벨 스쿼트: 몸은 모션캡처 그대로, 손만 등에 멘 바를 쥔다. 바는 숙인 등을 따라 움직이는데(기구 backbar) 손은 동작 파일의 자리에
    // 남아 앉을 때 바와 어긋났다 — 손목을 바의 쥘 자리 아래에 두고 손가락은 바를 넘어 감싼다 (손바닥은 앞·위)
    'barbell-squat': { base: 'barbell-squat', period: 2.27, gear: 'backbar', fist: true, pose: (u, C) => {
      const off = C.carry('mixamorig:Spine2', BACKBAR);
      const up = N(...C.carry('mixamorig:Spine2', [0, 0.94, -0.34])), palm = N(...C.carry('mixamorig:Spine2', [0, 0.34, 0.94]));
      // 쥘 자리는 IK 를 풀 때(빗장뼈를 제자리에 놓은 뒤) 셈한다 — 자세를 만들 때 미리 어깨 관절 자리를 읽으면, 그 자리가 앞 프레임에 우리가 놓은
      // 것인지 동작 파일이 막 덮어쓴 것인지에 따라 달라져 손이 한 프레임씩 4cm 튀었다 (리뷰: 잔 떨림). 바의 방향은 기구와 같이 빗장뼈 뿌리로 잰다
      const arm = (side, sgn) => ({ bend: C.carry('mixamorig:Spine2', [sgn * 0.25, -1, -0.15]), ik: p => {
        const n = p('mixamorig:Neck'), lc = p(L + 'Shoulder'), rc = p(R + 'Shoulder'), ls = p(L + 'Arm'), rs = p(R + 'Arm');
        const ax = N(lc.x - rc.x, lc.y - rc.y, lc.z - rc.z), half = ls.distanceTo(rs) / 2 + 0.22, k = C.along(side === L ? 'Left' : 'Right');   // 어깨너비보다 한 뼘 넓게
        return [0, 1, 2].map(i => [n.x, n.y, n.z][i] + off[i] + ax[i] * sgn * half - up[i] * k - palm[i] * 0.024); } });
      return { bones: { [L + 'Arm']: arm(L, 1), [R + 'Arm']: arm(R, -1), [L + 'Hand']: { aim: up, palm }, [R + 'Hand']: { aim: up, palm } } };
    } },
    // 브리지: 누워 무릎 세우고, 뒤꿈치로 밀어 무릎–엉덩이–어깨가 한 직선. 위에서 1~2초 조인다
    'bridge': { base: 'lying', period: 3.6, still: true, pose: u => {
      const k = hold(u, 0.1, 0.4, 0.58, 0.9);
      const up = N(...mix([0, 0, -1], [0, -0.42, -0.91], k)), front = N(...mix([0, 1, 0], [0, 0.91, -0.42], k));   // 어깨는 바닥에 둔 채 엉덩이만 올라간다
      return { root: { pos: mix([0, 0.11, 0], [0, 0.3, -0.02], k), up, front },
        bones: { ...spineAll(up, [0, 0.05, -1]),
          [L + 'UpLeg']: { ik: [0.094, 0.09, 0.4], bend: [0, 1, 0] }, [L + 'Foot']: FLAT,                                  // 발은 엉덩이 가까이 바닥에 고정 — 위에선 무릎이 발목 위(정강이 수직)
          [R + 'UpLeg']: { ik: [-0.094, 0.09, 0.4], bend: [0, 1, 0] }, [R + 'Foot']: FLAT,
          // 팔은 옆에 뻗어 손바닥 바닥 — 손목을 바닥의 한 자리에 박아 둔다 (방향으로만 겨누면 엉덩이를 올릴 때 어깨가 움직여 손이 4cm 쯤 미끄러지고 돌아가 보였다, 리뷰)
          // 자리는 어깨 옆 15cm · 엉덩이 옆 — 팔 길이의 95% 쯤이라 팔꿈치가 살짝만 굽는다 (어깨너비가 남·여 달라 어깨에서 잰다. 어깨의 x 는 동작 내내 같다)
          [L + 'Arm']: { ik: p => [p(L + 'Arm').x + 0.15, 0.035, 0.07], bend: [1, 0.1, -0.1] }, [L + 'Hand']: { aim: N(0.2, -0.02, 0.98), palm: [0, -1, 0] },
          [R + 'Arm']: { ik: p => [p(R + 'Arm').x - 0.15, 0.035, 0.07], bend: [-1, 0.1, -0.1] }, [R + 'Hand']: { aim: N(-0.2, -0.02, 0.98), palm: [0, -1, 0] } } };
    } },
    // 데드버그: 누워 팔은 천장, 엉덩이·무릎 90°. 한 팔은 머리 위로, 반대 다리는 앞으로 천천히 — 허리는 바닥에
    'dead-bug': { base: 'lying', period: 5.2, still: true, pose: u => {
      const side = u < 0.5 ? 0 : 1, a = hold(u - side * 0.5, 0.04, 0.24, 0.3, 0.48);
      const neutral = { ...both([0, 1, 0.08], [0, 0.05, 1], N(0, 0.85, 0.53)), [L + 'Arm']: [0.05, 1, 0], [L + 'ForeArm']: { aim: [0, 1, 0], palmTo: [-1, 0, 0] }, [R + 'Arm']: [-0.05, 1, 0], [R + 'ForeArm']: { aim: [0, 1, 0], palmTo: [1, 0, 0] } };   // 손바닥은 서로 마주 보게 — 바깥을 보면 어색하다 (리뷰)
      const moved = { [R + 'Arm']: N(-0.15, 0.2, -0.97), [R + 'ForeArm']: { aim: N(-0.1, 0.1, -0.99), palmTo: [1, 0, 0] }, [L + 'UpLeg']: N(0, 0.35, 0.94), [L + 'Leg']: N(0, 0.2, 0.98), [L + 'Foot']: N(0, 0.95, 0.32) };   // 머리 위로 넘어가도 손바닥은 안쪽
      return { root: LIE, bones: { ...spineAll([0, 0, -1]), ...blend(neutral, side ? mirror(moved) : moved, a) } };
    } },
    // 크런치: 머리와 어깨만 말아 올린다 — 허리는 바닥에, 손은 뒤통수(당기지 않는다), 턱은 살짝 당긴 채
    'crunch': { base: 'lying', period: 2.6, still: true, pose: (u, C) => {
      const c = hold(u, 0.1, 0.4, 0.5, 0.85);
      return { root: LIE, bones: { ...kneesUp,
        'mixamorig:Spine': N(...mix([0, 0, -1], [0, 0.12, -0.99], c)), 'mixamorig:Spine1': N(...mix([0, 0, -1], [0, 0.42, -0.9], c)), 'mixamorig:Spine2': N(...mix([0, 0, -1], [0, 0.7, -0.72], c)),
        'mixamorig:Neck': N(...mix([0, 0.05, -1], [0, 0.8, -0.6], c)), 'mixamorig:Head': N(...mix([0, 0.05, -1], [0, 0.85, -0.53], c)),
        // 손은 뒤통수를 받쳐 쥐듯: 손목은 뒤통수 옆·바닥 쪽(누워 있으니 뒤통수는 아래), 손바닥은 머리를 보고, 손가락은 가운데로 감싼다. 팔꿈치는 옆으로 넓게 (리뷰·참고 영상)
        [L + 'Arm']: { ik: () => occiput(C, 1).wrist, bend: [1, 0.35, 0.3] }, [L + 'Hand']: { aim: () => occiput(C, 1).hand, palm: () => occiput(C, 1).palm },
        [R + 'Arm']: { ik: () => occiput(C, -1).wrist, bend: [-1, 0.35, 0.3] }, [R + 'Hand']: { aim: () => occiput(C, -1).hand, palm: () => occiput(C, -1).palm } } };
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
    // 숄더프레스(앉아서 덤벨): 벤치 끝에 앉아 발은 바닥, 상체 곧게. 덤벨은 귀 높이에서 팔꿈치 90°(어깨보다 살짝 앞), 손바닥은 앞.
    // 어깨 위로 곧장 밀어 팔을 거의 펴고(잠그지 않는다) 덤벨이 위에서 살짝 모인다. 천천히 귀 높이로 내린다 (리뷰·참고 영상).
    // 예전엔 서서 손바닥을 머리 쪽으로 돌려 아래팔이 크게 비틀려 어깨·겨드랑이·팔꿈치 살이 깨져 보였다
    'shoulder-press': { base: 'idle', period: 2.6, gear: 'seatpress', fist: true, still: true, pose: u => {
      const p = hold(u, 0.05, 0.42, 0.5, 0.92);
      return { root: { pos: [0, 0.6, 0], up: [0, 1, 0], front: [0, 0, 1] },                                        // 벤치 위 0.45 에 앉는다
        bones: { ...spineAll([0, 1, 0]),
          [L + 'UpLeg']: N(0.2, 0, 0.98), [L + 'Leg']: N(0.03, -1, 0.02), [L + 'Foot']: FLAT, [R + 'UpLeg']: N(-0.2, 0, 0.98), [R + 'Leg']: N(-0.03, -1, 0.02), [R + 'Foot']: FLAT,
          [L + 'Arm']: N(...mix([0.85, -0.3, 0.42], [0.22, 0.96, 0.15], p)), [L + 'ForeArm']: { aim: N(...mix([0.05, 0.99, 0.1], [0.02, 1, 0.02], p)), palmTo: [0, 0, 1] },
          [R + 'Arm']: N(...mix([-0.85, -0.3, 0.42], [-0.22, 0.96, 0.15], p)), [R + 'ForeArm']: { aim: N(...mix([-0.05, 0.99, 0.1], [-0.02, 1, 0.02], p)), palmTo: [0, 0, 1] } } };
    } },
    // 한 발 서기: 손은 허리, 한 발을 바닥에서 든다(무릎 살짝 굽힘), 딛는 무릎은 잠그지 않는다, 시선은 앞
    'one-leg': { base: 'idle', period: 6, pose: (u, C) => ({
      root: { dpos: [-0.04 + 0.01 * Math.sin(u * Math.PI * 4), 0, 0] },
      bones: { ...spineAll([0, 1, 0]), ...handsOnHips(C), [L + 'UpLeg']: N(0.02, -0.94, 0.34), [L + 'Leg']: N(0, -0.8, -0.6), [L + 'Foot']: N(0, -0.7, 0.7) } }) },
    // 복식 호흡: 누워 무릎을 세우고(설명의 '처음' 자세) 한 손은 가슴, 한 손은 배 — 들이마실 때 배 손만 올라온다. 예전엔 서 있었다 (리뷰)
    'deep-breath': { base: 'lying', period: 6, still: true, pose: (u, C) => {
      const b = 0.5 - 0.5 * Math.cos(u * Math.PI * 2);                                                            // 0 → 1 → 0: 들이마시고 내쉰다
      return { root: LIE, bones: { ...spineAll([0, 0, -1]), ...kneesUp,
        // 손은 몸 위(가슴 살 두께 0.14)에 얹고 팔꿈치는 옆 바닥 쪽으로 — 손이 어깨에 너무 가까우면 팔꿈치가 접혀 살이 꼬이니 손은 아래쪽(명치·아랫배)에
        [R + 'Arm']: { ik: () => add(C.pos('mixamorig:Spine1'), [-0.04, 0.145, 0.03]), bend: [-1, -0.1, 0.15], palmTo: [0, -1, 0] },                   // 명치 위
        [L + 'Arm']: { ik: () => add(C.pos('mixamorig:Spine'), [0.05, 0.13 + 0.025 * b, 0.04]), bend: [1, -0.1, 0.15], palmTo: [0, -1, 0] } } };   // 배꼽 위 — 숨 따라 2.5cm 오르내린다 (더 아래면 세운 허벅지에 닿는다)
    } },
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
      // 손은 옆구리 앞(쉴 때)과 머리 위 반대편 귀 쪽(얹을 때)을 오간다. 곧장 가면 가슴을 뚫고 지나가서, 어깨 바깥의 경유점을 지나는
      // 굽은 길(2차 베지어)로 돈다. 얹은 손바닥은 머리를 감싼다 (누르지 않는다)
      const sgn = side => (side === L ? 1 : -1);
      const rest = side => add(C.pos('mixamorig:Hips'), [0.24 * sgn(side), 0.02, 0.16]);
      const via = side => add(C.pos(side + 'Arm'), [0.32 * sgn(side), 0.18, 0.1]);                                    // 어깨 바깥·위 — 가슴 앞을 가로지르지 않고 팔꿈치도 덜 접힌다
      const crown = () => { const h = C.pos('mixamorig:Head'), n = C.pos('mixamorig:Neck'), u = N(h.x - n.x, h.y - n.y, h.z - n.z); return { h, u }; };   // 머리 축(목→머리)
      const top = side => { const { h, u } = crown(); return [h.x + u[0] * 0.2 + 0.035 * sgn(side), h.y + u[1] * 0.2 + 0.015, h.z + u[2] * 0.2 + 0.02]; };   // 손목은 정수리 위, 제 쪽으로 조금 — 팔꿈치가 아니라 손바닥이 얹힌다 (리뷰)
      const drape = side => ({ aim: p => { const { h, u } = crown(), w = p(side + 'Hand'); return [h.x + u[0] * 0.13 - 0.1 * sgn(side) - w.x, h.y + u[1] * 0.13 - w.y, h.z + u[2] * 0.13 + 0.02 - w.z]; },
                               palm: p => { const { h, u } = crown(), w = p(side + 'Hand'); return [h.x + u[0] * 0.1 - w.x, h.y + u[1] * 0.1 - w.y, h.z + u[2] * 0.1 - w.z]; } });   // 손가락은 반대편 귀 위쪽으로 내려간다
      const bez = (a, b, c, w) => a.map((_, i) => (1 - w) * (1 - w) * a[i] + 2 * (1 - w) * w * b[i] + w * w * c[i]);
      const armAt = (side, w) => ({ ik: () => bez(rest(side), via(side), top(side), w), bend: N(...mix([0.9 * sgn(side), -0.4, -0.2], [0.7 * sgn(side), 0.6, 0.4], w)) });
      // 손은 내려와 있을 땐 아래팔을 잇고 손바닥은 몸 쪽, 머리에 가까워질수록 머리를 감싸는 쪽으로 서서히 — 0.9 에서 켜고 끄면 손이 한 프레임에 100° 돌았다 (리뷰: 잔 떨림)
      const handAt = (side, w) => { const k = ramp(w, 0.55, 1), d = drape(side);
        return { aim: p => { const e = p(side + 'ForeArm'), h = p(side + 'Hand'); return mix(N(h.x - e.x, h.y - e.y, h.z - e.z), N(...d.aim(p)), k); },
                 palm: p => mix(N(-0.8 * sgn(side), 0, -0.6), N(...d.palm(p)), k) }; };
      const right = { 'mixamorig:Neck': N(-0.15, 0.99, 0), 'mixamorig:Head': N(-0.5, 0.87, 0) };
      const left = { 'mixamorig:Neck': N(0.15, 0.99, 0), 'mixamorig:Head': N(0.5, 0.87, 0) };
      // 앞 절반(s = 1)은 왼손이 머리에 있으니 머리는 왼 어깨로(left), 뒤 절반은 오른 어깨로 — 예전엔 반대로 기울었다 (리뷰)
      return { bones: { 'mixamorig:Spine': [0, 1, 0], 'mixamorig:Spine1': [0, 1, 0], 'mixamorig:Spine2': [0, 1, 0], ...blend(right, left, s),
        [L + 'Arm']: armAt(L, upL), [R + 'Arm']: armAt(R, upR), [L + 'Hand']: handAt(L, upL), [R + 'Hand']: handAt(R, upR) } };                                              // 손은 아래팔을 따라 머리 위에 얹힌다 — 손가락을 따로 내리면 손목이 100° 넘게 꺾였다
    } },
    // 고관절 스트레칭(반무릎): 뒷무릎은 엉덩이 아래, 상체는 곧게, 손은 허리. 골반을 말고 2~3cm 앞으로 옮긴다
    'hip-stretch': { base: 'kneel', period: 6, pose: (u, C) => ({
      root: { pos: [0, 0.55, 0.04 * hold(u, 0.15, 0.4, 0.6, 0.85)], up: [0, 1, 0], front: [0, 0, 1] },
      bones: { ...spineAll([0, 1, 0]), ...handsOnHips(C, 0.16, 0.21),
        [L + 'UpLeg']: N(0, 0.04, 1), [L + 'Leg']: N(0, -0.92, 0.39), [L + 'Foot']: FLAT,                           // 앞다리: 고관절·무릎 90° 가까이, 발은 평평
        [R + 'UpLeg']: N(0, -0.99, -0.15), [R + 'Leg']: [0, 0, -1], [R + 'Foot']: N(0, -0.25, -0.97) } }) },      // 뒷다리: 무릎은 바닥, 정강이는 뒤로 눕고 발등이 바닥
    // 햄스트링 스트레칭(선 자세): 한 발 앞에 뒤꿈치, 발끝 위로, 다리는 편 채. 엉덩이를 빼며 등을 평평하게 숙인다
    'hamstring-stretch': { base: 'idle', period: 6, pose: (u, C) => {
      const h = hold(u, 0.1, 0.35, 0.65, 0.9), th = mix(10, 45, h) * D;                                                  // 엉덩이에서 접는 각 — 등은 평평한 채
      const up = [0, Math.cos(th), Math.sin(th)], front = [0, -Math.sin(th), Math.cos(th)];
      // 다리 길이·골반 너비는 리깅마다 달라 잰다. 앞발 뒤꿈치와 뒷발은 바닥에 박아 두고 엉덩이만 뒤·아래로 뺀다:
      // 앞다리가 '곧게 편 채' 뒤꿈치가 바닥에 닿는 엉덩이 높이를 다리 길이에서 풀고, 뒷다리는 IK 로 무릎이 앞으로 굽는다.
      // (예전엔 뒷다리 허벅지를 뒤로·정강이를 앞으로 겨눠 무릎이 거꾸로 꺾였다 — 리뷰 "더 개판")
      const hip = C.pos(L + 'UpLeg'), knee = C.pos(L + 'Leg'), ankle = C.pos(L + 'Foot'), mid = C.pos('mixamorig:Hips');
      const leg = (hip.distanceTo(knee) + knee.distanceTo(ankle)) * 0.997, half = Math.abs(hip.x - mid.x), drop0 = Math.abs(mid.y - hip.y) || 0.047;
      const HEEL_Y = 0.1, FRONT_Z = 0.27, BACK_Z = -0.1, zH = mix(0, -0.12, h);                                          // 뒤꿈치만 디딘 발목 높이, 앞·뒷발 자리, 엉덩이가 빠지는 거리
      const jz = zH - drop0 * Math.sin(th), dz = FRONT_Z - jz, dx = 0.02;                                                // 고관절은 골반뼈에서 drop0 아래 (숙이면 그만큼 뒤로 돈다)
      const drop = Math.sqrt(Math.max(0.01, leg * leg - dz * dz - dx * dx)), rootY = HEEL_Y + drop + drop0 * Math.cos(th);
      const straight = N(dx, -drop, dz);
      // 손은 제 쪽 허벅지 위에: 서 있을 땐 엉덩이 가까이, 숙일수록 무릎 쪽으로 미끄러진다 (팔 길이 안에서). 오른손을 왼 허벅지로 넘기면 골반을 스쳤다
      const thigh = (side, p) => { const a = p(side + 'UpLeg'), b = p(side + 'Leg');
        const d = N(b.x - a.x, b.y - a.y, b.z - a.z), k = 0.5 * d[1] + 0.85 * d[2], n = N(-k * d[0], 0.5 - k * d[1], 0.85 - k * d[2]);   // 허벅지 축에 수직인 앞·위쪽 — 선 허벅지는 앞면, 뻗은 허벅지는 윗면
        return { a, b, d, n }; };
      const onThigh = (side, t0, t1) => p => { const { a, b, n } = thigh(side, p), t = mix(t0, t1, h);
        return [mix(a.x, b.x, t) + n[0] * 0.125, mix(a.y, b.y, t) + n[1] * 0.125, mix(a.z, b.z, t) + n[2] * 0.125]; };   // 허벅지 살(9~10cm) + 손목 두께 — 손바닥이 살에 닿는다
      // 손은 허벅지를 따라 무릎 쪽으로 눕히고 손바닥은 허벅지를 본다 — 손을 아래팔 방향 그대로 두면 손가락이 허벅지를 파고든다 (여성 6cm, 검사)
      const flat = side => ({ aim: p => { const { d, n } = thigh(side, p); return [d[0] + n[0] * 0.12, d[1] + n[1] * 0.12, d[2] + n[2] * 0.12]; }, palm: p => thigh(side, p).n.map(x => -x) });
      return { root: { pos: [0, rootY, zH], up, front },
        bones: { ...spineAll(up, N(0, Math.cos(th * 0.75), Math.sin(th * 0.75))),
          [L + 'UpLeg']: straight, [L + 'Leg']: straight, [L + 'Foot']: N(0, 0.2, 0.98),                                  // 앞다리 곧게 앞으로, 뒤꿈치만 바닥에 발끝은 위로 (참고 영상)
          [R + 'UpLeg']: { ik: [-half - 0.01, 0.086, BACK_Z], bend: [0, 0, 1] }, [R + 'Foot']: FLAT,                       // 뒷다리는 엉덩이 아래에 디딘 채 무릎이 앞으로 굽는다
          [L + 'Arm']: { ik: onThigh(L, 0.3, 0.62), bend: [1, 0.1, -0.6] }, [R + 'Arm']: { ik: onThigh(R, 0.25, 0.5), bend: [-1, 0.1, -0.6] },
          [L + 'Hand']: flat(L), [R + 'Hand']: flat(R) } };
    } },
    // 종아리 스트레칭(벽): 벽에 손을 대고 한 발을 뒤로. 뒷다리는 곧게, 뒤꿈치는 바닥에. 앞무릎을 굽히며 몸을 앞으로 기울인다
    // (옆에서 보이게 벽은 +X 쪽에 두고 그쪽을 본다)
    'calf-stretch': { base: 'idle', period: 6, gear: 'wall', open: true, pose: u => {
      const c = hold(u, 0.1, 0.4, 0.6, 0.9), up = N(0.34, 0.94, 0), flatX = N(0.85, -0.53, 0);                    // 벽(+X) 쪽을 보고 평평하게 디딘 발
      return { root: { pos: [mix(-0.1, -0.16, c), 0.95, 0], up, front: N(0.94, -0.34, 0) },
        bones: { ...spineAll(up, N(0.2, 1, 0), N(0.94, -0.34, 0)),
          // 손바닥을 벽에 짚는다: 손목은 벽 앞 2cm, 어깨 높이, 팔꿈치는 살짝 굽혀 아래로, 손은 벽을 따라 위로(손가락 위) — 예전엔 팔을 벽에 곧게 꽂아
          // 손가락이 벽을 뚫고 손바닥 방향이 팔 축과 겹쳐 아래팔 비틀림이 제멋대로였다 (리뷰)
          [L + 'Arm']: { ik: [WALL_X - 0.02, 1.27, -0.17], bend: [0, -1, 0] }, [L + 'Hand']: { aim: N(0.12, 0.99, 0), palm: [1, 0, 0] },          // +X 를 보는 몸의 왼쪽은 -Z
          [R + 'Arm']: { ik: [WALL_X - 0.02, 1.27, 0.17], bend: [0, -1, 0] }, [R + 'Hand']: { aim: N(0.12, 0.99, 0), palm: [1, 0, 0] },
          [L + 'UpLeg']: N(-0.42, -0.91, 0), [L + 'Leg']: N(-0.42, -0.91, 0), [L + 'Foot']: flatX,                    // 뒷다리 곧게 25°, 뒤꿈치 바닥 (발등 굽힘 25°)
          [R + 'UpLeg']: N(0.62, -0.79, 0), [R + 'Leg']: [0, -1, 0], [R + 'Foot']: flatX } };                          // 앞무릎은 발목 위
    } },
    // 누워 허리 비틀기: 팔은 T 자, 한 무릎을 굽혀 반대쪽으로 넘긴다. 양 어깨는 바닥에, 머리는 반대쪽. 좌우 번갈아
    'twist': { base: 'lying', period: 12, still: true, pose: (u, C) => {
      const sideL = u < 0.5, s1 = sideL ? u : u - 0.5;                                                              // 앞 절반은 왼쪽으로, 뒤 절반은 오른쪽으로 — 가운데(무릎 세움)를 지나서
      const wB = hold(s1, 0.0, 0.06, 0.44, 0.5), wT = hold(s1, 0.06, 0.18, 0.38, 0.46);                             // 아래 다리를 먼저 펴고(wB) 위 다리를 넘긴다(wT) — 두 다리가 서로 지나가지 않게
      // 팔은 늘 IK 로 — T 자로 편 팔(방향)과 무릎을 누르는 팔(IK)을 섞으면 중간이 없어 절반에서 팔이 홱 튀고, 남아 있던 아래팔 방향이
      // IK 뒤에 다시 적용돼 손이 무릎에 닿지도 않았다 (리뷰: 팔이 떨리고 사라진다). 편 팔도 '어깨 옆 50cm' 를 짚는 IK 라 두 자세가 매끈하게 이어진다
      const armT = side => ({ ik: p => add(p(side + 'Arm'), [side === L ? 0.5 : -0.5, -0.02, 0.02]), bend: [0, -0.7, -0.7] });   // 팔꿈치는 아래·머리 쪽 — 그래야 바닥 짚은 손바닥이 아래팔 중립에 가깝다 (발 쪽이면 손목이 180° 꼬였다, 리뷰)
      const along = side => p => { const e = p(side + 'ForeArm'), w = p(side + 'Hand'); return [w.x - e.x, w.y - e.y, w.z - e.z]; };   // 손은 아래팔을 잇는다
      const handT = side => ({ aim: along(side), palm: [0, -1, 0] });                                                  // 편 팔의 손바닥은 바닥에
      const arms = { [L + 'Arm']: armT(L), [R + 'Arm']: armT(R), [L + 'Hand']: handT(L), [R + 'Hand']: handT(R) };
      // 무릎을 누르는 손: 손목은 무릎 위 12.5cm 에서 어깨 쪽으로 7cm 물러난 자리 — 손바닥 가운데가 무릎 위에 온다. 손가락은 무릎 너머로 넘어가고
      // 손바닥은 무릎을 본다 (예전엔 손목이 무릎 바로 위에 있고 손은 아래팔 방향 그대로라 손이 허공을 향해 서 있었다)
      const press = p => { const k = p(L + 'Leg'), sh = p(R + 'Arm'), a = N(k.x - sh.x, k.y - sh.y, k.z - sh.z); return { k, a, w: [k.x - a[0] * 0.07, k.y + 0.125 - a[1] * 0.07, k.z - a[2] * 0.07] }; };
      const center = { ...arms, ...kneesUp, 'mixamorig:Head': { aim: [0, 0.05, -1], front: [0, 1, 0] } };
      const left = { ...arms, [L + 'UpLeg']: N(-0.61, 0.61, 0.51), [L + 'Leg']: N(-0.6, -0.62, 0.5), [L + 'Foot']: { aim: footFollow(L, N(1 - 0.13 * wT, 0.5 * wT, 0), 55) },   // 위 다리: 무릎을 들어 아래 다리 위를 넘긴다 (발의 '왼쪽' 은 30° 돌아간 골반을 따라간다 — 세상 기준이면 발목이 옆으로 30° 꺾였다)
        [R + 'UpLeg']: [0, 0, 1], [R + 'Leg']: [0, 0, 1], [R + 'Foot']: N(0, 0.7, 0.7),
        [R + 'Arm']: { ik: p => press(p).w, bend: [-1, -0.15, -0.2] },                                                   // 손은 무릎 살 위에 (거울에선 반대 무릎). 팔꿈치는 몸 바깥으로 — 천장 쪽으로 두면 어깨가 160° 안으로 돌아야 해 위팔이 꼬였다
        [R + 'Hand']: { aim: p => { const { k, a, w } = press(p); return [k.x + a[0] * 0.06 - w[0], k.y + 0.04 - w[1], k.z + a[2] * 0.06 - w[2]]; },
                        palm: p => { const { k, w } = press(p); return [k.x - w[0], k.y - w[1], k.z - w[2]]; } },
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
          [R + 'UpLeg']: N(0, -0.415, 0.91), [R + 'Leg']: N(0, -0.415, 0.91),                                          // 위(오른) 다리는 7° 더 기울여 발이 아래 발 위에 얹힌다(발목 사이 8cm = 발 너비) — 골반 너비만큼 벌어져 있었다 (리뷰: 다리 붙여 줘)
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
          [L + 'Arm']: N(...mix([0.82, -0.25, 0.5], [0.12, 0.99, 0.05], p)), [L + 'ForeArm']: { aim: N(...mix([-0.05, 0.98, 0.15], [0, 1, 0.02], p)), palmTo: [0, 0, 1] },                   // 손바닥은 발 쪽 — 위([0,1,0])는 선 아래팔과 나란해 비틀림이 제멋대로였다 (리뷰)
          [R + 'Arm']: N(...mix([-0.82, -0.25, 0.5], [-0.12, 0.99, 0.05], p)), [R + 'ForeArm']: { aim: N(...mix([0.05, 0.98, 0.15], [0, 1, 0.02], p)), palmTo: [0, 0, 1] } } };
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
          // 팔은 등받이를 따라 내려 의자 옆 손잡이로 — 팔꿈치는 앞으로 15° 굽힌다 (거의 편 8° 는 굽는 쪽이 애매해 오른팔이 뒤로 꺾인 것으로 잡혔다)
          [L + 'Arm']: N(0.55, -0.65, -0.35), [L + 'ForeArm']: N(0.75, -0.6, -0.22), [R + 'Arm']: N(0.55, -0.65, 0.35), [R + 'ForeArm']: N(0.75, -0.6, 0.22) } };
    } },
    // 실내 자전거: 안장은 페달이 맨 아래일 때 무릎이 살짝 굽는 높이. 엉덩이에서 힌지해 상체를 살짝 앞으로, 팔꿈치는 부드럽게
    'cycle': { base: 'idle', period: 2.0, gear: 'bike', fist: true, pose: (u, C) => {
      const th = u * Math.PI * 2, up = N(0, 0.92, 0.39);
      // 발볼이 페달 가운데에 놓이게 — 발목은 페달보다 10cm 뒤·7cm 위 (발은 발목에서 앞·아래로 0.146). 각도는 -th 라 앞으로 돈다 (위 → 앞 → 아래 → 뒤). 예전엔 뒤로 돌았다 (리뷰)
      // 발볼이 페달 윗면에 놓인다: 발끝은 위(a = 90°)에서 25°, 아래에서 5° 내리고(발목이 덜 꺾인다), 발목은 그 발 방향에서 거꾸로 셈한다 —
      // 발볼은 발 뼈를 따라 12.5cm, 발바닥 쪽으로 3cm. 예전엔 발목을 페달 위에 두어 발이 페달 앞에 떠 있었다 (리뷰)
      const footDir = a => { const g = (32 + 15 + 10 * Math.sin(a)) * D; return [0, -Math.sin(g), Math.cos(g)]; };
      const HAND_ON_BAR = { dir: N(0, -0.3, 0.954), palm: N(0, -0.954, -0.3) };
      const gripBar = sgn => { const k = C.along(sgn > 0 ? 'Left' : 'Right'), d = HAND_ON_BAR.dir, n = HAND_ON_BAR.palm;
        return [sgn * BIKE.bar[0], BIKE.bar[1] - d[1] * k - n[1] * 0.027, BIKE.bar[2] - d[2] * k - n[2] * 0.027]; };
      const pedal = (side, x, a) => { const f = footDir(a), py = BIKE.crank[1] + BIKE.r * Math.sin(a) + 0.012, pz = BIKE.crank[2] + BIKE.r * Math.cos(a);
        return { ik: [x, py - 0.125 * f[1] + 0.03 * f[2], pz - 0.125 * f[2] - 0.03 * f[1]], bend: [x * 0.4, 0.6, 0.8] }; };
      return { root: { pos: [0, 1.0, -0.05], up, front: N(0, -0.39, 0.92) },
        bones: { ...spineAll(up, N(0, 0.99, 0.15)),
          [L + 'UpLeg']: pedal(L, BIKE.x, -th), [R + 'UpLeg']: pedal(R, -BIKE.x, -th + Math.PI), [L + 'Foot']: footDir(-th), [R + 'Foot']: footDir(-th + Math.PI),          // 발바닥은 페달 위에
          // 손잡이는 손바닥 가운데 아래에 온다: 손은 앞·살짝 아래로 뻗고 손바닥은 아래·뒤(손잡이 쪽). 손목은 거기서 손바닥 자리만큼(리깅마다 다르다)
          // 물러나고 손잡이 굵기만큼 뜬다 — 예전엔 손목 관절을 손잡이 자리에 두어 손잡이가 손목을 뚫었다 (리뷰)
          [L + 'Arm']: { ik: gripBar(1), bend: [0.3, -1, 0] }, [R + 'Arm']: { ik: gripBar(-1), bend: [-0.3, -1, 0] },
          [L + 'Hand']: { aim: HAND_ON_BAR.dir, palm: HAND_ON_BAR.palm }, [R + 'Hand']: { aim: HAND_ON_BAR.dir, palm: HAND_ON_BAR.palm } } };
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
    'barbell-squat': 'backbar', 'deadlift': 'barbell', 'dumbbell-curl': 'dumbbells', 'shoulder-press': 'seatpress',
    'kettlebell-swing': 'kettlebell', 'jump-rope': 'rope', 'treadmill': 'treadmill', 'swim': 'water',
    'bench-press': 'bench', 'lat-pulldown': 'pulldown', 'leg-press': 'legpress', 'cycle': 'bike', 'rowing': 'rower', 'calf-stretch': 'wall',
  };

  /* 손잡이 자리: 손 뼈는 손목에서 시작하니 손가락 쪽으로 조금 나간 곳(손바닥 가운데)을 잡는다.
     axis 는 손바닥을 가로지르는 축 — 덤벨·줄넘기 손잡이가 이 축을 따라 눕는다. */
  const GRIP = { along: 0.055, side: 0.0, curl: 75, thumbCurl: 40,
    // 쥔 엄지의 세 마디 방향 — 손 기준 [엄지 쪽, 손가락 쪽, 손바닥 쪽]. 엄지는 손잡이 아래(손바닥 쪽)로 돌아 집게·가운뎃손가락 끝을 덮는다.
    // 손가락처럼 손바닥 가로축으로만 말면 엄지가 옆으로 뻗쳐 '히치하이커 엄지'가 됐다 (리뷰: 기구를 손바닥으로 감싸 쥐어야)
    thumb: [[0.35, 0.45, 0.82], [0.0, 0.62, 0.78], [-0.4, 0.8, 0.45]] };

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

  /* ---- 팔꿈치 다시 묶기 ----
   * 자동 리깅이 팔꿈치 관절을 아래팔 중간쯤(어깨→손목의 63%, 여성 58%)에 두어, 팔이 팔꿈치가 아니라 아래팔에서 꺾이고
   * 아래팔이 짧아 보였다 (리뷰: "팔꿈치에 가야 하는 관절이 손과 팔꿈치 사이 팔 부분에 가 있다"). 살의 중심선이 꺾이는 자리(55% 안팎)와
   * 사람 비율(위팔 0.186 : 아래팔 0.146 → 56%)에 맞춰 관절을 위팔 축을 따라 위로 옮기고, 위팔·아래팔 살의 가중치를 새 관절 기준으로
   * 다시 나눈다. 위팔 뼈의 방향은 그대로고(새 관절이 그 축 위에 있다) 아래팔 뼈만 새 팔꿈치 → 손목을 보게 3° 쯤 돌린다 — 동작 파일의 회전값은
   * 그대로 쓴다(아래팔 살이 그만큼 따라 돌 뿐이다). 손목과 그 아래는 제자리다.
   * 묶인 자세(T 자세를 입히기 전)에서, 장면마다 한 번 한다. */
  const ELBOW_AT = 0.56, ELBOW_BLEND = 0.06;      // 어깨→손목 길이에 대한 비율: 관절 자리, 가중치가 섞이는 반폭(3cm 쯤)
  /* 스킨 가중치를 고쳐 쓰기 전에 실수(Float32)로 바꾼다. 파일의 가중치는 8비트 정수(1/255 단위)라, 새 값을 그대로 써 넣으면 반올림 때문에
   * 네 값의 합이 1 에서 ±0.4% 어긋난다 — 셰이더는 합을 다시 맞추지 않아서 꼭짓점이 원점 쪽으로 그만큼(키 1.75m 에서 5mm 안팎) 끌려가고,
   * 꼭짓점마다 어긋남이 달라 어깨 위가 톱니처럼 보였다. 합도 1 로 맞춰 둔다 */
  function floatSkinWeights(T, geometry){
    const sw = geometry.getAttribute('skinWeight');
    if (!sw || (sw.array instanceof Float32Array && !sw.normalized)) return sw;
    const out = new Float32Array(sw.count * 4);
    for (let i = 0; i < sw.count; i++) {
      let sum = 0; for (let k = 0; k < 4; k++) { out[i * 4 + k] = sw.getComponent(i, k); sum += out[i * 4 + k]; }
      if (sum > 0) for (let k = 0; k < 4; k++) out[i * 4 + k] /= sum;
    }
    geometry.setAttribute('skinWeight', new T.BufferAttribute(out, 4));
    return geometry.getAttribute('skinWeight');
  }
  function fixElbows(lib, body){
    const { T } = lib;
    body.updateMatrixWorld(true);
    const norm = n => String(n).replace(/[^A-Za-z0-9]/g, '');
    const bones = new Map(); body.traverse(o => { if (o.isBone) bones.set(norm(o.name), o); });
    const meshes = []; body.traverse(o => { if (o.isSkinnedMesh) meshes.push(o); });
    const plans = [];
    for (const side of ['Left', 'Right']) {
      const arm = bones.get('mixamorig' + side + 'Arm'), fore = bones.get('mixamorig' + side + 'ForeArm'), hand = bones.get('mixamorig' + side + 'Hand');
      if (!arm || !fore || !hand) continue;
      const S = arm.getWorldPosition(new T.Vector3()), E = fore.getWorldPosition(new T.Vector3()), W = hand.getWorldPosition(new T.Vector3());
      const l1 = S.distanceTo(E), l2 = E.distanceTo(W), total = l1 + l2, want = ELBOW_AT * total;
      if (!(l1 > 0) || Math.abs(want - l1) < 0.01 * total) continue;                 // 이미 제자리면 그대로
      const was = fore.matrixWorld.clone();
      const E2 = S.clone().add(E.clone().sub(S).multiplyScalar(want / l1));          // 위팔 축을 따라 위로
      const handQ = hand.getWorldQuaternion(new T.Quaternion()), foreQ = fore.getWorldQuaternion(new T.Quaternion());
      fore.position.multiplyScalar(want / l1); fore.updateMatrixWorld(true);
      // 아래팔 뼈의 축(Y)이 새 팔꿈치 → 손목을 지나게 뼈를 돌려 둔다. 관절만 옮기면 손목이 뼈 축에서 3~5° 비껴나, 뼈 축을 맞춰 '곧게 편' 팔이
      // 관절 자리로 보면 5° 거꾸로 꺾여 있고 IK 의 손도 목표에서 1~2cm 빗나갔다 (검사: 팔꿈치가 거꾸로 꺾였다). 손의 세상 자리·방향은 그대로 둔다
      const turned = new T.Quaternion().setFromUnitVectors(new T.Vector3(0, 1, 0).applyQuaternion(foreQ), W.clone().sub(E2).normalize()).multiply(foreQ);
      fore.quaternion.copy(fore.parent.getWorldQuaternion(new T.Quaternion()).invert().multiply(turned)); fore.updateMatrixWorld(true);
      hand.position.copy(fore.worldToLocal(W.clone())); hand.quaternion.copy(turned.invert().multiply(handQ)); hand.updateMatrixWorld(true);   // 손목(과 손)은 제자리에
      const n = E2.clone().sub(S).normalize().add(W.clone().sub(E2).normalize()).normalize();   // 팔을 따라 손 쪽을 보는 방향
      plans.push({ arm, fore, was, E2, n, r: ELBOW_BLEND * total });
    }
    if (!plans.length) return;
    body.updateMatrixWorld(true);
    const v = new T.Vector3(), fix = new T.Matrix4();
    for (const m of meshes) {
      const pos = m.geometry.getAttribute('position'), si = m.geometry.getAttribute('skinIndex'), sw = floatSkinWeights(T, m.geometry);
      if (!pos || !si || !sw) continue;
      for (const p of plans) {
        const ia = m.skeleton.bones.indexOf(p.arm), ib = m.skeleton.bones.indexOf(p.fore); if (ia < 0 || ib < 0) continue;
        // 아래팔 뼈의 묶인 자리가 바뀌었다: 새 역행렬 = 새 자리의 역 × 옛 자리 × 옛 역행렬 (메시·몸 크기 변환은 옛 역행렬에 들어 있다)
        m.skeleton.boneInverses[ib].premultiply(fix.copy(p.fore.matrixWorld).invert().multiply(p.was));
        for (let i = 0; i < pos.count; i++) {
          let ka = -1, kb = -1, sum = 0;
          for (let k = 0; k < 4; k++) { const w = sw.getComponent(i, k); if (w <= 0) continue; const b = si.getComponent(i, k); if (b === ia) { ka = k; sum += w; } else if (b === ib) { kb = k; sum += w; } }
          if (sum <= 0) continue;
          v.fromBufferAttribute(pos, i).applyMatrix4(m.matrixWorld);
          const t = Math.min(1, Math.max(0, (v.sub(p.E2).dot(p.n) + p.r) / (2 * p.r)));
          let wf = sum * t * t * (3 - 2 * t); if (wf < 1e-4) wf = 0; if (sum - wf < 1e-4) wf = sum;
          const wa = sum - wf, free = k0 => [0, 1, 2, 3].find(k => k !== k0 && sw.getComponent(i, k) <= 0);
          if (ka < 0 && wa > 0) { const f = free(kb); if (f === undefined) continue; ka = f; si.setComponent(i, ka, ia); }
          if (kb < 0 && wf > 0) { const f = free(ka); if (f === undefined) continue; kb = f; si.setComponent(i, kb, ib); }
          if (ka >= 0) sw.setComponent(i, ka, wa);
          if (kb >= 0) sw.setComponent(i, kb, wf);
        }
      }
      si.needsUpdate = true; sw.needsUpdate = true;
    }
  }

  /* ---- 팔 보조 뼈 (비틀림 뼈 · 나눠 도는 관절) ----
   * 이 리깅은 관절마다 뼈가 하나뿐이라, 선형 스키닝이 크게 돈 관절의 살을 두 자리의 '평균'(현)으로 끌어당긴다 —
   * 140° 굽힌 팔꿈치는 바깥쪽 살이 관절 쪽으로 꺼지고(관절 없이 휘는 느낌), 머리 위로 든 어깨는 종이처럼 접히고,
   * 아래팔·위팔을 제 축으로 비틀면 사탕 포장지처럼 가늘어졌다 (리뷰: 팔꿈치~손, 어깨·겨드랑이가 깨진다).
   * 게임 리깅이 하는 대로 고친다:
   *   · 비틀림 뼈: 위팔·아래팔의 제 축 비틀림을 0 · 0.2 · … · 0.8 만큼만 갖는 뼈를 두고, 살을 뼈를 따라 그 사이에 나눠 붙인다.
   *     어깨 쪽 살은 안 비틀리고 팔꿈치 쪽은 다 비틀린다 (아래팔은 팔꿈치 쪽이 0, 손목 쪽이 1 — 노뼈가 자뼈를 도는 모양).
   *   · 나눠 도는 관절: 팔꿈치엔 굽힌 각의 ⅓ · ⅔ 만, 어깨엔 절반만 도는 뼈를 두고, 두 뼈에 걸쳐 있던 살을 그 사이에 나눠 붙인다.
   *     살이 평균 자리로 꺼지는 대신 관절을 중심으로 호를 그리며 돌아 굵기가 남는다.
   * 뼈대의 자세값은 그대로라 동작 파일·자세 표는 손대지 않는다. 보조 뼈는 매 프레임 본래 뼈에서 계산한다 (setup 의 driveHelpers).
   * 묶인 자세에서, 장면마다 한 번. 꼭짓점의 영향 뼈는 4개까지라 넘치면 가장 작은 것을 가장 닮은 뼈에 합친다. */
  const TWIST_AT = [0, 0.2, 0.4, 0.6, 0.8];       // 비틀림을 이만큼씩만 갖는 뼈 (1 은 본래 뼈)
  const ELBOW_SWING_AT = [1 / 3, 2 / 3];          // 팔꿈치가 굽은 각의 이만큼만 도는 뼈
  const TWIST_FROM = 0.12, TWIST_TO = 0.88;       // 뼈 길이의 이 구간에서 비틀림이 0 → 1 로 는다 (관절 가까이는 한쪽 값)
  const SHOULDER_R = [0.3, 0.6];                  // 어깨 관절에서 위팔 길이의 이 배수까지는 보조 뼈가 다 맡고, 그 밖은 점점 안 맡는다
  const SHOULDER_CAP = [-0.6, -0.1];              // 관절에서 본 방향이 '바깥·위'(어깨 뚜껑)일수록 보조 뼈가 맡는다 — 겨드랑이·옆구리(안쪽·아래)는 예전처럼 늘어나기만 한다
  const SHOULDER_SMOOTH = 3, AXILLA_SMOOTH = 12;   // 위팔 몫을 이웃 꼭짓점과 고르게 하는 횟수: 어깨 뚜껑 / 겨드랑이(가슴 옆 ↔ 팔 안쪽이 한 모서리에서 0.1 → 0.7 로 뛰어, 팔을 들면 그 사이가 판자처럼 펴졌다)
  const SMOOTH_R = 0.8;                           // 어깨 관절에서 위팔 길이의 이 배수 안에서만 고르게 한다
  const NATURAL_TWIST = 100 * D, NATURAL_FROM = 0, NATURAL_TO = 75 * D;   // 팔을 수평 위로 들수록 위팔이 자연스레 바깥으로 도는 만큼 (어깨 쪽 살이 그만큼 따라 돈다)
  const smoothStep = (a, b, x) => { const t = Math.max(0, Math.min(1, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
  function addArmHelpers(lib, body){
    const { T } = lib;
    body.updateMatrixWorld(true);
    const norm = n => String(n).replace(/[^A-Za-z0-9]/g, '');
    const named = new Map(); body.traverse(o => { if (o.isBone) named.set(norm(o.name), o); });
    const meshes = []; body.traverse(o => { if (o.isSkinnedMesh) meshes.push(o); });
    const make = (name, parent, source, like) => {
      const b = new T.Bone(); b.name = name; b.helperOf = source;                       // (userData 는 복제 때 JSON 을 거쳐 뼈를 못 담는다)
      if (like) { b.position.copy(like.position); b.quaternion.copy(like.quaternion); b.scale.copy(like.scale); }
      parent.add(b); b.updateMatrixWorld(true); return b;
    };
    const Y = new T.Vector3(0, 1, 0);
    const rig = [];
    for (const side of ['Left', 'Right']) {
      const arm = named.get('mixamorig' + side + 'Arm'), fore = named.get('mixamorig' + side + 'ForeArm'), hand = named.get('mixamorig' + side + 'Hand');
      if (!arm || !fore || !hand || !arm.parent || !arm.parent.isBone) continue;
      const torso = [named.get('mixamorig' + side + 'Shoulder')].concat(['Hips', 'Spine', 'Spine1', 'Spine2', 'Neck', 'Head'].map(n => named.get('mixamorig' + n))).filter(Boolean);
      // 비틀림을 재는 기준: 기준 방향 dir0 을 볼 때의 뼈 방향 q0 을, 지금 뼈가 뻗은 쪽으로 가장 짧게 돌린 것. 기준 방향의 정반대 쪽에서는
      // 값이 제멋대로라, 팔이 갈 수 없는 쪽(몸 안쪽·뒤)이 정반대가 되게 위팔은 '바깥·앞'을 기준으로 잡는다 (묶인 A 자세를 기준으로 하면
      // 정반대가 '위·안쪽'이라 머리 위로 든 팔에서 비틀림이 ±180° 를 오가며 살이 튀었다). 아래팔은 굽는 각이 150° 를 못 넘어 묶인 방향 그대로
      const joint = (bone, tag, swingParent, swingAt, dir0World, natural) => {
        const bindQ = bone.quaternion.clone(), toParent = bone.parent.getWorldQuaternion(new T.Quaternion()).invert();
        const bindDir = Y.clone().applyQuaternion(bindQ), dir0 = dir0World ? dir0World.clone().applyQuaternion(toParent).normalize() : bindDir.clone();
        return { bone, bindQ, dir0, q0: new T.Quaternion().setFromUnitVectors(bindDir, dir0).multiply(bindQ),
          up: new T.Vector3(0, 1, 0).applyQuaternion(toParent), natural: natural || 0, twist: 0, swing: 0, prev: null,
          twists: TWIST_AT.map((tau, k) => ({ tau, bone: make('fx' + side + tag + 'Twist' + k, bone, bone) })),                // 본래 뼈의 자식 — 제 축으로 되감는다
          swings: swingAt.map((f, k) => ({ f, bone: make('fx' + side + tag + 'Swing' + k, swingParent, bone, bone) })) };      // 본래 뼈의 형제 — 부모에서 f 만큼만 돈다
      };
      const S = arm.getWorldPosition(new T.Vector3()), out = side === 'Left' ? 1 : -1;                                          // 선 몸의 왼쪽은 +X
      const cap = S.clone().sub(arm.parent.getWorldPosition(new T.Vector3())).setY(0).normalize().add(new T.Vector3(0, 1, 0)).normalize();   // 어깨 뚜껑 쪽 = 바깥 + 위
      rig.push({ torso, cap, upper: joint(arm, 'Arm', arm.parent, [0.5]), lower: joint(fore, 'ForeArm', arm, ELBOW_SWING_AT),
                 S, E: fore.getWorldPosition(new T.Vector3()), W: hand.getWorldPosition(new T.Vector3()) });
    }
    if (!rig.length) return rig;
    const helpers = []; rig.forEach(r => [r.upper, r.lower].forEach(j => j.twists.concat(j.swings).forEach(h => helpers.push(h.bone))));
    // 값 x(0~1) 를 마디(0 … 1)들에 나눠 싣는다 — 이웃한 두 마디에만
    const spread = (x, nodes) => {
      const out = nodes.map(() => 0), y = Math.max(0, Math.min(1, x)); let k = 0;
      while (k < nodes.length - 2 && y > nodes[k + 1]) k++;
      const t = (y - nodes[k]) / (nodes[k + 1] - nodes[k]); out[k] = 1 - t; out[k + 1] = t; return out;
    };
    const TWIST_NODES = TWIST_AT.concat(1), ELBOW_NODES = [0].concat(ELBOW_SWING_AT, 1);
    const v = new T.Vector3(), ax = new T.Vector3();
    for (const m of meshes) {
      const sk = m.skeleton, pos = m.geometry.getAttribute('position'), si = m.geometry.getAttribute('skinIndex'), sw = floatSkinWeights(T, m.geometry);
      if (!pos || !si || !sw) continue;
      const at = b => sk.bones.indexOf(b);
      if (rig.some(r => at(r.upper.bone) < 0 || at(r.lower.bone) < 0)) continue;
      // 보조 뼈를 뼈대에 더한다. 묶인 자리는 본래 뼈와 같다 (지금이 묶인 자세이고, 보조 뼈는 본래 뼈와 같은 자리·방향에서 시작한다)
      const bones = sk.bones.concat(helpers);
      const inverses = sk.boneInverses.map(x => x.clone()).concat(helpers.map(h => new T.Matrix4().copy(h.matrixWorld).invert().multiply(h.helperOf.matrixWorld).multiply(sk.boneInverses[at(h.helperOf)])));
      const id = b => bones.indexOf(b);
      const plans = rig.map(r => ({ torso: r.torso.map(id).filter(i => i >= 0), S: r.S, E: r.E, cap: r.cap,
        axU: r.E.clone().sub(r.S), axL: r.W.clone().sub(r.E),
        arm: id(r.upper.bone), fore: id(r.lower.bone),
        armTw: r.upper.twists.map(h => id(h.bone)), foreTw: r.lower.twists.map(h => id(h.bone)),
        half: id(r.upper.swings[0].bone), elSw: r.lower.swings.map(h => id(h.bone)) }));
      for (const p of plans) { p.lenU = p.axU.length(); p.lenL = p.axL.length(); p.axU.normalize(); p.axL.normalize(); }
      const ramp = s => (s - TWIST_FROM) / (TWIST_TO - TWIST_FROM);
      // 어깨의 위팔 몫 u 를 이웃 꼭짓점과 고르게 한다 — 자동 리깅의 가중치는 꼭짓점마다 들쭉날쭉해서, 살을 호를 따라 돌리면
      // 그 잡음이 어깨 살의 울퉁불퉁함으로 드러난다. 몫은 '팔 사슬 전체 : 몸통' 으로 잰다
      const index = m.geometry.getIndex(), near = new Array(pos.count);
      if (index) for (let f = 0; f + 2 < index.count; f += 3) {
        const tri = [index.getX(f), index.getX(f + 1), index.getX(f + 2)];
        for (const a of tri) for (const b of tri) if (a !== b) (near[a] || (near[a] = new Set())).add(b);
      }
      rig.forEach((r, n) => {
        const p = plans[n], chain = new Set(), torso = new Set(p.torso);
        r.upper.bone.traverse(o => { const k = at(o); if (k >= 0) chain.add(k); });
        let u = new Float32Array(pos.count).fill(-1);
        for (let i = 0; i < pos.count; i++) {
          let a = 0, t = 0;
          for (let k = 0; k < 4; k++) { const x = sw.getComponent(i, k); if (x <= 0) continue; const b = si.getComponent(i, k); if (chain.has(b)) a += x; else if (torso.has(b)) t += x; }
          if (a + t > 0) u[i] = a / (a + t);
        }
        const zone = new Uint8Array(pos.count);                                 // 어깨 둘레 — 몫이 0 이나 1 인 꼭짓점도 고르게 해야 뛰는 자리가 퍼진다
        for (let i = 0; i < pos.count; i++) if (u[i] >= 0 && near[i] && v.fromBufferAttribute(pos, i).applyMatrix4(m.matrixWorld).distanceTo(p.S) < SMOOTH_R * p.lenU) zone[i] = 1;
        const relax = (from, passes) => {
          let cur = from;
          for (let pass = 0; pass < passes; pass++) {
            const next = cur.slice();
            for (let i = 0; i < pos.count; i++) {
              if (!zone[i]) continue;
              let sum = 0, cnt = 0; for (const j of near[i]) if (cur[j] >= 0) { sum += cur[j]; cnt++; }
              if (cnt) next[i] = 0.5 * cur[i] + 0.5 * sum / cnt;
            }
            cur = next;
          }
          return cur;
        };
        p.u = relax(u, SHOULDER_SMOOTH); p.uWide = relax(u, AXILLA_SMOOTH); p.zone = zone;
      });
      // 영향 뼈가 4개를 넘으면 가장 작은 것을 '가장 닮은 뼈'에 합친다 — 그냥 버리면 이웃 꼭짓점과 다르게 움직여 살이 튄다.
      // 닮은 순서: 몸통 − 어깨 절반 − 위팔 비틀림 0 … 0.8 − 위팔 − 팔꿈치 ⅓ · ⅔ − 아래팔 비틀림 0 … 0.8 − 아래팔 − 손 (왼쪽은 +, 오른쪽은 −)
      const rung = new Map();
      rig.forEach((r, n) => {
        const p = plans[n], sign = n ? -1 : 1, hand = r.lower.bone.children.find(c => c.isBone && !c.helperOf);
        [p.half, ...p.armTw, p.arm, ...p.elSw, ...p.foreTw, p.fore, hand ? id(hand) : -1].forEach((b, k) => { if (b >= 0) rung.set(b, sign * (k + 1)); });
        for (const t of p.torso) rung.set(t, 0);
      });
      for (let i = 0; i < pos.count; i++) {
        const w = new Map();
        for (let k = 0; k < 4; k++) { const x = sw.getComponent(i, k); if (x > 0) { const b = si.getComponent(i, k); w.set(b, (w.get(b) || 0) + x); } }
        let touched = false;
        for (const p of plans) {
          if (!w.has(p.arm) && !w.has(p.fore) && !(p.zone[i] && p.uWide[i] > 1e-4)) continue;
          touched = true;
          v.fromBufferAttribute(pos, i).applyMatrix4(m.matrixWorld);
          const get = b => w.get(b) || 0, put = (b, x) => { if (x > 1e-5) w.set(b, x); else w.delete(b); };
          // 1) 어깨: 몸통 ↔ 위팔 사이에 절반만 도는 뼈를 끼운다. 몫은 (1−u)² : 2u(1−u) : u² — 꺾이는 데 없이 부드럽고, 몸통 몫이 천천히 줄어
          //    빗장뼈와 등뼈가 따로 움직여도 살이 튀지 않는다. 자동 리깅은 옆구리까지 위팔 가중치를 퍼뜨려 놓았는데, 관절에서 먼 살을 관절
          //    중심으로 돌리면 옆구리가 날개처럼 벌어진다 — 관절에서 멀거나 겨드랑이 쪽(안쪽·아래)일수록 보조 뼈 몫을 줄이고 본래 가중치를 둔다
          let wA = get(p.arm), wT = 0; for (const t of p.torso) wT += get(t);
          if (wA + wT > 0 && (p.zone[i] || (wA > 0 && wT > 0))) {
            const all = wA + wT, u = p.zone[i] ? p.u[i] : wA / all, uw = p.zone[i] ? p.uWide[i] : wA / all;   // 어깨 뚜껑 몫 · 겨드랑이 몫 (고르게 한 값)
            const dist = v.distanceTo(p.S), toward = dist > 1e-9 ? ax.copy(v).sub(p.S).dot(p.cap) / dist : 1;
            const g = (1 - smoothStep(SHOULDER_R[0] * p.lenU, SHOULDER_R[1] * p.lenU, dist)) * smoothStep(SHOULDER_CAP[0], SHOULDER_CAP[1], toward);
            const keep = all * (g * (1 - u) * (1 - u) + (1 - g) * (1 - uw));
            if (wT > 0) { for (const t of p.torso) if (w.has(t)) put(t, get(t) * keep / wT); } else put(p.torso[0], keep);      // 몸통 뼈가 없던 살은 빗장뼈에
            put(p.half, all * g * 2 * u * (1 - u)); put(p.arm, all * (g * u * u + (1 - g) * uw));
          }
          // 2) 팔꿈치: 위팔 ↔ 아래팔 사이를 ⅓ · ⅔ 도는 뼈로 잇는다 (몫은 fixElbows 가 자리로 정한 매끈한 값)
          wA = get(p.arm); let wF = get(p.fore);
          if (wA > 0 && wF > 0) {
            const all = wA + wF, lv = spread(wF / all, ELBOW_NODES);
            put(p.arm, lv[0] * all); p.elSw.forEach((b, k) => put(b, lv[k + 1] * all)); put(p.fore, lv[lv.length - 1] * all);
          }
          // 3) 위팔의 비틀림을 어깨(0) → 팔꿈치(1) 로 나눈다
          wA = get(p.arm);
          if (wA > 0) { const lv = spread(ramp(ax.copy(v).sub(p.S).dot(p.axU) / p.lenU), TWIST_NODES); p.armTw.forEach((b, k) => put(b, lv[k] * wA)); put(p.arm, lv[lv.length - 1] * wA); }
          // 4) 아래팔의 비틀림을 팔꿈치(0) → 손목(1) 으로 나눈다
          wF = get(p.fore);
          if (wF > 0) { const lv = spread(ramp(ax.copy(v).sub(p.E).dot(p.axL) / p.lenL), TWIST_NODES); p.foreTw.forEach((b, k) => put(b, lv[k] * wF)); put(p.fore, lv[lv.length - 1] * wF); }
        }
        if (!touched) continue;
        while (w.size > 4) {
          let small = -1, least = Infinity; for (const [b, x] of w) if (x < least) { least = x; small = b; }
          w.delete(small);
          const from = rung.get(small); if (from === undefined) continue;
          let kin = -1, gap = Infinity;
          for (const [b, x] of w) { const r = rung.get(b); if (r === undefined) continue; const d = Math.abs(r - from); if (d < gap || (d === gap && x > w.get(kin))) { gap = d; kin = b; } }
          if (kin >= 0) w.set(kin, w.get(kin) + least);
        }
        const top = [...w.entries()], sum = top.reduce((t, e) => t + e[1], 0) || 1;
        for (let k = 0; k < 4; k++) { si.setComponent(i, k, top[k] ? top[k][0] : 0); sw.setComponent(i, k, top[k] ? top[k][1] / sum : 0); }
      }
      si.needsUpdate = true; sw.needsUpdate = true;
      sk.dispose();
      m.bind(new T.Skeleton(bones, inverses), m.bindMatrix);
    }
    return rig;
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
      out.add(b.set(0, (ctx.hand[side] && ctx.hand[side].along) || GRIP.along, 0).applyQuaternion(q));
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
          // 목 뒤 승모근 위 — 더 낮추면 어깨를 뚫는다 (리뷰). '뒤·아래' 는 등(Spine2)을 따라 돈다: 세상 기준으로 두면 앉을 때 숙인 등이 바를 삼켰다
          ctx.pos('mixamorig:Neck', a); g.position.copy(a).add(ctx.carry('mixamorig:Spine2', b.fromArray(BACKBAR)));
          ctx.pos('mixamorig:LeftShoulder', a); ctx.pos('mixamorig:RightShoulder', b);
          g.quaternion.setFromUnitVectors(X, a.sub(b).normalize());
        } };
      }
      case 'dumbbells': { const L = add(dumbbell()), R = add(dumbbell()); return { update(){ inHand(L, 'Left'); inHand(R, 'Right'); } }; }
      case 'seatpress': {                                                                                            // 앉아서 하는 덤벨 프레스 — 벤치 끝에 앉는다
        const seat = mesh(new T.BoxGeometry(0.36, 0.45, 0.42), soft); seat.position.set(0, 0.225, -0.06); add(seat);
        const L = add(dumbbell()), R = add(dumbbell()); return { pad: 0.3, update(){ inHand(L, 'Left'); inHand(R, 'Right'); } };
      }
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
          grip('Left', L, q); handles[0].position.copy(L); handles[0].quaternion.setFromUnitVectors(up, u.copy(across('Left', q)));
          grip('Right', R, q); handles[1].position.copy(R); handles[1].quaternion.setFromUnitVectors(up, w.copy(across('Right', q)));
          // 줄은 손잡이의 바깥 끝(몸에서 먼 쪽)에서 나온다 — 손바닥 가운데에서 나오면 줄이 아래팔을 스쳐 지나갔다 (검사 3cm)
          axis.copy(R).sub(L).normalize();
          L.addScaledVector(u, (u.dot(axis) < 0 ? 1 : -1) * 0.07); R.addScaledVector(w, (w.dot(axis) > 0 ? 1 : -1) * 0.07);
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
        [rear, frontHub].forEach(h => { const w = mesh(new T.TorusGeometry(0.33, 0.02, 8, 36)); w.rotation.y = Math.PI / 2; w.position.copy(h); add(w); });   // 바퀴는 진행 방향(Z)으로 선다 — 옆으로 누워 있었다 (리뷰)
        const hb = mesh(new T.CylinderGeometry(0.015, 0.015, 0.5, 10)); hb.rotation.z = Math.PI / 2; hb.position.set(0, BIKE.bar[1], BIKE.bar[2]); add(hb);
        const sad = mesh(new T.BoxGeometry(0.14, 0.05, 0.26), soft); sad.position.copy(saddle).add(V(0, 0.04, 0)); add(sad);
        const arms = [0, 1].map(() => add(mesh(new T.BoxGeometry(0.03, 0.03, BIKE.r)))), pedals = [0, 1].map(() => add(mesh(new T.BoxGeometry(0.1, 0.02, 0.08), soft)));
        return { pad: 0.7, update(){
          const th = (ctx.u || 0) * Math.PI * 2;
          [0, 1].forEach(i => {
            const ang = -th + i * Math.PI, x = i ? -BIKE.x : BIKE.x;                                                 // 다리와 같은 방향(앞으로)
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
    fixElbows(lib, body);                                                  // 팔꿈치 관절을 제자리로 (묶인 자세에서, 매끈하게 한 살에)
    const helperRig = addArmHelpers(lib, body);                            // 비틀림 뼈 · 나눠 도는 관절 (어깨·팔꿈치 살이 꺼지지 않게)
    scene.add(body);
    body.updateMatrixWorld(true);
    // GLTFLoader 는 뼈 이름의 ':' 를 지운다(mixamorig:Hips → mixamorigHips). 글자와 숫자만 남겨 맞춘다 —
    // 숫자를 빼면 Spine·Spine1·Spine2 가 한 이름이 돼 척추 위쪽만 움직였다.
    const norm = n => String(n).replace(/[^A-Za-z0-9]/g, '');
    const map = new Map(); const boneList = [];
    body.traverse(o => { if (o.isBone && !o.helperOf) { map.set(norm(o.name), o); boneList.push(o); } });   // 보조 뼈는 자세·검사에서 뺀다 (본래 뼈를 따라갈 뿐)
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
      const m1 = bones.get('mixamorig:' + side + 'HandMiddle1');
      const along = m1 ? hb.getWorldPosition(new T.Vector3()).distanceTo(m1.getWorldPosition(new T.Vector3())) * 0.89 : GRIP.along;   // 손바닥 가운데 = 손 뼈 → 가운뎃손가락 밑마디의 0.89
      const t1 = bones.get('mixamorig:' + side + 'HandThumb1');                // 엄지 쪽(손 기준) — 엄지 첫 마디가 뻗은 방향에서 손가락·손바닥 성분을 뺀 것
      const radial = t1 ? new T.Vector3(0, 1, 0).applyQuaternion(restQ.get(t1)).applyQuaternion(inv) : across.clone();
      radial.addScaledVector(new T.Vector3(0, 1, 0), -radial.y).addScaledVector(palm, -radial.dot(palm)).normalize();
      hand[side] = { bone: hb, palm, across, curl, along, radial };                  // 여성 리깅은 손 뼈가 손목 위쪽에 있어 고정 5.5cm 면 기구가 손목에 걸렸다 (리뷰)
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
        const bone = bones.get(name); if (!bone) continue;
        if (how.rest && restLocalQ.has(bone)) bone.quaternion.copy(restLocalQ.get(bone));                  // rest: 부모에 대해 처음(T) 자세 그대로
        if (how.set) bone.quaternion.setFromEuler(_e.set(how.set[0] * D, how.set[1] * D, how.set[2] * D));
      }
      body.updateMatrixWorld(true);
      // 부모부터 — 자식의 방향은 부모가 정해진 뒤에 맞춘다
      const byBone = new Map(); for (const [name, how] of Object.entries(table)) { const b = bones.get(name); if (b && how.aim) byBone.set(b, how); }
      // 방향은 뼈를 돌리기 전에 다 계산해 둔다 — 부모(위팔)를 돌린 뒤에 자식(아래팔)의 '지금 방향'을 읽으면 이미 부모를 따라 돌아간 값이다
      const aims = new Map(); for (const [bone, how] of byBone) aims.set(bone, typeof how.aim === 'function' ? how.aim(posOf) : how.aim);
      for (const bone of boneList) if (byBone.has(bone)) {
        const how = byBone.get(bone);
        aimBone(bone, aims.get(bone));
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
        if (m[2] === 'Thumb' && GRIP.thumb) {                                  // 엄지는 마디마다 손 기준 방향으로 겨눈다 (부모 마디부터 — boneList 순서)
          const d = GRIP.thumb[+m[3] - 1];
          const dir = new T.Vector3().addScaledVector(h.radial, d[0]).addScaledVector(_v3.set(0, 1, 0), d[1]).addScaledVector(h.palm, d[2]).normalize().applyQuaternion(h.bone.getWorldQuaternion(new T.Quaternion()));
          aimBone(bone, dir.toArray()); continue;
        }
        const deg = (m[2] === 'Thumb' ? GRIP.thumbCurl : GRIP.curl) * (m[3] === '1' ? 0.75 : 1);
        bone.quaternion.copy(restLocalQ.get(bone)).multiply(_q1.setFromAxisAngle(h.curl, deg * D));
      }
    };
    // 편 손: 손가락을 처음(T) 자세대로 곧게 — 바탕 동작의 살짝 말린 손가락이 남으면 벽·바닥을 짚은 손이 접혀 보인다 (리뷰: 종아리 스트레칭)
    const openHands = () => {
      for (const bone of boneList) if (/(Left|Right)Hand(Thumb|Index|Middle|Ring|Pinky)[123]$/.test(bone.name) && restLocalQ.has(bone)) bone.quaternion.copy(restLocalQ.get(bone));
    };
    // 기구
    const v = new T.Vector3();
    const ctx = { scene, hand, u: 0, pos: (n, v) => bones.get(n) ? bones.get(n).getWorldPosition(v) : v.set(0, 0, 0), quat: (n, q) => bones.get(n) ? bones.get(n).getWorldQuaternion(q) : q.identity(),
      // 처음(T 자세) 기준의 벡터를 그 뼈가 지금까지 돈 만큼 돌린다 — 몸에 붙은 기구의 '뒤·아래' 가 몸을 따라가게
      carry: (n, vec) => { const bone = bones.get(n); return bone ? vec.applyQuaternion(bone.getWorldQuaternion(new T.Quaternion()).multiply(restQ.get(bone).clone().invert())) : vec; } };
    // ---- 학습한 자세로 만든 동작 적용 ----
    const proc = PROC[id];
    const stillBase = !!(proc && proc.still);                                 // 바탕 동작을 첫 프레임에 멈춘다 (누운 동작의 손 꼼지락거림)
    const restDir = bone => _v1.set(0, 1, 0).applyQuaternion(restQ.get(bone)).toArray();
    const C = { pos: n => posOf(n), rest: n => { const b = bones.get(n); return b ? restDir(b) : [0, 1, 0]; },
      carry: (n, vec) => ctx.carry(n, new T.Vector3().fromArray(vec)).toArray(),                 // 처음 기준의 방향을 그 뼈가 돈 만큼 돌린다 (몸에 붙은 기구를 쥘 때)
      along: side => (hand[side] && hand[side].along) || GRIP.along };                           // 손목 → 손바닥 가운데 (리깅마다 다르다)
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
    // 손: 손가락이 뻗는 방향(Y)과 손바닥이 보는 방향을 같이 정한다 — 처음(T) 자세에서 손바닥은 아래(-Y)를 본다.
    // 아래팔을 비틀어 손바닥을 맞추는 palmTo 는 목표가 아래팔 축과 나란하면(허리·벽·머리를 짚는 손) 비틀림이 제멋대로 튄다 — 그런 손은 이걸로 통째로 정한다
    const orientPalm = (bone, dir, palm) => {
      const rest = restQ.get(bone);
      const ry = _v1.set(0, 1, 0).applyQuaternion(rest), rp = _v2.set(0, -1, 0); rp.addScaledVector(ry, -rp.dot(ry)).normalize(); const rx = _v3.crossVectors(ry, rp);
      _m1.makeBasis(rx, ry, rp);
      const y = _v4.fromArray(dir).normalize(), z = _v5.fromArray(palm); z.addScaledVector(y, -z.dot(y));
      if (z.lengthSq() < 1e-6) { aimBone(bone, dir); return; }                                                    // 손바닥 방향이 손가락과 나란하면 방향만
      z.normalize(); const x = _v6.crossVectors(y, z);
      _m2.makeBasis(x, y, z); _m1.transpose(); _m2.multiply(_m1);
      const worldQ = _q1.setFromRotationMatrix(_m2).multiply(rest);
      bone.quaternion.copy(bone.parent.getWorldQuaternion(_q2).invert().multiply(worldQ)); bone.updateMatrixWorld(true);
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
    // 아래팔이 위팔에 대해 비틀리는 한도. 엎침·뒤침은 실제로 각 75~85° 지만 이 리깅엔 비틀림 뼈가 없어 아래팔 살이 통째로 꼬인다 —
    // 45° 를 넘기면 아래팔이 짧고 얇아 보이고 팔꿈치가 관절 없이 휘는 것처럼 보였다 (리뷰). 손바닥 방향은 그만큼 덜 맞아도 팔이 팔처럼 보이는 쪽을 택한다
    const TWIST_LIMIT = 100 * D, TWIST_LIMIT_STRAIGHT = 100 * D;         // 비틀림 뼈(addArmHelpers)가 생긴 뒤로는 실제 범위까지 — 그 전엔 45° 를 넘기면 아래팔이 통째로 꼬였다
    const _q3 = new T.Quaternion(), _q4 = new T.Quaternion(), _v7 = new T.Vector3(), _v8 = new T.Vector3(), _v9 = new T.Vector3(), _vh = new T.Vector3();
    const lastBend = new Map();                                        // 위팔 → 마지막으로 팔꿈치가 굽었던 쪽(세상 기준)
    const alignHinges = table => {
      for (const [pn, cn, flex0] of HINGES) {
        const p = bones.get('mixamorig:' + pn), c = bones.get('mixamorig:' + cn); if (!p || !c) continue;
        if (table && !table.has(p) && !table.has(c)) continue;
        const g = c.children.find(x => x.isBone); if (!g) continue;
        const axis = _v7.subVectors(c.getWorldPosition(_v1), p.getWorldPosition(_v2)).normalize();          // 위팔·허벅지 축
        const bend = _v8.subVectors(g.getWorldPosition(_v1), c.getWorldPosition(_v2)).normalize();          // 아래팔·정강이 방향
        bend.addScaledVector(axis, -bend.dot(axis));                                                         // 축에 수직인 성분 = 굽는 쪽
        let straight = bend.length() < 0.17;                                                                 // 거의 곧게 편 팔다리는 굽는 쪽이 없다 (10° 미만)
        if (straight && flex0[2] <= 0) {                                                                     //   다리는 발끝 반대쪽을 '뒤'로 — 무릎이 발끝을 본다
          const gg = g.children.find(x => x.isBone);
          if (gg) { bend.subVectors(gg.getWorldPosition(_v1), g.getWorldPosition(_v2)).normalize().negate(); bend.addScaledVector(axis, -bend.dot(axis)); straight = bend.length() < 0.17; }
        }
        _q3.copy(restQ.get(p)).invert();                                                                     // 처음 자세의 역 — 아래 비틀림 계산도 쓴다
        // 곧게 편 팔은 굽는 쪽을 잴 수 없다. 그렇다고 건너뛰면 팔이 10° 를 넘겨 굽기 시작하는 순간 위팔이 한 프레임에 100° 넘게 돌아 팔이 떨린다
        // (누워 허리 비틀기에서 T 자로 편 팔이 무릎을 잡으러 갈 때, 리뷰). 편 팔은 IK 가 굽힐 쪽(bend)을 미리 쓰고, 없으면 마지막으로 굽었던 쪽을 이어 쓴다
        let known = !straight;
        if (straight && flex0[2] > 0) {
          const hp0 = table && table.get(p);
          if (hp0 && hp0.ik && Array.isArray(hp0.bend)) { bend.fromArray(hp0.bend).negate(); bend.addScaledVector(axis, -bend.dot(axis)); known = bend.length() > 0.2; }   // bend 는 팔꿈치가 나가는 쪽 — 아래팔은 그 반대로 굽는다
          if (!known && lastBend.has(p)) { bend.copy(lastBend.get(p)); bend.addScaledVector(axis, -bend.dot(axis)); known = bend.length() > 0.2; }
        }
        if (known) {                                                                                         // 1) 위팔·허벅지를 제 축으로 돌려 경첩이 굽는 쪽을 보게
          bend.normalize();
          if (flex0[2] > 0) (lastBend.get(p) || lastBend.set(p, new T.Vector3()).get(p)).copy(bend);
          p.getWorldQuaternion(_q1); _q1.multiply(_q3);                                                      // 처음 자세에서 지금까지의 회전
          const hinge = _v9.fromArray(flex0).applyQuaternion(_q1);                                           // 지금 경첩이 굽는 방향
          hinge.addScaledVector(axis, -hinge.dot(axis)).normalize();
          const angle = Math.atan2(_v1.crossVectors(hinge, bend).dot(axis), hinge.dot(bend));
          if (Math.abs(angle) >= 0.02) {
            c.getWorldQuaternion(_q4);
            p.quaternion.multiply(_q1.setFromAxisAngle(_v2.set(0, 1, 0), angle)); p.updateMatrixWorld(true);   // 제 축으로 돌린다
            c.quaternion.copy(p.getWorldQuaternion(_q2).invert().multiply(_q4)); c.updateMatrixWorld(true);    // 아래팔·정강이(와 그 아래)는 그대로
          }
        }
        // 아래팔·정강이는 위팔·허벅지에 대해 비틀리지 않게 — 경첩 축(굽는 방향 × 뼈 축)을 부모와 나란히. 손바닥 방향을 정한 아래팔은 그대로 둔다
        const hc = table && table.get(c), hp = table && table.get(p);
        const keepTwist = !!((hc && (hc.palmTo || hc.roll)) || (hp && hp.ik && hp.palmTo));   // 손바닥 방향을 정한 아래팔은 그 비틀림을 두되 한도 안에서
        // 처음 자세의 경첩 축. 제 벡터(_vh)에 둔다 — 임시 벡터(_v2)에 두었더니 아래에서 정강이를 돌릴 때(_v2.set(0,1,0)) 덮여, 돌린 프레임엔 발 맞추기가
        // '위(0,1,0)'를 기준으로 셈됐다. 발끝을 편 발은 그 기준이 발 축과 거의 나란해 맞추기가 됐다 안 됐다 하며 발이 한 프레임씩 30° 돌았다 (리뷰: 무릎 푸시업의 발)
        const axis0 = _v1.set(0, 1, 0).applyQuaternion(restQ.get(p)), h0 = _vh.fromArray(flex0).cross(axis0);
        const hpar = _v9.copy(h0).applyQuaternion(_q1.copy(p.getWorldQuaternion(_q2)).multiply(_q3));                // 부모의 지금 경첩 축 (_q3 = 처음 자세의 역)
        const cax = _v7.subVectors(g.getWorldPosition(_v8), c.getWorldPosition(_v1)).normalize();                     // 아래팔·정강이 축
        const hch = _v8.copy(h0).applyQuaternion(_q1.copy(c.getWorldQuaternion(_q2)).multiply(_q4.copy(restQ.get(c)).invert()));   // 자식의 지금 경첩 축
        hpar.addScaledVector(cax, -hpar.dot(cax)); hch.addScaledVector(cax, -hch.dot(cax));
        if (hpar.lengthSq() < 0.05 || hch.lengthSq() < 0.05) continue;
        hpar.normalize(); hch.normalize();
        const tw = Math.atan2(_v1.crossVectors(hch, hpar).dot(cax), hch.dot(hpar));
        // 아래팔은 위팔에 대해 ±TWIST_LIMIT 까지만 비튼다 (엎침·뒤침의 실제 범위). 그 이상은 어깨가 도는 것이라 뼈 하나로 비틀면 팔꿈치 살이 꼬여 얇아진다
        if (straight && keepTwist && flex0[2] > 0) {                                                        // 곧게 편 팔은 굽는 쪽이 없어 위팔을 제 축으로 돌려도 된다 —
          if (Math.abs(tw) < 0.02) continue;                                                               // 아래팔을 비트는 대신 위팔(어깨 회전)이 손바닥 방향을 따라간다.
          c.getWorldQuaternion(_q4);                                                                       // 위팔 기준으로 한도를 걸면 위팔의 비틀림이 제멋대로라 좌우 덤벨이 다르게 돌았다
          p.quaternion.multiply(_q1.setFromAxisAngle(_v2.set(0, 1, 0), -tw)); p.updateMatrixWorld(true);
          c.quaternion.copy(p.getWorldQuaternion(_q2).invert().multiply(_q4)); c.updateMatrixWorld(true);  // 아래팔(과 손)의 세상 방향은 그대로
          continue;
        }
        const limit = straight ? TWIST_LIMIT_STRAIGHT : TWIST_LIMIT;
        const turn = keepTwist ? (Math.abs(tw) > limit ? tw - Math.sign(tw) * limit : 0) : tw;
        if (Math.abs(turn) >= 0.02) {
          g.getWorldQuaternion(_q4);
          c.quaternion.multiply(_q1.setFromAxisAngle(_v2.set(0, 1, 0), turn)); c.updateMatrixWorld(true);
          g.quaternion.copy(c.getWorldQuaternion(_q2).invert().multiply(_q4)); g.updateMatrixWorld(true);  // 손·발(과 그 아래)은 그대로
        }                                                                                                   // (돌릴 게 없어도 아래의 손·발 맞추기는 한다 — 여기서 건너뛰어 무릎 푸시업의 발이 정강이에 대해 50°·160° 비틀린 채였다, 리뷰)
        // 손바닥 방향을 정한 팔은 손을 다시 맞추지 않는다 — palmToward 가 손의 비틀림까지 셈해 아래팔을 돌렸는데 손을 또 돌리면 손바닥이 돌아간다
        // (브리지·런지에서 손이 돌아가 보였다, 리뷰)
        const hg = table && table.get(g), fixedHand = !!(hg && (hg.palm || hg.front));                        // 손 방향을 통째로 정한 자세 — 손은 그대로 둔다
        if (keepTwist) continue;                                                                           // 한도를 넘는 만큼은 손바닥이 덜 돌아간 채로 둔다 — 손목에서 메우면 손목이 꼬인다
        if (fixedHand) continue;
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
      // 빗장뼈(Shoulder)는 자세 표가 안 정하면 우리가 놓는다: 몸통만 따라간 제자리 + 들어 올린 각(lifts). aimPass 가 부모 → 자식 순서로
      // 지나갈 때 제 차례에 놓는다 — 몸통이 정해진 뒤, 위팔을 겨누기 전.
      const lifts = new Map(), clavicles = new Set();
      for (const side of [L, R]) { const cl = bones.get(side + 'Shoulder'); if (cl && cl.parent && !table.has(cl) && restQ.has(cl.parent)) clavicles.add(cl); }
      const placeClavicle = cl => {
        const carry = _q3.copy(cl.parent.getWorldQuaternion(_q1)).multiply(_q4.copy(restQ.get(cl.parent)).invert());     // 몸통이 T 자세에서 지금까지 돈 만큼
        const restWorld = _q2.copy(carry).multiply(restQ.get(cl));                                                    // 몸통만 따라간 빗장뼈의 방향
        const lift = lifts.get(cl) || 0;
        if (lift > 0) {
          const upB = _v7.set(0, 1, 0).applyQuaternion(carry).normalize(), d0 = _v9.set(0, 1, 0).applyQuaternion(restWorld).normalize();
          const axis = _v1.crossVectors(d0, upB);
          if (axis.lengthSq() > 1e-6) restWorld.premultiply(_q1.setFromAxisAngle(axis.normalize(), lift));
        }
        cl.quaternion.copy(cl.parent.getWorldQuaternion(_q4).invert().multiply(restWorld)); cl.updateMatrixWorld(true);
      };
      const aimPass = () => {                                                 // 방향 — 부모부터 (aim 이 함수면 뼈 위치 조회 함수를 받아 방향을 돌려준다)
        for (const bone of boneList) {
          if (clavicles.has(bone)) { placeClavicle(bone); continue; }
          const how = table.get(bone); if (!how || how.ik) continue;
          const aim = (Array.isArray(how) || how === 'rest') ? how : how.aim;
          if (aim) { const dir = aim === 'rest' ? restDir(bone) : (typeof aim === 'function' ? aim(posOf) : aim);
            if (how.front) orientBone(bone, dir, how.front); else if (how.palm) orientPalm(bone, dir, typeof how.palm === 'function' ? how.palm(posOf) : how.palm); else aimBone(bone, dir); }
          if (how.roll) { bone.quaternion.multiply(_q1.setFromAxisAngle(_v3.set(0, 1, 0), how.roll * D)); bone.updateMatrixWorld(true); }
        }
        for (const bone of boneList) {                                          // 손바닥 방향은 손 방향까지 다 정한 뒤에 (아래팔을 비트니 손도 같이 돈다)
          const how = table.get(bone); if (how && !how.ik && how.palmTo) palmToward(bone, how.palmTo);
        }
      };
      // 0) 팔은 자세가 정하는데 손은 안 정한 쪽은 손목을 중립(아래팔을 곧게 잇고 비틀림 없이)으로 둔다 — 부모에 대한 처음 자세 그대로.
      //    멈춰 둔 바탕 동작의 손목 각도(좌우가 다르고 70° 씩 비틀려 있기도 하다)가 남으면 기구가 손목에 걸리고 두 손이 짝짝이가 된다 (리뷰).
      //    palmTo 가 아래팔을 돌리기 전에 해 둬야 늘 같은 손을 보고 돌린다
      for (const side of [L, R]) {
        const h = bones.get(side + 'Hand'), f = bones.get(side + 'ForeArm'), arm = bones.get(side + 'Arm');
        if (!h || !f || table.has(h) || !restLocalQ.has(h)) continue;
        if (pose.fist || proc.fist || table.has(f) || (arm && table.get(arm) && table.get(arm).ik)) { h.quaternion.copy(restLocalQ.get(h)); h.updateMatrixWorld(true); }
      }
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
      // 3.5) 어깨뼈 리듬: 팔을 수평보다 위로 들면 빗장뼈(Shoulder)가 따라 올라간다 (어깨 관절 2 : 어깨뼈 1). 자세 표는 위팔만 돌려서
      //      머리 위로 든 팔의 어깨·겨드랑이 살이 접혀 깨져 보였다 (숄더프레스·크런치, 리뷰). 빗장뼈를 올린 뒤 팔 자세를 다시 푼다.
      //      올림각은 늘 '빗장뼈를 제자리에 두고 푼 팔'에서 잰다 — 지금 빗장뼈(앞 프레임에 우리가 올려 둔 것일 수도, 동작 파일이 막 덮어쓴 것일 수도
      //      있다)에서 재면 프레임마다 출발점이 달라 어깨가 1cm 씩 오르내렸다 (리뷰: 목·종아리 스트레칭의 잔 떨림)
      let shrugged = false;
      for (const cl of clavicles) {
        const arm = cl.children.find(x => x.isBone && !x.helperOf), fore = arm && arm.children.find(x => x.isBone && !x.helperOf); if (!fore) continue;
        const carry = _q3.copy(cl.parent.getWorldQuaternion(_q1)).multiply(_q4.copy(restQ.get(cl.parent)).invert());
        const upB = _v7.set(0, 1, 0).applyQuaternion(carry).normalize();
        const armDir = _v8.subVectors(fore.getWorldPosition(_v1), arm.getWorldPosition(_v2)).normalize();
        const elev = Math.acos(Math.max(-1, Math.min(1, -armDir.dot(upB))));                                         // 0 = 내린 팔, π = 머리 위
        // 많이 올리면(전엔 35° 까지) 빗장뼈에 붙은 윗가슴·승모근 살이 통째로 들려 어깨가 귀까지 솟고 가슴이 사다리꼴로 좁아졌다 (리뷰: 크런치의 어깨~가슴).
        // 어깨 살은 이제 보조 뼈(addArmHelpers)가 맡으니 빗장뼈는 살짝만(12° 까지) 따라간다
        const lift = Math.max(0, Math.min(12 * D, (elev - 80 * D) * 0.15));
        if (lift > 0.002) { lifts.set(cl, lift); shrugged = true; }
      }
      if (shrugged) { aimPass(); ikPass(); ikPass(); aimPass(); }
      alignHinges(table);                                                     // 4) 팔꿈치·무릎이 굽는 쪽에 위팔·허벅지의 비틀림을 맞춘다
      if (pose.fist || proc.fist) fist(); else if (pose.open || proc.open) openHands();
      body.updateMatrixWorld(true);
    };
    // 보조 뼈 구동 — 본래 뼈의 지금 방향에서 '제 축 비틀림' θ 를 잰다: 기준 방향(dir0)의 뼈 방향 q0 을 지금 뻗은 쪽으로 가장 짧게
    // 돌린 것과 지금 뼈의 차이. 위팔은 수평 위로 들수록 자연스레 바깥으로 도는 만큼(natural)을 빼, 그만큼은 어깨 쪽 살이 함께 돌게 한다.
    // 비틀림 뼈는 (1 − τ)·θ 를 되감고, 나눠 도는 뼈는 묶인 방향에서 '비틀림을 뺀 지금 방향'까지의 f 만큼만 돈다.
    // 동작 파일이든 자세 표든 자세를 다 잡은 뒤 매 프레임 한 번
    const _ht = new T.Quaternion(), _h0 = new T.Quaternion(), _hr = new T.Quaternion(), _hY = new T.Vector3(0, 1, 0), _hd = new T.Vector3();
    const twistNow = j => {                                                     // 이 뼈의 제 축 비틀림 (−π ~ π)
      const q = j.bone.quaternion;
      _hd.copy(_hY).applyQuaternion(q).normalize();
      _hr.setFromUnitVectors(j.dir0, _hd).multiply(j.q0);                       // 비틀림 없는 기준 방향
      _ht.copy(_hr).invert().multiply(q);                                       // 기준에서 지금까지 = 제 축(Y) 회전
      if (_ht.w < 0) _ht.set(-_ht.x, -_ht.y, -_ht.z, -_ht.w);
      return 2 * Math.atan2(_ht.y, _ht.w);
    };
    // 손목은 비틀리지 않는다 — 손바닥을 뒤집는 것은 아래팔(노뼈가 자뼈를 돈다)이다. 손이 아래팔에 대해 제 축으로 비틀려 있으면(자세 표가 손 방향을
    // 통째로 정했거나, 동작 파일이 엎침을 손목에 나눠 실었거나) 손목 살이 사탕 포장지처럼 꼬이며 갑자기 가늘어진다 (리뷰: 허리 비틀기·사이드 플랭크·
    // 플랭크의 손목). 그 비틀림을 아래팔로 넘긴다: 아래팔을 제 축으로 그만큼 돌리고 손은 세상 방향 그대로 — 아래팔의 비틀림은 비틀림 뼈들이
    // 팔꿈치 → 손목으로 고르게 나눠 갖는다. 아래팔이 위팔에 대해 돌 수 있는 범위(TWIST_LIMIT)까지만. 런지의 허리 짚은 손이 이렇게 돼 있었다
    const FOREARM_TWIST_MAX = TWIST_LIMIT;
    for (const r of helperRig) r.hand = r.lower.bone.children.find(x => x.isBone && !x.helperOf) || null;
    const untwistWrist = r => {
      const hand = r.hand, fore = r.lower.bone; if (!hand || !restLocalQ.has(hand)) return;
      _h0.copy(restLocalQ.get(hand)).invert().multiply(hand.quaternion);        // 처음 자세에서 지금까지, 손 기준 = 꺾임 × 제 축 비틀림
      if (_h0.w < 0) _h0.set(-_h0.x, -_h0.y, -_h0.z, -_h0.w);
      const tw = 2 * Math.atan2(_h0.y, _h0.w); r.short = 0; if (Math.abs(tw) < 0.01) return;
      const tf = twistNow(r.lower), to = Math.max(Math.min(-FOREARM_TWIST_MAX, tf), Math.min(Math.max(FOREARM_TWIST_MAX, tf), tf + tw)), turn = to - tf;
      if (Math.abs(turn) >= 0.005) { fore.quaternion.multiply(_hr.setFromAxisAngle(_hY, turn)); hand.quaternion.premultiply(_hr.setFromAxisAngle(_hY, -turn)); }
      // 아래팔이 다 못 받은 나머지는 손을 제 축으로 되돌려 없앤다 — 손바닥이 그만큼 덜 돌아가지만 손목은 꼬이지 않는다 (자세가 무리한 것이라 검사에서 본다: short)
      r.short = tw - turn;
      if (Math.abs(r.short) >= 0.005) hand.quaternion.multiply(_hr.setFromAxisAngle(_hY, -r.short));
    };
    const driveHelpers = () => {
      for (const r of helperRig) { untwistWrist(r); for (const j of [r.upper, r.lower]) {
        const q = j.bone.quaternion;
        let th = twistNow(j);
        if (j.natural) th -= j.natural * smoothStep(NATURAL_FROM, NATURAL_TO, Math.asin(Math.max(-1, Math.min(1, _hd.dot(j.up)))));
        if (j.prev !== null) { while (th - j.prev > Math.PI) th -= 2 * Math.PI; while (th - j.prev < -Math.PI) th += 2 * Math.PI; }   // ±180° 를 넘어가도 이어서 센다 (안 그러면 중간 뼈가 반대로 감긴다)
        if (Math.abs(th) > 200 * D) th -= 2 * Math.PI * Math.round(th / (2 * Math.PI));
        j.prev = th; j.twist = th;
        for (const h of j.twists) h.bone.quaternion.setFromAxisAngle(_hY, (h.tau - 1) * th);
        _h0.copy(q).multiply(_ht.setFromAxisAngle(_hY, -th));                   // 비틀림을 뺀 지금 방향
        j.swing = j.bindQ.angleTo(_h0);
        for (const h of j.swings) h.bone.quaternion.copy(j.bindQ).slerp(_h0, h.f);
      } }
    };
    const cycle = proc ? proc.period : clip.duration;                       // 한 바퀴 — 카메라·줄넘기 박자가 이것을 본다
    // 믹서는 값이 안 바뀐 프레임엔 뼈를 다시 쓰지 않는다. 그래서 우리가 덮어쓴 뼈를 다음 프레임 전에 '믹서가 마지막에 준 값'으로
    // 되돌려 둔다 — 처음 자세로 되돌리면 엉덩이 높이가 일정한 동작(무릎꿇기 등)에서 믹서가 안 써서 몸이 떠 버리고, 안 되돌리면 dpos 가 쌓인다.
    // 엉덩이(root.dpos, pitchAtHands)만이 아니라 모든 뼈를 되돌린다: 손목 비틀림을 아래팔로 넘기거나(untwistWrist) 손·발을 맞추며(alignHinges)
    // 돌려 둔 아래팔·손이 그대로 남으면, 믹서가 둘 중 하나만 새로 쓴 프레임에 한 번 더(또는 덜) 돌아 손목이 한 프레임씩 30~70° 튀었다
    // (스쿼트·덤벨 컬·케틀벨·줄넘기, 리뷰 3차 떨림 측정). 매 프레임은 늘 '믹서가 준 자세'에서 시작한다
    const hipsBone = bones.get('mixamorig:Hips');
    const hipsMixed = hipsBone ? hipsBone.position.clone() : null, mixedQ = boneList.map(b => b.quaternion.clone());
    const restoreMixed = () => { if (hipsBone) hipsBone.position.copy(hipsMixed); for (let i = 0; i < boneList.length; i++) boneList[i].quaternion.copy(mixedQ[i]); };
    const rememberMixed = () => { if (hipsBone) hipsMixed.copy(hipsBone.position); for (let i = 0; i < boneList.length; i++) mixedQ[i].copy(boneList[i].quaternion); };
    const poseAt = t => { restoreMixed(); mixer.setTime(stillBase ? 0 : t % clip.duration); rememberMixed(); body.updateMatrixWorld(true); applyTweaks(t); applyProc(t); driveHelpers(); body.updateMatrixWorld(true); };
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
    const _look = new T.Vector3();
    const place = (ms, view = me.view) => {
      // view = { a: 방위각(도), e: 올려본 각(도), zoom: 배율, at: 뼈 이름 } — 검토 화면이 돌려 보고 당겨 볼 때 (MOVE_3D.view). 없으면 늘 보던 자리
      const a = (view && view.a != null ? view.a : 34 + (calm ? 0 : 8 * Math.sin(ms / 1400))) * D;       // 천천히 좌우로 돌며 입체를 보여 준다
      const e = (view && view.e != null ? view.e : 14) * D, d = dist / ((view && view.zoom) || 1);
      const at = view && view.at && bones.get(view.at) ? bones.get(view.at).getWorldPosition(_look) : target;
      camera.position.set(at.x + Math.sin(a) * Math.cos(e) * d, at.y + Math.sin(e) * d, at.z + Math.cos(a) * Math.cos(e) * d);
      camera.lookAt(at);
    };

    const clock = new T.Clock();
    const frame = () => {
      if (me.dead) return;
      restoreMixed();
      const dt = clock.getDelta(); mixer.update(stillBase ? 0 : dt);
      rememberMixed();
      body.updateMatrixWorld(true);
      applyTweaks(clock.elapsedTime);
      applyProc(clock.elapsedTime);
      driveHelpers();
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
      cycle, body,                                                            // body: 검사 도구가 살·가중치를 직접 들여다볼 때
      pause(){ if (me.raf) cancelAnimationFrame(me.raf); me.raf = null; },
      // view 를 주면 그 각도·그 뼈를 가까이서 찍는다 (팔·손 검토용) — place 와 같은 꼴
      seek(t, view){ poseAt(t); if (gear.update) gear.update(t, action.time); place(0, view ? { a: 34, e: 14, ...view } : null); renderer.render(scene, camera); },
      joints(){ const o = {}; for (const b of boneList) { b.getWorldPosition(v); b.getWorldQuaternion(_q1); o[b.name] = [v.x, v.y, v.z, _q1.x, _q1.y, _q1.z, _q1.w].map(x => +x.toFixed(5)); } return o; },
      helpers(){ const o = {}; for (const r of helperRig) { for (const j of [r.upper, r.lower]) o[j.bone.name] = [+(j.twist / D).toFixed(1), +(j.swing / D).toFixed(1)];
        if (r.hand) o[r.hand.name] = [+((r.short || 0) / D).toFixed(1), 0]; } return o; },   // 보조 뼈가 나눠 갖는 비틀림·휘두름(도), 손은 '손바닥이 덜 돌아간 만큼'(자세가 무리하면 0 이 아니다)
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
            if (sk.bones[best] && sk.bones[best].helperOf) best = sk.bones.indexOf(sk.bones[best].helperOf);   // 보조 뼈의 살은 본래 뼈 것으로
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
  const view = (canvas, v) => { const me = actives.get(canvas); if (me) me.view = v || null; };   // 검토 화면용: 카메라를 돌려 보고 당겨 본다 (앱 화면은 안 쓴다)
  return { start, stop, preload, qa, view, CLIPS, APPROX, TWEAKS, PROC, PROC_NOTE, GEAR, GRIP, GAP_NOTE, LOADING_NOTE, FALLBACK_CLIP, BASE, MODEL, SEX };
})();
