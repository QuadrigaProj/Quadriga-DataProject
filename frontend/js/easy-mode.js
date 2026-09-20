/* 쉬운 모드 — 앱 이용이 어려우실 수 있는 분들을 위한 화면.

   어르신 전용이 아니다. 발달장애 · 시각장애가 있는 분도 쓴다고 보고 만든다:
   쉬운 말 · 짧은 문장, 그림 + 글, 큰 글자와 또렷한 색, 화면을 읽어 주기, 화면낭독기 초점과 알림,
   휴대폰 자판 대신 화면 안의 큰 숫자판, "또래 10명 중 몇 번째", 동작을 글로도 설명하기.

   일반 화면 위에 통째로 덮는 층(#easyRoot)이다. 화면만 다르고 **계산 · 저장 · 기록은 일반 모드와 같은 것을 쓴다** —
   체력나이는 서버(/fitness-age)가 내고, 결과는 commitResult() 로, 운동한 날은 routineLog 로 남는다.
   그래서 두 모드를 오가도 숫자와 기록이 같다. (index.html 의 state · API · measurement() … 를 그대로 부른다)

   들어오는 문: 로그인하면(applyProfile 끝) EASY.afterLogin() — 고른 적이 없으면 '쉬운 모드 / 일반 모드' 두 버튼이 먼저 뜬다.
   고른 모드는 프로필(state.uiMode)에 저장되고, 프로필의 '화면 모드' 에서 언제든 바꾼다.
   글자 크기 · 또렷한 색 · 자동 읽기는 이 기기의 보기 설정이라 localStorage 에만 둔다. */
(() => {
  'use strict';

  const VIEW_KEY = 'quadriga.easyView';
  const root = () => document.getElementById('easyRoot');
  const grpOf = age => ageGroup(age);                  // 앱과 같은 경계: 11~18 성장기 · 19~64 성인 · 65+ 어르신

  /* 나이대마다 힘을 재는 방법이 다르다 — 앱(국민체력100)과 같다 */
  const POWER = {
    '어르신': { item: '의자앉았다일어서기', key: '근지구력', name: '다리 힘', title: '의자에서 일어서기', short: '일어선 횟수', unit: '번', max: 80, secs: 30, def: 15,
      why: '30초 동안 몇 번 일어서는지 봐요. 다리 힘을 알 수 있어요.',
      how: ['등받이 있는 튼튼한 의자를 벽에 붙여요.', '두 팔을 가슴 앞에 모아요.', '무릎을 다 펴고 일어섰다가, 엉덩이가 닿게 앉아요.'],
      safe: '어지럽거나 아프면 바로 멈춰요. 센 데까지만 넣어도 돼요.',
      runTitle: '일어설 때마다 아래를 눌러요', padText: '여기를 눌러서 세요', rec: v => `30초에 ${v}번 일어섰어요`, confirm: v => `${v}번 일어서셨어요.` },
    '성인': { item: '교차윗몸일으키기', key: '근지구력', name: '배 힘', title: '윗몸일으키기', short: '윗몸일으키기 횟수', unit: '번', max: 100, secs: 60, def: 25,
      why: '1분 동안 몇 번 하는지 봐요. 배와 허리 힘을 알 수 있어요.',
      how: ['등을 대고 누워 무릎을 세워요. 발은 누가 잡아 주거나 가구 밑에 걸어요.', '두 팔을 가슴 앞에 엇갈려 모아요.', '몸을 일으켜 팔꿈치가 허벅지에 닿으면 1번이에요.'],
      safe: '목이나 허리가 아프면 바로 멈춰요. 하는 동안에는 세어 주는 분이 화면을 눌러 주세요.',
      runTitle: '한 번 할 때마다 아래를 눌러요', padText: '세어 주는 분이 여기를 눌러요', rec: v => `1분에 ${v}번 했어요`, confirm: v => `${v}번 하셨어요.` },
    '성장기': { item: '제자리멀리뛰기', key: '순발력', name: '뛰는 힘', title: '제자리 멀리뛰기', short: '뛴 거리', unit: 'cm', max: 350, secs: 0, def: 150,
      why: '제자리에서 얼마나 멀리 뛰는지 봐요.',
      how: ['출발선에 두 발을 모으고 서요.', '팔을 흔들며 앞으로 힘껏 뛰어요.', '출발선에서 뒤꿈치가 닿은 곳까지 줄자로 재요.'],
      safe: '미끄럽지 않은 바닥에서 해요. 두 번 뛰어서 더 먼 쪽을 넣어요.', rec: v => `${v}cm 뛰었어요` },
  };

  const FIELDS = {
    age: { label: '나이', obj: '나이를', unit: '세', min: 11, max: 100 },
    height: { label: '키', obj: '키를', unit: 'cm', min: 100, max: 210 },
    weight: { label: '몸무게', obj: '몸무게를', unit: 'kg', min: 20, max: 150 },
    reach: { label: '굽힌 길이', obj: '길이를', unit: 'cm', min: -30, max: 40, neg: true },
    steps: { label: '걸음 수', obj: '걸음 수를', unit: '번', min: 0, max: 250 },
  };
  const fieldOf = f => { if (f !== 'power') return FIELDS[f]; const t = POWER[grp()]; return { label: t.short, obj: '숫자를', unit: t.unit, min: 0, max: t.max }; };

  /* ── 상태 ──
     V: 이 기기의 보기 설정.  P: 재는 동안 들고 있는 값(결과 보기를 눌러야 앱의 state 로 옮긴다).  */
  let V = { size: 0, hc: false, auto: false };
  try { V = { ...V, ...(JSON.parse(localStorage.getItem(VIEW_KEY) || 'null') || {}) }; } catch (e) {}
  const saveView = () => { try { localStorage.setItem(VIEW_KEY, JSON.stringify(V)); } catch (e) {} };
  let P = null, screen = 'mode', phase = 'how', ex = 0, T = null, sheet = null, pad = null, busy = false, opened = false;

  function loadP(){
    const g = state.age ? grpOf(state.age) : null;
    const 잰적 = !!(state.result || state.first);      // 점검한 적이 없으면 성별을 미리 골라 두지 않는다 — 일반 화면의 기본값(남성)이 말없이 따라오면 안 된다
    P = { age: state.age || 60, sex: 잰적 ? (state.sex || null) : null, height: state.height ?? null, weight: state.weight ?? null,
          power: state.strength ?? null, reach: state.flexibility ?? null, steps: g === '어르신' ? (state.endurance ?? null) : null };
    lastGroup = grpOf(P.age);
  }

  /* ── 말 ── */
  const grp = () => grpOf(P.age);
  const NAMES = { '유연성': '몸 굽히기', '심폐지구력': '오래 걷는 힘', '체성분': '몸무게' };
  const nameOf = k => NAMES[k] || POWER[grp()].name;
  const diffText = d => grp() === '성장기'
    ? (d > 0 ? `또래보다 ${d}살 앞서 있어요.` : d < 0 ? `또래보다 ${-d}살 천천히 가고 있어요.` : '또래와 같아요.')
    : (d < 0 ? `실제 나이보다 ${-d}살 젊어요.` : d > 0 ? `실제 나이보다 ${d}살 많게 나왔어요.` : '실제 나이와 같아요.');
  const ageTitle = () => grp() === '성장기' ? '내 발달 나이' : '내 체력나이';
  const stateOf = pct => pct >= 60 ? ['good', '좋아요'] : pct >= 30 ? ['okay', '보통이에요'] : ['low', '조금 더 힘내요'];
  const rank10 = pct => Math.max(1, Math.min(10, Math.ceil((100 - pct) / 10)));
  const reachText = v => v > 0 ? `손끝이 발끝을 ${v}cm 넘었어요` : v < 0 ? `손끝이 발끝까지 ${-v}cm 남았어요` : '손끝이 발끝에 딱 닿았어요';
  const fmtDay = d => `${d.getMonth() + 1}월 ${d.getDate()}일`;
  const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const dayShift = n => { const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() + n); return d; };

  /* 결과는 서버가 낸 것(state.result)을 읽는다 — 일반 모드와 같은 숫자다 */
  const nowAge = () => (state.result && displayAge() != null) ? displayAge() : null;
  function rows(){
    const peers = state.result?.또래비교 || {}, t = POWER[grp()], out = [];
    const add = (k, rec) => { const pct = peers[k]?.백분위; if (typeof pct === 'number') out.push({ k, rec, pct }); };
    if (state.strength != null) add(t.key, t.rec(state.strength));
    if (state.flexibility != null) add('유연성', reachText(state.flexibility));
    if (state.endurance != null && grp() === '어르신') add('심폐지구력', `2분에 ${state.endurance}번 걸었어요`);
    return out;
  }
  /* 몸무게는 나이로 바꾸지 않는다. 성인 · 어르신은 널리 쓰는 기준으로만 말하고, 성장기는 말하지 않는다(자라는 중이라 같은 기준을 쓸 수 없다) */
  function bmiRow(){
    if (grp() === '성장기' || !state.height || !state.weight) return null;
    const b = state.weight / Math.pow(state.height / 100, 2);
    return b < 18.5 ? { st: ['okay', '마른 편이에요'], rec: '조금 더 드셔도 좋아요' } : b < 25 ? { st: ['good', '알맞아요'], rec: '지금 몸무게를 지켜 주세요' } : { st: ['okay', '조금 무거운 편이에요'], rec: '무릎을 위해 천천히 줄여 봐요' };
  }
  /* 운동한 날 — 일반 모드에서 한 것도 같이 센다 */
  const stamps = () => new Set(allRoutineLog().map(e => e.date));

  /* ── 소리 · 진동 · 화면낭독기 알림 ── */
  function say(text){
    try { const u = new SpeechSynthesisUtterance(text); u.lang = 'ko-KR'; u.rate = 0.95; speechSynthesis.cancel(); speechSynthesis.speak(u); } catch (e) {}
  }
  const hush = () => { try { speechSynthesis.cancel(); } catch (e) {} };
  const live = text => { const el = document.getElementById('ezLive'); if (!el) return; el.textContent = ''; setTimeout(() => { el.textContent = text; }, 30); };      // 화면낭독기에게만
  const buzz = ms => { try { if (navigator.vibrate) navigator.vibrate(ms); } catch (e) {} };
  let audio = null;
  function beep(freq, sec){
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      const o = audio.createOscillator(), g = audio.createGain();
      o.frequency.value = freq; o.connect(g); g.connect(audio.destination);
      g.gain.setValueAtTime(0.18, audio.currentTime); g.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + sec);
      o.start(); o.stop(audio.currentTime + sec);
    } catch (e) {}
  }

  /* ── 그림 ── */
  const IC = {
    back: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg>',
    go: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5l7 7-7 7"/></svg>',
    spk: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9H4z"/><path d="M17 8.5a5 5 0 010 7"/></svg>',
    eye: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.8"/></svg>',
    watch: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="13.5" r="7"/><path d="M12 13.5V9.5M9.5 3h5"/></svg>',
    move: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="4.5" r="2"/><path d="M12 7.5v6.5l-3 6M12 14l3 6M6.5 11l5.5-2 5.5 2"/></svg>',
    cal: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="5.5" width="16" height="14.5" rx="2.5"/><path d="M4 10.5h16M9 3.5v4M15 3.5v4"/></svg>',
    warn: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4l9 16H3z"/><path d="M12 10v4.5M12 17.4v.1"/></svg>',
    hand: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 11V5.5a1.8 1.8 0 013.6 0V11M12.6 10V8.5a1.7 1.7 0 013.4 0V11M16 11v-.5a1.7 1.7 0 013.4 0V15a6 6 0 01-6 6h-1.2a6 6 0 01-4.9-2.5L4 13.8a1.7 1.7 0 012.7-2L9 14"/></svg>',
    grid: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5"/></svg>',
  };
  const CHAIR = '<g class="chair"><path d="M70 96h50M70 96V46M73 96v42M117 96v42"/></g>';
  const CHAIR_R = '<g class="chair"><path d="M100 96h50M150 96V46M103 96v42M147 96v42"/></g>';
  const FLOOR = '<g class="chair"><path d="M30 140h170"/></g>';
  const FIG = {
    sit: ['40 12 130 134', `${CHAIR}<circle cx="98" cy="36" r="11"/><path d="M98 49v45h38v44M98 62l28-8M98 62l-24-10"/><g class="hint"><path d="M134 40a12 12 0 1 1-6-10"/></g>`],
    squat: ['50 8 175 138', `${CHAIR}<circle cx="166" cy="28" r="11"/><path d="M166 41v50l-8 47M166 91l8 47M166 57l24 4"/><g class="hint"><path d="M204 54v58M196 64l8-10 8 10M196 102l8 10 8-10"/></g>`],
    heel: ['85 6 150 140', `${CHAIR_R}<circle cx="186" cy="26" r="11"/><path d="M186 39v50l-5 41M186 89l6 41M186 56l-34-9M181 130l-9 6M192 130l9 6"/><g class="hint"><path d="M212 132v-26M205 114l7-8 7 8"/></g>`],
    oneleg: ['85 6 150 140', `${CHAIR_R}<circle cx="186" cy="26" r="11"/><path d="M186 39v50v48M186 89l15 20-10 17M186 56l-34-9"/>`],
    reach: ['50 22 150 124', `${CHAIR}<circle cx="130" cy="50" r="11"/><path d="M98 94l22-34M98 94h40l40 28M116 68l46 32"/><g class="hint"><path d="M170 84l10 10-4 4"/></g>`],
    stand: ['40 6 150 140', `${FLOOR}<circle cx="115" cy="26" r="11"/><path d="M115 39v51l-10 48M115 90l10 48M115 54l-24 20M115 54l24 20"/><g class="hint"><path d="M152 44a12 12 0 1 1-6-10"/></g>`],
    march: ['40 6 150 140', `${FLOOR}<circle cx="115" cy="26" r="11"/><path d="M115 39v51l-2 48M115 90l26 6-2 28M115 54l21 13M115 54l-18 19"/><g class="hint"><path d="M162 112V90M155 98l7-8 7 8"/></g>`],
    jack: ['40 4 150 142', `${FLOOR}<circle cx="115" cy="28" r="11"/><path d="M115 41v48l-28 49M115 89l28 49M115 52L84 26M115 52l31-26"/>`],
    squatFree: ['40 12 150 134', `${FLOOR}<circle cx="106" cy="40" r="11"/><path d="M108 53l20 45-32 8 8 32M108 62H76"/><g class="hint"><path d="M164 50v58M156 60l8-10 8 10M156 98l8 10 8-10"/></g>`],
    lunge: ['30 8 160 138', `${FLOOR}<circle cx="110" cy="28" r="11"/><path d="M110 41v47l30 12v38M110 88l-18 28-26 18M110 54l14 22"/>`],
    bridge: ['30 40 170 106', `${FLOOR}<circle cx="50" cy="122" r="10"/><path d="M62 124l50-36 38 4 8 46M70 132h40"/><g class="hint"><path d="M112 74V52M105 60l7-8 7 8"/></g>`],
    plank: ['30 40 180 106', `${FLOOR}<circle cx="48" cy="84" r="10"/><path d="M60 92l130 42M62 94l2 44"/><g class="hint"><path d="M112 62v26M105 70l7-8 7 8M105 80l7 8 7-8"/></g>`],
    floorReach: ['40 40 160 106', `${FLOOR}<circle cx="108" cy="64" r="10"/><path d="M70 124h100M70 124l30-46M96 86l54 24"/>`],
  };

  const fig = (kind, name) => `<figure class="ez-fig"><svg viewBox="${FIG[kind][0]}" role="img" aria-label="${name} 동작 그림">${FIG[kind][1]}</svg></figure>`;

  /* ── 오늘 운동: 앱 데이터(routines_250.json)의 나이대별 첫 루틴. how = 그림을 못 봐도 따라 할 수 있는 글 설명 ── */
  const ROUTINES = {
    '어르신': { title: '넘어지지 않는 몸 만들기', safe: '튼튼한 의자를 벽에 붙여 두세요. 어지러우면 바로 앉아서 쉬어요.', list: [
      { tag: '준비운동', name: '앉아서 목·어깨·손목·발목 돌리기', dose: '1분 동안 천천히', sec: 60, fig: 'sit', how: ['의자에 깊숙이 앉아요.', '목, 어깨, 손목, 발목을 차례로 천천히 돌려요.'], tip: '아프지 않은 만큼만 돌려요.' },
      { tag: '본운동 1', name: '의자에서 앉았다 일어서기', dose: '8번씩 2번', fig: 'squat', how: ['의자 앞에 서요.', '엉덩이를 뒤로 빼며 천천히 앉아요.', '다시 일어서요.'], tip: '무릎이 아프면 반만 앉아요.' },
      { tag: '본운동 2', name: '의자 잡고 뒤꿈치 들기', dose: '8번씩 2번', fig: 'heel', how: ['의자 뒤에 서서 등받이를 잡아요.', '뒤꿈치를 천천히 들어요.', '천천히 내려요.'], tip: '등받이를 꼭 잡아요.' },
      { tag: '본운동 3', name: '의자 잡고 한 발로 서기', dose: '한쪽에 20초씩', sec: 20, fig: 'oneleg', how: ['의자 옆에 서서 등받이를 잡아요.', '한쪽 발을 바닥에서 조금 들어요.', '20초 뒤에 발을 바꿔요.'], tip: '흔들리면 바로 발을 내려요.' },
      { tag: '정리운동', name: '앉아서 앞으로 굽히기 · 종아리 늘이기', dose: '1분 동안 천천히', sec: 60, fig: 'reach', how: ['의자에 앉아 한쪽 다리를 앞으로 펴요.', '허리를 펴고 몸을 천천히 앞으로 숙여요.', '다리를 바꿔요.'], tip: '숨을 참지 않아요. 당기는 느낌까지만 해요.' } ] },
    '성인': { title: '다리 힘 기르기', safe: '주변을 치우고 미끄럽지 않은 곳에서 해요. 아프면 바로 멈춰요.', list: [
      { tag: '준비운동', name: '제자리 걷기와 팔 흔들기', dose: '1분 동안', sec: 60, fig: 'march', how: ['제자리에서 걸어요.', '팔을 앞뒤로 크게 흔들어요.'], tip: '몸이 따뜻해질 때까지 천천히 해요.' },
      { tag: '본운동 1', name: '앉았다 일어서기 (스쿼트)', dose: '10번씩 2번', fig: 'squatFree', how: ['발을 어깨너비로 벌리고 서요.', '엉덩이를 뒤로 빼며 앉아요.', '다시 일어서요.'], tip: '무릎이 아프면 의자에 앉았다 일어서요.' },
      { tag: '본운동 2', name: '한 발 뒤로 내딛기 (런지)', dose: '10번씩 2번', fig: 'lunge', how: ['똑바로 서요.', '한 발을 뒤로 크게 내딛고 두 무릎을 굽혀요.', '돌아와서 발을 바꿔요.'], tip: '무릎이 아프면 조금만 굽혀요. 벽을 잡아도 돼요.' },
      { tag: '본운동 3', name: '누워서 엉덩이 들기 (브릿지)', dose: '10번씩 2번', fig: 'bridge', how: ['등을 대고 누워 무릎을 세워요.', '엉덩이를 천천히 들어요.', '천천히 내려요.'], tip: '허리가 아프면 조금만 들어요.' },
      { tag: '정리운동', name: '앉아서 다리 늘이기', dose: '1분 동안 천천히', sec: 60, fig: 'floorReach', how: ['바닥에 앉아 다리를 앞으로 펴요.', '몸을 천천히 앞으로 숙여요.'], tip: '당기는 느낌까지만 해요.' } ] },
    '청소년': { title: '온몸 힘 기르기', safe: '주변을 치우고 미끄럽지 않은 곳에서 해요. 아프면 바로 멈춰요.', list: [
      { tag: '준비운동', name: '목·어깨·엉덩이·발목 풀기', dose: '1분 동안', sec: 60, fig: 'stand', how: ['똑바로 서요.', '목, 어깨, 엉덩이, 발목을 차례로 천천히 돌려요.'], tip: '아프지 않은 만큼만 돌려요.' },
      { tag: '본운동 1', name: '앉았다 일어서기 (스쿼트)', dose: '10번씩 2번', fig: 'squatFree', how: ['발을 어깨너비로 벌리고 서요.', '엉덩이를 뒤로 빼며 앉아요.', '다시 일어서요.'], tip: '무릎이 발끝보다 많이 나가지 않게 해요.' },
      { tag: '본운동 2', name: '팔굽혀펴기', dose: '10번씩 2번', fig: 'plank', how: ['엎드려 두 손으로 바닥을 짚어요.', '팔을 굽혀 가슴을 바닥 가까이 내려요.', '팔을 펴서 올라와요.'], tip: '힘들면 무릎을 바닥에 대요.' },
      { tag: '본운동 3', name: '엎드려 버티기 (플랭크)', dose: '20초씩 2번', sec: 20, fig: 'plank', how: ['엎드려 팔꿈치와 발끝으로 몸을 받쳐요.', '머리부터 발까지 곧게 펴고 버텨요.'], tip: '허리가 아프면 바로 멈춰요.' },
      { tag: '정리운동', name: '온몸 늘이기', dose: '1분 동안 천천히', sec: 60, fig: 'floorReach', how: ['바닥에 앉아 다리를 앞으로 펴요.', '몸을 천천히 앞으로 숙여요.'], tip: '당기는 느낌까지만 해요.' } ] },
    '유소년': { title: '기본 운동', safe: '주변을 치우고 미끄럽지 않은 곳에서 해요. 아프면 바로 멈춰요.', list: [
      { tag: '준비운동', name: '목·어깨·손목·발목 돌리기', dose: '1분 동안', sec: 60, fig: 'stand', how: ['똑바로 서요.', '목, 어깨, 손목, 발목을 차례로 천천히 돌려요.'], tip: '아프지 않은 만큼만 돌려요.' },
      { tag: '본운동 1', name: '반만 앉았다 일어서기', dose: '8번씩 2번', fig: 'squatFree', how: ['발을 어깨너비로 벌리고 서요.', '엉덩이를 뒤로 빼며 반만 앉아요.', '다시 일어서요.'], tip: '무릎이 아프면 더 조금만 앉아요.' },
      { tag: '본운동 2', name: '무릎 대고 팔굽혀펴기', dose: '8번씩 2번', fig: 'plank', how: ['무릎을 바닥에 대고 두 손으로 바닥을 짚어요.', '팔을 굽혀 가슴을 내려요.', '팔을 펴서 올라와요.'], tip: '어깨가 아프면 멈춰요.' },
      { tag: '본운동 3', name: '팔 벌려 뛰기', dose: '30초 동안', sec: 30, fig: 'jack', how: ['똑바로 서요.', '뛰면서 팔과 다리를 옆으로 벌려요.', '다시 뛰면서 모아요.'], tip: '무릎이 아프면 뛰지 말고 팔만 벌려요.' },
      { tag: '정리운동', name: '온몸 늘이기', dose: '1분 동안 천천히', sec: 60, fig: 'floorReach', how: ['바닥에 앉아 다리를 앞으로 펴요.', '몸을 천천히 앞으로 숙여요.'], tip: '당기는 느낌까지만 해요.' } ] },
  };

  const routine = () => { const g = grp(); return ROUTINES[g === '성장기' ? (P.age <= 12 ? '유소년' : '청소년') : g]; };

  /* ── 화면 조각 ── */
  const SIZES = ['보통', '크게', '더 크게', '아주 크게'];
  const top = back => `<div class="ez-top">${back
      ? `<button type="button" class="ez-tool" data-act="back">${IC.back}<span>뒤로</span></button>`
      : '<span class="ez-brand">Fitage</span>'}
      <span class="sp"></span>
      <button type="button" class="ez-tool" data-act="openSet" aria-label="보기 설정. 글자 크기, 또렷한 색, 자동으로 읽어 주기">${IC.eye}<span>보기 설정</span></button>
      <button type="button" class="ez-tool" data-act="read" aria-label="이 화면 읽어 주기">${IC.spk}<span>읽어 주기</span></button></div>`;
  const flow = () => grp() === '어르신' ? ['m_age', 'm_body', 'm_power', 'm_reach', 'm_walk'] : ['m_age', 'm_body', 'm_power', 'm_reach'];
  const prog = scr => { const f = flow(), n = f.indexOf(scr) + 1; return `<div class="ez-prog"><span>${f.length}가지 가운데 ${n}번째</span><i aria-hidden="true"><b style="width:${n / f.length * 100}%"></b></i></div>`; };
  const stepper = f => { const F = fieldOf(f), v = P[f];
    return `<div class="ez-step"><button type="button" data-act="step" data-f="${f}" data-d="-1" aria-label="${F.label} 하나 줄이기">−</button>
      <button type="button" class="num" data-act="openPad" data-f="${f}" aria-label="${F.label} ${v}${F.unit}. 눌러서 숫자로 직접 넣기">${v}<small>${F.unit}</small></button>
      <button type="button" data-act="step" data-f="${f}" data-d="1" aria-label="${F.label} 하나 늘리기">+</button></div>
      <p class="ez-hint">숫자를 누르면 직접 넣을 수 있어요</p>`; };
  const chips = (f, list) => `<div class="ez-chips" role="group" aria-label="${fieldOf(f).label} 빠른 선택">${list.map(v => `<button type="button" class="ez-chip" data-act="set" data-f="${f}" data-v="${v}" aria-pressed="${P[f] === v}">${v}</button>`).join('')}</div>`;
  const safe = text => `<div class="ez-safe">${IC.warn}<span>${text}</span></div>`;
  const weekCount = () => { const s = stamps(); let n = 0; for (let i = -6; i <= 0; i++) if (s.has(iso(dayShift(i)))) n++; return n; };
  const week = () => { const names = ['일', '월', '화', '수', '목', '금', '토'], s = stamps(); let h = '';
    for (let i = -6; i <= 0; i++) { const d = dayShift(i), done = s.has(iso(d));
      h += `<div class="ez-day${done ? ' done' : ''}${i === 0 ? ' today' : ''}"><span class="st">${done ? '잘' : ''}</span><span>${i === 0 ? '오늘' : names[d.getDay()]}</span></div>`; }
    return `<div class="ez-week" role="img" aria-label="지난 7일 가운데 ${weekCount()}일 운동했어요">${h}</div>`; };
  const dots = n => `<span class="ez-dots" aria-hidden="true">${Array.from({ length: 10 }, (_, i) => `<i${i === n - 1 ? ' class="me"' : ''}></i>`).join('')}</span>`;

  function timerView(o){     // o: { title, padText, secs }
    return `<div class="ez-body"><h2>${o.title}</h2>
      <div class="ez-timer" aria-hidden="true"><span id="tLeft">${o.secs}</span><small>초 남았어요</small></div>
      <div class="ez-bar" aria-hidden="true"><b id="tBar"></b></div>
      <button type="button" class="ez-pad" data-act="tap" id="tapPad" aria-label="${o.padText}. 누를 때마다 하나씩 세요"><span class="c" id="tCount">0</span><span>${o.padText}</span></button></div>
      <div class="ez-foot"><button type="button" class="ez-btn ghost" data-act="stopRun">그만하고 돌아가기</button></div>`;
  }
  function countView(scr, f, title, next, nextLabel, quick){     // 타이머가 끝난 뒤, 또는 숫자로 바로 넣을 때
    return top(true) + `<div class="ez-body">${prog(scr)}<h2>${title}<br>맞나요?</h2><p class="sub">다르면 −, + 로 고치거나 숫자를 눌러 직접 넣어요.</p>${stepper(f)}${quick ? chips(f, quick) : ''}</div>
      <div class="ez-foot"><button type="button" class="ez-btn" data-act="${next}">${nextLabel}</button><button type="button" class="ez-btn text" data-act="phase" data-v="how">다시 재기</button></div>`;
  }

  const VIEWS = {
    mode(){
      return top(false) + `<div class="ez-body">
        <h2>어떤 화면으로 볼까요?</h2><p class="sub">아래에서 하나를 골라 주세요.</p>
        <button type="button" class="ez-mode main" data-act="pickEasy"><span class="pic">${IC.hand}</span><b>쉬운 모드</b><span class="s">앱 이용이 어려우실 수 있는 분들을 위한 화면과 기능이 있어요.</span></button>
        <button type="button" class="ez-mode" data-act="pickNormal"><span class="pic">${IC.grid}</span><b>일반 모드</b><span class="s">앱 이용을 쉽게 하시는 분들을 위한 화면과 기능들이에요.</span></button>
        <p class="sub">나중에 프로필에서 언제든지 바꿀 수 있어요.</p>
      </div>`;
    },
    home(){
      const a = nowAge(), d = a != null ? Math.round(a) - P.age : 0;
      return top(false) + `<div class="ez-body">
        <h2>안녕하세요.<br>오늘도 천천히 해 봐요.</h2>
        ${a != null ? `<div class="ez-age"><div class="k">${ageTitle()}</div><div class="n">${Math.round(a)}<small>세</small></div><p>${diffText(d)}</p></div>`
                    : '<div class="ez-age"><div class="k">내 체력나이</div><p>아직 재지 않았어요. 3분이면 돼요.</p></div>'}
        <button type="button" class="ez-tile" data-act="go" data-to="m_age"><span class="pic">${IC.watch}</span><span><b>체력 재기</b><span class="s">3분이면 돼요</span></span><span class="go">${IC.go}</span></button>
        <button type="button" class="ez-tile" data-act="go" data-to="ex_intro"><span class="pic">${IC.move}</span><span><b>오늘 운동</b><span class="s">다섯 가지 · 10분쯤</span></span><span class="go">${IC.go}</span></button>
        <button type="button" class="ez-tile" data-act="go" data-to="records"><span class="pic">${IC.cal}</span><span><b>내 기록</b><span class="s">지난 7일에 ${weekCount()}번 했어요</span></span><span class="go">${IC.go}</span></button>
        <button type="button" class="ez-btn text" data-act="go" data-to="mode">일반 모드로 바꾸기</button>
        <button type="button" class="ez-btn text" data-act="logout">${state.account ? '로그아웃' : '나가기'}</button>
      </div>`;
    },
    m_age(){
      return top(true) + `<div class="ez-body">${prog('m_age')}<h2>나이를 알려 주세요</h2>
        ${stepper('age')}${chips('age', [15, 25, 35, 45, 55, 65, 75, 85])}
        <p class="ez-label" id="sexLabel">성별</p>
        <div class="ez-two" role="group" aria-labelledby="sexLabel"><button type="button" data-act="sex" data-v="F" aria-pressed="${P.sex === 'F'}">여성</button><button type="button" data-act="sex" data-v="M" aria-pressed="${P.sex === 'M'}">남성</button></div>
      </div><div class="ez-foot"><button type="button" class="ez-btn" data-act="toBody">다음</button></div>`;
    },
    m_body(){
      if (P.height == null) { P.height = P.sex === 'F' ? 158 : 170; P.weight = P.sex === 'F' ? 56 : 68; }
      return top(true) + `<div class="ez-body">${prog('m_body')}<h2>키와 몸무게를 알려 주세요</h2>
        <p class="ez-label">키</p>${stepper('height')}
        <p class="ez-label">몸무게</p>${stepper('weight')}
      </div><div class="ez-foot"><button type="button" class="ez-btn" data-act="go" data-to="m_power">다음</button>
        <button type="button" class="ez-btn text" data-act="skip" data-f="body" data-to="m_power">잘 모르겠어요, 건너뛰기</button></div>`;
    },
    m_power(){
      const t = POWER[grp()];
      if (P.power == null) P.power = t.def;
      if (phase === 'run') return top(true) + timerView({ title: t.runTitle, padText: t.padText, secs: t.secs });
      if (phase === 'confirm') return countView('m_power', 'power', t.secs ? t.confirm(P.power) : `${P.power}cm 뛰었어요.`, 'toReach', '맞아요, 다음');
      return top(true) + `<div class="ez-body">${prog('m_power')}<h2>${t.title}</h2><p class="sub">${t.why}</p>
        <ol class="ez-how">${t.how.map(x => `<li>${x}</li>`).join('')}</ol>${safe(t.safe)}
      </div><div class="ez-foot">${t.secs ? `<button type="button" class="ez-btn" data-act="run" data-f="power" data-s="${t.secs}">${t.secs === 60 ? '1분' : '30초'} 시작하기</button>
        <button type="button" class="ez-btn text" data-act="phase" data-v="confirm">이미 쟀어요, 숫자로 넣기</button>` : '<button type="button" class="ez-btn" data-act="phase" data-v="confirm">뛴 거리 넣기</button>'}</div>`;
    },
    m_reach(){
      if (P.reach == null) P.reach = 5;
      return top(true) + `<div class="ez-body">${prog('m_reach')}<h2>앉아서 앞으로 굽히기</h2>
        <p class="sub">바닥에 다리를 펴고 앉아요. 두 손끝을 앞으로 쭉 뻗어요. 발끝이 0이에요. 발끝을 넘으면 +, 못 미치면 − 예요.</p>
        ${stepper('reach')}<p class="ez-label" style="text-align:center">${reachText(P.reach)}</p>
        ${safe('반동을 주지 말고 천천히 해요. 허리가 아프면 하지 않아도 돼요.')}
      </div><div class="ez-foot"><button type="button" class="ez-btn" data-act="afterReach">${grp() === '어르신' ? '다음' : '결과 보기'}</button>
        <button type="button" class="ez-btn text" data-act="skip" data-f="reach" data-to="after">자가 없어요, 건너뛰기</button></div>`;
    },
    m_walk(){
      if (phase === 'run') return top(true) + timerView({ title: '오른 무릎이 올라올 때마다 눌러요', padText: '세어 주는 분이 여기를 눌러요', secs: 120 });
      if (phase === 'confirm') { if (P.steps == null) P.steps = 100; return countView('m_walk', 'steps', `${P.steps}번 걸으셨어요.`, 'calc', '결과 보기', [80, 90, 100, 110, 120]); }
      return top(true) + `<div class="ez-body">${prog('m_walk')}<h2>2분 제자리 걷기</h2>
        <p class="sub">하지 않아도 결과는 나와요. 세어 줄 분이 있을 때 해 보세요.</p>
        <ol class="ez-how"><li>벽이나 의자 옆에 서요.</li><li>무릎을 허벅지 가운데 높이까지 올리며 제자리에서 걸어요.</li><li>2분 동안 오른 무릎이 올라온 횟수를 세요.</li></ol>
        ${safe('숨이 많이 차면 천천히 걷거나 쉬었다 해요.')}
      </div><div class="ez-foot"><button type="button" class="ez-btn" data-act="run" data-f="steps" data-s="120">2분 시작하기</button>
        <button type="button" class="ez-btn ghost" data-act="skip" data-f="steps" data-to="result">건너뛰고 결과 보기</button>
        <button type="button" class="ez-btn text" data-act="phase" data-v="confirm">이미 쟀어요, 숫자로 넣기</button></div>`;
    },
    wait(){
      return top(false) + '<div class="ez-body"><h2>결과를 보고 있어요</h2><p class="ez-wait">조금만 기다려 주세요…</p></div>';
    },
    result(){
      const a = nowAge();
      if (a == null) return top(true) + '<div class="ez-body"><h2>아직 잰 기록이 없어요</h2><p class="sub">한 가지만 재도 결과가 나와요.</p></div><div class="ez-foot"><button type="button" class="ez-btn" data-act="go" data-to="m_age">체력 재러 가기</button></div>';
      const d = Math.round(a) - P.age, rs = rows(), b = bmiRow();
      const weak = rs.length ? rs.reduce((x, c) => c.pct < x.pct ? c : x) : null;
      return top(true) + `<div class="ez-body">
        <h2 class="sr">결과</h2>
        <div class="ez-age big"><div class="k">${ageTitle()}</div><div class="n">${Math.round(a)}<small>세</small></div><p><b>${diffText(d)}</b></p></div>
        <div class="ez-rows">${rs.map(r => { const st = stateOf(r.pct), n = rank10(r.pct); return `<div class="ez-row"><b>${nameOf(r.k)}</b><span class="ez-state ${st[0]}"><i></i>${st[1]}</span><span class="d">${r.rec}. 또래 10명 중 ${n}번째예요.</span>${dots(n)}</div>`; }).join('')}
          ${b ? `<div class="ez-row"><b>${NAMES['체성분']}</b><span class="ez-state ${b.st[0]}"><i></i>${b.st[1]}</span><span class="d">${b.rec}</span></div>` : ''}</div>
        ${weak ? `<p class="sub">먼저 챙길 것은 <b>${nameOf(weak.k)}</b>예요. 오늘 운동에 들어 있어요.</p>` : ''}
      </div><div class="ez-foot"><button type="button" class="ez-btn" data-act="go" data-to="ex_intro">오늘 운동 하러 가기</button>
        <button type="button" class="ez-btn ghost" data-act="share">결과 보내기</button></div>`;
    },
    ex_intro(){
      const r = routine();
      return top(true) + `<div class="ez-body"><h2>오늘 운동</h2><p class="sub">${r.title} · 다섯 가지 · 10분쯤</p>
        <ol class="ez-how">${r.list.map(e => `<li>${e.name}</li>`).join('')}</ol>${safe(r.safe)}
      </div><div class="ez-foot"><button type="button" class="ez-btn" data-act="exStart">시작하기</button></div>`;
    },
    ex_step(){
      const list = routine().list, e = list[ex], last = ex === list.length - 1;
      return top(true) + `<div class="ez-body"><div class="ez-prog"><span>${list.length}가지 가운데 ${ex + 1}번째</span><i aria-hidden="true"><b style="width:${(ex + 1) / list.length * 100}%"></b></i></div>
        <span class="ez-tag">${e.tag}</span><h2>${e.name}</h2>${fig(e.fig, e.name)}
        <p class="ez-dose" id="exDose">${e.dose}</p>
        <ol class="ez-how">${e.how.map(x => `<li>${x}</li>`).join('')}</ol>${safe(e.tip)}
      </div><div class="ez-foot"><button type="button" class="ez-btn" data-act="exNext">${last ? '했어요, 끝내기' : '했어요, 다음'}</button>
        ${e.sec ? `<button type="button" class="ez-btn ghost" data-act="exTimer" id="exTimerBtn">${e.sec}초 재 주세요</button>` : ''}</div>`;
    },
    ex_done(){
      return top(false) + `<div class="ez-body"><div class="ez-stamp" aria-hidden="true">참<br>잘했어요</div><h2 style="text-align:center">오늘 운동 끝!</h2>
        <p class="sub" style="text-align:center">오늘 도장을 찍었어요. 지난 7일에 ${weekCount()}번 했어요.</p>${week()}
      </div><div class="ez-foot"><button type="button" class="ez-btn" data-act="go" data-to="home">처음으로</button></div>`;
    },
    records(){
      const a = nowAge(), first = state.first?.결과?.체력나이 ?? null;
      const next = state.programStart ? new Date(nextCheckDate() + 'T00:00:00') : null;      // 일반 모드의 '다음 점검일' 과 같은 날(시작일 + 12주)
      const left = next ? daysToNextCheck() : null;
      return top(true) + `<div class="ez-body"><h2>내 기록</h2><p class="ez-label">지난 7일</p>${week()}
        <p class="sub">지난 7일에 <b>${weekCount()}번</b> 운동했어요.</p>
        ${a != null && first != null ? `<div class="ez-card"><span class="k">${ageTitle()}</span><span class="v">처음 ${Math.round(first)}세 → 지금 ${Math.round(a)}세</span></div>` : ''}
        ${next ? `<div class="ez-card"><span class="k">다음에 다시 재는 날</span><span class="v">${fmtDay(next)}</span><span class="sub">${left > 0 ? `${left}일 남았어요. 같은 방법으로 다시 재요.` : '다시 잴 때가 됐어요.'}</span></div>` : ''}
      </div><div class="ez-foot"><button type="button" class="ez-btn" data-act="go" data-to="home">처음으로</button></div>`;
    },
  };

  const SAY = {
    mode: () => '어떤 화면으로 볼까요? 두 가지 가운데 하나를 골라 주세요. 첫째, 쉬운 모드. 앱 이용이 어려우실 수 있는 분들을 위한 화면과 기능이 있어요. 둘째, 일반 모드. 앱 이용을 쉽게 하시는 분들을 위한 화면과 기능들이에요. 나중에 프로필에서 언제든지 바꿀 수 있어요.',
    home: () => `안녕하세요. ${nowAge() != null ? `${ageTitle()}는 ${Math.round(nowAge())}세예요. ` : ''}체력 재기, 오늘 운동, 내 기록 가운데 하나를 눌러 주세요.`,
    m_age: () => `나이를 알려 주세요. 지금 ${P.age}세로 되어 있어요. 빼기와 더하기 단추로 맞추거나, 숫자를 눌러 직접 넣어요. 성별을 고른 다음, 다음을 눌러 주세요.`,
    m_body: () => `키와 몸무게를 알려 주세요. 지금 키 ${P.height}센티미터, 몸무게 ${P.weight}킬로그램으로 되어 있어요. 잘 모르면 건너뛰기를 눌러도 돼요.`,
    m_power: () => { const t = POWER[grp()]; return phase === 'confirm' ? `${P.power}${t.unit === '번' ? '번' : '센티미터'}으로 되어 있어요. 맞으면 다음을 눌러 주세요.` : `${t.title}예요. ${t.why} ${t.how.join(' ')} ${t.safe}`; },
    m_reach: () => `앉아서 앞으로 굽히기예요. 다리를 펴고 앉아 손끝을 앞으로 뻗어요. 지금은 ${reachText(P.reach ?? 0)}로 되어 있어요.`,
    m_walk: () => '이 분 제자리 걷기예요. 하지 않아도 결과는 나와요. 세어 줄 분이 있을 때 해 보세요.',
    wait: () => '결과를 보고 있어요. 조금만 기다려 주세요.',
    result: () => nowAge() != null ? `${ageTitle()}는 ${Math.round(nowAge())}세예요. ${diffText(Math.round(nowAge()) - P.age)} ${rows().map(r => `${nameOf(r.k)}. ${stateOf(r.pct)[1]}. 또래 열 명 중 ${rank10(r.pct)}번째예요.`).join(' ')}` : '아직 잰 기록이 없어요.',
    ex_intro: () => { const r = routine(); return `오늘 운동은 ${r.title}. 다섯 가지, 십 분쯤이에요. ${r.safe} 시작하기를 눌러 주세요.`; },
    ex_step: () => { const e = routine().list[ex]; return `${e.name}. ${e.dose}. ${e.how.join(' ')} ${e.tip}`; },
    ex_done: () => '오늘 운동 끝! 참 잘했어요. 도장을 찍었어요.',
    records: () => `지난 칠 일에 ${weekCount()}번 운동했어요.`,
  };

  /* ── 시트: 보기 설정 · 숫자판 · 결과 보내기 ── */
  const onoff = (act, on, a, b) => `<div class="ez-two" role="group"><button type="button" data-act="${act}" data-v="0" aria-pressed="${!on}">${a}</button><button type="button" data-act="${act}" data-v="1" aria-pressed="${on}">${b}</button></div>`;
  function shareText(){
    const rs = rows().map(r => `${nameOf(r.k)} ${stateOf(r.pct)[1]}`).join(', ');
    return `Fitage 로 체력을 재 봤어요. ${ageTitle().replace('내 ', '')} ${Math.round(nowAge())}세 (실제 ${P.age}세). ${rs}${rs ? '. ' : ''}지난 7일에 운동은 ${weekCount()}번 했어요.`;
  }
  function sheetView(){
    if (sheet === 'set') return `<div class="ez-sheet"><div class="ez-sheet-card" role="dialog" aria-modal="true" aria-label="보기 설정"><h2 tabindex="-1">보기 설정</h2>
      <div class="ez-set"><p class="ez-label" id="setSize">글자 크기</p><div class="ez-chips" role="group" aria-labelledby="setSize">${SIZES.map((s, i) => `<button type="button" class="ez-chip" data-act="setSize" data-v="${i}" aria-pressed="${V.size === i}">${s}</button>`).join('')}</div></div>
      <div class="ez-set"><p class="ez-label">색</p>${onoff('setHc', V.hc, '기본 색', '또렷한 색')}<p class="sub">또렷한 색은 검정 바탕에 흰 글자, 노란 버튼이에요.</p></div>
      <div class="ez-set"><p class="ez-label">화면이 바뀌면 읽어 주기</p>${onoff('setAuto', V.auto, '끄기', '켜기')}<p class="sub">화면낭독기(톡백·보이스오버)를 쓰시면 꺼 두세요. 두 번 읽지 않게요.</p></div>
      <button type="button" class="ez-btn" data-act="closeSheet">다 됐어요</button></div></div>`;
    if (sheet === 'pad') { const F = fieldOf(pad.f);
      return `<div class="ez-sheet"><div class="ez-sheet-card" role="dialog" aria-modal="true" aria-label="${F.label} 직접 넣기"><h2 tabindex="-1">${F.obj} 숫자로 눌러 주세요</h2>
        <div class="ez-padout" id="padOut">${pad.text === '' ? '&nbsp;' : pad.text}<small>${F.unit}</small></div>
        <p class="sub" id="padHint">${pad.err || `${F.min}부터 ${F.max}까지 넣을 수 있어요.`}</p>
        <div class="ez-keys">${[1, 2, 3, 4, 5, 6, 7, 8, 9].map(n => `<button type="button" data-act="padKey" data-v="${n}">${n}</button>`).join('')}
          ${F.neg ? '<button type="button" class="fn" data-act="padKey" data-v="sign" aria-label="더하기 빼기 바꾸기">+ / −</button>' : '<button type="button" class="fn" data-act="padKey" data-v="clear">모두 지우기</button>'}
          <button type="button" data-act="padKey" data-v="0">0</button><button type="button" class="fn" data-act="padKey" data-v="del">지우기</button></div>
        <button type="button" class="ez-btn" data-act="padOk">확인</button><button type="button" class="ez-btn ghost" data-act="closeSheet">취소</button></div></div>`; }
    if (sheet === 'share') return `<div class="ez-sheet"><div class="ez-sheet-card" role="dialog" aria-modal="true" aria-label="결과 보내기"><h2 tabindex="-1">결과 보내기</h2>
      <p class="sub">가족이나 도와주시는 분에게 이 글을 보내요.</p><p class="msg" id="shareMsg">${shareText()}</p>
      <button type="button" class="ez-btn" data-act="send">이 글 보내기</button><button type="button" class="ez-btn ghost" data-act="closeSheet">닫기</button></div></div>`;
    return '';
  }

  /* ── 그리기 ── */
  function paint(focusSel){
    const box = root(); if (!box || !opened) return;
    box.innerHTML = `<div class="ez-screen"><div class="ez" data-size="${V.size}" data-hc="${V.hc ? 1 : 0}"${sheet ? ' aria-hidden="true" inert' : ''}>${VIEWS[screen]()}</div>${sheetView()}<div class="sr" id="ezLive" aria-live="polite"></div></div>`;
    if (focusSel) { const el = box.querySelector(focusSel); if (el) { if (el.tagName === 'H2') el.tabIndex = -1; el.focus({ preventScroll: true }); } }
  }
  /* 다시 그려도 누르던 자리에 초점을 되돌린다 — 자판 · 화면낭독기 사용자가 자리를 잃지 않게 */
  const selOf = d => `[data-act="${d.act}"]` + ['f', 'd', 'v', 'to'].filter(k => d[k] != null).map(k => `[data-${k}="${d[k]}"]`).join('');
  function toast(msg){
    const scr = root()?.querySelector('.ez-screen'); if (!scr) return;
    const old = scr.querySelector('.ez-toast'); if (old) old.remove();
    const el = document.createElement('div'); el.className = 'ez-toast'; el.textContent = msg; scr.appendChild(el);
    live(msg); setTimeout(() => el.remove(), 6000);      // 천천히 읽는 분을 위해 6초
  }

  /* ── 타이머 ── */
  function stopTimer(){ if (T) { clearInterval(T.id); T = null; } }
  function startTimer(total, onEnd, onTick){
    stopTimer();
    T = { total, left: total, count: 0, endAt: performance.now() + total * 1000, onEnd, warned: false };
    beep(880, 0.25); buzz(200); say('시작!'); live('시작');
    T.id = setInterval(() => {
      T.left = Math.max(0, (T.endAt - performance.now()) / 1000);      // 틱 횟수가 아니라 끝나는 시각으로 — 화면이 잠깐 멈춰도 어긋나지 않는다
      if (!T.warned && T.total > 15 && T.left <= 10) { T.warned = true; say('10초 남았어요'); live('10초 남았어요'); }
      if (onTick) onTick(T);
      if (T.left <= 0) { const t = T; stopTimer(); beep(440, 0.7); buzz([300, 120, 300]); t.onEnd(t); }
    }, 100);
  }
  const paintRun = t => { const a = document.getElementById('tLeft'), b = document.getElementById('tBar');
    if (a) a.textContent = Math.ceil(t.left); if (b) b.style.transform = `scaleX(${t.left / t.total})`; };

  const BACK = { home: 'mode', m_age: 'home', m_body: 'm_age', m_power: 'm_body', m_reach: 'm_power', m_walk: 'm_reach', result: 'home', ex_intro: 'home', ex_done: 'home', records: 'home' };
  function go(to){ stopTimer(); screen = to; phase = 'how'; sheet = null; pad = null; paint('.ez-body h2'); if (V.auto) say(SAY[to]()); }

  /* 재 놓은 값을 앱의 state 로 옮기고 서버에서 체력나이를 받는다 — 일반 모드의 '결과 보기' 와 같은 길이다 */
  async function calc(){
    if (busy) return;
    if (P.power == null && P.reach == null && P.steps == null) return go('result');       // 아무것도 안 쟀다 — '아직 잰 기록이 없어요'
    busy = true; go('wait');
    try {
      const g = grpOf(P.age);
      state.age = P.age; state.sex = P.sex; state.ageGbn = g;
      state.height = P.height; state.weight = P.weight;
      state.strength = P.power; state.flexibility = P.reach;
      if (g === '어르신') state.endurance = P.steps;
      state.strengthFrom30s = false;                   // 쉬운 모드는 공식 규격(성인 1분 · 어르신 30초)으로만 잰다
      state.calcVer = CALC_VER;
      state.result = await API.fitnessAge(measurement());
      commitResultQuietly();                           // 첫 점검 · 점검 기록 · 저장까지 일반 모드와 같은 길. '어려졌어요' 연출만 띄우지 않는다
      syncInputsFromState(); renderResult();           // 일반 모드로 돌아가도 같은 값이 보이게
      go('result');
      if (!V.auto && nowAge() != null) say(`${ageTitle()}는 ${Math.round(nowAge())}세예요.`);
    } catch (e) {
      go('m_reach'); toast('결과를 받아오지 못했어요. 잠시 뒤에 다시 눌러 주세요.');
    } finally { busy = false; }
  }

  /* 오늘 운동을 끝냈다 — 일반 모드의 '운동한 날' 과 같은 곳(routineLog)에, 같은 모양으로 남긴다. 날짜당 한 줄. */
  function logRoutine(){
    const today = todayIso(), r = routine();
    if (!Array.isArray(state.routineLog)) state.routineLog = [];
    let e = state.routineLog.find(x => x.date === today && !x.시간대);
    if (!e) { e = { date: today, no: null, done: true, 시간대: null, name: r.title, steps: [], 부분: [], 강도: null }; state.routineLog.push(e); }
    if (!(e.부분 || []).includes('daily')) e.부분 = [...(e.부분 || []), 'daily'];
    const 한것 = r.list.map(x => ({ 단계: x.tag.replace(/ \d+$/, ''), 운동명: x.name, 체력요인: null }));
    e.steps = [...(e.steps || []), ...한것.filter(s => !(e.steps || []).some(t => t.단계 === s.단계 && t.운동명 === s.운동명))];
    if (!state.programStart && state.result) state.programStart = today;
    (async () => { try { await refreshActivityAge(); await refreshLogAges({ 전부: true }); } catch (err) {} await saveProfile(); paintGauges(); })();
  }

  const ACT = {
    go: d => go(d.to),
    pickEasy(){ state.uiMode = 'easy'; saveProfile(); loadP(); go('home'); },
    pickNormal(){ state.uiMode = 'normal'; saveProfile(); close();
      const 지금 = document.querySelector('.screen.active')?.id;
      if (state.result && (지금 === 's1' || 지금 === 's0')) { renderResult(); goTo('s3'); } },      // 쉬운 모드에서 이미 쟀으면 첫 점검 화면이 아니라 홈으로
    logout(){ close(); logout(); },
    back(){ if (phase !== 'how' && (screen === 'm_power' || screen === 'm_walk')) { stopTimer(); phase = 'how'; return paint('.ez-body h2'); }
      if (screen === 'ex_step') { stopTimer(); if (ex > 0) { ex--; paint('.ez-body h2'); if (V.auto) say(SAY.ex_step()); return; } return go('ex_intro'); }
      go(BACK[screen] || 'home'); },
    read(){ say(SAY[screen]()); },
    openSet(){ sheet = 'set'; paint('.ez-sheet-card h2'); },
    setSize(d){ V.size = Number(d.v); saveView(); paint(selOf(d)); live(`글자 크기 ${SIZES[V.size]}`); },
    setHc(d){ V.hc = d.v === '1'; saveView(); paint(selOf(d)); live(V.hc ? '또렷한 색을 켰어요' : '기본 색으로 바꿨어요'); },
    setAuto(d){ V.auto = d.v === '1'; saveView(); paint(selOf(d)); if (V.auto) say('이제 화면이 바뀔 때마다 읽어 드릴게요.'); else { hush(); live('자동으로 읽어 주기를 껐어요'); } },
    closeSheet(){ const was = sheet, f = pad && pad.f; sheet = null; pad = null; paint(was === 'pad' ? `[data-act="openPad"][data-f="${f}"]` : was === 'set' ? '[data-act="openSet"]' : '[data-act="share"]'); },
    step(d){ const F = fieldOf(d.f); P[d.f] = Math.max(F.min, Math.min(F.max, (P[d.f] ?? 0) + Number(d.d))); afterValue(d.f); paint(selOf(d)); live(`${F.label} ${P[d.f]}${F.unit}`); },
    set(d){ P[d.f] = Number(d.v); afterValue(d.f); paint(selOf(d)); live(`${fieldOf(d.f).label} ${P[d.f]}${fieldOf(d.f).unit}`); },
    sex(d){ P.sex = d.v; paint(selOf(d)); live(d.v === 'F' ? '여성을 골랐어요' : '남성을 골랐어요'); },
    toBody(){ if (!P.sex) { const m = '여성, 남성 가운데 하나를 눌러 주세요.'; toast(m); if (V.auto) say(m); return; } go('m_body'); },      // 성별이 있어야 또래와 견준다
    openPad(d){ pad = { f: d.f, text: '', err: '' }; sheet = 'pad'; paint('.ez-sheet-card h2'); if (V.auto) say(`${fieldOf(d.f).obj} 숫자로 눌러 주세요.`); },
    padKey(d){ if (!pad) return; const v = d.v;
      if (v === 'del') pad.text = pad.text.slice(0, -1); else if (v === 'clear') pad.text = '';
      else if (v === 'sign') pad.text = pad.text.startsWith('-') ? pad.text.slice(1) : '-' + pad.text;
      else if (pad.text.replace('-', '').length < 3) pad.text += v;
      pad.err = ''; paint(selOf(d)); live(pad.text === '' ? '비었어요' : pad.text.replace('-', '빼기 ')); },
    padOk(){ if (!pad) return; const F = fieldOf(pad.f), n = parseInt(pad.text, 10);
      if (Number.isNaN(n) || n < F.min || n > F.max) { pad.err = Number.isNaN(n) ? '숫자를 먼저 눌러 주세요.' : `${F.min}부터 ${F.max}까지 넣을 수 있어요. 지우고 다시 눌러 주세요.`; paint('[data-act="padOk"]'); live(pad.err); if (V.auto) say(pad.err); return; }
      const f = pad.f; P[f] = n; afterValue(f); sheet = null; pad = null; paint(`[data-act="openPad"][data-f="${f}"]`); live(`${F.label} ${n}${F.unit}로 넣었어요`); },
    skip(d){ if (d.f === 'body') { P.height = null; P.weight = null; } else P[d.f] = null;
      if (d.to === 'result') return calc(); if (d.to === 'after') return ACT.afterReach(); go(d.to); },
    phase(d){ stopTimer(); phase = d.v; paint('.ez-body h2'); if (V.auto) say(SAY[screen]()); },
    toReach(){ go('m_reach'); },
    afterReach(){ if (grp() === '어르신') go('m_walk'); else calc(); },
    run(d){ phase = 'run'; paint('#tapPad');
      startTimer(Number(d.s), t => { P[d.f] = t.count; phase = 'confirm'; paint('.ez-body h2'); const m = `그만! 수고하셨어요. ${t.count}번 하셨어요.`; say(m); live(m); }, paintRun); },
    tap(){ if (!T) return; T.count++; const c = document.getElementById('tCount'); if (c) c.textContent = T.count; beep(660, 0.08); buzz(40); say(String(T.count)); },
    stopRun(){ stopTimer(); phase = 'how'; paint('.ez-body h2'); },
    calc(){ calc(); },
    share(){ sheet = 'share'; paint('.ez-sheet-card h2'); },
    async send(){ const text = shareText();
      try { if (navigator.share) { await navigator.share({ text }); sheet = null; return paint('[data-act="share"]'); } } catch (e) { if (e && e.name === 'AbortError') return; }
      try { await navigator.clipboard.writeText(text); sheet = null; paint('[data-act="share"]'); toast('글을 복사했어요. 문자나 카카오톡에 붙여 넣으세요.'); }
      catch (e) { toast('글을 길게 눌러 복사해 주세요.'); } },
    exStart(){ ex = 0; go('ex_step'); },
    exTimer(){ const e = routine().list[ex], dose = document.getElementById('exDose'), btn = document.getElementById('exTimerBtn'); if (!e.sec || T) return;
      if (btn) btn.disabled = true;
      startTimer(e.sec, () => { if (dose) dose.textContent = '다 됐어요!'; say('그만! 잘했어요.'); live('그만! 잘했어요.'); if (btn) btn.disabled = false; }, t => { if (dose) dose.textContent = `${Math.ceil(t.left)}초 남았어요`; }); },
    exNext(){ stopTimer(); const list = routine().list; if (ex < list.length - 1) { ex++; paint('.ez-body h2'); if (V.auto) say(SAY.ex_step()); return; }
      logRoutine(); go('ex_done'); if (!V.auto) say('오늘 운동 끝! 참 잘했어요.'); },
  };
  /* 나이가 다른 나이대로 넘어가면 힘 재기 항목이 바뀐다 — 앞 나이대의 기록은 버린다 */
  let lastGroup = null;
  function afterValue(f){ if (f === 'age' && grpOf(P.age) !== lastGroup) { lastGroup = grpOf(P.age); P.power = null; P.steps = null; ex = 0; } }

  /* ── 열고 닫기 ── */
  const others = () => [...document.body.children].filter(el => el !== root() && el.tagName !== 'SCRIPT');
  function open(to){
    const box = root(); if (!box || !state.user) return;
    loadP(); opened = true; box.hidden = false;
    others().forEach(el => el.setAttribute('inert', ''));          // 아래에 깔린 일반 화면은 자판 · 화면낭독기에게도 없는 것이 된다
    go(to || 'home');
  }
  function close(){
    const box = root(); if (!box) return;
    stopTimer(); hush(); opened = false; sheet = null; pad = null; box.hidden = true; box.innerHTML = '';
    others().forEach(el => el.removeAttribute('inert'));
  }
  /* 로그인하면(applyProfile 끝): 고른 적이 없으면 두 버튼부터, 쉬운 모드를 골라 둔 사람은 바로 쉬운 모드로 */
  function afterLogin(){
    if (!state.user) return close();
    if (state.uiMode === 'easy') return open('home');
    if (!state.uiMode) return open('mode');
    close();
  }

  document.addEventListener('click', ev => { if (!opened) return; const t = ev.target.closest('#easyRoot [data-act]'); if (t && !t.disabled && ACT[t.dataset.act]) ACT[t.dataset.act]({ ...t.dataset }); });
  document.addEventListener('keydown', ev => {
    if (!opened) return;
    if (sheet === 'pad' && pad) {
      if (/^[0-9]$/.test(ev.key)) { ACT.padKey({ act: 'padKey', v: ev.key }); ev.preventDefault(); }
      else if (ev.key === 'Backspace') { ACT.padKey({ act: 'padKey', v: 'del' }); ev.preventDefault(); }
      else if (ev.key === 'Enter' && !ev.target.closest('button')) { ACT.padOk(); ev.preventDefault(); }
    }
    if (ev.key === 'Escape' && sheet) ACT.closeSheet();
  });

  window.EASY = { afterLogin, open, close, isOpen: () => opened };
})();
