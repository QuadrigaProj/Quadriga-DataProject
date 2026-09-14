"""목표 체력나이에 언제 닿을지 — 권장 용량(backend/dose.py)대로 주 3회 할 때의 추정.

측정 항목이 12주에 보통 얼마나 좋아지는지(문헌, docs/effective_dose.md 뒤에 정리)를
지금 측정값에 얹어 다시 환산나이를 내고, 체력나이가 목표 아래로 내려가는 주를 찾는다.
계산은 backend/fitness_age.py 의 같은 함수(convert_age · u_shaped_age · aggregate_age)로 한다 —
측정과 다른 잣대를 쓰지 않는다.

오차가 커서 "빠르면 N주, 늦으면 M주" 범위로만 말하고, 재측정 때마다 다시 잡는다.
추정이지 약속이 아니다 — 화면에 '추정' 이라고 적는다.
"""
from __future__ import annotations

try:
    from backend import fitness_age as fa
except ImportError:
    import fitness_age as fa  # type: ignore

# 항목 → 12주에 보통 좋아지는 폭 (단위, 낮은 추정, 높은 추정). 초보~중급이 권고 용량으로 할 때.
IMPROVE_12W = {
    "앉아윗몸앞으로굽히기": ("cm", 2.0, 4.0),       # 정적 스트레칭 주 3회 이상 4~12주: +2~4 cm
    "교차윗몸일으키기": ("pct", 15.0, 30.0),        # 근지구력 8~12주: +15~30 %
    "의자앉았다일어서기": ("pct", 10.0, 20.0),      # 어르신 하체 근력 12주: +10~20 %
    "제자리멀리뛰기": ("pct", 3.0, 8.0),            # 순발력 8~12주 (플라이오메트릭): +3~8 %
    "상대악력": ("pct", 4.0, 10.0),                 # 악력 12주 근력 훈련: +4~10 %
    "왕복오래달리기": ("pct", 8.0, 15.0),           # 심폐 8~12주: VO2max +8~15 %, 왕복 횟수도 그만큼
    "2분제자리걷기": ("pct", 8.0, 15.0),
    "BMI": ("abs", -0.5, -1.0),                     # 운동만으로(식단 없이) 12주: BMI −0.5~−1.0
}
DIMINISH = (1.0, 0.6, 0.4, 0.3)     # 12주 블록마다 곱 — 초보 효과는 처음이 가장 크고 점점 준다
MAX_WEEKS = 48
STEP_WEEKS = 4
ASSUMPTION = "주 3회 권장 용량대로 할 때"      # 게이지 아래 한 줄이라 짧게. 재측정으로 다시 잡힌다는 말은 안내에


def gain_fraction(weeks: float) -> float:
    """0주 → 0, 12주 → 1.0, 24주 → 1.6, 36주 → 2.0, 48주 → 2.3. 향상 폭은 점점 준다."""
    frac = 0.0
    for i, k in enumerate(DIMINISH):
        frac += k * min(1.0, max(0.0, (weeks - 12 * i) / 12))
    return frac


def improved(item: str, value: float, weeks: float, hi: bool) -> float:
    """그 항목의 측정값이 weeks 주 뒤에 어디쯤일지. 표에 없는 항목은 그대로."""
    spec = IMPROVE_12W.get(item)
    if spec is None or value is None:
        return value
    unit, lo, up = spec
    폭 = (up if hi else lo) * gain_fraction(weeks)
    if unit == "pct":
        return value * (1 + 폭 / 100)
    return value + 폭


def _parts(d, age_gbn: str, sex: str, raw: dict, weeks: float, hi: bool) -> dict:
    """fitness_age.fitness_age 와 같은 항목 구성으로, 값만 weeks 주 뒤로 옮겨서."""
    parts: dict[str, float] = {}
    v = raw.get("flexibility")
    if fa._given(v):
        a = fa.convert_age(d, age_gbn, sex, "앉아윗몸앞으로굽히기", improved("앉아윗몸앞으로굽히기", v, weeks, hi))
        if a is not None:
            parts["유연성"] = a
    v = raw.get("strength")
    if fa._given(v):
        label, item = fa.POWER_ITEM.get(age_gbn, fa.DEFAULT_POWER)
        a = fa.convert_age(d, age_gbn, sex, item, improved(item, v, weeks, hi))
        if a is not None:
            parts[label] = a
    v = raw.get("grip")
    if fa._given(v):
        a = fa.convert_age(d, age_gbn, sex, fa.GRIP_ITEM, improved(fa.GRIP_ITEM, v, weeks, hi))
        if a is not None:
            parts["근력"] = a
    v = raw.get("endurance")
    cardio = fa.CARDIO_ITEM.get(age_gbn)
    if fa._given(v) and cardio:
        a = fa.convert_age(d, age_gbn, sex, cardio, improved(cardio, v, weeks, hi))
        if a is not None:
            parts["심폐지구력"] = a
    v = raw.get("bmi")
    if fa._given(v):
        a = fa.u_shaped_age(d, age_gbn, sex, "BMI", improved("BMI", v, weeks, hi))
        if a is not None:
            parts["체성분"] = a
    return parts


def project(d, *, age_gbn: str, sex: str, age, target: float, flexibility=None, strength=None,
            grip=None, endurance=None, bmi=None) -> dict:
    """지금 측정값 → 목표 체력나이에 닿는 주 (빠르면·늦으면). 못 닿으면 None.

    성장기는 나이가 들수록 기록이 좋아져 "체력나이가 낮다 = 좋다" 가 아니다. 추정하지 않는다.
    """
    if age_gbn == fa.GROWTH:
        return {"가능": False, "안내": "성장기는 발달 수준으로 읽어서 도달 시점을 추정하지 않아요."}
    raw = {"flexibility": flexibility, "strength": strength, "grip": grip,
           "endurance": endurance, "bmi": bmi}
    지금 = fa.aggregate_age(_parts(d, age_gbn, sex, raw, 0, False), age_gbn, age)["체력나이"]
    if 지금 is None:
        return {"가능": False, "안내": "측정값이 부족해 추정할 수 없어요."}
    out = {"가능": True, "지금": 지금, "목표": float(target), "가정": ASSUMPTION,
           "빠르면주": None, "늦으면주": None, "12주뒤": {}, "요인별_12주뒤": {}}
    if 지금 <= target:
        out["이미도달"] = True
        out["안내"] = "목표에 이미 닿았어요. 다음 측정으로 확인해요."
        return out
    빠르면 = 늦으면 = None
    for weeks in range(STEP_WEEKS, MAX_WEEKS + 1, STEP_WEEKS):
        높게 = fa.aggregate_age(_parts(d, age_gbn, sex, raw, weeks, True), age_gbn, age)["체력나이"]
        낮게 = fa.aggregate_age(_parts(d, age_gbn, sex, raw, weeks, False), age_gbn, age)["체력나이"]
        if weeks == 12:
            out["12주뒤"] = {"빠르면": 높게, "늦으면": 낮게}
            out["요인별_12주뒤"] = fa.aggregate_age(_parts(d, age_gbn, sex, raw, 12, True), age_gbn, age)["항목별"]
        if 빠르면 is None and 높게 is not None and 높게 <= target:
            빠르면 = weeks
        if 늦으면 is None and 낮게 is not None and 낮게 <= target:
            늦으면 = weeks
        if 빠르면 is not None and 늦으면 is not None:
            break
    out["빠르면주"] = 빠르면
    out["늦으면주"] = 늦으면
    if 빠르면 is None:
        out["안내"] = "지금 측정값으로는 1년 안에 닿기 어려워요. 목표를 조금 가깝게 잡거나 용량을 올려요."
    elif 늦으면 is None:
        out["안내"] = f"빠르면 {빠르면}주, 느리면 1년 넘게 걸릴 수 있어요."
    else:
        out["안내"] = f"빠르면 {빠르면}주, 늦으면 {늦으면}주쯤 걸려요."
    return out
