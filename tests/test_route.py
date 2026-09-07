"""출발지→목적지 경로 분석 (F2). 외부 API 는 전부 가짜로 바꾼다 — 네트워크 호출 금지."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import daily, geo, route          # noqa: E402
from backend.main import app                   # noqa: E402

c = TestClient(app)
SEONGBUK, GANGNAM = geo.PLACES["성북구"], geo.PLACES["강남역"]


def _async(value):
    async def f(*a, **k):
        return value
    return f


def _fake(monkeypatch, *, minutes=10, distance_m=None, guidance=(), gain=0.0, places=None):
    """provider 3개를 가짜로. places=None 이면 성북구/강남역만 안다(그 외는 None → geo.geocode 로 폴백)."""
    table = places if places is not None else {"성북구": SEONGBUK, "강남역": GANGNAM}

    async def geocode(q):
        return table.get(q)

    walk = None if minutes is None else {
        "거리m": distance_m or minutes * 80, "시간초": minutes * 60,
        "구간안내": list(guidance), "좌표": [SEONGBUK, GANGNAM]}
    monkeypatch.setattr(route, "geocode_text", geocode)
    monkeypatch.setattr(route, "kakao_walk", _async(walk))
    monkeypatch.setattr(route, "elevation_gain", _async(gain))


def _advice(**kw):
    q = {"from": "성북구", "to": "강남역", "strength_stars": 3}
    q.update(kw)
    return c.get("/route/advice", params=q)


# ---------- 규칙 분기 ----------

def test_짧은_거리는_전부_걷기(monkeypatch):
    _fake(monkeypatch, minutes=12)
    r = _advice()
    assert r.status_code == 200
    j = r.json()
    assert j["추천"]["유형"] == "전부걷기"
    assert "12분" in j["추천"]["문구"]
    assert j["계단있음"] is False
    assert j["출처"] == "kakao"
    assert j["시간분"] == 12


def test_중간_거리는_한_정거장_먼저_내려_걷기(monkeypatch):
    _fake(monkeypatch, minutes=28)
    j = _advice().json()
    assert j["추천"]["유형"] == "일부걷기"
    assert "1정거장" in j["추천"]["문구"]


def test_조금_더_멀면_두_정거장(monkeypatch):
    _fake(monkeypatch, minutes=40)
    j = _advice().json()
    assert j["추천"]["유형"] == "일부걷기"
    assert "2정거장" in j["추천"]["문구"]


def test_먼_거리는_대중교통(monkeypatch):
    _fake(monkeypatch, minutes=70)
    j = _advice().json()
    assert j["추천"]["유형"] == "대중교통"
    assert "대중교통" in j["추천"]["문구"]


def test_오르막이_있으면_근력에_맞는_계단_문구가_붙는다(monkeypatch):
    _fake(monkeypatch, minutes=12, gain=22)
    j = _advice(strength_stars=5).json()
    assert j["계단있음"] is True
    assert daily.STAIRS["상위"] in j["추천"]["문구"]
    assert "오르막" in j["추천"]["문구"]


def test_안내문에_계단이_있으면_오르막이_없어도_계단있음(monkeypatch):
    guidance = ["계단을 올라 육교를 건너세요"]
    _fake(monkeypatch, minutes=12, guidance=guidance, gain=3)
    j = _advice().json()
    assert j["계단있음"] is True
    assert "계단 구간" in j["추천"]["문구"]
    assert j["구간안내"] == guidance


def test_근력이_약하면_계단을_권하지_않는다(monkeypatch):
    _fake(monkeypatch, minutes=12, gain=30)
    weak = _advice(strength_stars=1).json()["추천"]["문구"]
    strong = _advice(strength_stars=5).json()["추천"]["문구"]
    assert daily.STAIRS["하위"] in weak
    assert "무리한 계단" in weak
    assert weak != strong


def test_평지면_계단_문구가_없다(monkeypatch):
    _fake(monkeypatch, minutes=12, gain=5, guidance=())
    j = _advice().json()
    assert j["계단있음"] is False
    for text in daily.STAIRS.values():
        assert text not in j["추천"]["문구"]


def test_경계값():
    """route.recommend 직접 호출 — 네트워크 없음."""
    assert route.recommend(20, None, False, 3)["유형"] == "전부걷기"
    assert route.recommend(21, None, False, 3)["유형"] == "일부걷기"
    assert route.recommend(45, None, False, 3)["유형"] == "일부걷기"
    assert route.recommend(46, None, False, 3)["유형"] == "대중교통"


# ---------- 폴백 ----------

def test_키가_없으면_카카오를_부르지_않는다(monkeypatch):
    monkeypatch.delenv("KAKAO_CLIENT_ID", raising=False)

    async def boom(*a, **k):
        raise AssertionError("네트워크 호출")

    monkeypatch.setattr(route, "_get_json", boom)
    assert asyncio.run(route.geocode_text("성북구")) is None
    assert asyncio.run(route.kakao_walk(SEONGBUK, GANGNAM)) is None


def test_카카오가_안_되면_직선거리로_추정한다(monkeypatch):
    _fake(monkeypatch, minutes=None, gain=None, places={})   # geocode_text 전부 None → geo.geocode
    r = _advice(**{"from": "성북구", "to": "강남구"})
    assert r.status_code == 200
    j = r.json()
    assert j["출처"] == "추정"
    assert j["구간안내"] == []
    assert j["오르막m"] is None
    assert j["계단있음"] is False
    기대거리 = round(daily._km(*geo.PLACES["성북구"], *geo.PLACES["강남구"]) * 1000)
    assert j["거리m"] == 기대거리
    assert j["시간분"] == round(기대거리 / 80)
    assert "직선거리" in j["안내"]
    assert j["추천"]["유형"] == "대중교통"


def test_추정_경로에서도_오르막은_본다(monkeypatch):
    _fake(monkeypatch, minutes=None, gain=40, places={})
    j = _advice(**{"from": "성북구", "to": "강남구"}).json()
    assert j["출처"] == "추정"
    assert j["계단있음"] is True
    assert "Open-Meteo" in j["안내"]


def test_지역을_못_찾으면_404(monkeypatch):
    _fake(monkeypatch, places={})
    r = _advice(**{"from": "없는동네12345"})
    assert r.status_code == 404
    assert "없는동네12345" in r.json()["detail"]


def test_출발지와_목적지가_같으면_400(monkeypatch):
    _fake(monkeypatch, places={"성북구": SEONGBUK, "강남역": SEONGBUK})
    assert _advice().status_code == 400


def test_빈_입력은_422():
    assert c.get("/route/advice", params={"from": "", "to": "강남역"}).status_code == 422


# ---------- 파싱 (전송 계층만 가짜) ----------

def test_카카오_경로_응답_파싱(monkeypatch):
    monkeypatch.setenv("KAKAO_CLIENT_ID", "test-key")
    payload = {"status": "OK", "route": {"properties": {"totalDistance": 1234, "totalTime": 900},
               "legs": [{"steps": [
                   {"properties": {"guidance": "직진"},
                    "path": {"points": [[127.0167, 37.5894], [127.02, 37.59]]}},
                   {"properties": {"guidance": "계단을 올라가세요"},
                    "path": {"points": [[127.03, 37.6]]}},
               ]}]}}
    monkeypatch.setattr(route, "_get_json", _async(payload))
    w = asyncio.run(route.kakao_walk(SEONGBUK, GANGNAM))
    assert w["거리m"] == 1234 and w["시간초"] == 900
    assert w["구간안내"] == ["직진", "계단을 올라가세요"]
    assert w["좌표"][0] == (37.5894, 127.0167)      # x,y → (위도, 경도)
    assert len(w["좌표"]) == 3


def test_상태가_OK가_아니면_None(monkeypatch):
    monkeypatch.setenv("KAKAO_CLIENT_ID", "test-key")
    monkeypatch.setattr(route, "_get_json", _async({"status": "START_LINK_NOT_FOUND"}))
    assert asyncio.run(route.kakao_walk(SEONGBUK, GANGNAM)) is None


def test_장소검색_응답_파싱(monkeypatch):
    monkeypatch.setenv("KAKAO_CLIENT_ID", "test-key")
    monkeypatch.setattr(route, "_get_json", _async({"documents": [{"x": "127.0276", "y": "37.4979"}]}))
    assert asyncio.run(route.geocode_text("강남역")) == (37.4979, 127.0276)
    monkeypatch.setattr(route, "_get_json", _async({"documents": []}))
    assert asyncio.run(route.geocode_text("강남역")) is None


def test_고도_응답에서_오르막만_더한다(monkeypatch):
    monkeypatch.setattr(route, "_get_json", _async({"elevation": [10, 15, 12, 20]}))
    pts = [(37.0, 127.0), (37.1, 127.0), (37.2, 127.0), (37.3, 127.0)]
    assert asyncio.run(route.elevation_gain(pts)) == 13.0      # 5 + 8


def test_고도_점수가_안_맞으면_None(monkeypatch):
    monkeypatch.setattr(route, "_get_json", _async({"elevation": [10, 15, 12]}))
    pts = [(37.0, 127.0), (37.1, 127.0), (37.2, 127.0), (37.3, 127.0)]
    assert asyncio.run(route.elevation_gain(pts)) is None


def test_고도는_100점_이하로_샘플링():
    pts = [(37 + i * 1e-4, 127) for i in range(500)]
    s = route._sample(pts, 100)
    assert len(s) == 100 and s[0] == pts[0] and s[-1] == pts[-1]


# ---------- 파싱 실패 → None (응답 모양이 가정과 다를 때) ----------

def test_경로_응답_모양이_다르면_None(monkeypatch):
    """필드명은 devtalk 공지 기준(미검증). 모양이 다르면 예외(→400/500) 대신 None → advise 가 추정 폴백."""
    monkeypatch.setenv("KAKAO_CLIENT_ID", "test-key")
    props = {"totalDistance": 1000, "totalTime": 600}

    def route_with(points):
        return {"properties": props, "legs": [{"steps": [{"path": {"points": points}}]}]}

    for payload in (
        {"status": "OK", "route": route_with([{"x": 127.0, "y": 37.5}])},          # points 가 {x, y} 객체
        {"status": "OK", "route": route_with([[127.0, 37.5, 0.0]])},               # points 가 3원소
        {"status": "OK", "route": [route_with([[127.0, 37.5]])]},                  # route 가 리스트
        {"status": "OK", "route": {"properties": props, "legs": {"steps": []}}},   # legs 가 dict
        ["status", "OK"],                                                           # 응답 자체가 리스트
    ):
        monkeypatch.setattr(route, "_get_json", _async(payload))
        assert asyncio.run(route.kakao_walk(SEONGBUK, GANGNAM)) is None, payload


def test_장소검색_응답_모양이_다르면_None(monkeypatch):
    monkeypatch.setenv("KAKAO_CLIENT_ID", "test-key")
    for payload in (
        [{"x": "127.0", "y": "37.5"}],                  # 응답 자체가 리스트
        {"documents": [["127.0", "37.5"]]},             # 문서가 배열
        {"documents": [{"x": "경도", "y": "위도"}]},     # 좌표가 숫자가 아님
    ):
        monkeypatch.setattr(route, "_get_json", _async(payload))
        assert asyncio.run(route.geocode_text("강남역")) is None, payload


def test_고도_응답_모양이_다르면_None(monkeypatch):
    pts = [(37.0, 127.0), (37.1, 127.0)]
    for payload in (["elevation"], {"elevation": [10, None]}, {"elevation": ["a", "b"]}):
        monkeypatch.setattr(route, "_get_json", _async(payload))
        assert asyncio.run(route.elevation_gain(pts)) is None, payload


def test_응답_모양이_달라도_추정으로_폴백한다(monkeypatch):
    """리뷰 재현: 키가 있고 카카오·Open-Meteo 응답 모양이 전부 가정과 다르면 400/500 이 아니라 200 추정."""
    monkeypatch.setenv("KAKAO_CLIENT_ID", "test-key")

    async def odd_shapes(url, params, headers=None):
        if url == route.KAKAO_KEYWORD_URL:
            return [{"x": "127.0", "y": "37.5"}]                    # 리스트 → geo.geocode 로
        if url == route.KAKAO_WALK_URL:
            return {"status": "OK", "route": {"properties": {"totalDistance": 1, "totalTime": 60},
                    "legs": [{"steps": [{"path": {"points": [{"x": 127.0, "y": 37.5}]}}]}]}}
        return ["elevation"]

    monkeypatch.setattr(route, "_get_json", odd_shapes)
    r = _advice()
    assert r.status_code == 200
    j = r.json()
    assert j["출처"] == "추정" and j["오르막m"] is None


def test_전용_예외만_404_400_으로_바꾼다(monkeypatch):
    """파싱에서 샌 KeyError(⊂LookupError)·ValueError 가 404/400 으로 둔갑해 내부 오류 문자열이 보이지 않게."""
    for exc in (KeyError("y"), ValueError("could not convert string to float: 'y'")):
        async def broken(*a, **k):
            raise exc

        monkeypatch.setattr(route, "advise", broken)
        with pytest.raises(type(exc)):
            _advice()


# ---------- 프론트 문자열 회귀 ----------

def test_홈_카드에_출발지_목적지_입력이_있다():
    html = c.get("/").text
    for s in ('id="commuteFrom"', 'id="commuteTo"', '>분석</button>', 'routeAdvice', 'commute:'):
        assert s in html, s
    assert "routeAdvice" in c.get("/js/api.js").text
