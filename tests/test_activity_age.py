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


# ---------- K1. 날짜별 체력나이 · 그날 잰 몸 상태 ----------

def test_그날_잰_몸무게로_체성분을_다시_계산한다():
    """추정이 아니라 그날 실제로 잰 값이라 편차 제한을 걸지 않는다."""
    그냥 = 부르기(sex="M", 활동={})
    무거움 = 부르기(sex="M", 활동={}, 키=176, 몸무게=95)
    assert "잰체성분" in 무거움 and "잰체성분" not in 그냥
    assert 무거움["항목별"]["체성분"] == 무거움["잰체성분"]
    # BMI 30 대는 체성분 환산나이가 올라간다 → 체력나이도 올라간다
    assert 무거움["체력나이"] > 그냥["체력나이"]


def test_체지방률이_있으면_그쪽을_쓴다():
    """체지방률이 BMI 보다 직접적이다."""
    bmi만 = 부르기(sex="M", 활동={}, 키=176, 몸무게=95)
    둘다 = 부르기(sex="M", 활동={}, 키=176, 몸무게=95, 체지방률=12)
    assert 둘다["잰체성분"] != bmi만["잰체성분"]
    assert 둘다["체력나이"] < bmi만["체력나이"]      # 체지방률이 낮으니 더 젊다


def test_성별이_없으면_몸_상태를_쓰지_않는다():
    """분포는 성별로 갈린다. 성별 없이 환산하면 근거가 없다."""
    out = 부르기(활동={}, 키=176, 몸무게=95)      # sex 없음
    assert "잰체성분" not in out
    assert out["항목별"]["체성분"] == 25.0


def test_말도_안_되는_몸무게는_422로_막는다():
    r = client.post("/fitness-age/activity",
                    json={**성인, "sex": "M", "활동": {}, "키": 176, "몸무게": 9999})
    assert r.status_code == 422


# ---------- 여러 날 한 번에 ----------

def 날(date, **덮어쓰기):
    return {**성인, "sex": "M", "date": date, "활동": {}, **덮어쓰기}


def test_여러_날을_한_번에_돌려준다():
    r = client.post("/fitness-age/activity/days", json=[
        날("2026-09-01", 활동={"근지구력": 3}),
        날("2026-09-05", 활동={"근지구력": 10}),
    ])
    assert r.status_code == 200
    rows = r.json()
    assert [x["date"] for x in rows] == ["2026-09-01", "2026-09-05"]
    # 더 많이 운동한 날이 더 젊다
    assert rows[1]["체력나이"] < rows[0]["체력나이"]


def test_계산할_수_없는_날은_빼고_돌려준다():
    """한 날이 잘못됐다고 나머지까지 못 받으면 화면이 통째로 빈다."""
    r = client.post("/fitness-age/activity/days", json=[
        날("2026-09-01"),
        {**날("2026-09-02"), "항목별": {}},      # 기준이 없는 날
        날("2026-09-03"),
    ])
    assert [x["date"] for x in r.json()] == ["2026-09-01", "2026-09-03"]


def test_빈_목록도_받는다():
    assert client.post("/fitness-age/activity/days", json=[]).json() == []


def test_너무_많으면_거절한다():
    r = client.post("/fitness-age/activity/days",
                    json=[날(f"2026-09-{i:02d}") for i in range(1, 29)] * 15)
    assert r.status_code == 400

