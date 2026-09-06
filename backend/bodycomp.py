"""InBody(체성분 분석기) 결과 → 체성분 분석 + (근거가 있으면) 추정 체력나이.

임의 가중치로 InBody 수치를 체력나이로 바꾸지 않는다(기획안 개정 1-A).
체력나이는 공개 측정데이터에 분포가 있는 항목(BMI·체지방률)만으로 산출하고,
골격근량·허리둘레·체수분은 판정 기준이 명확한 것만 '분석'으로 보여준다.
"""
from __future__ import annotations

try:
    from backend import fitness_age as fa
except ImportError:
    import fitness_age as fa

# 대한비만학회 체지방률 기준(성인) — 비만 컷오프
BODYFAT_OBESE = {"M": 25.0, "F": 30.0}
BODYFAT_LOW = {"M": 10.0, "F": 18.0}
# 허리/키 비율 (WHtR) — 0.5 이상이면 복부비만 위험 (WHO)
WHTR_RISK = 0.5
# 골격근량지수(SMI = 골격근량/키m²) 낮음 참고치 (AWGS 2019, DXA ASM 기준 근사)
SMI_LOW = {"M": 7.0, "F": 5.7}
# 체수분 비율 정상 범위(체중 대비, 성인 근사)
TBW_RANGE = {"M": (55.0, 65.0), "F": (45.0, 60.0)}


def _band(value, low, high):
    if value < low:
        return "낮음"
    if value > high:
        return "높음"
    return "정상"


def analyze(*, sex: str, age: float, height_cm: float, weight_kg: float,
            skeletal_muscle_kg: float | None = None, body_fat_pct: float | None = None,
            waist_cm: float | None = None, body_water_pct: float | None = None,
            dist=None) -> dict:
    h = height_cm / 100
    bmi = round(weight_kg / (h * h), 1)

    분석: list[dict] = [
        {"항목": "BMI", "값": bmi, "단위": "",
         "판정": _band(bmi, 18.5, 25.0), "기준": "18.5~25 정상 (대한비만학회)"}
    ]
    if body_fat_pct is not None:
        obese = BODYFAT_OBESE[sex]
        low = BODYFAT_LOW[sex]
        판정 = "비만" if body_fat_pct >= obese else ("낮음" if body_fat_pct < low else "정상")
        분석.append({"항목": "체지방률", "값": round(body_fat_pct, 1), "단위": "%",
                    "판정": 판정, "기준": f"{sex=='M' and '남 25%' or '여 30%'} 이상 비만"})
    if waist_cm is not None:
        whtr = round(waist_cm / height_cm, 2)
        분석.append({"항목": "허리/키 비율", "값": whtr, "단위": "",
                    "판정": "복부비만 위험" if whtr >= WHTR_RISK else "정상",
                    "기준": "0.5 이상 위험 (WHO)"})
    if skeletal_muscle_kg is not None:
        smi = round(skeletal_muscle_kg / (h * h), 1)
        분석.append({"항목": "골격근량지수", "값": smi, "단위": "kg/m²",
                    "판정": "낮음(근감소 참고)" if smi < SMI_LOW[sex] else "정상",
                    "기준": f"AWGS 참고치 {SMI_LOW[sex]} 미만 낮음"})
    if body_water_pct is not None:
        lo, hi = TBW_RANGE[sex]
        분석.append({"항목": "체수분 비율", "값": round(body_water_pct, 1), "단위": "%",
                    "판정": _band(body_water_pct, lo, hi), "기준": f"{lo}~{hi}% (성인 근사)"})

    # 근거 있는 체력나이 — BMI/체지방률 분포가 있는 연령군만
    체력나이 = None
    if dist is not None:
        age_gbn = "어르신" if age >= 65 else ("성인" if age >= 19 else None)
        if age_gbn:
            r = fa.fitness_age(dist, age_gbn, sex, bmi=bmi, body_fat=body_fat_pct, age=age)
            if r["체력나이"] is not None:
                체력나이 = {
                    "값": r["체력나이"], "신뢰구간": r["신뢰구간"],
                    "항목별": r["항목별"], "집중개선영역": r["집중개선영역"],
                    "안내": "체성분(BMI·체지방률)만으로 추정한 값이에요. "
                          "근력·유연성·심폐지구력은 홈 체력측정으로 채우면 더 정확해요.",
                }

    return {
        "BMI": bmi,
        "체성분분석": 분석,
        "추정체력나이": 체력나이,
        "안내": "골격근량·체수분은 InBody 제조사·모델마다 정의가 달라 참고 지표로만 보여줘요. "
              "임의 산식으로 체력나이를 만들지 않습니다.",
    }
