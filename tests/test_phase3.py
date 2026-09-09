"""InBody(체성분) · 홈 체력측정 · 센터 지역 검색 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import daily, geo                 # noqa: E402
from backend.main import app                   # noqa: E402

client = TestClient(app)


def data_ready() -> bool:
    h = client.get("/health").json()
    return h["분포_로드됨"]


needs_data = pytest.mark.skipif(not data_ready(), reason="분포 데이터 없음")


# ---------- InBody ----------

def test_bodycomp_분석_판정():
    b = client.post("/bodycomp", json={
        "sex": "M", "age": 40, "height_cm": 175, "weight_kg": 82,
        "body_fat_pct": 28, "waist_cm": 95, "skeletal_muscle_kg": 30,
    }).json()
    항목 = {x["항목"]: x for x in b["체성분분석"]}
    assert 항목["체지방률"]["판정"] == "비만"           # 남 25% 이상
    assert 항목["허리/키 비율"]["판정"] == "복부비만 위험"  # 95/175 > 0.5


def test_bodycomp_임의산식_안씀():
    """골격근량만 주고 체지방률·BMI 분포가 없으면 체력나이를 만들지 않는다."""
    b = client.post("/bodycomp", json={
        "sex": "F", "age": 11, "height_cm": 130, "weight_kg": 28,
        "skeletal_muscle_kg": 10,
    }).json()
    assert b["추정체력나이"] is None                # 유소년 분포 없음 → 억지 산출 안 함


@needs_data
def test_bodycomp_체지방률_있으면_체력나이():
    b = client.post("/bodycomp", json={
        "sex": "M", "age": 45, "height_cm": 175, "weight_kg": 88,
        "body_fat_pct": 30, "waist_cm": 100,
    }).json()
    assert b["추정체력나이"] is not None
    assert 30 <= b["추정체력나이"]["값"] <= 60


# ---------- 홈 체력측정 ----------

@needs_data
def test_hometest_추정체력나이_2항목만_반영():
    b = client.post("/hometest", json={
        "sex": "M", "age": 30, "height_cm": 175, "weight_kg": 74,
        "jump_30s": 50, "curlup_30s": 28, "knee_pushup_30s": 10, "high_knee_2min": 80,
    }).json()
    assert b["추정체력나이"] is not None
    # 무릎 푸시업·2분 하이니는 등급으로만
    등급항목 = {x["항목"] for x in b["홈체력등급"]}
    assert any("푸시업" in x for x in 등급항목)
    assert any("하이니" in x for x in 등급항목)
    assert "가장부족한요인" in b


@needs_data
def test_hometest_체력나이는_실제나이_pm15():
    b = client.post("/hometest", json={
        "sex": "F", "age": 25, "height_cm": 162, "weight_kg": 55,
        "jump_30s": 10, "curlup_30s": 3,
    }).json()
    if b["추정체력나이"] is not None:
        assert 10 <= b["추정체력나이"] <= 40


# ---------- 센터 ----------

def test_centers_지역명_검색():
    b = client.get("/centers", params={"region": "성신여대입구역", "limit": 3}).json()
    assert b["기준좌표"]["입력"] == "성신여대입구역"
    assert len(b["items"]) == 3
    거리 = [c["거리km"] for c in b["items"]]
    assert 거리 == sorted(거리)
    assert all("예약" in c for c in b["items"])       # 예약 링크 붙는다


def test_centers_도보시간은_만들지_않는다():
    b = client.get("/centers", params={"region": "강남구"}).json()
    dump = str(b)
    assert "도보" in b["안내"]                        # "도보 시간은 지도 앱에서"
    for c in b["items"]:
        assert "도보" not in c and "walk" not in c    # 개별 항목엔 도보시간 없음


def test_centers_모르는_지역():
    b = client.get("/centers", params={"region": "없는동네12345"}).json()
    assert b["지역인식실패"] is True
    assert b["기준좌표"] is None


# ---------- 센터: 구 단위 주소 일치 (C7) ----------

def test_centers_구_주소_일치():
    """'양천구' 처럼 구 이름을 넣으면 주소(addr)에 그 구가 있는 센터만 나온다."""
    b = client.get("/centers", params={"region": "양천구", "limit": 3}).json()
    assert b["매칭방식"] == "주소"
    assert b["지역인식실패"] is False
    assert len(b["items"]) == 1
    assert all("양천구" in c["addr"] for c in b["items"])
    assert all("예약" in c for c in b["items"])


def test_centers_주소_일치_여러_건은_거리순():
    """같은 구 이름이 여러 시·도에 있으면(대전 서구·광주 서구) 전부 보이고, 좌표가 있으면 가까운 순."""
    b = client.get("/centers", params={"region": "서구", "lat": 36.35, "lon": 127.38}).json()
    assert b["매칭방식"] == "주소"
    assert [c["addr"] for c in b["items"]] == ["대전광역시 서구", "광주광역시 서구"]
    거리 = [c["거리km"] for c in b["items"]]
    assert 거리 == sorted(거리)


def test_centers_주소_일치_좌표_없으면_순서_그대로():
    """좌표표(geo.PLACES)에 없는 구(남동구)는 거리를 붙이지 않고 파일 순서 그대로 둔다."""
    b = client.get("/centers", params={"region": "남동구"}).json()
    assert b["매칭방식"] == "주소"
    assert b["기준좌표"] is None
    assert b["지역인식실패"] is False
    assert len(b["items"]) == 1 and "거리km" not in b["items"][0]


def test_centers_주소_불일치는_가까운_순_폴백():
    """주소에 없는 구(성북구)는 기존 geocode 경로로 폴백해 가까운 순으로 돌려준다."""
    b = client.get("/centers", params={"region": "성북구", "limit": 3}).json()
    assert b["매칭방식"] == "거리"
    assert b["지역인식실패"] is False
    assert b["기준좌표"]["입력"] == "성북구"
    assert len(b["items"]) == 3
    거리 = [c["거리km"] for c in b["items"]]
    assert 거리 == sorted(거리)
    assert "가까운 순" in b["안내"]


def test_centers_공백_섞인_입력도_구로_대조():
    """'서울 양천구' 처럼 시·도를 앞에 붙여도 마지막 낱말(양천구)로 주소를 대조한다."""
    b = client.get("/centers", params={"region": "서울 양천구"}).json()
    assert b["매칭방식"] == "주소"
    assert [c["addr"] for c in b["items"]] == ["서울특별시 양천구"]


def test_centers_모르는_지역은_매칭방식_거리():
    b = client.get("/centers", params={"region": "없는동네12345"}).json()
    assert b["매칭방식"] == "거리"
    assert b["지역인식실패"] is True


def test_centers_좌표만_주면_종전과_같다():
    b = client.get("/centers", params={"lat": 37.55, "lon": 127.0, "limit": 3}).json()
    assert b["매칭방식"] == "거리"
    assert b["지역인식실패"] is False
    거리 = [c["거리km"] for c in b["items"]]
    assert 거리 == sorted(거리)


def test_centers_짧은_구_이름은_긴_구_이름_꼬리에_안_걸린다():
    """'동구' 는 '남동구' 와 다른 구다 — 주소 일치가 없으니 가까운 순 폴백(매칭방식 '거리')으로 간다."""
    assert daily.centers_by_addr("동구") == []
    assert daily.centers_by_addr("인천 동구") == []
    b = client.get("/centers", params={"region": "동구"}).json()
    assert b["매칭방식"] == "거리"
    assert "가까운 순" in b["안내"]


def test_centers_by_addr_구_이름은_낱말_단위로_대조(monkeypatch):
    """구 이름(…구)은 주소 낱말과 통째로 맞아야 하고(서구 ≠ 강서구), 시·도 이름은 종전처럼 부분 문자열."""
    items = [{"addr": a} for a in ("인천광역시 동구", "인천광역시 남동구", "서울특별시 강서구",
                                    "부산광역시 서구", "서울특별시 중구")]
    monkeypatch.setattr(daily, "load_json", lambda name: {"items": items})
    assert [c["addr"] for c in daily.centers_by_addr("동구")] == ["인천광역시 동구"]
    assert [c["addr"] for c in daily.centers_by_addr("서구")] == ["부산광역시 서구"]
    assert [c["addr"] for c in daily.centers_by_addr("인천광역시 동구")] == ["인천광역시 동구"]
    assert [c["addr"] for c in daily.centers_by_addr("서울")] == ["서울특별시 강서구", "서울특별시 중구"]


def test_geo_부분일치():
    assert geo.geocode("서울 강남구") == geo.PLACES["강남구"]
    assert geo.geocode("수원 영통구") is not None
    assert geo.geocode("존재하지않음") is None
