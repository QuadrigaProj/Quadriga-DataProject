"""루틴 추천 — 사용자 데이터로 후보에 점수를 매겨 순위를 낸다.

추천을 지어내지 않는다. 이미 있는 200개 KSPO 루틴(data/generated/routines_200_kspo.json)
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

# 난이도 — 원본 데이터에 난이도 칸이 없어서 루틴의 구성으로 재본다 (H3).
#   숨찬 운동일수록 · 부담 부위가 있을수록 · 도구가 필요할수록 어렵다.
HARD_FACTORS = ("심폐지구력", "순발력", "민첩성")
PHASE_KEY = {"준비운동": "prep", "본운동": "main", "정리운동": "cool"}


def _factor_hit(a: str, b: str) -> bool:
    """'근력·근지구력(하체)' 처럼 묶여 있어 부분 일치로 본다."""
    return a in b or b in a


def routine_steps(age_gbn: str, routine: dict) -> list[dict]:
    """루틴 한 벌의 동작을 순서대로. 화면이 자세히 보여줄 재료다 (H2)."""
    pools = rt.load()["pools"].get(age_gbn, {})
    out = []
    for phase, key in PHASE_KEY.items():
        for code in routine.get(key, []):
            info = pools.get(phase, {}).get(code)
            if not info:
                continue
            out.append({
                "단계": phase, "코드": code, "동작": info.get("동작"),
                "체력요인": info.get("체력요인", []), "도구": info.get("도구"),
                "유형": info.get("유형"), "부담부위": info.get("부담부위", []),
            })
    return out


def routine_factors(age_gbn: str, routine: dict) -> Counter:
    """루틴 한 벌이 어떤 체력요인을 몇 번 다루는지."""
    c: Counter = Counter()
    for step in routine_steps(age_gbn, routine):
        c.update(step["체력요인"])
    return c


def difficulty(steps: list[dict]) -> float:
    """0(가장 쉬움) ~ 1(가장 어려움). 데이터에 없는 값이라 구성으로 재는 추정치다."""
    본 = [s for s in steps if s["단계"] == "본운동"] or steps
    if not 본:
        return 0.0
    숨참 = sum(1 for s in 본 if any(_factor_hit(h, f) for f in s["체력요인"] for h in HARD_FACTORS))
    부담 = sum(1 for s in 본 if s["부담부위"])
    도구 = sum(1 for s in 본 if s["도구"] and s["도구"] not in ("맨몸", "미제공"))
    n = len(본)
    return round(0.5 * (숨참 / n) + 0.3 * (부담 / n) + 0.2 * (도구 / n), 3)


def difficulty_label(score: float) -> str:
    return "쉬움" if score < 0.25 else ("어려움" if score >= 0.5 else "보통")


def step_amount(step: dict, 강도: dict) -> str:
    """이 동작을 오늘 얼마나 하는지 — 횟수/초씩 세트 (H2).

    "2세트 · 10회"처럼 세트를 앞세우면 반복이 먼저인지 세트가 먼저인지
    헷갈려한다는 피드백이 있어, "10회씩 2세트"처럼 반복을 앞세운다.
    """
    세트 = 강도.get("세트")
    if step.get("단계") != "본운동":
        return "천천히 한 번"
    if step.get("유형") == "시간":
        초 = 강도.get("시간초")
        return f"{초}초씩 {세트}세트" if 초 else f"{세트}세트"
    if 강도.get("반복") is not None:
        return f"{강도['반복']}회씩 {세트}세트"
    if 강도.get("라운드") is not None:
        return f"{강도['라운드']}라운드"
    return f"{세트}세트"


def score(age_gbn: str, *, weak=None, style_purpose=None, sport_factors=None,
          target_gap=None, limit: int = 5, sport_names=None) -> list[dict]:
    """목적 × 루틴 후보에 점수를 매겨 높은 순으로 돌려준다.

    sport_factors 는 {요인: 몇 개 종목이 요구하는지} 다. 목록으로 줘도 받는다
    (그때는 전부 1로 본다). 여러 종목이 같은 요인을 요구하면 그만큼 무겁게
    센다 — 러닝과 수영을 함께 골랐으면 심폐지구력이 두 배로 중요하다.
    """
    d = rt.load()
    purpose_factors = d["config"]["purpose_factors"]
    reframe = d["config"]["reframe"].get(age_gbn, {})
    weak = [w for w in (weak or []) if w]
    무게 = (dict(sport_factors) if isinstance(sport_factors, dict)
          else {f: 1 for f in (sport_factors or []) if f})
    무게 = {f: max(1, int(w or 1)) for f, w in 무게.items() if f}
    sport_factors = list(무게)
    종목이름 = " · ".join(sport_names or [])

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
            # 여러 종목이 함께 요구하는 요인일수록 무겁게 센다
            점수 += 1.5 * sum(무게[f] for f in 맞은종목)
            누가 = f"{종목이름}이(가) " if 종목이름 else "고른 종목이 "
            이유.append(f"{누가}많이 쓰는 {' · '.join(맞은종목)}이(가) 들어 있어요")

        if target_gap is not None and target_gap >= GAP_THRESHOLD:
            if any(any(_factor_hit(g, f) for f in 우선) for g in GAP_FACTORS):
                점수 += 1.5
                이유.append(f"목표까지 {round(target_gap, 1)}세 남아서 숨차는 운동에 무게를 뒀어요")

        for r in 묶음:
            steps = routine_steps(age_gbn, r)
            factors = routine_factors(age_gbn, r)
            덮은약점 = [w for w in weak if any(_factor_hit(w, f) for f in factors)]
            # 종목 반영은 여태까지 목적(purpose) 단위로만 붙어서(맞은종목), 그 목적 안의
            # 루틴이면 실제로 그 요인을 다루든 말든 다 같은 점수를 받았다 — 결과가 항상
            # "기초 체력 증진" 같은 넓은 목적 몇 개로만 쏠리고, 고른 종목(등산·수영 등)이
            # 실제로 어떤 동작에 반영됐는지는 드러나지 않았다. 약점(덮은약점)과 같은
            # 자리에서 이 루틴 자체의 체력요인을 보고 한 번 더 매겨서, 종목이 필요로
            # 하는 요인을 실제로 다루는 루틴이 그 목적 안에서도 앞에 오게 한다.
            덮은종목요인 = sorted({s for s in sport_factors if any(_factor_hit(s, f) for f in factors)})
            루틴점수 = (점수 + 1.0 * len(덮은약점)
                    + 0.8 * sum(무게[f] for f in 덮은종목요인) + 0.1 * len(factors))
            루틴이유 = list(이유)
            if 덮은약점:
                루틴이유.append(f"오늘 동작에 {' · '.join(덮은약점)} 운동이 들어 있어요")
            if 덮은종목요인:
                누가 = f"{종목이름}에" if 종목이름 else "고른 종목에"
                루틴이유.append(f"{누가} 필요한 {' · '.join(덮은종목요인)} 동작이 오늘 루틴에 있어요")
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
                "난이도점수": difficulty(steps),
                "난이도": difficulty_label(difficulty(steps)),
                "steps": steps,
            })

    # 목적이 다섯인데 다섯 개를 뽑으면, 목적마다 한 줄씩 세우느라 점수가 묻힌다.
    # 무엇을 골라도 같은 다섯 개가 나오는 것처럼 보였다. 그래서 **가장 높은
    # 두 개는 목적과 상관없이 그대로** 내고, 나머지만 목적이 겹치지 않게 채운다.
    # 고른 종목이 뚜렷하면 그 목적이 두 자리를 가져갈 수 있다.
    out.sort(key=lambda x: (-x["점수"], x["목적"], x["루틴번호"] or 0))
    # 고를 근거가 있을 때만 두 자리를 내준다. 근거가 없으면 점수가 고만고만해서
    # 앞자리를 몰아 줄 이유가 없다 — 그때는 예전처럼 목적을 골고루 보여 준다.
    TOP_AS_IS = 2 if (weak or 무게 or style_purpose) else 0
    골고루 = out[:min(TOP_AS_IS, limit)]
    남은 = [x for x in out if x not in 골고루]
    while 남은 and len(골고루) < limit:
        본목적 = set()
        나머지 = []
        # 앞자리에 이미 나온 목적은 다시 세우지 않는다. 같은 목적이 셋씩
        # 이어지면 그것대로 고를 맛이 없다.
        본목적 = {y["목적"] for y in 골고루}
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
             target_gap=None, limit: int = 5, week: int = 1) -> dict:
    """화면이 그대로 그릴 수 있는 형태. sports 는 종목 id 목록."""
    ids = [s for s in (sports or []) if s]
    무게 = sp.factor_weights(ids) if ids else {}
    factors = list(무게)
    이름 = [s.get("이름") for s in sp.resolve(ids)] if ids else []
    care = sp.care_parts(ids) if ids else []
    후보 = score(age_gbn, weak=weak, style_purpose=style_purpose,
                sport_factors=무게, target_gap=target_gap, limit=limit,
                sport_names=이름)
    # 오늘 얼마나 하는지를 동작마다 붙인다 (H2). 주차는 프로그램 경과에서 온다.
    강도 = rt.intensity_for(age_gbn, max(1, min(13, int(week or 1))))
    분 = rt.load()["config"]["age_minutes"].get(age_gbn)
    for x in 후보:
        for s in x.get("steps", []):
            s["수행량"] = step_amount(s, 강도)
        x["예상시간분"] = 분
    return {
        "연령대": age_gbn,
        "추천": 후보,
        "강도": 강도,
        "참고": {"약점": list(weak or []), "종목요인": factors,
                "종목요인무게": 무게, "고른종목": 이름,
                "스타일목적": style_purpose, "목표격차": target_gap},
        "조심할부위": care,
        "샘플": rt.is_sample(),
    }
