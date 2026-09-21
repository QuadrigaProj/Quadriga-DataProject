"""루틴 추천 — 사용자 데이터로 후보에 점수를 매겨 순위를 낸다.

추천을 지어내지 않는다. 이미 있는 200개 KSPO 루틴(data/generated/routines_200_kspo.json)
안에서 고르고, 왜 골랐는지를 근거 문장으로 함께 돌려준다.
근거를 댈 수 없는 추천은 하지 않는다는 것이 이 모듈의 규칙이다.

사용자가 운동 단계(목적)를 골랐으면 **그 목적의 루틴 안에서만** 고른다 — 다이어트를 골랐는데 벌크업 루틴을
내밀지 않는다. 고르지 않았을 때만 여덟 목적 전부에서 고르고, 목적이 골고루 섞이게 세운다.

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
                "부위": (info.get("kspo") or {}).get("trng_part_nm") or "",      # 국민체력100 이 붙인 운동 부위 (관리 부위 고르기에 쓴다)
            })
    return out


# 다이어트에서 고르는 '관리하고 싶은 부위' → 그 부위를 쓰는 동작을 알아보는 법.
# 먼저 국민체력100 이 동작마다 붙여 둔 운동 부위(kspo.trng_part_nm: 복부 · 둔부 · 허벅지앞쪽 · 위팔뒤쪽 …)를 보고,
# 그 값이 비었거나 '//' 처럼 깨진 동작은 이름의 낱말로 알아본다.
# 살은 부위별로 따로 빠지지 않는다. 여기서 하는 일은 그 부위 근육을 쓰는 동작이 든 루틴을 앞에 세우는 것뿐이고,
# 화면도 그렇게 말한다.
FOCUS_AREAS = {
    "팔": {"부위": ("위팔", "아래팔"), "낱말": ("팔굽혀", "팔꿈치", "아령", "덤벨 들어", "덤벨 옆으로", "물병 옆으로", "물통으로")},
    "뱃살": {"부위": ("복부", "윗복근", "아랫복근"), "낱말": ("윗몸", "배가로근", "V자", "크런치", "대고 버티기", "무릎 당기기")},
    "옆구리": {"부위": (), "낱말": ("옆구리", "비틀", "옆으로 굽히기", "옆으로 기울이기", "측면", "옆으로 누워 버티기",
                                "옆으로 팔 대고 버티기", "몸통 돌리기", "몸통 회전")},
    "등": {"부위": ("등",), "낱말": ("당겨 내리기", "뒤로 당기기", "바벨 끌어당기기", "당겨 올리기", "슈퍼맨", "등 모으기", "상체 들어올리기")},
    "엉덩이": {"부위": ("둔부",), "낱말": ("엉덩이 들어올리기", "뒤로 차기", "뒤로 다리", "다리 뒤로", "한 발 뒤로", "앉았다 일어서기")},
    "허벅지": {"부위": ("허벅지",), "낱말": ("앉았다 일어서기", "굽혔다 펴기", "계단", "스텝박스", "박스 오르내리기")},
    "종아리": {"부위": ("종아리",), "낱말": ("뒤꿈치", "줄넘기")},
}


def _area_hit(area: str, step: dict) -> bool:
    spec = FOCUS_AREAS[area]
    tokens = [t.strip() for t in str(step.get("부위") or "").split("/") if t.strip()]
    if any(t.startswith(prefix) for t in tokens for prefix in spec["부위"]):
        return True
    name = str(step.get("동작") or "")
    return any(k in name for k in spec["낱말"])


def focus_hits(steps: list[dict], areas) -> list[str]:
    """고른 부위 가운데 이 루틴의 본운동이 실제로 쓰는 부위 — 고른 순서대로."""
    main = [s for s in steps if s.get("단계") == "본운동"]
    return [a for a in (areas or []) if a in FOCUS_AREAS and any(_area_hit(a, s) for s in main)]


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
    """이 동작을 오늘 얼마나 하는지 — 세트 수만 (H2).

    영상을 따라 하는 구조라 반복 횟수나 초 단위 수행 시간은 화면에 쓰지 않는다.
    준비·정리 운동은 세트 개념이 없어 그대로 한 번 따라 한다.
    """
    if step.get("단계") != "본운동":
        return "천천히 한 번"
    세트 = 강도.get("세트", 2)
    return f"{세트}세트"


def score(age_gbn: str, *, weak=None, style_purpose=None, sport_factors=None,
          target_gap=None, limit: int = 5, sport_names=None, areas=None, purpose=None) -> list[dict]:
    """목적 × 루틴 후보에 점수를 매겨 높은 순으로 돌려준다.

    purpose 는 사용자가 고른 운동 단계다. 주면 그 목적의 루틴(연령대마다 10개) 안에서만 점수 순으로 고른다.
    안 줬거나 모르는 이름이면 예전처럼 여덟 목적 전부에서 고른다.

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
    고른목적 = purpose if purpose in rt.PURPOSES and d["routines"].get(age_gbn, {}).get(purpose) else None
    목적들 = [고른목적] if 고른목적 else list(rt.PURPOSES)

    out = []
    for purpose in 목적들:
        묶음 = d["routines"].get(age_gbn, {}).get(purpose) or []
        우선 = purpose_factors.get(purpose, [])
        점수 = 0.0
        이유 = [f"고른 운동 단계 '{고른목적}' 에 맞춘 루틴이에요"] if 고른목적 else []

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
            덮은부위 = focus_hits(steps, areas)          # 다이어트에서 고른 관리 부위 — 그 부위를 쓰는 본운동이 있나
            루틴점수 = (점수 + 1.0 * len(덮은약점)
                    + 0.8 * sum(무게[f] for f in 덮은종목요인) + 1.2 * len(덮은부위) + 0.1 * len(factors))
            루틴이유 = list(이유)
            if 덮은약점:
                루틴이유.append(f"오늘 동작에 {' · '.join(덮은약점)} 운동이 들어 있어요")
            if 덮은종목요인:
                누가 = f"{종목이름}에" if 종목이름 else "고른 종목에"
                루틴이유.append(f"{누가} 필요한 {' · '.join(덮은종목요인)} 동작이 오늘 루틴에 있어요")
            if 덮은부위:
                루틴이유.append(f"관리하고 싶은 {' · '.join(덮은부위)}을(를) 쓰는 동작이 들어 있어요")
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
    if 고른목적:                          # 한 목적 안에서는 점수 순 그대로 — 목적을 골고루 섞을 일이 없다
        for i, x in enumerate(out[:limit], 1):
            x["순위"] = i
        return out[:limit]
    # 고를 근거가 있을 때만 두 자리를 내준다. 근거가 없으면 점수가 고만고만해서
    # 앞자리를 몰아 줄 이유가 없다 — 그때는 예전처럼 목적을 골고루 보여 준다.
    TOP_AS_IS = 2 if (weak or 무게 or style_purpose or areas) else 0
    골고루 = out[:min(TOP_AS_IS, limit)]
    앞자리 = {id(x) for x in 골고루}
    남은 = [x for x in out if id(x) not in 앞자리]
    # 한 바퀴에 목적마다 하나씩 세운다. 같은 목적이 셋씩 이어지면 고를 맛이
    # 없어서다. 다음 바퀴에서 다시 처음부터 — 그래야 목적 수보다 많이
    # 달라고 해도 채워진다.
    #
    # 예전에는 본 목적을 골고루 전체에서 다시 뽑았다. 그러면 목적이 한 번씩
    # 다 나온 뒤로는 아무것도 못 담으면서 남은 것은 그대로라, limit 이 목적
    # 수(5)보다 크면 이 while 이 영영 끝나지 않았다. 화면은 limit=12 로
    # 부른다 — 추천이 통째로 멈춰 있었다.
    첫바퀴 = True
    while 남은 and len(골고루) < limit:
        # 첫 바퀴만 앞자리(TOP_AS_IS)에 나온 목적을 피한다. 앞에 두 개가 같은
        # 목적이면 바로 뒤에 또 세울 이유가 없다. 두 바퀴째부터는 비우고
        # 다시 시작한다 — 그래야 목적 수보다 많이 달라고 해도 채워진다.
        본목적: set[str] = {y["목적"] for y in 골고루} if 첫바퀴 else set()
        첫바퀴 = False
        나머지 = []
        for x in 남은:
            if x["목적"] in 본목적 or len(골고루) >= limit:
                나머지.append(x)
            else:
                본목적.add(x["목적"])
                골고루.append(x)
        if len(나머지) == len(남은):
            break                         # 한 바퀴 돌고 아무것도 안 담겼다면 더 담을 것이 없다
        남은 = 나머지
    for i, x in enumerate(골고루, 1):
        x["순위"] = i
    return 골고루


def for_user(age_gbn: str, *, weak=None, style_purpose=None, sports=None,
             target_gap=None, limit: int = 5, week: int = 1, areas=None, purpose=None) -> dict:
    """화면이 그대로 그릴 수 있는 형태. sports 는 종목 id 목록, purpose 는 사용자가 고른 운동 단계(목적)."""
    purpose = purpose if purpose in rt.PURPOSES else None
    ids = [s for s in (sports or []) if s]
    무게 = sp.factor_weights(ids) if ids else {}
    factors = list(무게)
    이름 = [s.get("이름") for s in sp.resolve(ids)] if ids else []
    care = sp.care_parts(ids) if ids else []
    areas = list(dict.fromkeys(a for a in (areas or []) if a in FOCUS_AREAS))      # 모르는 이름은 버리고, 같은 부위를 두 번 세지 않는다
    후보 = score(age_gbn, weak=weak, style_purpose=style_purpose,
                sport_factors=무게, target_gap=target_gap, limit=limit,
                sport_names=이름, areas=areas, purpose=purpose)
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
                "스타일목적": style_purpose, "목표격차": target_gap, "관리부위": areas,
                "고른목적": purpose},
        "조심할부위": care,
        "샘플": rt.is_sample(),
    }
