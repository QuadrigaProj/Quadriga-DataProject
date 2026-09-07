"""카카오페이 이용권 결제.

실제 카카오 서버를 부르지 않는다. httpx.MockTransport 로 응답을 만들어
**우리가 보내는 요청 모양**과 **이상한 응답에서 안 터지는지**를 본다.

지켜야 할 것
  - 키가 없으면 아무것도 부르지 않는다
  - 승인 금액은 카카오가 알려준 값을 쓴다 (화면이 보낸 숫자를 안 믿는다)
  - 한 주문은 한 번만 반영된다 (새로고침으로 두 번 충전되지 않는다)
  - 카드번호 같은 건 애초에 주고받지 않는다
"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import kakaopay as kp
from backend import main as m

client = TestClient(m.app)

# 진짜 AsyncClient 를 한 번만 붙잡아 둔다. 매번 잡으면 앞서 끼운 가짜를
# 다시 상속해서, 나중에 끼운 응답이 앞의 것에 덮인다.
_REAL_CLIENT = httpx.AsyncClient


@pytest.fixture
def 키(monkeypatch):
    monkeypatch.setenv("KAKAOPAY_SECRET_KEY", "DEV_TEST_KEY")
    monkeypatch.setenv("KAKAOPAY_CID", "TC0ONETIME")


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


# ---------- 키가 없을 때 ----------

def test_키가_없으면_쓸수없다고_알린다():
    d = client.get("/pay/methods").json()
    assert d["kakao"]["쓸수있음"] is False
    assert d["packs"] == [1000, 3000, 5000]


def test_키가_없으면_준비도_안_한다():
    r = client.post("/pay/kakao/ready", json={"amount": 3000})
    assert r.status_code == 503


@pytest.mark.anyio
async def test_모듈이_키_없이_호출되면_None():
    assert await kp.ready(amount=1000, order_id="a", user_id="u",
                          approval_url="x", cancel_url="y", fail_url="z") is None
    assert await kp.approve(tid="t", pg_token="p", order_id="a", user_id="u") is None


# ---------- 준비 ----------

def test_고를_수_없는_금액은_거절한다(키):
    assert client.post("/pay/kakao/ready", json={"amount": 7}).status_code == 400
    assert client.post("/pay/kakao/ready", json={"amount": -3000}).status_code == 400


def test_준비하면_결제창_주소를_준다(키, monkeypatch):
    기록 = []
    monkeypatch.setattr(kp.httpx, "AsyncClient",
                        가짜({"tid": "T1", "next_redirect_pc_url": "https://kakao/pc",
                             "next_redirect_mobile_url": "https://kakao/mo"}, 기록))
    r = client.post("/pay/kakao/ready", json={"amount": 3000})
    assert r.status_code == 200
    d = r.json()
    assert d["redirect"] == "https://kakao/mo"
    assert d["order"]

    보낸것 = 기록[0]
    assert 보낸것["url"].endswith("/online/v1/payment/ready")
    assert 보낸것["headers"]["authorization"] == "SECRET_KEY DEV_TEST_KEY"
    assert 보낸것["body"]["total_amount"] == 3000
    assert 보낸것["body"]["cid"] == "TC0ONETIME"
    # 카드번호 같은 건 애초에 보내지 않는다
    assert not (set(보낸것["body"]) & {"card", "card_number", "cvc", "account"})


@pytest.mark.parametrize("응답", [
    {}, {"tid": "T1"}, {"next_redirect_mobile_url": "x"},
    {"tid": None, "next_redirect_mobile_url": "x"}, {"tid": "T1", "next_redirect_mobile_url": ""},
])
def test_준비_응답이_모자라면_502(키, monkeypatch, 응답):
    monkeypatch.setattr(kp.httpx, "AsyncClient", 가짜(응답))
    assert client.post("/pay/kakao/ready", json={"amount": 1000}).status_code == 502


def test_카카오가_에러를_주면_502(키, monkeypatch):
    monkeypatch.setattr(kp.httpx, "AsyncClient", 가짜({"error": "nope"}, status=400))
    assert client.post("/pay/kakao/ready", json={"amount": 1000}).status_code == 502


# ---------- 승인 ----------

def 준비(monkeypatch):
    monkeypatch.setattr(kp.httpx, "AsyncClient",
                        가짜({"tid": "T1", "next_redirect_mobile_url": "https://kakao/mo"}))
    return client.post("/pay/kakao/ready", json={"amount": 3000}).json()["order"]


def test_승인하면_충전을_반영할_수_있다(키, monkeypatch):
    order = 준비(monkeypatch)
    monkeypatch.setattr(kp.httpx, "AsyncClient",
                        가짜({"aid": "A1", "amount": {"total": 3000}}))
    r = client.get(f"/pay/kakao/approve?order={order}&pg_token=PG",
                   follow_redirects=False)
    assert r.status_code in (302, 307)
    assert f"pay=ok&order={order}" in r.headers["location"]

    d = client.get(f"/pay/result/{order}").json()
    assert d == {"paid": True, "amount": 3000}


def test_같은_주문은_두_번_반영되지_않는다(키, monkeypatch):
    order = 준비(monkeypatch)
    monkeypatch.setattr(kp.httpx, "AsyncClient", 가짜({"amount": {"total": 3000}}))
    client.get(f"/pay/kakao/approve?order={order}&pg_token=PG", follow_redirects=False)
    assert client.get(f"/pay/result/{order}").status_code == 200
    assert client.get(f"/pay/result/{order}").status_code == 404      # 새로고침해도 한 번뿐


def test_승인_금액은_카카오가_말한_값을_쓴다(키, monkeypatch):
    """화면이 3000원을 준비했어도 카카오가 1000원이라 하면 1000원이다."""
    order = 준비(monkeypatch)
    monkeypatch.setattr(kp.httpx, "AsyncClient", 가짜({"amount": {"total": 1000}}))
    client.get(f"/pay/kakao/approve?order={order}&pg_token=PG", follow_redirects=False)
    assert client.get(f"/pay/result/{order}").json()["amount"] == 1000


@pytest.mark.parametrize("응답", [
    {}, {"amount": {}}, {"amount": {"total": 0}}, {"amount": {"total": "3000"}},
    {"amount": None}, {"amount": {"total": -1}},
])
def test_승인_응답이_이상하면_실패로_보낸다(키, monkeypatch, 응답):
    order = 준비(monkeypatch)
    monkeypatch.setattr(kp.httpx, "AsyncClient", 가짜(응답))
    r = client.get(f"/pay/kakao/approve?order={order}&pg_token=PG", follow_redirects=False)
    assert "pay=fail" in r.headers["location"]
    assert client.get(f"/pay/result/{order}").status_code == 404


def test_pg_token_이_없으면_승인하지_않는다(키, monkeypatch):
    order = 준비(monkeypatch)
    r = client.get(f"/pay/kakao/approve?order={order}", follow_redirects=False)
    assert "pay=fail" in r.headers["location"]


def test_모르는_주문은_승인하지_않는다(키):
    r = client.get("/pay/kakao/approve?order=없는주문&pg_token=PG", follow_redirects=False)
    assert "pay=fail" in r.headers["location"]


def test_취소하면_준비한_주문이_사라진다(키, monkeypatch):
    order = 준비(monkeypatch)
    r = client.get(f"/pay/kakao/cancel?order={order}", follow_redirects=False)
    assert "pay=cancel" in r.headers["location"]
    # 취소한 주문은 나중에 승인해도 안 된다
    r2 = client.get(f"/pay/kakao/approve?order={order}&pg_token=PG", follow_redirects=False)
    assert "pay=fail" in r2.headers["location"]
