"""목표 체력나이 도달 시점 추정 (backend/projection.py)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import projection as pj  # noqa: E402
from backend.main import app  # noqa: E402

client = TestClient(app)
ADULT = {"age_gbn": "성인", "sex": "M", "age": 40, "flexibility": 8.0, "strength": 25,
         "height_cm": 175, "weight_kg": 74}


def data_ready() -> bool:
    h = client.get("/health").json()
    return h["분포_로드됨"] and h["처방_로드됨"]


needs_data = pytest.mark.skipif(not data_ready(), reason="분포 데이터 없음")


def test_향상_폭은_12주에_1이고_점점_준다():
    assert pj.gain_fraction(0) == 0 and pj.gain_fraction(6) == 0.5 and pj.gain_fraction(12) == 1.0
    assert abs(pj.gain_fraction(24) - 1.6) < 1e-9 and abs(pj.gain_fraction(48) - 2.3) < 1e-9
    assert pj.improved("앉아윗몸앞으로굽히기", 8.0, 12, hi=True) == 12.0      # +4 cm
    assert pj.improved("교차윗몸일으키기", 20, 12, hi=False) == 23.0        # +15 %
    assert pj.improved("BMI", 24.0, 12, hi=True) == 23.0                   # −1.0
    assert pj.improved("모르는항목", 5, 12, hi=True) == 5                   # 표에 없으면 그대로


@needs_data
def test_목표가_가까우면_빠르면_늦으면_주가_나오고_멀면_못_닿는다():
    지금 = client.post("/fitness-age", json=ADULT).json()["체력나이"]
    r = client.post("/fitness-age/eta", json={**ADULT, "target": 지금 - 2}).json()
    assert r["가능"] and r["빠르면주"] is not None and r["빠르면주"] % 4 == 0
    assert r["늦으면주"] is None or r["빠르면주"] <= r["늦으면주"]
    assert r["12주뒤"]["빠르면"] <= r["12주뒤"]["늦으면"] <= 지금            # 높은 추정이 더 젊다
    assert "주 3회 권장 용량대로" in r["가정"] and "주" in r["안내"]
    멀리 = client.post("/fitness-age/eta", json={**ADULT, "target": 지금 - 25}).json()
    assert 멀리["가능"] and 멀리["빠르면주"] is None and "1년 안에" in 멀리["안내"]
    이미 = client.post("/fitness-age/eta", json={**ADULT, "target": 지금 + 1}).json()
    assert 이미.get("이미도달") and "이미 닿았어요" in 이미["안내"]


@needs_data
def test_성장기는_추정하지_않고_측정값이_없으면_400():
    r = client.post("/fitness-age/eta", json={"age_gbn": "성장기", "sex": "F", "age": 15,
                                              "flexibility": 10, "strength": 150, "target": 14}).json()
    assert r["가능"] is False and "성장기" in r["안내"]
    assert client.post("/fitness-age/eta", json={"age_gbn": "성인", "sex": "M", "target": 30}).status_code == 400
