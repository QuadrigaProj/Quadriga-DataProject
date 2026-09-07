"""루틴 추천 — 사용자 데이터로 후보에 점수를 매겨 순위를 낸다.

추천을 지어내지 않는다. 이미 있는 250개 고정 루틴(data/sample/routines_250.json)
안에서 고르고, 왜 골랐는지를 근거 문장으로 함께 돌려준다.
근거를 댈 수 없는 추천은 하지 않는다는 것이 이 모듈의 규칙이다.

점수는 네 가지를 본다.
  1. 약점      체력나이 항목별에서 뒤처지는 요인을 그 목적이 다루는가
  2. 스타일    운동 스타일 테스트가 고른 목적과 같은가
  3. 고른 종목 배우고 싶다고 고른 종목이 요구하는 요인이 들어 있는가
  4. 목표      목표 체력나이까지 남은 격차가 클수록 심폐·근지구력 쪽에 무게를 준다
"""
from __future__ import annotations

from collections import Counter

try:                                     # 저장소 루트에서 실행할 때
    from backend import routines as rt, sports as sp
except ImportError:                      # backend/ 안에서 직접 실행할 때
    import routines as rt                # noqa: E402
    import sports as sp                  # noqa: E402

# 격차가 클 때 무게를 더 주는 요인 — 체력나이를 가장 빨리 끌어내리는 축
GAP_FACTORS = ("심폐지구력", "근지구력")
GAP_THRESHOLD = 5.0                      # 목표까지 이만큼 넘게 남으면 가산


def _factor_hit(a: str, b: str) -> bool:
    """'근력·근지구력(하체)' 처럼 묶여 있어 부분 일치로 본다."""
    return a in b or b in a


def routine_factors(age_gbn: str, routine: dict) -> Counter:
    """루틴 한 벌이 어떤 체력요인을 몇 번 다루는지."""
    pools = rt.load()["pools"].get(age_gbn, {})
    c: Counter = Counter()
    for phase in ("준비운동", "본운동", "정리운동"):
        codes = routine.get({"준비운동": "prep", "본운동": "main", "정리운동": "cool"}[phase], [])
        for code in codes:
            info = pools.get(phase, {}).get(code)
            if info:
                c.update(info.get("체력요인", []))
    return c


def score(age_gbn: str, *, weak=None, style_purpose=None, sport_factors=None,
          target_gap=None, limit: int = 5) -> list[dict]:
    """목적 × 루틴 후보에 점수를 매겨 높은 순으로 돌려준다."""
    d = rt.load()
    purpose_factors = d["config"]["purpose_factors"]
    reframe = d["config"]["reframe"].get(age_gbn, {})
    weak = [w for w in (weak or []) if w]
    sport_factors = [f for f in (sport_factors or []) if f]

    out = []
    for purpose in rt.PURPOSES:
        묶음 = d["routines"].get(age_gbn, {}).get(purpose) or []
        우선 = purpose_factors.get(purpose, [])
        점수 = 0.0
        이유 = []

        맞은약점 = [w for w in weak if any(_factor_hit(w, f) for f in 우선)]
        if 맞은약점:
            점수 += 3.0 * len(맞은약점)
            이유.append(f"뒤처지는 {' · '.join(맞은약점)}을(를) 바로 다루는 프로그램이에요")

        if style_purpose and style_purpose == purpose:
            점수 += 2.0
            이유.append("운동 스타일 테스트가 고른 목적과 같아요")

        맞은종목 = sorted({f for f in sport_factors if any(_factor_hit(f, u) for u in 우선)})
        if 맞은종목:
            점수 += 1.5 * len(맞은종목)
            이유.append(f"고른 종목이 많이 쓰는 {' · '.join(맞은종목)}이(가) 들어 있어요")

        if target_gap is not None and target_gap >= GAP_THRESHOLD:
            if any(any(_factor_hit(g, f) for f in 우선) for g in GAP_FACTORS):
                점수 += 1.5
                이유.append(f"목표까지 {round(target_gap, 1)}세 남아서 숨차는 운동에 무게를 뒀어요")

        for r in 묶음:
            factors = routine_factors(age_gbn, r)
            덮은약점 = [w for w in weak if any(_factor_hit(w, f) for f in factors)]
            루틴점수 = 점수 + 1.0 * len(덮은약점) + 0.1 * len(factors)
            루틴이유 = list(이유)
            if 덮은약점:
                루틴이유.append(f"오늘 동작에 {' · '.join(덮은약점)} 운동이 들어 있어요")
            if not 루틴이유:
                루틴이유.append("먼저 기본을 고르게 채우는 구성이에요")
            out.append({
                "목적": purpose,
                "표시목적": reframe.get(purpose, purpose),
                "루틴번호": r.get("no"),
                "루틴명": r.get("name"),
                "점수": round(루틴점수, 2),
                "이유": 루틴이유,
                "체력요인": [k for k, _ in factors.most_common()],
                "동작수": len(r.get("steps", [])),
            })

    # 같은 목적이 연달아 나오면 고를 맛이 없다 — 목적별로 가장 높은 것부터 번갈아 낸다
    out.sort(key=lambda x: (-x["점수"], x["목적"], x["루틴번호"] or 0))
    골고루, 남은 = [], list(out)
    while 남은 and len(골고루) < limit:
        본목적 = set()
        나머지 = []
        for x in 남은:
            if x["목적"] in 본목적 or len(골고루) >= limit:
                나머지.append(x)
            else:
                본목적.add(x["목적"])
                골고루.append(x)
        남은 = 나머지
    for i, x in enumerate(골고루, 1):
        x["순위"] = i
    return 골고루


def for_user(age_gbn: str, *, weak=None, style_purpose=None, sports=None,
             target_gap=None, limit: int = 5) -> dict:
    """화면이 그대로 그릴 수 있는 형태. sports 는 종목 id 목록."""
    ids = [s for s in (sports or []) if s]
    factors = list(sp.factor_weights(ids)) if ids else []
    care = sp.care_parts(ids) if ids else []
    후보 = score(age_gbn, weak=weak, style_purpose=style_purpose,
                sport_factors=factors, target_gap=target_gap, limit=limit)
    return {
        "연령대": age_gbn,
        "추천": 후보,
        "참고": {"약점": list(weak or []), "종목요인": factors,
                "스타일목적": style_purpose, "목표격차": target_gap},
        "조심할부위": care,
        "샘플": rt.is_sample(),
    }
