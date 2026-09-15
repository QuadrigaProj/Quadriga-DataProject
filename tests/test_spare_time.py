"""짬시간 추천 — 남는 칸을 찾고 거기서 할 것을 고른다."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import spare_time as spare, sports as sp   # noqa: E402
from backend.main import app                            # noqa: E402

client = TestClient(app)


def _종목(*이름들) -> list[str]:
    return [s["id"] for s in sp.catalog()["종목"] if s["이름"] in 이름들]


# ---------- 남는 칸 ----------

def test_바쁜_시간을_빼고_남는_칸을_준다():
    칸 = spare.free_slots([{"시작": "09:00", "끝": "18:00"}])
    assert [(c["시작"], c["끝"]) for c in 칸] == [("07:00", "09:00"), ("18:00", "22:00")]
    assert 칸[0]["분"] == 120


def test_겹치거나_뒤죽박죽이어도_된다():
    """사람이 적는 값이다. 순서와 겹침을 앱이 정리해야 한다."""
    칸 = spare.free_slots([{"시작": "13:00", "끝": "15:00"},
                          {"시작": "09:00", "끝": "14:00"}])
    assert [(c["시작"], c["끝"]) for c in 칸] == [("07:00", "09:00"), ("15:00", "22:00")]


def test_너무_짧은_칸은_주지_않는다():
    """옮겨 다니다 끝나는 시간에 운동하라고 하면 안 된다."""
    칸 = spare.free_slots([{"시작": "07:00", "끝": "12:00"},
                          {"시작": "12:10", "끝": "22:00"}])
    assert 칸 == []


def test_모양이_틀린_줄은_건너뛴다():
    칸 = spare.free_slots([{"시작": "아홉시", "끝": "18:00"},
                          {"끝": "18:00"},
                          {"시작": "09:00", "끝": "18:00"}])
    assert [(c["시작"], c["끝"]) for c in 칸] == [("07:00", "09:00"), ("18:00", "22:00")]


def test_거꾸로_된_줄은_없는_것으로_본다():
    assert spare.free_slots([{"시작": "18:00", "끝": "09:00"}])[0]["분"] == 15 * 60


# ---------- 무엇을 할지 ----------

def test_짧은_칸에는_종목을_넣지_않는다():
    """러닝·수영은 오가고 준비하는 시간이 있다."""
    나온것 = spare.suggest_for(20, sports_ids=_종목("수영", "등산"))
    assert 나온것 and all(x["갈래"] != "종목" for x in 나온것)


def test_넉넉하면_고른_종목을_그대로_넣는다():
    나온것 = spare.suggest_for(90, sports_ids=_종목("수영", "등산"))
    이름 = [x["이름"] for x in 나온것]
    assert "수영" in 이름 or "등산" in 이름
    assert any(x["갈래"] == "종목" for x in 나온것)


def test_고른_종목이_없으면_비슷한_류로_채운다():
    """'안 될 것 같다면 비슷한 류의 스포츠나 운동' — 갈래를 밝혀서 넣는다."""
    나온것 = spare.suggest_for(90, sports_ids=_종목("수영"))
    갈래 = {x["갈래"] for x in 나온것}
    assert "종목" in 갈래
    assert "비슷한 종목" in 갈래


def test_뒤처지는_요인을_먼저_고른다():
    나온것 = spare.suggest_for(20, weak=["유연성"])
    assert 나온것[0]["왜"].startswith("뒤처지는 유연성")


def test_아무것도_안_골라도_할_것은_준다():
    """고른 종목도 약점도 없을 수 있다. 그때도 빈 화면을 두지 않는다."""
    assert spare.suggest_for(20)


def test_없는_운동을_지어내지_않는다():
    from backend import workout_items as wi
    있는것 = {x["이름"] for x in wi.catalog()["종목"]}
    있는것 |= {s["이름"] for s in sp.catalog()["종목"]}
    for 분 in (15, 30, 60, 120):
        for x in spare.suggest_for(분, sports_ids=_종목("수영", "등산"), weak=["근력"]):
            assert x["이름"] in 있는것, x


# ---------- 요일별 ----------

def test_안_적은_요일은_결과에도_없다():
    """하루가 통째로 빈다고 단정하면, 안 적은 사람에게 온종일 운동하라고 하는 셈이다."""
    p = spare.plan({"월": [{"시작": "09:00", "끝": "18:00"}]})
    assert set(p) == {"월"}


def test_요일별로_칸과_할_것을_함께_준다():
    p = spare.plan({"월": [{"시작": "09:00", "끝": "18:00"}]},
                   sports_ids=_종목("수영"), limit=2)
    assert len(p["월"]) == 2
    assert all(c["추천"] and len(c["추천"]) <= 2 for c in p["월"])


# ---------- API ----------

def test_라우터가_요일별_계획을_준다():
    r = client.post("/spare-time/plan", json={
        "바쁜시간": {"월": [{"시작": "09:00", "끝": "18:00"}]},
        "sports": _종목("수영"), "weak": ["근력"], "limit": 3})
    assert r.status_code == 200
    d = r.json()
    assert d["요일"] == list(spare.WEEKDAYS)
    assert set(d["요일별"]) == {"월"}


def test_모르는_요일은_버린다():
    r = client.post("/spare-time/plan", json={
        "바쁜시간": {"월": [{"시작": "09:00", "끝": "18:00"}], "먼데이": []}})
    assert set(r.json()["요일별"]) == {"월"}


def test_일정을_안_주면_아무것도_주지_않는다():
    r = client.post("/spare-time/plan", json={})
    assert r.status_code == 200 and r.json()["요일별"] == {}
