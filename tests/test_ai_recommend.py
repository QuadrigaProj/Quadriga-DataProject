"""AI 루틴 추천 (H1).

실제 API 를 부르지 않는다. 가짜 응답으로 (1) 붙었을 때 순서·이유가 바뀌는지,
(2) 지어낸 응답을 버리는지, (3) 어떤 실패에도 점수 결과로 돌아오는지를 본다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.main import app  # noqa: E402
from backend import ai_recommend as air  # noqa: E402
from backend import auth, billing, community  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    """AI 추천은 이용권을 서버 원장에서 깎는다 — DB 가 있어야 한다."""
    import tempfile
    if auth.is_postgres():
        with auth.db() as con:
            auth.init_db(); community.init_db(); billing.init_db()
            for t in ("credit_ledger", "pay_orders", "measurements", "sessions",
                      "oauth_states", "users"):
                con.execute(f"DELETE FROM {t}")
    else:
        monkeypatch.setattr(auth, "DB_PATH", Path(tempfile.mkdtemp()) / "t.db")
        auth.init_db(); community.init_db(); billing.init_db()
    yield


def _paid(credit: int = 1000) -> TestClient:
    """이용권을 가진 로그인 사용자."""
    c = TestClient(app)
    c.post("/auth/signup", json={"email": "a@x.com", "password": "pw12345678",
                                 "display_name": "가"})
    if credit:
        billing.charge(1, credit, credit, f"seed-{credit}")
    return c

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
    a = _paid(1000)
    d = a.get("/recommend/routines", params={"age_gbn": "성인", "limit": 3}).json()
    assert d["출처"] == "ai"
    assert d["추천"][0]["이유"] == ["이게 먼저예요"]
    assert d["잔액"] == 900                     # 서버가 100원 깎았다
    # ai=0 이면 부르지 않고 깎지도 않는다
    d2 = a.get("/recommend/routines",
               params={"age_gbn": "성인", "limit": 3, "ai": 0}).json()
    assert d2["출처"] == "점수" and d2["잔액"] == 900


def test_이용권이_없으면_AI를_부르지_않는다(monkeypatch):
    """부르고 나서 못 받으면 우리만 돈을 쓴다."""
    _fake_sdk(monkeypatch, '{"순서":[2,1,0],"이유":{"2":["이게 먼저예요"]}}')
    a = _paid(0)
    d = a.get("/recommend/routines", params={"age_gbn": "성인", "limit": 3}).json()
    assert d["출처"] == "점수" and d["잔액"] == 0
    assert "이용권이 모자라요" in d["안내"]
    assert len(d["추천"]) == 3                  # 화면은 비지 않는다


def test_로그인하지_않으면_AI를_부르지_않는다(monkeypatch):
    _fake_sdk(monkeypatch, '{"순서":[2,1,0],"이유":{"2":["이게 먼저예요"]}}')
    d = TestClient(app).get("/recommend/routines",
                            params={"age_gbn": "성인", "limit": 3}).json()
    assert d["출처"] == "점수" and d["잔액"] == 0
    assert "로그인" in d["안내"]


def test_폴백이면_한_푼도_안_깎는다(monkeypatch):
    """AI 를 불렀지만 응답을 버렸다면 사용자에게 받지 않는다."""
    _fake_sdk(monkeypatch, "이건 JSON 이 아니다")
    a = _paid(1000)
    d = a.get("/recommend/routines", params={"age_gbn": "성인", "limit": 3}).json()
    assert d["출처"] == "점수"
    assert d["잔액"] == 1000
    assert a.get("/credit").json()["잔액"] == 1000


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
    assert "선결제하기" in html                      # K3 에서 문구가 바뀌었다
    assert "function renderCredit()" in html
    assert "{ 이용권: 1000, 결제: 700,  할인: 30 }," in html
    assert "credit: 0," in html and "creditLog: []," in html


def test_결제창은_카드정보를_묻지_않는다():
    """카드번호·CVC·계좌번호를 받는 입력칸을 만들지 않는다.

    실제 서비스에서 그건 PG사 결제창이 받는다(PCI-DSS). 우리가 받으면 사고다.
    J2 에서 약관 동의 체크박스가 생겼으므로 "입력칸이 하나도 없다" 가 아니라
    "카드·계좌를 받는 입력칸이 없다" 로 본다. 설명하는 주석에는 그 낱말이
    나올 수 있으니, 낱말 검색이 아니라 **input 태그와 placeholder** 를 본다.
    """
    html = _html()

    민감 = ("카드번호", "card-number", "cardnumber", "cvc", "유효기간",
          "expiry", "계좌번호", "account-number", "accountnumber")

    for tag in re.findall(r"<input[^>]*>", html, re.I):
        낮 = tag.lower()
        assert not any(w in 낮 for w in 민감), tag
        # 카드 입력을 부르는 자동완성도 없어야 한다
        assert "autocomplete=\"cc-" not in 낮, tag

    for ph in re.findall(r'placeholder="([^"]*)"', html):
        낮 = ph.lower()
        assert not any(w in 낮 for w in 민감), ph

    # 결제창 안의 input 은 체크박스(약관 동의)뿐이어야 한다
    결제창 = html.split("function payWayHtml()")[1].split("function pickPay(v)")[0]
    타입 = re.findall(r'<input type="([a-z]+)', 결제창)
    assert 타입 == ["checkbox"], 타입

    # 카드·계좌 정보를 우리가 받지 않는다고 화면에 적어야 한다
    assert "이 앱이 받지" in 결제창
    assert "PG사 결제창이 받습니다" in 결제창


def test_AI가_실제로_다듬었을_때만_값을_받는다():
    """폴백(출처='점수')이면 차감하지 않는다 — 안 쓴 것에 돈을 받지 않는다.

    실결제로 옮기면서 차감이 서버로 갔다. 화면 쪽이 아니라 서버가 지켜야 한다
    (동작 자체는 test_폴백이면_한_푼도_안_깎는다 가 확인한다).
    """
    import inspect
    from backend import main as m
    src = inspect.getsource(m.get_recommend_routines)
    # 다듬어졌을 때만 깎는다
    assert "if 다듬음:" in src
    깎는줄 = [l for l in src.splitlines() if "billing.spend" in l]
    assert len(깎는줄) == 1, 깎는줄
    assert src.index("if 다듬음:") < src.index("billing.spend")
    # 잔액이 모자라면 부르지도 않는다
    assert src.index('out["잔액"] < AI_PRICE') < src.index("air.refine")


def test_잔액이_모자라면_무료로_돌아간다():
    html = _html()
    body = html.split("async function renderRecommend()")[1].split("\nfunction paintRecommend")[0]
    assert "(state.credit || 0) < AI_PRICE" in body
    assert "이용권이 모자라요" in body


def test_키가_없으면_AI방식이_잠긴다():
    html = _html()
    body = html.split("function paintRecoMode()")[1].split("\n}")[0]
    assert "ai.disabled = recoAiReady !== true;" in body
    assert "관리자가 키를 등록하면 켜져요" in body


def test_확인되기_전에는_눌러도_조용히_무시하지_않는다():
    """recoAiReady 가 서버 응답 전(null)일 때 눌리면 예전엔 그냥 아무 일도 안 일어났다.

    버튼 자체는 그때 disabled 가 아직 안 걸려 있어(paintRecoMode 가 안 불렸다),
    "눌러도 반응이 없는 버튼"처럼 보였다 — 화면에 뜬 안내와 실제 동작이 달랐다.
    """
    html = _html()
    assert "let recoAiReady = null;" in html   # false 로 시작하면 '확인 전'과 '확인해서 없음'을 구분 못 한다
    body = html.split("function setRecoMode(mode){")[1].split("\n}")[0]
    assert "recoAiReady !== true" in body
    assert "showToast(" in body
    # 화면에 들어오자마자(첫 fetch 전에) 한 번 그려서, 정적 HTML 그대로 눌리는 창을 없앤다
    reco = html.split("async function renderRecommend(){")[1].split("\n}")[0]
    assert re.search(r"recoBody['\"]\);\s*\r?\n\s*paintRecoMode\(\);", reco)
