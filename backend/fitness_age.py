"""
체력나이 산출

data/processed/ (없으면 data/sample/) 의 fitness_distribution.csv 의 연령구간별 중앙값(p50)을 이용해
사용자 측정값이 어느 연령대 수준인지 선형보간으로 역산한다.
나이에 따라 거의 움직이지 않는 항목(성인 유연성 등)은 곡선을 거꾸로 읽을 수 없어 또래 안 순위로 나이를 매기고(rank_age),
BMI 는 정상 범위면 실제 나이 그대로, 벗어난 만큼만 나이를 더한다(bmi_age).

국민체력100은 등급(1~6)만 제공하고 체력나이는 제공하지 않는다.
공개 측정결과 데이터의 성별·연령대별 분포에서 우리가 직접 산출하는 지표다.

사용법:
    python backend/fitness_age.py
"""
from __future__ import annotations

import math
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

try:                                     # 저장소 루트에서 실행할 때
    from backend.paths import find_data
except ImportError:                      # backend/ 안에서 직접 실행할 때
    from paths import find_data


def _given(v) -> bool:
    """사용자가 실제로 잰 값인지 — None 은 물론, 어쩌다 섞여 들어온 NaN 도 '안 잰 것'으로 본다.

    프런트는 빈 입력칸을 null 로 보내지만(placeholder 는 절대 값으로 쓰지 않는다),
    그래도 이 함수를 거치지 않은 값이 NaN 으로 들어오면 아래 보간 계산이 조용히
    NaN 을 퍼뜨릴 수 있다 — 있지도 않은 측정을 있는 것처럼 계산하지 않기 위한
    마지막 방어선이다.
    """
    return v is not None and not (isinstance(v, float) and math.isnan(v))

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
#   심폐지구력 성인·성장기는 왕복오래달리기(회), 어르신은 2분제자리걷기.
#             성장기는 **또래 백분위만** 낸다 — 11~12세는 15m, 13세부터 20m 로 재서 나이별 중앙값이
#             12세 52회 → 13세 36회로 끊기고 그 뒤로는 평평하다(여 22회 안팎). 나이로 거꾸로 읽을 수 없는 곡선이다.
GRIP_ITEM = "상대악력"
CARDIO_ITEM = {"성인": "왕복오래달리기", "어르신": "2분제자리걷기", "성장기": "왕복오래달리기"}
CARDIO_NO_AGE = {"성장기"}          # 심폐를 환산나이로 바꾸지 않는 연령군 (또래비교에는 들어간다)

# 선택 항목(운동체력) — 잰 사람만 넣는다. 입력 이름 → {연령군: (축 이름, 분포의 항목)}.
# 축 이름은 국민체력100 공식 분류다: 성인 순발력 = 제자리 멀리뛰기(cm) · 민첩성 = 10M 4회 왕복달리기(초),
# 어르신 평형성 = 의자에 앉아 3M 표적 돌아오기(초) · 협응력 = 8자보행(초). 넷 다 분포에 1.9만~4.7만 건이 있고
# 나이에 따라 한쪽으로만 움직여 환산나이로 읽을 수 있다. 성장기의 순발력은 strength(제자리멀리뛰기)가 맡는다.
EXTRA_ITEMS = {
    "long_jump":   {"성인": ("순발력", "제자리멀리뛰기")},
    "shuttle_10m": {"성인": ("민첩성", "10m왕복달리기")},
    "target_3m":   {"어르신": ("평형성", "3m표적돌아오기")},
    "figure8":     {"어르신": ("협응력", "8자보행")},
}


def extra_items(age_gbn: str, extras: dict | None):
    """이 연령군에서 쓰는 선택 항목만 (축 이름, 분포 항목, 값) 으로 — 잰 것만."""
    for key, by_group in EXTRA_ITEMS.items():
        v = (extras or {}).get(key)
        if _given(v) and age_gbn in by_group:
            label, item = by_group[age_gbn]
            yield label, item, v


# 성장기 근지구력 — 공식 항목(윗몸말아올리기 item_f009 · 반복점프 item_f010)이 아직 분포 파일에 없다.
# 대신 국민체력100 인증기준의 등급 기준 값을 쓴다 (문화체육관광부고시 제2025-27호 「체력인증의 등급별 기준과
# 절차에 관한 규정」 별표2·별표5, https://nfa.kspo.or.kr 인증기준 표와 같다). 같은 고시 제6조에 따라
# 1·2·3등급은 또래 상위 30·50·70% — 곧 성별·나이별 백분위 70·50·30 의 값 세 개다.
#   만 11~12세(유소년)  윗몸말아올리기(회) — 3초에 한 번 울리는 신호에 맞춰, 박자를 놓칠 때까지
#   만 13~18세(청소년)  반복점프(회) — 30cm 장애물을 두 발로 30초 동안 좌우로 넘은 횟수
#                       (공식은 윗몸말아올리기와 택1. 집에서 혼자 재기 쉬운 쪽을 골랐다)
# 값은 (1등급, 2등급, 3등급) = (P70, P50, P30). 원자료로 분포를 만들면 이 표는 분포로 바꾼다.
GROWTH_ENDURANCE = {
    "윗몸말아올리기": {
        "M": {11: (36, 26, 19), 12: (35, 27, 19)},
        "F": {11: (36, 26, 18), 12: (35, 27, 19)},
    },
    "반복점프": {
        "M": {13: (44, 39, 33), 14: (48, 42, 36), 15: (50, 44, 38),
              16: (50, 45, 39), 17: (50, 44, 38), 18: (52, 46, 40)},
        "F": {13: (31, 27, 22), 14: (34, 28, 23), 15: (35, 29, 24),
              16: (34, 28, 22), 17: (33, 27, 21), 18: (36, 29, 23)},
    },
}
GROWTH_ENDURANCE_SOURCE = "국민체력100 인증기준 (문체부고시 제2025-27호)"


def growth_endurance_item(age: float) -> str:
    """성장기 근지구력으로 재는 항목 — 만 12세까지 윗몸말아올리기, 13세부터 반복점프."""
    return "윗몸말아올리기" if age < 13 else "반복점프"


def growth_endurance_stats(sex: str, age: float, value: float) -> dict | None:
    """성장기 근지구력 기록을 공식 등급 기준에 견준다 → 등급과 또래 백분위(어림).

    기준이 세 점(P30·P50·P70)뿐이라 그 사이는 직선으로 잇고, 양 끝은 이웃 구간의 기울기로 늘려
    5~95 안에서 자른다. 분포에서 바로 읽는 다른 항목과 달리 어림값이라 '어림' 을 함께 준다.
    """
    item = growth_endurance_item(age)
    by_age = GROWTH_ENDURANCE[item].get(sex)
    if not by_age:
        return None
    cuts = by_age.get(min(max(int(age), min(by_age)), max(by_age)))
    if not cuts:
        return None
    c1, c2, c3 = (float(c) for c in cuts)
    if value >= c2:
        pct = 50 + 20 * (value - c2) / max(c1 - c2, 1.0)
    else:
        pct = 50 - 20 * (c2 - value) / max(c2 - c3, 1.0)
    등급 = 1 if value >= c1 else 2 if value >= c2 else 3 if value >= c3 else None
    return {
        "항목": item,
        "내기록": round(float(value), 1),
        "또래중앙값": c2,                       # 2등급 기준 = 또래 상위 50%
        "백분위": round(float(np.clip(pct, 5, 95)), 1),
        "등급": 등급,
        "어림": True,
        "근거": GROWTH_ENDURANCE_SOURCE,
        "표본수": 0,                            # 표본에서 읽은 값이 아니다 — 종합 등수의 '몇 명 중' 에는 세지 않는다
        "비교구간": str(int(age)),
    }


# 성장기는 나이가 많을수록 기록이 좋아진다. 성인·어르신과 방향이 반대라
# "체력나이가 높다 = 나쁘다" 가 성립하지 않는다. 화면에서는 발달 수준으로 읽는다.
GROWTH = "성장기"

PCTS = (5, 10, 25, 50, 75, 90, 95)

# 항목별 방향: True = 값이 클수록 좋음(젊음)
HIGHER_IS_BETTER = {
    "교차윗몸일으키기": True, "앉아윗몸앞으로굽히기": True,
    "의자앉았다일어서기": True, "6분걷기": True, "2분제자리걷기": True,
    "왕복오래달리기": True, "제자리멀리뛰기": True, "상대악력": True,
    "3m표적돌아오기": False, "8자보행": False,   # 초 단위 = 작을수록 좋음
    "10m왕복달리기": False,                     # 민첩성(초). 지금은 쓰지 않지만 분포에는 있다
    "체지방률": False,                          # 체지방률은 높을수록 불리 → 나이 들수록 상승
}


# 끝이 열린 구간("80+")도 이웃 구간처럼 5세 폭(80~84)으로 본다. 예전에는 80~120 으로 보아 대표 나이가 100세였다 —
# 그러면 85세의 또래가 75~79세로 잡히고(100 보다 77 이 가깝다), 80대의 평균 기록이 100세로 읽힌다.
OPEN_BAND_SPAN = 4
# 끝이 열린 구간을 이어 갈 때의 상한(세)
OLDEST_AGE = 100.0


def band_mid(b: str) -> float:
    """연령구간 문자열 → 중앙값.

    "19~24" → 21.5, "80+" → 82 (80~84 로 본다), "15"(성장기 1세 단위) → 15
    """
    b = str(b)
    if b.endswith("+"):
        b = f"{b[:-1]}~{float(b[:-1]) + OPEN_BAND_SPAN}"
    lo, sep, hi = b.partition("~")
    lo = float(lo)
    if not sep:
        return lo                       # 1세 단위 구간
    return (lo + float(hi)) / 2


def load(path: Path | None = None, windows_path: Path | None = None) -> pd.DataFrame:
    """분포 표. 또래 비교용 좁은 창(fitness_peer_windows.csv)이 있으면 d.attrs["windows"] 에 같이 싣는다.

    좁은 창은 없어도 된다 — 없으면 또래 비교도 5세 구간으로 한다(지금까지와 같다).
    path 를 직접 준 호출(테스트 · 도구)은 windows_path 도 직접 줘야 싣는다: 남의 표에 이 저장소의 창을 붙이지 않는다.
    """
    d = pd.read_csv(path or find_data("fitness_distribution.csv"))
    d["age_mid"] = d["연령구간"].map(band_mid)
    try:
        wp = windows_path or (None if path else find_data("fitness_peer_windows.csv"))
    except FileNotFoundError:
        wp = None
    if wp:
        w = pd.read_csv(wp)
        d.attrs["windows"] = {(r["연령군"], r["성별"], int(r["나이"]), r["항목"]): r for r in w.to_dict("records")}
    return d


def _peer_row(d: pd.DataFrame, age_gbn: str, sex: str, age: float, item: str):
    """또래 비교에 쓸 한 줄 — 좁은 창이 있으면 그 나이의 창, 없으면 가장 가까운 5세 구간."""
    win = (d.attrs.get("windows") or {}).get((age_gbn, sex, int(age), item))
    if win:
        return win, str(win["구간"]), True
    sub = d[(d["연령군"] == age_gbn) & (d["성별"] == sex) & (d["항목"] == item)]
    if sub.empty:
        return None, None, False
    row = sub.iloc[(sub["age_mid"] - age).abs().to_numpy().argmin()]
    return row, str(row["연령구간"]), False


def convert_age(d: pd.DataFrame, age_gbn: str, sex: str, item: str, value: float) -> float | None:
    """측정값 → 환산 나이. 해당 성별·연령군의 p50 곡선에 선형보간한다."""
    sub = d[(d["연령군"] == age_gbn) & (d["성별"] == sex) & (d["항목"] == item)]
    sub = sub.sort_values("age_mid")
    if len(sub) < MIN_BANDS:
        return None
    ages, meds = sub["age_mid"].to_numpy(), sub["p50"].to_numpy()
    # 값이 클수록 좋으면 나이가 들수록 p50이 감소 → 보간을 위해 뒤집는다
    higher_better = HIGHER_IS_BETTER.get(item, True)
    # 끝이 열린 구간("80+")의 중앙값보다 못한 기록은 끝값에 묶지 않고 마지막 두 구간의 기울기로 이어 간다.
    # 묶어 두면 80대의 평균 기록과 아주 나쁜 기록이 같은 나이로 읽힌다. 곡선이 끝에서도 나이 방향으로 움직일 때만.
    if str(sub["연령구간"].iloc[-1]).endswith("+"):
        worse = value < meds[-1] if higher_better else value > meds[-1]
        ages_on = meds[-1] < meds[-2] if higher_better else meds[-1] > meds[-2]
        if worse and ages_on:
            slope = (ages[-1] - ages[-2]) / (meds[-1] - meds[-2])
            return float(min(OLDEST_AGE, ages[-1] + (value - meds[-1]) * slope))
    x, y = (meds[::-1], ages[::-1]) if higher_better else (meds, ages)
    order = np.argsort(x)
    return float(np.interp(value, x[order], y[order]))


# 한 항목이 체력나이를 기준점에서 이만큼(세)보다 더 끌어당기지 못한다.
# "20세인데 유연성 하나 낮아서 체력나이 50세" 같은 결과를 막는다(기획안 개정 4절).
STABILIZE_LIMIT = 15.0
# 환산나이가 기준점보다 이만큼(세) 이상 나쁘면 '집중 개선 영역'으로 따로 표시한다.
FOCUS_GAP = 10.0


# 나이에 따라 거의 움직이지 않는 항목 — p50 곡선을 거꾸로 읽어 '몇 살 수준' 을 낼 수 없다.
# (구간 중앙값의 최대 − 최소) ÷ (같은 구간 안 IQR 의 중앙값) 이 이보다 작으면 또래 안 순위로 나이를 매긴다(rank_age).
# 2026-09-22 점검: 성인 유연성 여 0.17 · 남 0.16(중앙값이 해마다 0.006cm · 0.036cm, 오르내림이 다섯 번 뒤집힌다),
# 성장기 남 체지방률 0.10. 그 밖에 쓰는 항목은 0.29 이상이다. 예전에는 곡선을 그대로 읽어
# 34세 여성의 유연성이 12cm 면 42세, 16cm 로 늘면 47.7세 — 좋아졌는데 늙게 나왔다.
AGE_SIGNAL_MIN = 0.2

# BMI 정상 범위 — 대한비만학회 기준(18.5 이상 23 미만). 이 안이면 체성분은 실제 나이 그대로다(bmi_age).
BMI_NORMAL = (18.5, 23.0)
# 정상 범위를 벗어나면 단계 하나에 5세씩 더한다(사이는 직선으로). (BMI, 더하는 나이)
#   위쪽 — 대한비만학회: 비만 전단계 23~24.9 → 1단계 25 → 2단계 30 → 3단계 35
#   아래쪽 — WHO 저체중 단계: 경도 17~18.4 → 중등도 16~16.9 → 고도 16 미만
# BMI 는 체력을 재는 값이 아니라 건강 위험을 알리는 값이라, 다른 항목의 '순위 한 칸' 눈금(성인 약 25세)을 쓰지 않는다 —
# 그 눈금이면 45세 남성의 BMI 26 이 +15세(상한)가 된다. 단계로 끊으면 BMI 26 은 +6세다.
BMI_ADD_OVER = ((23.0, 0.0), (25.0, 5.0), (30.0, 10.0), (35.0, 15.0))
BMI_ADD_UNDER = ((15.0, 15.0), (16.0, 10.0), (17.0, 5.0), (18.5, 0.0))

_NORMAL = NormalDist()


def _curve(d: pd.DataFrame, age_gbn: str, sex: str, item: str) -> pd.DataFrame:
    """그 성별·연령군 · 항목의 연령구간별 줄 — 나이순."""
    sub = d[(d["연령군"] == age_gbn) & (d["성별"] == sex) & (d["항목"] == item)]
    return sub.sort_values("age_mid")


def age_signal(d: pd.DataFrame, age_gbn: str, sex: str, item: str) -> float | None:
    """중앙값이 나이에 따라 얼마나 움직이는가 — (구간 중앙값의 최대 − 최소) ÷ (구간 안 IQR 의 중앙값)."""
    sub = _curve(d, age_gbn, sex, item)
    if len(sub) < MIN_BANDS:
        return None
    iqr = float(np.median(sub["p75"] - sub["p25"]))
    return float(sub["p50"].max() - sub["p50"].min()) / iqr if iqr > 0 else None


def years_per_sd(d: pd.DataFrame, age_gbn: str, sex: str) -> float | None:
    """또래 안 순위 한 칸(표준편차 1)이 몇 살인지 — 그 연령군의 기본 항목(누구나 재는 근지구력 · 순발력) 곡선에서 잰다.

    (구간 안 표준편차의 중앙값) ÷ (1년에 중앙값이 움직이는 양). 성인 교차윗몸일으키기 여 25.0세 · 남 23.3세,
    어르신 의자앉았다일어서기 여 14.9세 · 남 12.0세. 순위로 나이를 매기는 항목도 같은 사람의 이 항목과 같은 눈금을 쓴다.
    """
    _, item = POWER_ITEM.get(age_gbn, DEFAULT_POWER)
    sub = _curve(d, age_gbn, sex, item)
    if len(sub) < MIN_BANDS:
        return None
    slope = float(np.polyfit(sub["age_mid"].to_numpy(), sub["p50"].to_numpy(), 1)[0])
    sd = float(np.median(sub["표준편차"]))
    return sd / abs(slope) if slope and sd > 0 else None


def _age_bounds(d: pd.DataFrame, age_gbn: str, sex: str, item: str, age: float) -> tuple[float, float]:
    """순위 · 정상 범위로 매긴 나이가 머무를 범위 — 실제 나이 ±STABILIZE_LIMIT, 그리고 그 연령군 구간의 양 끝.

    곡선으로 읽는 항목(convert_age)과 같은 끝을 쓴다: 성인은 가장 나이 든 구간의 대표 나이, 끝이 열린 구간(80+)은 OLDEST_AGE.
    실제 나이는 언제나 범위 안에 둔다 — 구간 끝에 걸려 좋은 기록이 늙게, 나쁜 기록이 어리게 읽히지 않게.
    """
    sub = _curve(d, age_gbn, sex, item)
    lo_band = float(sub["age_mid"].min())
    hi_band = OLDEST_AGE if str(sub["연령구간"].iloc[-1]).endswith("+") else float(sub["age_mid"].max())
    lo = min(age, max(lo_band, age - STABILIZE_LIMIT))
    hi = max(age, min(hi_band, age + STABILIZE_LIMIT))
    return lo, hi


def rank_age(d: pd.DataFrame, age_gbn: str, sex: str, age, item: str, value: float) -> float | None:
    """또래 안 순위 → 나이. 나이에 따라 거의 움직이지 않는 항목(AGE_SIGNAL_MIN)에 쓴다.

    또래 중앙값이면 실제 나이 그대로, 또래보다 좋으면 어리게(성장기는 앞서게) — 좋아지면 언제나 좋은 쪽으로 움직인다.
    백분위를 2.5~97.5 로 자른 뒤 정규분포의 몇 칸(표준편차)인지로 바꾸고, 한 칸에 years_per_sd 만큼 움직인다.
    """
    if not _given(age):
        return None                              # 실제 나이가 없으면 또래를 정할 수 없다
    r = peer_stats(d, age_gbn, sex, float(age), item, value)
    rate = years_per_sd(d, age_gbn, sex)
    if r is None or rate is None or "백분위" not in r:
        return None
    z = _NORMAL.inv_cdf(min(max(r["백분위"], 2.5), 97.5) / 100)
    a = float(age) + z * rate if age_gbn == GROWTH else float(age) - z * rate
    lo, hi = _age_bounds(d, age_gbn, sex, item, float(age))
    return float(np.clip(a, lo, hi))


def item_age(d: pd.DataFrame, age_gbn: str, sex: str, item: str, value: float, age=None) -> float | None:
    """한 항목의 환산나이 — 나이에 따라 움직이는 항목은 p50 곡선으로(convert_age), 거의 안 움직이는 항목은 또래 순위로(rank_age)."""
    signal = age_signal(d, age_gbn, sex, item)
    if signal is not None and signal < AGE_SIGNAL_MIN:
        return rank_age(d, age_gbn, sex, age, item, value)
    return convert_age(d, age_gbn, sex, item, value)


def bmi_age(d: pd.DataFrame, age_gbn: str, sex: str, bmi: float, age=None) -> float | None:
    """BMI → 체성분 환산나이.

    BMI 는 U자형이고 성인 · 어르신의 BMI 중앙값은 나이에 따라 거의 움직이지 않아 곡선을 거꾸로 읽을 수 없다
    (예전 방식에서는 34세 여성의 BMI 22 가 37세, 23.5 가 27세로 나왔다). 그래서 정상 범위(BMI_NORMAL) 안이면
    실제 나이 그대로 두고, 벗어나면 비만 · 저체중 단계만큼 나이를 더한다(BMI_ADD_OVER · BMI_ADD_UNDER).
    정상 범위 안에서 '더 좋은' BMI 는 없으므로 어리게 만들지는 않는다.
    성장기는 BMI 로 발달 수준을 말할 수 없어 나이로 바꾸지 않는다(또래비교에는 그대로 나온다).
    """
    if not _given(bmi) or not _given(age) or age_gbn == GROWTH:
        return None
    lo, hi = BMI_NORMAL
    if lo <= bmi < hi:
        return float(age)
    steps = BMI_ADD_OVER if bmi >= hi else BMI_ADD_UNDER
    add = float(np.interp(bmi, [b for b, _ in steps], [y for _, y in steps]))   # 양 끝 밖은 끝값(15세)
    return float(min(float(age) + add, _age_bounds(d, age_gbn, sex, "BMI", float(age))[1]))


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
                body_fat=None, grip=None, endurance=None, age=None, extras=None) -> dict:
    """자가 측정 항목 → 체력나이. 없는 항목은 평균에서 제외한다."""
    parts: dict[str, float] = {}

    if _given(flexibility):
        a = item_age(d, age_gbn, sex, "앉아윗몸앞으로굽히기", flexibility, age)
        if a is not None:
            parts["유연성"] = a

    if _given(strength):
        label, item = POWER_ITEM.get(age_gbn, DEFAULT_POWER)
        a = item_age(d, age_gbn, sex, item, strength, age)
        if a is not None:
            parts[label] = a

    if _given(grip):
        a = item_age(d, age_gbn, sex, GRIP_ITEM, grip, age)
        if a is not None:
            parts["근력"] = a

    cardio = CARDIO_ITEM.get(age_gbn)
    if _given(endurance) and cardio and age_gbn not in CARDIO_NO_AGE:
        a = item_age(d, age_gbn, sex, cardio, endurance, age)
        if a is not None:
            parts["심폐지구력"] = a

    for label, item, v in extra_items(age_gbn, extras):
        a = item_age(d, age_gbn, sex, item, v, age)
        if a is not None:
            parts[label] = a

    if _given(bmi):
        a = bmi_age(d, age_gbn, sex, bmi, age)
        if a is not None:
            parts["체성분"] = a

    if _given(body_fat):
        # 체지방률은 높을수록 불리하고 나이 들수록 오르는 단조 항목 → 곡선에 직접 대조한다(곡선이 평평하면 또래 순위로).
        a = item_age(d, age_gbn, sex, "체지방률", body_fat, age)
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
    row, band, narrow = _peer_row(d, age_gbn, sex, age, item)
    if row is None:
        return None

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
        "비교구간": band,                 # 좁은 창이면 "20~22", 아니면 5세 구간 "19~24"
        "좁은창": narrow,
    }


def peer_report(d: pd.DataFrame, age_gbn: str, sex: str, age: float, *,
                flexibility=None, strength=None, bmi=None,
                grip=None, endurance=None, muscle_endurance=None, extras=None) -> dict:
    """측정한 항목별로 또래 비교를 붙인다.

    각 인자가 실제로 온 것(_given)일 때만 그 항목의 또래비교를 만든다 —
    안 잰 항목은 이유 없이 상위/하위 %·또래 중앙값이 나오면 안 된다.
    """
    out = {}
    if _given(flexibility):
        r = peer_stats(d, age_gbn, sex, age, "앉아윗몸앞으로굽히기", flexibility)
        if r:
            out["유연성"] = r
    if _given(strength):
        label, item = POWER_ITEM.get(age_gbn, DEFAULT_POWER)
        r = peer_stats(d, age_gbn, sex, age, item, strength)
        if r:
            out[label] = r
    if _given(grip):
        r = peer_stats(d, age_gbn, sex, age, GRIP_ITEM, grip)
        if r:
            out["근력"] = r
    cardio = CARDIO_ITEM.get(age_gbn)
    if _given(endurance) and cardio:
        r = peer_stats(d, age_gbn, sex, age, cardio, endurance)
        if r:
            out["심폐지구력"] = r
    if _given(muscle_endurance) and age_gbn == GROWTH:      # 성인·어르신의 근지구력은 strength 가 맡는다
        r = growth_endurance_stats(sex, age, muscle_endurance)
        if r:
            out["근지구력"] = r
    for label, item, v in extra_items(age_gbn, extras):
        r = peer_stats(d, age_gbn, sex, age, item, v)
        if r:
            out[label] = r
    if _given(bmi):
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


def body_part(d, age_gbn: str, sex: str, *, 키=None, 몸무게=None, 체지방률=None, age=None):
    """그날 잰 몸무게·체지방률 → 체성분 환산나이 (K1).

    이건 추정이 아니라 **그날 실제로 잰 값**이라 그대로 항목별에 넣는다.
    체지방률이 있으면 그쪽이 더 직접적이라 우선한다. 측정 때와 같은 함수(item_age · bmi_age)로 환산한다.
    """
    if 체지방률 is not None:
        a = item_age(d, age_gbn, sex, "체지방률", 체지방률, age)
        if a is not None:
            return a
    if 키 and 몸무게:
        h = float(키) / 100
        if h > 0:
            a = bmi_age(d, age_gbn, sex, float(몸무게) / (h * h), age)
            if a is not None:
                return a
    return None


def activity_adjusted(항목별: dict, 신뢰구간, 활동: dict,
                      age_gbn: str, age=None, 체성분=None) -> dict:
    """마지막 측정 + 최근 운동 기록 → 반영된 추정 체력나이.

    활동은 {요인: 그 요인을 운동한 날 수}. 항목별에 없는 요인은 무시한다.

    한 요인의 폭은 편차를 넘지 않고, 그 폭은 항목 수로 나눠 체력나이에 실린다
    (체력나이가 항목별 평균이므로 한 항목이 통째로 끌고 가지 않는다).
    다 합쳐도 편차를 넘지 않는다.

    체성분이 들어오면(그날 몸무게·체지방률을 쟀으면) 그 항목만 **실제 값**으로
    갈아 끼운다. 추정이 아니라 잰 값이라 편차 제한을 걸지 않는다.
    """
    항목별 = dict(항목별 or {})
    잰것 = None
    if 체성분 is not None:
        잰것 = round(float(체성분), 1)
        항목별["체성분"] = 잰것

    base = aggregate_age(항목별, age_gbn, age)
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
    if 잰것 is not None:
        out["잰체성분"] = 잰것        # 이 항목은 추정이 아니라 그날 잰 값이다
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
