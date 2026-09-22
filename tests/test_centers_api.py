"""체력인증센터 목록 — 공단 오픈API(측정건수 정보)를 받아 쓰고, 못 받으면 스냅숏 · 예시로 (backend/centers_api.py)."""
import datetime as dt
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import centers_api as ca
from backend.main import app

client = TestClient(app)

ROWS = [
    {"test_ym": "202608", "center_nm": "노원구 체력인증센터", "center_addr1": "서울특별시 노원구 동일로 1238",
     "center_addr2": "노원구민체육센터", "la": "37.655", "lo": "127.061", "test_cnt": "310"},
    {"test_ym": "202607", "center_nm": "노원구 체력인증센터", "center_addr1": "서울특별시 노원구 동일로 1238",
     "center_addr2": "노원구민체육센터", "la": "37.655", "lo": "127.061", "test_cnt": "290"},
    {"test_ym": "202608", "center_nm": "청주 체력인증센터", "center_addr1": "청주시 서원구 사직대로 229 (종합운동장 북3문)",
     "la": "127.47", "lo": "36.63", "test_cnt": "120"},                                # 위도 · 경도가 뒤바뀐 행
    {"test_ym": "202608", "center_nm": "양천구 체력인증센터", "center_addr1": "서울특별시 양천구 목동동로 1"},  # 좌표 없음
    {"test_ym": "202608", "center_addr1": "이름 없는 행"},
]


@pytest.fixture(autouse=True)
def _fresh(monkeypatch, tmp_path):
    """다른 테스트가 받아 둔 목록 · 이 PC 의 인증키 · 저장소의 스냅숏에 기대지 않는다."""
    monkeypatch.delenv("DATA_GO_KR_KEY", raising=False)
    monkeypatch.setattr(ca, "SNAPSHOT", tmp_path / "centers_kspo.json")
    ca._cache.update(at=0.0, items=None, source=None, fields=[], error=None)
    yield
    ca._cache.update(at=0.0, items=None, source=None, fields=[], error=None)


def test_행을_화면_모양으로_묶는다():
    got = {c["fcltyNm"]: c for c in ca.normalize(ROWS)}
    assert set(got) == {"노원구 체력인증센터", "청주 체력인증센터", "양천구 체력인증센터"}      # 이름 없는 행은 버린다
    노원 = got["노원구 체력인증센터"]
    assert 노원["addr"] == "서울특별시 노원구 동일로 1238 노원구민체육센터"
    assert (노원["la"], 노원["lo"], 노원["좌표어림"]) == (37.655, 127.061, False)
    assert 노원["측정건수"] == 600 and 노원["기준월"] == "202608"          # 같은 센터의 달은 합치고 최근 달을 적는다
    assert (got["청주 체력인증센터"]["la"], got["청주 체력인증센터"]["lo"]) == (36.63, 127.47)
    양천 = got["양천구 체력인증센터"]
    assert 양천["좌표어림"] is True and 양천["la"] is not None                # 주소의 구 이름으로 대략의 좌표


def test_응답의_목록_모양이_달라도_읽는다():
    body = {"response": {"body": {"items": {"item": ROWS[:1]}, "totalCount": "1"}}}
    assert ca._items_of(body) == (ROWS[:1], 1)
    one = {"response": {"body": {"items": {"item": ROWS[0]}}}}
    assert ca._items_of(one) == ([ROWS[0]], None)
    flat = {"body": {"items": ROWS[:2]}}
    assert ca._items_of(flat)[0] == ROWS[:2]
    assert ca._items_of({"response": {"body": {"items": ""}}}) == ([], None)


def test_인증키는_인코딩돼_있어도_풀어서_쓴다(monkeypatch):
    assert ca.service_key() is None
    monkeypatch.setenv("DATA_GO_KR_KEY", "abc%2Bdef%3D%3D")
    assert ca.service_key() == "abc+def=="
    monkeypatch.setenv("DATA_GO_KR_KEY", "your_api_key_here")
    assert ca.service_key() is None


def test_지난달이_비었으면_두_달_전을_받는다():
    seen = []

    def handler(req: httpx.Request):
        q = dict(req.url.params)
        seen.append(q.get("test_ym"))
        assert q["serviceKey"] == "KEY" and q["resultType"] == "json"
        items = ROWS[:2] if q.get("test_ym") == "202607" else []
        return httpx.Response(200, json={"response": {"body": {"items": {"item": items}, "totalCount": str(len(items))}}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        rows, fields = ca.fetch("KEY", client=c, today=dt.date(2026, 9, 22))
    assert seen == ["202608", "202607"]
    assert len(rows) == 2 and "center_nm" in fields and "test_cnt" in fields


def test_키가_없으면_예시_목록():
    got, source = ca.items()
    assert source == "sample" and got                              # data/sample/centers.json


def test_못_받으면_스냅숏으로(monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_KEY", "KEY")
    monkeypatch.setattr(ca, "fetch", lambda key: (_ for _ in ()).throw(httpx.ConnectError("down")))
    ca.SNAPSHOT.write_text(json.dumps({"items": ca.normalize(ROWS)}, ensure_ascii=False), encoding="utf-8")
    got, source = ca.items()
    assert source == "snapshot" and len(got) == 3
    assert ca.status()["오류"] == "ConnectError"


def test_받으면_하루_동안_다시_받지_않는다(monkeypatch):
    calls = []
    monkeypatch.setenv("DATA_GO_KR_KEY", "KEY")
    monkeypatch.setattr(ca, "fetch", lambda key: (calls.append(key) or (ROWS, ["center_nm"])))
    first, source = ca.items()
    again, _ = ca.items()
    assert source == "api" and len(first) == 3 and again is first and calls == ["KEY"]


def test_검색은_받아_둔_목록을_쓰고_고치지_않는다(monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_KEY", "KEY")
    monkeypatch.setattr(ca, "fetch", lambda key: (ROWS, ["center_nm"]))
    b = client.get("/centers", params={"region": "노원구"}).json()
    assert b["출처"] == "api" and "측정건수 정보" in b["데이터"]
    assert [c["fcltyNm"] for c in b["items"]] == ["노원구 체력인증센터"] and b["items"][0]["예약"]
    assert "예약" not in ca._cache["items"][0]                     # 응답에만 붙인다
    # 좌표를 모르는 센터가 섞여도 거리순이 깨지지 않는다
    b = client.get("/centers", params={"lat": 37.55, "lon": 127.0, "limit": 5}).json()
    assert [c["거리km"] is None for c in b["items"]] == sorted(c["거리km"] is None for c in b["items"])


def test_진단은_칸_이름만_낸다(monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_KEY", "KEY")
    monkeypatch.setattr(ca, "fetch", lambda key: (ROWS, sorted(ROWS[0])))
    s = client.get("/centers/source").json()
    assert s["출처"] == "api" and s["센터수"] == 3 and "center_nm" in s["응답필드"]
    assert "KEY" not in json.dumps(s)
    a = client.get("/centers/all").json()
    assert a["출처"] == "api" and len(a["items"]) == 3
