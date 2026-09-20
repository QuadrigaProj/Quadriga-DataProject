"""Postgres 로 테스트할 때의 출발선 (CI 의 pytest-postgres 작업, 또는 DATABASE_URL 을 주고 돌릴 때).

SQLite 에서는 테스트마다 새 파일을 만들어서 늘 빈 DB 로 시작하고 첫 사용자의 id 가 1 이다.
Postgres 는 DB 하나를 모든 테스트가 같이 쓴다. 표마다 DELETE 만 하면 번호(id)가 이어져서
"첫 사용자는 1번" 이라고 적은 테스트(billing.charge(1, …))가 외래 키 오류로 깨지고, 빠뜨린 표에는 앞 테스트의 줄이 남는다.
그래서 모든 표를 한꺼번에 비우고 번호도 1 부터 다시 센다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import auth, billing, community  # noqa: E402


def reset_postgres() -> None:
    """표를 만들고(없으면), 전부 비우고, 번호를 1 부터 다시 센다. Postgres 일 때만 부른다."""
    assert auth.is_postgres(), "SQLite 에서는 테스트마다 새 파일을 쓴다 — 이 함수를 부를 일이 없다"
    auth.init_db()
    community.init_db()
    billing.init_db()
    with auth.db() as con:
        rows = con.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'").fetchall()
        names = ", ".join('"' + r["tablename"] + '"' for r in rows)
        if names:
            con.execute(f"TRUNCATE {names} RESTART IDENTITY CASCADE")
