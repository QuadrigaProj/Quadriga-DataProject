"""운동 스타일 테스트(F1) — 문항 제공·채점·화면 진입."""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.main import app                   # noqa: E402
from backend import routines as rt             # noqa: E402
from backend import sports as sp               # noqa: E402
from backend import style_test as st           # noqa: E402

c = TestClient(app)

# 유형별로 그 유형이 나오는 답(설계 시 확인). 채점 데이터가 바뀌면 여기도 같이 고친다.
KNOWN = {
    "runner": [0, 2, 0, 2, 2, 3, 0, 0, 1],
    "builder": [1, 2, 0, 0, 2, 2, 0, 3, 1],
    "team": [0, 1, 2, 2, 1, 0, 1, 0, 0],
    "racket": [1, 1, 1, 0, 1, 0, 1, 2, 0],
    "rhythm": [0, 1, 1, 0, 1, 1, 1, 2, 0],
    "balance": [2, 1, 0, 0, 1, 1, 2, 1, 2],
    "walker": [2, 1, 1, 2, 0, 3, 2, 1, 2],
    "quick": [1, 0, 0, 0, 0, 0, 1, 0, 2],
}


def test_문항이_나온다():
    r = c.get("/style-test")
    assert r.status_code == 200
    body = r.json()
    qs = body["문항"]
    assert 8 <= len(qs) <= 10
    for q in qs:
        assert q["질문"]
        assert 2 <= len(q["선택지"]) <= 4
        assert all(isinstance(x, str) and x for x in q["선택지"])
        assert "점수" not in q                      # 채점 기준은 서버만 안다
    assert body["유형"]
    assert all("가중치" not in t for t in body["유형"])


def test_유형은_6개에서_8개():
    types = st.result_types()
    assert 6 <= len(types) <= 8
    ids = [t["id"] for t in types]
    assert len(ids) == len(set(ids))
    for t in types:
        assert t["이름"] and t["설명"]


def test_추천목적과_종목이_실제_데이터와_맞는다():
    table = sp.by_id()
    for t in st.result_types():
        assert t["추천목적"] in rt.PURPOSES, t["id"]
        assert t["추천목적"] in st.PURPOSE_KEY, t["id"]
        assert len(t["추천종목"]) == 3, t["id"]
        assert all(i in table for i in t["추천종목"]), t["id"]
        assert isinstance(t["하루투자분"], int) and t["하루투자분"] > 0, t["id"]


def test_채점은_결정적이다():
    a = KNOWN["runner"]
    r1 = c.post("/style-test/result", json={"answers": a})
    r2 = c.post("/style-test/result", json={"answers": a})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()
    assert st.score(a) == st.score(list(a))


def test_정해진_답은_정해진_유형():
    for tid, a in KNOWN.items():
        assert st.score(a)["유형"]["id"] == tid, tid


def test_모든_유형에_도달할_수_있다():
    ranges = [range(len(q["선택지"])) for q in st.questions()]
    reached = {st.score(list(x))["유형"]["id"] for x in itertools.product(*ranges)}
    assert reached == {t["id"] for t in st.result_types()}


def test_결과_응답_모양():
    a = KNOWN["balance"]
    r = c.post("/style-test/result", json={"answers": a})
    assert r.status_code == 200
    body = r.json()
    t = body["유형"]
    assert {"id", "이름", "설명", "추천목적", "목적키", "추천종목", "하루투자분"} <= set(t)
    assert t["목적키"] == "flex"
    assert t["추천목적"] == "유연성 강화"
    assert body["답변"] == a
    assert body["점수"] and all(0.0 <= v <= 1.0 for v in body["점수"].values())
    assert [s["id"] for s in body["종목"]] == t["추천종목"]
    for s in body["종목"]:
        assert s["이름"] and s["아이콘"]


@pytest.mark.parametrize("bad", [
    [0] * 8,                 # 개수 부족
    [0] * 10,                # 개수 초과
    [0] * 8 + [9],           # 범위 밖
    [0] * 8 + [-1],          # 음수
    [0] * 8 + ["a"],         # 문자열
    [0] * 8 + [True],        # bool
    [0] * 8 + [1.5],         # 실수
])
def test_잘못된_답은_400(bad):
    r = c.post("/style-test/result", json={"answers": bad})
    assert r.status_code == 400
    assert r.json()["detail"]


def test_화면에_테스트_진입_링크와_s10_이_있다():
    html = c.get("/").text
    assert html.count("뭘 골라야 할지 모르겠어요 → 운동 스타일 테스트") == 2   # s2 · s8
    assert 'id="s10"' in html
    assert "이 목적으로 시작" in html
    assert "이 종목 담기" in html
    assert "styleTest: null" in html
    assert "openStyleTest(" in html
    js = c.get("/js/api.js").text
    assert "/style-test" in js and "/style-test/result" in js
