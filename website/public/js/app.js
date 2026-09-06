// 체력나이 서비스 프런트엔드 - 화면 전환 + 상태관리 + 각 화면 로직
(function () {
  'use strict';

  const STORAGE_KEY = 'bodyage_state_v1';

  const PURPOSES = [
    { key: 'diet', label: '다이어트', emoji: '🔥', aim: '체중 감량', extra: null },
    { key: 'basic', label: '기초 체력 증진', emoji: '⚖️', aim: '기초 체력', extra: null },
    { key: 'sport', label: '특정 운동을 위한 체력 증진', emoji: '⛰️', aim: '특정 운동 준비', extra: '민첩성·순발력' },
    { key: 'fall', label: '낙상 예방', emoji: '🦵', aim: '낙상 예방', extra: '평형성' },
    { key: 'exam', label: '수험생 체력 증진', emoji: '📚', aim: '일상 컨디션', extra: null },
    { key: 'flex', label: '유연성 강화', emoji: '🧘', aim: '일상 컨디션', extra: null },
  ];
  const FACTOR_TO_VIDEO_LABEL = { strength: '근력·근지구력', flex: '유연성', bmi: '심폐지구력' };
  const FACTOR_ORDER = ['flex', 'strength', 'bmi'];
  const FACTOR_LABEL = { flex: '유연성', strength: '근력', bmi: '체성분(BMI)' };

  // ---------------------------------------------------------------- state
  function defaultState() {
    return {
      measurement: null, // {sex, birthYear, heightCm, weightKg, flexCm, strengthReps, testType, date}
      bodyAgeResult: null,
      purpose: null,
      purposeChangeMode: false,
      heavyDay: false,
      excludeParts: [],
      bonusSlots: [],
      familyShare: { enabled: false, name: '' },
      history: [], // {date, bodyAgeResult}
      completedDates: [],
      bonusCompletedDates: [],
      startDate: null,
      unlockedIds: [],
    };
  }
  let state = loadState();
  function loadState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return defaultState();
      return Object.assign(defaultState(), JSON.parse(raw));
    } catch (e) {
      return defaultState();
    }
  }
  function saveState() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }

  // ---------------------------------------------------------------- utils
  function $(sel) { return document.querySelector(sel); }
  function $all(sel) { return Array.from(document.querySelectorAll(sel)); }
  function todayStr() { return new Date().toISOString().slice(0, 10); }
  function daysBetween(a, b) { return Math.round((new Date(b) - new Date(a)) / 86400000); }
  function starString(n) { return '★'.repeat(n) + '☆'.repeat(5 - n); }
  function ageFromBirthYear(y) { return new Date().getFullYear() - Number(y); }

  let toastTimer = null;
  function toast(msg) {
    const el = $('#toast');
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('show'), 2200);
  }

  function showScreen(id) {
    $all('section.screen').forEach((s) => (s.hidden = s.id !== id));
    window.scrollTo(0, 0);
  }

  $('#topbarRight').textContent = new Date().toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'short' });

  // ============================================================ 첫 점검
  let sex = 'M';
  $('#sexSeg').addEventListener('click', (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    sex = btn.dataset.val;
    $all('#sexSeg button').forEach((b) => b.classList.toggle('active', b === btn));
    updateStrengthTestLabel();
  });
  $('#heightCm').addEventListener('input', updateBmiPreview);
  $('#weightKg').addEventListener('input', updateBmiPreview);
  function updateBmiPreview() {
    const h = Number($('#heightCm').value), w = Number($('#weightKg').value);
    if (h > 0 && w > 0) {
      const bmi = (w / Math.pow(h / 100, 2)).toFixed(1);
      $('#bmiPreview').textContent = `자동 계산된 BMI: ${bmi}`;
    } else {
      $('#bmiPreview').textContent = '';
    }
  }
  $('#birthYear').addEventListener('input', updateStrengthTestLabel);
  function isSenior() {
    const y = Number($('#birthYear').value);
    if (!y) return false;
    return ageFromBirthYear(y) >= 65;
  }
  function updateStrengthTestLabel() {
    const senior = isSenior();
    $('#strengthTestLabel').textContent = senior
      ? '만 65세 이상 기준: 의자에 앉았다 일어서기 30초간 반복 횟수'
      : '만 65세 미만 기준: 교차윗몸일으키기 1분간 반복 횟수';
    resetTimer();
  }

  // 타이머
  let timerHandle = null, timerRemaining = 60, repCount = 0;
  function timerTotalSec() { return isSenior() ? 30 : 60; }
  function renderTimer() {
    const m = String(Math.floor(timerRemaining / 60)).padStart(2, '0');
    const s = String(timerRemaining % 60).padStart(2, '0');
    $('#timerDisplay').textContent = `${m}:${s}`;
    $('#repCount').textContent = repCount;
  }
  function resetTimer() {
    clearInterval(timerHandle);
    timerHandle = null;
    timerRemaining = timerTotalSec();
    repCount = 0;
    renderTimer();
  }
  $('#tapBtn').addEventListener('click', () => {
    repCount++;
    renderTimer();
    if (navigator.vibrate) navigator.vibrate(15);
  });
  $('#timerStartBtn').addEventListener('click', () => {
    if (timerHandle) return;
    timerRemaining = timerTotalSec();
    renderTimer();
    timerHandle = setInterval(() => {
      timerRemaining--;
      renderTimer();
      if (timerRemaining <= 0) {
        clearInterval(timerHandle);
        timerHandle = null;
        $('#strengthReps').value = repCount;
        toast('측정 종료! 아래 횟수를 확인해 주세요.');
      }
    }, 1000);
  });
  $('#timerResetBtn').addEventListener('click', resetTimer);
  renderTimer();

  $('#submitMeasureBtn').addEventListener('click', async () => {
    const birthYear = Number($('#birthYear').value);
    const heightCm = Number($('#heightCm').value);
    const weightKg = Number($('#weightKg').value);
    const flexCm = Number($('#flexCm').value);
    const strengthReps = Number($('#strengthReps').value);
    if (!birthYear || !heightCm || !weightKg || $('#flexCm').value === '' || $('#strengthReps').value === '') {
      toast('모든 항목을 입력해 주세요.');
      return;
    }
    const testType = isSenior() ? 'chairstand' : 'situp';
    const measurement = { sex, birthYear, heightCm, weightKg, flexCm, strengthReps, testType, date: todayStr() };

    try {
      const result = await Api.bodyAge(measurement);
      state.measurement = measurement;
      state.bodyAgeResult = result;
      state.startDate = state.startDate || todayStr();
      state.history.push({ date: todayStr(), bodyAgeResult: result });
      saveState();
      renderMeasureResult(result);
      showScreen('screen-measure-result');
    } catch (e) {
      toast('계산 중 오류가 발생했어요: ' + e.message);
    }
  });

  function renderMeasureResult(result) {
    $('#resultAgeActual').textContent = result.actualAge;
    $('#resultAgeNum').textContent = result.bodyAge;
    const delta = Math.round((result.actualAge - result.bodyAge) * 10) / 10;
    $('#resultAgeChip').innerHTML = chipForDelta(delta);
    $('#resultProfileCard').innerHTML = `
      <h3>스포츠 프로필 (참고용 추정치)</h3>
      ${FACTOR_ORDER.map((k) => factorRowHtml(k, result.stars[k])).join('')}
      <p class="disclaimer">자가 측정값은 참고용 추정치입니다. 정확한 값은 가까운 국민체력100 체력인증센터 무료 측정으로 확인하세요. (설정 탭 → 가까운 센터 찾기)</p>
    `;
  }
  function chipForDelta(delta) {
    if (delta > 0) return `<span class="chip good">실제보다 ${delta}세 젊게 나왔어요</span>`;
    if (delta < 0) return `<span class="chip warn">실제보다 ${Math.abs(delta)}세 많게 나왔어요</span>`;
    return `<span class="chip">실제 나이와 같아요</span>`;
  }
  function factorRowHtml(key, stars) {
    return `<div class="factor-row">
      <div class="name">${FACTOR_LABEL[key]}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${(stars / 5) * 100}%"></div></div>
      <div class="stars">${starString(stars)}</div>
    </div>`;
  }

  // ============================================================ 목적 선택
  $('#goPurposeBtn').addEventListener('click', () => {
    state.purposeChangeMode = false;
    renderPurposeGrid();
    showScreen('screen-purpose');
  });
  $('#changePurposeBtn').addEventListener('click', () => {
    state.purposeChangeMode = true;
    renderPurposeGrid();
    showScreen('screen-purpose');
  });

  let selectedPurpose = null;
  function renderPurposeGrid() {
    selectedPurpose = state.purpose;
    $('#purposeGrid').innerHTML = PURPOSES.map(
      (p) => `<div class="choice-card ${p.key === selectedPurpose ? 'selected' : ''}" data-key="${p.key}">
        <span class="emoji">${p.emoji}</span>${p.label}
      </div>`
    ).join('');
    $('#confirmPurposeBtn').disabled = !selectedPurpose;
  }
  $('#purposeGrid').addEventListener('click', (e) => {
    const card = e.target.closest('.choice-card');
    if (!card) return;
    selectedPurpose = card.dataset.key;
    $all('.choice-card').forEach((c) => c.classList.toggle('selected', c === card));
    $('#confirmPurposeBtn').disabled = false;
  });
  $('#confirmPurposeBtn').addEventListener('click', () => {
    state.purpose = selectedPurpose;
    saveState();
    if (!state.purposeChangeMode) {
      $('#tabbar').hidden = false;
      switchTab('home');
    } else {
      switchTab('profile');
    }
  });

  // ============================================================ 탭바
  $('#tabbar').addEventListener('click', (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    switchTab(btn.dataset.tab);
  });
  function switchTab(tab) {
    $all('#tabbar button').forEach((b) => b.classList.toggle('active', b.dataset.tab === tab));
    showScreen('screen-' + tab);
    if (tab === 'home') renderHome();
    if (tab === 'routine') renderRoutineScreen();
    if (tab === 'profile') renderProfile();
    if (tab === 'recheck') renderRecheck();
    if (tab === 'settings') renderSettings();
  }

  // ============================================================ 홈
  $('#startRoutineBtn').addEventListener('click', () => switchTab('routine'));
  $('#heavyDayToggle').addEventListener('change', (e) => {
    state.heavyDay = e.target.checked;
    saveState();
    renderHome();
  });
  $('#walkCheckBtn').addEventListener('click', async () => {
    const minutes = Number($('#walkMinutesInput').value);
    const strengthStars = state.bodyAgeResult.stars.strength;
    const res = await Api.dailyPrescription({ strengthStars, walkMinutes: minutes });
    $('#walkResult').textContent = res.walk ? res.walk.text : '도보 시간을 입력해 주세요.';
  });

  async function renderHome() {
    const r = state.bodyAgeResult;
    const purpose = PURPOSES.find((p) => p.key === state.purpose);
    const daysSinceStart = Math.max(0, daysBetween(state.startDate, todayStr()));
    $('#homeSub').textContent = `목적: ${purpose.label} · 시작한 지 ${daysSinceStart}일째 · 오늘 루틴은 ${FACTOR_LABEL[r.weakest.key]} 중심이에요`;

    const stage = await Api.intensity(daysSinceStart);
    $('#homeRoutineMeta').textContent = state.heavyDay
      ? `몸 무거운 날 모드 · ${Math.max(1, Math.round(stage.reps / 2))}회 × 1세트로 가볍게`
      : `${stage.label} · ${stage.reps}회 × ${stage.sets}세트`;
    $('#heavyDayToggle').checked = state.heavyDay;

    const dday = 90 - daysSinceStart;
    $('#ddayText').textContent = dday <= 0 ? '지금 재점검할 수 있어요' : `D-${dday}`;

    const daily = await Api.dailyPrescription({ strengthStars: r.stars.strength, walkMinutes: null });
    $('#dailyPrescriptionCard').innerHTML = `
      <h3>🏢 오늘의 일상 처방</h3>
      <p>${daily.stairs.text}</p>
      <span class="chip">하지근력 ${daily.stairs.level}</span>
    `;

    if (state.bonusSlots.length > 0) {
      $('#bonusCard').innerHTML = `
        <h3>⏱ 짬 보너스</h3>
        <p class="hint">등록한 시간: ${state.bonusSlots.join(' · ')}</p>
        <button class="btn btn-secondary btn-sm" id="startBonusBtn">지금 짬 보너스 하기 (3~5분)</button>
      `;
      $('#startBonusBtn').addEventListener('click', startBonusRoutine);
    } else {
      $('#bonusCard').innerHTML = `<h3>⏱ 짬 보너스</h3><p class="hint">설정 탭에서 자주 비는 시간을 등록하면 짧은 보너스 루틴을 추천해 드려요.</p>`;
    }

    $('#walkResult').textContent = '';
  }

  async function startBonusRoutine() {
    const res = await Api.videos({});
    const bonusVideos = res.items.filter((v) => v.id.startsWith('b'));
    const v = bonusVideos[Math.floor(Math.random() * bonusVideos.length)];
    if (!v) return toast('보너스 루틴을 찾지 못했어요.');
    toast(`${v.videoNm} 재생 중… (${Math.round(v.playSec / 60 * 10) / 10}분)`);
    setTimeout(() => {
      if (!state.bonusCompletedDates.includes(todayStr())) state.bonusCompletedDates.push(todayStr());
      saveState();
      toast('짬 보너스 완료! (메인 루틴과 별개로 기록돼요)');
    }, 1500);
  }

  // ============================================================ 루틴 플레이어
  let playlist = [];
  let stageIndex = 0;
  let stageTimer = null;
  let stageRemaining = 0;

  $('#partFilterTags').addEventListener('click', (e) => {
    const btn = e.target.closest('.tag-btn');
    if (!btn) return;
    const part = btn.dataset.part;
    const idx = state.excludeParts.indexOf(part);
    if (idx >= 0) state.excludeParts.splice(idx, 1);
    else state.excludeParts.push(part);
    saveState();
    renderRoutineScreen();
  });

  async function renderRoutineScreen() {
    $all('#partFilterTags .tag-btn').forEach((b) => b.classList.toggle('active', state.excludeParts.includes(b.dataset.part)));
    const daysSinceStart = Math.max(0, daysBetween(state.startDate, todayStr()));
    const stage = await Api.intensity(daysSinceStart);
    const reps = state.heavyDay ? Math.max(1, Math.round(stage.reps / 2)) : stage.reps;
    const sets = state.heavyDay ? 1 : stage.sets;
    $('#routineMetaText').textContent = `${stage.label} 기준 ${reps}회 × ${sets}세트${state.heavyDay ? ' (몸 무거운 날 · 절반 강도)' : ''}`;

    playlist = await buildPlaylist();
    stageIndex = 0;
    renderPlaylist(reps, sets);
    renderStage(reps, sets);
  }

  async function buildPlaylist() {
    const weak = state.bodyAgeResult.weakest.key;
    const mainFactor = FACTOR_TO_VIDEO_LABEL[weak];
    const purpose = PURPOSES.find((p) => p.key === state.purpose);
    const excludeParts = state.excludeParts.join(',');

    const warmup = (await Api.videos({ se: '준비운동', factor: '유연성', excludeParts })).items.slice(0, 1);
    let main = (await Api.videos({ se: '본운동', factor: mainFactor, excludeParts })).items.slice(0, 2);
    if (main.length === 0) main = (await Api.videos({ se: '본운동', excludeParts })).items.slice(0, 2);
    let extra = [];
    if (purpose.extra) {
      extra = (await Api.videos({ se: '본운동', factor: purpose.extra, excludeParts })).items.slice(0, 1);
    }
    const cooldown = (await Api.videos({ se: '정리운동', factor: '유연성', excludeParts })).items.slice(0, 1);

    const all = [...warmup, ...main, ...extra, ...cooldown].filter((v) => v.id !== undefined);
    // 중복 제거
    const seen = new Set();
    return all.filter((v) => (seen.has(v.id) ? false : (seen.add(v.id), true)));
  }

  function renderPlaylist(reps, sets) {
    if (playlist.length === 0) {
      $('#playlistList').innerHTML = `<div class="empty-state">조건에 맞는 영상을 찾지 못했어요. 부위 필터를 조정해 보세요.</div>`;
      return;
    }
    $('#playlistList').innerHTML = playlist
      .map((v, i) => {
        const repText = v.trng_se_nm === '본운동' ? `${reps}회 × ${sets}세트` : `${Math.round(v.playSec / 60 * 10) / 10}분`;
        return `<div class="video-card ${i < stageIndex ? 'done' : ''}" data-i="${i}">
          <div class="thumb">${v.thumb || '🎬'}</div>
          <div class="meta">
            <div class="title">${i + 1}. ${v.videoNm}</div>
            <div class="sub">${v.trng_se_nm} · ${v.ftns_fctr_nm} · ${repText}</div>
          </div>
        </div>`;
      })
      .join('');
  }

  function currentReps() {
    return { reps: Number($('#routineMetaText').textContent.match(/(\d+)회/)?.[1] || 10), sets: Number($('#routineMetaText').textContent.match(/×\s*(\d+)세트/)?.[1] || 2) };
  }

  function renderStage(reps, sets) {
    clearInterval(stageTimer);
    stageTimer = null;
    const v = playlist[stageIndex];
    if (!v) {
      $('#stageEmoji').textContent = '🎉';
      $('#stageName').textContent = '오늘의 루틴을 모두 살펴봤어요';
      $('#stageRep').textContent = '';
      $('#stageProgress').style.width = '100%';
      $('#stageCountText').textContent = '';
      return;
    }
    $('#stageEmoji').textContent = v.thumb || '🎬';
    $('#stageName').textContent = v.videoNm;
    $('#stageRep').textContent = v.trng_se_nm === '본운동' ? `${reps}회 × ${sets}세트` : `${v.trng_se_nm}`;
    $('#stageProgress').style.width = '0%';
    stageRemaining = state.heavyDay ? Math.round(v.playSec / 2) : v.playSec;
    $('#stageCountText').textContent = `예상 소요 ${stageRemaining}초`;
    $('#stagePlayBtn').textContent = '시작';
  }

  $('#stagePlayBtn').addEventListener('click', () => {
    const v = playlist[stageIndex];
    if (!v) return;
    if (stageTimer) {
      clearInterval(stageTimer);
      stageTimer = null;
      $('#stagePlayBtn').textContent = '계속';
      return;
    }
    const total = stageRemaining;
    let elapsed = 0;
    $('#stagePlayBtn').textContent = '일시정지';
    stageTimer = setInterval(() => {
      elapsed++;
      stageRemaining--;
      $('#stageProgress').style.width = `${Math.min(100, (elapsed / total) * 100)}%`;
      $('#stageCountText').textContent = `남은 시간 ${Math.max(0, stageRemaining)}초`;
      if (stageRemaining <= 0) {
        clearInterval(stageTimer);
        stageTimer = null;
        toast(`${v.videoNm} 완료!`);
        goStage(stageIndex + 1);
      }
    }, 1000);
  });
  $('#stagePrevBtn').addEventListener('click', () => goStage(stageIndex - 1));
  $('#stageNextBtn').addEventListener('click', () => goStage(stageIndex + 1));
  function goStage(i) {
    stageIndex = Math.max(0, Math.min(playlist.length, i));
    const { reps, sets } = currentReps();
    renderStage(reps, sets);
    renderPlaylist(reps, sets);
  }

  $('#finishRoutineBtn').addEventListener('click', () => {
    if (!state.completedDates.includes(todayStr())) state.completedDates.push(todayStr());
    saveState();
    toast('오늘의 루틴을 완료했어요! 내일 같은 시간에 만나요 🙌');
    switchTab('home');
  });

  // ============================================================ 프로필
  $('#targetCalcBtn').addEventListener('click', async () => {
    const targetAge = Number($('#targetAgeInput').value);
    if (!targetAge) return toast('목표 나이를 입력해 주세요.');
    const plan = await Api.target({ ...state.measurement, targetAge });
    if (plan.steps.length === 0) {
      $('#targetResult').innerHTML = `<p class="chip good">이미 목표를 달성한 상태로 계산돼요.</p>`;
      return;
    }
    $('#targetResult').innerHTML = `
      <div class="hint">현재 ${plan.startBodyAge}세 → 목표 ${plan.targetAge}세</div>
      ${plan.steps.map((s, i) => `<div class="hint">${i + 1}. ${s.label}을(를) 또래 평균 수준까지 올리면 → ${s.bodyAgeAfter}세로 계산돼요</div>`).join('')}
      <p class="${plan.reached ? 'chip good' : 'chip warn'}" style="margin-top:8px">${plan.reached ? '위 조건이면 목표에 도달하는 것으로 계산돼요.' : '세 항목을 모두 또래 평균으로 올려도 목표에는 못 미쳐요. 목표를 조정해 보세요.'}</p>
      <p class="disclaimer">예측이 아니라 계산입니다 — "이렇게 하면 젊어진다"가 아니라 "이 수치가 되면 이렇게 계산된다"까지만 제시해요.</p>
    `;
  });

  function renderProfile() {
    const r = state.bodyAgeResult;
    const purpose = PURPOSES.find((p) => p.key === state.purpose);
    $('#profileBodyAge').textContent = `${r.bodyAge}세`;
    const delta = Math.round((r.actualAge - r.bodyAge) * 10) / 10;
    $('#profileDeltaChip').innerHTML = chipForDelta(delta) + ` <span class="hint">(실제 ${r.actualAge}세)</span>`;
    $('#factorRows').innerHTML = FACTOR_ORDER.map((k) => factorRowHtml(k, r.stars[k])).join('');

    $('#weakPointCard').innerHTML = `
      <h3>💡 약점 우선순위</h3>
      <p>지금 당신의 체력나이를 가장 많이 낮추는 것은 <b>${r.weakest.label}</b>입니다.<br/>
      ${r.weakest.label}만 또래 평균 수준으로 올리면 → <b>${r.bodyAge}세 → ${r.weakest.bodyAgeIfFixed}세</b></p>
      <div id="whatIfChart" style="margin-top:10px"></div>
      <p class="disclaimer">예측이 아니라 도달값입니다. "몇 주 뒤 젊어진다"가 아니라 "이 항목이 또래 평균이 되면 이렇게 계산된다"까지만 제시해요.</p>
    `;
    Charts.renderRankedBars($('#whatIfChart'), { items: r.whatIf.map((w) => ({ label: w.label, value: w.delta })), unit: '세' });

    $('#currentPurposeText').textContent = `${purpose.emoji} ${purpose.label}`;
  }

  // ============================================================ 분기 점검
  $('#autoFillRecheckBtn').addEventListener('click', () => {
    const done = state.completedDates.length;
    const m = state.measurement;
    $('#reFlexCm').value = Math.round((m.flexCm + Math.min(6, done * 0.3)) * 10) / 10;
    $('#reStrengthReps').value = Math.round(m.strengthReps + Math.min(15, done * 0.6));
    $('#reHeightCm').value = m.heightCm;
    $('#reWeightKg').value = Math.max(40, Math.round((m.weightKg - Math.min(4, done * 0.1)) * 10) / 10);
    toast(`완료한 루틴 ${done}회를 반영해 값을 채웠어요 (데모용 추정).`);
  });

  $('#submitRecheckBtn').addEventListener('click', async () => {
    const flexCm = Number($('#reFlexCm').value);
    const strengthReps = Number($('#reStrengthReps').value);
    const heightCm = Number($('#reHeightCm').value);
    const weightKg = Number($('#reWeightKg').value);
    if ($('#reFlexCm').value === '' || $('#reStrengthReps').value === '' || !heightCm || !weightKg) {
      return toast('모든 항목을 입력해 주세요.');
    }
    const before = state.bodyAgeResult;
    const measurement = {
      sex: state.measurement.sex,
      birthYear: state.measurement.birthYear,
      heightCm, weightKg, flexCm, strengthReps,
      testType: state.measurement.testType,
      previousBodyAge: before.bodyAge,
    };
    const after = await Api.bodyAge(measurement);

    renderRecheckResult(before, after);

    // 상태 갱신 - 새로운 3개월 주기 시작
    state.measurement = { ...state.measurement, heightCm, weightKg, flexCm, strengthReps, date: todayStr() };
    state.bodyAgeResult = after;
    state.history.push({ date: todayStr(), bodyAgeResult: after });
    state.startDate = todayStr();
    state.completedDates = [];
    saveState();
  });

  function renderRecheckResult(before, after) {
    const delta = Math.round((before.bodyAge - after.bodyAge) * 10) / 10;
    $('#recheckResultCard').innerHTML = `
      <h3>변화 비교</h3>
      <div class="row" style="align-items:center">
        <div class="center-text"><div class="small">이전</div><div style="font-size:28px;font-weight:700">${before.bodyAge}세</div></div>
        <div class="center-text">→</div>
        <div class="center-text"><div class="small">이후</div><div style="font-size:28px;font-weight:700;color:var(--series-2)">${after.bodyAge}세</div></div>
      </div>
      <div style="text-align:center;margin-top:6px">${delta > 0 ? `<span class="chip good">${delta}세 젊어진 것으로 계산돼요</span>` : delta < 0 ? `<span class="chip warn">${Math.abs(delta)}세 높아진 것으로 계산돼요</span>` : `<span class="chip">변화 없음</span>`}</div>
      ${after.capped ? '<p class="disclaimer">측정 오차 완충을 위해 이번 점검의 변화 폭은 직전 대비 최대 ±5세로 제한했어요.</p>' : ''}
      <div id="compareChart" style="margin-top:14px"></div>
    `;
    Charts.renderGroupedBars($('#compareChart'), {
      categories: FACTOR_ORDER.map((k) => FACTOR_LABEL[k]),
      seriesA: { label: '이전', color: getCssVar('--series-1'), values: FACTOR_ORDER.map((k) => before.stars[k]) },
      seriesB: { label: '이후', color: getCssVar('--series-2'), values: FACTOR_ORDER.map((k) => after.stars[k]) },
      yMax: 5,
    });

    renderUnlocks(before, after);
  }

  async function renderUnlocks(before, after) {
    const improved = FACTOR_ORDER.filter((k) => after.stars[k] > before.stars[k]);
    if (improved.length === 0) {
      $('#unlockCard').innerHTML = `<h3>🔓 루틴 해금</h3><p class="hint">이번 점검에서는 새로 해금된 루틴이 없어요. 다음 점검을 기대해 주세요.</p>`;
      return;
    }
    let unlocked = [];
    for (const k of improved) {
      const res = await Api.videos({ factor: FACTOR_TO_VIDEO_LABEL[k] });
      unlocked.push(...res.items.filter((v) => v.id.startsWith('u') && !state.unlockedIds.includes(v.id)));
    }
    state.unlockedIds.push(...unlocked.map((v) => v.id));
    saveState();
    $('#unlockCard').innerHTML = `
      <h3>🔓 루틴 해금</h3>
      <p class="hint">${improved.map((k) => FACTOR_LABEL[k]).join(', ')} 별점이 올라 새 루틴이 열렸어요.</p>
      <div class="list">${unlocked.length ? unlocked.map((v) => `<div class="video-card"><div class="thumb">${v.thumb}</div><div class="meta"><div class="title">${v.videoNm}</div><div class="sub">${v.ftns_fctr_nm} · ${v.lvl_nm}</div></div></div>`).join('') : '<div class="hint">모든 관련 루틴을 이미 해금했어요.</div>'}</div>
    `;
  }

  function renderRecheck() {
    const m = state.measurement;
    $('#reFlexCm').value = m.flexCm;
    $('#reStrengthReps').value = m.strengthReps;
    $('#reHeightCm').value = m.heightCm;
    $('#reWeightKg').value = m.weightKg;
    $('#recheckResultCard').innerHTML = '';
    $('#unlockCard').innerHTML = '';
  }

  function getCssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

  // ============================================================ 설정
  $('#addBonusSlotBtn').addEventListener('click', () => {
    const v = $('#bonusSlotInput').value.trim();
    if (!v) return;
    if (state.bonusSlots.length >= 3) return toast('짬 보너스 시간은 최대 3개까지 등록할 수 있어요.');
    state.bonusSlots.push(v);
    $('#bonusSlotInput').value = '';
    saveState();
    renderSettings();
  });

  $('#familyShareToggle').addEventListener('change', (e) => {
    state.familyShare.enabled = e.target.checked;
    saveState();
    renderSettings();
  });
  $('#familyNameInput').addEventListener('input', (e) => {
    state.familyShare.name = e.target.value;
    saveState();
    renderFamilyPreview();
  });
  $('#sendFamilyBtn').addEventListener('click', () => {
    toast('가족에게 안심 리포트를 보냈어요 (데모 미리보기).');
  });

  $('#findCenterBtn').addEventListener('click', () => {
    $('#centerList').innerHTML = '<div class="hint">위치 확인 중…</div>';
    if (!navigator.geolocation) return loadCenters(null, null);
    navigator.geolocation.getCurrentPosition(
      (pos) => loadCenters(pos.coords.latitude, pos.coords.longitude),
      () => loadCenters(null, null),
      { timeout: 5000 }
    );
  });
  async function loadCenters(lat, lon) {
    const res = await Api.centers(lat, lon, 5);
    if (lat == null) {
      $('#centerList').innerHTML = '<div class="hint">위치 권한이 없어 전체 목록을 보여드려요.</div>' + res.items.map((c) => centerRowHtml(c)).join('');
    } else {
      $('#centerList').innerHTML = res.items.map((c) => centerRowHtml(c)).join('');
    }
  }
  function centerRowHtml(c) {
    return `<div class="center-row"><div>${c.fcltyNm}<div class="hint">${c.addr}</div></div>${c.distanceKm != null ? `<div class="dist">${c.distanceKm}km</div>` : ''}</div>`;
  }

  $('#resetAllBtn').addEventListener('click', () => {
    if (!confirm('모든 기록을 삭제하고 처음부터 시작할까요?')) return;
    localStorage.removeItem(STORAGE_KEY);
    location.reload();
  });

  function renderFamilyPreview() {
    const weekAgo = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10);
    const count = state.completedDates.filter((d) => d >= weekAgo).length;
    const name = state.familyShare.name || '회원';
    const box = $('#familyPreviewCard');
    if (count > 0) {
      box.innerHTML = `<div>이번 주 <b>${name}</b>님이 <b>${count}번</b>의 건강한 루틴을 완료하셨어요 👏</div>`;
    } else {
      box.innerHTML = `<div>이번 주는 ${name}님의 루틴 기록이 아직 없어요.</div>
        <button class="btn btn-ghost btn-sm" id="cheerBtn" style="margin-top:8px">응원하기 👋</button>`;
      const btn = document.getElementById('cheerBtn');
      if (btn) btn.addEventListener('click', () => toast('응원을 보냈어요! (데모)'));
    }
  }

  function renderSettings() {
    $('#bonusSlotList').innerHTML = state.bonusSlots
      .map((s, i) => `<div class="center-row"><div>${s}</div><button class="btn btn-ghost btn-sm" data-remove="${i}">삭제</button></div>`)
      .join('') || '<div class="hint">등록된 시간이 없어요.</div>';
    $all('#bonusSlotList [data-remove]').forEach((b) =>
      b.addEventListener('click', () => {
        state.bonusSlots.splice(Number(b.dataset.remove), 1);
        saveState();
        renderSettings();
      })
    );
    $('#familyShareToggle').checked = state.familyShare.enabled;
    $('#familyNameInput').value = state.familyShare.name;
    renderFamilyPreview();
  }

  // ============================================================ 초기 진입
  function init() {
    if (!state.measurement || !state.bodyAgeResult) {
      showScreen('screen-measure');
      updateStrengthTestLabel();
      return;
    }
    if (!state.purpose) {
      renderPurposeGrid();
      showScreen('screen-purpose');
      return;
    }
    $('#tabbar').hidden = false;
    switchTab('home');
  }
  init();
})();
