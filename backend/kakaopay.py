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

import logging
import os
import uuid

import httpx

log = logging.getLogger(__name__)

HOST = os.getenv("KAKAOPAY_HOST", "https://open-api.kakaopay.com").rstrip("/")
READY = "/online/v1/payment/ready"
APPROVE = "/online/v1/payment/approve"
CANCEL = "/online/v1/payment/cancel"
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


def _fail(where: str, status: int | None, body) -> dict:
    """실패 이유를 남기고, 부르는 쪽이 화면에 보여 줄 만큼만 돌려준다.

    예전에는 그냥 None 을 돌려줘서 "실패했다" 밖에 알 수 없었다. 설정이 틀렸는지
    키가 틀렸는지 구분이 안 되면 붙이는 사람이 손쓸 방법이 없다.
    """
    코드 = None
    메시지 = None
    if isinstance(body, dict):
        코드 = body.get("error_code")
        메시지 = body.get("error_message")
    log.warning("카카오페이 %s 실패: status=%s error_code=%s error_message=%s",
                where, status, 코드, 메시지)
    return {"error": {"status": status, "code": 코드, "message": 메시지}}


# 카카오가 알려 주는 흔한 원인 — 붙이는 사람에게 다음 할 일을 바로 알려 준다
ERROR_HINT = {
    -400: "요청이 잘못됐어요. 서버 설정을 확인해 주세요.",
    -401: "SECRET KEY 가 맞지 않아요. 키를 다시 확인해 주세요.",
    -403: "카카오페이 개발자센터에서 '사용 API' 에 온라인 결제를 등록해 주세요.",
    -404: "요청 주소가 잘못됐어요.",
    -429: "오늘 호출 한도를 넘었어요. 내일 다시 시도해 주세요.",
    -500: "카카오페이 서버 오류예요. 잠시 뒤 다시 시도해 주세요.",
    -503: "카카오페이가 점검 중이에요. 잠시 뒤 다시 시도해 주세요.",
}


def hint(err: dict | None) -> str:
    """사용자에게 보여 줄 한 줄. 모르는 코드면 일반 문구로 둔다."""
    e = (err or {}).get("error") or {}
    return ERROR_HINT.get(e.get("code"), "카카오페이 결제를 시작하지 못했어요.")


def _headers() -> dict:
    return {
        "Authorization": f"SECRET_KEY {secret_key()}",
        "Content-Type": "application/json",
    }


def new_order_id() -> str:
    return uuid.uuid4().hex


async def ready(*, amount: int, order_id: str, user_id: str,
                approval_url: str, cancel_url: str, fail_url: str) -> dict | None:
    """결제 준비. 성공하면 {"tid", "redirect_pc", "redirect_mobile", "redirect_app"}.

    카카오는 접속 환경별로 서로 다른 주소를 준다. **아무거나 쓰면 안 된다.**
      next_redirect_pc_url     PC 웹 — 카카오톡으로 결제 요청을 보내는 화면(QR)
      next_redirect_mobile_url 모바일 웹
      next_redirect_app_url    모바일 앱
    셋 다 돌려주고 고르는 일은 화면에 맡긴다 — 서버는 접속 환경을 모른다.

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
                try:
                    본문 = r.json()
                except Exception:
                    본문 = r.text[:300]
                return _fail("ready", r.status_code, 본문)
            d = r.json()
    except Exception as e:
        log.warning("카카오페이 ready 호출 실패: %r", e)
        return None

    tid = d.get("tid")
    pc = d.get("next_redirect_pc_url")
    mo = d.get("next_redirect_mobile_url")
    app = d.get("next_redirect_app_url")
    if not tid or not (pc or mo or app):
        return None
    # 하나라도 비면 있는 것으로 메운다. 빈 주소로 보내면 화면이 멈춘다.
    있는것 = pc or mo or app
    return {"tid": tid,
            "redirect_pc": pc or 있는것,
            "redirect_mobile": mo or 있는것,
            "redirect_app": app or mo or 있는것}


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
                try:
                    본문 = r.json()
                except Exception:
                    본문 = r.text[:300]
                _fail("approve", r.status_code, 본문)
                return None
            d = r.json()
    except Exception as e:
        log.warning("카카오페이 approve 호출 실패: %r", e)
        return None

    amount = (d.get("amount") or {}).get("total")
    if not isinstance(amount, int) or amount <= 0:
        return None
    return {"amount": amount, "aid": d.get("aid"), "approved_at": d.get("approved_at")}


async def cancel(*, tid: str, amount: int) -> dict | None:
    """결제 취소(환불). 전액만 다룬다 — 부분 환불은 규정을 정하고 붙일 것.

    전자상거래법상 청약철회를 받아야 하므로 운영에 이 길이 필요하다.
    성공하면 {"canceled": 취소된 금액}. 실패하면 None.
    """
    if not available():
        return None
    body = {
        "cid": cid(),
        "tid": tid,
        "cancel_amount": int(amount),
        "cancel_tax_free_amount": 0,
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SEC) as http:
            r = await http.post(HOST + CANCEL, json=body, headers=_headers())
            if r.status_code >= 400:
                try:
                    본문 = r.json()
                except Exception:
                    본문 = r.text[:300]
                _fail("cancel", r.status_code, 본문)
                return None
            d = r.json()
    except Exception as e:
        log.warning("카카오페이 cancel 호출 실패: %r", e)
        return None

    총 = (d.get("canceled_amount") or {}).get("total")
    if not isinstance(총, int) or 총 <= 0:
        return None
    return {"canceled": 총, "status": d.get("status")}
