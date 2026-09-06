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
