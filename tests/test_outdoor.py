"""오늘 날씨에 맞춘 대안 (backend/outdoor.py).

바깥 서비스는 부르지 않는다. 날씨를 흉내 내서 규칙과 안내만 본다.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.main import app  # noqa: E402
from backend import outdoor, season as ssn  # noqa: E402

client = TestClient(app)

맑음 = {"하늘": "맑음", "최고": 24, "최저": 15, "습도": 55, "강수확률": 10, "기준": "서울"}
비 = dict(맑음, 하늘="비", 강수확률=80)
폭염 = dict(맑음, 최고=34)
한파 = dict(맑음, 최고=2, 최저=-7)
후텁 = dict(맑음, 최고=30, 습도=90)
비올듯 = dict(맑음, 강수확률=45)

러닝 = {"출처": "종목", "id": "running", "동작": "러닝"}
수영 = {"출처": "종목", "id": "swimming", "동작": "수영"}
걷기 = {"출처": "기록", "id": "walk", "동작": "걷기"}
공식 = {"출처": "동작", "코드": "Vx", "동작": "스쿼트"}


@pytest.mark.parametrize("날씨,실외", [(맑음, "괜찮음"), (비, "실내"), (폭염, "실내"),
                                    (한파, "조심"), (후텁, "조심"), (비올듯, "조심"), (None, "모름")])
def test_밖에서_해도_되는지(날씨, 실외):
    assert outdoor.verdict(날씨)["실외"] == 실외


def test_까닭을_말한다():
    v = outdoor.verdict(dict(맑음, 하늘="눈", 최저=-8))
    assert v["실외"] == "실내" and "눈 예보" in v["이유"] and any("준비운동" in x for x in v["이유"])


def test_밖에서_하는_동작만_고른다():
    assert outdoor.outdoor_of(러닝)[0] == "러닝"
    assert outdoor.outdoor_of(걷기)[0] == "걷기"
    assert outdoor.outdoor_of(수영) is None          # 수영은 실내다
    assert outdoor.outdoor_of(공식) is None          # 공식 동작은 집에서 하는 것이다
    assert outdoor.outdoor_of({"출처": "종목", "id": "없는것"}) is None


def test_비가_오면_실내_대안을_앞세운다():
    r = outdoor.alternatives([러닝, 수영, 공식], 비)
    assert [x["동작"] for x in r["실외동작"]] == ["러닝"]
    assert len(r["대안"]) == 1
    a = r["대안"][0]
    assert a["동작"] == "러닝" and a["대신"] == "러닝머신 25분" and a["또는"]
    assert "비 예보" in a["왜"] and a["권함"] == "실내로"


def test_괜찮으면_대안_없이_밖에서_해도_좋다고만():
    r = outdoor.alternatives([러닝], 맑음)
    assert r["실외동작"] and r["대안"] == [] and r["판정"]["실외"] == "괜찮음"


def test_밖에서_하는_동작이_없으면_아무_말도_없다():
    r = outdoor.alternatives([수영, 공식], 비)
    assert r["실외동작"] == [] and r["대안"] == []


def test_날씨를_모르면_괜찮다고_하지_않는다():
    r = outdoor.alternatives([러닝], None)
    assert r["판정"]["실외"] == "모름" and r["대안"] == []


def test_같은_날_같은_자리는_한_번만_묻는다(monkeypatch):
    부른수 = {"n": 0}
    def _fw(날짜, 위도=None, 경도=None):
        부른수["n"] += 1; return dict(맑음)
    monkeypatch.setattr(ssn, "fetch_weather", _fw)
    outdoor._cache.clear()
    outdoor.today_weather(37.5, 127.0); outdoor.today_weather(37.51, 127.04)   # 0.1도 안이면 같은 자리
    outdoor.today_weather(None, None); outdoor.today_weather(None, None)
    assert 부른수["n"] == 2
    outdoor._cache.clear()


def test_엔드포인트는_로그인_없이_값_없이(monkeypatch):
    monkeypatch.setattr(ssn, "fetch_weather", lambda *a, **k: dict(비))
    outdoor._cache.clear()
    d = TestClient(app).post("/routine/weather-check", json={"steps": [러닝, 공식]}).json()
    assert d["날짜"] == dt.date.today().isoformat()
    assert d["날씨"]["하늘"] == "비" and d["판정"]["실외"] == "실내"
    assert d["대안"][0]["대신"] == "러닝머신 25분"
    outdoor._cache.clear()


def test_엔드포인트는_스무_개까지():
    r = client.post("/routine/weather-check", json={"steps": [러닝] * 21})
    assert r.status_code == 422
