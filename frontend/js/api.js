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
    workoutItems: () => call('/workout-items'),
    recommendRoutines: (q) => call('/recommend/routines?' + qs(q)),
    activityAge: (b) => post('/fitness-age/activity', b),
    activityAgeDays: (b) => post('/fitness-age/activity/days', b),
    // 이용권 결제 (J2). 카드번호 같은 건 오가지 않는다 — 금액과 주문번호뿐이다.
    // 잔액은 서버 원장이 기준이다. 브라우저 숫자로 올리거나 깎지 않는다.
    credit: () => call('/credit'),
    payMethods: () => call('/pay/methods'),
    payReady: (b) => post('/pay/kakao/ready', b),
    payResult: (order) => call('/pay/result/' + encodeURIComponent(order)),
    sportsSummary: (ids) => call('/sports/summary?' + qs({ ids: (ids || []).join(',') })),
    styleTest: () => call('/style-test'),
    styleTestResult: (answers) => post('/style-test/result', { answers }),

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

    // --- 커뮤니티 ---
    commMeta: () => call('/community/meta'),
    commFeed: (before) => call('/community/posts' + (before ? '?before=' + before : '')),
    commPost: (b) => post('/community/posts', b),
    commPostDetail: (id) => call('/community/posts/' + id),
    commPostDelete: (id) => call('/community/posts/' + id, { method: 'DELETE' }),
    commComment: (id, body) => post('/community/posts/' + id + '/comments', { body }),
    commReact: (target_type, target_id, emoji) =>
      post('/community/reactions', { target_type, target_id, emoji }),
    // 앱 내 아이디와 상호 친구. 다른 사람에게 보이는 건 닉네임과 아이디뿐이다.
    commMyHandle: () => call('/community/me/handle'),
    commFindUser: (handle) => call('/community/users/' + encodeURIComponent(handle)),
    commFriends: () => call('/community/friends'),
    commFriendAdd: (handle) => post('/community/friends', { handle }),
    commFriendRemove: (handle) => call('/community/friends/' + encodeURIComponent(handle),
                                       { method: 'DELETE' }),
    // 개인 채팅은 상대 아이디로만 연다 — 방 만들기로는 못 만든다 (L1)
    commDirect: (handle) => post('/community/direct', { handle }),
    commRooms: () => call('/community/rooms'),
    commRoomNew: (body) => post('/community/rooms', body),
    commRoomJoin: (id, password) => post('/community/rooms/' + id + '/join', { password }),
    // 단체 채팅방 멤버 관리 (L6). 초대·내보내기 모두 아이디로 한다.
    commRoomMembers: (id) => call('/community/rooms/' + id + '/members'),
    commRoomInvite: (id, handle) => post('/community/rooms/' + id + '/invite', { handle }),
    commRoomInviteCancel: (id, handle) =>
      call('/community/rooms/' + id + '/invite/' + encodeURIComponent(handle), { method: 'DELETE' }),
    // 초대는 받은 사람이 수락해야 들어간다. 비공개 방이면 그때 비밀번호를 넣는다.
    commInvites: () => call('/community/invites'),
    commInviteAccept: (id, password) => post('/community/invites/' + id + '/accept', { password }),
    commInviteDecline: (id) => call('/community/invites/' + id, { method: 'DELETE' }),
    commRoomKick: (id, handle) => post('/community/rooms/' + id + '/kick', { handle }),
    commRoomLeave: (id) => post('/community/rooms/' + id + '/leave', {}),
    commRoomPassword: (id, password) => call('/community/rooms/' + id + '/password', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password }),
    }),
    commMessages: (id, after) => call('/community/rooms/' + id + '/messages' + (after ? '?after=' + after : '')),
    commSend: (id, body) => post('/community/rooms/' + id + '/messages', { body }),
  };
})();
