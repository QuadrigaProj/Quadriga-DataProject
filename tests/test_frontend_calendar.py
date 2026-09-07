"""달력·변화추이 화면(F4) 정적 회귀 테스트.

index.html 을 "/" 로 받아 문자열만 확인한다. 화면 골격·탭·기간 선택지가 있고,
기록 화면의 state.first 경로 버그 수정이 되돌아가지 않았는지 잡는 것이 목적이다.
"""
from fastapi.testclient import TestClient

from backend.main import app

c = TestClient(app)


def _index() -> str:
    r = c.get("/")
    assert r.status_code == 200
    return r.text


def test_달력_화면이_있다():
    html = _index()
    assert 'id="s9"' in html
    assert 'id="calGrid"' in html
    assert 'id="calDayDetail"' in html
    assert 'id="trendChart"' in html


def test_탭바에_달력이_들어갔다():
    html = _index()
    assert "{ id: 's9', icon: '📅', label: '달력' }" in html
    for s in ("'s3'", "'s7'", "'s9'", "'s8'", "'s5'"):   # 홈·기록·달력·운동 고르기·프로필
        assert f"{{ id: {s}," in html


def test_변화추이_기간_선택지가_있다():
    html = _index()
    for label in ("7일", "30일", "90일", "전체"):
        assert f">{label}</button>" in html


def test_기록_화면의_첫_점검_경로_버그가_고쳐졌다():
    html = _index()
    assert "state.first?.결과?.체력나이" in html
    assert "state.first?.체력나이 ?? null" not in html


def test_달력_화면이_goTo_에_연결됐다():
    html = _index()
    assert "if(id === 's9') renderCalendar();" in html
    assert "function renderCalendar()" in html or "async function renderCalendar()" in html


def test_달력은_라이브러리를_쓰지_않는다():
    """F4 달력·그래프는 인라인 DOM/SVG — 외부 차트/달력 스크립트가 붙지 않아야 한다."""
    html = _index()
    for lib in ("chart.js", "fullcalendar", "d3.min", "apexcharts"):
        assert lib not in html.lower()
