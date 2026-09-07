"""운동 기록을 반영한 체력나이 (I3).

핵심은 "얼마나 좋아지나" 가 아니라 **얼마나 안 움직이나** 다.
운동만으로 체력나이를 다시 산출할 근거가 없으니, 마지막 측정의 편차 안에서만
움직여야 하고 측정한 항목값은 손대지 않아야 한다.
"""

import pytest
from fastapi.testclient import TestClient

from backend import fitness_age as fa
from backend.main import app

client = TestClient(app)

성인 = {"age_gbn": "성인", "age": 30,
        "항목별": {"유연성": 47, "근지구력": 62, "체성분": 25}, "신뢰구간": 3}


def 부르기(**덮어쓰기):
    body = {**성인, **덮어쓰기}
    r = client.post("/fitness-age/activity", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_운동이_없으면_측정값_그대로다():
    out = 부르기(활동={})
    assert out["당김"] == 0
    assert out["체력나이"] == out["기준나이"]
    assert out["활동반영"] == {}


def test_운동한_만큼_체력나이가_내려간다():
    적게 = 부르기(활동={"근지구력": 3})
    많이 = 부르기(활동={"근지구력": 12})
    assert 적게["당김"] > 0
    assert 많이["당김"] > 적게["당김"]
    assert 많이["체력나이"] < 적게["체력나이"] < 적게["기준나이"]


def test_아무리_운동해도_측정_편차를_넘지_않는다():
    # 세 항목 전부를 1년 내내 했다고 해도 편차(3세) 밖으로는 못 나간다
    out = 부르기(활동={"유연성": 999, "근지구력": 999, "체성분": 999})
    assert out["당김"] == pytest.approx(3.0)
    assert out["기준나이"] - out["체력나이"] == pytest.approx(3.0, abs=0.05)


def test_편차가_0이면_한_발짝도_안_움직인다():
    out = 부르기(신뢰구간=0, 활동={"근지구력": 999})
    assert out["당김"] == 0
    assert out["체력나이"] == out["기준나이"]


def test_측정한_항목값은_손대지_않는다():
    out = 부르기(활동={"근지구력": 999})
    assert out["항목별"] == {"유연성": 47.0, "근지구력": 62.0, "체성분": 25.0}


def test_한_항목만_해서는_전체를_끌고_가지_못한다():
    하나 = 부르기(활동={"근지구력": 999})
    전부 = 부르기(활동={"유연성": 999, "근지구력": 999, "체성분": 999})
    # 항목이 3개이므로 하나만 하면 당김도 1/3
    assert 하나["당김"] == pytest.approx(전부["당김"] / 3, abs=0.05)


def test_재지_않은_요인은_무시한다():
    # 심폐지구력은 이 사용자의 항목별에 없다 — 없는 값을 만들어내지 않는다
    out = 부르기(활동={"심폐지구력": 999})
    assert out["활동반영"] == {}
    assert out["당김"] == 0


def test_성장기는_반대로_올라간다():
    out = 부르기(age_gbn="성장기", age=15,
                항목별={"유연성": 13, "순발력": 17}, 신뢰구간=2,
                활동={"유연성": 20})
    assert out["체력나이"] > out["기준나이"]


def test_측정_결과가_없으면_400():
    r = client.post("/fitness-age/activity",
                    json={"age_gbn": "성인", "항목별": {}, "활동": {"근지구력": 5}})
    assert r.status_code == 400


@pytest.mark.parametrize("나쁜값", ["열흘", None, {}, [], float("nan")])
def test_날_수가_이상해도_터지지_않는다(나쁜값):
    out = fa.activity_adjusted(성인["항목별"], 3, {"근지구력": 나쁜값}, "성인", 30)
    assert out["체력나이"] is not None
    assert out["당김"] == 0
