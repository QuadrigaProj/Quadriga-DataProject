"""SQLite 에서는 통과하고 Postgres(배포)에서만 터지는 SQL 을 미리 잡는다.

로컬 테스트는 SQLite 로 돈다. 그래서 Postgres 만 엄격하게 보는 문법은
테스트를 다 통과하고 배포에서 처음 터진다. 실제로 그런 일이 있었다.

  WHERE r.room_type <> 'direct' OR (SELECT 1 FROM chat_members ...)
  → SQLite: 1 을 참으로 받는다
  → Postgres: argument of OR must be type boolean, not type integer

여기서는 그 종류만 본다. SQL 전체를 검사하려는 게 아니다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
대상 = ["community.py", "billing.py", "auth.py", "main.py"]


def _sql_텍스트(path: Path) -> str:
    """이어 붙인 문자열 조각을 한 줄로 만든다. "..." "..." → "......" """
    t = path.read_text(encoding="utf-8")
    t = re.sub(r'"\s*(?:#[^\n]*)?\s*\n\s*"', "", t)      # 조각 잇기(중간 주석 포함)
    return t


@pytest.mark.parametrize("이름", 대상)
def test_boolean_자리에_스칼라_서브쿼리를_쓰지_않는다(이름):
    """WHERE/AND/OR 바로 뒤의 (SELECT ...) 는 Postgres 에서 타입 오류다.

    EXISTS 로 감싸거나 비교 연산자(=, >, IS NULL …)로 boolean 을 만들어야 한다.
    """
    sql = _sql_텍스트(ROOT / "backend" / 이름)
    나쁜것 = []
    for m in re.finditer(r"\b(WHERE|AND|OR)\s+\(SELECT\b", sql):
        꼬리 = sql[m.end():m.end() + 400]
        # 괄호를 닫은 뒤 비교 연산자가 오면 boolean 이 된다
        깊이, 끝 = 1, None
        for i, c in enumerate(꼬리):
            if c == "(":
                깊이 += 1
            elif c == ")":
                깊이 -= 1
                if 깊이 == 0:
                    끝 = i + 1
                    break
        뒤 = 꼬리[끝:끝 + 24].lstrip(' "') if 끝 is not None else ""
        if re.match(r"(=|<>|!=|<|>|IS\b|NOT\b|IN\b|BETWEEN\b)", 뒤, re.I):
            continue                                      # 비교라서 boolean 이다
        나쁜것.append(sql[max(0, m.start() - 70):m.end() + 90].strip())

    assert not 나쁜것, (
        "Postgres 에서 'argument of OR must be type boolean' 으로 죽는다. "
        "EXISTS 로 감싸세요:\n" + "\n\n".join(나쁜것))


@pytest.mark.parametrize("이름", 대상)
def test_불린_컬럼에_정수를_비교하지_않는다(이름):
    """Postgres 는 boolean 컬럼과 0/1 을 직접 비교하지 못한다.

    스키마가 INTEGER 라 지금은 문제가 없지만, BOOLEAN 으로 바꾸는 순간
    조용히 깨진다. 새로 쓸 때 걸리게 해 둔다.
    """
    sql = _sql_텍스트(ROOT / "backend" / 이름)
    assert not re.search(r"\bis_private\s*=\s*(TRUE|FALSE)\b", sql, re.I)
