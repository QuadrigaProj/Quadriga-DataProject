"""이용권 잔액과 결제 주문 — 서버가 들고 있는다.

실제로 돈을 받으려면 이 두 가지는 브라우저에 둘 수 없다.

1. **잔액**
   지금까지 잔액은 화면 스냅샷(state.credit)에만 있었다. 시연이면 괜찮지만,
   실제 결제에서는 브라우저에서 숫자만 바꾸면 AI 추천을 공짜로 무제한 쓸 수
   있다. 그래서 원장(credit_ledger)에 한 줄씩 쌓고, 잔액은 그 합으로 낸다.
   충전도 차감도 서버에서만 일어난다.

2. **주문**
   준비(ready)와 승인(approve) 사이에 서버가 재시작되면 메모리에 있던 주문이
   사라진다. 사용자는 돈을 냈는데 이용권이 안 올라간다. DB에 남긴다.

한 주문은 한 번만 반영된다 — order_id 에 UNIQUE 를 걸어 DB 가 막는다.
같은 승인 콜백이 두 번 와도 두 번 충전되지 않는다.
"""
from __future__ import annotations

import time

try:
    from backend import auth
except ImportError:                          # backend/ 안에서 직접 실행할 때
    import auth                              # noqa: F401

from fastapi import HTTPException

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS credit_ledger (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  amount     INTEGER NOT NULL,          -- 이용권 증감(원). 충전 +, 사용 -
  kind       TEXT NOT NULL,             -- charge | use | refund
  paid       INTEGER,                   -- 실제로 낸 돈(원). 충전일 때만
  order_id   TEXT,                      -- 결제 주문번호. 같은 주문은 한 번만
  memo       TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ledger_user ON credit_ledger(user_id, id DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ledger_order ON credit_ledger(order_id);

CREATE TABLE IF NOT EXISTS pay_orders (
  order_id   TEXT PRIMARY KEY,
  user_id    INTEGER,                   -- 손님 결제는 NULL
  tid        TEXT NOT NULL,
  credit     INTEGER NOT NULL,          -- 올려 줄 이용권
  amount     INTEGER NOT NULL,          -- 실제 청구액
  status     TEXT NOT NULL,             -- ready | paid | canceled | failed | refunded
  aid        TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orders_user ON pay_orders(user_id, created_at DESC);
"""
SCHEMA_PG = (SCHEMA_SQLITE
             .replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY"))


def init_db() -> None:
    schema = SCHEMA_PG if auth.is_postgres() else SCHEMA_SQLITE
    with auth.db() as con:
        for stmt in filter(str.strip, schema.split(";")):
            con.execute(stmt)


# ---------------- 잔액 ----------------

def balance(user_id: int) -> int:
    """원장의 합. 음수가 될 수 없게 차감 쪽에서 막는다."""
    with auth.db() as con:
        r = con.execute("SELECT COALESCE(SUM(amount), 0) AS s FROM credit_ledger"
                        " WHERE user_id=?", (user_id,)).fetchone()
    return int(r["s"] or 0)


def history(user_id: int, limit: int = 30) -> list[dict]:
    with auth.db() as con:
        rows = con.execute(
            "SELECT amount, kind, paid, memo, created_at FROM credit_ledger"
            " WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit)).fetchall()
    종류 = {"charge": "충전", "use": "사용", "refund": "환불"}
    return [{"종류": 종류.get(r["kind"], r["kind"]),
             "금액": abs(int(r["amount"])), "부호": 1 if r["amount"] > 0 else -1,
             "결제": r["paid"], "메모": r["memo"],
             "때": int(r["created_at"])} for r in rows]


def _add(con, user_id: int, amount: int, kind: str, *,
         paid: int | None = None, order_id: str | None = None, memo: str = "") -> None:
    con.execute(
        "INSERT INTO credit_ledger (user_id, amount, kind, paid, order_id, memo, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (user_id, int(amount), kind, paid, order_id, memo, int(time.time())))


def charge(user_id: int, credit: int, paid: int, order_id: str) -> int:
    """결제 승인분을 올린다. 같은 주문은 한 번만 — DB 가 막는다."""
    with auth.db() as con:
        있음 = con.execute("SELECT 1 FROM credit_ledger WHERE order_id=?",
                          (order_id,)).fetchone()
        if not 있음:
            _add(con, user_id, credit, "charge", paid=paid, order_id=order_id)
    return balance(user_id)


def spend(user_id: int, amount: int, memo: str = "") -> int:
    """차감. 잔액이 모자라면 402 로 막고 한 푼도 쓰지 않는다."""
    if amount <= 0:
        raise HTTPException(400, "차감 금액을 확인해 주세요.")
    with auth.db() as con:
        r = con.execute("SELECT COALESCE(SUM(amount), 0) AS s FROM credit_ledger"
                        " WHERE user_id=?", (user_id,)).fetchone()
        남음 = int(r["s"] or 0)
        if 남음 < amount:
            raise HTTPException(402, "이용권이 모자라요. 먼저 충전해 주세요.")
        _add(con, user_id, -amount, "use", memo=memo)
        return 남음 - amount


def refund(user_id: int, credit: int, order_id: str, memo: str = "") -> int:
    """환불한 만큼 이용권을 되돌린다(음수 한 줄).

    이미 써 버려서 잔액이 모자라면 그대로 마이너스가 된다 — 숨기지 않는다.
    운영에서 눈에 보여야 조치할 수 있다.
    """
    with auth.db() as con:
        _add(con, user_id, -credit, "refund", order_id=f"refund:{order_id}", memo=memo)
    return balance(user_id)


# ---------------- 주문 ----------------

def new_order(order_id: str, user_id: int | None, tid: str,
              credit: int, amount: int) -> None:
    now = int(time.time())
    with auth.db() as con:
        con.execute(
            "INSERT INTO pay_orders (order_id, user_id, tid, credit, amount, status,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (order_id, user_id, tid, int(credit), int(amount), "ready", now, now))


def get_order(order_id: str) -> dict | None:
    with auth.db() as con:
        r = con.execute("SELECT * FROM pay_orders WHERE order_id=?", (order_id,)).fetchone()
    return dict(r) if r else None


def set_status(order_id: str, status: str, aid: str | None = None) -> None:
    with auth.db() as con:
        con.execute("UPDATE pay_orders SET status=?, aid=COALESCE(?, aid), updated_at=?"
                    " WHERE order_id=?", (status, aid, int(time.time()), order_id))
