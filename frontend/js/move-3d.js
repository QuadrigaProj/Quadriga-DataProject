/* 영상이 없는 동작을 위한 3D 캐릭터 (M5).
 *
 * 고른 종목·기록 종목은 공식 영상이 없다. 그 자리에 Mixamo(Adobe)의 무료
 * 캐릭터 "Y Bot" 이 실제 사람의 모션캡처로 그 동작을 하는 모습을 띄운다.
 * 캐릭터와 동작 모두 Mixamo 에서 받은 것이고, 우리는 그 파일을 웹용 GLB 로
 * 바꿔 assets/3d 에 두었다 (ybot.glb = 캐릭터, anim/*.glb = 동작 하나씩).
 *
 * three.js 와 GLTFLoader 는 js/vendor 에 같이 둔다 (import() 는 이 파일 기준 상대경로) — 밖에서 받지 않으니
 * 오프라인 시연에서도 돈다. 처음 필요할 때 한 번만 불러온다.
 */
const MOVE_3D = (() => {
  const BASE = 'assets/3d/';

  /* 동작 id → 동작 파일 (anim/<이름>.glb). 같은 파일을 여러 id 가 쓸 수 있다. */
  const CLIPS = {
    'squat': 'squat', 'pushup': 'pushup', 'knee-pushup': 'pushup', 'plank': 'plank', 'crunch': 'crunch',
    'burpee': 'burpee', 'barbell-squat': 'barbell-squat', 'dumbbell-curl': 'dumbbell-curl',
    'kettlebell-swing': 'kettlebell-swing', 'jump-rope': 'jump-rope', 'stair': 'stair', 'swim': 'swim',
    'shoulder-stretch': 'shoulder-stretch', 'neck-stretch': 'neck-stretch', 'deep-breath': 'deep-breath',
    'treadmill': 'treadmill', 'deadlift': 'deadlift', 'shoulder-press': 'shoulder-press',
    'walk': 'walk', 'run': 'run', 'one-leg': 'one-leg',
  };
  /* 똑같은 동작이 Mixamo 에 없어 비슷한 동작으로 보여 주는 것 — 화면에 그렇다고 적는다 */
  const APPROX = {
    'knee-pushup': '무릎 푸시업 대신 일반 푸시업 동작이에요',
    'deadlift': '데드리프트 대신 비슷한 스모 하이풀 동작이에요',
    'shoulder-press': '숄더프레스 대신 비슷한 프론트 레이즈 동작이에요',
    'one-leg': '한 발 서기 대신 한 발 스쿼트(피스톨) 동작이에요',
  };
  /* 아직 동작 파일이 없는 것은 기본 자세(idle)만 보여 준다 */
  const GAP_NOTE = '이 동작의 3D 동작은 아직 없어 기본 자세만 보여 줘요';
  const FALLBACK_CLIP = 'idle';

  /* ---- three.js 불러오기 (한 번만). 'three' 는 index.html 의 importmap 이 js/vendor 로 잇는다 ---- */
  let libP = null;
  function loadLib(){
    if (!libP) {
      libP = Promise.all([import('three'), import('./vendor/loaders/GLTFLoader.js')])
        .then(([T, L]) => ({ T, GLTFLoader: L.GLTFLoader }))
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

  /* ---- 무대 ---- */
  function setup(lib, me, clip){
    const { T } = lib;
    const { canvas, body } = me;
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

    // 캐릭터: 크기를 미터로 맞추고, 그림자를 드리우게
    const box = new T.Box3().setFromObject(body);
    const h = box.max.y - box.min.y;
    if (h > 10) body.scale.setScalar(1 / h * 1.8);          // cm 단위로 왔으면 사람 키로
    // Mixamo 미리보기처럼 밝은 파랑 몸 + 짙은 관절. 파일 색은 더 어두워서 여기서 맞춘다.
    body.traverse(o => {
      if (!o.isMesh) return;
      o.castShadow = true; o.frustumCulled = false;
      const m = o.material; if (!m) return;
      const joints = /joint/i.test(m.name || '') || /joint/i.test(o.name || '');
      m.color.set(joints ? 0x2B3742 : 0x74B4D4); m.roughness = joints ? 0.7 : 0.45; m.metalness = joints ? 0.1 : 0.15;
    });
    scene.add(body);
    const bones = []; body.traverse(o => { if (o.isBone) bones.push(o); });

    const mixer = new T.AnimationMixer(body);
    const action = mixer.clipAction(clip); action.play();
    const still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (still) { action.paused = true; action.time = clip.duration / 2; }

    // 카메라는 이 동작이 한 바퀴 도는 동안 뼈대가 차지하는 상자 전체에 맞춘다 —
    // 서 있다가 엎드리는 동작도 처음부터 끝까지 화면에 다 들어오고, 흔들리지 않는다
    const camera = new T.PerspectiveCamera(30, 1, 0.1, 60);
    const v = new T.Vector3(), lo = new T.Vector3(Infinity, Infinity, Infinity), hi = new T.Vector3(-Infinity, -Infinity, -Infinity);
    for (let i = 0; i <= 24; i++) {
      mixer.setTime(clip.duration * i / 24); body.updateMatrixWorld(true);
      for (const b of bones) { b.getWorldPosition(v); lo.min(v); hi.max(v); }
    }
    mixer.setTime(0);
    if (!isFinite(lo.x)) { lo.set(-0.5, 0, -0.5); hi.set(0.5, 1.8, 0.5); }
    const target = lo.clone().add(hi).multiplyScalar(0.5);
    const dist = Math.max(hi.x - lo.x, hi.y - lo.y + 0.3, hi.z - lo.z, 1.2) * 1.9 + 0.8;   // 머리·손끝 여유
    const place = ms => {
      const a = (34 + (still ? 0 : 8 * Math.sin(ms / 1400))) * Math.PI / 180;   // 천천히 좌우로 돌며 입체를 보여 준다
      const e = 14 * Math.PI / 180;
      camera.position.set(target.x + Math.sin(a) * Math.cos(e) * dist, target.y + Math.sin(e) * dist, target.z + Math.cos(a) * Math.cos(e) * dist);
      camera.lookAt(target);
    };

    const clock = new T.Clock();
    const frame = () => {
      if (me.dead) return;
      mixer.update(clock.getDelta());
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
    const clipName = CLIPS[id] || FALLBACK_CLIP;
    const note = CLIPS[id] ? (APPROX[id] || '') : GAP_NOTE;
    if (onNote) onNote(note);
    const me = { canvas, dead: false, raf: null, renderer: null, body: null };
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

  return { start, stop, CLIPS, APPROX, GAP_NOTE, FALLBACK_CLIP, BASE };
})();
