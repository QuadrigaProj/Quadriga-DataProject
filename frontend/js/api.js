/* 백엔드 호출 계층.
 *
 * 화면과 API 는 같은 서버(uvicorn backend.main:app)가 함께 내보내므로
 * 경로만 적으면 된다.
 *
 * 서버 없이 이 파일을 브라우저로 직접 열어도 화면 흐름은 볼 수 있게,
 * 호출이 실패하면 offline 플래그를 세우고 호출한 쪽이 예시값으로 대체한다.
 */
const API = (() => {
  let offline = false;

  function qs(obj) {
    const p = new URLSearchParams();
    Object.entries(obj || {}).forEach(([k, v]) => {
      if (v !== null && v !== undefined && v !== '') p.set(k, v);
    });
    return p.toString();
  }

  async function call(path, opts) {
    const res = await fetch(path, { credentials: 'same-origin', ...(opts || {}) });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || `${res.status} 오류`);
    return body;
  }

  const post = (path, body) => call(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  return {
    get offline() { return offline; },
    set offline(v) { offline = v; },

    async health() {
      try {
        const h = await call('/health');
        offline = !(h['분포_로드됨'] && h['처방_로드됨']);
        return h;
      } catch (e) {
        offline = true;
        return null;
      }
    },

    fitnessAge: (m) => post('/fitness-age', m),
    recheck: (before, after) => post('/recheck', { 이전: before, 현재: after }),
    routine: (q) => call('/routine?' + qs(q)),
    videoRoutine: (q) => call('/video-routine?' + qs(q)),
    programRoutine: (q) => call('/program/routine?' + qs(q)),
    programPurposes: (q) => call('/program/purposes?' + qs(q)),
    purposes: () => call('/purposes'),
    daily: (q) => call('/daily?' + qs(q)),
    routeAdvice: (q) => call('/route/advice?' + qs(q)),   // F2: {from, to, strength_stars}
    videos: (q) => call('/videos?' + qs(q)),
    centers: (q) => call('/centers?' + qs(q)),
    sports: () => call('/sports'),
    sportsSummary: (ids) => call('/sports/summary?' + qs({ ids: (ids || []).join(',') })),

    // --- 계정 ---
    providers: () => call('/auth/providers'),
    me: () => call('/auth/me'),
    signup: (b) => post('/auth/signup', b),
    signin: (b) => post('/auth/login', b),
    signout: () => post('/auth/logout', {}),
    deleteAccount: () => call('/auth/me', { method: 'DELETE' }),
    rename: (이름) => call('/auth/me', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 이름 }),
    }),
    myMeasurements: () => call('/me/measurements'),
    pushMeasurement: (b) => post('/me/measurements', b),
  };
})();
