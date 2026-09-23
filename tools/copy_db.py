"""Postgres → Postgres 로 표 내용을 복사한다 (Render 무료 DB → Neon 옮길 때).

    SRC_DATABASE_URL=postgresql://...render.com/...  DST_DATABASE_URL=postgresql://...neon.tech/...?sslmode=require \\
        python tools/copy_db.py            # 미리 보기(옮길 표와 줄 수만)
        python tools/copy_db.py --go       # 실제로 복사

받는 쪽(DST)의 표는 서버가 먼저 떠서 만들어 둔 상태여야 한다(DATABASE_URL 을 Neon 으로 바꿔 한 번 배포하면 된다).
겹치는 줄(같은 id · 같은 계정)은 건너뛴다(ON CONFLICT DO NOTHING) — 여러 번 돌려도 된다. 원본(SRC)은 읽기만 한다.
외래키 순서(users → 세션 · 이용권 · 커뮤니티 …)는 참조 관계를 읽어 스스로 정한다. 복사한 뒤 id 시퀀스를 최댓값으로 맞춘다.
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


def tables_in_fk_order(con) -> list[str]:
    """public 스키마의 표를 참조되는 쪽이 먼저 오게 정렬한다."""
    with con.cursor() as cur:
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'")
        tables = [r["table_name"] for r in cur.fetchall()]
        cur.execute("""
            SELECT tc.table_name AS child, ccu.table_name AS parent
            FROM information_schema.table_constraints tc
            JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'""")
        deps = defaultdict(set)
        for r in cur.fetchall():
            if r["child"] != r["parent"]:
                deps[r["child"]].add(r["parent"])
    order, seen = [], set()

    def visit(t, trail=()):
        if t in seen:
            return
        if t in trail:                       # 순환 참조면 그냥 넣는다 (ON CONFLICT 로 두 번 돌리면 된다)
            return
        for p in sorted(deps.get(t, ())):
            visit(p, trail + (t,))
        seen.add(t)
        order.append(t)

    for t in sorted(tables):
        visit(t)
    return order


def columns(con, table: str) -> list[str]:
    with con.cursor() as cur:
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s"
                    " ORDER BY ordinal_position", (table,))
        return [r["column_name"] for r in cur.fetchall()]


def main() -> None:
    src_url, dst_url = os.environ.get("SRC_DATABASE_URL"), os.environ.get("DST_DATABASE_URL")
    if not src_url or not dst_url:
        sys.exit("SRC_DATABASE_URL 과 DST_DATABASE_URL 을 환경변수로 주세요")
    go = "--go" in sys.argv
    with psycopg.connect(src_url, row_factory=dict_row) as src, psycopg.connect(dst_url, row_factory=dict_row) as dst:
        order = tables_in_fk_order(src)
        dst_tables = set(tables_in_fk_order(dst))
        print("순서:", " → ".join(order))
        for t in order:
            if t not in dst_tables:
                print(f"- {t}: 받는 쪽에 표가 없어 건너뜀 (서버를 먼저 띄워 표를 만드세요)")
                continue
            cols = [c for c in columns(src, t) if c in set(columns(dst, t))]
            with src.cursor() as cur:
                cur.execute(sql.SQL("SELECT {} FROM {}").format(sql.SQL(", ").join(map(sql.Identifier, cols)), sql.Identifier(t)))
                rows = cur.fetchall()
            if not go:
                print(f"- {t}: {len(rows)}줄 ({len(cols)}칸)")
                continue
            copied = 0
            with dst.cursor() as cur:
                stmt = sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING").format(
                    sql.Identifier(t), sql.SQL(", ").join(map(sql.Identifier, cols)),
                    sql.SQL(", ").join(sql.Placeholder() * len(cols)))
                for r in rows:
                    cur.execute(stmt, [r[c] for c in cols])
                    copied += cur.rowcount
                if "id" in cols and rows:
                    cur.execute(sql.SQL("SELECT setval(pg_get_serial_sequence(%s, 'id'), GREATEST(COALESCE(MAX(id), 1), 1)) FROM {}")
                                .format(sql.Identifier(t)), (t,))
            dst.commit()
            print(f"- {t}: {copied}/{len(rows)}줄 복사 (나머지는 이미 있어 건너뜀)")
        if not go:
            print("\n실제로 복사하려면 --go 를 붙이세요.")


if __name__ == "__main__":
    main()
