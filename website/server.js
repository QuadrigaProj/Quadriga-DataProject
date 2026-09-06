// 체력나이 기반 일상 운동 루틴 및 생활활동 처방 서비스 - 백엔드
//
// 이 서버는 두 가지 모드로 동작합니다.
//  1) 서비스키(DATA_GO_KR_KEY)가 채워져 있으면 국민체력100 동영상/센터 API를
//     실제로 호출해서 응답을 그대로 내려줍니다.
//  2) 키가 없으면(기본값) data/sample-*.json 목업 데이터로 동일한 형태의 응답을 만들어 냅니다.
// 프런트엔드(public/)는 어느 모드인지 신경 쓰지 않고 항상 /api/* 만 호출합니다.
//
// 서비스키는 저장소 루트 관례(README "🔑 공공데이터 API")를 따라 .env 의
// DATA_GO_KR_KEY 로 읽습니다. website/ 전용으로 쓰려면 website/.env 에 같은
// 이름으로 넣어도 됩니다(둘 다 .gitignore 대상이라 커밋되지 않습니다).
// config.json은 엔드포인트 경로처럼 비밀이 아닌 값만 두는 보조 설정입니다.

const path = require('path');
const fs = require('fs');
const express = require('express');

const app = express();
app.use(express.json());

// ---------------------------------------------------------------------------
// 설정 로드
// ---------------------------------------------------------------------------
// 팀 컨벤션(.env)을 따르되, dotenv 의존성을 새로 추가하지 않도록 아주 단순한
// KEY=VALUE 파서만 둔다. 이미 설정된 process.env 값은 덮어쓰지 않는다.
function loadDotEnv(file) {
  if (!fs.existsSync(file)) return;
  for (const line of fs.readFileSync(file, 'utf-8').split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eq = trimmed.indexOf('=');
    if (eq === -1) continue;
    const key = trimmed.slice(0, eq).trim();
    let value = trimmed.slice(eq + 1).trim();
    if (/^".*"$/.test(value) || /^'.*'$/.test(value)) value = value.slice(1, -1);
    if (!(key in process.env)) process.env[key] = value;
  }
}
loadDotEnv(path.join(__dirname, '..', '.env')); // 저장소 루트 .env (팀 공용)
loadDotEnv(path.join(__dirname, '.env')); // website/ 전용 .env (있다면 우선 적용)

function loadConfig() {
  const configPath = path.join(__dirname, 'config.json');
  const examplePath = path.join(__dirname, 'config.example.json');
  const file = fs.existsSync(configPath) ? configPath : examplePath;
  try {
    const json = JSON.parse(fs.readFileSync(file, 'utf-8'));
    // 서비스키는 .env(DATA_GO_KR_KEY)가 있으면 그 값을 최우선으로 쓴다.
    json.KSPO_SERVICE_KEY = process.env.DATA_GO_KR_KEY || json.KSPO_SERVICE_KEY || '';
    return json;
  } catch (e) {
    console.warn('[config] 설정 파일을 읽지 못했습니다. 기본값(목업 모드)으로 동작합니다.', e.message);
    return { KSPO_SERVICE_KEY: process.env.DATA_GO_KR_KEY || '' };
  }
}
const CONFIG = loadConfig();
const USE_LIVE_API = Boolean(CONFIG.KSPO_SERVICE_KEY && CONFIG.KSPO_SERVICE_KEY.trim());
console.log(`[mode] ${USE_LIVE_API ? '실제 공공데이터 API 호출 모드' : '샘플(목업) 데이터 모드 - .env의 DATA_GO_KR_KEY를 채우면 실제 API 모드로 전환됩니다.'}`);

// ---------------------------------------------------------------------------
// 데이터 로드
// ---------------------------------------------------------------------------
function loadJson(rel) {
  return JSON.parse(fs.readFileSync(path.join(__dirname, 'data', rel), 'utf-8'));
}
const FITNESS_DIST = loadJson('fitness_distribution.json').rows;
const SAMPLE_VIDEOS = loadJson('sample-videos.json');
const SAMPLE_CENTERS = loadJson('sample-centers.json');
const PRESCRIPTIONS = loadJson('prescriptions.json');

// ---------------------------------------------------------------------------
// 체력나이 산출 로직 (기획안 4~7절)
//
// data/fitness_distribution.json(실측 296만여 건 집계, 담당 A 제공)과
// fitness_age.py(같은 데이터로 만든 "참조 구현")를 그대로 JS로 옮긴 것이다.
// 유연성·근력 두 축은 fitness_age.py의 convert_age()를 1:1로 포팅했고,
// BMI 축만 아래 별도 설명대로 다르게 계산한다.
// ---------------------------------------------------------------------------
const FACTOR_LABEL = { flex: '유연성', strength: '근력', bmi: '체성분(BMI)' };
const BMI_IDEAL = 22.0;
// 항목별 방향: true = 값이 클수록 좋음(젊음). fitness_age.py의 HIGHER_IS_BETTER와 동일.
const HIGHER_IS_BETTER = {
  교차윗몸일으키기: true,
  앉아윗몸앞으로굽히기: true,
  의자앉았다일어서기: true,
};

function calcAge(birthYear, refDate = new Date()) {
  return refDate.getFullYear() - Number(birthYear);
}

// "19~24" → 21.5, "80"(build_dist.py가 80세 이상을 홑값으로 적어 둔 열린 구간) → 82.
// fitness_age.py의 band_mid()는 "~"가 없는 문자열을 만나면 hi = lo+4 로 채운 뒤
// 중앙값을 구한다((80+84)/2=82) - 겉보기엔 +2.5일 것 같지만 실제로는 +2다.
function bandMidSimple(band) {
  const str = String(band);
  if (!str.includes('~')) return Number(str) + 2; // 열린 구간: hi=lo+4로 간주한 중앙값
  const [lo, hi] = str.split('~').map(Number);
  return (lo + hi) / 2;
}

function distRows(ageGbn, sex, item) {
  return FITNESS_DIST.filter((r) => r['연령군'] === ageGbn && r['성별'] === sex && r['항목'] === item);
}

// numpy.interp과 동일한 선형보간: x는 오름차순(동률 허용), 범위 밖 값은 양 끝으로 클램프.
// 동률 구간에서는 numpy처럼 "value 이하인 가장 마지막(오른쪽) x"를 기준으로 삼는다 -
// 처음에 "value를 포함하는 첫 구간"으로 짰다가, fitness_age.py와 나란히 돌려보니
// 유연성처럼 p50에 동률이 있는 축에서 다른 값이 나와 numpy 쪽 규칙에 맞춰 고쳤다.
function npInterp(value, xs, ys) {
  const n = xs.length;
  // 진짜 범위 밖(동률이 아닌 경우)만 양 끝으로 클램프한다. value가 xs[0]과 같을 때도
  // 뒤에 동률이 더 있을 수 있어 곧장 반환하면 안 된다 - 아래 스캔이 그 경우까지 처리한다.
  if (value < xs[0]) return ys[0];
  if (value > xs[n - 1]) return ys[n - 1];
  let j = 0;
  for (let i = 0; i < n; i++) {
    if (xs[i] <= value) j = i;
    else break;
  }
  if (j === n - 1 || xs[j] === value) return ys[j];
  const t = (value - xs[j]) / (xs[j + 1] - xs[j]);
  return ys[j] + t * (ys[j + 1] - ys[j]);
}

// fitness_age.py의 convert_age() 포팅: 측정값 → 환산 나이 (해당 성별·연령군 p50 곡선에 선형보간)
function convertAge(ageGbn, sex, item, value) {
  const sub = distRows(ageGbn, sex, item)
    .map((r) => ({ ageMid: bandMidSimple(r['연령구간']), p50: r.p50 }))
    .sort((a, b) => a.ageMid - b.ageMid);
  if (sub.length < 2) return null;

  const higherBetter = HIGHER_IS_BETTER[item] !== false;
  let xs = sub.map((s) => s.p50);
  let ys = sub.map((s) => s.ageMid);
  if (higherBetter) {
    // 값이 클수록 좋으면 나이가 들수록 p50이 감소 → 보간을 위해 뒤집어 오름차순으로
    xs = xs.slice().reverse();
    ys = ys.slice().reverse();
  }
  const monotonic = xs.every((x, i) => i === 0 || x > xs[i - 1]);
  if (!monotonic) {
    // 실측 데이터의 노이즈로 단조성이 깨지면 x 기준으로 재정렬 (참조 구현과 동일한 안전장치)
    const paired = xs.map((x, i) => [x, ys[i]]).sort((a, b) => a[0] - b[0]);
    xs = paired.map((p) => p[0]);
    ys = paired.map((p) => p[1]);
  }
  return npInterp(value, xs, ys);
}
// 참고: fitness_age.py와 나란히 돌려 대조해보면 유연성·근력 축은 항상 일치하고,
// 아주 가끔 소수점 첫째 자리가 ±0.1 차이 날 수 있다 - 로직 차이가 아니라 정확히
// .5에 걸리는 값에서 파이썬 round()(가장 가까운 짝수로 반올림)와 JS Math.round()
// (항상 올림)의 반올림 방식이 다르기 때문이다.

// 자가 측정 보정 - 윈저화 (기획안 17절 "보정 보충 레이어")
// 실측 분포의 p0.5~p99.5는 이미 build_dist.py 집계 단계에서 한 번 윈저화됐다(항목별
// 상하위 0.5%). 여기서는 그보다 한 단계 더 자가측정 오입력을 거르기 위해, 실측
// 데이터에 나타나는 성인·어르신 전 구간의 p5~p95 범위로 한 번 더 클리핑한다.
function computeWinsorBounds() {
  function rangeOf(item) {
    const rows = FITNESS_DIST.filter((r) => (r['연령군'] === '성인' || r['연령군'] === '어르신') && r['항목'] === item);
    const p5s = rows.map((r) => r.p5);
    const p95s = rows.map((r) => r.p95);
    return [Math.min(...p5s), Math.max(...p95s)];
  }
  return {
    flexCm: rangeOf('앉아윗몸앞으로굽히기'),
    bmi: rangeOf('BMI'),
    situp: rangeOf('교차윗몸일으키기'),
    chairstand: rangeOf('의자앉았다일어서기'),
  };
}
const WINSOR_BOUNDS = computeWinsorBounds();
function winsorize(value, [lo, hi]) {
  return Math.max(lo, Math.min(hi, value));
}

// BMI는 U자형이라 원값을 그대로 연령대 중앙값과 대조하면 역산이 꼬인다
// (참조 구현 fitness_age.py도 "|BMI-22| 편차 곡선"을 연령대와 대조하는 방식을 쓴다).
//
// 그런데 실측 데이터로 그 방식을 그대로 옮겨 검증해보니, 여성의 경우 편차가 가장
// 작아지는 구간이 35~39세(편차 0.1)에 몰려 있어서, BMI가 22에 가까운 건강한 22세
// 여성이 "BMI 환산나이 37세"로 나오는 등 나이와 무관하게 특정 연령대로 쏠리는
// 문제가 그대로 재현됐다(합성 데이터로 처음 발견했던 문제와 같은 종류).
//
// 그래서 BMI 축만 연령대 곡선 전체를 대조하는 대신, "내 나이대의 실제 평균적인
// 편차"와 내 편차를 비교하는 방식으로 바꿨다: 또래보다 이상 체중에 가까우면 그만큼
// 젊게, 또래보다 멀면 그만큼 나이 들게 계산한다. 편차가 또래 평균과 같으면
// 환산나이 = 실제나이(중립)다. 3-2절 "체력나이는 항상 동일 기준으로 산출" 원칙과
// 맞고, 다른 연령대와의 착시 없이 산술적으로만 움직여 심사 질문에도 그대로
// 답할 수 있다.
const BMI_AGE_SENSITIVITY = 2.0; // 또래 대비 편차 1(kg/m²)당 더하는 나이(년) - 시연용 상수
function peerBmiDeviation(ageGbn, sex, actualAge) {
  const sub = distRows(ageGbn, sex, 'BMI').map((r) => ({ ageMid: bandMidSimple(r['연령구간']), p50: r.p50 }));
  if (sub.length === 0) return 0;
  const nearest = sub.reduce((best, s) => (Math.abs(s.ageMid - actualAge) < Math.abs(best.ageMid - actualAge) ? s : best));
  return Math.abs(nearest.p50 - BMI_IDEAL);
}
function bmiEquivalentAge(ageGbn, sex, actualAge, bmi) {
  const userDeviation = Math.abs(bmi - BMI_IDEAL);
  const peerDeviation = peerBmiDeviation(ageGbn, sex, actualAge);
  const age = actualAge + (userDeviation - peerDeviation) * BMI_AGE_SENSITIVITY;
  return Math.max(5, Math.min(100, Math.round(age * 10) / 10));
}

function starsFromDelta(actualAge, equivalentAge) {
  const delta = actualAge - equivalentAge; // 양수 = 또래보다 젊게 나옴 (좋음)
  return Math.max(1, Math.min(5, Math.round(3 + delta / 8)));
}

function weightedBodyAge(ages) {
  // 3항목 균등 가중평균 (기획안 3-2절: 체력나이는 항상 동일 기준으로 산출, fitness_age.py도 단순평균)
  const sum = ages.flex + ages.strength + ages.bmi;
  return Math.round((sum / 3) * 10) / 10;
}

function computeBodyAge(input) {
  const { sex, birthYear, heightCm, weightKg, testType, previousBodyAge } = input;
  const actualAge = calcAge(birthYear);
  const isChairstand = testType === 'chairstand';
  const ageGbn = isChairstand ? '어르신' : '성인';
  const strengthItem = isChairstand ? '의자앉았다일어서기' : '교차윗몸일으키기';

  // 보정 ① 윈저화 - 실측 분포의 p5~p95 범위로 클리핑 후 계산
  const flexCm = winsorize(Number(input.flexCm), WINSOR_BOUNDS.flexCm);
  const strengthReps = winsorize(Number(input.strengthReps), WINSOR_BOUNDS[isChairstand ? 'chairstand' : 'situp']);
  const rawBmi = weightKg / Math.pow(heightCm / 100, 2);
  const bmi = Math.round(winsorize(rawBmi, WINSOR_BOUNDS.bmi) * 10) / 10;

  const equivAges = {
    flex: Math.round(convertAge(ageGbn, sex, '앉아윗몸앞으로굽히기', flexCm) * 10) / 10,
    strength: Math.round(convertAge(ageGbn, sex, strengthItem, strengthReps) * 10) / 10,
    bmi: bmiEquivalentAge(ageGbn, sex, actualAge, bmi),
  };

  const stars = {
    flex: starsFromDelta(actualAge, equivAges.flex),
    strength: starsFromDelta(actualAge, equivAges.strength),
    bmi: starsFromDelta(actualAge, equivAges.bmi),
  };

  let bodyAge = weightedBodyAge(equivAges);
  let capped = false;
  // 보정 ② 점검당 변동 제한 - 재점검 시 직전 체력나이 대비 ±5세를 넘지 않도록 완충
  if (previousBodyAge != null && !Number.isNaN(Number(previousBodyAge))) {
    const prev = Number(previousBodyAge);
    const cappedAge = Math.max(prev - 5, Math.min(prev + 5, bodyAge));
    if (cappedAge !== bodyAge) capped = true;
    bodyAge = Math.round(cappedAge * 10) / 10;
  }

  // 약점 우선순위 지목 (기획안 5-2절 + 참조 구현 fitness_age.py의 weakest_link() 포팅).
  // 참고: 기획안 원문은 "또래 평균(실제나이)까지 올리면"이라 적혀 있지만, 팀이 실제로
  // 만든 참조 구현은 "이미 가진 항목 중 가장 좋은 값(자기 자신의 최고 기록)까지
  // 올리면"으로 계산한다(target = 세 항목 중 최솟값). 판단 기준을 실제 코드에 맞춰
  // 이쪽을 그대로 따랐다 - 자기 자신의 실측 최고치와 비교하는 쪽이 인구 평균 곡선의
  // 잡음에 덜 흔들리고, "당신은 이미 이만큼 할 수 있다"는 근거로도 더 명확하다.
  const keys = ['flex', 'strength', 'bmi'];
  const vals = keys.map((k) => equivAges[k]);
  const best = Math.min(...vals); // 세 항목 중 가장 젊게 나온(가장 좋은) 값
  const whatIf = keys
    .map((key) => {
      const others = keys.filter((k) => k !== key).map((k) => equivAges[k]);
      const newBodyAge = Math.round(((others.reduce((a, b) => a + b, 0) + best) / 3) * 10) / 10;
      return {
        key,
        label: FACTOR_LABEL[key],
        bodyAgeIfFixed: newBodyAge,
        delta: Math.round((bodyAge - newBodyAge) * 10) / 10,
      };
    })
    .sort((a, b) => b.delta - a.delta);

  return {
    actualAge,
    bmi,
    capped,
    testType: testType === 'chairstand' ? '의자에 앉았다 일어서기(30초)' : '교차윗몸일으키기(1분)',
    equivAges,
    stars,
    bodyAge,
    weakest: whatIf[0],
    whatIf,
  };
}

// 목표 체력나이 역산 (기획안 7절): 약점부터 순서대로 또래 평균으로 끌어올리며 목표 도달까지 반복
function computeTargetPlan(input, targetAge) {
  const base = computeBodyAge(input);
  let ages = { ...base.equivAges };
  let bodyAge = base.bodyAge;
  const order = [...base.whatIf].sort((a, b) => b.delta - a.delta).map((w) => w.key);
  const steps = [];

  for (const key of order) {
    if (bodyAge <= targetAge) break;
    ages = { ...ages, [key]: base.actualAge };
    bodyAge = weightedBodyAge(ages);
    steps.push({ key, label: FACTOR_LABEL[key], bodyAgeAfter: bodyAge });
  }

  return {
    startBodyAge: base.bodyAge,
    targetAge,
    reached: bodyAge <= targetAge,
    finalBodyAge: bodyAge,
    steps,
  };
}

// ---------------------------------------------------------------------------
// 일상 처방 (기획안 9절)
// ---------------------------------------------------------------------------
function stairSuggestion(strengthStars) {
  if (strengthStars >= 4) return { level: '상위', text: '3층 이내는 계단으로 올라가 보세요.' };
  if (strengthStars >= 2) return { level: '중간', text: '올라갈 때만 계단을, 내려올 땐 엘리베이터를 이용하세요.' };
  return { level: '하위', text: '계단 대신 한 정거장 먼저 내려서 걷는 것을 추천해요. 무리한 계단 이용은 권하지 않습니다.' };
}

function walkSuggestion(walkMinutes) {
  if (walkMinutes == null || Number.isNaN(walkMinutes)) return null;
  if (walkMinutes <= 20) return { suggest: true, text: `도보 약 ${walkMinutes}분 거리예요. 오늘은 걸어가 보는 건 어떨까요?` };
  return { suggest: false, text: '걷기에는 다소 먼 거리예요. 무리한 이동 제안은 드리지 않아요.' };
}

// ---------------------------------------------------------------------------
// 4주 강도 자동 상승 (기획안 6-4, 15-2절: 세트·반복 횟수 자체 규칙으로 점증)
// ---------------------------------------------------------------------------
function intensityStage(daysSinceStart) {
  const week = Math.floor(daysSinceStart / 7) + 1;
  if (week <= 4) return { week, reps: 10, sets: 2, label: '1~4주차' };
  if (week <= 8) return { week, reps: 12, sets: 3, label: '5~8주차' };
  return { week, reps: 15, sets: 3, label: '9~12주차+' };
}

// ---------------------------------------------------------------------------
// 동영상 / 센터 조회 (실제 API 또는 목업)
// ---------------------------------------------------------------------------
async function fetchVideosLive(params) {
  const url = new URL(CONFIG.VIDEO_API_BASE + '/' + CONFIG.VIDEO_API_OPERATION);
  url.searchParams.set('serviceKey', CONFIG.KSPO_SERVICE_KEY);
  url.searchParams.set('type', 'json');
  Object.entries(params).forEach(([k, v]) => v != null && url.searchParams.set(k, v));
  const res = await fetch(url);
  if (!res.ok) throw new Error(`동영상 API 응답 오류: ${res.status}`);
  return res.json();
}

async function fetchCentersLive() {
  const url = new URL(CONFIG.CENTER_API_BASE + '/' + CONFIG.CENTER_API_OPERATION);
  url.searchParams.set('serviceKey', CONFIG.KSPO_SERVICE_KEY);
  url.searchParams.set('type', 'json');
  const res = await fetch(url);
  if (!res.ok) throw new Error(`센터 API 응답 오류: ${res.status}`);
  return res.json();
}

function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// ---------------------------------------------------------------------------
// API 라우트
// ---------------------------------------------------------------------------
app.get('/api/health', (req, res) => {
  res.json({ ok: true, mode: USE_LIVE_API ? 'live' : 'sample' });
});

app.get('/api/norms', (req, res) => res.json(NORMS));

app.post('/api/bodyage', (req, res) => {
  try {
    const result = computeBodyAge(req.body);
    res.json(result);
  } catch (e) {
    res.status(400).json({ error: e.message });
  }
});

app.post('/api/target', (req, res) => {
  try {
    const { targetAge, ...measurement } = req.body;
    const result = computeTargetPlan(measurement, Number(targetAge));
    res.json(result);
  } catch (e) {
    res.status(400).json({ error: e.message });
  }
});

app.post('/api/daily-prescription', (req, res) => {
  const { strengthStars, walkMinutes } = req.body;
  res.json({
    stairs: stairSuggestion(Number(strengthStars) || 3),
    walk: walkSuggestion(walkMinutes != null ? Number(walkMinutes) : null),
  });
});

app.get('/api/intensity', (req, res) => {
  const days = Number(req.query.daysSinceStart) || 0;
  res.json(intensityStage(days));
});

app.get('/api/prescriptions', (req, res) => {
  const factor = req.query.factor;
  const notes = PRESCRIPTIONS.byFactor[factor] || [];
  res.json({ factor, notes });
});

app.get('/api/videos', async (req, res) => {
  const { factor, place, excludeParts, maxSec, level, aim, se } = req.query;
  try {
    let items;
    if (USE_LIVE_API) {
      const live = await fetchVideosLive({ ftns_fctr_nm: factor, trng_aim_nm: aim });
      items = live.items || live.response?.body?.items || [];
    } else {
      items = SAMPLE_VIDEOS.items;
    }

    const exclude = (excludeParts ? String(excludeParts).split(',') : []).filter(Boolean);
    const filtered = items.filter((v) => {
      if (factor && v.ftns_fctr_nm !== factor) return false;
      if (se && v.trng_se_nm !== se) return false;
      if (place && v.trng_plc_nm && !v.trng_plc_nm.includes(place)) return false;
      if (level && v.lvl_nm !== level) return false;
      if (maxSec && v.playSec > Number(maxSec)) return false;
      if (exclude.length && (v.burdenParts || []).some((p) => exclude.includes(p))) return false;
      return true;
    });

    res.json({ mode: USE_LIVE_API ? 'live' : 'sample', items: filtered });
  } catch (e) {
    console.warn('[videos] 실제 API 호출 실패, 샘플 데이터로 대체합니다:', e.message);
    res.json({ mode: 'sample-fallback', items: SAMPLE_VIDEOS.items });
  }
});

app.get('/api/centers', async (req, res) => {
  const lat = req.query.lat != null ? Number(req.query.lat) : null;
  const lon = req.query.lon != null ? Number(req.query.lon) : null;
  const limit = Number(req.query.limit) || 5;
  try {
    let items;
    if (USE_LIVE_API) {
      const live = await fetchCentersLive();
      items = live.items || live.response?.body?.items || [];
    } else {
      items = SAMPLE_CENTERS.items;
    }

    let out = items;
    if (lat != null && lon != null) {
      out = items
        .map((c) => ({ ...c, distanceKm: Math.round(haversineKm(lat, lon, c.la, c.lo) * 10) / 10 }))
        .sort((a, b) => a.distanceKm - b.distanceKm);
    }
    res.json({ mode: USE_LIVE_API ? 'live' : 'sample', items: out.slice(0, limit) });
  } catch (e) {
    console.warn('[centers] 실제 API 호출 실패, 샘플 데이터로 대체합니다:', e.message);
    res.json({ mode: 'sample-fallback', items: SAMPLE_CENTERS.items.slice(0, limit) });
  }
});

// ---------------------------------------------------------------------------
// 정적 프런트엔드
// ---------------------------------------------------------------------------
app.use(express.static(path.join(__dirname, 'public')));
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`서버 실행 중: http://localhost:${PORT}`);
});
