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
