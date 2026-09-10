"""AI 루틴 추천 (H1 → 맞춤 짓기).

실제 API 를 부르지 않는다. 가짜 응답으로 (1) 검증된 재료로 루틴이 지어지는지,
(2) 재료에 없는 것은 줄 단위로 버리고 너무 적으면 통째로 버리는지,
(3) 어떤 실패에도 점수 결과로 돌아오고 값을 받지 않는지를 본다.
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

사용자 = {"연령대": "성인", "실제 나이": 40, "체력나이": 44,
       "항목별 체력나이": {"유연성": 52, "근력": 41, "심폐지구력": 45, "근지구력": 40},
       "뒤처지는 체력요인": ["유연성"], "고른 종목": ["러닝"], "강도": {"세트": 2, "반복": 10, "시간초": 30}}


def _코드(단계: str, n: int = 0) -> str:
    """그 단계의 실제 공식 동작 코드 — 재료 표에 있는 것."""
    from backend import routines as rt
    return list(rt.load()["pools"]["성인"][단계])[n]


def _지은응답(꼬리: str = "", 동작=None) -> str:
    """검증된 재료로 짠 그럴듯한 응답. 꼬리로 짬시간 같은 것을 덧붙인다."""
    import json as _j
    줄 = 동작 if 동작 is not None else [
        {"코드": _코드("준비운동"), "단계": "준비운동", "수행량": "30초", "왜": "몸을 풀어요"},
        {"코드": _코드("본운동"), "단계": "본운동", "수행량": "10회 2세트", "왜": "본운동"},
        {"종목": "running", "단계": "본운동", "수행량": "15분", "왜": "고른 종목이에요"},
        {"기록": "squat", "단계": "본운동", "수행량": "12회 3세트", "왜": "하체"},
        {"코드": _코드("정리운동"), "단계": "정리운동", "수행량": "30초", "왜": "정리"},
    ]
    본문 = _j.dumps({"목적": "다이어트", "루틴명": "오늘의 나", "한마디": "가볍게 시작해요",
                    "왜": ["유연성이 뒤처져요"], "주의": ["무릎이 아프면 쉬세요"], "동작": 줄},
                   ensure_ascii=False)
    return 본문[:-1] + 꼬리 + "}"


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
    assert air.compose(사용자, "성인") is None


def test_검증된_재료로_루틴이_지어진다(monkeypatch):
    _fake_sdk(monkeypatch, _지은응답())
    r = air.compose(사용자, "성인", 종목ids=["running"])["루틴"]
    assert r["루틴명"] == "오늘의 나" and r["목적"] == "다이어트"
    assert r["구성"] == "ai" and r["출처"] == "ai" and r["순위"] == 1
    assert r["이유"] == ["유연성이 뒤처져요"] and r["주의"] == ["무릎이 아프면 쉬세요"]
    assert r["동작수"] == 5 and r["강도"] == 사용자["강도"]
    assert [x["단계"] for x in r["steps"]] == ["준비운동", "본운동", "본운동", "본운동", "정리운동"]
    assert r["steps"][1]["수행량"] == "10회 2세트" and r["steps"][1]["왜"] == "본운동"


def test_영상이_없어도_검증된_종목이면_들어간다(monkeypatch):
    """영상 유무는 조건이 아니다. 고른 종목은 영상이 없지만 검증된 종목이다."""
    _fake_sdk(monkeypatch, _지은응답())
    steps = air.compose(사용자, "성인", 종목ids=["running"])["루틴"]["steps"]
    종목 = next(x for x in steps if x["출처"] == "종목")
    기록 = next(x for x in steps if x["출처"] == "기록")
    assert 종목["동작"] == "러닝" and 종목["youtube_id"] is None and 종목["아이콘"]
    assert 기록["동작"] == "스쿼트" and 기록["youtube_id"] is None
    assert all(x["youtube_id"] for x in steps if x["출처"] == "동작")   # 공식 동작은 영상이 있다


def test_재료에_없는_것은_그_줄만_버린다(monkeypatch):
    """이름을 지어낼 수 없다. 다만 한 줄 틀렸다고 루틴 전체를 잃지는 않는다."""
    _fake_sdk(monkeypatch, _지은응답(동작=[
        {"코드": _코드("준비운동"), "단계": "준비운동", "수행량": "30초"},
        {"코드": "V지어낸코드", "단계": "본운동", "수행량": "x"},
        {"종목": "quidditch", "단계": "본운동", "수행량": "x"},
        {"기록": "없는운동", "단계": "본운동", "수행량": "x"},
        {"코드": _코드("본운동"), "단계": "본운동", "수행량": "10회"},
        {"코드": _코드("본운동"), "단계": "본운동", "수행량": "또"},          # 같은 것 두 번
        {"코드": _코드("정리운동"), "단계": "정리운동", "수행량": "30초"},
    ]))
    steps = air.compose(사용자, "성인")["루틴"]["steps"]
    assert len(steps) == 3
    assert all(x["동작"] not in ("V지어낸코드", "quidditch", "없는운동") for x in steps)


def test_재료의_이름을_쓴다_응답의_이름이_아니라(monkeypatch):
    """응답이 코드에 엉뚱한 이름을 붙여도 화면에는 재료의 이름이 뜬다."""
    _fake_sdk(monkeypatch, _지은응답(동작=[
        {"코드": _코드("준비운동"), "단계": "준비운동", "동작": "엉뚱한 이름", "수행량": "30초"},
        {"코드": _코드("본운동"), "단계": "본운동", "동작": "엉뚱한 이름", "수행량": "10회"},
        {"코드": _코드("정리운동"), "단계": "정리운동", "동작": "엉뚱한 이름", "수행량": "30초"},
    ]))
    steps = air.compose(사용자, "성인")["루틴"]["steps"]
    assert all(x["동작"] != "엉뚱한 이름" for x in steps)


@pytest.mark.parametrize("본문", [
    '{"목적":"다이어트"}',                                  # 동작이 없음
    '{"동작":"스쿼트 열 번"}',                               # 목록이 아님
    '{"동작":[{"코드":"V없음"},{"종목":"없음"},{"기록":"없음"}]}',   # 전부 지어냄
    '이건 JSON 이 아니에요',
    '',
])
def test_루틴이_안_되면_통째로_버린다(monkeypatch, 본문):
    _fake_sdk(monkeypatch, 본문)
    assert air.compose(사용자, "성인") is None


def test_세_줄이_안_되거나_본운동이_없으면_루틴이_아니다(monkeypatch):
    두줄 = [{"코드": _코드("준비운동"), "단계": "준비운동"}, {"코드": _코드("본운동"), "단계": "본운동"}]
    _fake_sdk(monkeypatch, _지은응답(동작=두줄))
    assert air.compose(사용자, "성인") is None
    본없음 = [{"코드": _코드("준비운동", i), "단계": "준비운동"} for i in range(3)]
    _fake_sdk(monkeypatch, _지은응답(동작=본없음))
    assert air.compose(사용자, "성인") is None


def test_없는_목적이면_기본_목적으로(monkeypatch):
    본문 = _지은응답().replace('"목적": "다이어트"', '"목적": "우주 정복"')
    _fake_sdk(monkeypatch, 본문)
    assert air.compose(사용자, "성인")["루틴"]["목적"] == "기초 체력 증진"


def test_거절과_예외도_폴백한다(monkeypatch):
    _fake_sdk(monkeypatch, _지은응답(), stop="refusal")
    assert air.compose(사용자, "성인") is None
    _fake_sdk(monkeypatch, boom=RuntimeError("연결 실패"))
    assert air.compose(사용자, "성인") is None


def test_엔드포인트가_출처를_알려준다(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    d = client.get("/recommend/routines", params={"age_gbn": "성인", "limit": 3}).json()
    assert d["출처"] == "점수" and d["ai가능"] is False
    assert len(d["추천"]) == 3          # 키가 없어도 화면은 비지 않는다


def test_엔드포인트가_AI를_쓴다(monkeypatch):
    _fake_sdk(monkeypatch, _지은응답())
    a = _paid(1000)
    d = a.get("/recommend/routines", params={"age_gbn": "성인", "limit": 3}).json()
    assert d["출처"] == "ai"
    assert len(d["추천"]) == 1 and d["추천"][0]["구성"] == "ai"   # 후보 목록이 아니라 지은 루틴 하나
    assert d["추천"][0]["이유"] == ["유연성이 뒤처져요"]
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


def test_AI가_실제로_지었을_때만_값을_받는다():
    """폴백(출처='점수')이면 차감하지 않는다 — 안 쓴 것에 돈을 받지 않는다.

    실결제로 옮기면서 차감이 서버로 갔다. 화면 쪽이 아니라 서버가 지켜야 한다
    (동작 자체는 test_폴백이면_한_푼도_안_깎는다 가 확인한다).
    """
    import inspect
    from backend import main as m
    src = inspect.getsource(m._recommend)   # GET·POST 가 함께 쓰는 본체
    # 지어졌을 때만 깎는다
    조건 = 'if 지음 and 지음.get("루틴"):'
    assert 조건 in src
    깎는줄 = [l for l in src.splitlines() if "billing.spend" in l]
    assert len(깎는줄) == 1, 깎는줄
    assert src.index(조건) < src.index("billing.spend")
    # 잔액이 모자라면 부르지도 않는다
    assert src.index('out["잔액"] < AI_PRICE') < src.index("air.compose")


def test_잔액이_모자라면_무료로_돌아간다():
    html = _html()
    body = html.split("async function renderRecommend()")[1].split("\nfunction paintRecommend")[0]
    assert "(state.credit || 0) < AI_PRICE" in body
    assert "이용권이 모자라요" in body


def test_키가_없으면_AI방식은_들어가되_받기_버튼만_잠긴다():
    """탭은 잠그지 않는다 — 여기는 '받을지 고르는 자리' 다.

    한때 탭 자체를 잠갔더니, 쓸 수 있는지 확인이 끝나기 전에는 들어가 볼
    수조차 없었다. 값이 빠지는 '받기' 버튼만 잠근다.
    """
    html = _html()
    body = html.split("function paintRecoMode()")[1].split("\n}")[0]
    assert "ai.disabled" not in body
    assert "관리자가 키를 등록하면 켜져요" in body      # 부제로는 알려 준다
    intro = html.split("function aiIntroHtml()")[1].split("\n}")[0]
    assert "${확인중 || 못씀 || 모자람 ? 'disabled' : ''}" in intro


def test_확인되기_전에는_눌러도_조용히_무시하지_않는다():
    """recoAiReady 가 서버 응답 전(null)일 때 눌리면 예전엔 그냥 아무 일도 안 일어났다.

    버튼 자체는 그때 disabled 가 아직 안 걸려 있어(paintRecoMode 가 안 불렸다),
    "눌러도 반응이 없는 버튼"처럼 보였다 — 화면에 뜬 안내와 실제 동작이 달랐다.
    """
    html = _html()
    assert "let recoAiReady = null;" in html   # false 로 시작하면 '확인 전'과 '확인해서 없음'을 구분 못 한다
    # 확인 전에 눌러도 들어가진다. 대신 화면이 '확인하는 중' 이라고 말한다.
    body = html.split("function setRecoMode(mode){")[1].split("\n}")[0]
    assert "recoMode = mode;" in body and "return;" not in body
    intro = html.split("function aiIntroHtml()")[1].split("\n}")[0]
    assert "const 확인중 = recoAiReady === null;" in intro
    assert "확인하는 중이에요" in intro
    # 화면에 들어오자마자(첫 fetch 전에) 한 번 그려서, 정적 HTML 그대로 눌리는 창을 없앤다
    reco = html.split("async function renderRecommend(){")[1].split("\n}")[0]
    assert re.search(r"recoBody['\"]\);\s*\r?\n\s*paintRecoMode\(\);", reco)

# ---------- 일정을 함께 읽는다 ----------

일정 = {"상태": "학생",
      "요일별": {"월": [{"시작": "12:00", "끝": "13:00", "분": 60,
                     "추천": [{"이름": "달리기"}, {"이름": "맨몸 근력"}]}]}}


def test_비는_칸을_프롬프트에_적어_보낸다(monkeypatch):
    """AI 가 고를 수 있는 칸과 거기서 할 수 있는 것을 알려주지 않으면 지어낸다."""
    본 = {}

    class _Messages:
        def create(self, **kw):
            본["글"] = kw["messages"][0]["content"]
            return _Msg(_지은응답())

    class _Client:
        def __init__(self, **kw): self.messages = _Messages()

    mod = type(sys)("anthropic")
    mod.Anthropic = _Client
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    air.compose(dict(사용자, **{"하루의 모습": ["학생"]}), "성인", 종목ids=["running"], 일정=일정)
    글 = 본["글"]
    assert "비는 시간" in 글
    assert "월 0. 12:00–13:00 (60분) — 달리기 / 맨몸 근력" in 글
    assert "학생" in 글                      # 하루의 모습도 함께
    # 이 사람의 데이터와 재료가 다 실린다
    assert '"유연성": 52' in 글 and "재료" in 글
    assert "★ 러닝" in 글                    # 고른 종목은 표시해 준다
    assert _코드("본운동") in 글


def test_그_칸에_없는_것을_고르면_그_줄만_버린다(monkeypatch):
    """지어낸 운동을 내보내지 않는다. 다만 한 줄 틀렸다고 나머지까지 잃지는 않는다."""
    _fake_sdk(monkeypatch, _지은응답(
        ',"짬시간":{"월":[{"칸":0,"할것":"수영","한줄":"버려질 줄"},'
        '{"칸":0,"할것":"달리기","한줄":"점심에 가볍게"}]}'))
    r = air.compose(사용자, "성인", 일정=일정)
    assert [x["할것"] for x in r["짬시간"]["월"]] == ["달리기"]
    assert r["짬시간"]["월"][0]["한줄"] == "점심에 가볍게"
    assert r["짬시간"]["월"][0]["시작"] == "12:00"   # 시각은 서버 것을 쓴다


@pytest.mark.parametrize("고른것", [
    '{"월":[{"칸":9,"할것":"달리기"}]}',        # 없는 칸
    '{"월":[{"칸":"점심","할것":"달리기"}]}',    # 번호가 아님
    '{"화":[{"칸":0,"할것":"달리기"}]}',        # 안 적은 요일
    '{"월":"달리기"}',                         # 줄이 아님
    '"달리기"',                                # 통째로 엉뚱함
])
def test_말이_안_되는_짬시간은_담지_않는다(monkeypatch, 고른것):
    _fake_sdk(monkeypatch, _지은응답(',"짬시간":' + 고른것))
    assert air.compose(사용자, "성인", 일정=일정)["짬시간"] == {}


def test_일정을_안_주면_짬시간도_없다(monkeypatch):
    """안 적은 사람에게 비는 시간을 지어내 주지 않는다."""
    _fake_sdk(monkeypatch, _지은응답(',"짬시간":{"월":[{"칸":0,"할것":"달리기"}]}'))
    assert air.compose(사용자, "성인")["짬시간"] == {}


def test_POST로_보내면_일정까지_함께_본다(monkeypatch):
    _fake_sdk(monkeypatch, _지은응답(
        ',"짬시간":{"월":[{"칸":0,"할것":"스트레칭","한줄":"짧게"}]}'))
    a = _paid(1000)
    d = a.post("/recommend/routines",
               json={"age_gbn": "성인", "limit": 3,
                     "바쁜시간": {"월": [{"시작": "09:00", "끝": "12:00"}]}},
               ).json()
    assert d["출처"] == "ai" and d["잔액"] == 900
    assert d["추천"][0]["구성"] == "ai"
    assert d["짬시간"]["월"], "일정을 줬으면 비는 칸이 나와야 한다"
    골라둔 = d.get("짬시간계획", {}).get("월") or []
    assert all(x["할것"] for x in 골라둔)


def test_일정을_안_넣은_POST는_GET과_같다(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    g = client.get("/recommend/routines",
                   params={"age_gbn": "성인", "limit": 3}).json()
    p = client.post("/recommend/routines",
                    json={"age_gbn": "성인", "limit": 3}).json()
    assert [x["루틴명"] for x in p["추천"]] == [x["루틴명"] for x in g["추천"]]
    assert "짬시간" not in p          # 안 적었으면 지어내지 않는다


def test_없는_요일은_그냥_버린다():
    """엉뚱한 키 하나로 추천 전체가 죽으면 안 된다."""
    d = client.post("/recommend/routines",
                    json={"age_gbn": "성인", "limit": 3,
                          "바쁜시간": {"먼데이": [{"시작": "09:00", "끝": "12:00"}]}}).json()
    assert len(d["추천"]) == 3
    assert "짬시간" not in d


# ---------- 계절별로 자세히 도전하기 ----------

루틴 = {"목적": "다이어트", "루틴명": "전신 HIIT", "동작수": 5,
      "체력요인": ["심폐지구력"], "난이도": "보통"}


def _네계절(꼬리: str = "") -> str:
    안 = ", ".join(
        '{"계절":"%s","한줄":"%s에는 이렇게","할것":["가볍게"],"조심":"무리 마세요"}' % (c, c)
        for c in ("봄", "여름", "가을", "겨울"))
    return '{"계절":[' + 안 + ']' + 꼬리 + '}'


def test_네_계절을_순서대로_돌려준다(monkeypatch):
    _fake_sdk(monkeypatch, _네계절())
    r = air.seasons(루틴, {}, "성인", "학생")
    assert [x["계절"] for x in r] == ["봄", "여름", "가을", "겨울"]
    assert r[0]["한줄"] == "봄에는 이렇게"
    assert r[0]["할것"] == ["가볍게"]


def test_계절이_섞여_와도_봄부터_그린다(monkeypatch):
    """받은 순서가 아니라 1년 순서로 읽혀야 한다."""
    안 = ", ".join('{"계절":"%s","한줄":"x"}' % c for c in ("겨울", "봄", "가을", "여름"))
    _fake_sdk(monkeypatch, '{"계절":[' + 안 + ']}')
    assert [x["계절"] for x in air.seasons(루틴, {}, "성인")] == ["봄", "여름", "가을", "겨울"]


@pytest.mark.parametrize("본문", [
    '{"계절":[{"계절":"봄","한줄":"x"},{"계절":"여름","한줄":"x"}]}',   # 두 계절뿐
    '{"계절":[{"계절":"장마","한줄":"x"}]}',                          # 없는 계절
    '{"계절":[{"계절":"봄"},{"계절":"봄"},{"계절":"봄"},{"계절":"봄"}]}',  # 중복
    '{"계절":"봄부터 시작해요"}',                                     # 목록이 아님
    '{"순서":[0]}',                                                  # 계절이 없음
    "이건 JSON 이 아니에요",
    "",
])
def test_1년이_안_되면_통째로_버린다(monkeypatch, 본문):
    """봄·여름만 있는 1년 계획은 받아 든 사람이 나머지를 채워야 해서 없느니만 못하다."""
    _fake_sdk(monkeypatch, 본문)
    assert air.seasons(루틴, {}, "성인") is None


def test_하루의_모습을_프롬프트에_적어_보낸다(monkeypatch):
    본 = {}

    class _Messages:
        def create(self, **kw):
            본["글"] = kw["messages"][0]["content"]
            본["시스템"] = kw["system"]
            return _Msg(_네계절())

    class _Client:
        def __init__(self, **kw): self.messages = _Messages()

    mod = type(sys)("anthropic")
    mod.Anthropic = _Client
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    air.seasons(루틴, {"약점": ["유연성"]}, "성인", "알바생")
    assert "알바생" in 본["글"]
    assert "전신 HIIT" in 본["글"]
    assert "유연성" in 본["글"]
    assert "루틴을 바꾸지 마세요" in 본["시스템"]


def test_계절_엔드포인트는_값을_받지_않는다(monkeypatch):
    """AI 추천을 받을 때 이미 치렀다. 더 알아보는 건 선택 사항이고 돈이 다시 들지 않는다."""
    _fake_sdk(monkeypatch, _네계절())
    a = _paid(1000)
    d = a.post("/recommend/seasons",
               json={"age_gbn": "성인", "루틴": 루틴, "상태": "학생"}).json()
    assert [x["계절"] for x in d["계절"]] == ["봄", "여름", "가을", "겨울"]
    assert d["루틴명"] == "전신 HIIT"
    assert "잔액" not in d                                # 잔액을 건드리지 않는다
    assert a.get("/credit").json()["잔액"] == 1000        # 한 푼도 안 빠졌다


def test_못_받았으면_한_푼도_안_깎는다(monkeypatch):
    """안 쓴 것에 돈을 받지 않는다."""
    _fake_sdk(monkeypatch, "이건 JSON 이 아니다")
    a = _paid(1000)
    r = a.post("/recommend/seasons", json={"age_gbn": "성인", "루틴": 루틴})
    assert r.status_code == 503
    assert a.get("/credit").json()["잔액"] == 1000


def test_이용권이_없어도_알아볼_수_있다(monkeypatch):
    """무료라서 이용권이 0 이어도 된다."""
    _fake_sdk(monkeypatch, _네계절())
    a = _paid(0)
    r = a.post("/recommend/seasons", json={"age_gbn": "성인", "루틴": 루틴})
    assert r.status_code == 200
    assert len(r.json()["계절"]) == 4


def test_계절_경로에는_차감이_없다():
    import inspect
    from backend import main as m
    src = inspect.getsource(m.post_recommend_seasons)
    assert "billing.spend" not in src and "AI_PRICE" not in src


def test_로그인하지_않으면_부르지_않는다(monkeypatch):
    _fake_sdk(monkeypatch, _네계절())
    r = TestClient(app).post("/recommend/seasons",
                             json={"age_gbn": "성인", "루틴": 루틴})
    assert r.status_code in (401, 403)


def test_키가_없으면_계절도_잠긴다(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    a = _paid(1000)
    r = a.post("/recommend/seasons", json={"age_gbn": "성인", "루틴": 루틴})
    assert r.status_code == 503
    assert a.get("/credit").json()["잔액"] == 1000


# ---------- 사진으로 시간표 읽기 ----------

사진 = "data:image/png;base64," + "A" * 400


def _시간표(본문: str):
    return 본문


def test_사진에서_읽은_시간을_두_자리로_맞춘다(monkeypatch):
    _fake_sdk(monkeypatch, '{"바쁜시간":{"월":[{"시작":"9:5","끝":"12:00"}]}}')
    r = air.read_schedule_photo("A" * 400, "image/png")
    assert r == {"월": [{"시작": "09:05", "끝": "12:00"}]}


def test_거꾸로거나_못_읽은_칸은_담지_않는다(monkeypatch):
    """그런 줄은 빈 시간을 엉뚱하게 만든다."""
    _fake_sdk(monkeypatch,
              '{"바쁜시간":{"월":[{"시작":"18:00","끝":"09:00"},'          # 거꾸로
              '{"시작":"09:00","끝":"09:00"},'                            # 길이가 0
              '{"시작":"25:00","끝":"26:00"},'                            # 시각이 아님
              '{"시작":"09:00"},'                                         # 끝이 없음
              '{"시작":"13:00","끝":"14:00"}]}}')                          # 이것만 남는다
    assert air.read_schedule_photo("A" * 400, "image/png") == {
        "월": [{"시작": "13:00", "끝": "14:00"}]}


def test_없는_요일과_시간표가_아닌_사진(monkeypatch):
    _fake_sdk(monkeypatch, '{"바쁜시간":{"먼데이":[{"시작":"09:00","끝":"12:00"}]}}')
    assert air.read_schedule_photo("A" * 400, "image/png") == {}
    _fake_sdk(monkeypatch, '{"바쁜시간":{}}')
    assert air.read_schedule_photo("A" * 400, "image/png") == {}


@pytest.mark.parametrize("본문", ['{"바쁜시간":"월요일 9시"}', '{"순서":[0]}',
                                "JSON 이 아니에요", ""])
def test_모양이_다르면_None(monkeypatch, 본문):
    _fake_sdk(monkeypatch, 본문)
    assert air.read_schedule_photo("A" * 400, "image/png") is None


def test_안_되는_형식은_부르지도_않는다(monkeypatch):
    _fake_sdk(monkeypatch, '{"바쁜시간":{}}')
    assert air.read_schedule_photo("A" * 400, "image/heic") is None
    assert air.read_schedule_photo("", "image/png") is None


def test_사진_엔드포인트가_값을_받는다(monkeypatch):
    _fake_sdk(monkeypatch, '{"바쁜시간":{"월":[{"시작":"09:00","끝":"12:00"}]}}')
    a = _paid(1000)
    d = a.post("/schedule/photo", json={"사진": 사진}).json()
    assert d["바쁜시간"] == {"월": [{"시작": "09:00", "끝": "12:00"}]}
    assert d["잔액"] == 900


def test_시간표가_아니면_왜_비었는지_알려준다(monkeypatch):
    _fake_sdk(monkeypatch, '{"바쁜시간":{}}')
    a = _paid(1000)
    d = a.post("/schedule/photo", json={"사진": 사진}).json()
    assert d["바쁜시간"] == {}
    assert "직접 적어주세요" in d["안내"]


def test_못_읽었으면_한_푼도_안_깎는다(monkeypatch):
    _fake_sdk(monkeypatch, "이건 JSON 이 아니다")
    a = _paid(1000)
    assert a.post("/schedule/photo", json={"사진": 사진}).status_code == 503
    assert a.get("/credit").json()["잔액"] == 1000


def test_큰_사진과_안_되는_형식은_부르기_전에_막는다(monkeypatch):
    """부르고 나서 실패하면 우리만 값을 치른다."""
    _fake_sdk(monkeypatch, '{"바쁜시간":{}}')
    a = _paid(1000)
    큰것 = "data:image/png;base64," + "A" * 6_000_000
    assert a.post("/schedule/photo", json={"사진": 큰것}).status_code == 413
    assert a.post("/schedule/photo",
                  json={"사진": "data:image/heic;base64,AAAA"}).status_code == 415
    assert a.get("/credit").json()["잔액"] == 1000


def test_사진도_로그인과_이용권이_있어야_한다(monkeypatch):
    _fake_sdk(monkeypatch, '{"바쁜시간":{}}')
    assert TestClient(app).post("/schedule/photo",
                                json={"사진": 사진}).status_code in (401, 403)
    assert _paid(0).post("/schedule/photo", json={"사진": 사진}).status_code == 402


# ---------- 하루의 모습은 여럿 ----------

def test_하루의_모습을_목록_하나로_다듬는다():
    from backend import main as m
    assert m._life_kinds("학생") == ["학생"]                    # 예전에 하나만 골랐던 것
    assert m._life_kinds(["대학생", "알바생", "대학생"]) == ["대학생", "알바생"]
    assert m._life_kinds(None) == [] and m._life_kinds({"a": 1}) == []
    assert m._life_kinds(["가" * 40]) == ["가" * 20]            # 직접 적은 것은 자른다
    assert len(m._life_kinds([str(i) for i in range(20)])) == 6


def test_여러_모습이_프롬프트에_다_실린다(monkeypatch):
    본 = {}

    class _Messages:
        def create(self, **kw):
            본["글"] = kw["messages"][0]["content"]
            return _Msg(_네계절())

    class _Client:
        def __init__(self, **kw): self.messages = _Messages()

    mod = type(sys)("anthropic")
    mod.Anthropic = _Client
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    a = _paid(1000)
    a.post("/recommend/seasons", json={"age_gbn": "성인", "루틴": 루틴,
                                       "상태": ["대학생", "알바생"]})
    assert "대학생" in 본["글"] and "알바생" in 본["글"]


# ---------- AI 를 쓸 수 있는지만 따로 묻는다 ----------

def test_상태_확인은_값이_들지_않고_루틴을_매기지_않는다(monkeypatch):
    """추천을 받아야만 알 수 있으면, 받아 둔 추천이 있을 때 영영 모른다."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    a = _paid(1000)
    d = a.get("/recommend/ai-status").json()
    assert d["ai가능"] is False
    assert "ANTHROPIC_API_KEY" in d["이유"]
    assert d["잔액"] == 1000 and d["로그인"] is True
    assert d["값"] == 100
    assert "추천" not in d                      # 루틴 점수를 매기지 않는다
    assert a.get("/credit").json()["잔액"] == 1000   # 한 푼도 안 빠진다


def test_상태_확인은_로그인_없이도_된다(monkeypatch):
    _fake_sdk(monkeypatch, "{}")
    d = TestClient(app).get("/recommend/ai-status").json()
    assert d["ai가능"] is True and d["이유"] is None
    assert d["잔액"] == 0 and d["로그인"] is False


# ---------- 이 사람을 읽는다 ----------

def test_POST의_사용자_데이터가_프롬프트에_실린다(monkeypatch):
    """항목별 체력나이와 최근 기록이 없으면 '맞춤' 이 아니다."""
    본 = {}

    class _Messages:
        def create(self, **kw):
            본["글"] = kw["messages"][0]["content"]
            return _Msg(_지은응답())

    class _Client:
        def __init__(self, **kw): self.messages = _Messages()

    mod = type(sys)("anthropic")
    mod.Anthropic = _Client
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    a = _paid(1000)
    d = a.post("/recommend/routines", json={
        "age_gbn": "성인", "limit": 3, "sports": ["running"],
        "항목별": {"유연성": 52.5, "근력": 41}, "체력나이": 44.2,
        "최근기록": [{"date": "2026-09-08", "이름": "스쿼트", "값": "12횟수 3세트"}],
        "상태": ["대학생", "알바생"]}).json()
    assert d["출처"] == "ai"
    글 = 본["글"]
    assert "52.5" in 글 and "44.2" in 글
    assert "스쿼트" in 글 and "12횟수 3세트" in 글
    assert "대학생" in 글 and "알바생" in 글
    assert "★ 러닝" in 글


def test_사용자_데이터는_무료_추천을_바꾸지_않는다(monkeypatch):
    """무료는 점수 규칙 그대로다. 같은 조건이면 같은 결과가 나와야 한다."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    기본 = client.post("/recommend/routines", json={"age_gbn": "성인", "limit": 5, "ai": False}).json()
    같이 = client.post("/recommend/routines", json={
        "age_gbn": "성인", "limit": 5, "ai": False,
        "항목별": {"유연성": 60}, "체력나이": 55,
        "최근기록": [{"date": "2026-09-08", "이름": "스쿼트", "값": "x"}]}).json()
    assert [x["루틴명"] for x in 같이["추천"]] == [x["루틴명"] for x in 기본["추천"]]
    assert 같이["출처"] == "점수" and len(같이["추천"]) == 5


def test_지어낸_루틴의_한_줄에_영상_없는_것이_섞여도_전체가_산다(monkeypatch):
    _fake_sdk(monkeypatch, _지은응답())
    a = _paid(1000)
    d = a.post("/recommend/routines", json={"age_gbn": "성인", "sports": ["running"]}).json()
    steps = d["추천"][0]["steps"]
    assert any(x["출처"] == "종목" for x in steps) and any(x["출처"] == "동작" for x in steps)


# ---------- 자세히 알아보기: 계절 | 시간대 ----------

def _네시간대() -> str:
    안 = ", ".join(
        '{"시간대":"%s","한줄":"%s에는 이렇게","할것":["가볍게"],"조심":"무리 마세요"}' % (c, c)
        for c in ("아침", "낮", "저녁", "밤"))
    return '{"시간대":[' + 안 + ']}'


def test_시간대별로도_네_구간을_순서대로_돌려준다(monkeypatch):
    _fake_sdk(monkeypatch, _네시간대())
    r = air.periods(루틴, {}, "성인", ["직장인"], 축="시간대")
    assert [x["시간대"] for x in r] == ["아침", "낮", "저녁", "밤"]
    assert r[0]["한줄"] == "아침에는 이렇게"


def test_시간대_프롬프트는_하루를_말한다():
    글 = air._period_system("시간대")
    assert "하루 동안" in 글 and "아침·낮·저녁·밤" in 글
    assert "루틴을 바꾸지 마세요" in 글
    assert '"시간대": [' in 글                     # JSON 열쇠도 축을 따른다
    assert air.SEASON_SYSTEM == air._period_system("계절")   # 예전 이름은 계절 축


@pytest.mark.parametrize("본문", [
    '{"시간대":[{"시간대":"아침","한줄":"x"},{"시간대":"밤","한줄":"x"}]}',   # 둘뿐
    '{"시간대":[{"시간대":"새벽","한줄":"x"}]}',                              # 없는 구간
    '{"계절":[{"계절":"봄","한줄":"x"}]}',                                    # 축이 다르다
])
def test_시간대가_다_안_나오면_통째로_버린다(monkeypatch, 본문):
    _fake_sdk(monkeypatch, 본문)
    assert air.periods(루틴, {}, "성인", None, 축="시간대") is None


def test_없는_축은_부르지도_않는다(monkeypatch):
    _fake_sdk(monkeypatch, _네시간대())
    assert air.periods(루틴, {}, "성인", None, 축="분기") is None


def test_periods_엔드포인트_시간대(monkeypatch):
    """값을 받지 않고, 비는 시간을 주면 프롬프트에 실린다."""
    본 = {}

    class _Messages:
        def create(self, **kw):
            본["글"] = kw["messages"][0]["content"]
            본["시스템"] = kw["system"]
            return _Msg(_네시간대())

    class _Client:
        def __init__(self, **kw): self.messages = _Messages()

    mod = type(sys)("anthropic")
    mod.Anthropic = _Client
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    a = _paid(0)                                   # 이용권이 없어도 된다
    d = a.post("/recommend/periods", json={
        "age_gbn": "성인", "루틴": 루틴, "축": "시간대", "상태": ["직장인"],
        "바쁜시간": {"월": [{"시작": "09:00", "끝": "18:00"}]}}).json()
    assert d["축"] == "시간대"
    assert [x["시간대"] for x in d["시간대"]] == ["아침", "낮", "저녁", "밤"]
    assert "잔액" not in d and a.get("/credit").json()["잔액"] == 0
    assert "하루 동안" in 본["시스템"]
    assert "비는 시간" in 본["글"] and "18:00" in 본["글"]   # 비는 칸이 재료로 실렸다


def test_periods_축은_둘뿐이다():
    r = client.post("/recommend/periods", json={"age_gbn": "성인", "루틴": 루틴, "축": "분기"})
    assert r.status_code == 422


def test_seasons_주소는_계절_축_그대로(monkeypatch):
    _fake_sdk(monkeypatch, _네계절())
    d = _paid(0).post("/recommend/seasons", json={"age_gbn": "성인", "루틴": 루틴}).json()
    assert d["축"] == "계절" and [x["계절"] for x in d["계절"]] == ["봄", "여름", "가을", "겨울"]
