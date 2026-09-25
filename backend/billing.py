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
import json
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

CREATE TABLE IF NOT EXISTS ai_jobs (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind        TEXT NOT NULL,            -- 루틴 | 조정
  status      TEXT NOT NULL,            -- running | done | failed
  result      TEXT,                     -- 끝났을 때 화면에 줄 응답 전체(JSON)
  error       TEXT,
  seen        INTEGER NOT NULL DEFAULT 0,   -- 화면이 결과를 가져갔는가 (새로고침해도 한 번은 보여 주려고)
  created_at  INTEGER NOT NULL,
  finished_at INTEGER,
  taken_sec   REAL                      -- 실제로 걸린 시간 — 다음 사람에게 '보통 이만큼' 이라고 말해 주려고
);
CREATE INDEX IF NOT EXISTS idx_ai_jobs_user ON ai_jobs(user_id, id DESC);
"""
SCHEMA_PG = (SCHEMA_SQLITE
             .replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY"))


def init_db() -> None:
    schema = SCHEMA_PG if auth.is_postgres() else SCHEMA_SQLITE
    with auth.db() as con:
        for stmt in filter(str.strip, schema.split(";")):
            con.execute(stmt)
    # 예전에 만든 표에는 product 칸이 없다 — 없을 때만 붙인다 (Postgres 는 실패한 문장이 트랜잭션을 통째로 깨서 try 로 못 가린다)
    with auth.db() as con:
        if auth.is_postgres():
            con.execute("ALTER TABLE pay_orders ADD COLUMN IF NOT EXISTS product TEXT")
        else:
            있는것 = {row["name"] for row in con.execute("PRAGMA table_info(pay_orders)").fetchall()}
            if "product" not in 있는것:
                con.execute("ALTER TABLE pay_orders ADD COLUMN product TEXT")


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

    종류 = {"charge": "충전", "use": "사용", "refund": "환불", "sub": "구독", "demo_reset": "시연 정리"}
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
    """차감. 잔액이 모자라면 402 로 막고 한 푼도 쓰지 않는다.

    "잔액 확인 → 차감" 두 문장이면 같은 순간 온 두 요청이 둘 다 통과한다. 차감 줄을 넣는 INSERT 안에서 잔액을 다시 재서
    (INSERT … SELECT … WHERE 잔액 >= 값) 한 문장으로 한다 — 두 번째 요청은 줄이 안 들어가 402 가 된다.
    """
    if amount <= 0:
        raise HTTPException(400, "차감 금액을 확인해 주세요.")
    with auth.db() as con:
        들어감 = con.execute(
            "INSERT INTO credit_ledger (user_id, amount, kind, paid, order_id, memo, created_at)"
            " SELECT ?, ?, 'use', NULL, NULL, ?, ?"
            " WHERE (SELECT COALESCE(SUM(amount), 0) FROM credit_ledger WHERE user_id=?) >= ?",
            (user_id, -int(amount), memo, int(time.time()), user_id, int(amount))).rowcount
        if 들어감 != 1:
            raise HTTPException(402, "이용권이 모자라요. 먼저 충전해 주세요.")
        r = con.execute("SELECT COALESCE(SUM(amount), 0) AS s FROM credit_ledger WHERE user_id=?",
                        (user_id,)).fetchone()
        return int(r["s"] or 0)


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


def unused_orders(user_id: int) -> list[dict]:
    """안 쓴 충전 결제 — 환불할 수 있는 것. 구독은 여기 들지 않는다(환불 규정이 따로다)."""
    with auth.db() as con:
        rows = con.execute("SELECT * FROM pay_orders WHERE user_id=? AND status='paid' ORDER BY created_at",
                           (user_id,)).fetchall()
    return [dict(o) for o in rows if not o["product"] and not used_after(user_id, o["order_id"])]


def delete_preview(user_id: int) -> dict:
    """계정을 지우면 돈이 어떻게 되는지 — 화면이 확인 문구를 만드는 재료.

    환불: 안 쓴 충전(전액 자동 환불). 소멸: 쓴 충전의 남은 잔액(환불 규정상 돌려주지 않는다) + 살아 있는 구독.
    """
    환불 = unused_orders(user_id)
    환불이용권 = sum(int(o["credit"]) for o in 환불)
    잔액 = balance(user_id)
    return {"환불건수": len(환불), "환불금액": sum(int(o["amount"]) for o in 환불),
            "소멸잔액": max(0, 잔액 - 환불이용권),
            "구독": active_addon(user_id, "구독")}


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
        _forget_old_ips(con, now)


def _forget_old_ips(con, now: float | None = None) -> None:
    """지난 날의 접속 주소(IP)를 지운다 — IP 는 그날의 하루 한도(main.DEMO_IP_LIMIT)를 세는 데만 쓴다(개인정보처리방침 3)."""
    con.execute("UPDATE ai_usage SET ip=NULL WHERE ip IS NOT NULL AND day<?", (kst_today(now),))


def forget_ai_usage(user_id: int, now: float | None = None) -> int:
    """계정을 지울 때 — AI 이용 기록에서 회원번호를 지워 누구의 것인지 알 수 없게 한다. 지운 줄 수를 돌려준다.

    ai_usage 는 원가 통계(ai_cost_summary)로 남기려고 users 에 CASCADE 로 묶지 않았다. 그래서 계정을 지워도
    회원번호와 IP 가 그대로 남았다(2026-09-25 점검). 종류 · 토큰 수 · 시각만 남기고, 오늘 줄의 IP 는 그날 한도를
    계속 세도록 두었다가 다음 날 _forget_old_ips 가 지운다 — 계정을 지웠다 다시 만들어 그날 한도를 넘지 못하게.
    """
    with auth.db() as con:
        _forget_old_ips(con, now)
        return con.execute("UPDATE ai_usage SET user_id=NULL WHERE user_id=?", (user_id,)).rowcount


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


# ---------------------------------------------------------------------------
# AI 작업 — 루틴 짓기는 요청과 떼어 백그라운드에서 끝까지 돌리고, 결과를 여기 둔다.
# 사용자가 '받겠다' 고 한 뒤에는 화면을 옮기거나 새로고침해도 결과가 남는다 (예현 2026-09-23).
# ---------------------------------------------------------------------------

JOB_STALE_SEC = 15 * 60          # 이보다 오래 running 이면 서버가 도중에 죽은 것 — failed 로 본다
JOB_KEEP_SEC = 24 * 3600         # 하루 지난 작업은 화면에 알리지 않는다
JOB_DEFAULT_SEC = 60.0           # 걸린 기록이 아직 없을 때의 예상(초)


def job_start(user_id: int, kind: str, now: float | None = None) -> int:
    with auth.db() as con:
        return con.insert_id("INSERT INTO ai_jobs (user_id, kind, status, created_at) VALUES (?,?,?,?)",
                             (user_id, kind, "running", int(now if now is not None else time.time())))


def job_finish(job_id: int, result: dict | None, error: str | None = None, now: float | None = None) -> None:
    """끝났다 — result 가 있으면 done, 없으면 failed. taken_sec 은 시작부터의 시간."""
    끝 = now if now is not None else time.time()
    with auth.db() as con:
        r = con.execute("SELECT created_at FROM ai_jobs WHERE id=?", (job_id,)).fetchone()
        걸림 = max(0.0, 끝 - int(r["created_at"])) if r else None
        con.execute("UPDATE ai_jobs SET status=?, result=?, error=?, finished_at=?, taken_sec=? WHERE id=?",
                    ("done" if result is not None else "failed",
                     json.dumps(result, ensure_ascii=False) if result is not None else None,
                     (error or "")[:300] if error else None, int(끝), 걸림, job_id))


def _job_row(r, now: float) -> dict:
    d = dict(r)
    d["result"] = json.loads(d["result"]) if d.get("result") else None
    if d["status"] == "running" and now - int(d["created_at"]) > JOB_STALE_SEC:
        d["status"] = "failed"                     # 서버가 도중에 다시 떴다 — 값은 받지 않았으니 다시 받으면 된다
        d["error"] = "서버가 도중에 다시 시작돼 짓던 것이 사라졌어요. 다시 받아 주세요 (값은 받지 않았어요)."
    d["지난초"] = round(now - int(d["created_at"]), 1)
    return d


def job_get(job_id: int, user_id: int, mark_seen: bool = False, now: float | None = None) -> dict | None:
    """내 작업 하나. mark_seen 이면 끝난 결과를 화면이 가져갔다고 표시한다."""
    now = now if now is not None else time.time()
    with auth.db() as con:
        r = con.execute("SELECT * FROM ai_jobs WHERE id=? AND user_id=?", (job_id, user_id)).fetchone()
        if not r:
            return None
        d = _job_row(r, now)
        if d["status"] == "failed" and r["status"] == "running":
            con.execute("UPDATE ai_jobs SET status='failed', error=?, finished_at=? WHERE id=?", (d["error"], int(now), job_id))
        if mark_seen and d["status"] != "running" and not r["seen"]:
            con.execute("UPDATE ai_jobs SET seen=1 WHERE id=?", (job_id,))
    return d


def job_pending(user_id: int, now: float | None = None) -> dict | None:
    """화면이 알아야 할 내 최근 작업 — 아직 짓는 중이거나, 끝났는데 아직 안 가져간 것(하루 안). 없으면 None."""
    now = now if now is not None else time.time()
    with auth.db() as con:
        r = con.execute("SELECT * FROM ai_jobs WHERE user_id=? AND created_at>=? ORDER BY id DESC LIMIT 1",
                        (user_id, int(now - JOB_KEEP_SEC))).fetchone()
    if not r:
        return None
    d = _job_row(r, now)
    if d["status"] == "running" or (d["status"] == "done" and not r["seen"]):
        return {"id": d["id"], "종류": d["kind"], "상태": d["status"], "시작": int(d["created_at"]), "지난초": d["지난초"]}
    return None


def job_running(user_id: int, now: float | None = None) -> bool:
    p = job_pending(user_id, now)
    return bool(p and p["상태"] == "running")


def job_typical_sec(kind: str | None = None, default: float = JOB_DEFAULT_SEC) -> float:
    """최근에 실제로 걸린 시간(끝난 작업 열 개)의 가운데값 — 화면의 '보통 이만큼 걸려요'. 기록이 없으면 default."""
    with auth.db() as con:
        if kind:
            rows = con.execute("SELECT taken_sec FROM ai_jobs WHERE status='done' AND kind=? AND taken_sec IS NOT NULL"
                               " ORDER BY id DESC LIMIT 10", (kind,)).fetchall()
        else:
            rows = con.execute("SELECT taken_sec FROM ai_jobs WHERE status='done' AND taken_sec IS NOT NULL"
                               " ORDER BY id DESC LIMIT 10").fetchall()
    값들 = sorted(float(r["taken_sec"]) for r in rows if r["taken_sec"] is not None and float(r["taken_sec"]) > 0)
    if not 값들:
        return float(default)
    return round(값들[len(값들) // 2], 1)


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


# ---------------- 시연 이용권 정리 ----------------

def reset_demo_credits(now: float | None = None) -> dict:
    """실결제로 바꿀 때 한 번 — 시연 기간(테스트 가맹점)의 결제로 얻은 이용권 · 구독을 모두 지운다.

    원장은 지우지 않고 잔액만큼 음수 줄('demo_reset')을 넣어 0 으로 만든다(내역은 남는다). 살아 있는 구독은 지금 끝낸다.
    'paid' 주문은 'demo' 로 바꿔 환불 대상에서 뺀다 — 돈이 실제로 오가지 않은 결제다(약관 6조의2 '시연 기간').
    돌려주는 값은 몇 사람 · 얼마를 지웠는지.
    """
    now = int(now if now is not None else time.time())
    with auth.db() as con:
        rows = con.execute("SELECT user_id, COALESCE(SUM(amount), 0) AS s FROM credit_ledger GROUP BY user_id").fetchall()
        지운사람, 지운금액 = 0, 0
        for r in rows:
            잔액 = int(r["s"] or 0)
            if 잔액 > 0:
                _add(con, r["user_id"], -잔액, "demo_reset", memo="시연 이용권 정리 (실결제 전환)")
                지운사람 += 1
                지운금액 += 잔액
        구독 = con.execute("UPDATE ai_addons SET ends_at=? WHERE kind='구독' AND ends_at>?", (now, now)).rowcount
        상세 = con.execute("UPDATE ai_addons SET ends_at=? WHERE kind='상세' AND ends_at>?", (now, now)).rowcount
        주문 = con.execute("UPDATE pay_orders SET status='demo', updated_at=? WHERE status='paid'", (now,)).rowcount
    return {"지운사람": 지운사람, "지운이용권": 지운금액, "끝낸구독": int(구독), "끝낸자세히": int(상세), "시연주문": int(주문)}


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


def set_status(order_id: str, status: str, aid: str | None = None,
               only_from: str | None = None) -> bool:
    """주문 상태를 바꾼다. only_from 을 주면 지금 상태가 그것일 때만 — 같은 순간 온 두 환불 요청 가운데 첫 것만 통과한다.
    돌려주는 값은 실제로 바뀌었는지."""
    with auth.db() as con:
        if only_from:
            바뀜 = con.execute("UPDATE pay_orders SET status=?, aid=COALESCE(?, aid), updated_at=?"
                             " WHERE order_id=? AND status=?", (status, aid, int(time.time()), order_id, only_from)).rowcount
        else:
            바뀜 = con.execute("UPDATE pay_orders SET status=?, aid=COALESCE(?, aid), updated_at=?"
                             " WHERE order_id=?", (status, aid, int(time.time()), order_id)).rowcount
    return 바뀜 == 1
