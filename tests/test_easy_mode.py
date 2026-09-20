"""쉬운 모드 — 앱 이용이 어려우실 수 있는 분들을 위한 화면 (frontend/js/easy-mode.js · frontend/easy-mode.css).

예현이 정한 것 (2026-09-20):
- 새로 로그인하면 '쉬운 모드 / 일반 모드' 버튼 두 개가 먼저 뜬다. 설명 문구는 각 이름 아래에 그대로.
- 어르신 전용이 아니다 — 지적(발달)장애 · 시각장애가 있는 분도 쓴다고 보고 만든다.
- 나이는 직접 입력도 된다.

지키려는 것은 하나 더 있다: **화면만 다르고 계산 · 저장 · 기록은 일반 모드와 같다.** 두 모드의 숫자가 갈리면 어느 쪽이 맞는지 알 수 없다.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import main as m  # noqa: E402

client = TestClient(m.app)
FRONT = Path(__file__).resolve().parents[1] / "frontend"


def _html() -> str:
    return client.get("/").text.replace("\r\n", "\n")


def _js() -> str:
    return (FRONT / "js" / "easy-mode.js").read_text(encoding="utf-8")


def _css() -> str:
    return (FRONT / "easy-mode.css").read_text(encoding="utf-8")


def test_두_파일을_내보낸다():
    for 경로 in ("/js/easy-mode.js", "/easy-mode.css"):
        r = client.get(경로)
        assert r.status_code == 200, 경로
        assert r.headers.get("cache-control") == "no-cache, must-revalidate", 경로      # 배포하면 바로 새것이 보이게 (다른 화면 파일과 같다)


def test_로그인하면_모드를_고르는_두_버튼이_먼저_뜬다():
    html, js = _html(), _js()
    assert '<link rel="stylesheet" href="/easy-mode.css" />' in html
    assert '<script src="js/easy-mode.js"></script>' in html
    assert '<div id="easyRoot" hidden></div>' in html
    끝 = html.split("function applyProfile(saved)")[1].split("function renderProfileList()")[0]
    assert "if (window.EASY) EASY.afterLogin();" in 끝                                   # 계정 · 닉네임 두 길이 모두 applyProfile 로 모인다
    들어옴 = js.split("function afterLogin()")[1].split("document.addEventListener")[0]
    assert "if (state.uiMode === 'easy') return open('home');" in 들어옴                 # 쉬운 모드를 골라 둔 사람은 바로 쉬운 모드로
    assert "if (!state.uiMode) return open('mode');" in 들어옴                           # 고른 적이 없으면 두 버튼부터
    # 문구는 예현이 준 그대로, 각 이름 아래에
    assert "<b>쉬운 모드</b><span class=\"s\">앱 이용이 어려우실 수 있는 분들을 위한 화면과 기능이 있어요.</span>" in js
    assert "<b>일반 모드</b><span class=\"s\">앱 이용을 쉽게 하시는 분들을 위한 화면과 기능들이에요.</span>" in js
    assert "보통 모드" not in js and "어르신 모드" not in js                              # 이름은 '일반 모드', 그리고 어르신 전용이 아니다


def test_고른_모드는_프로필에_저장되고_프로필에서_바꾼다():
    html, js = _html(), _js()
    assert "uiMode: null," in html                                                       # 상태
    assert "uiMode: state.uiMode," in html.split("function snapshot()")[1].split("function syncDangerRow")[0]
    assert "state.uiMode = ['easy', 'normal'].includes(saved?.uiMode) ? saved.uiMode : null;" in html
    assert "pickEasy(){ state.uiMode = 'easy'; saveProfile();" in js and "pickNormal(){ state.uiMode = 'normal'; saveProfile(); close();" in js
    assert """onclick="EASY.open('mode')">바꾸기</button>""" in html                      # 프로필 → 내 정보 → 화면 모드
    assert "$('editUiMode').textContent = state.uiMode === 'easy' ? '쉬운 모드' : '일반 모드';" in html
    # 나가면 층을 걷고, 다음 사람에게는 다시 묻는다 (로그아웃 · 계정 삭제 · 초기화)
    assert html.count("state.uiMode = null;") == 3 and html.count("if (window.EASY) EASY.close();") == 3
    # 글자 크기 · 또렷한 색 · 자동 읽기는 기록이 아니라 이 기기의 보기 설정이다
    assert "const VIEW_KEY = 'quadriga.easyView';" in js and "uiMode" not in js.split("const saveView")[1].split(";")[0]


def test_계산과_저장은_일반_모드와_같은_것을_쓴다():
    """시안은 분포표와 계산식을 화면 안에 따로 들고 있었다. 앱에서는 그러면 안 된다 — 서버가 낸 숫자 하나만 쓴다."""
    js = _js()
    assert "const DIST" not in js and "function convertAge" not in js and "function fitnessAge" not in js
    계산 = js.split("async function calc()")[1].split("function logRoutine()")[0]
    assert "state.result = await API.fitnessAge(measurement());" in 계산
    assert "commitResultQuietly();" in 계산                                               # 첫 점검 · 점검 기록 · 저장까지 같은 길
    assert "syncInputsFromState(); renderResult();" in 계산                               # 일반 모드로 돌아가도 같은 값이 보이게
    for 옮김 in ("state.age = P.age;", "state.strength = P.power;", "state.flexibility = P.reach;", "if (g === '어르신') state.endurance = P.steps;"):
        assert 옮김 in 계산, 옮김
    assert "const nowAge = () => (state.result && displayAge() != null) ? displayAge() : null;" in js     # 게이지 · 프로필과 같은 숫자
    assert "const pct = peers[k]?.백분위;" in js                                          # '10명 중 몇 번째' 도 서버의 또래 백분위에서
    html = _html()
    조용히 = html.split("function commitResultQuietly()")[1].split("function lastMeasuredAge()")[0]
    assert "try { commitResult(); } finally { questMuted = false; }" in 조용히            # 같은 함수를 부른다 — 연출만 끈다
    assert "if (questMuted) return;" in html.split("function showQuestClear(이전, 지금)")[1][:200]
    # 오늘 운동을 끝내면 일반 모드의 '운동한 날' 과 같은 곳에, 같은 모양으로 — 날짜당 한 줄
    기록 = js.split("function logRoutine()")[1].split("const ACT = {")[0]
    assert "state.routineLog.find(x => x.date === today && !x.시간대)" in 기록
    assert "{ date: today, no: null, done: true, 시간대: null, name: r.title, steps: [], 부분: [], 강도: null }" in 기록
    assert "await refreshActivityAge(); await refreshLogAges({ 전부: true });" in 기록
    assert "const stamps = () => new Set(allRoutineLog().map(e => e.date));" in js         # 도장은 일반 모드에서 한 날도 같이 센다


def test_재는_항목은_앱과_같은_공식_규격이다():
    """성인 윗몸일으키기 1분 · 어르신 의자 일어서기 30초 · 성장기 제자리멀리뛰기 — 기록을 공개 분포와 견주기 때문이다."""
    js, html = _js(), _html()
    assert "'성인': { item: '교차윗몸일으키기', key: '근지구력'" in js and "unit: '번', max: 100, secs: 60" in js
    assert "'어르신': { item: '의자앉았다일어서기', key: '근지구력'" in js and "unit: '번', max: 80, secs: 30" in js
    assert "'성장기': { item: '제자리멀리뛰기', key: '순발력'" in js and "unit: 'cm', max: 350, secs: 0" in js
    assert "timer: true,  seconds: 60 }" in html and "timer: true,  seconds: 30 }" in html  # 일반 모드의 STRENGTH_ITEM 과 같다
    assert "const grpOf = age => ageGroup(age);" in js                                    # 나이대 경계도 앱의 것
    assert "age: { label: '나이', obj: '나이를', unit: '세', min: 11, max: 100 }" in js    # 만 11세부터, 어르신 전용이 아니다
    # 나이는 −/+ · 빠른 선택 · 직접 입력(화면 안 큰 숫자판) 세 가지로 넣는다
    assert "data-act=\"openPad\"" in js and "chips('age', [15, 25, 35, 45, 55, 65, 75, 85])" in js
    # 점검한 적이 없는 사람에게 성별을 미리 골라 두지 않는다 (일반 화면의 기본값이 말없이 따라오면 안 된다)
    assert "sex: 잰적 ? (state.sex || null) : null" in js and "여성, 남성 가운데 하나를 눌러 주세요." in js


def test_잘_안_보이거나_읽기_어려운_분도_쓸_수_있다():
    js, css = _js(), _css()
    # 화면낭독기: 알림 영역 · 대화상자 · 아래에 깔린 화면은 없는 것으로
    assert 'id="ezLive" aria-live="polite"' in js and 'role="dialog" aria-modal="true"' in js
    assert "others().forEach(el => el.setAttribute('inert', ''));" in js and "others().forEach(el => el.removeAttribute('inert'));" in js
    assert "el.focus({ preventScroll: true })" in js                                     # 화면이 바뀌면 제목으로 초점을 옮긴다
    # 읽어 주기 (켜 둔 사람에게만 자동으로)
    assert "new SpeechSynthesisUtterance(text)" in js and "u.lang = 'ko-KR'" in js and "if (V.auto) say(SAY[to]());" in js
    # 글자 네 단계 · 또렷한 색 · 누르는 곳은 52px 이상
    assert "const SIZES = ['보통', '크게', '더 크게', '아주 크게'];" in js
    assert '.ez[data-size="3"]{ --fs:30px; }' in css and '.ez[data-hc="1"], .ez[data-hc="1"] ~ .ez-sheet{' in css
    assert "--paper:#000000;" in css and "--pine:#FFE500;" in css                        # 검정 바탕 · 노란 버튼
    assert ".ez-tool{ min-height:52px;" in css and ".ez-chip{ min-height:52px;" in css
    # 상태는 모양 + 말 + 색 세 가지로 — 색을 못 가려도 읽힌다
    assert ".ez-state.good i{ border-radius:50%; }" in css and ".ez-state.okay i{ clip-path:polygon(50% 0, 100% 100%, 0 100%); }" in css
    assert "['good', '좋아요']" in js and "또래 10명 중 ${n}번째예요." in js               # 백분위 대신 '10명 중 몇 번째'
    # 일반 화면의 색을 건드리지 않는다 — 색 이름은 이 층 안에서만 다시 정한다
    assert css.count(":root") == 0 and "#easyRoot{" in css and "#easyRoot svg.ic{" in css


def test_동작마다_글_설명과_조심할_점이_있다():
    """3D 화면을 못 보는 분도 '읽어 주기' 로 따라 할 수 있어야 한다."""
    js = _js()
    루틴 = js.split("const ROUTINES = {")[1].split("const routine = ")[0]
    for 나이대 in ("'어르신'", "'성인'", "'청소년'", "'유소년'"):
        assert 나이대 + ": { title:" in 루틴, 나이대
    assert 루틴.count("how: [") == 20 and 루틴.count("tip: '") == 20                      # 나이대 넷 × 다섯 동작
    assert 루틴.count("tag: '준비운동'") == 4 and 루틴.count("tag: '정리운동'") == 4
