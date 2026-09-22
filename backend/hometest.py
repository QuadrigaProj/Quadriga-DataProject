"""홈 체력측정(약 4분) → 추정 체력나이 + 항목별 홈 체력등급 + 가장 부족한 요인.

홈 측정 4항목 중 국민체력100 공개 데이터에 **같은 측정**이 있는 것은 하나다:
  윗몸일으키기(1분) = item '교차윗몸일으키기'  → 환산나이를 낸다 (curlup_30s 는 옛 이름 — 값은 1분 횟수다)
무릎 푸시업·2분 하이니는 공개 데이터에 대응 항목이 없어 **체력나이로 억지 환산하지 않고**
나이·성별 기준표로 등급(A~E)만 매긴다.
30초 제자리 점프는 기록만 돌려준다. 전에는 분포의 '반복점프'(item_f020)와 견줬는데, 그 필드는 반복점프가 아니라
왕복오래달리기(회)였다 — 점프 횟수를 달리기 횟수와 견준 셈이라 뺐다. 진짜 반복점프 자료가 생기면 되살린다.
"""
from __future__ import annotations

try:
    from backend import fitness_age as fa
except ImportError:
    import fitness_age as fa

GRADES = ["E", "D", "C", "B", "A"]

# 나이·성별별 30초/2분 반복 기준 (중앙값 근사, 홈 자가측정 난이도 반영).
# 공개 데이터가 없는 항목이라 '등급' 표기이며 체력나이 산출에는 쓰지 않는다.
# {요인: {성별: [(상한나이, [E,D,C,B] 컷)]}} — 값 이상이면 그 등급, 마지막은 A
KNEE_PUSHUP = {   # 30초 무릎 푸시업 (회)
    "M": [(29, [8, 14, 20, 27]), (49, [6, 11, 16, 22]), (200, [4, 8, 12, 17])],
    "F": [(29, [6, 11, 16, 22]), (49, [4, 8, 12, 17]), (200, [3, 6, 9, 13])],
}
HIGH_KNEE = {     # 2분 제자리 높은 무릎 뛰기 (회, 한 다리 기준)
    "M": [(29, [70, 95, 120, 145]), (49, [60, 82, 104, 126]), (200, [45, 65, 85, 105])],
    "F": [(29, [60, 82, 104, 126]), (49, [50, 70, 90, 110]), (200, [38, 55, 72, 90])],
}


def _grade(table: dict, sex: str, age: float, value: float) -> str:
    rows = table.get(sex, table["M"])
    cuts = next(cuts for top, cuts in rows if age <= top)
    g = 0
    for c in cuts:
        if value >= c:
            g += 1
    return GRADES[g]


def evaluate(dist, *, sex: str, age: float, height_cm: float, weight_kg: float,
             jump_30s: float | None = None, curlup_30s: float | None = None,
             knee_pushup_30s: float | None = None, high_knee_2min: float | None = None,
             waist_cm: float | None = None) -> dict:
    age_gbn = ("어르신" if age >= 65 else "성인" if age >= 19
               else "성장기" if age >= 11 else None)
    bmi = round(weight_kg / (height_cm / 100) ** 2, 1)

    parts: dict[str, float] = {}
    등급: list[dict] = []

    if age_gbn:
        if fa._given(curlup_30s):
            a = fa.item_age(dist, age_gbn, sex, "교차윗몸일으키기", curlup_30s, age)
            if a is not None:
                parts["근지구력"] = a
        cb = fa.bmi_age(dist, age_gbn, sex, bmi, age)
        if cb is not None:
            parts["체성분"] = cb

    # 공개 데이터 없는 항목 — 등급만. 실제로 잰 항목만(_given) 등급을 매긴다 —
    # 안 잰 항목이 0·None 언저리 값으로 계산돼 등급이 나오면 안 된다.
    if fa._given(jump_30s):                     # 견줄 공개 자료가 없다 — 등급 없이 기록만
        등급.append({"항목": "30초 제자리 점프", "값": jump_30s, "등급": None})
    if fa._given(knee_pushup_30s):
        등급.append({"항목": "상체 근력(무릎 푸시업)", "값": knee_pushup_30s,
                    "등급": _grade(KNEE_PUSHUP, sex, age, knee_pushup_30s)})
    if fa._given(high_knee_2min):
        등급.append({"항목": "심폐지구력(2분 하이니)", "값": high_knee_2min,
                    "등급": _grade(HIGH_KNEE, sex, age, high_knee_2min)})

    agg = fa.aggregate_age(parts, age_gbn or "성인", age)

    # 가장 부족한 요인: 환산나이가 실제 나이보다 가장 많이 높은 항목,
    # 없으면 등급이 가장 낮은 항목.
    부족 = None
    if agg["항목별"]:
        worst = max(agg["항목별"].items(), key=lambda kv: kv[1] - age)
        if worst[1] - age >= 3:
            부족 = worst[0]
    매긴것 = [e for e in 등급 if e["등급"]]
    if 부족 is None and 매긴것:
        부족 = min(매긴것, key=lambda e: GRADES.index(e["등급"]))["항목"]

    return {
        "추정체력나이": agg["체력나이"],
        "신뢰구간": agg["신뢰구간"],
        "항목별환산나이": agg["항목별"],
        "홈체력등급": 등급,
        "집중개선영역": agg["집중개선영역"],
        "가장부족한요인": 부족,
        "BMI": bmi,
        "안내": ("무릎 푸시업·2분 하이니는 공개 데이터에 대응 항목이 없어 등급으로만 보여줘요. "
               "30초 점프는 기록만 남깁니다. 셋 다 체력나이에는 반영하지 않습니다."
               if age_gbn else
               "이 연령대는 공개 체력 분포가 없어 체력나이 대신 홈 등급만 제공해요."),
    }
