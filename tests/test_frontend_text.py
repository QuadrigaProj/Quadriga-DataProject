"""화면 문구 회귀 테스트 — "/" 응답 본문의 문자열만 본다.

JS 를 실행하지 않고 index.html 본문에 노션이 정한 문구가 있는지, 교체·삭제를 요구한
옛 문구가 사라졌는지만 확인한다. 문구를 바꾸면 이 파일도 같이 고친다.
뒤 작업은 파일 끝에 `# ---------- <요구사항> ----------` 절을 덧붙여 쓴다
(import · client · _index 는 재정의하지 않는다).
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.main import app  # noqa: E402

client = TestClient(app)


def _index() -> str:
    """index.html 본문. tests/test_api.py 의 test_frontend_served 와 같은 경로."""
    r = client.get("/")
    assert r.status_code == 200
    return r.text


# ---------- A6 로그인 문구 ----------

def test_로그인_제목과_설명():
    html = _index()
    assert "체력 나이로<br/>맞춤 운동을 시작하세요" in html
    assert "국민체력100 데이터 기반으로 3분 만에 또래 대비 내 체력을 비교해 드립니다." in html
    assert "오늘 할 운동을 정해요</h1>" not in html      # <title> 태그의 옛 슬로건은 범위 밖이라 </h1> 로 한정
    assert "3분이면 첫 점검이 끝나요" not in html


def test_로그인_메인_버튼():
    html = _index()
    assert 'id="authBtn"' in html
    assert "이메일로 시작하기</button>" in html
    assert "textContent = '이메일로 시작하기'" in html          # setAuthMode 가 되돌리지 않는다
    assert "'회원가입' : '로그인'" not in html
    assert "'이 기기에서 시작하기'" in html                     # localOnly 닉네임 모드는 그대로


def test_개인정보_안내():
    html = _index()
    assert "<b>수집 정보 최소화</b>" in html
    assert "닉네임과 체력 측정값만 받으며, 전화번호나 주소 등 개인정보는 요구하지 않습니다." in html
    assert "받는 정보는" not in html
    assert "소셜 계정에서도 가져오지 않아요" not in html


def test_비회원_시작_버튼():
    html = _index()
    assert "가입 없이 이 기기에서만 써볼게요</button>" in html
    assert 'onclick="enterAsGuest()"' in html
    assert "게스트로 바로 시작하기" not in html
    assert "guest-note" not in html                            # 마크업·CSS 모두 삭제
    assert "나중에 계정을 만들면 지금까지의 기록을 그대로 옮겨드립니다" not in html


def test_유지되는_요소():
    """A6 가 손대지 말라고 한 것들 — 소셜 버튼·탭·입력칸·닉네임 링크·정책 링크."""
    html = _index()
    for s in ("구글로 계속하기", "네이버로 계속하기", "카카오로 계속하기",
              'id="tabLogin"', 'id="tabSignup"', 'placeholder="이메일"', 'placeholder="비밀번호 (8자 이상)"',
              "닉네임을 정해서 시작할래요", "개인정보처리방침", "이용약관", "또는 이메일로"):
        assert s in html, s


# ---------- C1·C2·A5 ----------

def test_간단_자가측정은_사라졌다():
    html = _index()
    assert "간단 자가측정" not in html
    assert 'data-m="self"' not in html
    assert "selectMethod('self')" not in html
    assert "method: 'self'" not in html


def test_측정_방식은_홈_체력측정과_InBody_둘뿐이다():
    html = _index()
    assert html.count("onclick=\"selectMethod('") == 2
    assert 'class="on" data-m="home"' in html          # 홈 체력측정이 기본 선택
    assert 'data-m="inbody"' in html
    assert "홈 체력측정" in html and "InBody" in html


def test_홈_체력측정_항목_문구가_원문과_같다():
    html = _index()
    for s in [
        "나이 · 성별",
        "다리를 펴고 앉아 손끝이 닿는 거리",
        "윗몸일으키기",
        "키 · 몸무게",
        "30초 제자리 점프", "두 발 모아 제자리에서 최대한 빠르게",
        "30초 무릎 푸시업", "무릎을 대고 팔굽혀펴기",
        "2분 제자리 높은 무릎 뛰기", "한쪽 무릎이 올라올 때마다 1회",
    ]:
        assert s in html, s
    assert 'id="homeExtra">' in html                    # 홈 추가 3종이 기본으로 보인다(hidden 아님)


def test_홈_체력등급_표시_영역이_있다():
    html = _index()
    assert 'id="homeGradeBlock"' in html
    assert "async function loadHomeGrades" in html
    assert "function renderHometest" not in html       # 옛 홈 흐름은 제거


def test_키_몸무게_입력은_1_이상만_받는다():
    html = _index()
    assert 'id="heightInput" type="number" min="1"' in html
    assert 'id="weightInput" type="number" min="1"' in html
    assert "키와 몸무게는 0보다 큰 값으로 입력해주세요." in html   # 제출 시 JS 검증 문구


# ---------- C3/C4 타이머 ----------

def test_타이머는_측정_카드마다_하나씩이다():
    """윗몸일으키기·점프·무릎 푸시업은 30초, 높은 무릎 뛰기는 2분 — 마크업의 data-seconds 가 곧 정의다."""
    html = _index()
    assert 'data-timer="situp" data-seconds="30"' in html
    assert 'data-timer="jump" data-seconds="30"' in html
    assert 'data-timer="kneePushup" data-seconds="30"' in html
    assert 'data-timer="highKnee" data-seconds="120"' in html
    assert html.count('class="timer-btn"') == 4
    assert '<div class="timer-time">02:00</div>' in html  # 2분 타이머 초기 표시


def test_타이머_함수는_한_세트다():
    """startTimer/pauseTimer/resetTimer 로 통합됐고, 음수로 내려가던 옛 toggleTimer() 가 없다."""
    html = _index()
    for fn in ("function startTimer(id, seconds)", "function pauseTimer()", "function resetTimer(id)",
               "function resetAllTimers()", "function toggleTimer(id)"):
        assert fn in html, fn
    assert "timerSeconds--" not in html          # 리셋 없이 깎기만 하던 옛 코드
    assert 'onclick="toggleTimer()"' not in html  # 인자 없는 옛 버튼
    assert "Math.max(0, Math.ceil((timerState.endAt - Date.now()) / 1000))" in html  # 음수 불가 계산식


def test_타이머가_끝나면_빨간색_클래스가_있다():
    html = _index()
    assert ".timer-time.done{ color:var(--clay); }" in html
    assert "'다시 시작'" in html  # 00:00 뒤 재시작 버튼 문구


# ---------- A1~A4·B 결과·프로필 문구 ----------

# 노션이 삭제를 요구한 문구·요소 — 하나라도 남아 있으면 실패
삭제된_문구 = [
    '<div class="eyebrow">스포츠 프로필</div>',            # A1
    "항목 간 편차",                                        # A1 ±N세 표시 전부
    "공개 데이터로 잴 수 있는 항목만 표시합니다",            # A1
    '<div class="eyebrow">첫 점검</div>',                  # A1 보조 단계 문구
    '<div class="eyebrow">목적 선택</div>',
    '<div class="eyebrow">운동 고르기</div>',
    '<div class="eyebrow">기록</div>',
    '<div class="eyebrow">3개월 재점검</div>',
    "목표 나이를 미리 정하지 않아요",                        # A2
    '<div class="prescribe-label">지금부터</div>',         # A2
    "지금 가장 먼저 채우면 좋은 건",                         # A3
    "또래보다 특히 처지는 건",                               # A3
    "세 앞서 있어요",                                       # A4
    "세 젊어요",                                            # A4
    '<div class="eyebrow">또래와 비교</div>',              # B2
    'id="ciLow"', 'id="ciMid"', 'id="ciHigh"',            # B2 발달 수준 3숫자
    'id="ciNote"', 'id="ciCaption"',                      # B2 해석 문구 표시
    "가장 앞선 항목은",                                     # B2
    "명 중 약 ${fmtInt(rank)}등",                          # B2 항목별 등수
    "막대 가운데 선은 또래 중앙값이에요",                     # B2 긴 설명
    'id="calcTable"',                                     # B2 반복 영역
    "또래 평균",                                            # B5 — 중앙값 사용이므로 금지
]

# 교체·추가된 문구 — 하나라도 없으면 실패
추가된_문구 = [
    # A2. #70 에서 "3개월간" 을 빼고 다시 썼다 — 프로그램 기간을 못 박지 않는 쪽이 맞다.
    "맞춤 운동을 진행하다가, 원할 때 다시 측정해서 달라진 체력을 확인해보세요.",
    "집중 개선 영역: ${",                                                   # A3 동적
    "3개월 프로그램이 이 항목 중심으로 구성됩니다.",                            # A3
    "신체 나이가 또래 중앙값보다<br/><span class=\"peer-emph\">${n}세 높게</span> 나왔어요.",   # A4
    "신체 나이가 또래 중앙값보다<br/><span class=\"peer-emph\">${n}세 낮게</span> 나왔어요.",   # A4
    "또래 중앙값과 비슷해요.",                                               # A4 중립
    '<div class="eyebrow">당신의 체력나이</div>',                            # B1 유지
    "국민체력100 데이터 기준 (동일 성별·연령)",                               # B1
    "내 기록 ${v.내기록}${u} / 또래 중앙값 ${v.또래중앙값}${u}",                # B1/B5
    'class="peer-badge up"', 'class="peer-badge down"',                    # B3 ▲/▼
]


def test_삭제한_문구가_화면에_없다():
    html = _index()
    남은것 = [s for s in 삭제된_문구 if s in html]
    assert not 남은것, f"삭제 대상 문구가 아직 있다: {남은것}"


def test_교체한_문구가_화면에_있다():
    html = _index()
    빠진것 = [s for s in 추가된_문구 if s not in html]
    assert not 빠진것, f"교체 문구가 없다: {빠진것}"


def test_체력나이_제목은_남아_있다():
    """보조 문구만 지우고 주요 제목은 건드리지 않는다 (A1 단서)."""
    html = _index()
    assert 'id="s1Title"' in html
    assert 'id="ageResult"' in html
    assert 'id="peerRank"' in html


# ---------- C7 센터 검색 (구 단위) ----------

def test_센터_검색창은_구_단위_placeholder():
    assert 'placeholder="지역명 (예: 성북구)"' in _index()


def test_지하철역_문구는_사라졌다():
    html = _index()
    assert "지하철역" not in html
    assert "성신여대입구역" not in html
    assert "역 이름으로" not in html


def test_센터_검색은_매칭방식으로_안내_위치를_정한다():
    html = _index()
    assert "r.매칭방식 === '거리'" in html
    assert "구 이름으로 다시 입력해 주세요" in html


# ---------- C8/C9 오늘 컨디션 ----------

def test_아픈_부위_선택_UI가_화면에_없다():
    """C8: 무릎·허리·어깨 칩과 관련 함수·안내 문구가 index.html 에서 사라졌다."""
    html = _index()
    for gone in ("chipKnee", "chipBack", "chipShoulder", "toggleChip(", "excludedParts(",
                 "data-part=", "exclude_parts", ".cond-btn.off",
                 "아픈 부위나 오늘 컨디션을 누르면", "부위에 부담이 가는 영상을 제외했어요",
                 "부위 제한을 해제했어요", "아프면 위 버튼을 눌러주세요"):
        assert gone not in html, gone


def test_컨디션_선택지는_몸이_무거운_날_하나만():
    """C9: cond-btn 은 heavyBtn 하나뿐이고, heavy 는 계속 서버로 보낸다."""
    html = _index()
    assert html.count('class="cond-btn') == 1
    assert 'id="heavyBtn"' in html
    assert "몸이 무거운 날" in html
    assert "toggleHeavy()" in html
    assert "heavy: heavyOn" in html
    assert "아무것도 누르지 않으면 오늘의 원래 루틴 그대로예요" in html


# ---------- F3 신체나이 재측정 (즉시) ----------

def test_홈에_재측정하기_버튼이_있다():
    """F3: 홈 우상단 D-day 필이 항상 누를 수 있는 「재측정하기」 버튼이 됐다."""
    html = _index()
    assert 'id="ddayPill"' in html
    assert 'onclick="remeasure()"' in html
    assert "재측정하기" in html


def test_3개월_뒤_재점검_문구가_사라졌다():
    """3개월 뒤 재점검을 전제한 문구는 전부 없다 (A2 의 '3개월간 맞춤 운동을 진행한 뒤' 권장 문구는 s5 에 남는다)."""
    html = _index()
    for gone in ("재점검까지 D-", "재점검할 때가 됐어요", "이번 3개월",
                 "3개월마다 다시 잴 수 있어요", "지난 3개월, 이렇게 바뀌었어요",
                 "3개월 뒤 다시 재보면"):
        assert gone not in html, gone


def test_기간_보관과_측정_이력이_저장된다():
    """archivePeriod/commitResult 가 있고 snapshot 이 history·measureLog 를 같이 저장한다."""
    html = _index()
    assert "function archivePeriod(" in html
    assert "function commitResult(" in html
    assert "history: state.history" in html
    assert "measureLog: state.measureLog" in html


def test_지난_점검_결과_링크는_남아_있다():
    """s6 는 '첫 점검 vs 최근 측정' 비교로 남고 홈의 미리 보기 링크도 그대로다."""
    html = _index()
    assert "지난 점검 결과 미리 보기" in html
    assert "첫 점검 이후, 이렇게 바뀌었어요" in html
    assert 'id="cmpAfterLabel"' in html


# ---------- G5 목록(좌상단 드로어) ----------

def test_하단_탭바가_사라졌다():
    """G5: 아래쪽 다섯 버튼을 좌상단 목록 버튼으로 옮겼다."""
    html = _index()
    for gone in ('class="tabbar"', "data-tabbar", "renderTabbar", "const TABS =",
                 "tab-icon", "tab-label"):
        assert gone not in html, gone


def test_목록_버튼과_패널이_있다():
    html = _index()
    assert 'id="menuBtn"' in html
    assert 'onclick="toggleMenu(event)"' in html
    assert 'aria-label="목록"' in html
    assert 'id="menuPanel"' in html
    assert "function renderMenu(activeId)" in html
    assert "function toggleMenu(ev)" in html
    assert "function closeMenu()" in html


def test_목록_항목_다섯개가_그대로다():
    """홈·기록·달력·운동 고르기·프로필 — 위치만 옮기고 항목은 그대로."""
    html = _index()
    assert "const MENU_ITEMS = [" in html
    block = html.split("const MENU_ITEMS = [")[1].split("];")[0]
    for sid, label in (("s3", "홈"), ("s7", "기록"), ("s9", "달력"),
                       ("s8", "운동 고르기"), ("s5", "프로필")):
        assert f"id: '{sid}'" in block, sid
        assert f"'{label}'" in block, label


def test_화면을_옮기면_목록이_닫힌다():
    html = _index()
    goto = html.split("function goTo(id){")[1].split("\n}")[0]
    assert "renderMenu(id);" in goto
    assert "closeMenu();" in goto


# ---------- G1 점검기록 선택 삭제 ----------

def test_점검기록_선택_삭제_UI가_있다():
    html = _index()
    assert 'id="recDeleteBtn"' in html
    assert 'onclick="deleteSelectedMeasures()"' in html
    assert "삭제할 기록을 고르세요" in html
    assert "function renderMeasureRecords()" in html
    assert "function pickMeasure(i, on)" in html
    assert "async function deleteSelectedMeasures()" in html


def test_점검기록은_measureLog를_보여준다():
    """달력·변화추이와 같은 배열을 읽어야 지운 결과가 함께 반영된다."""
    html = _index()
    body = html.split("function renderMeasureRecords()")[1].split("\nfunction pickMeasure")[0]
    assert "state.measureLog" in body
    # 서버 스냅샷 목록을 쓰던 옛 경로는 사라졌다
    assert "const rows = (r.기록 || []).filter" not in html


def test_삭제는_저장까지_한다():
    html = _index()
    body = html.split("async function deleteSelectedMeasures()")[1].split("\n}")[0]
    assert "confirm(" in body            # 되돌릴 수 없으니 한 번 묻는다
    assert "saveProfile()" in body       # 기기·계정 모두에 반영
    assert "renderRecords()" in body


def test_직접적은운동_선택_삭제_UI가_있다():
    """직접 적은 운동도 점검 기록과 같은 방식(체크박스 + 일괄 삭제)으로 지울 수 있다."""
    html = _index()
    assert 'id="recManualDeleteBtn"' in html
    assert 'onclick="deleteSelectedManual()"' in html
    assert "function renderManualRecords()" in html
    assert "function pickManual(i, on)" in html
    assert "async function deleteSelectedManual()" in html
    body = html.split("async function deleteSelectedManual()")[1].split("\n}")[0]
    assert "confirm(" in body
    assert "saveProfile()" in body
    assert "renderRecords()" in body


def test_점검기록_삭제는_직접적은운동이_남아있으면_막힌다():
    """같은 날짜에 직접 적은 운동이 남아있으면, 그 기록의 기준나이가 참조하고 있을 수
    있어 점검 기록을 먼저 지우지 못하게 막는다."""
    html = _index()
    body = html.split("async function deleteSelectedMeasures()")[1].split("\n}")[0]
    assert "state.workoutLog" in body
    assert "직접 적은 운동에서 먼저 삭제를 진행해주세요" in body


def test_점검기록_삭제_안내는_닫을수있는_모달로_보인다():
    html = _index()
    assert 'id="noticeModal"' in html
    assert 'onclick="closeNoticeModal()"' in html
    assert "openNoticeModal('직접 적은 운동에서 먼저 삭제를 진행해주세요')" in html


def test_커뮤니티_작성과_채팅방_생성은_플러스_버튼으로_연다():
    html = _index()
    assert 'onclick="openPostComposer()"' in html
    assert 'onclick="openRoomComposer()"' in html
    assert 'id="postComposer"' in html and 'id="roomComposer"' in html


# ---------- G2 변화추이 기간 직접 입력 ----------

def test_전체_버튼이_직접_입력으로_바뀌었다():
    html = _index()
    assert 'onclick="setTrendPeriod(0)">전체</button>' not in html
    assert 'id="trendCustomBtn"' in html
    assert 'onclick="toggleTrendCustom()">직접</button>' in html


def test_숫자와_단위를_고를_수_있다():
    html = _index()
    assert 'id="trendNum"' in html
    assert 'id="trendUnit"' in html
    for v, u in (("1", "일"), ("7", "주"), ("30", "개월")):
        assert f'value="{v}"' in html and f">{u}</option>" in html, u
    assert "function applyTrendCustom()" in html


def test_기간_이름이_단위를_살린다():
    """'최근 90일' 이 아니라 '최근 3개월' 로 보이게 trendLabel 을 쓴다."""
    html = _index()
    assert "let trendLabel" in html
    assert "const label = trendLabel;" in html
    body = html.split("function applyTrendCustom()")[1].split("\n}")[0]
    assert "trendLabel = `최근 ${n}${unit}`;" in body


# ---------- G6 체력나이 항목 확대 ----------

def test_선택_측정_입력칸이_있다():
    html = _index()
    assert 'id="moreCard"' in html
    assert 'id="gripInput"' in html
    assert 'id="enduranceInput"' in html
    assert "function toggleMoreMeasure()" in html
    assert "function syncMoreMeasure()" in html


def test_심폐_항목은_연령군마다_다르다():
    html = _index()
    assert "'성인':   { 이름: '왕복오래달리기'" in html
    assert "'어르신': { 이름: '2분제자리걷기'" in html
    # 성장기는 CARDIO_LABEL 에 없다 → syncMoreMeasure 가 칸을 숨긴다
    body = html.split("function syncMoreMeasure()")[1].split("\n}")[0]
    assert "row.hidden = !c;" in body


def test_선택값을_서버로_보낸다():
    html = _index()
    body = html.split("function measurement()")[1].split("\n}")[0]
    assert "grip_kg: state.gripKg" in body
    assert "endurance: state.endurance" in body


# ---------- H5 프로필 차트 항목 ----------

def test_차트_순서가_고정이다():
    """유연성 · 근력 · 근지구력 · 심폐지구력 · 체성분 — 안 잰 항목도 자리를 지킨다."""
    html = _index()
    assert "const AXIS_ORDER = ['유연성', '근력', '근지구력', '심폐지구력', '체성분'];" in html
    assert "function axisOrder(항목별)" in html


def test_안_잰_항목은_해당사항_모름이다():
    html = _index()
    assert "해당사항 모름" in html
    body = html.split("const 순서 = axisOrder(r.항목별);")[1].split("}).join('');")[0]
    assert "const 잰것 = Number.isFinite(v);" in body
    assert "axis-none" in body          # 별 대신 안내 문구


def test_잰_항목만_그리던_옛_코드가_없다():
    html = _index()
    assert "Object.entries(r.항목별).map(([k,v],i,arr)" not in html


# ---------- I3. 운동 기록 반영 체력나이 ----------

def test_기록을_저장하면_체력나이를_다시_본다():
    """saveDailyLog 안에서 refreshActivityAge 를 부르고 게이지를 다시 칠해야 한다."""
    html = _index()
    본문 = html.split("async function saveDailyLog()")[1].split("\n}")[0]
    assert "refreshActivityAge()" in 본문
    assert "paintGauges()" in 본문


def test_기록에_요인을_함께_남긴다():
    # 요인이 없으면 나중에 카탈로그 없이 셀 수 없다
    html = _index()
    본문 = html.split("function collectLogItems()")[1].split("\n}")[0]
    assert "요인: x.요인" in 본문


def test_체력나이_표시는_반영값을_먼저_본다():
    html = _index()
    assert "function displayAge()" in html
    본문 = html.split("function displayAge()")[1].split("\n}")[0]
    assert "state.activityAge?.체력나이" in 본문
    assert "state.result?.체력나이" in 본문
    # 게이지가 옛 경로를 그대로 쓰면 화면이 안 바뀐다
    assert "fitnessAge: displayAge()" in html


def test_다시_재면_추정치를_버린다():
    html = _index()
    본문 = html.split("function commitResult()")[1].split("\n}")[0]
    assert "state.activityAge = null" in 본문


def test_반영값도_저장하고_되돌린다():
    html = _index()
    assert "activityAge: state.activityAge," in html            # snapshot
    assert "state.activityAge = (saved?.activityAge" in html    # applyProfile


def test_서버가_실패하면_조용히_측정값으로_남는다():
    html = _index()
    본문 = html.split("async function refreshActivityAge()")[1].split("\n}\n")[0]
    assert "catch" in 본문
    assert "state.activityAge = null" in 본문


# ---------- J1·J3. 계정 패널 이용권 · 아바타 두 곳 ----------

def test_계정_패널에_이용권_줄이_있다():
    html = _index()
    assert 'id="acctPay"' in html
    assert "function renderAcctCredit()" in html
    본문 = html.split("function renderAcctCredit()")[1].split("\n}")[0]
    assert "AI 추천 선결제" in 본문
    # 결제 여부와 남은 금액을 둘 다 적어야 한다
    assert "선결제됨" in 본문 and "선결제 안 함" in 본문
    assert "won(원)" in 본문


def test_패널을_열_때마다_이용권을_다시_그린다():
    html = _index()
    본문 = html.split("function renderAccount()")[1].split("\n}")[0]
    assert "renderAcctCredit()" in 본문


def test_이용권_줄을_누르면_충전창이_열린다():
    html = _index()
    assert 'onclick="payFromAccount(event)"' in html
    본문 = html.split("function payFromAccount(ev)")[1].split("\n}")[0]
    assert "openPaySheet()" in 본문


def test_충전하면_패널_줄도_갱신한다():
    # J2 에서 confirmPay 가 addCredit 으로 바뀌었다 — 충전을 반영하는 자리는 여기 하나다
    html = _index()
    본문 = html.split("async function addCredit(금액, 결제)")[1].split("\n}")[0]
    assert "renderAcctCredit()" in 본문


def test_아바타_두_곳_모두_프로필로_간다():
    """J3: 헤더 아바타(한 번 더 누르기)와 패널 안 큰 아바타가 같은 길을 쓴다."""
    html = _index()
    # 패널 아바타는 span 이 아니라 button 이어야 키보드로도 눌린다
    머리 = html.split('id="acctAvatarBig"')[0]
    assert 머리.rstrip().endswith('<button type="button" class="acct-avatar big"')
    assert 'onclick="goProfile()"' in html
    assert "function goProfile(ev)" in html
    본문 = html.split("function goProfile(ev)")[1].split("\n}")[0]
    assert "goTo('s5')" in 본문
    # 헤더 아바타도 같은 함수를 쓴다 (두 곳이 갈라지지 않게)
    토글 = html.split("function toggleAccount(ev)")[1].split("\n}")[0]
    assert "goProfile()" in 토글


# ---------- J4·J5. 자세히 보기 — 목록 오른쪽 · 세 목록 모두 ----------

def test_자세히_보기는_공통_함수로_만든다():
    """목록마다 따로 쓰면 한 곳만 고쳐지고 나머지가 남는다."""
    html = _index()
    assert "function moreToggle(html)" in html
    본문 = html.split("function moreToggle(html)")[1].split("\n}")[0]
    assert "rec-more" in 본문 and "rec-detail" in 본문
    assert "if (!html) return ''" in 본문          # 보여줄 게 없으면 버튼도 없다


def test_버튼은_줄_오른쪽에_붙는다():
    html = _index()
    css = html.split(".rec-more{")[1].split("}")[0]
    assert "margin-left:auto" in css               # 오른쪽 끝으로 민다
    # 상세는 줄 아래 한 칸 전체를 쓴다
    assert "flex-wrap:wrap" in html.split(".rec-item{")[1].split("}")[0]
    assert "flex-basis:100%" in html.split(".rec-detail{")[1].split("}")[0]


def test_토글은_줄_안에서_상세를_찾는다():
    """버튼 바로 옆에 상세가 없어도(가운데 ✓ 가 끼어도) 동작해야 한다."""
    html = _index()
    본문 = html.split("function toggleRecDetail(btn)")[1].split("\n}")[0]
    assert "closest('.rec-item')" in 본문
    assert "querySelector('.rec-detail')" in 본문
    assert "nextElementSibling" not in 본문


def test_세_목록_모두_자세히_보기가_있다():
    html = _index()
    루틴 = html.split("$('recList').innerHTML")[1].split("renderMeasureRecords()")[0]
    assert "moreToggle(routineDetailHtml(e))" in 루틴
    직접 = html.split("$('recManual').innerHTML")[1].split("\n}")[0]
    assert "moreToggle(manualDetailHtml(w))" in 직접
    점검 = html.split("$('recMeasures').innerHTML")[1].split("paintMeasureDeleteBtn()")[0]
    assert "moreToggle(measureDetailHtml(m))" in 점검


def test_달력_아래_목록도_같다():
    """J5: 달력에서 고른 날의 운동·측정 줄에도 같은 버튼이 붙는다."""
    html = _index()
    본문 = html.split("function renderCalDay()")[1].split("\n}")[0]
    # K1 에서 그날 체력나이를 붙이려고 원본 기록(logAt)을 넘기도록 바뀌었다
    assert "moreToggle(e.직접 ? manualDetailHtml(logAt(e.date) || e) : routineDetailHtml(e))" in 본문
    assert "moreToggle(measureDetailHtml(p))" in 본문


def test_달력이_직접기록의_종목을_받는다():
    """items 를 안 넘기면 달력에서 펼칠 내용이 비어 버튼이 사라진다."""
    html = _index()
    본문 = html.split("function allRoutineLog()")[1].split("\n}")[0]
    assert "items: w.items" in 본문


def test_점검_기록은_버튼과_체크박스가_안_겹친다():
    """label 안에 button 을 두면 버튼을 눌러도 체크박스가 켜진다."""
    html = _index()
    점검 = html.split("$('recMeasures').innerHTML")[1].split("paintMeasureDeleteBtn()")[0]
    assert '<div class="rec-item rec-pick">' in 점검      # label 이 아니다
    assert '<label class="rec-pick-main">' in 점검        # 고르는 부분만 label
    # 버튼은 label 밖에 있어야 한다
    assert 점검.index("</label>") < 점검.index("moreToggle(")


# ---------- J2. 결제창 · 카카오페이 ----------

def test_결제_수단_세_가지가_있다():
    html = _index()
    assert "const PAY_WAYS = {" in html
    본문 = html.split("const PAY_WAYS = {")[1].split("};")[0]
    for k in ("kakao:", "card:", "bank:"):
        assert k in 본문, k
    assert "카카오페이" in 본문 and "신용·체크카드" in 본문 and "계좌이체" in 본문


def test_카드사와_은행은_서버가_준_목록을_쓴다():
    """화면에 박아 두면 늘리거나 줄일 때 배포를 다시 해야 한다."""
    html = _index()
    본문 = html.split("function payWayHtml()")[1].split("function pickPay(v)")[0]
    assert "payInfo?.카드" in 본문 and "payInfo?.은행" in 본문


def test_동의_전에는_결제_버튼이_잠긴다():
    html = _index()
    본문 = html.split("function payWayHtml()")[1].split("function pickPay(v)")[0]
    assert "const 준비됨 = payAgree &&" in 본문
    # 카드·계좌는 발급사를 골라야 한다
    assert "payWay === 'kakao' || !!payIssuer" in 본문
    assert "${준비됨 ? '' : 'disabled'}" in 본문


def test_키가_없으면_카카오페이_버튼이_잠긴다():
    html = _index()
    본문 = html.split("function payAmountHtml()")[1].split("\n}")[0]
    assert "payInfo?.kakao?.쓸수있음" in 본문
    assert "관리자가 키를 등록하면 켜져요" in 본문


def test_테스트_가맹점인지_화면에_적는다():
    """실제로 돈이 빠지는지 아닌지를 사용자가 눌러 보기 전에 알아야 한다."""
    html = _index()
    assert "payInfo?.kakao?.테스트" in html
    assert "실제로 돈이 빠지지 않아요" in html
    assert "실제로 결제됩니다" in html


def test_카카오페이만_진짜_결제창으로_보낸다():
    html = _index()
    본문 = html.split("async function startPay()")[1].split("\n}")[0]
    assert "if (payWay === 'kakao')" in 본문
    assert "API.payReady({ amount: payPick })" in 본문
    assert "location.href = r.redirect" in 본문
    assert "await addCredit(팩.이용권, 팩.결제);" in 본문   # 나머지는 모의 승인


def test_충전_금액은_서버가_확인해_준_값을_쓴다():
    """화면이 고른 숫자를 그대로 올리면 조작할 수 있다."""
    html = _index()
    본문 = html.split("async function handlePayReturn()")[1].split("\n}")[0]
    assert "API.payResult(order)" in 본문
    assert "addCredit(r.amount, r.결제)" in 본문
    assert "addCredit(payPick)" not in 본문


def test_결제만_되고_프로필이_없으면_들고_있는다():
    """결제창을 다녀오면 페이지가 새로 뜬다. 손님은 그때 프로필이 없다."""
    html = _index()
    본문 = html.split("async function handlePayReturn()")[1].split("\n}")[0]
    assert "if (state.user) {" in 본문
    assert "stashCredit(r.amount, r.결제)" in 본문
    assert "function stashCredit(금액, 결제)" in html
    assert "async function applyPendingCredit()" in html
    # 프로필이 정해지는 모든 길에서 확인해야 한다
    적용 = html.split("function applyProfile(saved)")[1].split("\n}")[0]
    assert "applyPendingCredit" in 적용
    # 한 번 반영하면 지운다 (두 번 충전되지 않게)
    보관 = html.split("async function applyPendingCredit()")[1].split("\n}")[0]
    assert "removeItem(PENDING_CREDIT)" in 보관


def test_돌아온_뒤_주소창을_치운다():
    """?pay=ok 가 남으면 새로고침할 때마다 또 확인하러 간다."""
    html = _index()
    본문 = html.split("async function handlePayReturn()")[1].split("\n}")[0]
    assert "history.replaceState" in 본문


def test_시작하면_결제_수단을_불러온다():
    html = _index()
    본문 = html.split("async function openPaySheet()")[1].split("\n}")[0]
    assert "API.payMethods()" in 본문
    assert "catch" in 본문                      # 못 불러와도 창은 떠야 한다
    시작 = html.split("(async function init()")[1]
    assert "await handlePayReturn();" in 시작


# ---------- K2. 그날의 몸 상태 (운동 시간·휴식·키·몸무게·인바디) ----------

def test_그날_몸_상태를_함께_받는다():
    html = _index()
    assert 'id="logSummary"' in html
    assert "const LOG_SUMMARY = [" in html
    표 = html.split("const LOG_SUMMARY = [")[1].split("];")[0]
    for k in ("운동시간", "휴식시간", "키", "몸무게", "체지방률", "골격근량"):
        assert f"key: '{k}'" in 표, k
    # 인바디에서 오는 값은 그렇게 표시한다
    assert 표.count("인바디: true") == 2


def test_말도_안_되는_값은_버린다():
    """키 3cm, 몸무게 9999kg 같은 오타를 그대로 저장하면 분석이 망가진다."""
    html = _index()
    표 = html.split("const LOG_SUMMARY = [")[1].split("];")[0]
    assert "max: 250" in 표 and "min: 80" in 표          # 키
    assert "max: 300" in 표 and "min: 20" in 표          # 몸무게
    본문 = html.split("function collectLogSummary()")[1].split("\n}")[0]
    assert "v < (f.min ?? 0) || v > f.max" in 본문
    assert "if (v <= 0) return;" in 본문


def test_몸_상태만_적어도_저장된다():
    html = _index()
    본문 = html.split("function paintLogSaveBtn()")[1].split("\n}")[0]
    assert "collectLogSummary()" in 본문
    assert "btn.disabled = !n && !m;" in 본문
    저장 = html.split("async function saveDailyLog()")[1].split("\n}")[0]
    assert "if (!items.length && !Object.keys(요약).length) return;" in 저장
    assert "state.workoutLog.push({ date: 날, items, 요약 });" in 저장


def test_오늘_잰_키_몸무게만_프로필에_반영한다():
    """지난 날짜를 고칠 때 그때 값으로 지금 프로필을 덮으면 안 된다."""
    html = _index()
    저장 = html.split("async function saveDailyLog()")[1].split("\n}")[0]
    assert "if (날 === todayIso()) {" in 저장
    assert "state.height = 요약.키" in 저장
    assert "state.weight = 요약.몸무게" in 저장


def test_몸_상태만_적은_날은_운동한_날로_세지_않는다():
    """연속 일수·완료 루틴 수가 부풀면 안 된다."""
    html = _index()
    본문 = html.split("function allRoutineLog()")[1].split("\n}")[0]
    assert "(w.items || []).length" in 본문
    assert "요약" not in 본문


def test_몸_상태도_자세히_보기에_나온다():
    html = _index()
    assert "function summaryDetailHtml(요약)" in html
    본문 = html.split("function manualDetailHtml(w)")[1].split("\n}")[0]
    assert "summaryDetailHtml(w.요약)" in 본문
    상세 = html.split("function summaryDetailHtml(요약)")[1].split("\n}")[0]
    assert "요약[f.key] != null" in 상세          # 적은 것만 보여 준다


def test_몸_상태만_적은_날도_목록에_나온다():
    html = _index()
    본문 = html.split("function renderManualRecords()")[1].split("\n}")[0]
    assert "Object.keys(w.요약 || {}).length" in 본문
    이름 = html.split("function manualLogName(w)")[1].split("\n}")[0]
    assert "몸 상태 기록" in 이름


# ---------- K3. 선결제 할인 · 결제 내역 접기 ----------

def test_선결제_할인표가_서버_표와_같다():
    """화면 사본이 서버와 어긋나면 표시 금액과 청구 금액이 달라진다."""
    html = _index()
    표 = html.split("const PAY_PACKS = [")[1].split("];")[0]
    for 이용권, 결제, 할인 in [(100, 100, 0), (1000, 700, 30), (2000, 1300, 35),
                            (3000, 1800, 40), (5000, 2500, 50)]:
        assert f"이용권: {이용권}," in 표, 이용권
        assert f"결제: {결제}," in 표, 결제
        assert f"할인: {할인}" in 표, 할인
    # 서버가 준 값을 먼저 쓴다
    본문 = html.split("function payPacks()")[1].split("\n}")[0]
    assert "payInfo?.packs" in 본문


def test_할인율과_원래_금액을_보여준다():
    html = _index()
    본문 = html.split("function payAmountHtml()")[1].split("\n}")[0]
    assert "% 할인" in 본문
    assert 'class="was"' in 본문                 # 취소선 원가
    assert "won(p.결제)" in 본문                  # 실제로 내는 돈이 크게
    assert "won(p.이용권)" in 본문                # 앱에서 쓰는 금액
    css = html.split(".pay-pick .was{")[1].split("}")[0]
    assert "line-through" in css


def test_1회만_결제는_따로_적는다():
    html = _index()
    본문 = html.split("function payAmountHtml()")[1].split("\n}")[0]
    assert "1회만 결제" in 본문
    assert "p.이용권 === AI_PRICE" in 본문


def test_결제_버튼에_실제_낼_금액이_적힌다():
    html = _index()
    본문 = html.split("function payWayHtml()")[1].split("function pickPay(v)")[0]
    assert "won(팩.결제)" in 본문
    assert "won(payPick)" not in 본문           # 이용권 액면을 청구액처럼 쓰면 안 된다


def test_프로필_문구가_선결제로_바뀌었다():
    html = _index()
    assert "AI 추천 선결제" in html
    assert "선결제하기" in html
    assert "AI 추천 이용권" not in html


def test_결제_내역은_접었다_편다():
    html = _index()
    assert 'id="creditLogBtn"' in html
    assert "결제 내역 조회" in html
    assert 'id="creditLog" hidden' in html      # 처음엔 접혀 있다
    본문 = html.split("function toggleCreditLog()")[1].split("\n}")[0]
    assert "box.hidden = !펼침" in 본문
    assert "aria-expanded" in 본문


def test_내역에_실제로_낸_돈도_남긴다():
    """이용권 3,000원을 1,800원에 샀다는 걸 나중에도 알아야 한다."""
    html = _index()
    본문 = html.split("async function addCredit(금액, 결제)")[1].split("\n}")[0]
    assert "결제: 결제 ?? 금액" in 본문
    내역 = html.split("function renderCredit()")[1].split("\n}")[0]
    assert "e.결제 != null && e.결제 < e.금액" in 내역


# ---------- K1. 운동을 기록한 날짜에 체력나이도 저장 ----------

def test_기록한_날마다_체력나이를_저장한다():
    html = _index()
    assert "async function refreshLogAges(" in html
    본문 = html.split("async function refreshLogAges(")[1].split("\n}")[0]
    assert "API.activityAgeDays(bodies)" in 본문      # 날마다 부르지 않고 한 번에
    assert "w.체력나이 = {" in 본문
    저장 = html.split("async function saveDailyLog()")[1].split("\n}")[0]
    assert "refreshLogAges({ 전부: true })" in 저장


def test_그날까지의_측정만_기준으로_쓴다():
    """9월 5일 기록에 9월 20일 측정을 쓰면 미래를 갖다 쓰는 셈이다."""
    html = _index()
    본문 = html.split("function measureAtOrBefore(날)")[1].split("\n}")[0]
    assert "m.date <= 날" in 본문


def test_그날까지의_운동만_센다():
    html = _index()
    본문 = html.split("function activityCounts(끝날)")[1].split("\n}")[0]
    assert "w.date < 시작 || w.date > 끝" in 본문     # 창 밖과 미래를 뺀다
    assert "끝날 || todayIso()" in 본문               # 안 주면 오늘까지 (I3 그대로)


def test_그날_잰_몸_상태를_함께_보낸다():
    html = _index()
    본문 = html.split("function activityBodyFor(w)")[1].split("\n}")[0]
    for k in ("키:", "몸무게:", "체지방률:", "sex:"):
        assert k in 본문, k
    assert "요약.몸무게" in 본문


def test_기준이_없으면_만들지_않는다():
    """측정 전에 적은 날은 비교할 기준이 없다."""
    html = _index()
    본문 = html.split("function activityBodyFor(w)")[1].split("\n}")[0]
    assert "if (!기준?.항목별 || !state.ageGbn) return null;" in 본문


def test_예전_기록은_한_번에_채운다():
    html = _index()
    assert "async function backfillLogAges()" in html
    본문 = html.split("async function backfillLogAges()")[1].split("\n}")[0]
    assert "!w.체력나이" in 본문                       # 빈 날만
    assert "saveProfile()" in 본문                      # 채웠으면 저장한다


def test_지우면_뒤_날들도_다시_센다():
    """하루가 빠지면 그 뒤 날들의 28일 창이 달라진다."""
    html = _index()
    본문 = html.split("async function deleteCalDayLog()")[1].split("\n}")[0]
    assert "refreshLogAges({ 전부: true })" in 본문


def test_그날_체력나이를_상세에_보여준다():
    html = _index()
    assert "function dayAgeHtml(w)" in html
    본문 = html.split("function dayAgeHtml(w)")[1].split("\n}")[0]
    assert "체력나이" in 본문
    assert "측정 ${Math.round(a.기준나이)}세에서" in 본문   # 측정값과 비교해서 보여 준다
    assert "체성분은 그날 잰 값" in 본문
    상세 = html.split("function manualDetailHtml(w)")[1].split("\n}")[0]
    assert "dayAgeHtml(w)" in 상세


def test_서버가_실패해도_있던_값을_지우지_않는다():
    html = _index()
    본문 = html.split("async function refreshLogAges(")[1].split("\n}")[0]
    assert "catch" in 본문
    assert "있던 값을 그대로 둔다" in 본문


# ---------- 기록 삭제 뒷정리 ----------

def test_삭제_버튼이_부르는_함수가_실제로_있다():
    """#85 는 버튼만 만들고 함수를 안 만들어서, 누르면 ReferenceError 가 났다.

    onclick 에 적힌 이름은 반드시 정의돼 있어야 한다. 같은 실수를 다음에도 잡는다.
    """
    import re as _re
    html = _index()
    이름들 = set(_re.findall(r'onclick="([A-Za-z_$][\w$]*)\(', html))
    assert 이름들, "onclick 을 하나도 못 찾았다 — 정규식을 확인할 것"
    for f in sorted(이름들):
        assert f"function {f}(" in html, f"onclick 에 있는 {f} 가 정의돼 있지 않다"


def test_삭제_함수가_중복_정의되지_않는다():
    """#85 에서 deleteSelectedMeasures 가 두 번 선언돼 앞엣것이 죽은 코드가 됐다."""
    html = _index()
    for f in ("deleteSelectedMeasures", "deleteSelectedManual",
              "pickManual", "paintManualDeleteBtn", "renderManualRecords"):
        assert html.count(f"function {f}(") == 1, f


def test_직접기록을_지우면_날짜별_체력나이를_다시_센다():
    """하루가 빠지면 그 뒤 날들의 28일 창이 달라진다 (K1).

    달력의 deleteCalDayLog 에는 있는 처리가 기록 화면 쪽에는 빠져 있었다.
    """
    html = _index()
    for 함수 in ("async function deleteSelectedManual()", "async function deleteCalDayLog()"):
        본문 = html.split(함수)[1].split("\n}")[0]
        assert "refreshLogAges({ 전부: true })" in 본문, 함수
        assert "refreshActivityAge()" in 본문, 함수


# ---------- L. 앱 내 아이디 · 상호 친구 ----------

def test_커뮤니티에_친구_탭이_있다():
    html = _index()
    assert 'data-c="friend"' in html
    assert 'id="commFriend"' in html
    본문 = html.split("function commTab(t)")[1].split("\n}")[0]
    assert "$('commFriend').hidden = t !== 'friend'" in 본문
    assert "loadFriends()" in 본문


def test_내_아이디를_보여준다():
    html = _index()
    assert 'id="myHandle"' in html
    본문 = html.split("async function loadFriends()")[1].split("\n}")[0]
    assert "API.commMyHandle()" in 본문


def test_친구는_아이디로만_찾는다():
    """이메일로 찾게 두면 이메일이 곧 검색키가 된다(가입 여부가 새어 나간다)."""
    html = _index()
    본문 = html.split("async function findFriend()")[1].split("\n}")[0]
    assert "API.commFindUser(" in 본문
    assert "email" not in 본문.lower()
    assert 'id="friendQuery"' in html


def test_친구_카드에_닉네임과_아이디만_쓴다():
    """서로의 프로필은 볼 수 없다 — 체력나이나 기록이 새면 안 된다."""
    html = _index()
    본문 = html.split("function friendGroup(제목, 목록, 버튼)")[1].split("\n}")[0]
    assert "u['닉네임']" in 본문 and "u['아이디']" in 본문
    for 금지 in ("체력나이", "항목별", "measureLog", "email"):
        assert 금지 not in 본문, 금지


def test_세_가지_상태를_나눠_보여준다():
    html = _index()
    본문 = html.split("async function loadFriends()")[1].split("\n}")[0]
    for k in ("받은신청", "친구", "보낸신청"):
        assert f"f['{k}']" in 본문, k


def test_아이디를_그대로_넣지_않고_이스케이프한다():
    """닉네임과 아이디는 남이 정한 값이다."""
    html = _index()
    본문 = html.split("function friendGroup(제목, 목록, 버튼)")[1].split("\n}")[0]
    assert "esc(u['닉네임'])" in 본문 and "esc(u['아이디'])" in 본문
    찾기 = html.split("async function findFriend()")[1].split("\n}")[0]
    assert "esc(u['닉네임'])" in 찾기 and "esc(u['아이디'])" in 찾기

