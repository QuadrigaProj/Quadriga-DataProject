"""운동 스타일 테스트 — 문항 제공과 채점.

좋아하는 운동의 종류나 운동에 투자하고 싶은 시간이 아직 뚜렷하지 않을 때 쓰는 짧은 테스트(F1).
data/sample/style_test.json 이 문항(선택지별 축 점수)과 결과 유형(축 가중치)을 갖고 있고,
이 모듈은 그 데이터를 읽어 채점만 한다. 추천 로직을 코드에 두지 않는다.

채점: 선택지 점수를 축별로 합산 → 문항별 최대값의 합으로 0~1 정규화
      → 유형별 가중합(가중치 × 정규화 점수)이 가장 큰 유형. 동점이면 파일에 먼저 적힌 유형.
"""
from __future__ import annotations

import json

try:
    from backend.paths import find_data
except ImportError:
    from paths import find_data

# 추천목적(routines.PURPOSES 표기) → 화면 s2 목적 카드의 data-p 키
PURPOSE_KEY = {
    "다이어트": "diet",
    "기초 체력 증진": "basic",
    "재활 및 기능 회복": "fall",
    "수험생 체력 증진": "study",
    "유연성 강화": "flex",
}

_data: dict | None = None


def load() -> dict:
    """테스트 데이터를 한 번만 읽어 캐시한다."""
    global _data
    if _data is None:
        _data = json.loads(find_data("style_test.json").read_text(encoding="utf-8"))
    return _data


def questions() -> list[dict]:
    """화면이 그대로 그릴 문항 — 점수는 빼고 글만 준다."""
    return [{"id": q["id"], "질문": q["질문"], "선택지": [c["글"] for c in q["선택지"]]}
            for q in load()["문항"]]


def result_types() -> list[dict]:
    """결과 유형 목록 — 가중치는 빼고 준다."""
    return [{k: v for k, v in t.items() if k != "가중치"} for t in load()["유형"]]


def axis_max() -> dict[str, float]:
    """축별로 얻을 수 있는 최대 점수(문항마다 그 축의 최대 선택지 점수를 더한 값). 정규화 분모."""
    mx: dict[str, float] = {}
    for q in load()["문항"]:
        best: dict[str, float] = {}
        for c in q["선택지"]:
            for a, v in c.get("점수", {}).items():
                best[a] = max(best.get(a, 0.0), float(v))
        for a, v in best.items():
            mx[a] = mx.get(a, 0.0) + v
    return mx


def validate(answers) -> list[int]:
    """답 목록을 검사한다. 개수·범위·타입이 어긋나면 ValueError(→ API 400)."""
    qs = load()["문항"]
    if not isinstance(answers, list):
        raise ValueError("answers 는 선택지 번호 목록이어야 해요")
    if len(answers) != len(qs):
        raise ValueError(f"문항은 {len(qs)}개인데 답이 {len(answers)}개예요")
    out = []
    for i, (a, q) in enumerate(zip(answers, qs)):
        if isinstance(a, bool) or not isinstance(a, int):
            raise ValueError(f"{i + 1}번 답이 선택지 번호가 아니에요")
        n = len(q["선택지"])
        if not 0 <= a < n:
            raise ValueError(f"{i + 1}번 답 {a} 은(는) 선택지 범위(0~{n - 1}) 밖이에요")
        out.append(a)
    return out


def axis_scores(answers: list[int]) -> dict[str, float]:
    """검사를 통과한 답 → 축별 0~1 점수."""
    mx = axis_max()
    raw = {a: 0.0 for a in mx}
    for a, q in zip(answers, load()["문항"]):
        for axis, v in q["선택지"][a].get("점수", {}).items():
            raw[axis] += float(v)
    return {a: round(raw[a] / mx[a], 3) if mx[a] else 0.0 for a in mx}


def score(answers) -> dict:
    """답 목록 → {"유형": {...가중치 제외, 목적키 추가}, "점수": 축별 0~1, "답변": [...]}.

    같은 답이면 항상 같은 결과(결정적). 잘못된 답은 ValueError.
    """
    ans = validate(answers)
    norm = axis_scores(ans)
    best, best_val = None, 0.0
    for t in load()["유형"]:
        val = sum(float(w) * norm.get(a, 0.0) for a, w in t["가중치"].items())
        if best is None or val > best_val + 1e-9:
            best, best_val = t, val
    out = {k: v for k, v in best.items() if k != "가중치"}
    out["목적키"] = PURPOSE_KEY.get(out.get("추천목적"))
    return {"유형": out, "점수": norm, "답변": ans}
