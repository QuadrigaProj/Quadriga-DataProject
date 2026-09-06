"""
체력나이 산출

data/processed/ (없으면 data/sample/) 의 fitness_distribution.csv 의 연령구간별 중앙값(p50)을 이용해
사용자 측정값이 어느 연령대 수준인지 선형보간으로 역산한다.

국민체력100은 등급(1~6)만 제공하고 체력나이는 제공하지 않는다.
공개 측정결과 데이터의 성별·연령대별 분포에서 우리가 직접 산출하는 지표다.

사용법:
    python backend/fitness_age.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

try:                                     # 저장소 루트에서 실행할 때
    from backend.paths import find_data
except ImportError:                      # backend/ 안에서 직접 실행할 때
    from paths import find_data

BMI_IDEAL = 22.0

# 연령구간이 2개뿐이면 선형보간이 양 끝값에 붙어버려 누구나 같은 값이 나온다.
# (예: 청소년은 공개 데이터에 10~14 / 15~19 두 구간뿐이라 산출 불가)
MIN_BANDS = 3

# 항목별 방향: True = 값이 클수록 좋음(젊음)
HIGHER_IS_BETTER = {
    "교차윗몸일으키기": True, "앉아윗몸앞으로굽히기": True,
    "의자앉았다일어서기": True, "6분걷기": True, "2분제자리걷기": True,
    "왕복오래달리기": True, "제자리멀리뛰기": True, "상대악력": True,
    "3m표적돌아오기": False, "8자보행": False,   # 초 단위 = 작을수록 좋음
}


def band_mid(b: str) -> float:
    """연령구간 문자열("19~24") → 중앙값."""
    b = str(b).replace("+", "~120")
    lo, _, hi = b.partition("~")
    lo = float(lo)
    hi = float(hi) if hi else lo + 4
    return (lo + hi) / 2


def load(path: Path | None = None) -> pd.DataFrame:
    d = pd.read_csv(path or find_data("fitness_distribution.csv"))
    d["age_mid"] = d["연령구간"].map(band_mid)
    return d


def convert_age(d: pd.DataFrame, age_gbn: str, sex: str, item: str, value: float) -> float | None:
    """측정값 → 환산 나이. 해당 성별·연령군의 p50 곡선에 선형보간한다."""
    sub = d[(d["연령군"] == age_gbn) & (d["성별"] == sex) & (d["항목"] == item)]
    sub = sub.sort_values("age_mid")
    if len(sub) < MIN_BANDS:
        return None
    ages, meds = sub["age_mid"].to_numpy(), sub["p50"].to_numpy()
    # 값이 클수록 좋으면 나이가 들수록 p50이 감소 → 보간을 위해 뒤집는다
    higher_better = HIGHER_IS_BETTER.get(item, True)
    x, y = (meds[::-1], ages[::-1]) if higher_better else (meds, ages)
    order = np.argsort(x)
    return float(np.interp(value, x[order], y[order]))


def fitness_age(d, age_gbn, sex, *, flexibility=None, strength=None, bmi=None) -> dict:
    """필수 3항목 → 체력나이. 없는 항목은 평균에서 제외한다."""
    parts: dict[str, float] = {}

    if flexibility is not None:
        a = convert_age(d, age_gbn, sex, "앉아윗몸앞으로굽히기", flexibility)
        if a is not None:
            parts["유연성"] = a

    if strength is not None:
        # 연령군마다 근력 측정 항목이 다르다 (성인 f019 / 어르신 f023)
        item = "의자앉았다일어서기" if age_gbn == "어르신" else "교차윗몸일으키기"
        a = convert_age(d, age_gbn, sex, item, strength)
        if a is not None:
            parts["근력"] = a

    if bmi is not None:
        # BMI는 U자형이라 원값을 역산하면 저체중이 "젊음"으로 계산된다.
        # 적정치(22)로부터의 편차 절댓값으로 변환해 단조 관계를 만든다.
        sub = d[(d["연령군"] == age_gbn) & (d["성별"] == sex) & (d["항목"] == "BMI")]
        sub = sub.sort_values("age_mid")
        if len(sub) >= MIN_BANDS:
            dev = (sub["p50"] - BMI_IDEAL).abs().to_numpy()
            ages = sub["age_mid"].to_numpy()
            order = np.argsort(dev)
            parts["체성분"] = float(np.interp(abs(bmi - BMI_IDEAL), dev[order], ages[order]))

    if not parts:
        return {"체력나이": None, "신뢰구간": None, "항목별": {}}

    vals = list(parts.values())
    return {
        "체력나이": round(float(np.mean(vals)), 1),
        # 항목 간 편차가 클수록 추정이 불안정하다 → 화면에 ± 로 함께 표시한다
        "신뢰구간": round(float(np.std(vals)) / max(len(vals) ** 0.5, 1), 1),
        "항목별": {k: round(v, 1) for k, v in parts.items()},
    }


def weakest_link(result: dict) -> dict | None:
    """어느 항목을 고치면 체력나이가 가장 많이 내려가는지 계산한다.

    별도 근거 데이터가 필요 없다. 우리 산출식 위의 산술 계산이다.
    """
    parts = result.get("항목별") or {}
    if len(parts) < 2:
        return None
    base = float(np.mean(list(parts.values())))
    best = min(parts.values())          # 가장 좋은 항목 수준까지 올린다고 가정
    gains = {}
    for k in parts:
        others = [v for kk, v in parts.items() if kk != k]
        gains[k] = round(base - float(np.mean(others + [best])), 1)
    top = max(gains, key=gains.get)
    return {"약점": top, "개선효과": gains[top], "전체": gains}


if __name__ == "__main__":
    d = load()
    print("[예시] 성인 남성 45세 · 유연성 3cm · 교차윗몸일으키기 25회 · BMI 27\n")
    r = fitness_age(d, "성인", "M", flexibility=3, strength=25, bmi=27)
    print(f"체력나이 {r['체력나이']}세 (±{r['신뢰구간']})")
    for k, v in r["항목별"].items():
        print(f"  {k:6s} {v}세 수준")
    w = weakest_link(r)
    if w:
        print(f"\n가장 효율적인 약점: {w['약점']} → 개선 시 약 {w['개선효과']}세 감소")
        print(f"  항목별 효과: {w['전체']}")
