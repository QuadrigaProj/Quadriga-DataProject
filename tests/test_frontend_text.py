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
