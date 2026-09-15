"""시작일의 계절과 날씨 (backend/season.py).

바깥 서비스(Open-Meteo)는 부르지 않는다. 예보 범위 밖 날짜로 None 이 되는
것과, 응답을 흉내 내서 다듬는 것만 본다.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import season as ssn  # noqa: E402


@pytest.mark.parametrize("월,계절", [(3, "봄"), (5, "봄"), (6, "여름"), (8, "여름"),
                                   (9, "가을"), (11, "가을"), (12, "겨울"), (1, "겨울"), (2, "겨울")])
def test_달로_계절을_가른다(월, 계절):
    assert ssn.season_of(dt.date(2026, 월, 15)) == 계절


def test_시작_계절부터_한_바퀴():
    """봄에 받았다고 봄부터가 아니다."""
    assert ssn.order_from("가을") == ("가을", "겨울", "봄", "여름")
    assert ssn.order_from("봄") == ("봄", "여름", "가을", "겨울")
    assert ssn.order_from("장마") == ssn.SEASONS          # 모르는 건 기본 순서


def test_날짜는_YYYY_MM_DD_만():
    assert ssn.parse_date("2026-09-12") == dt.date(2026, 9, 12)
    assert ssn.parse_date("2026-09-12T10:00") == dt.date(2026, 9, 12)
    for 나쁜 in ("09/12", "내일", "", None, 20260912):
        assert ssn.parse_date(나쁜) is None


def test_예보_범위_밖이면_부르지_않고_None():
    """네트워크 없이도 이 테스트는 돌아야 한다 — 범위 밖은 부르기 전에 끝난다."""
    먼날 = dt.date.today() + dt.timedelta(days=ssn.FORECAST_DAYS + 1)
    assert ssn.fetch_weather(먼날) is None
    assert ssn.fetch_weather(dt.date.today() - dt.timedelta(days=1)) is None


def test_예보_응답을_다듬는다(monkeypatch):
    class _R:
        def raise_for_status(self): pass
        def json(self): return {"daily": {"temperature_2m_max": [26.4], "temperature_2m_min": [17.9],
                                          "precipitation_probability_max": [40],
                                          "relative_humidity_2m_mean": [63], "weather_code": [61]}}
    잡힌 = {}
    def _get(url, params=None, timeout=None):
        잡힌.update(params); return _R()
    monkeypatch.setattr(ssn.httpx, "get", _get)
    w = ssn.fetch_weather(dt.date.today(), 35.1, 129.0)
    assert w == {"최고": 26.4, "최저": 17.9, "강수확률": 40, "습도": 63, "하늘": "비", "기준": "내 위치"}
    assert 잡힌["latitude"] == 35.1 and 잡힌["timezone"] == "Asia/Seoul"
    # 위치를 모르면 서울 기준이라고 말한다
    assert ssn.fetch_weather(dt.date.today())["기준"] == "서울"


def test_예보가_실패해도_None(monkeypatch):
    def _boom(*a, **k): raise RuntimeError("연결 실패")
    monkeypatch.setattr(ssn.httpx, "get", _boom)
    assert ssn.fetch_weather(dt.date.today()) is None


@pytest.mark.parametrize("code,하늘", [(0, "맑음"), (2, "구름 조금"), (3, "흐림"), (45, "안개"),
                                      (61, "비"), (81, "비"), (73, "눈"), (95, "뇌우"), (None, None), ("x", None)])
def test_날씨_코드를_한_낱말로(code, 하늘):
    assert ssn._sky(code) == 하늘


def test_start_info(monkeypatch):
    monkeypatch.setattr(ssn, "fetch_weather", lambda *a, **k: None)
    assert ssn.start_info("2027-10-05") == {"시작일": "2027-10-05", "계절": "가을", "날씨": None}
    assert ssn.start_info("아무때나") is None
