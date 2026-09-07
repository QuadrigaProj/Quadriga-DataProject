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
MIN_BANDS = 3

# 연령군마다 잴 수 있는 항목이 다르다.
#   성인   교차윗몸일으키기 (item_f019)
#   어르신 의자앉았다일어서기 (item_f023)
#   성장기 제자리멀리뛰기 (item_f022) — 11~18세는 윗몸일으키기 데이터가 없다.
#          줄자만 있으면 집에서 잴 수 있어 자가 측정 전제와도 맞는다.
POWER_ITEM = {
    "어르신": ("근지구력", "의자앉았다일어서기"),
    "성장기": ("순발력", "제자리멀리뛰기"),
}
DEFAULT_POWER = ("근지구력", "교차윗몸일으키기")

# 선택 입력 — 잰 사람만 넣는다 (G6). 넣지 않으면 지금까지와 똑같이 동작한다.
#   근력      상대악력 = 악력(kg) / 몸무게(kg) * 100. 세 연령군 모두 분포가 있다.
#   심폐지구력 성인은 왕복오래달리기, 어르신은 2분제자리걷기.
#             성장기는 공개 분포에 심폐 항목이 없어 산출하지 않는다.
GRIP_ITEM = "상대악력"
CARDIO_ITEM = {"성인": "왕복오래달리기", "어르신": "2분제자리걷기"}

# 성장기는 나이가 많을수록 기록이 좋아진다. 성인·어르신과 방향이 반대라
# "체력나이가 높다 = 나쁘다" 가 성립하지 않는다. 화면에서는 발달 수준으로 읽는다.
GROWTH = "성장기"

PCTS = (5, 10, 25, 50, 75, 90, 95)

# 항목별 방향: True = 값이 클수록 좋음(젊음)
HIGHER_IS_BETTER = {
    "교차윗몸일으키기": True, "앉아윗몸앞으로굽히기": True,
    "의자앉았다일어서기": True, "6분걷기": True, "2분제자리걷기": True,
    "왕복오래달리기": True, "제자리멀리뛰기": True, "상대악력": True,
    "반복점프": True,
    "3m표적돌아오기": False, "8자보행": False,   # 초 단위 = 작을수록 좋음
    "체지방률": False,                          # 체지방률은 높을수록 불리 → 나이 들수록 상승
}


def band_mid(b: str) -> float:
    """연령구간 문자열 → 중앙값.

    "19~24" → 21.5, "80+" → 100, "15"(성장기 1세 단위) → 15
    """
    b = str(b).replace("+", "~120")
    lo, sep, hi = b.partition("~")
    lo = float(lo)
    if not sep:
        return lo                       # 1세 단위 구간
    return (lo + float(hi)) / 2


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


# 한 항목이 체력나이를 기준점에서 이만큼(세)보다 더 끌어당기지 못한다.
# "20세인데 유연성 하나 낮아서 체력나이 50세" 같은 결과를 막는다(기획안 개정 4절).
STABILIZE_LIMIT = 15.0
# 환산나이가 기준점보다 이만큼(세) 이상 나쁘면 '집중 개선 영역'으로 따로 표시한다.
FOCUS_GAP = 10.0


def u_shaped_age(d, age_gbn, sex, item, value, ideal=None) -> float | None:
    """BMI·체지방률처럼 U자형(적정치에서 멀수록 나쁨) 항목의 환산나이.

    적정치로부터의 편차 절댓값을 그 성별·연령군 p50 편차 곡선에 대조한다.
    """
    sub = d[(d["연령군"] == age_gbn) & (d["성별"] == sex) & (d["항목"] == item)]
    sub = sub.sort_values("age_mid")
    if len(sub) < MIN_BANDS:
        return None
    if ideal is None:
        ideal = float(sub["p50"].median()) if (age_gbn == GROWTH or item != "BMI") else BMI_IDEAL
    dev = (sub["p50"] - ideal).abs().to_numpy()
    ages = sub["age_mid"].to_numpy()
    order = np.argsort(dev)
    return float(np.interp(abs(value - ideal), dev[order], ages[order]))


def aggregate_age(parts: dict[str, float], age_gbn: str, age=None) -> dict:
    """항목별 환산나이(dict) → 안정화된 체력나이 + 편차 + 집중 개선 영역.

    한 항목이 기준점(실제 나이, 없으면 중앙값)에서 ±STABILIZE_LIMIT 를 넘겨
    체력나이를 끌어당기지 못하게 한다. 근거 없는 가중치는 두지 않는다.
    """
    if not parts:
        return {"체력나이": None, "신뢰구간": None, "항목별": {}, "집중개선영역": []}

    raw = list(parts.values())
    anchor = float(age) if age is not None else float(np.median(raw))
    clamped = [float(np.clip(v, anchor - STABILIZE_LIMIT, anchor + STABILIZE_LIMIT)) for v in raw]
    body_age = float(np.mean(clamped))
    if age is not None:
        body_age = float(np.clip(body_age, age - STABILIZE_LIMIT, age + STABILIZE_LIMIT))

    focus = [
        k for k, v in parts.items()
        if (anchor - v if age_gbn == GROWTH else v - anchor) >= FOCUS_GAP
    ]
    return {
        "체력나이": round(body_age, 1),
        "신뢰구간": round(float(np.std(raw)) / max(len(raw) ** 0.5, 1), 1),
        "항목별": {k: round(v, 1) for k, v in parts.items()},
        "집중개선영역": focus,
    }


def fitness_age(d, age_gbn, sex, *, flexibility=None, strength=None, bmi=None,
                body_fat=None, grip=None, endurance=None, age=None) -> dict:
    """자가 측정 항목 → 체력나이. 없는 항목은 평균에서 제외한다."""
    parts: dict[str, float] = {}

    if flexibility is not None:
        a = convert_age(d, age_gbn, sex, "앉아윗몸앞으로굽히기", flexibility)
        if a is not None:
            parts["유연성"] = a

    if strength is not None:
        label, item = POWER_ITEM.get(age_gbn, DEFAULT_POWER)
        a = convert_age(d, age_gbn, sex, item, strength)
        if a is not None:
            parts[label] = a

    if grip is not None:
        a = convert_age(d, age_gbn, sex, GRIP_ITEM, grip)
        if a is not None:
            parts["근력"] = a

    cardio = CARDIO_ITEM.get(age_gbn)
    if endurance is not None and cardio:
        a = convert_age(d, age_gbn, sex, cardio, endurance)
        if a is not None:
            parts["심폐지구력"] = a

    if bmi is not None:
        a = u_shaped_age(d, age_gbn, sex, "BMI", bmi)
        if a is not None:
            parts["체성분"] = a

    if body_fat is not None:
        # 체지방률은 높을수록 불리하고 나이 들수록 오르는 단조 항목 → 곡선에 직접 대조한다.
        a = convert_age(d, age_gbn, sex, "체지방률", body_fat)
        if a is not None:                        # 체지방률이 있으면 체성분을 이 값으로 대체(더 직접적)
            parts["체성분"] = a

    return aggregate_age(parts, age_gbn, age)


def peer_stats(d: pd.DataFrame, age_gbn: str, sex: str, age: float,
               item: str, value: float) -> dict | None:
    """같은 나이 또래 안에서 내 기록이 어디쯤인지.

    체력나이는 "몇 살 수준인가" 를 말해주지만, 성장기처럼 나이가 많을수록
    기록이 좋아지는 구간에서는 해석이 뒤집힌다. 백분위는 어느 연령군에서나
    같은 방향으로 읽히므로 함께 준다.

    반환값의 백분위는 100에 가까울수록 좋다.
    """
    sub = d[(d["연령군"] == age_gbn) & (d["성별"] == sex) & (d["항목"] == item)]
    if sub.empty:
        return None
    row = sub.iloc[(sub["age_mid"] - age).abs().to_numpy().argmin()]

    xs = np.array([float(row[f"p{p}"]) for p in PCTS])
    ys = np.array(PCTS, dtype=float)
    order = np.argsort(xs)
    pct = float(np.interp(value, xs[order], ys[order]))
    if not HIGHER_IS_BETTER.get(item, True):
        pct = 100 - pct                       # 초 단위 항목은 작을수록 좋다

    return {
        "항목": item,
        "내기록": round(float(value), 1),
        "또래중앙값": round(float(row["p50"]), 1),
        "백분위": round(pct, 1),
        "표본수": int(row["n"]),
        "비교구간": str(row["연령구간"]),
    }


def peer_report(d: pd.DataFrame, age_gbn: str, sex: str, age: float, *,
                flexibility=None, strength=None, bmi=None,
                grip=None, endurance=None) -> dict:
    """측정한 항목별로 또래 비교를 붙인다."""
    out = {}
    if flexibility is not None:
        r = peer_stats(d, age_gbn, sex, age, "앉아윗몸앞으로굽히기", flexibility)
        if r:
            out["유연성"] = r
    if strength is not None:
        label, item = POWER_ITEM.get(age_gbn, DEFAULT_POWER)
        r = peer_stats(d, age_gbn, sex, age, item, strength)
        if r:
            out[label] = r
    if grip is not None:
        r = peer_stats(d, age_gbn, sex, age, GRIP_ITEM, grip)
        if r:
            out["근력"] = r
    cardio = CARDIO_ITEM.get(age_gbn)
    if endurance is not None and cardio:
        r = peer_stats(d, age_gbn, sex, age, cardio, endurance)
        if r:
            out["심폐지구력"] = r
    if bmi is not None:
        # BMI 는 U자형이라 "상위 몇 %" 가 성립하지 않는다.
        # 백분위 없이 또래 중앙값과의 차이만 준다.
        r = peer_stats(d, age_gbn, sex, age, "BMI", bmi)
        if r:
            r.pop("백분위", None)
            r["또래대비"] = round(r["내기록"] - r["또래중앙값"], 1)
            out["체성분"] = r
    return out


# 운동 기록 반영 (I3)
#
# 운동을 했다고 체력나이를 다시 "산출" 할 근거는 공개 데이터에 없다.
# 그래서 마지막 측정을 기준으로 두고, 운동한 날 수만큼 체력나이를 조금씩
# 당기되 **그 측정의 편차(신뢰구간) 안에서만** 움직인다.
#   - 항목별 환산나이는 측정값 그대로 둔다 (측정한 적 없는 값을 만들지 않는다)
#   - 측정으로 확인되지 않은 변화를 사실처럼 말하지 않는다
#   - 다시 재면 진짜 값으로 덮인다
ACTIVITY_STEP = 0.2          # 그 요인을 운동한 하루당 당기는 폭(세)


def activity_adjusted(항목별: dict, 신뢰구간, 활동: dict,
                      age_gbn: str, age=None) -> dict:
    """마지막 측정 + 최근 운동 기록 → 반영된 추정 체력나이.

    활동은 {요인: 그 요인을 운동한 날 수}. 항목별에 없는 요인은 무시한다.

    한 요인의 폭은 편차를 넘지 않고, 그 폭은 항목 수로 나눠 체력나이에 실린다
    (체력나이가 항목별 평균이므로 한 항목이 통째로 끌고 가지 않는다).
    다 합쳐도 편차를 넘지 않는다.
    """
    base = aggregate_age(항목별 or {}, age_gbn, age)
    if base["체력나이"] is None:
        return base

    ci = float(신뢰구간) if 신뢰구간 is not None else float(base["신뢰구간"] or 0)
    ci = max(0.0, ci)
    n = max(len(항목별), 1)

    반영: dict[str, float] = {}
    총 = 0.0
    for 요인, 일수 in (활동 or {}).items():
        if 요인 not in 항목별:
            continue
        try:
            cnt = int(일수)
        except (TypeError, ValueError):
            continue
        폭 = min(cnt * ACTIVITY_STEP, ci)
        if 폭 <= 0:
            continue
        반영[요인] = round(폭, 2)
        총 += 폭

    # 요인별 상한이 이미 있으니 총합도 편차를 못 넘지만, 규칙이 바뀌어도
    # 편차 밖으로 나가지 않게 한 번 더 막는다.
    당김 = min(총 / n, ci)
    # 성장기는 방향이 반대다 — 숫자가 오를수록 좋다
    나이 = base["체력나이"] + 당김 if age_gbn == GROWTH else base["체력나이"] - 당김

    out = dict(base)
    out["체력나이"] = round(나이, 1)
    out["기준나이"] = base["체력나이"]      # 운동 반영 전 — 어느 쪽으로 움직였는지 이걸로 판단한다
    out["활동반영"] = 반영
    out["당김"] = round(당김, 1)
    out["한도"] = round(ci, 1)
    return out


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
