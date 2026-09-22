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


# ---------- 좌표 (2026-09-22 배포 서버에서 본 것: 공단 API 는 좌표를 주지 않는다) ----------

def test_어림_좌표는_시도부터_본다():
    """뒤에서부터 보면 "울산광역시 남구" 의 '남구' 가 서울 '강남구' 에 부분 일치해 울산 센터가 서울에 찍혔다."""
    got = {c["fcltyNm"]: c for c in ca.normalize([
        {"center_nm": "울산", "center_addr1": "울산광역시 남구 웅촌로 1342 (무거동)문수체육관 내"},
        {"center_nm": "관악", "center_addr1": "서울 관악구 신림동 1646"},
        {"center_nm": "오산", "center_addr1": "경기도 오산시 경기동로 33 (오산동)"},
    ], known={})}
    assert abs(got["울산"]["la"] - 35.54) < 0.1 and abs(got["울산"]["lo"] - 129.31) < 0.1      # 울산이지 서울이 아니다
    assert abs(got["관악"]["la"] - 37.478) < 0.01                                            # 서울은 자치구로
    assert got["오산"]["la"] is None                                                           # 모르면 모른다고 둔다


def test_스냅숏의_지오코딩_좌표를_먼저_쓴다():
    """API 행에 좌표가 없으면 스냅숏(data/sample/centers_kspo.json)에 적어 둔 좌표를 이름으로 찾아 넣는다."""
    ca.SNAPSHOT.write_text(json.dumps({"items": [{"fcltyNm": "오산", "la": 37.15, "lo": 127.07, "좌표어림": False}]},
                                      ensure_ascii=False), encoding="utf-8")
    got = ca.normalize([{"center_nm": "오산", "center_addr1": "경기도 오산시 경기동로 33", "test_cnt": "5"}])
    assert (got[0]["la"], got[0]["lo"], got[0]["좌표어림"]) == (37.15, 127.07, False)
    assert ca.known_coords() == {"오산": (37.15, 127.07, False)}


def test_저장소의_스냅숏은_전국_센터의_좌표를_다_갖고_있다():
    """2026-09-22 배포 서버가 받은 100곳(시험 행 2곳 제외 98곳)을 Nominatim 으로 지오코딩해 둔 것."""
    from backend.paths import ROOT
    items = json.loads((ROOT / "data" / "sample" / "centers_kspo.json").read_text(encoding="utf-8"))["items"]
    assert len(items) >= 90 and all(c["la"] is not None and c["lo"] is not None for c in items)
    assert all(33 <= c["la"] <= 39 and 124 <= c["lo"] <= 132 for c in items)                # 전부 한국 안
    울산 = next(c for c in items if c["fcltyNm"] == "울산")
    assert abs(울산["la"] - 35.5) < 0.2                                                       # 예전 버그였던 자리


def test_공단_자료의_시험_행은_버린다():
    got = ca.normalize([{"center_nm": "2026 국민체력100 1번 업체", "test_cnt": "14"},
                        {"center_nm": "노원", "center_addr1": "서울특별시 노원구 월계로 378"}], known={})
    assert [c["fcltyNm"] for c in got] == ["노원"]


def test_포털이_한_쪽을_100줄로_깎아도_끝까지_받는다():
    """numOfRows=1000 을 보내도 100줄씩 주는 API 가 있다 — totalCount 를 보고 다음 쪽을 받는다."""
    pages = []

    def handler(req: httpx.Request):
        q = dict(req.url.params)
        pages.append(int(q["pageNo"]))
        n = int(q["pageNo"])
        items = [{"center_nm": f"센터{n}-{i}", "center_addr1": "서울특별시 노원구 x"} for i in range(100 if n < 3 else 50)]
        return httpx.Response(200, json={"response": {"body": {"items": {"item": items}, "totalCount": "250"}}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        rows, _ = ca.fetch("KEY", client=c, today=dt.date(2026, 9, 22))
    assert pages == [1, 2, 3] and len(rows) == 250
