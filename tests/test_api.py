"""API 스모크 테스트.

실행:
    pytest -q

서버를 따로 띄우지 않아도 된다. FastAPI TestClient 가 앱을 직접 호출한다.
화면(frontend/)이 기대하는 응답 모양이 깨지지 않았는지 확인하는 것이 목적이다.
API 응답의 키 이름을 바꾸면 화면이 조용히 깨지므로, 바꿀 때는 이 파일도 함께 고친다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.main import app  # noqa: E402

client = TestClient(app)

ADULT = {"age_gbn": "성인", "sex": "M", "flexibility": 8.0, "strength": 25,
         "height_cm": 175, "weight_kg": 74}


def data_ready() -> bool:
    h = client.get("/health").json()
    return h["분포_로드됨"] and h["처방_로드됨"]


needs_data = pytest.mark.skipif(
    not data_ready(), reason="분포/처방 데이터 없음 — /health 안내 참고"
)


# ---------- 기본 ----------

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_frontend_served():
    """화면과 API 를 같은 서버가 내보낸다."""
    r = client.get("/")
    assert r.status_code == 200
    assert "체력나이" in r.text
    assert client.get("/js/api.js").status_code == 200


def test_purposes():
    """목적 6종은 데이터 없이도 떠야 한다 (화면 2가 먼저 로드된다)."""
    body = client.get("/purposes").json()
    assert len(body) == 6
    assert {"목적", "우선요인"} <= set(body[0])


# ---------- 체력나이 ----------

@needs_data
def test_fitness_age_성인():
    b = client.post("/fitness-age", json=ADULT).json()
    assert 10 < b["체력나이"] < 100
    assert b["신뢰구간"] > 0
    assert {"유연성", "근력", "체성분"} <= set(b["항목별"])
    assert b["약점"]["약점"] in b["항목별"]


@needs_data
def test_fitness_age_어르신():
    r = client.post("/fitness-age",
                    json={"age_gbn": "어르신", "sex": "F",
                          "flexibility": 10.0, "strength": 18, "bmi": 23.5})
    assert r.status_code == 200
    assert r.json()["체력나이"] > 50


@needs_data
def test_bmi_는_양방향_편차():
    """저체중도 과체중처럼 불리하게 잡혀야 한다 (BMI 는 U 자형)."""
    def 체성분(bmi):
        return client.post("/fitness-age",
                           json={"age_gbn": "성인", "sex": "M", "bmi": bmi}
                           ).json()["항목별"]["체성분"]

    assert 체성분(16.0) > 체성분(22.0)
    assert 체성분(30.0) > 체성분(22.0)


@needs_data
def test_청소년은_구간부족으로_거절():
    """공개 데이터에 연령구간이 2개뿐이라 보간이 무의미하다 → 산출하지 않는다."""
    r = client.post("/fitness-age",
                    json={"age_gbn": "청소년", "sex": "M",
                          "flexibility": 10, "strength": 25, "bmi": 21})
    assert r.status_code == 422


def test_측정값_없으면_400():
    assert client.post("/fitness-age",
                       json={"age_gbn": "성인", "sex": "M"}).status_code == 400


def test_없는_연령군은_422():
    assert client.post("/fitness-age",
                       json={"age_gbn": "유아", "sex": "M", "strength": 25}
                       ).status_code == 422


# ---------- 루틴 ----------

@needs_data
def test_routine_순서():
    steps = client.get("/routine", params={"age_gbn": "성인", "sex": "M",
                                           "purpose": "다이어트",
                                           "weak_factor": "근력"}).json()
    order = ["준비운동", "본운동", "정리운동"]
    assert [s["단계"] for s in steps] == sorted(
        (s["단계"] for s in steps), key=order.index)
    assert steps[0]["단계"] == "준비운동"
    assert steps[-1]["단계"] == "정리운동"


@needs_data
def test_recheck_변화량():
    b = client.post("/recheck", json={
        "이전": ADULT,
        "현재": {**ADULT, "flexibility": 12.0, "strength": 32, "weight_kg": 72},
    }).json()
    assert b["변화"] == round(b["현재"] - b["이전"], 1)
    assert b["변화"] < 0          # 측정값이 좋아졌으니 체력나이는 내려가야 한다


# ---------- 일상 처방 ----------

def test_daily_계단은_근력에_따라_달라진다():
    약 = client.get("/daily", params={"strength_stars": 1}).json()
    강 = client.get("/daily", params={"strength_stars": 5}).json()
    assert 약["계단"]["수준"] == "하위"
    assert 강["계단"]["수준"] == "상위"
    assert 약["계단"]["문구"] != 강["계단"]["문구"]


def test_daily_먼_거리는_걷기를_권하지_않는다():
    assert client.get("/daily", params={"walk_minutes": 12}).json()["도보"]["권장"] is True
    assert client.get("/daily", params={"walk_minutes": 45}).json()["도보"]["권장"] is False
    assert client.get("/daily").json()["도보"] is None


def test_daily_강도는_4주마다_올라간다():
    assert client.get("/daily", params={"days_since_start": 0}).json()["강도"]["세트"] == 2
    assert client.get("/daily", params={"days_since_start": 40}).json()["강도"]["세트"] == 3


# ---------- 동영상 ----------

def test_videos_요인_부분일치():
    """동영상 API 요인명은 '근력·근지구력' 처럼 묶여 있다."""
    assert client.get("/videos", params={"factor": "근력"}).json()["개수"] > 0


def test_videos_부담부위_제외():
    전체 = client.get("/videos", params={"factor": "근력"}).json()["개수"]
    제외 = client.get("/videos", params={"factor": "근력",
                                      "exclude_parts": "무릎"}).json()["개수"]
    assert 제외 < 전체


def test_centers_거리순():
    items = client.get("/centers", params={"lat": 37.55, "lon": 127.0,
                                           "limit": 3}).json()["items"]
    거리 = [c["거리km"] for c in items]
    assert 거리 == sorted(거리)
