"""카카오페이 이용권 결제 — 실제 결제를 받을 수 있는 상태인지 본다.

실제 카카오 서버를 부르지 않는다. httpx.MockTransport 로 응답을 만들어
**우리가 보내는 요청 모양**과 **이상한 응답에서 안 터지는지**를 본다.

돈이 걸린 부분이라 특히 이것들을 지킨다.
  - 잔액은 서버 원장이 기준이다. 화면이 보낸 숫자로 올리지 않는다
  - 청구 금액도 올려 줄 이용권도 서버 표(PAY_PACKS)로만 정한다
  - 카카오가 승인한 금액이 청구액과 다르면 반영하지 않는다
  - 한 주문은 한 번만 충전된다 (승인 콜백이 두 번 와도)
  - 재시작해도 주문이 살아 있다 (DB에 있다)
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import auth, billing, community      # noqa: E402
from backend import kakaopay as kp                # noqa: E402
from backend.main import app                      # noqa: E402

# 진짜 AsyncClient 를 한 번만 붙잡아 둔다. 매번 잡으면 앞서 끼운 가짜를
# 다시 상속해서, 나중에 끼운 응답이 앞의 것에 덮인다.
_REAL_CLIENT = httpx.AsyncClient


@pytest.fixture(autouse=True)
def _db(monkeypatch):
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


@pytest.fixture
def 키(monkeypatch):
    monkeypatch.setenv("KAKAOPAY_SECRET_KEY", "DEV_TEST_KEY")
    monkeypatch.setenv("KAKAOPAY_CID", "TC0ONETIME")


def _login(email: str = "a@x.com", name: str = "가") -> TestClient:
    c = TestClient(app)
    c.post("/auth/signup", json={"email": email, "password": "pw12345678",
                                 "display_name": name})
    return c


def 가짜(응답, 기록=None, status=200):
    """카카오 대신 대답하는 transport 를 끼운다."""
    def handler(request: httpx.Request) -> httpx.Response:
        if 기록 is not None:
            기록.append({"url": str(request.url),
                        "headers": dict(request.headers),
                        "body": json.loads(request.content or b"{}")})
        return httpx.Response(status, json=응답)

    class Patched(_REAL_CLIENT):
        def __init__(self, *a, **kw):
            kw["transport"] = httpx.MockTransport(handler)
            super().__init__(*a, **kw)

    return Patched


READY_OK = {"tid": "T1", "next_redirect_pc_url": "https://kakao/pc",
            "next_redirect_mobile_url": "https://kakao/mo"}


def 준비(c, monkeypatch, 이용권=3000, 기록=None):
    monkeypatch.setattr(kp.httpx, "AsyncClient", 가짜(READY_OK, 기록))
    r = c.post("/pay/kakao/ready", json={"amount": 이용권})
    assert r.status_code == 200, r.text
    return r.json()


# ---------- 키가 없을 때 ----------

def test_키가_없으면_쓸수없다고_알린다():
    d = _login().get("/pay/methods").json()
    assert d["kakao"]["쓸수있음"] is False


def test_선결제_할인표는_서버가_내려준다():
    """할인율을 화면에서 계산하면 표시와 청구가 어긋날 수 있다."""
    packs = _login().get("/pay/methods").json()["packs"]
    표 = {p["이용권"]: (p["결제"], p["할인"]) for p in packs}
    assert 표 == {100: (100, 0), 1000: (700, 30), 2000: (1300, 35),
                 3000: (1800, 40), 5000: (2500, 50)}


def test_키가_없으면_준비도_안_한다():
    assert _login().post("/pay/kakao/ready", json={"amount": 3000}).status_code == 503


@pytest.mark.anyio
async def test_모듈이_키_없이_호출되면_None():
    assert await kp.ready(amount=1000, order_id="a", user_id="u",
                          approval_url="x", cancel_url="y", fail_url="z") is None
    assert await kp.approve(tid="t", pg_token="p", order_id="a", user_id="u") is None


# ---------- 로그인 ----------

def test_로그인하지_않으면_결제할_수_없다(키):
    """잔액이 서버 원장에 쌓인다. 붙일 계정이 없으면 돈만 받고 줄 곳이 없다."""
    c = TestClient(app)
    assert c.post("/pay/kakao/ready", json={"amount": 3000}).status_code == 401
    assert c.get("/credit").status_code == 401


# ---------- 준비 ----------

def test_고를_수_없는_금액은_거절한다(키):
    a = _login()
    assert a.post("/pay/kakao/ready", json={"amount": 7}).status_code == 400
    assert a.post("/pay/kakao/ready", json={"amount": -3000}).status_code == 400
    # 할인 후 금액을 이용권 자리에 넣어도 안 통한다 (700원짜리 팩은 없다)
    assert a.post("/pay/kakao/ready", json={"amount": 700}).status_code == 400


def test_준비하면_결제창_주소를_주고_주문을_남긴다(키, monkeypatch):
    기록 = []
    a = _login()
    d = 준비(a, monkeypatch, 3000, 기록)
    assert d["redirect"] == "https://kakao/mo"
    # 3,000원 이용권은 40% 할인이라 1,800원을 청구한다
    assert d["결제"] == 1800 and d["이용권"] == 3000

    보낸것 = 기록[0]
    assert 보낸것["url"].endswith("/online/v1/payment/ready")
    assert 보낸것["headers"]["authorization"] == "SECRET_KEY DEV_TEST_KEY"
    assert 보낸것["body"]["total_amount"] == 1800
    assert 보낸것["body"]["cid"] == "TC0ONETIME"
    # 카드번호 같은 건 애초에 보내지 않는다
    assert not (set(보낸것["body"]) & {"card", "card_number", "cvc", "account"})

    # 주문이 DB 에 남는다 — 재시작해도 살아 있어야 한다
    o = billing.get_order(d["order"])
    assert o["status"] == "ready" and o["credit"] == 3000 and o["amount"] == 1800


def test_1회만_결제는_할인이_없다(키, monkeypatch):
    기록 = []
    d = 준비(_login(), monkeypatch, 100, 기록)
    assert d["결제"] == 100 and d["이용권"] == 100
    assert 기록[0]["body"]["total_amount"] == 100


@pytest.mark.parametrize("응답", [
    {}, {"tid": "T1"}, {"next_redirect_mobile_url": "x"},
    {"tid": None, "next_redirect_mobile_url": "x"}, {"tid": "T1", "next_redirect_mobile_url": ""},
])
def test_준비_응답이_모자라면_502(키, monkeypatch, 응답):
    monkeypatch.setattr(kp.httpx, "AsyncClient", 가짜(응답))
    assert _login().post("/pay/kakao/ready", json={"amount": 1000}).status_code == 502


def test_카카오가_에러를_주면_502(키, monkeypatch):
    monkeypatch.setattr(kp.httpx, "AsyncClient", 가짜({"error": "nope"}, status=400))
    assert _login().post("/pay/kakao/ready", json={"amount": 1000}).status_code == 502


# ---------- 승인 ----------

def 승인(c, order, 금액=1800, monkeypatch=None):
    monkeypatch.setattr(kp.httpx, "AsyncClient",
                        가짜({"aid": "A1", "amount": {"total": 금액}}))
    return c.get(f"/pay/kakao/approve?order={order}&pg_token=PG", follow_redirects=False)


def test_승인하면_서버_잔액이_오른다(키, monkeypatch):
    a = _login()
    order = 준비(a, monkeypatch)["order"]
    assert a.get("/credit").json()["잔액"] == 0

    r = 승인(a, order, 1800, monkeypatch)
    assert r.status_code in (302, 307)
    assert f"pay=ok&order={order}" in r.headers["location"]

    # 1,800원 내고 3,000원짜리 이용권을 받는다
    c = a.get("/credit").json()
    assert c["잔액"] == 3000
    줄 = c["내역"][0]
    assert (줄["종류"], 줄["금액"], 줄["부호"], 줄["결제"], 줄["메모"])         == ("충전", 3000, 1, 1800, "")
    assert a.get(f"/pay/result/{order}").json()["amount"] == 3000


def test_같은_주문은_두_번_충전되지_않는다(키, monkeypatch):
    """승인 콜백이 두 번 와도(새로고침) 한 번만 오른다."""
    a = _login()
    order = 준비(a, monkeypatch)["order"]
    승인(a, order, 1800, monkeypatch)
    r = 승인(a, order, 1800, monkeypatch)
    assert "pay=ok" in r.headers["location"]
    assert a.get("/credit").json()["잔액"] == 3000

    # 원장에 직접 한 번 더 넣으려 해도 막힌다
    billing.charge(1, 3000, 1800, order)
    assert a.get("/credit").json()["잔액"] == 3000


@pytest.mark.parametrize("승인액", [100, 1000, 1799, 1801, 3000, 999999])
def test_청구액과_다르게_승인되면_반영하지_않는다(키, monkeypatch, 승인액):
    """3,000원(이용권 액면)이 승인돼도 청구는 1,800원이었으므로 거부한다."""
    a = _login()
    order = 준비(a, monkeypatch)["order"]
    r = 승인(a, order, 승인액, monkeypatch)
    assert "pay=fail" in r.headers["location"]
    assert a.get("/credit").json()["잔액"] == 0
    assert billing.get_order(order)["status"] == "failed"


@pytest.mark.parametrize("응답", [
    {}, {"amount": {}}, {"amount": {"total": 0}}, {"amount": {"total": "3000"}},
    {"amount": None}, {"amount": {"total": -1}},
])
def test_승인_응답이_이상하면_실패로_보낸다(키, monkeypatch, 응답):
    a = _login()
    order = 준비(a, monkeypatch)["order"]
    monkeypatch.setattr(kp.httpx, "AsyncClient", 가짜(응답))
    r = a.get(f"/pay/kakao/approve?order={order}&pg_token=PG", follow_redirects=False)
    assert "pay=fail" in r.headers["location"]
    assert a.get("/credit").json()["잔액"] == 0


def test_pg_token_이_없으면_승인하지_않는다(키, monkeypatch):
    a = _login()
    order = 준비(a, monkeypatch)["order"]
    r = a.get(f"/pay/kakao/approve?order={order}", follow_redirects=False)
    assert "pay=fail" in r.headers["location"]
    assert a.get("/credit").json()["잔액"] == 0


def test_모르는_주문은_승인하지_않는다(키):
    a = _login()
    r = a.get("/pay/kakao/approve?order=없는주문&pg_token=PG", follow_redirects=False)
    assert "pay=fail" in r.headers["location"]


def test_취소하면_주문이_닫힌다(키, monkeypatch):
    a = _login()
    order = 준비(a, monkeypatch)["order"]
    r = a.get(f"/pay/kakao/cancel?order={order}", follow_redirects=False)
    assert "pay=cancel" in r.headers["location"]
    assert billing.get_order(order)["status"] == "canceled"
    # 취소한 주문은 나중에 승인해도 안 된다
    r2 = 승인(a, order, 1800, monkeypatch)
    assert "pay=fail" in r2.headers["location"]
    assert a.get("/credit").json()["잔액"] == 0


def test_남의_결제_결과는_못_본다(키, monkeypatch):
    a = _login("a@x.com", "가")
    b = _login("b@x.com", "나")
    order = 준비(a, monkeypatch)["order"]
    승인(a, order, 1800, monkeypatch)
    assert b.get(f"/pay/result/{order}").status_code == 404
    assert b.get("/credit").json()["잔액"] == 0


# ---------- 잔액 원장 ----------

def test_잔액은_원장의_합이다(키, monkeypatch):
    a = _login()
    order = 준비(a, monkeypatch)["order"]
    승인(a, order, 1800, monkeypatch)
    assert billing.spend(1, 100, "AI 추천") == 2900
    assert a.get("/credit").json()["잔액"] == 2900
    내역 = a.get("/credit").json()["내역"]
    assert 내역[0]["종류"] == "사용" and 내역[0]["금액"] == 100 and 내역[0]["부호"] == -1


def test_잔액보다_많이_쓸_수_없다():
    _login()
    with pytest.raises(Exception) as e:
        billing.spend(1, 100)
    assert getattr(e.value, "status_code", None) == 402
    assert billing.balance(1) == 0


def test_음수나_0은_차감하지_않는다():
    _login()
    for 나쁜 in (0, -100):
        with pytest.raises(Exception) as e:
            billing.spend(1, 나쁜)
        assert getattr(e.value, "status_code", None) == 400


# ---------- 환불 (청약철회) ----------

def 환불응답(금액):
    return {"canceled_amount": {"total": 금액}, "status": "CANCEL_PAYMENT"}


def 충전된(monkeypatch):
    a = _login()
    order = 준비(a, monkeypatch)["order"]
    승인(a, order, 1800, monkeypatch)
    return a, order


def test_환불하면_돈도_이용권도_되돌아간다(키, monkeypatch):
    a, order = 충전된(monkeypatch)
    기록 = []
    monkeypatch.setattr(kp.httpx, "AsyncClient", 가짜(환불응답(1800), 기록))
    r = a.post(f"/pay/refund/{order}").json()
    assert r == {"ok": True, "환불": 1800, "잔액": 0}
    assert 기록[0]["url"].endswith("/online/v1/payment/cancel")
    assert 기록[0]["body"]["cancel_amount"] == 1800
    assert billing.get_order(order)["status"] == "refunded"
    내역 = a.get("/credit").json()["내역"]
    assert 내역[0]["종류"] == "환불" and 내역[0]["금액"] == 3000


def test_카카오가_취소하지_못하면_이용권을_안_뺏는다(키, monkeypatch):
    """순서가 바뀌면 돈은 그대로인데 이용권만 사라진다."""
    a, order = 충전된(monkeypatch)
    monkeypatch.setattr(kp.httpx, "AsyncClient", 가짜({"error": "no"}, status=400))
    assert a.post(f"/pay/refund/{order}").status_code == 502
    assert a.get("/credit").json()["잔액"] == 3000
    assert billing.get_order(order)["status"] == "paid"


def test_취소_금액이_다르면_환불로_치지_않는다(키, monkeypatch):
    a, order = 충전된(monkeypatch)
    monkeypatch.setattr(kp.httpx, "AsyncClient", 가짜(환불응답(1000)))
    assert a.post(f"/pay/refund/{order}").status_code == 502
    assert a.get("/credit").json()["잔액"] == 3000


def test_남의_결제는_환불할_수_없다(키, monkeypatch):
    a, order = 충전된(monkeypatch)
    b = _login("b@x.com", "나")
    monkeypatch.setattr(kp.httpx, "AsyncClient", 가짜(환불응답(1800)))
    assert b.post(f"/pay/refund/{order}").status_code == 404
    assert a.get("/credit").json()["잔액"] == 3000


def test_결제되지_않은_주문은_환불할_수_없다(키, monkeypatch):
    a = _login()
    order = 준비(a, monkeypatch)["order"]          # ready 까지만
    monkeypatch.setattr(kp.httpx, "AsyncClient", 가짜(환불응답(1800)))
    assert a.post(f"/pay/refund/{order}").status_code == 404


def test_한_번이라도_쓰면_환불할_수_없다(키, monkeypatch):
    """쓴 만큼은 이미 제공한 서비스다. 일부만 돌려주려면 규정이 있어야 한다."""
    a, order = 충전된(monkeypatch)
    billing.spend(1, 100, "AI 추천")              # 3,000 중 100 만 썼어도
    monkeypatch.setattr(kp.httpx, "AsyncClient", 가짜(환불응답(1800)))
    r = a.post(f"/pay/refund/{order}")
    assert r.status_code == 409
    assert "이미 사용한" in r.json()["detail"]
    # 돈도 이용권도 그대로다 — 카카오를 부르지도 않았다
    assert a.get("/credit").json()["잔액"] == 2900
    assert billing.get_order(order)["status"] == "paid"


def test_안_쓰고_그대로면_환불된다(키, monkeypatch):
    a, order = 충전된(monkeypatch)
    monkeypatch.setattr(kp.httpx, "AsyncClient", 가짜(환불응답(1800)))
    assert a.post(f"/pay/refund/{order}").json()["잔액"] == 0


def test_그_결제_전에_쓴_것은_따지지_않는다(키, monkeypatch):
    """예전 충전분을 썼다고 이번 결제를 못 무르면 말이 안 된다."""
    a = _login()
    billing.charge(1, 1000, 1000, "예전주문")
    billing.spend(1, 500, "AI 추천")              # 예전 것에서 씀
    order = 준비(a, monkeypatch)["order"]
    승인(a, order, 1800, monkeypatch)
    assert a.get("/credit").json()["잔액"] == 3500

    monkeypatch.setattr(kp.httpx, "AsyncClient", 가짜(환불응답(1800)))
    assert a.post(f"/pay/refund/{order}").json()["잔액"] == 500


def test_나중_결제는_앞의_사용과_무관하게_환불된다(키, monkeypatch):
    a = _login()
    첫 = 준비(a, monkeypatch)["order"]
    승인(a, 첫, 1800, monkeypatch)
    billing.spend(1, 100, "AI 추천")              # 첫 결제분에서 씀
    둘 = 준비(a, monkeypatch, 1000)["order"]
    승인(a, 둘, 700, monkeypatch)

    monkeypatch.setattr(kp.httpx, "AsyncClient", 가짜(환불응답(1800)))
    assert a.post(f"/pay/refund/{첫}").status_code == 409      # 쓴 것
    monkeypatch.setattr(kp.httpx, "AsyncClient", 가짜(환불응답(700)))
    assert a.post(f"/pay/refund/{둘}").json()["잔액"] == 2900   # 안 쓴 것


def test_환불로_잔액이_음수가_되지_않는다():
    """부르는 쪽을 우회해도 원장이 마지막으로 막는다."""
    _login()
    billing.charge(1, 1000, 1000, "주문A")
    billing.spend(1, 900, "AI 추천")
    with pytest.raises(Exception) as e:
        billing.refund(1, 1000, "주문A")
    assert getattr(e.value, "status_code", None) == 409
    assert billing.balance(1) == 100


# ---------- 환불 버튼이 쓸 정보 ----------

def test_내역이_환불_가능_여부를_함께_준다(키, monkeypatch):
    """환불 규칙을 화면에 옮겨 두면 서버와 어긋난다."""
    a, order = 충전된(monkeypatch)
    줄 = a.get("/credit").json()["내역"][0]
    assert 줄["종류"] == "충전"
    assert 줄["주문번호"] == order
    assert 줄["환불가능"] is True and 줄["사유"] is None


def test_쓰고_나면_환불_불가로_바뀐다(키, monkeypatch):
    a, order = 충전된(monkeypatch)
    billing.spend(1, 100, "AI 추천")
    내역 = a.get("/credit").json()["내역"]
    충전줄 = [x for x in 내역 if x["종류"] == "충전"][0]
    assert 충전줄["환불가능"] is False
    assert "이미 사용" in 충전줄["사유"]
    # 사용 줄에는 환불 얘기가 없다
    사용줄 = [x for x in 내역 if x["종류"] == "사용"][0]
    assert 사용줄["환불가능"] is False and 사용줄["주문번호"] is None


def test_환불한_뒤에는_환불함으로_보인다(키, monkeypatch):
    a, order = 충전된(monkeypatch)
    monkeypatch.setattr(kp.httpx, "AsyncClient", 가짜(환불응답(1800)))
    a.post(f"/pay/refund/{order}")
    충전줄 = [x for x in a.get("/credit").json()["내역"] if x["종류"] == "충전"][0]
    assert 충전줄["환불가능"] is False and 충전줄["사유"] == "환불함"


def test_나중_결제만_환불_가능으로_표시된다(키, monkeypatch):
    a = _login()
    첫 = 준비(a, monkeypatch)["order"]
    승인(a, 첫, 1800, monkeypatch)
    billing.spend(1, 100, "AI 추천")
    둘 = 준비(a, monkeypatch, 1000)["order"]
    승인(a, 둘, 700, monkeypatch)

    표 = {x["주문번호"]: x["환불가능"] for x in a.get("/credit").json()["내역"]
          if x["종류"] == "충전"}
    assert 표[첫] is False and 표[둘] is True



# ---------- 접속 환경별 결제창 주소 ----------

READY_3 = {"tid": "T1",
           "next_redirect_pc_url": "https://kakao/pc",
           "next_redirect_mobile_url": "https://kakao/mo",
           "next_redirect_app_url": "https://kakao/app"}


def test_세_주소를_모두_돌려준다(키, monkeypatch):
    """PC 에서 모바일 주소로 보내면 결제 화면이 제대로 뜨지 않는다.

    PC 주소가 카카오톡으로 결제 요청을 보내는 화면(QR)이다.
    """
    monkeypatch.setattr(kp.httpx, "AsyncClient", 가짜(READY_3))
    d = _login().post("/pay/kakao/ready", json={"amount": 3000}).json()
    assert d["redirect_pc"] == "https://kakao/pc"
    assert d["redirect_mobile"] == "https://kakao/mo"
    assert d["redirect_app"] == "https://kakao/app"


@pytest.mark.parametrize("빠진것, 기대", [
    ("next_redirect_pc_url", {"pc": "https://kakao/mo"}),
    ("next_redirect_mobile_url", {"mobile": "https://kakao/pc"}),
    ("next_redirect_app_url", {"app": "https://kakao/mo"}),
])
def test_하나가_비면_있는_것으로_메운다(키, monkeypatch, 빠진것, 기대):
    """빈 주소로 보내면 화면이 그 자리에서 멈춘다."""
    응답 = {k: v for k, v in READY_3.items() if k != 빠진것}
    monkeypatch.setattr(kp.httpx, "AsyncClient", 가짜(응답))
    d = _login().post("/pay/kakao/ready", json={"amount": 3000}).json()
    for 키이름, 값 in 기대.items():
        assert d[f"redirect_{키이름}"] == 값
    assert all(d[f"redirect_{k}"] for k in ("pc", "mobile", "app"))


# ---------- 실패 이유를 그대로 알려 준다 ----------

@pytest.mark.parametrize("코드, 조각", [
    (-401, "SECRET KEY"),
    (-403, "사용 API"),
    (-429, "한도"),
    (-500, "카카오페이 서버"),
    (-503, "점검"),
])
def test_카카오_에러코드를_할_일로_바꿔_알려준다(키, monkeypatch, 코드, 조각):
    """'실패했다' 만 알려주면 붙이는 사람이 손쓸 방법이 없다."""
    monkeypatch.setattr(kp.httpx, "AsyncClient",
                        가짜({"error_code": 코드, "error_message": "x"}, status=abs(코드)))
    r = _login().post("/pay/kakao/ready", json={"amount": 100})
    assert r.status_code == 502
    assert 조각 in r.json()["detail"], r.json()["detail"]


def test_모르는_에러코드는_일반_문구로_둔다(키, monkeypatch):
    monkeypatch.setattr(kp.httpx, "AsyncClient",
                        가짜({"error_code": -9999, "error_message": "x"}, status=400))
    r = _login().post("/pay/kakao/ready", json={"amount": 100})
    assert r.status_code == 502
    assert r.json()["detail"] == "카카오페이 결제를 시작하지 못했어요."


def test_에러가_JSON_이_아니어도_터지지_않는다(키, monkeypatch):
    class Patched(_REAL_CLIENT):
        def __init__(self, *a, **kw):
            kw["transport"] = httpx.MockTransport(
                lambda req: httpx.Response(500, text="<html>gateway</html>"))
            super().__init__(*a, **kw)
    monkeypatch.setattr(kp.httpx, "AsyncClient", Patched)
    r = _login().post("/pay/kakao/ready", json={"amount": 100})
    assert r.status_code == 502


def test_실패_이유를_서버_로그에_남긴다(키, monkeypatch, caplog):
    """운영에서 눈으로 볼 수 있어야 한다."""
    import logging
    monkeypatch.setattr(kp.httpx, "AsyncClient",
                        가짜({"error_code": -403, "error_message": "사용 API에 없습니다"}, status=403))
    with caplog.at_level(logging.WARNING):
        _login().post("/pay/kakao/ready", json={"amount": 100})
    합친것 = " ".join(r.getMessage() for r in caplog.records)
    assert "ready" in 합친것 and "-403" in 합친것
