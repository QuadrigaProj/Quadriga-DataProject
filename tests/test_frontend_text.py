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


_ROOT = Path(__file__).resolve().parents[1]


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
    "또래 중앙값보다 <span class=\"peer-emph\">${n}세 높게</span> 나왔어요.",   # A4
    "또래 중앙값보다 <span class=\"peer-emph\">${n}세 낮게</span> 나왔어요.",   # A4
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


# ---------- G1 점검기록 ----------

def test_점검기록에는_삭제가_없다():
    """점검 기록은 재측정과 운동 기록에 딸린 것이다. 원본을 그대로 두고
    이 줄만 지우면 두 목록이 어긋난다."""
    html = _index()
    for 없어야 in ("recDeleteBtn", "deleteSelectedMeasures", "measurePicked",
                 "pickMeasure", "paintMeasureDeleteBtn"):
        assert 없어야 not in html, 없어야
    본문 = html.split("function renderMeasureRecords()")[1].split("\n}")[0]
    assert "checkbox" not in 본문
    assert "점검 기록은 여기서 지우지 않아요" in html


def test_점검기록은_measureLog를_보여준다():
    """달력·변화추이와 같은 배열을 읽어야 결과가 함께 반영된다."""
    html = _index()
    body = html.split("function measureRows()")[1].split("\n}")[0]
    assert "state.measureLog" in body
    # 서버 스냅샷 목록을 쓰던 옛 경로는 사라졌다
    assert "const rows = (r.기록 || []).filter" not in html


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


def test_안내_모달은_닫을_수_있다():
    html = _index()
    assert 'id="noticeModal"' in html
    assert 'onclick="closeNoticeModal()"' in html


def test_채팅방_생성은_플러스_버튼으로_연다():
    html = _index()
    assert 'onclick="openRoomComposer()"' in html
    assert 'id="roomComposer"' in html


def test_게시글_작성란은_플러스_버튼으로_폈다_접는다():
    """모달 → 늘 펼쳐진 하단 입력란 → 지금은 ＋ 로 펴는 하단 입력란.

    늘 펼쳐 두니 좁은 화면에서 피드를 가려서, 머리의 ＋ 로 펴게 되돌렸다.
    모달로는 안 돌아간다 — 접었다 펴는 자리는 그대로 피드 하단이다."""
    html = _index()
    assert 'id="postComposer"' not in html          # 모달은 없앤 그대로
    머리 = html.split('id="commFeed"')[1].split('id="feedList"')[0]
    assert 'id="postAddBtn"' in 머리
    assert 'onclick="togglePostComposer()"' in 머리
    본문 = html.split('id="commFeed"')[1].split('id="commFriend"')[0]
    assert 'id="postComposeBar" class="post-compose-bar" hidden' in 본문
    assert '<input id="postBody" type="text"' in 본문
    css = html.split(".post-compose-bar{")[1].split("}")[0]
    assert "position:sticky" in css and "bottom:0" in css
    assert "position:fixed" not in css   # 이 저장소는 position:fixed 를 금지한다


def test_게시_버튼은_글자_대신_아이콘이다():
    """게시 버튼이 자리를 많이 먹어서 입력란이 짧아 보였다."""
    html = _index()
    본문 = html.split('id="postComposeBar"')[1].split("</div>")[0]
    assert 'class="post-send"' in 본문
    assert "<svg" in 본문                              # 글자가 아니라 아이콘
    assert ">게시</button>" not in 본문
    assert 'aria-label="게시"' in 본문                 # 아이콘만 있어도 읽히게
    css = html.split(".post-send{")[1].split("}")[0]
    assert "flex-shrink:0" in css                      # 입력란이 남는 자리를 갖는다
    입력 = html.split(".post-compose-bar input[type=text]{")[1].split("}")[0]
    assert "flex:1" in 입력


def test_작성란을_펴면_입력칸에_바로_쓸_수_있다():
    html = _index()
    본문 = html.split("function togglePostComposer(열기)")[1].split("\n}")[0]
    assert "$('postBody').focus()" in 본문
    assert "aria-expanded" in 본문                     # 접힘/펼침을 읽어 줄 수 있게
    assert "$('postPreview').hidden" in 본문           # 미리보기도 같이 접힌다


def test_게시글을_누르면_댓글창이_열린다():
    """본문 클릭도 '💬 댓글' 버튼과 같은 곳(토글)으로 이동한다 — 별도 상세 화면은 안 만든다."""
    html = _index()
    본문 = html.split("function postCard(p){")[1].split("\n}")[0]
    assert 'class="post-open" onclick="toggleComments(${p.id})"' in 본문
    # 미디어(사진·동영상) 클릭은 재생/확대만 하고 댓글창을 열면 안 된다
    assert "post-media\" onclick=\"event.stopPropagation()\"" in 본문


def test_게시글_본문이_댓글보다_크고_굵게_보인다():
    """예전엔 14.5px 대 13px 로 거의 안 갈렸다 — 헷갈린다는 피드백으로 벌렸다."""
    html = _index()
    post_css = html.split(".post-body{")[1].split("}")[0]
    comment_css = html.split(".comment{")[1].split("}")[0]
    assert "font-weight:600" in post_css
    post_size = float(post_css.split("font-size:")[1].split("px")[0])
    comment_size = float(comment_css.split("font-size:")[1].split("px")[0])
    assert post_size - comment_size >= 2.5


def test_채팅방_목록에서_내_채팅만_볼_수_있다():
    html = _index()
    assert 'id="roomFilter"' in html
    assert "onclick=\"setRoomFilter('all')\">전체</button>" in html
    assert "onclick=\"setRoomFilter('mine')\">내 채팅</button>" in html
    본문 = html.split("function renderRoomList(){")[1].split("\n}")[0]
    assert "const 내채팅 = COMM.roomFilter === 'mine';" in 본문
    assert "내채팅 ? rm['참여중'] : !rm['참여중']" in 본문


def test_방장만_단체_채팅방을_폭파할_수_있다():
    """개인 채팅(1:1)은 대상이 아니다 — 상대가 있는 대화를 혼자 없앨 수는 없다."""
    html = _index()
    본문 = html.split("function renderRoomList(){")[1].split("\n}")[0]
    assert "rm['방장'] && rm['종류'] !== 'direct'" in 본문
    assert "API.commRoomDelete" in html.split("async function destroyRoom(id){")[1].split("\n}")[0]


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
    assert "closest('.rec-item, .post-record')" in 본문
    assert "querySelector('.rec-detail')" in 본문
    assert "nextElementSibling" not in 본문


def test_세_목록_모두_자세히_보기가_있다():
    html = _index()
    루틴 = html.split("$('recList').innerHTML")[1].split("renderMeasureRecords()")[0]
    assert "moreToggle(routineDetailHtml(e))" in 루틴
    직접 = html.split("$('recManual').innerHTML")[1].split("\n}")[0]
    assert "moreToggle(manualDetailHtml(w))" in 직접
    점검 = html.split("$('recMeasures').innerHTML")[1].split(".join('')")[0]
    assert "measureDetailHtml(r)" in 점검
    assert "dayAgeHtml(r.date)" in 점검                 # 운동에서 뽑은 줄도 펼쳐진다


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


def test_점검_기록에는_고르는_자리가_없다():
    """지우기가 없어졌으니 체크박스도 label 도 없다 — 줄 모양이 하나다."""
    html = _index()
    점검 = html.split("$('recMeasures').innerHTML")[1].split(".join('')")[0]
    assert '<div class="rec-item">' in 점검
    assert "<label" not in 점검
    assert "rec-pick" not in 점검


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



def test_기록한_날마다_체력나이를_저장한다():
    html = _index()
    assert "async function refreshLogAges(" in html
    본문 = html.split("async function refreshLogAges(")[1].split("\n}")[0]
    assert "API.activityAgeDays(bodies)" in 본문      # 날마다 부르지 않고 한 번에
    assert "state.dayAges[r.date] = {" in 본문         # 날짜별 보관함에 넣는다
    assert "w.체력나이 = state.dayAges[w.date]" in 본문  # 직접 적은 줄에도 붙여 둔다
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
    assert "날 < 시작 || 날 > 끝" in 본문             # 창 밖과 미래를 뺀다
    assert "끝날 || todayIso()" in 본문               # 안 주면 오늘까지 (I3 그대로)


def test_그날_잰_몸_상태를_함께_보낸다():
    html = _index()
    본문 = html.split("function activityBodyFor(날)")[1].split("\n}")[0]
    for k in ("키:", "몸무게:", "체지방률:", "sex:"):
        assert k in 본문, k
    assert "요약.몸무게" in 본문
    # 루틴만 끝낸 날에는 직접 적은 줄이 없다 — 날짜로 찾아온다 (규칙 3)
    assert "logAt(날)?.요약" in 본문


def test_한_번도_안_쟀으면_만들지_않는다():
    """잰 적이 아예 없으면 비교할 기준 자체가 없다 — 값을 지어내지 않는다."""
    html = _index()
    본문 = html.split("function activityBodyFor(날)")[1].split("\n}")[0]
    assert "if (!기준?.항목별 || !state.ageGbn) return null;" in 본문


def test_그날_전에_잰_적이_없으면_뒤_측정을_거슬러_쓴다():
    """기록이 있는 날은 무조건 체력나이를 남긴다 (규칙 2).

    되도록 그날까지의 측정을 쓰지만, 그전에 잰 적이 아예 없으면
    가장 이른 뒤 측정을 끌어다 쓴다. 대신 추정이라고 화면에 밝힌다."""
    html = _index()
    본문 = html.split("function measureAtOrBefore(날)")[1].split("\n}")[0]
    assert "const 이전 = list.filter(m => m.date <= 날);" in 본문   # 먼저 그날까지
    assert "if (list.length) return list[0];" in 본문              # 없으면 가장 이른 것
    산출 = html.split("async function refreshLogAges(")[1].split("\n}")[0]
    assert "소급: !!(기준 && 기준.date && 기준.date > r.date)" in 산출
    # 화면에는 '거슬러 쓴 추정' 이라고 적지 않는다 — 그래프의 속 빈 점과
    # 안내 문구가 이미 추정치라고 말한다. 값에는 그 사실을 남겨 둔다.
    상세 = html.split("function dayAgeHtml(날)")[1].split("\n}")[0]
    assert "거슬러 쓴 추정" not in 상세


def test_예전_기록은_한_번에_채운다():
    html = _index()
    assert "async function backfillLogAges()" in html
    본문 = html.split("async function backfillLogAges()")[1].split("\n}")[0]
    assert "workoutDates().filter(d => !dayAge(d))" in 본문   # 빈 날만
    assert "saveProfile()" in 본문                             # 채웠으면 저장한다


def test_지우면_뒤_날들도_다시_센다():
    """하루가 빠지면 그 뒤 날들의 28일 창이 달라진다."""
    html = _index()
    본문 = html.split("async function deleteCalDayLog()")[1].split("\n}")[0]
    assert "refreshLogAges({ 전부: true })" in 본문


def test_그날_체력나이를_상세에_보여준다():
    html = _index()
    assert "function dayAgeHtml(날)" in html
    본문 = html.split("function dayAgeHtml(날)")[1].split("\n}")[0]
    assert "체력나이" in 본문
    assert "측정 ${Math.round(a.기준나이)}세에서" in 본문   # 측정값과 비교해서 보여 준다
    assert "체성분은 그날 잰 값" in 본문
    상세 = html.split("function manualDetailHtml(w)")[1].split("\n}")[0]
    assert "dayAgeHtml(w.date)" in 상세


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
    for f in ("deleteSelectedManual",
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


# ---------- L1·L2. 개인 채팅 생성 경로 · 방 만들기 규칙 ----------

def test_방_만들기에_개인채팅_선택지가_없다():
    """개인 채팅은 사용자가 만들지 않는다 — 상대 프로필에서 열린다."""
    html = _index()
    assert 'id="roomType"' not in html
    assert 'id="roomMemberEmail"' not in html
    assert "단체 채팅방 만들기" in html
    assert "개인 채팅은 상대 프로필에서" in html


def test_비공개_방_비밀번호는_숫자만_받는다():
    html = _index()
    assert "const ROOM_PIN_RE = /^[0-9]{4,12}$/;" in html      # 서버와 같은 규칙
    비번칸 = html.split('id="roomPassword"')[1].split(">")[0]
    assert 'inputmode="numeric"' in 비번칸
    assert 'maxlength="12"' in 비번칸
    본문 = html.split("async function createRoom()")[1].split("\n}")[0]
    assert "ROOM_PIN_RE.test(password)" in 본문
    assert "room_type" not in 본문 and "member_email" not in 본문


def test_공개_비공개만_고른다():
    html = _index()
    본문 = html.split("function syncRoomFields()")[1].split("\n}")[0]
    assert "$('roomPrivacy').value !== 'private'" in 본문
    assert "roomType" not in 본문


def test_채팅_보내기로_개인방을_연다():
    html = _index()
    assert "async function openDirect(handle)" in html
    본문 = html.split("async function openDirect(handle)")[1].split("\n}")[0]
    assert "API.commDirect(handle)" in 본문
    assert "openRoom(r.room_id" in 본문
    assert "commTab('chat')" in 본문


def test_친구와_찾은_사람에게_채팅_버튼이_붙는다():
    html = _index()
    묶음 = html.split("function friendGroup(제목, 목록, 버튼)")[1].split("\n}")[0]
    assert "data-dm=" in 묶음
    assert "제목 === '친구'" in 묶음            # 친구에게만
    찾기 = html.split("async function findFriend()")[1].split("\n}")[0]
    assert "data-dm=" in 찾기
    assert "관계 === '나'" in 찾기               # 나 자신에게는 안 뜬다
    배선 = html.split("function wireFriendButtons()")[1].split("\n}")[0]
    assert "openDirect(b.dataset.dm)" in 배선


# ---------- L5·L6. 목록 버튼 · 멤버 관리 ----------

def test_모든_채팅방에_목록_버튼이_있다():
    """멤버면 방장이 아니어도 멤버를 보고 나갈 수 있어야 한다 — 개인 채팅방도 같다."""
    html = _index()
    assert 'id="chatMenuBtn"' in html
    assert 'onclick="openRoomMembers()"' in html
    본문 = html.split("async function openRoom(id, name)")[1].split("\n}")[0]
    assert "$('chatMenuBtn').hidden = false;" in 본문


def test_개인_채팅방에서는_초대칸을_가린다():
    """개인 채팅방에는 초대할 자리가 없다. 멤버 확인과 나가기만 남긴다."""
    html = _index()
    본문 = html.split("async function loadRoomMembers()")[1].split("\n}")[0]
    assert "MEMBERS['종류'] === 'direct'" in 본문
    assert "초대칸.hidden = 개인" in 본문
    assert "if (!개인) await renderInviteFriends();" in html


def test_멤버_창에_요청한_것들이_다_있다():
    html = _index()
    창 = html.split('id="roomMembers"')[1].split("</section>")[0]
    assert 'id="memberList"' in 창              # 멤버 확인
    assert 'id="memberFriends"' in 창           # 친구 초대
    assert 'id="inviteQuery"' in 창             # 아이디로 초대
    assert "leaveFromMembers()" in 창           # 나가기
    본문 = html.split("async function loadRoomMembers()")[1].split("\n}")[0]
    assert "멤버 ${MEMBERS['인원']}명" in 본문     # 상단에 인원수


def test_방장만_내보내기_버튼을_본다():
    html = _index()
    본문 = html.split("async function loadRoomMembers()")[1].split("\n}")[0]
    assert "방장 && !개인 && !u['나']" in 본문   # 개인 채팅방엔 내보낼 사람이 없다
    assert "data-kick=" in 본문
    assert "API.commRoomKick" in 본문


def test_내보내기와_나가기는_한_번_묻는다():
    html = _index()
    본문 = html.split("async function loadRoomMembers()")[1].split("\n}")[0]
    assert "confirm(" in 본문
    나가기 = html.split("async function leaveFromMembers()")[1].split("\n}")[0]
    assert "confirm(" in 나가기
    assert "API.commRoomLeave" in 나가기


def test_초대해_둔_사람은_초대_목록에서_뺀다():
    html = _index()
    친구 = html.split("async function renderInviteFriends()")[1].split("\n}")[0]
    assert "MEMBERS?.['초대중']" in 친구


def test_친구는_바로_초대하고_아니면_아이디로_초대한다():
    html = _index()
    친구 = html.split("async function renderInviteFriends()")[1].split("\n}")[0]
    assert "API.commFriends()" in 친구
    assert "이미.has(u['아이디'])" in 친구        # 이미 들어온 친구는 빼고
    assert "data-invite=" in 친구
    아이디 = html.split("async function inviteByHandle()")[1].split("\n}")[0]
    assert "API.commRoomInvite(COMM.room, h)" in 아이디


def test_멤버_창도_닉네임과_아이디만_그린다():
    html = _index()
    본문 = html.split("async function loadRoomMembers()")[1].split("\n}")[0]
    assert "esc(u['닉네임'])" in 본문 and "esc(u['아이디'])" in 본문
    for 금지 in ("체력나이", "email", "measureLog"):
        assert 금지 not in 본문, 금지


def test_방을_닫으면_멤버_창도_닫는다():
    html = _index()
    본문 = html.split("function closeRoom()")[1].split("\n}")[0]
    assert "closeRoomMembers()" in 본문


# ---------- 초대는 받은 사람이 수락해야 들어간다 ----------

def test_받은_초대_자리가_있다():
    html = _index()
    assert 'id="inviteBox"' in html
    assert 'id="inviteList"' in html
    assert "async function loadInvites()" in html
    본문 = html.split("async function loadInvites()")[1].split("\n}")[0]
    assert "API.commInvites()" in 본문
    # 채팅방 목록을 그릴 때마다 초대도 본다
    방목록 = html.split("async function loadRooms()")[1].split("\n}\n\n")[0]
    assert "loadInvites()" in 방목록


def test_비공개_방은_초대받아도_비밀번호를_묻는다():
    """초대가 비밀번호를 건너뛰면 비공개 방이 무너진다."""
    html = _index()
    본문 = html.split("async function acceptInvite(roomId, isPrivate, name)")[1].split("\n}")[0]
    assert "isPrivate" in 본문 and "prompt(" in 본문
    assert "if (isPrivate && !password) return;" in 본문
    assert "API.commInviteAccept(roomId, password)" in 본문


def test_초대_카드에_비밀번호가_필요한지_적는다():
    html = _index()
    본문 = html.split("async function loadInvites()")[1].split("\n}")[0]
    assert "비밀번호 필요" in 본문
    assert "data-accept=" in 본문 and "data-decline=" in 본문
    assert "API.commInviteDecline" in 본문


def test_방장_화면에_수락_대기가_보인다():
    html = _index()
    본문 = html.split("async function loadRoomMembers()")[1].split("\n}")[0]
    assert "수락 대기" in 본문
    assert "초대함 ${초대중.length}명" in 본문
    assert "data-uninvite=" in 본문               # 초대를 거둘 수 있다
    assert "API.commRoomInviteCancel" in 본문


def test_초대하면_바로_들어오지_않는다고_적는다():
    html = _index()
    창 = html.split('id="roomMembers"')[1].split("</section>")[0]
    assert "상대가 수락해야 들어와요" in 창


# ---------- 실결제: 잔액은 서버 원장이 기준 ----------

def test_잔액을_서버에서_읽는다():
    """브라우저에 두면 숫자만 바꿔 AI 추천을 공짜로 무제한 쓸 수 있다."""
    html = _index()
    assert "async function loadCredit()" in html
    본문 = html.split("async function loadCredit()")[1].split("\n}")[0]
    assert "API.credit()" in 본문
    assert "state.credit = c['잔액']" in 본문


def test_잔액을_스냅샷에_담지_않는다():
    """스냅샷은 브라우저가 보내는 값이다 — 거기 잔액이 있으면 조작된다."""
    html = _index()
    본문 = html.split("function snapshot()")[1].split("\n}")[0]
    assert "credit" not in 본문


def test_화면이_잔액을_더하거나_빼지_않는다():
    html = _index()
    충전 = html.split("async function addCredit()")[1].split("\n}")[0]
    assert "loadCredit()" in 충전
    assert "state.credit =" not in 충전
    # AI 추천 차감도 서버 응답을 그대로 쓴다
    추천 = html.split("async function renderRecommend()")[1].split("\nfunction paintRecommend")[0]
    assert "state.credit = r['잔액']" in 추천
    assert "- AI_PRICE" not in 추천


def test_카카오페이만_진짜_결제창으로_보낸다():
    html = _index()
    본문 = html.split("async function startPay()")[1].split("\n}")[0]
    assert "if (payWay === 'kakao')" in 본문
    assert "API.payReady({ amount: payPick })" in 본문
    assert "location.href = payRedirect(r)" in 본문   # 접속 환경에 맞는 주소를 고른다
    # 카드·계좌를 화면에서 모의로 올리면 그게 곧 무료 충전 통로가 된다
    assert "addCredit(팩" not in 본문
    assert "아직 카카오페이만 결제할 수 있어요" in 본문


def test_결제하고_돌아오면_서버_잔액을_다시_읽는다():
    html = _index()
    본문 = html.split("async function handlePayReturn()")[1].split("\n}")[0]
    assert "API.payResult(order)" in 본문
    assert "await addCredit();" in 본문          # 인자 없이 — 서버가 이미 올렸다
    assert "stashCredit" not in 본문


# ---------- 게이지 오른쪽 끝 = 처음 기록한 체력나이 ----------

def test_게이지_기준은_처음_기록한_체력나이다():
    """실제 나이로 두면 눈금이 해마다 움직여, 좋아졌는지가 눈금 이동에 섞인다."""
    html = _index()
    assert "function baselineAge()" in html
    본문 = html.split("function baselineAge()")[1].split("\n}")[0]
    assert "state.measureLog" in 본문
    assert "a.date < b.date ? -1 : 1" in 본문        # 가장 이른 것
    assert "state.first?.결과?.체력나이" in 본문       # 이력이 없으면 첫 점검
    assert "return state.age;" in 본문                # 잰 적 없으면 실제 나이


def test_게이지가_기준나이를_넘긴다():
    html = _index()
    본문 = html.split("function gaugeData()")[1].split("\n}")[0]
    assert "baseAge: baselineAge()" in 본문
    assert "age: state.age" not in 본문


def test_게이지_모듈이_기준나이로_비율을_낸다():
    js = (_ROOT / "frontend" / "js" / "gauge.js").read_text(encoding="utf-8")
    본문 = js.split("function ratios(")[1].split("\n  }")[0]
    assert "baseAge" in 본문
    assert "targetAge / baseAge" in 본문
    assert "fitnessAge / baseAge" in 본문
    # 문서도 같이 고쳐야 다음 사람이 헷갈리지 않는다
    assert "처음 기록한 체력나이" in js


def test_범례가_오른쪽_끝을_처음이라고_적는다():
    html = _index()
    assert ">처음 <b id=\"gaugeReal\">" in html
    본문 = html.split("function paintGauges(")[1].split("\n}")[0]
    assert "baselineAge()" in 본문
    # 목표도 체력나이다 — '만' 을 붙이지 않는다
    assert "`만 ${targetAge()}세`" not in 본문


# ---------- 실제 나이 눈금 ----------

def test_실제_나이를_검은_눈금으로_그린다():
    js = (_ROOT / "frontend" / "js" / "gauge.js").read_text(encoding="utf-8")
    assert "function tickPath(tick)" in js
    본문 = js.split("function tickPath(tick)")[1].split("\n  }")[0]
    assert "<line" in 본문
    assert "TICK" in 본문
    # 링을 가로지른다 (안쪽 반지름 → 바깥쪽 반지름)
    assert "R - SW / 2" in 본문 and "R + SW / 2" in 본문


def test_눈금_밖이면_선을_그리지_않는다():
    """눈금이 닿지 않는 자리에 억지로 붙이면 거짓말이 된다."""
    js = (_ROOT / "frontend" / "js" / "gauge.js").read_text(encoding="utf-8")
    본문 = js.split("function tickPath(tick)")[1].split("\n  }")[0]
    assert "if (!(tick > 0 && tick <= 1)) return '';" in 본문


def test_눈금은_실제나이를_기준나이로_나눈다():
    js = (_ROOT / "frontend" / "js" / "gauge.js").read_text(encoding="utf-8")
    본문 = js.split("function ratios(")[1].split("\n  }")[0]
    assert "realAge / baseAge" in 본문
    html = _index()
    게이지 = html.split("function gaugeData()")[1].split("\n}")[0]
    assert "realAge: state.age" in 게이지


def test_눈금은_차오르는_애니메이션에_안_섞인다():
    """눈금은 고정된 자리다 — 같이 움직이면 나이가 변하는 것처럼 보인다."""
    js = (_ROOT / "frontend" / "js" / "gauge.js").read_text(encoding="utf-8")
    본문 = js.split("function render(")[1].split("\n  }")[0]
    assert "svg(green * t, dot * t, id, tick)" in 본문      # tick 에는 t 를 안 곱한다


def test_범례에_실제_나이도_있다():
    html = _index()
    assert 'id="gaugeAgeRow"' in html and 'id="gaugeAge"' in html
    assert "sw-tick" in html
    본문 = html.split("function paintGauges(")[1].split("\n}")[0]
    assert "state.age <= 기준" in 본문                      # 눈금 안에 드는지
    assert "off-scale" in 본문


def test_범례_세_칸이_글자로_접히지_않는다():
    """375px 에서 '목 표 33 세' 처럼 글자 단위로 접혔다."""
    html = _index()
    css = html.split(".gauge-legend{")[1].split("}")[0]
    assert "flex-direction:column" in css
    assert "white-space:nowrap" in html.split(".gauge-legend > div{")[1].split("}")[0]


def test_프로필_안내가_게이지_설명과_맞는다():
    """눈금 뜻을 바꾸면 이 안내도 같이 고쳐야 한다 — 안 고치면 거짓말이 된다."""
    html = _index()
    안내 = html.split('class="edit-note"')[1].split("</div>")[0]
    assert "오른쪽 끝은 처음 기록한 체력나이" in 안내
    assert "검은 눈금</b>은 실제 나이" in 안내
    assert "오른쪽 끝은 실제 나이" not in 안내


def test_PC_에서는_QR_화면으로_보낸다():
    """카카오는 접속 환경별로 다른 주소를 준다. PC 주소가 QR 화면이다."""
    html = _index()
    assert "function payRedirect(r)" in html
    본문 = html.split("function payRedirect(r)")[1].split("\n}")[0]
    assert "navigator.userAgent" in 본문
    assert "r.redirect_pc" in 본문 and "r.redirect_mobile" in 본문
    시작 = html.split("async function startPay()")[1].split("\n}")[0]
    assert "payRedirect(r)" in 시작
    assert "location.href = r.redirect;" not in 시작


def test_id_가_중복되지_않는다():
    """#99 가 새 topbar 를 더하면서 옛 것을 안 지워 id 가 두 벌이 됐다.

    같은 id 가 둘이면 화면에는 버튼이 둘 보이는데 $() 는 앞엣것만 잡는다.
    눈으로 보기 전에는 테스트도 못 잡던 종류라 여기서 막는다.
    """
    import re as _re
    from collections import Counter
    html = _index()
    ids = _re.findall(r'\sid="([^"]+)"', html)
    겹침 = {k: v for k, v in Counter(ids).items() if v > 1}
    assert not 겹침, f"중복된 id: {겹침}"


def test_홈에_재측정_버튼이_하나뿐이다():
    html = _index()
    홈 = html.split('id="s3"')[1].split("</section>")[0]
    assert 홈.count('class="dday-pill"') == 1
    assert 홈.count('class="topbar"') == 1


# ---------- 글쓴이 프로필 · 채팅 요청 ----------

def test_게시글에_프로필이_함께_뜬다():
    html = _index()
    assert "function whoHtml(닉네임, 아이디)" in html
    본문 = html.split("function whoHtml(닉네임, 아이디)")[1].split("\n}")[0]
    assert "who-avatar" in 본문
    assert "openProfile(" in 본문
    assert "if (!아이디) return" in 본문          # 예전 글은 누를 수 없다
    피드 = html.split('class="post-top"')[1].split("</div>")[0]
    assert "whoHtml(p['작성자'], p['작성자아이디'])" in 피드


def test_프로필에_채팅과_친구_버튼이_있다():
    html = _index()
    본문 = html.split("async function openProfile(handle)")[1].split("\n}")[0]
    assert "data-p-chat=" in 본문 and "data-p-friend=" in 본문
    assert "API.commFindUser(handle)" in 본문
    # 서버가 내려준 상태로 버튼을 그린다 — 규칙이 화면에 흩어지지 않게
    assert "u['관계']" in 본문 and "u['채팅']" in 본문
    # 프로필에는 닉네임과 아이디뿐이다
    for 금지 in ("체력나이", "email", "measureLog"):
        assert 금지 not in 본문, 금지


def test_친구가_아니면_요청만_보낸다():
    html = _index()
    본문 = html.split("async function openDirect(handle)")[1].split("\n}")[0]
    assert "if (!r.room_id)" in 본문
    assert "채팅을 요청했어요" in 본문


def test_받은_채팅_요청_자리가_있다():
    html = _index()
    assert 'id="chatReqBox"' in html and 'id="chatReqList"' in html
    본문 = html.split("async function loadChatRequests()")[1].split("\n}")[0]
    assert "API.commChatRequests()" in 본문
    assert "data-creq-ok=" in 본문 and "data-creq-no=" in 본문
    방목록 = html.split("async function loadRooms()")[1].split("\n}\n\n")[0]
    assert "loadChatRequests()" in 방목록


def test_요청을_수락하면_방이_열린다():
    html = _index()
    본문 = html.split("async function acceptChat(handle)")[1].split("\n}")[0]
    assert "API.commChatAccept(handle)" in 본문
    assert "openRoom(r.room_id" in 본문


# ---------- 변화추이에 운동한 날 (M4) ----------

def test_그래프가_측정과_운동을_함께_쓴다():
    """측정만 그리면 매일 운동해도 그래프가 안 움직이는 것처럼 보인다."""
    html = _index()
    assert "function trendPoints()" in html
    본문 = html.split("function trendPoints()")[1].split("\n}")[0]
    assert "workoutDates()" in 본문      # 루틴만 끝낸 날도 들어온다 (규칙 3)
    assert "dayAge(d)" in 본문
    assert "measurePoints()" in 본문
    assert "'운동'" in 본문 and "'측정'" in 본문


def test_잰_날은_꽉_찬_점으로_그리되_값은_그날_최종값이다():
    """점 모양은 잰 날인지 아닌지를 말하고, 값은 화면마다 같아야 한다."""
    html = _index()
    본문 = html.split("function trendPoints()")[1].split("\n}")[0]
    운동자리 = 본문.index("출처: '운동'")
    측정자리 = 본문.index("measurePoints().forEach")
    assert 운동자리 < 측정자리        # 나중에 set 하는 쪽이 남는다
    assert "체력나이: dayFinalAge(p.date) ?? p.체력나이" in 본문


def test_하루에_보여_주는_체력나이는_하나다():
    """점검 기록과 직접 적은 운동에 같은 날 다른 숫자가 뜨면
    어느 게 맞는 값인지 알 수 없다."""
    html = _index()
    본문 = html.split("function dayFinalAge(날)")[1].split("\n}")[0]
    assert "dayAge(날)" in 본문                      # 운동까지 반영한 값이 먼저
    assert "state.measureLog" in 본문                # 없으면 잰 값

    점검 = html.split("function measureRows()")[1].split("\n}")[0]
    assert "체력나이: dayFinalAge(m.date) ?? m.체력나이" in 점검

    # 자리수도 맞춘다 — 29.7 을 한쪽은 30, 한쪽은 29.7 로 쓰면 달라 보인다
    목록 = html.split("$(\'recMeasures\').innerHTML")[1].split(".join(\'\')")[0]
    assert "Math.round(r.체력나이 * 10) / 10" in 목록


def test_체력나이가_없는_운동일은_안_찍는다():
    """측정 전에 적은 날은 기준이 없어 값이 없다. 0 으로 찍으면 거짓말이 된다."""
    html = _index()
    본문 = html.split("function trendPoints()")[1].split("\n}")[0]
    assert "a.값 == null" in 본문


def test_그래프가_trendPoints를_쓴다():
    html = _index()
    본문 = html.split("function renderTrend()")[1].split("\n\n  $('trendCount')")[0]
    assert "trendPoints().filter" in 본문
    assert "measurePoints().filter" not in 본문


def test_그래프가_빈_날을_채우고_다시_그린다():
    """예전에 적어 둔 날에는 체력나이가 없다. 채운 뒤 한 번 더 그린다."""
    html = _index()
    본문 = html.split("function renderTrend()")[1].split("\n}")[0]
    assert "backfillLogAges().then(ok => { if (ok) renderTrend(); })" in 본문


def test_추정치는_속_빈_점으로_그린다():
    """잰 값과 추정치를 같은 모양으로 그리면 둘을 구분할 수 없다."""
    html = _index()
    본문 = html.split("function trendSvg(pts)")[1].split("\n}")[0]
    assert "p.출처 === '운동'" in 본문
    assert "fill:var(--paper);stroke:var(--pine)" in 본문     # 속 빈 점
    assert "fill:var(--pine);stroke:var(--paper)" in 본문     # 꽉 찬 점


def test_추정치라고_문구에_적는다():
    html = _index()
    본문 = html.split("function renderTrend()")[1].split("\n}")[0]
    assert "속 빈 점" in 본문 and "추정치" in 본문


# ---------- 채팅방 목록 표기 ----------

def test_방_종류는_공개_여부만_적는다():
    """'비공개 단체 채팅' 은 좁은 목록에서 너무 길다."""
    html = _index()
    본문 = html.split("function renderRoomList()")[1].split("\n}")[0]
    assert "'비공개 단체 채팅'" not in 본문 and "'공개 단체 채팅'" not in 본문
    assert "rm['비공개'] ? '비공개' : '공개'" in 본문
    assert "'개인 채팅'" in 본문          # 개인 채팅은 그대로 구분해서 보여 준다


def test_내가_방장인_방은_이름_옆에_표시된다():
    html = _index()
    본문 = html.split("function renderRoomList()")[1].split("\n}")[0]
    assert "rc-host" in 본문
    assert 'aria-label="내가 만든 방"' in 본문
    assert "${privateMark}${hostMark}" in 본문     # 이름 옆에 붙는다
    # 개인 채팅에는 방장이 없다 — 먼저 말을 건 쪽일 뿐이라 표시할 뜻이 없다
    assert "(rm['방장'] && rm['종류'] !== 'direct')" in 본문


def test_방_카드가_좁아도_이름이_접히지_않는다():
    """방장이면 버튼이 셋이라, 이름 칸이 한 글자씩 세로로 접혔다."""
    html = _index()
    카드 = html.split(".room-card{")[1].split("}")[0]
    assert "flex-wrap:wrap" in 카드              # 버튼 줄이 아래로 내려간다
    정보 = html.split(".room-card .rc-info{")[1].split("}")[0]
    assert "min-width:0" in 정보
    버튼 = html.split(".room-actions{")[1].split("}")[0]
    assert "flex-shrink:0" not in 버튼           # 이름을 밀어내지 않는다
    assert 'class="rc-info"' in html


def test_두_목록은_겹치지_않는다():
    """같은 방이 '전체' 와 '내 채팅' 양쪽에 다 뜨면 어느 쪽을 봐야 할지 모른다."""
    html = _index()
    본문 = html.split("function renderRoomList()")[1].split("\n}")[0]
    assert "내채팅 ? rm['참여중'] : !rm['참여중']" in 본문
    # 빈 목록 문구도 각자 뜻에 맞게
    assert "아직 들어가 있는 채팅방이 없어요" in 본문
    assert "새로 들어갈 채팅방이 없어요" in 본문


# ---------- 기록 규칙 (2·3·4) ----------

def test_운동한_날에는_루틴만_한_날도_들어간다():
    """루틴만 하는 사람은 아무리 운동해도 그래프에 점이 안 찍혔다 (규칙 3)."""
    html = _index()
    본문 = html.split("function workoutDates()")[1].split("\n}")[0]
    assert "allRoutineLog()" in 본문          # 루틴을 끝낸 날
    assert "state.workoutLog" in 본문         # 직접 적은 날 (몸 상태만 적은 날 포함)
    assert "new Set()" in 본문                # 겹쳐도 한 번만


def test_기록이_지워진_날은_체력나이도_지운다():
    html = _index()
    본문 = html.split("async function refreshLogAges(")[1].split("\n}")[0]
    assert "delete state.dayAges[d]" in 본문


def test_루틴을_끝내도_그날_체력나이를_뽑는다():
    """저장만 하고 끝내면 루틴만 한 날은 영영 값이 없다 (규칙 2)."""
    html = _index()
    본문 = html.split("function logRoutineDone()")[1].split("\n}\n")[0]
    assert "refreshLogAges({ 전부: true })" in 본문
    assert "saveProfile()" in 본문


def test_날짜별_체력나이는_저장되고_돌아온다():
    html = _index()
    assert "dayAges: state.dayAges," in html                       # 스냅샷에 담는다
    assert "state.dayAges = (saved?.dayAges" in html               # 되돌린다
    assert html.count("state.dayAges = {};") >= 3                  # 초기화 자리마다


def test_점검_기록은_날짜당_한_줄이다():
    """같은 날 두 줄이면 어느 쪽이 지금 값인지 알 수 없다 (규칙 4)."""
    html = _index()
    본문 = html.split("function dedupeMeasureLog()")[1].split("\n}")[0]
    assert "byDate.set(m.date, m)" in 본문        # 나중 것이 이긴다
    보탬 = html.split("function appendMeasureLog()")[1].split("\n}")[0]
    assert "dedupeMeasureLog()" in 보탬           # 잴 때마다 정리한다
    assert "dedupeMeasureLog();" in html.split("state.dayAges = (saved?.dayAges")[1][:400]


def test_운동한_날은_점검_기록에도_뜬다():
    """'직접 적은 운동' 에는 있는데 '점검 기록' 에는 없는 날이 생기면 안 된다 (규칙 4)."""
    html = _index()
    본문 = html.split("function measureRows()")[1].split("\n}")[0]
    assert "workoutDates()" in 본문
    assert "출처: '운동'" in 본문
    assert "출처: '측정'" in 본문
    # 잰 값이 나중에 덮는다 — 실제로 잰 쪽이 이긴다
    assert 본문.index("출처: '운동'") < 본문.index("출처: '측정'")


def test_점검_기록은_어느_줄도_지울_수_없다():
    """그날 운동 기록이나 재측정 쪽에서만 바뀐다. 여기서 따로 지우면 어긋난다."""
    html = _index()
    점검 = html.split("$('recMeasures').innerHTML")[1].split(".join('')")[0]
    assert "checkbox" not in 점검
    assert "그날 운동 기록을 지우면 함께 사라집니다" in html


def test_끝낸_루틴도_운동한_날로_센다():
    """루틴만 하는 사람의 기록이 체력나이에 하나도 안 닿으면,
    운동해도 숫자가 안 움직인다 (규칙 2)."""
    html = _index()
    본문 = html.split("function activityCounts(끝날)")[1].split("\n}")[0]
    assert "allRoutineLog()" in 본문
    assert "if (e.직접) return;" in 본문                  # 직접 적은 건 두 번 세지 않는다
    assert "String(st.체력요인 || '').split('·')" in 본문   # '근력·협응력' 을 나눈다
    # 루틴 기록에 체력요인을 남겨야 셀 수 있다
    완료 = html.split("function logRoutineDone()")[1].split("\n}\n")[0]
    assert "체력요인: s.체력요인 || null" in 완료



def test_x축에_찍힌_날짜를_적는다():
    """점만 있고 며칠 기록인지 알 수 없으면 그래프를 읽을 수 없다."""
    html = _index()
    본문 = html.split("function trendSvg(pts)")[1].split("\nfunction ")[0]
    assert "const 날짜들 = 날짜자리();" in 본문
    assert "날짜들.map(p => tick(p) + dateLabel(p, 어느쪽(p)))" in 본문
    assert "pts.slice(1, -1).forEach" in 본문     # 가운데 점들도 후보다


def test_x축_날짜는_겹치면_건너뛴다():
    """글자가 겹치면 아예 못 읽는다. 처음과 끝은 반드시 남긴다."""
    html = _index()
    본문 = html.split("function trendSvg(pts)")[1].split("\nfunction ")[0]
    assert "if (왼 >= 오른끝) { 고른것.push(p); 오른끝 = 오; }" in 본문
    # anchor 마다 글자가 퍼지는 방향이 달라서 자리를 따로 잰다
    assert "if (anchor === 'start') return [cx, cx + w];" in 본문
    assert "if (anchor === 'end') return [cx - w, cx];" in 본문
    assert "고른것.push(b);" in 본문               # 끝은 늘 들어간다


def test_댓글_등록도_아이콘_버튼이다():
    """게시글 작성란과 같은 모양 — 입력칸이 넓고 버튼은 작은 아이콘."""
    html = _index()
    본문 = html.split('class="comment-row"')[1].split("</div>")[0]
    assert 'class="post-send sm"' in 본문
    assert "<svg" in 본문
    assert ">등록</button>" not in 본문
    assert 'aria-label="댓글 등록"' in 본문
    입력 = html.split(".comment-row input{")[1].split("}")[0]
    assert "flex:1" in 입력                     # 남는 자리는 입력칸이 가져간다
    assert "border-radius:999px" in 입력        # 작성란과 같은 알약 모양
    버튼 = html.split(".post-send.sm{")[1].split("}")[0]
    assert "32px" in 버튼                       # 게시 버튼(38px)보다 한 단계 작다


def test_이미_적은_날을_고치면_한_번_묻는다():
    """하루에 하나다. 덮어쓰면 되돌릴 수 없고 그날 체력나이도 다시 뽑힌다."""
    html = _index()
    본문 = html.split("async function saveDailyLog()")[1].split("\n}")[0]
    assert "이전 기록은 사라지고 저장되는 기록으로 바뀝니다. 괜찮으시겠습니까?" in 본문
    assert "적어둔게있다" in 본문
    # 아니라고 하면 아무것도 바뀌지 않는다 — 묻기가 먼저다
    assert "&& !confirm(" in 본문
    assert 본문.index("confirm(") < 본문.index("state.workoutLog.push")


# ---------- 내가 쓴 것 고치기·지우기, 채팅 이모지 ----------

def test_내_글_댓글_메시지에_수정과_삭제가_있다():
    html = _index()
    카드 = html.split("function postCard(p)")[1].split("\n}")[0]
    assert 'onclick="editPost(${p.id})"' in 카드
    assert 'onclick="removePost(${p.id})"' in 카드
    assert "p['내글']" in 카드                    # 남의 글에는 안 뜬다

    댓글 = html.split("async function toggleComments(id)")[1].split("\n}")[0]
    assert "editComment(${id}, ${c.id})" in 댓글
    assert "removeComment(${id}, ${c.id})" in 댓글
    assert "c['내글']" in 댓글

    메시지 = html.split("function chatMsgHtml(m)")[1].split("\n}")[0]
    assert "editMessage(${m.id})" in 메시지
    assert "removeMessage(${m.id})" in 메시지
    assert "m['내글']" in 메시지


def test_채팅_메시지에도_이모지를_단다():
    """상대 글에도 달 수 있어야 쓸 데가 있다 — 내글 조건을 걸지 않는다."""
    html = _index()
    본문 = html.split("function chatMsgHtml(m)")[1].split("\n}")[0]
    이모지줄 = [l for l in 본문.split("\n") if "reactBar(" in l][0]
    assert "reactBar('message', m.id, m['반응'])" in 이모지줄
    assert "내글" not in 이모지줄


def test_고친_글에는_표시가_남는다():
    html = _index()
    assert "function 수정됨(o)" in html
    본문 = html.split("function 수정됨(o)")[1].split("\n}")[0]
    assert "o['수정시각']" in 본문
    assert "수정됨" in 본문


def test_그_자리에서_고친다():
    """새 창을 열면 앞뒤 맥락이 사라진다. 저장이 실패하면 되돌린다."""
    html = _index()
    본문 = html.split("function openInlineEdit(대상, 원래글, 저장)")[1].split("\nasync function")[0]
    assert "class=\"edit-input\"" in 본문
    assert "되돌리기" in 본문
    assert "catch (e) { showToast(e.message); 되돌리기(); }" in 본문   # 쓴 글이 사라지지 않게
    assert "e.key === 'Escape'" in 본문


def test_지우기는_한_번_묻는다():
    html = _index()
    for 함수 in ("async function removeComment(pid, cid)", "async function removeMessage(id)"):
        본문 = html.split(함수)[1].split("\n}")[0]
        assert "confirm(" in 본문, 함수


def test_채팅은_목록을_통째로_다시_그린다():
    """고친 글·지운 글·이모지는 새 id 를 만들지 않는다.
    새 것만 이어 붙이면 화면이 영영 안 바뀐다."""
    html = _index()
    본문 = html.split("async function pollChat()")[1].split("\n}")[0]
    assert "API.commMessages(COMM.room)" in 본문      # after 를 주지 않는다
    assert "paintChat(" in 본문
    그리기 = html.split("function paintChat(list, { 강제 = false } = {})")[1].split("\n}")[0]
    assert "if (!강제 && sig === chatSig) return;" in 그리기   # 달라졌을 때만
    assert "맨아래였다" in 그리기                      # 읽는 중에 스크롤이 튀지 않게
    assert "적던것" in 그리기                          # 적다 만 댓글은 지킨다
    assert "lastMsgId" not in html                    # 이어 붙이던 자리는 사라졌다


# ---------- 기록 공유 ----------

def test_공유한_기록에_항목별_지표와_그날_운동이_담긴다():
    """나이 한 줄만으로는 무엇을 해서 그렇게 됐는지 알 수 없다."""
    html = _index()
    본문 = html.split("async function shareMyRecord()")[1].split("\n}")[0]
    assert "항목별: r?.['항목별'] || null" in 본문
    assert "오늘운동: todayMoves()" in 본문

    오늘 = html.split("function todayMoves()")[1].split("\n}")[0]
    assert "logAt(오늘)?.items" in 오늘          # 직접 적은 종목
    assert "state.routineLog" in 오늘            # 끝낸 루틴의 동작
    assert "목록.some(m => m.이름 === st.운동명)" in 오늘   # 같은 걸 두 번 적지 않는다


def test_공유한_기록은_다섯_줄까지만_늘어놓는다():
    """피드에서 글 하나가 화면을 다 차지하면 다른 글을 못 본다."""
    html = _index()
    assert "const SHARE_ROWS_INLINE = 5;" in html
    본문 = html.split("function recordHtml(rec)")[1].split("\n}")[0]
    assert "줄.length > SHARE_ROWS_INLINE ? moreToggle(표) : 표" in 본문
    assert "AXIS_ORDER" in 본문                   # 항목 차례는 앱 기준을 따른다
    # 카드를 누르면 댓글이 열린다. 안의 버튼이 그 동작까지 타면 안 된다
    assert 'onclick="event.stopPropagation()"' in 본문


def test_자세히_보기는_기록_카드_안에서도_열린다():
    html = _index()
    본문 = html.split("function toggleRecDetail(btn)")[1].split("\n}")[0]
    assert "btn.closest('.rec-item, .post-record')" in 본문


# ---------- 채팅방 목록 : 필터와 고정 ----------

def test_필터를_누르면_목록으로_돌아온다():
    """방을 열어 둔 채로 누르면 화면이 그대로여서, 두 버튼이 아무 일도
    안 하는 것처럼 보였다."""
    html = _index()
    본문 = html.split("function setRoomFilter(f)")[1].split("\n}")[0]
    assert "if (COMM.room) closeRoom();" in 본문
    assert "renderRoomList();" in 본문


def test_고정한_방이_위로_간다():
    html = _index()
    본문 = html.split("function renderRoomList()")[1].split("\n}")[0]
    assert "const 고정 = new Set(내채팅 ? (state.pinnedRooms || []).map(Number) : []);" in 본문
    assert ".sort((a, b) => (고정.has(b.id) ? 1 : 0) - (고정.has(a.id) ? 1 : 0))" in 본문
    assert "data-pin-room=" in 본문
    assert 'aria-pressed="${고정.has(rm.id)}"' in 본문   # 켜짐/꺼짐을 읽어 줄 수 있게


def test_고정_버튼은_내_채팅에만_뜬다():
    """전체 목록은 아직 안 들어간 방이다. 고정할 것이 아니다."""
    html = _index()
    본문 = html.split("function renderRoomList()")[1].split("\n}")[0]
    핀 = 본문.split("data-pin-room=")[0]
    assert 핀.rstrip().endswith("${내채팅 ? `<button class=\"room-pin\"")


def test_고정은_계정에_남는다():
    html = _index()
    본문 = html.split("async function togglePinRoom(id)")[1].split("\n}")[0]
    assert "state.pinnedRooms.splice(있던자리, 1)" in 본문   # 다시 누르면 풀린다
    assert "state.pinnedRooms.unshift(id)" in 본문
    assert "saveProfile()" in 본문
    assert "pinnedRooms: state.pinnedRooms," in html                 # 스냅샷에 담고
    assert "state.pinnedRooms = Array.isArray(saved?.pinnedRooms)" in html   # 되돌린다
    assert html.count("state.pinnedRooms = [];") >= 3                # 초기화 자리마다


# ---------- 채팅 댓글 ----------

def test_채팅_메시지에_댓글을_단다():
    html = _index()
    본문 = html.split("function chatRepliesHtml(m)")[1].split("\n}")[0]
    assert "toggleReplies(${m.id})" in 본문
    assert "💬 댓글 ${목록.length}" in 본문
    assert 'id="cr-${m.id}"' in 본문                 # 댓글 입력칸
    assert 'class="post-send sm"' in 본문            # 게시글 댓글과 같은 모양
    줄 = html.split("function chatMsgHtml(m)")[1].split("\n}")[0]
    assert "chatRepliesHtml(m)" in 줄


def test_채팅_댓글도_내_것만_고치고_지운다():
    html = _index()
    본문 = html.split("function chatRepliesHtml(m)")[1].split("\n}")[0]
    assert "c['내글']" in 본문
    assert "editReply(${c.id})" in 본문 and "removeReply(${c.id})" in 본문
    지우기 = html.split("async function removeReply(id)")[1].split("\n}")[0]
    assert "confirm(" in 지우기


def test_펼쳐_둔_댓글은_다시_그려도_접히지_않는다():
    """채팅은 4초마다 다시 그린다. 펴 둔 게 접히면 읽을 수가 없다."""
    html = _index()
    assert "const openReplies = new Set();" in html
    본문 = html.split("function toggleReplies(id)")[1].split("\n}")[0]
    assert "openReplies.delete(id)" in 본문 and "openReplies.add(id)" in 본문
    그리기 = html.split("function paintChat(list, { 강제 = false } = {})")[1].split("\n}")[0]
    assert "[...openReplies].sort().join(',')" in 그리기   # 펴고 접은 것도 화면에 든다


def test_댓글을_보내면_입력칸을_비운다():
    """다시 그릴 때 '적다 만 것' 으로 되살아나면, 방금 단 댓글이 칸에 남는다."""
    html = _index()
    본문 = html.split("async function sendReply(mid)")[1].split("\n}")[0]
    assert "inp.value = '';" in 본문
    assert 본문.index("inp.value = '';") < 본문.index("API.commMsgReply")


def test_방을_옮기면_펴_둔_댓글은_잊는다():
    html = _index()
    본문 = html.split("async function openRoom(id, name)")[1].split("\n}")[0]
    assert "openReplies.clear()" in 본문


def test_인라인_수정창은_프로필_폼과_이름이_겹치지_않는다():
    """.edit-row 는 프로필 폼(성별 버튼 포함)이 이미 쓰던 이름이다.
    같은 이름을 쓰면 여기 button 규칙이 그쪽 버튼까지 칠한다."""
    html = _index()
    assert 'class="inline-edit"' in html
    assert ".inline-edit button{" in html
    # 프로필 폼 쪽 규칙은 그대로 살아 있어야 한다
    assert ".edit-row > span:first-child{" in html
    앞 = html.split(".edit-seg button.on{")[1].split("}")[0]
    assert "background:var(--pine)" in 앞
    # 인라인 수정창 CSS 가 .edit-row 를 다시 정의하지 않는다
    assert ".edit-row button{" not in html
    assert ".edit-row{ display:flex; gap:6px;" not in html
