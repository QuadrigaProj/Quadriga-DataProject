"""루틴 추천 (G7).

추천을 지어내지 않는다 — 이미 있는 250개 고정 루틴 중에서 고르고 근거를 함께 낸다.
여기서는 "점수가 근거대로 움직이는가" 와 "근거 없는 추천이 없는가" 를 본다.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.main import app  # noqa: E402
from backend import recommend as rc, routines as rt  # noqa: E402

client = TestClient(app)


def test_추천이_나온다():
    r = client.get("/recommend/routines", params={"age_gbn": "성인", "limit": 5})
    assert r.status_code == 200
    d = r.json()
    assert len(d["추천"]) == 5
    for x in d["추천"]:
        assert x["목적"] in rt.PURPOSES
        assert x["루틴명"] and x["이유"]        # 근거 없는 추천은 내지 않는다


def test_입력이_없어도_안전하다():
    """첫 점검 전에도 화면이 비지 않아야 한다."""
    d = rc.for_user("성인", limit=3)
    assert len(d["추천"]) == 3
    assert all(x["이유"] for x in d["추천"])


def test_약점을_다루는_목적이_위로_온다():
    없음 = rc.for_user("성인", limit=5)["추천"]
    있음 = rc.for_user("성인", weak=["심폐지구력"], limit=5)["추천"]
    상위목적 = 있음[0]["목적"]
    assert "심폐지구력" in rt.load()["config"]["purpose_factors"][상위목적]
    assert 있음[0]["점수"] > 없음[0]["점수"]


def test_스타일_테스트_결과가_점수를_올린다():
    기본 = {x["목적"]: x["점수"] for x in rc.for_user("성인", limit=5)["추천"]}
    반영 = {x["목적"]: x["점수"] for x in
           rc.for_user("성인", style_purpose="유연성 강화", limit=5)["추천"]}
    assert 반영["유연성 강화"] > 기본["유연성 강화"]


def test_고른_종목이_점수와_주의부위에_반영된다():
    d = rc.for_user("성인", sports=["running", "tennis"], limit=5)
    assert d["참고"]["종목요인"]                  # 종목 → 체력요인
    assert d["조심할부위"]                        # 종목 → 조심할 부위
    assert any("고른 종목" in y for x in d["추천"] for y in x["이유"])


def test_목표_격차가_크면_숨찬_운동에_무게를_준다():
    작음 = {x["목적"]: x["점수"] for x in rc.for_user("성인", target_gap=1, limit=5)["추천"]}
    큼 = {x["목적"]: x["점수"] for x in rc.for_user("성인", target_gap=9, limit=5)["추천"]}
    assert 큼["다이어트"] > 작음["다이어트"]       # 심폐·근지구력 목적


def test_목적이_골고루_섞인다():
    """같은 목적만 다섯 개 나오면 고를 맛이 없다."""
    추천 = rc.for_user("성인", weak=["심폐지구력"], limit=5)["추천"]
    assert len({x["목적"] for x in 추천}) >= 4


def test_연령대마다_루틴이_다르다():
    성인 = {x["루틴명"] for x in rc.for_user("성인", limit=5)["추천"]}
    어르신 = {x["루틴명"] for x in rc.for_user("어르신", limit=5)["추천"]}
    assert 성인 != 어르신


def test_화면에_루틴_추천이_붙어_있다():
    html = client.get("/").text
    assert 'id="s12"' in html
    assert "label: '루틴 추천'" in html
    assert "async function renderRecommend()" in html
    # '다음 추천' 은 H3·H4 에서 네 버튼으로 갈라졌다
    assert "function easierRecommend()" in html
    assert "function harderRecommend()" in html
    assert "function backRecommend()" in html
    assert "async function useRecommend()" in html


# ---------- H2·H3·H4 상세 안내와 네 버튼 ----------

def test_추천에_동작이_자세히_들어온다():
    """H2: 어떤 루틴인지 종목과 단위수까지 한 페이지에 보여줄 재료."""
    x = rc.for_user("성인", limit=3, week=5)["추천"][0]
    assert x["steps"], "동작 목록이 없다"
    assert x["예상시간분"]
    단계 = {s["단계"] for s in x["steps"]}
    assert {"준비운동", "본운동", "정리운동"} <= 단계
    for s in x["steps"]:
        assert s["동작"] and s["수행량"]          # 이름과 단위수
        assert "체력요인" in s and "도구" in s


def test_수행량은_주차에_따라_늘어난다():
    앞 = rc.for_user("성인", limit=1, week=1)["강도"]
    뒤 = rc.for_user("성인", limit=1, week=10)["강도"]
    assert 뒤["세트"] >= 앞["세트"]
    assert 뒤["반복"] > 앞["반복"]


def test_난이도가_붙고_쉬움과_어려움이_모두_나온다():
    """H3: '더 쉽게 / 더 어렵게' 로 오가려면 폭이 있어야 한다."""
    xs = rc.for_user("성인", limit=12)["추천"]
    점수 = [x["난이도점수"] for x in xs]
    assert all(0 <= p <= 1 for p in 점수)
    assert max(점수) > min(점수), "난이도가 모두 같으면 오갈 수 없다"
    assert {x["난이도"] for x in xs} & {"쉬움", "보통", "어려움"}


def test_난이도_계산은_구성을_따른다():
    쉬움 = rc.difficulty([{"단계": "본운동", "체력요인": ["유연성"], "도구": "맨몸", "부담부위": []}])
    어려움 = rc.difficulty([{"단계": "본운동", "체력요인": ["심폐지구력"], "도구": "의자",
                          "부담부위": ["무릎"]}])
    assert 쉬움 == 0.0 and 어려움 == 1.0
    assert rc.difficulty_label(쉬움) == "쉬움"
    assert rc.difficulty_label(어려움) == "어려움"


def test_화면에_네_버튼이_순서대로_있다():
    """H4 최종 순서: 이전 루틴, 더 쉬운 루틴, 더 어려운 루틴, 이 루틴으로 시작."""
    html = client.get("/").text
    # 기록 화면에도 같은 이름의 .rec-actions 가 있어 추천 카드 쪽으로 좁힌다
    card = html.split("function paintRecommend()")[1]
    actions = card.split('<div class="rec-actions">')[1].split("</div>")[0]
    자리 = [actions.find(t) for t in
           ("이전 루틴", "더 쉬운 루틴", "더 어려운 루틴", "이 루틴으로 시작")]
    assert all(i >= 0 for i in 자리), 자리
    assert 자리 == sorted(자리), "버튼 순서가 요구와 다르다"
