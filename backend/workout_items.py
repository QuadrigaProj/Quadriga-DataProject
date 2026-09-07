"""당일 기록 작성 화면이 쓰는 운동 종목 목록.

이 모듈은 판단을 하지 않는다. data/sample/workout_items.json 을 읽어 그대로 내보낸다.
종목·단위가 바뀌면 JSON 만 고치면 되고, 화면은 받은 대로 그린다.
"""
from __future__ import annotations

import json

try:                                     # 저장소 루트에서 실행할 때
    from backend.paths import find_data
except ImportError:                      # backend/ 안에서 직접 실행할 때
    from paths import find_data

_data: dict | None = None


def load() -> dict:
    """종목 데이터를 한 번만 읽어 캐시한다."""
    global _data
    if _data is None:
        _data = json.loads(find_data("workout_items.json").read_text(encoding="utf-8"))
    return _data


def catalog() -> dict:
    """화면이 그대로 그릴 수 있는 형태 — 분류 순서, 종목, 단위 표기, 요인 목록.

    요인(유연성·근력·심폐지구력·근지구력)은 종목 앞에 붙는 아이콘을 고르는 데 쓴다.
    """
    d = load()
    return {"분류": d["분류"], "종목": d["종목"], "단위": d["단위"],
            "요인": d.get("요인", [])}


def by_id() -> dict[str, dict]:
    return {s["id"]: s for s in load()["종목"]}
