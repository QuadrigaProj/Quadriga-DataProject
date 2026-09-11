/* 영상이 없는 동작을 위한 3D 캐릭터 (M5).
 *
 * 고른 종목·기록 종목은 공식 영상이 없다. 그 자리에 Mixamo(Adobe)의 무료
 * 캐릭터 "Y Bot" 이 실제 사람의 모션캡처로 그 동작을 하는 모습을 띄운다.
 * 캐릭터와 동작 모두 Mixamo 에서 받은 것이고, 우리는 그 파일을 웹용 GLB 로
 * 바꿔 assets/3d 에 두었다 (ybot.glb = 캐릭터, anim/*.glb = 동작 하나씩).
 *
 * 여기서 손보는 것:
 *   - 겉모습: 각진 면을 매끈하게 다듬고(법선 다시 계산) 회색 하나로 칠한다.
 *   - 비슷한 동작으로 대신하는 넷은 뼈 몇 개를 덮어써 원래 동작에 가깝게 (TWEAKS).
 *   - 기구가 필요한 동작엔 바벨·덤벨·케틀벨·줄·트레드밀·물을 손과 몸에 붙여 준다 (GEAR).
 *
 * three.js 와 GLTFLoader 는 js/vendor 에 같이 둔다 (import() 는 이 파일 기준 상대경로) —
 * 밖에서 받지 않으니 오프라인 시연에서도 돈다. 처음 필요할 때 한 번만 불러온다.
 */
const MOVE_3D = (() => {
  const BASE = 'assets/3d/';
  const D = Math.PI / 180;

  /* 동작 id → 동작 파일 (anim/<이름>.glb). 같은 파일을 여러 id 가 쓸 수 있다. */
  const CLIPS = {
    'squat': 'squat', 'pushup': 'pushup', 'knee-pushup': 'pushup', 'plank': 'plank', 'crunch': 'crunch',
    'burpee': 'burpee', 'barbell-squat': 'barbell-squat', 'dumbbell-curl': 'dumbbell-curl',
    'kettlebell-swing': 'kettlebell-swing', 'jump-rope': 'jump-rope', 'stair': 'stair', 'swim': 'swim',
    'shoulder-stretch': 'shoulder-stretch', 'neck-stretch': 'neck-stretch', 'deep-breath': 'deep-breath',
    'treadmill': 'treadmill', 'deadlift': 'deadlift', 'shoulder-press': 'shoulder-press',
    'walk': 'walk', 'run': 'run', 'one-leg': 'one-leg',
  };
  /* 똑같은 동작이 Mixamo 에 없어 비슷한 동작을 손봐서 보여 주는 것 — 화면에 그렇다고 적는다 */
  const APPROX = {
    'knee-pushup': '푸시업 동작의 무릎을 바닥에 붙여 무릎 푸시업으로 손봤어요',
    'deadlift': '스모 하이풀 동작의 팔을 늘어뜨려 데드리프트처럼 손봤어요',
    'shoulder-press': '기본 자세에 팔을 밀어 올리는 동작을 더해 숄더프레스로 보여 줘요',
    'one-leg': '기본 자세에 한 발을 든 자세를 더해 한 발 서기로 보여 줘요',
  };
  /* 아직 동작 파일이 없는 것은 기본 자세(idle)만 보여 준다 */
  const GAP_NOTE = '이 동작의 3D 동작은 아직 없어 기본 자세만 보여 줘요';
  const FALLBACK_CLIP = 'idle';

  /* ---- 비슷한 동작 손보기 ----
   * base      : 바탕으로 쓸 동작 파일 (없으면 CLIPS 의 것)
   * pitchAtHands : 두 손을 축으로 몸 전체를 기울이기 (도)
   * bones     : 뼈 이름 → { set: [x,y,z] 뼈 기준 각도로 바꿈 | aim: [x,y,z] 세상 기준 이 방향을 가리키게,
   *             roll: 그 축으로 비틀기(도), palmTo: 'head' 면 손바닥이 머리 쪽을 보게 비튼다 }
   *             함수면 초 단위 시간을 받아 매 프레임 새로 준다
   * fist      : 손가락을 말아 쥔다 (기구를 잡는 동작) */
  const press = t => {
    const p = (1 - Math.cos(t / 1.6 * Math.PI * 2)) / 2;               // 1.6초에 한 번 올렸다 내린다
    const a = (85 + 80 * p) * D, e = (95 - 85 * p) * D;              // 팔 벌림 · 팔꿈치
    const up = [Math.sin(a), -Math.cos(a), 0], fa = [Math.sin(a + e), -Math.cos(a + e), 0];
    // 아래팔은 손바닥이 머리 쪽을 보게 비튼다 (뉴트럴 그립)
    return { 'mixamorig:LeftArm': { aim: up }, 'mixamorig:LeftForeArm': { aim: fa, palmTo: 'head' },
             'mixamorig:RightArm': { aim: [-up[0], up[1], 0] }, 'mixamorig:RightForeArm': { aim: [-fa[0], fa[1], 0], palmTo: 'head' } };
  };
  const oneLeg = () => {
    const 팔 = [Math.sin(60 * D), -Math.cos(60 * D), 0];
    return { 'mixamorig:LeftUpLeg': { aim: [0, -Math.cos(60 * D), Math.sin(60 * D)] },     // 왼쪽 허벅지를 앞으로 들고
             'mixamorig:LeftLeg': { aim: [0, -1, -0.25] },                                  // 정강이는 아래로 — 발이 확실히 뜬다
             'mixamorig:LeftArm': { aim: 팔 }, 'mixamorig:LeftForeArm': { aim: 팔 },
             'mixamorig:RightArm': { aim: [-팔[0], 팔[1], 0] }, 'mixamorig:RightForeArm': { aim: [-팔[0], 팔[1], 0] } };
  };
  const hang = { aim: [0, -1, 0.15] };
  const TWEAKS = {
    'knee-pushup': { pitchAtHands: -14, bones: { 'mixamorig:LeftLeg': { set: [90, 0, 0] }, 'mixamorig:RightLeg': { set: [90, 0, 0] } } },
    'deadlift': { fist: true, bones: { 'mixamorig:LeftArm': hang, 'mixamorig:RightArm': hang, 'mixamorig:LeftForeArm': hang, 'mixamorig:RightForeArm': hang } },
    'shoulder-press': { base: 'idle', bones: press, fist: true },
    'one-leg': { base: 'idle', bones: oneLeg },
  };

  /* ---- 기구 ---- 동작 id → 기구. 손·몸 뼈의 세상 좌표를 따라 매 프레임 옮긴다. */
  const GEAR = {
    'barbell-squat': 'backbar', 'deadlift': 'barbell', 'dumbbell-curl': 'dumbbells', 'shoulder-press': 'dumbbells',
    'kettlebell-swing': 'kettlebell', 'jump-rope': 'rope', 'treadmill': 'treadmill', 'swim': 'water',
  };

  /* 손잡이 자리: 손 뼈는 손목에서 시작하니 손가락 쪽으로 조금 나간 곳(손바닥 가운데)을 잡는다.
     axis 는 손바닥을 가로지르는 축 — 덤벨·줄넘기 손잡이가 이 축을 따라 눕는다. */
  const GRIP = { along: 0.055, side: 0.0, curl: 75, thumbCurl: 40 };

  /* ---- three.js 불러오기 (한 번만). 'three' 는 index.html 의 importmap 이 js/vendor 로 잇는다 ---- */
  let libP = null;
  function loadLib(){
    if (!libP) {
      libP = Promise.all([import('three'), import('./vendor/loaders/GLTFLoader.js'), import('./vendor/utils/BufferGeometryUtils.js')])
        .then(([T, L, U]) => ({ T, GLTFLoader: L.GLTFLoader, U }))
        .catch(e => { libP = null; throw e; });
    }
    return libP;
  }
  function loadGltf(lib, url){
    return new Promise((res, rej) => new lib.GLTFLoader().load(url, res, undefined, rej));
  }
  // 동작은 나눠 쓸 수 있으니 한 번 받으면 기억한다. 캐릭터는 장면마다 새로 읽는다.
  const clipCache = new Map();
  function loadClip(lib, name){
    if (!clipCache.has(name)) {
      clipCache.set(name, loadGltf(lib, BASE + 'anim/' + name + '.glb').then(g => g.animations[0])
        .catch(e => { clipCache.delete(name); throw e; }));
    }
    return clipCache.get(name);
  }

  /* 겉모습: 각진 면을 매끈하게(같은 자리 꼭짓점을 합치고 법선을 다시 계산), 회색 하나로 */
  function smoothAndGray(lib, body){
    const { T, U } = lib;
    body.traverse(o => {
      if (!o.isMesh) return;
      const g = o.geometry.clone();
      g.deleteAttribute('normal'); g.deleteAttribute('uv');                 // 텍스처는 안 쓰니 이음새도 합친다
      const merged = U.mergeVertices(g, 1e-4); merged.computeVertexNormals();
      o.geometry = merged;
      const joints = /joint/i.test(o.material?.name || '') || /joint/i.test(o.name || '');
      o.material = new T.MeshStandardMaterial({ color: joints ? 0xA4A9B0 : 0xBCC1C7, roughness: 0.62, metalness: 0.04 });
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
      case 'water': {
        const w = new T.Mesh(new T.PlaneGeometry(4, 4), new T.MeshStandardMaterial({ color: 0xE1E6EC, transparent: true, opacity: 0.55, roughness: 0.3 }));
        w.rotation.x = -Math.PI / 2; w.position.y = 0.15; w.receiveShadow = true; add(w);
        return {};
      }
    }
    return {};
  }

  /* ---- 무대 ---- */
  function setup(lib, me, clip){
    const { T } = lib;
    const { canvas, body, id } = me;
    const size = Math.max(160, Math.min(canvas.clientWidth || 320, 480));
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const renderer = new T.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setPixelRatio(dpr); renderer.setSize(size, size, false);
    renderer.setClearColor(0x000000, 0);
    renderer.shadowMap.enabled = true; renderer.shadowMap.type = T.PCFSoftShadowMap;
    const scene = new T.Scene();
    scene.add(new T.HemisphereLight(0xffffff, 0x9AA3AD, 1.6));
    const key = new T.DirectionalLight(0xffffff, 2.4); key.position.set(2.5, 4.5, 3); key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024); key.shadow.bias = -0.0004;
    Object.assign(key.shadow.camera, { left: -2, right: 2, top: 3, bottom: -1, near: 1, far: 14 });
    scene.add(key);
    const fill = new T.DirectionalLight(0xffffff, 0.8); fill.position.set(-3, 2, -2); scene.add(fill);
    const floor = new T.Mesh(new T.PlaneGeometry(10, 10), new T.ShadowMaterial({ opacity: 0.18 }));
    floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);

    // 캐릭터: 크기를 미터로 맞추고, 매끈한 회색으로
    const box = new T.Box3().setFromObject(body);
    const h = box.max.y - box.min.y;
    if (h > 10) body.scale.setScalar(1 / h * 1.8);          // cm 단위로 왔으면 사람 키로
    smoothAndGray(lib, body);
    scene.add(body);
    body.updateMatrixWorld(true);
    // GLTFLoader 는 뼈 이름의 ':' 를 지운다(mixamorig:Hips → mixamorigHips). 글자만 남겨 맞춘다.
    const norm = n => String(n).replace(/[^A-Za-z]/g, '');
    const map = new Map(); const boneList = [];
    body.traverse(o => { if (o.isBone) { map.set(norm(o.name), o); boneList.push(o); } });
    const bones = { get: n => map.get(norm(n)) };
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
    const still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

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
        aimBone(bone, how.aim);
        if (how.roll) { bone.quaternion.multiply(_q1.setFromAxisAngle(_v3.set(0, 1, 0), how.roll * D)); bone.updateMatrixWorld(true); }
        if (how.palmTo) palmToward(bone, how.palmTo);
      }
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
    const poseAt = t => { mixer.setTime(t); body.updateMatrixWorld(true); applyTweaks(t); };

    // 기구
    const v = new T.Vector3();
    const ctx = { scene, hand, pos: (n, v) => bones.get(n) ? bones.get(n).getWorldPosition(v) : v.set(0, 0, 0), quat: (n, q) => bones.get(n) ? bones.get(n).getWorldQuaternion(q) : q.identity() };
    if (GEAR[id] === 'rope') {
      const hips = bones.get('mixamorig:Hips'); const N = 60, ys = [];
      for (let i = 0; i < N; i++) { poseAt(clip.duration * i / N); ys.push(hips.getWorldPosition(v).y); }
      const peaks = []; for (let i = 0; i < N; i++) { const pv = ys[(i + N - 1) % N], c = ys[i], nx = ys[(i + 1) % N]; if (c > pv && c >= nx) peaks.push(i); }
      ctx.jump = { peak0: peaks.length ? clip.duration * peaks[0] / N : 0, period: peaks.length ? clip.duration / peaks.length : 0.6 };
    }
    const gear = GEAR[id] ? makeGear(T, GEAR[id], ctx) : {};

    // 카메라는 이 동작이 한 바퀴 도는 동안 뼈대가 차지하는 상자 전체에 맞춘다 —
    // 서 있다가 엎드리는 동작도 처음부터 끝까지 화면에 다 들어오고, 흔들리지 않는다
    const camera = new T.PerspectiveCamera(30, 1, 0.1, 60);
    const lo = new T.Vector3(Infinity, Infinity, Infinity), hi = new T.Vector3(-Infinity, -Infinity, -Infinity);
    for (let i = 0; i <= 24; i++) {
      poseAt(clip.duration * i / 24);
      for (const b of boneList) { b.getWorldPosition(v); lo.min(v); hi.max(v); }
    }
    poseAt(0);
    if (!isFinite(lo.x)) { lo.set(-0.5, 0, -0.5); hi.set(0.5, 1.8, 0.5); }
    const target = lo.clone().add(hi).multiplyScalar(0.5);
    const dist = Math.max(hi.x - lo.x, hi.y - lo.y + 0.3, hi.z - lo.z, 1.2) * 1.9 + 0.8;   // 머리·손끝 여유
    const place = ms => {
      const a = (34 + (still ? 0 : 8 * Math.sin(ms / 1400))) * D;      // 천천히 좌우로 돌며 입체를 보여 준다
      const e = 14 * D;
      camera.position.set(target.x + Math.sin(a) * Math.cos(e) * dist, target.y + Math.sin(e) * dist, target.z + Math.cos(a) * Math.cos(e) * dist);
      camera.lookAt(target);
    };

    if (still) { action.paused = true; action.time = clip.duration / 2; }
    const clock = new T.Clock();
    const frame = () => {
      if (me.dead) return;
      mixer.update(clock.getDelta());
      body.updateMatrixWorld(true);
      applyTweaks(clock.elapsedTime);
      if (gear.update) gear.update(clock.elapsedTime, action.time);
      place(clock.elapsedTime * 1000);
      renderer.render(scene, camera);
      if (!still) me.raf = requestAnimationFrame(frame);
    };
    me.renderer = renderer;
    frame();
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
  function start(canvas, id, { onNote } = {}){
    if (!canvas || !id) return false;
    stop(canvas);
    const clipName = (TWEAKS[id] && TWEAKS[id].base) || CLIPS[id] || FALLBACK_CLIP;
    const note = CLIPS[id] ? (APPROX[id] || '') : GAP_NOTE;
    if (onNote) onNote(note);
    const me = { canvas, id, dead: false, raf: null, renderer: null, body: null };
    actives.set(canvas, me);
    loadLib()
      .then(lib => Promise.all([lib, loadGltf(lib, BASE + 'ybot.glb'), loadClip(lib, clipName)]))
      .then(([lib, gltf, clip]) => { if (me.dead) return; me.body = gltf.scene; setup(lib, me, clip); })
      .catch(err => { console.warn('3D 동작을 못 불러왔어요', err); if (!me.dead) fallbackText(canvas, '3D 동작을 불러오지 못했어요'); });
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

  return { start, stop, CLIPS, APPROX, TWEAKS, GEAR, GRIP, GAP_NOTE, FALLBACK_CLIP, BASE };
})();
