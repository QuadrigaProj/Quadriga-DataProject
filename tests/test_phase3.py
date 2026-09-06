"""InBody(체성분) · 홈 체력측정 · 센터 지역 검색 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import geo                        # noqa: E402
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
        "sex": "F", "age": 8, "height_cm": 130, "weight_kg": 28,
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


def test_geo_부분일치():
    assert geo.geocode("서울 강남구") == geo.PLACES["강남구"]
    assert geo.geocode("수원 영통구") is not None
    assert geo.geocode("존재하지않음") is None
