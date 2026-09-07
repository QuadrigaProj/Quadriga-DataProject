"""카카오페이 단건결제 — 이용권 충전에만 쓴다.

흐름은 카카오 문서 그대로다.
    1. ready   : 결제를 준비하고 tid 와 결제창 주소를 받는다
    2. 사용자가 그 주소에서 결제한다
    3. approve : 돌아온 pg_token 으로 승인한다 (여기서 실제로 돈이 빠진다)

**키가 없으면 아무것도 부르지 않는다.** available() 이 False 면 화면은
카카오페이 버튼을 잠그고 다른 수단만 보여 준다.

설정
    1. https://developers.kakao.com 에서 앱을 만들고 카카오페이를 신청한다
    2. .env 에 넣는다
         KAKAOPAY_SECRET_KEY=DEV...      (개발용은 DEV 로 시작한다)
         KAKAOPAY_CID=TC0ONETIME         (기본값. 테스트 가맹점 코드다)
    3. 서버 재시작

주의
  - 기본 CID 는 카카오가 주는 **테스트 코드**(TC0ONETIME)다. 실제 돈이
    빠지지 않는다. 실결제는 가맹점 계약 후 발급받은 CID 로 바꿔야 한다.
  - 카드번호·CVC 는 이 서버가 받지 않는다. 카카오 결제창이 받는다.
"""
from __future__ import annotations

import os
import uuid

import httpx

HOST = os.getenv("KAKAOPAY_HOST", "https://open-api.kakaopay.com").rstrip("/")
READY = "/online/v1/payment/ready"
APPROVE = "/online/v1/payment/approve"
TIMEOUT_SEC = 10.0

# 테스트 가맹점 코드. 실제 계약을 하면 발급받은 코드로 바꾼다.
TEST_CID = "TC0ONETIME"

ITEM_NAME = "Fitage AI 추천 이용권"


def secret_key() -> str:
    return (os.getenv("KAKAOPAY_SECRET_KEY") or "").strip()


def cid() -> str:
    return (os.getenv("KAKAOPAY_CID") or TEST_CID).strip()


def available() -> bool:
    """키가 있어야만 부른다."""
    return bool(secret_key())


def is_test() -> bool:
    """테스트 가맹점 코드로 도는 중인지 — 화면에 그대로 알린다."""
    return cid() == TEST_CID


def _headers() -> dict:
    return {
        "Authorization": f"SECRET_KEY {secret_key()}",
        "Content-Type": "application/json",
    }


def new_order_id() -> str:
    return uuid.uuid4().hex


async def ready(*, amount: int, order_id: str, user_id: str,
                approval_url: str, cancel_url: str, fail_url: str) -> dict | None:
    """결제 준비. 성공하면 {"tid", "redirect_pc", "redirect_mobile"}.

    실패하면 None 을 돌려준다 — 부르는 쪽이 다른 수단으로 안내한다.
    """
    if not available():
        return None
    body = {
        "cid": cid(),
        "partner_order_id": order_id,
        "partner_user_id": user_id,
        "item_name": ITEM_NAME,
        "quantity": 1,
        "total_amount": int(amount),
        "tax_free_amount": 0,
        "approval_url": approval_url,
        "cancel_url": cancel_url,
        "fail_url": fail_url,
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SEC) as http:
            r = await http.post(HOST + READY, json=body, headers=_headers())
            if r.status_code >= 400:
                return None
            d = r.json()
    except Exception:
        return None

    tid = d.get("tid")
    pc = d.get("next_redirect_pc_url")
    mo = d.get("next_redirect_mobile_url")
    if not tid or not (pc or mo):
        return None
    return {"tid": tid, "redirect_pc": pc or mo, "redirect_mobile": mo or pc}


async def approve(*, tid: str, pg_token: str, order_id: str, user_id: str) -> dict | None:
    """승인. 성공하면 {"amount", "aid", "approved_at"}. 실패하면 None.

    금액은 **카카오가 알려준 값**을 쓴다. 화면이 보낸 숫자를 믿지 않는다.
    """
    if not available():
        return None
    body = {
        "cid": cid(),
        "tid": tid,
        "partner_order_id": order_id,
        "partner_user_id": user_id,
        "pg_token": pg_token,
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SEC) as http:
            r = await http.post(HOST + APPROVE, json=body, headers=_headers())
            if r.status_code >= 400:
                return None
            d = r.json()
    except Exception:
        return None

    amount = (d.get("amount") or {}).get("total")
    if not isinstance(amount, int) or amount <= 0:
        return None
    return {"amount": amount, "aid": d.get("aid"), "approved_at": d.get("approved_at")}
