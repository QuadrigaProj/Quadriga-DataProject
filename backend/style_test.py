"""운동 스타일 테스트 — 문항 제공과 채점.

좋아하는 운동의 종류나 운동에 투자하고 싶은 시간이 아직 뚜렷하지 않을 때 쓰는 짧은 테스트(F1).
data/sample/style_test.json 이 문항(선택지별 축 점수)과 결과 유형(축 가중치)을 갖고 있고,
이 모듈은 그 데이터를 읽어 채점만 한다. 추천 로직을 코드에 두지 않는다.

채점: 선택지 점수를 축별로 합산 → 문항별 최대값의 합으로 0~1 정규화
      → 유형별 가중합(가중치 × 정규화 점수)이 가장 큰 유형. 동점이면 파일에 먼저 적힌 유형.

성향 코드: 유형 이름과 함께 MBTI 처럼 네 글자(예: HSOL = 고강도 · 혼자 · 야외 · 길게)를 준다.
      어느 축을 어느 기준으로 자르는지는 style_test.json 의 "코드" 에 있다 (type_code).
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
    "벌크업": "bulk",
    "근육량 늘리기": "muscle",
    "지구력 늘리기": "endurance",
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


def type_code(norm: dict[str, float]) -> dict:
    """축별 0~1 점수 → 네 글자 성향 코드.

    축마다 값이 기준 이상이면 앞 글자, 아니면 뒤 글자다. 반대축이 있으면(길게 ↔ 짧게) 두 축의 차이를 0~1 로 옮겨 견준다.
    "비율" 은 앞 글자 쪽 백분율이고, 기준이 꼭 50% 가 되게 편 값이다 — 글자와 막대가 어긋나 보이지 않게
    (기준이 0.4 인 축에서 0.4 는 50%, 1.0 은 100%).
    """
    axes, letters = [], ""
    for c in load().get("코드", []):
        v = float(norm.get(c["축"], 0.0))
        if c.get("반대축"):
            v = (v - float(norm.get(c["반대축"], 0.0)) + 1) / 2
        th = float(c.get("기준", 0.5))
        pct = 50 * v / th if v < th else 50 + 50 * (v - th) / (1 - th)
        first = v >= th - 1e-9
        pick = 0 if first else 1
        letters += c["글자"][pick]
        axes.append({
            "id": c["id"], "글자": c["글자"][pick], "이름": c["이름"][pick], "말": c["말"][pick],
            "양쪽": [{"글자": g, "이름": n} for g, n in zip(c["글자"], c["이름"])],
            "비율": int(round(pct)),                  # 앞 글자 쪽 (뒤 글자 쪽은 100 − 비율)
        })
    return {"글자": letters, "축": axes}


def score(answers) -> dict:
    """답 목록 → {"유형": {...가중치 제외, 목적키 추가}, "점수": 축별 0~1, "코드": 네 글자 성향 코드, "답변": [...]}.

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
    return {"유형": out, "점수": norm, "코드": type_code(norm), "답변": ans}
