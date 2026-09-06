"""
체력나이 산출 — 참조 구현

fitness_distribution.csv 의 연령구간별 중앙값(p50)을 이용해
사용자 측정값이 어느 연령대 수준인지 선형보간으로 역산한다.

사용법:
    python fitness_age.py
"""
from __future__ import annotations
import pandas as pd, numpy as np
from pathlib import Path

DIST = Path(__file__).resolve().parents[1] / "data" / "sample" / "fitness_distribution.csv"
BMI_IDEAL = 22.0

# 항목별 방향: True = 값이 클수록 좋음(젊음)
HIGHER_IS_BETTER = {
    "교차윗몸일으키기": True, "앉아윗몸앞으로굽히기": True,
    "의자앉았다일어서기": True, "6분걷기": True, "2분제자리걷기": True,
    "왕복오래달리기": True, "제자리멀리뛰기": True, "상대악력": True,
    "3m표적돌아오기": False, "8자보행": False,   # 초 단위 = 작을수록 좋음
    "BMI편차": False,                            # 적정치에서 멀수록 나쁨
}

def band_mid(b: str) -> float:
    b = str(b).replace("+", "~120")
    lo, _, hi = b.partition("~")
    lo = float(lo); hi = float(hi) if hi else lo + 4
    return (lo + hi) / 2

def load(dist_path: Path = DIST) -> pd.DataFrame:
    d = pd.read_csv(dist_path)
    d["age_mid"] = d["연령구간"].map(band_mid)
    return d

def convert_age(d: pd.DataFrame, age_gbn: str, sex: str, item: str, value: float) -> float | None:
    """측정값 → 환산 나이. 해당 성별/연령군의 p50 곡선에 선형보간."""
    sub = d[(d["연령군"] == age_gbn) & (d["성별"] == sex) & (d["항목"] == item)]
    sub = sub.sort_values("age_mid")
    if len(sub) < 2:
        return None
    ages, meds = sub["age_mid"].to_numpy(), sub["p50"].to_numpy()
    higher_better = HIGHER_IS_BETTER.get(item, True)
    # 값이 클수록 좋으면 나이가 들수록 p50이 감소 → 보간 위해 뒤집는다
    x, y = (meds[::-1], ages[::-1]) if higher_better else (meds, ages)
    if not np.all(np.diff(x) > 0):          # 단조가 아니면 정렬 강제
        order = np.argsort(x); x, y = x[order], y[order]
    return float(np.interp(value, x, y))

def fitness_age(d, age_gbn, sex, *, flexibility=None, strength=None, bmi=None) -> dict:
    """필수 3항목 → 체력나이. 없는 항목은 평균에서 제외한다."""
    parts = {}
    if flexibility is not None:
        a = convert_age(d, age_gbn, sex, "앉아윗몸앞으로굽히기", flexibility)
        if a is not None: parts["유연성"] = a
    if strength is not None:
        item = "의자앉았다일어서기" if age_gbn == "어르신" else "교차윗몸일으키기"
        a = convert_age(d, age_gbn, sex, item, strength)
        if a is not None: parts["근력"] = a
    if bmi is not None:
        # BMI는 U자형 → 적정치로부터의 편차로 변환한 뒤 역산
        sub = d[(d["연령군"] == age_gbn) & (d["성별"] == sex) & (d["항목"] == "BMI")].sort_values("age_mid")
        if len(sub) >= 2:
            dev_med = (sub["p50"] - BMI_IDEAL).abs().to_numpy()
            ages = sub["age_mid"].to_numpy()
            x, y = dev_med, ages
            order = np.argsort(x)
            parts["체성분"] = float(np.interp(abs(bmi - BMI_IDEAL), x[order], y[order]))
    if not parts:
        return {"체력나이": None, "항목별": {}}
    vals = list(parts.values())
    return {
        "체력나이": round(float(np.mean(vals)), 1),
        "신뢰구간": round(float(np.std(vals)) / max(len(vals) ** 0.5, 1), 1),
        "항목별": {k: round(v, 1) for k, v in parts.items()},
    }

def weakest_link(d, age_gbn, sex, result: dict) -> dict | None:
    """각 항목을 또래 평균(=실제 나이 수준)으로 올렸을 때 체력나이가 얼마나 떨어지는지."""
    parts = result["항목별"]
    if len(parts) < 2:
        return None
    base = np.mean(list(parts.values()))
    gains = {}
    for k in parts:
        others = [v for kk, v in parts.items() if kk != k]
        # 해당 항목이 또래 평균이면 그 항목의 환산 나이 = 나머지 평균 수준으로 가정
        target = min(parts.values())
        gains[k] = round(base - np.mean(others + [target]), 1)
    top = max(gains, key=gains.get)
    return {"약점": top, "개선효과": gains[top], "전체": gains}

if __name__ == "__main__":
    d = load()
    print("[예시] 성인 남성 45세, 유연성 3cm / 교차윗몸일으키기 25회 / BMI 27\n")
    r = fitness_age(d, "성인", "M", flexibility=3, strength=25, bmi=27)
    print(f"체력나이 {r['체력나이']}세 (±{r['신뢰구간']})")
    for k, v in r["항목별"].items():
        print(f"  {k:6s} {v}세 수준")
    w = weakest_link(d, "성인", "M", r)
    if w:
        print(f"\n가장 효율적인 약점: {w['약점']} → 개선 시 약 {w['개선효과']}세 감소")
        print(f"  항목별 효과: {w['전체']}")
