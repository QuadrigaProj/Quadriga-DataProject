"""루틴 추천 (G7).

추천을 지어내지 않는다 — 이미 있는 250개 고정 루틴 중에서 고르고 근거를 함께 낸다.
여기서는 "점수가 근거대로 움직이는가" 와 "근거 없는 추천이 없는가" 를 본다.
"""
from __future__ import annotations

import re
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


def test_종목_반영은_목적_전체가_아니라_그_요인을_다루는_루틴에_실제로_붙는다():
    """예전엔 맞은종목이 목적(purpose) 단위로만 붙어서, 같은 목적 안이면 그 요인을
    실제로 다루든 말든 모든 루틴이 똑같은 점수를 받았다 — 결과가 홈트·기초체력 몇
    개로만 쏠리고 고른 종목이 진짜 반영됐는지 알 수 없었다. 같은 루틴을 놓고
    종목 요인을 껐다 켰다 하면서, 그 루틴 '자체'가 점수를 더 받는지 직접 본다."""
    꺼짐 = rc.score("성인", limit=999)
    켜짐 = {(x["목적"], x["루틴번호"]): x for x in rc.score("성인", sport_factors=["평형성"], limit=999)}

    맞는루틴 = next(x for x in 꺼짐 if "평형성" in x["체력요인"])
    후 = 켜짐[(맞는루틴["목적"], 맞는루틴["루틴번호"])]
    assert 후["점수"] == round(맞는루틴["점수"] + 0.8, 2)
    assert any("고른 종목에 필요한" in y and "평형성" in y for y in 후["이유"])

    # 그 요인이 없는 루틴은 종목을 켜도 그대로다
    안맞는루틴 = next(x for x in 꺼짐 if "평형성" not in x["체력요인"])
    후2 = 켜짐[(안맞는루틴["목적"], 안맞는루틴["루틴번호"])]
    assert 후2["점수"] == 안맞는루틴["점수"]


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
    actions = card.split('<div class="reco-actions">')[1].split("</div>")[0]
    자리 = [actions.find(t) for t in
           ("이전 루틴", "더 쉬운 루틴", "더 어려운 루틴", "이 루틴으로 시작")]
    assert all(i >= 0 for i in 자리), 자리
    assert 자리 == sorted(자리), "버튼 순서가 요구와 다르다"


def test_네_버튼이_같은_크기_같은_모양이다():
    """I2: 넷 다 .reco-btn 한 클래스만 쓴다 — 폭·높이·모서리가 같아진다."""
    html = client.get("/").text
    card = html.split("function paintRecommend()")[1]
    actions = card.split('<div class="reco-actions">')[1].split("</div>")[0]
    btns = re.findall(r'class="([^"]*reco-btn[^"]*)"', actions)
    assert len(btns) == 4, btns
    # 색만 다르고(마지막 go) 크기·모양을 정하는 클래스는 하나뿐이다
    assert {c.replace(" go", "").strip() for c in btns} == {"reco-btn"}
    assert "wide" not in actions            # 한 칸을 통째로 먹던 버튼이 없다
    assert "btn-primary" not in actions and "btn-ghost" not in actions


def test_기록_화면_버튼과_이름이_겹치지_않는다():
    """전에는 .rec-actions 를 두 화면이 함께 써서 나중 정의가 앞을 덮었다."""
    html = client.get("/").text
    assert html.count(".reco-actions{") == 1
    assert html.count(".rec-actions{") == 1
