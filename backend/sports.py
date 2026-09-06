"""배우고 싶은 운동 종목 — 목록과 체력요인 매핑.

이 모듈은 추천을 하지 않는다. data/sample/sports.json 을 읽어 그대로 내보내고,
선택한 종목들이 어떤 체력요인을 요구하는지 세어 줄 뿐이다.
루틴을 고르는 쪽(backend/routines.py)이 그 숫자를 참고한다.
"""
from __future__ import annotations

import json
from collections import Counter

try:
    from backend.paths import find_data
except ImportError:
    from paths import find_data

_data: dict | None = None


def load() -> dict:
    global _data
    if _data is None:
        _data = json.loads(find_data("sports.json").read_text(encoding="utf-8"))
    return _data


def catalog() -> dict:
    """화면이 그대로 그릴 수 있는 형태 — 분류 순서와 종목 목록."""
    d = load()
    return {"분류": d["groups"], "종목": d["sports"]}


def by_id() -> dict[str, dict]:
    return {s["id"]: s for s in load()["sports"]}


def resolve(ids: list[str]) -> list[dict]:
    """모르는 id 는 조용히 버린다. 저장된 선택이 낡아도 화면이 깨지지 않게."""
    table = by_id()
    return [table[i] for i in ids if i in table]


def factor_weights(ids: list[str]) -> dict[str, int]:
    """선택한 종목들이 요구하는 체력요인을 센다.

    같은 요인을 여러 종목이 요구하면 그만큼 커진다.
    (러닝 + 마라톤 → 심폐지구력 2)
    """
    c: Counter[str] = Counter()
    for s in resolve(ids):
        c.update(s.get("체력요인", []))
    return dict(c.most_common())


def care_parts(ids: list[str]) -> list[str]:
    """선택한 종목들이 자주 무리를 주는 부위. 루틴에서 조심할 곳."""
    c: Counter[str] = Counter()
    for s in resolve(ids):
        c.update(s.get("부담부위", []))
    return [p for p, _ in c.most_common()]
