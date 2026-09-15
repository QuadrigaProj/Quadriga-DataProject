/* Mixamo 에서 우리 캐릭터로 동작을 내보내 받는 스크립트 — mixamo.com 에 로그인한 뒤 브라우저 개발자 도구 콘솔에 붙여 넣는다.
 *
 * 쓰는 법
 *   1. Mixamo 에 캐릭터를 올려 리깅한 뒤(README 참고) 그 캐릭터가 화면에 보이는 상태에서 F12 → Console.
 *   2. 이 파일 전체를 붙여 넣는다 (window.MX 가 생긴다).
 *   3. 캐릭터 메시:   await MX.get([{ id: 'tpose', q: 't-pose', name: 'T-Pose', skin: true }])
 *      동작 하나씩:   await MX.get([{ id: 'squat', q: 'air squat', name: 'Air Squat', descs: ['Air Squat Workout'] }])
 *      → 화면 왼쪽 위에 주황색 "DL squat" 링크가 뜬다. 눌러서 받는다 (자동 다운로드는 두 번째 파일부터 브라우저가 막으므로
 *        사람이 누른다). 링크 URL 은 5분이 지나면 만료된다.
 *   4. 받은 파일(제품 이름.fbx)은 docs/3d/collect_downloads.py 로 id 이름으로 옮긴다.
 *
 * 앱이 쓰는 동작 목록(MX.ITEMS)은 아래에. inplace 는 제자리 걸음/달리기용.
 */
window.MX = (() => {
  const tok = localStorage.getItem('access_token');
  const h = { 'Authorization': 'Bearer ' + tok, 'X-Api-Key': 'mixamo2', 'Accept': 'application/json', 'Content-Type': 'application/json' };
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const M = { pending: [] };
  M.ITEMS = [
    { id: 'squat', q: 'air squat', name: 'Air Squat', descs: ['Air Squat Workout'] },
    { id: 'pushup', q: 'push up', name: 'Push Up' },
    { id: 'plank', q: 'plank', name: 'Plank' },
    { id: 'crunch', q: 'situps', name: 'Situps' },
    { id: 'burpee', q: 'burpee', name: 'Burpee', descs: ['Burpee Workout'] },
    { id: 'barbell-squat', q: 'back squat', name: 'Back Squat', descs: ['Back Squat Workout'] },
    { id: 'dumbbell-curl', q: 'bicep curl', name: 'Bicep Curl' },
    { id: 'kettlebell-swing', q: 'kettlebell swing', name: 'Kettlebell Swing', descs: ['Russian Kettlebell Swing'] },
    { id: 'jump-rope', q: 'jumping rope', name: 'Jumping Rope' },
    { id: 'stair', q: 'ascending stairs', name: 'Ascending Stairs', inplace: true },
    { id: 'swim', q: 'swimming', name: 'Swimming', descs: ['Swimming Underwater'], inplace: true },
    { id: 'shoulder-stretch', q: 'arm stretching', name: 'Arm Stretching' },
    { id: 'neck-stretch', q: 'neck stretching', name: 'Neck Stretching' },
    { id: 'deep-breath', q: 'breathing idle', name: 'Breathing Idle' },
    { id: 'treadmill', q: 'treadmill running', name: 'Treadmill Running', inplace: true },
    { id: 'deadlift', q: 'sumo high pull', name: 'Sumo High Pull', descs: ['Sumo High Pull Workout'] },
    { id: 'shoulder-press', q: 'front raises', name: 'Front Raises' },
    { id: 'walk', q: 'standard walk', name: 'Standard Walk', inplace: true },
    { id: 'run', q: 'running', name: 'Running', descs: ['Running', 'Standard Run', 'Running Forward Quickly', 'Running Forward', 'Running With Intention'], inplace: true },
    { id: 'one-leg', q: 'pistol', name: 'Pistol', descs: ['Pistol Workout'] },
    { id: 'idle', q: 'fitness idle', name: 'Idle', descs: ['Male Fitness Idle', 'Male Fitness Idle With Breathing'] },
    { id: 'lying', q: 'lying down', name: 'Lying Down', descs: ['Laying Down On An Exam Table/Bed As In A Doctors Office'] },
    { id: 'kneel', q: 'kneeling', name: 'Kneeling', descs: ['Kneeling On One Knee Idle'] },
    { id: 'sit-reach', q: 'male sitting pose', name: 'Male Sitting Pose', descs: ['Reaching Hands Towards Toes'] },
    { id: 'sit', q: 'male sitting pose', name: 'Male Sitting Pose', descs: ['Arms Resting On Knees'] },
  ];
  M.primary = async () => fetch('/api/v1/characters/primary', { headers: h }).then(r => r.json());
  async function pick(item){
    const s = await fetch('/api/v1/products?page=1&limit=96&order=&type=Motion%2CMotionPack&query=' + encodeURIComponent(item.q), { headers: h }).then(r => r.json());
    const rs = (s.results || []).filter(x => x.type === 'Motion');
    for (const d of (item.descs || [])) { const m = rs.find(x => x.name === item.name && x.description === d); if (m) return m; }
    return rs.find(x => x.name === item.name) || rs[0];
  }
  // 하나씩 내보내고(1분쯤) 완성되면 pending 에 URL 을 둔다
  M.export = async (items) => {
    const CH = (await M.primary()).primary_character_id;
    const out = [];
    for (const item of items) {
      try {
        const m = await pick(item);
        const d = await fetch('/api/v1/products/' + m.id + '?similar=0&character_id=' + CH, { headers: h }).then(r => r.json());
        const g = d.details.gms_hash;
        const gms = { 'model-id': g['model-id'], mirror: false, trim: [0, 100], inplace: !!(item.inplace && d.details.supports_inplace), 'arm-space': 0, params: (g.params || []).map(p => p[1]).join(',') };
        const body = { gms_hash: [gms], preferences: { format: 'fbx7_2019', skin: item.skin ? 'true' : 'false', fps: '30', reducekf: '0' }, character_id: CH, type: 'Motion', product_name: m.name };
        await fetch('/api/v1/animations/export', { method: 'POST', headers: h, body: JSON.stringify(body) });
        let mon = null;
        for (let i = 0; i < 80; i++) { await sleep(1500); mon = await fetch('/api/v1/characters/' + CH + '/monitor', { headers: h }).then(r => r.json()); if (mon.status === 'completed' || mon.status === 'failed') break; }
        if (mon && mon.status === 'completed') { M.pending.push({ id: item.id, url: mon.job_result }); out.push(item.id + ': ok (' + m.name + ')'); }
        else out.push(item.id + ': ' + (mon && mon.status));
      } catch (e) { out.push(item.id + ': ' + e.message); }
    }
    return out;
  };
  // pending 의 URL 을 화면 왼쪽 위 링크로 — 사람이 눌러 받는다
  M.links = () => {
    document.querySelectorAll('a.__dl').forEach(a => a.remove());
    M.pending.forEach((p, i) => {
      const a = document.createElement('a'); a.className = '__dl'; a.href = p.url; a.textContent = 'DL ' + p.id;
      a.style.cssText = 'position:fixed;left:10px;top:' + (10 + i * 50) + 'px;width:200px;height:40px;line-height:40px;background:#ff8800;color:#fff;font:bold 16px sans-serif;text-align:center;z-index:2147483647;';
      document.body.appendChild(a);
    });
    const n = M.pending.length; M.pending = []; return n;
  };
  M.get = async (items) => { const r = await M.export(items); M.links(); return r; };
  return M;
})();
