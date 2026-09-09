"""루틴 추천 (G7).

추천을 지어내지 않는다 — 이미 있는 200개 KSPO 루틴 중에서 고르고 근거를 함께 낸다.
여기서는 "점수가 근거대로 움직이는가" 와 "근거 없는 추천이 없는가" 를 본다.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import pytest
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
    # 이제는 '고른 종목' 대신 고른 종목의 이름을 그대로 적는다
    이유들 = " ".join(y for x in d["추천"] for y in x["이유"])
    assert "러닝" in 이유들 or "테니스" in 이유들


def test_종목_반영은_목적_전체가_아니라_그_요인을_다루는_루틴에_실제로_붙는다():
    before = rc.score("어르신", limit=999)
    after = {(x["목적"], x["루틴번호"]): x for x in rc.score("어르신", sport_factors=["심폐지구력"], limit=999)}
    matches = []
    for routine in before:
        hit = "심폐지구력" in routine["체력요인"]
        matches.append(hit)
        purpose_hit = "심폐지구력" in rc.rt.load()["config"]["purpose_factors"][routine["목적"]]
        updated = after[(routine["목적"], routine["루틴번호"])]
        assert updated["점수"] == round(routine["점수"] + 1.5 * purpose_hit + 0.8 * hit, 2)
    assert any(matches) and not all(matches)


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


def test_버튼이_모두_같은_크기_같은_모양이다():
    """I2: 다 .reco-btn 한 클래스만 쓴다 — 폭·높이·모서리가 같아진다.

    처음엔 네 개였고 그 뒤로 '자세히 도전하기'·'AI 추천 다시 받기' 가 붙었다.
    개수를 못 박아 두면 버튼이 늘 때마다 이 테스트가 깨진다. 지키려는 것은
    개수가 아니라 '크기·모양을 정하는 클래스가 하나뿐인가' 다.
    """
    html = client.get("/").text
    card = html.split("function paintRecommend()")[1]
    actions = card.split('<div class="reco-actions">')[1].split("</div>")[0]
    btns = re.findall(r'class="([^"]*reco-btn[^"]*)"', actions)
    assert len(btns) >= 4, btns
    # 색만 다르고(마지막 go) 크기·모양을 정하는 클래스는 하나뿐이다
    assert {c.replace(" go", "").strip() for c in btns} == {"reco-btn"}
    assert "wide" not in actions            # 한 칸을 통째로 먹던 버튼이 없다
    assert "btn-primary" not in actions and "btn-ghost" not in actions


def test_기록_화면_버튼과_이름이_겹치지_않는다():
    """전에는 .rec-actions 를 두 화면이 함께 써서 나중 정의가 앞을 덮었다."""
    html = client.get("/").text
    assert html.count(".reco-actions{") == 1
    assert html.count(".rec-actions{") == 1


# ---------- 목적 수보다 많이 달라고 해도 끝난다 ----------

@pytest.mark.parametrize("limit", [1, 5, 6, 12, 30, 999])
def test_어떤_개수를_달라고_해도_끝난다(limit):
    """목적은 다섯인데 화면은 12개를 부른다.

    한때 '이미 나온 목적' 을 골고루 전체에서 다시 뽑는 바람에, 목적이 한 번씩
    다 나온 뒤로는 아무것도 못 담으면서 남은 것도 그대로라 while 이 영영
    끝나지 않았다. 추천이 통째로 멈춰 있었다.
    """
    시작 = time.time()
    결과 = rc.score("성인", limit=limit)
    걸린시간 = time.time() - 시작
    assert 걸린시간 < 5, f"{걸린시간:.1f}초나 걸렸다 — 멈춘 것과 다름없다"
    assert 결과, "하나도 못 골랐다"
    assert len(결과) <= limit
    assert [x["순위"] for x in 결과] == list(range(1, len(결과) + 1))


def test_달라는_만큼_채운다():
    """다섯 개까지만 나오면 '더 쉬운 루틴' 으로 옮겨 갈 자리가 없다."""
    assert len(rc.score("성인", limit=12)) == 12


def test_같은_목적이_이어서_나오지_않는다():
    """한 바퀴에 목적마다 하나씩 — 같은 목적이 셋씩 이어지면 고를 맛이 없다."""
    목적들 = [x["목적"] for x in rc.score("성인", limit=12)]
    이어짐 = [i for i in range(1, len(목적들)) if 목적들[i] == 목적들[i - 1]]
    assert not 이어짐, 목적들


def test_더_달라고_해도_있는_만큼만():
    """없는 루틴을 지어내지 않는다."""
    전부 = rc.score("성인", limit=999)
    assert len(전부) == len(rc.score("성인", limit=len(전부) + 50))
    번호 = [(x["목적"], x["루틴번호"]) for x in 전부]
    assert len(번호) == len(set(번호)), "같은 루틴이 두 번 나왔다"
