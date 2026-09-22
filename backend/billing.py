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

import datetime as _dt
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
  credit     INTEGER NOT NULL,          -- 올려 줄 이용권 (구독이면 0)
  amount     INTEGER NOT NULL,          -- 실제 청구액
  status     TEXT NOT NULL,             -- ready | paid | canceled | failed | refunded
  aid        TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  product    TEXT                       -- NULL=이용권 충전 · '구독'=한 달 구독
);
CREATE INDEX IF NOT EXISTS idx_orders_user ON pay_orders(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ai_usage (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER,
  ip         TEXT,
  kind       TEXT NOT NULL,             -- 루틴 | 조정 | 구간 | 시간표사진 | 건강사진
  day        TEXT NOT NULL,             -- YYYY-MM-DD (한국 시간). 하루 횟수를 셀 때
  paid       INTEGER NOT NULL,          -- 받은 값(원). 시연 · 이용권 안이면 0
  input_tok  INTEGER,                   -- 응답의 usage — 원가 계산용
  output_tok INTEGER,
  cache_tok  INTEGER,
  model      TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_usage_user ON ai_usage(user_id, day);
CREATE INDEX IF NOT EXISTS idx_ai_usage_ip ON ai_usage(ip, day);

CREATE TABLE IF NOT EXISTS ai_addons (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind       TEXT NOT NULL,             -- 상세 (자세히 보기) | 구독
  starts_at  INTEGER NOT NULL,
  ends_at    INTEGER NOT NULL,
  memo       TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_ai_addons_user ON ai_addons(user_id, ends_at DESC);
"""
SCHEMA_PG = (SCHEMA_SQLITE
             .replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY"))


def init_db() -> None:
    schema = SCHEMA_PG if auth.is_postgres() else SCHEMA_SQLITE
    with auth.db() as con:
        for stmt in filter(str.strip, schema.split(";")):
            con.execute(stmt)
    # 예전에 만든 표에는 product 칸이 없다 — 있으면 그대로, 없으면 붙인다
    with auth.db() as con:
        try:
            con.execute("ALTER TABLE pay_orders ADD COLUMN product TEXT")
        except Exception:                 # 이미 있다 (sqlite · postgres 둘 다 '중복 칸' 오류를 낸다)
            pass


# ---------------- 잔액 ----------------

def balance(user_id: int) -> int:
    """원장의 합. 음수가 될 수 없게 차감 쪽에서 막는다."""
    with auth.db() as con:
        r = con.execute("SELECT COALESCE(SUM(amount), 0) AS s FROM credit_ledger"
                        " WHERE user_id=?", (user_id,)).fetchone()
    return int(r["s"] or 0)


def history(user_id: int, limit: int = 30) -> list[dict]:
    """결제 내역. 충전 줄에는 환불할 수 있는지도 함께 적는다.

    환불 규칙을 화면에 옮겨 두면 서버와 어긋난다. 여기서 판단해서 내려준다.
    """
    with auth.db() as con:
        rows = con.execute(
            "SELECT id, amount, kind, paid, order_id, memo, created_at FROM credit_ledger"
            " WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit)).fetchall()
        # 마지막 '사용' 보다 뒤에 있는 충전만 아직 안 쓴 것이다 — 한 번에 구한다
        u = con.execute("SELECT COALESCE(MAX(id), 0) AS m FROM credit_ledger"
                        " WHERE user_id=? AND kind='use'", (user_id,)).fetchone()
        마지막사용 = int(u["m"] or 0)
        낸주문 = {o["order_id"]: o["status"] for o in con.execute(
            "SELECT order_id, status FROM pay_orders WHERE user_id=?", (user_id,)).fetchall()}

    종류 = {"charge": "충전", "use": "사용", "refund": "환불", "sub": "구독"}
    out = []
    for r in rows:
        줄 = {"종류": 종류.get(r["kind"], r["kind"]),
             "금액": abs(int(r["amount"])), "부호": 1 if r["amount"] > 0 else -1,
             "결제": r["paid"], "메모": r["memo"],
             "때": int(r["created_at"]),
             "주문번호": None, "환불가능": False, "사유": None}
        if r["kind"] == "charge" and r["order_id"]:
            줄["주문번호"] = r["order_id"]
            상태 = 낸주문.get(r["order_id"])
            if 상태 == "refunded":
                줄["사유"] = "환불함"
            elif 상태 != "paid":
                줄["사유"] = "환불할 수 없는 결제예요"
            elif r["id"] < 마지막사용:
                줄["사유"] = "이미 사용해서 환불할 수 없어요"
            else:
                줄["환불가능"] = True
        out.append(줄)
    return out


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


def used_after(user_id: int, order_id: str) -> bool:
    """그 결제로 받은 이용권을 한 번이라도 썼는지.

    원장은 넣은 순서대로 id 가 붙는다. 그 결제의 충전 줄보다 뒤에 사용 줄이
    하나라도 있으면 쓴 것으로 본다 — 나중에 한 다른 충전은 이 판단에 끼지 않는다.
    """
    with auth.db() as con:
        r = con.execute("SELECT id FROM credit_ledger WHERE order_id=?",
                        (order_id,)).fetchone()
        if not r:
            return False
        뒤 = con.execute(
            "SELECT 1 FROM credit_ledger WHERE user_id=? AND kind='use' AND id>? LIMIT 1",
            (user_id, r["id"])).fetchone()
    return bool(뒤)


def refund(user_id: int, credit: int, order_id: str, memo: str = "") -> int:
    """환불한 만큼 이용권을 되돌린다(음수 한 줄).

    부르는 쪽이 used_after 로 막고 오므로 여기서 잔액이 음수가 될 일은 없다.
    그래도 한 번 더 확인한다 — 돈이 걸린 자리라 조용히 마이너스로 두지 않는다.
    """
    with auth.db() as con:
        r = con.execute("SELECT COALESCE(SUM(amount), 0) AS s FROM credit_ledger"
                        " WHERE user_id=?", (user_id,)).fetchone()
        if int(r["s"] or 0) < credit:
            raise HTTPException(409, "이미 사용한 이용권은 환불할 수 없어요.")
        _add(con, user_id, -credit, "refund", order_id=f"refund:{order_id}", memo=memo)
    return balance(user_id)


# ---------------- AI 사용 기록 · 부가 이용권 ----------------
#
# 호출 하나하나를 남긴다. 두 가지 쓸모 — (1) 시연 기간의 하루 무료 횟수를 센다,
# (2) 응답의 토큰 수(usage)를 적어 두어 실제 원가를 안다. 청구서가 와야 아는 것과는 다르다.

KST = _dt.timezone(_dt.timedelta(hours=9))


def kst_today(now: float | None = None) -> str:
    """한국 날짜 — 하루 횟수는 한국 자정에 새로 센다."""
    return _dt.datetime.fromtimestamp(now if now is not None else time.time(), KST).date().isoformat()


def note_ai_use(user_id: int | None, ip: str | None, kind: str, paid: int,
                usage: dict | None = None, now: float | None = None) -> None:
    u = usage or {}
    with auth.db() as con:
        con.execute(
            "INSERT INTO ai_usage (user_id, ip, kind, day, paid, input_tok, output_tok, cache_tok, model, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (user_id, ip, kind, kst_today(now), int(paid), u.get("input"), u.get("output"), u.get("cache"),
             u.get("model"), int(now if now is not None else time.time())))


def ai_uses_today(user_id: int, kinds: tuple[str, ...], now: float | None = None) -> int:
    """오늘(한국 시간) 이 사람이 그 종류들을 몇 번 썼는지."""
    자리 = ",".join("?" * len(kinds))
    with auth.db() as con:
        r = con.execute(f"SELECT COUNT(*) AS n FROM ai_usage WHERE user_id=? AND day=? AND kind IN ({자리})",
                        (user_id, kst_today(now), *kinds)).fetchone()
    return int(r["n"] or 0)


def ai_uses_today_ip(ip: str, now: float | None = None) -> int:
    """오늘 한 곳(IP)에서 AI 를 몇 번 불렀는지 — 계정을 늘려 무료 횟수를 우회하는 것을 막는다."""
    with auth.db() as con:
        r = con.execute("SELECT COUNT(*) AS n FROM ai_usage WHERE ip=? AND day=?", (ip, kst_today(now))).fetchone()
    return int(r["n"] or 0)


def ai_uses_since(user_id: int, kind: str, since: int) -> int:
    with auth.db() as con:
        r = con.execute("SELECT COUNT(*) AS n FROM ai_usage WHERE user_id=? AND kind=? AND created_at>=?",
                        (user_id, kind, int(since))).fetchone()
    return int(r["n"] or 0)


def add_addon(user_id: int, kind: str, days: int, memo: str = "", now: float | None = None) -> dict:
    """부가 이용권(자세히 보기 · 구독)을 연다. 아직 남은 것이 있으면 그 끝에 이어 붙인다 — 겹쳐 사도 날이 사라지지 않는다."""
    now = int(now if now is not None else time.time())
    있는것 = active_addon(user_id, kind, now)
    시작 = now
    끝 = max(now, 있는것["ends_at"] if 있는것 else now) + days * 86400
    with auth.db() as con:
        con.execute("INSERT INTO ai_addons (user_id, kind, starts_at, ends_at, memo) VALUES (?,?,?,?,?)",
                    (user_id, kind, 시작, 끝, memo))
    return {"종류": kind, "부터": 시작, "까지": 끝}


def active_addon(user_id: int, kind: str, now: float | None = None) -> dict | None:
    """지금 살아 있는 부가 이용권. 여럿이면 가장 늦게 끝나는 것."""
    now = int(now if now is not None else time.time())
    with auth.db() as con:
        r = con.execute("SELECT id, kind, starts_at, ends_at FROM ai_addons WHERE user_id=? AND kind=? AND ends_at>?"
                        " ORDER BY ends_at DESC LIMIT 1", (user_id, kind, now)).fetchone()
    return dict(r) if r else None


def ai_cost_summary(days: int = 30, now: float | None = None) -> dict:
    """최근 며칠의 호출 수 · 토큰 합 · 받은 값 — 관리자가 원가를 볼 때. 개인 정보는 없다."""
    since = int(now if now is not None else time.time()) - days * 86400
    with auth.db() as con:
        rows = con.execute(
            "SELECT kind, COUNT(*) AS n, COALESCE(SUM(paid),0) AS paid, COALESCE(SUM(input_tok),0) AS i,"
            " COALESCE(SUM(output_tok),0) AS o, COALESCE(SUM(cache_tok),0) AS c FROM ai_usage"
            " WHERE created_at>=? GROUP BY kind", (since,)).fetchall()
    return {r["kind"]: {"호출": int(r["n"]), "받은값": int(r["paid"]), "입력토큰": int(r["i"]),
                        "출력토큰": int(r["o"]), "캐시토큰": int(r["c"])} for r in rows}


# ---------------- 주문 ----------------

def new_order(order_id: str, user_id: int | None, tid: str,
              credit: int, amount: int, product: str | None = None) -> None:
    now = int(time.time())
    with auth.db() as con:
        con.execute(
            "INSERT INTO pay_orders (order_id, user_id, tid, credit, amount, status,"
            " created_at, updated_at, product) VALUES (?,?,?,?,?,?,?,?,?)",
            (order_id, user_id, tid, int(credit), int(amount), "ready", now, now, product))


def subscribe(user_id: int, paid: int, order_id: str, days: int) -> dict:
    """구독 결제 승인분 — 원장에 '구독' 줄(이용권 증감 0, 낸 돈만)을 남기고 구독을 연다. 같은 주문은 한 번만."""
    with auth.db() as con:
        있음 = con.execute("SELECT 1 FROM credit_ledger WHERE order_id=?", (order_id,)).fetchone()
        if 있음:
            return active_addon(user_id, "구독") or {}
        _add(con, user_id, 0, "sub", paid=paid, order_id=order_id, memo=f"한 달 구독 {days}일")
    return add_addon(user_id, "구독", days, memo=order_id)


def get_order(order_id: str) -> dict | None:
    with auth.db() as con:
        r = con.execute("SELECT * FROM pay_orders WHERE order_id=?", (order_id,)).fetchone()
    return dict(r) if r else None


def set_status(order_id: str, status: str, aid: str | None = None) -> None:
    with auth.db() as con:
        con.execute("UPDATE pay_orders SET status=?, aid=COALESCE(?, aid), updated_at=?"
                    " WHERE order_id=?", (status, aid, int(time.time()), order_id))
