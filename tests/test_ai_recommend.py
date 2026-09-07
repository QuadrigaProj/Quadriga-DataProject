"""AI 루틴 추천 (H1).

실제 API 를 부르지 않는다. 가짜 응답으로 (1) 붙었을 때 순서·이유가 바뀌는지,
(2) 지어낸 응답을 버리는지, (3) 어떤 실패에도 점수 결과로 돌아오는지를 본다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.main import app  # noqa: E402
from backend import ai_recommend as air  # noqa: E402

client = TestClient(app)

후보 = [
    {"목적": "다이어트", "루틴명": "전신 HIIT", "동작수": 5, "체력요인": ["심폐지구력"],
     "이유": ["원래 이유"], "순위": 1},
    {"목적": "유연성 강화", "루틴명": "온몸 늘리기", "동작수": 5, "체력요인": ["유연성"],
     "이유": ["원래 이유"], "순위": 2},
]


class _Blk:
    def __init__(self, text): self.type, self.text = "text", text


class _Msg:
    def __init__(self, text, stop="end_turn"):
        self.content, self.stop_reason = [_Blk(text)], stop


def _fake_sdk(monkeypatch, text=None, stop="end_turn", boom=None):
    """anthropic 모듈이 없어도 되도록 통째로 가짜를 끼운다."""
    class _Messages:
        def create(self, **kw):
            if boom:
                raise boom
            return _Msg(text, stop)

    class _Client:
        def __init__(self, **kw): self.messages = _Messages()

    mod = type(sys)("anthropic")
    mod.Anthropic = _Client
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")


def test_키가_없으면_부르지_않는다(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert air.available() is False
    assert air.refine(후보, {}, "성인") is None


def test_붙으면_순서와_이유를_다듬는다(monkeypatch):
    _fake_sdk(monkeypatch, '{"순서":[1,0],"이유":{"1":["유연성이 급해요"]},"한마디":"천천히"}')
    r = air.refine(후보, {"약점": ["유연성"]}, "성인")
    assert [x["루틴명"] for x in r] == ["온몸 늘리기", "전신 HIIT"]
    assert r[0]["이유"] == ["유연성이 급해요"]
    assert r[0]["한마디"] == "천천히"
    assert r[0]["순위"] == 1 and r[1]["순위"] == 2
    assert all(x["출처"] == "ai" for x in r)
    # 이유를 안 준 후보는 원래 이유를 지킨다
    assert r[1]["이유"] == ["원래 이유"]


@pytest.mark.parametrize("본문", [
    '{"순서":[0,5]}',          # 없는 후보 번호
    '{"순서":[0,0]}',          # 중복
    '{"순서":["첫째"]}',        # 번호가 아님
    '{"순서":[]}',             # 빈 순서
    '{"이유":{"0":["x"]}}',    # 순서 없음
    '이건 JSON 이 아니에요',
    '',
])
def test_지어낸_응답은_통째로_버린다(monkeypatch, 본문):
    _fake_sdk(monkeypatch, 본문)
    assert air.refine(후보, {}, "성인") is None


def test_거절과_예외도_폴백한다(monkeypatch):
    _fake_sdk(monkeypatch, '{"순서":[0]}', stop="refusal")
    assert air.refine(후보, {}, "성인") is None
    _fake_sdk(monkeypatch, boom=RuntimeError("연결 실패"))
    assert air.refine(후보, {}, "성인") is None


def test_엔드포인트가_출처를_알려준다(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    d = client.get("/recommend/routines", params={"age_gbn": "성인", "limit": 3}).json()
    assert d["출처"] == "점수" and d["ai가능"] is False
    assert len(d["추천"]) == 3          # 키가 없어도 화면은 비지 않는다


def test_엔드포인트가_AI를_쓴다(monkeypatch):
    _fake_sdk(monkeypatch, '{"순서":[2,1,0],"이유":{"2":["이게 먼저예요"]}}')
    d = client.get("/recommend/routines",
                   params={"age_gbn": "성인", "limit": 3}).json()
    assert d["출처"] == "ai"
    assert d["추천"][0]["이유"] == ["이게 먼저예요"]
    # ai=0 이면 부르지 않는다
    d2 = client.get("/recommend/routines",
                    params={"age_gbn": "성인", "limit": 3, "ai": 0}).json()
    assert d2["출처"] == "점수"


def test_모델은_opus5다():
    assert air.MODEL == "claude-opus-5"


# ---------- I1 추천 2방식과 이용권 ----------

def _html():
    return client.get("/").text


def test_추천_방식이_둘이다():
    html = _html()
    assert 'data-mode="free"' in html and 'data-mode="ai"' in html
    assert "무료 추천" in html and "AI 추천" in html
    assert "function setRecoMode(mode)" in html


def test_한_번에_백원이다():
    html = _html()
    assert "const AI_PRICE = 100;" in html
    assert "1회 100원" in html


def test_미리_충전해_둘_수_있다():
    """I1: 프로필에서 잔액·결제 여부를 보고 미리 채워둔다."""
    html = _html()
    assert 'id="creditCard"' in html
    assert 'id="creditAmt"' in html and 'id="creditTimes"' in html
    assert "이용권 충전하기" in html
    assert "function renderCredit()" in html
    assert "const PAY_PACKS = [1000, 3000, 5000];" in html
    assert "credit: 0," in html and "creditLog: []," in html


def test_결제창은_카드정보를_묻지_않는다():
    """실제 PG 계약 전이라 모의 승인이다. 카드 번호를 받는 화면을 만들지 않는다."""
    html = _html()
    body = html.split("function paySheetHtml()")[1].split("\n}")[0]
    assert "시연용 모의 결제입니다" in body
    assert "<input" not in body
    for 금지 in ("카드번호", "card-number", "cvc", "유효기간"):
        assert 금지 not in html, 금지


def test_AI가_실제로_다듬었을_때만_값을_받는다():
    """폴백(출처='점수')이면 차감하지 않는다 — 안 쓴 것에 돈을 받지 않는다."""
    html = _html()
    body = html.split("async function renderRecommend()")[1].split("\nfunction paintRecommend")[0]
    assert "if (ai쓰기 && recoBy === 'ai')" in body
    assert "state.credit = Math.max(0, (state.credit || 0) - AI_PRICE);" in body
    assert "종류: '사용'" in body


def test_잔액이_모자라면_무료로_돌아간다():
    html = _html()
    body = html.split("async function renderRecommend()")[1].split("\nfunction paintRecommend")[0]
    assert "(state.credit || 0) < AI_PRICE" in body
    assert "이용권이 모자라요" in body


def test_키가_없으면_AI방식이_잠긴다():
    html = _html()
    body = html.split("function paintRecoMode()")[1].split("\n}")[0]
    assert "ai.disabled = !recoAiReady;" in body
    assert "관리자가 키를 등록하면 켜져요" in body
