"""
처방 추천

국민체력100이 실제로 내린 처방(pres_note, 296만 건)을 근거로,
사용자와 프로필이 유사한 집단에서 많이 처방된 운동을 반환한다.

우리가 "근력이 부족하면 이 운동" 같은 기준을 만들지 않는다.
공단이 실제로 처방한 기록을 집계할 뿐이다. 심사에서 근거를 물으면 그대로 답할 수 있다.

입력: data/processed/ 또는 data/sample/ 의 exercise_freq.csv  (backend/build_distribution.py 산출물)

사용법:
    python backend/prescription.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

try:                                     # 저장소 루트에서 실행할 때
    from backend.paths import find_data
except ImportError:                      # backend/ 안에서 직접 실행할 때
    from paths import find_data

PHASES = ("준비운동", "본운동", "정리운동")

# 목적 → 우선 보강할 체력요인 (기획안 3절)
PURPOSE_FACTORS = {
    "다이어트": ["심폐지구력", "근지구력"],
    "기초 체력 증진": ["근력", "유연성", "심폐지구력"],
    "재활 및 기능 회복": ["평형성", "근력"],
    "수험생 체력 증진": ["유연성", "심폐지구력"],
    "유연성 강화": ["유연성"],
}

# 운동명 키워드 → 체력요인 (동영상 API의 ftns_fctr_nm 분류와 맞춤)
FACTOR_KEYWORDS = {
    "유연성": ["스트레칭", "요가", "필라테스", "굽히기"],
    "근력": ["팔굽혀", "일어서기", "버티기", "들어올리기", "덤벨", "맨몸운동",
             "윗몸", "들기", "스쿼트", "런지"],
    "심폐지구력": ["걷기", "달리기", "조깅", "자전거", "트레드밀", "수영",
                  "줄넘기", "계단", "등산", "에어로빅"],
    "평형성": ["한 발", "외발", "균형", "제자리", "보행"],
}

# 집에서 못 하는 운동 (장비·시설 필요)
EQUIPMENT = ["트레드밀", "자전거", "덤벨", "헬스", "수영", "짐볼", "사다리", "밴드"]


def classify(name: str) -> str:
    """운동명 → 체력요인. 매칭 안 되면 '기타'."""
    for factor, keys in FACTOR_KEYWORDS.items():
        if any(k in name for k in keys):
            return factor
    return "기타"


def load_freq(path: Path | None = None) -> pd.DataFrame:
    df = pd.read_csv(path or find_data("exercise_freq.csv"))
    df["체력요인"] = df["운동명"].map(classify)
    return df


def recommend(
    freq: pd.DataFrame,
    *,
    age_gbn: str,
    sex: str,
    purpose: str | None = None,
    weak_factor: str | None = None,
    home_only: bool = True,
    top_n: int = 5,
) -> dict[str, pd.DataFrame]:
    """단계별 추천 운동을 반환한다.

    weak_factor : 약점 지목 결과(fitness_age.weakest_link)를 넣으면 최우선 반영
    purpose     : 목적 6종 중 하나. weak_factor 다음 순위
    home_only   : 장비가 필요한 운동 제외 (집에서 하는 루틴용)
    """
    sub = freq[(freq["연령군"] == age_gbn) & (freq["성별"] == sex)].copy()
    if sub.empty:
        return {p: pd.DataFrame() for p in PHASES}

    if home_only:
        sub = sub[~sub["운동명"].str.contains("|".join(EQUIPMENT), na=False)]

    # 가중치: 약점 요인 3배, 목적 요인 2배
    weights: dict[str, float] = {}
    if weak_factor:
        weights[weak_factor] = 3.0
    for f in PURPOSE_FACTORS.get(purpose or "", []):
        weights.setdefault(f, 2.0)
    sub["점수"] = sub["빈도"] * sub["체력요인"].map(lambda f: weights.get(f, 1.0))

    out = {}
    for phase in PHASES:
        p = sub[sub["단계"] == phase].nlargest(top_n, "점수")
        out[phase] = p[["운동명", "체력요인", "빈도", "비율%", "점수"]].reset_index(drop=True)
    return out


def build_routine(rec: dict[str, pd.DataFrame]) -> list[dict]:
    """준비 → 본 → 정리 순서의 루틴 한 벌로 조립한다."""
    routine = []
    for phase, n_take in (("준비운동", 2), ("본운동", 3), ("정리운동", 2)):
        df = rec.get(phase)
        if df is None or df.empty:
            continue
        for _, r in df.head(n_take).iterrows():
            routine.append({"단계": phase, "운동명": r["운동명"], "체력요인": r["체력요인"]})
    return routine


if __name__ == "__main__":
    freq = load_freq()

    for label, kw in [
        ("성인 남성 · 기초 체력 증진 · 약점 근력",
         dict(age_gbn="성인", sex="M", purpose="기초 체력 증진", weak_factor="근력")),
        ("어르신 여성 · 재활 및 기능 회복 · 약점 평형성",
         dict(age_gbn="어르신", sex="F", purpose="재활 및 기능 회복", weak_factor="평형성")),
    ]:
        print(f"=== {label} ===")
        for i, step in enumerate(build_routine(recommend(freq, **kw)), 1):
            print(f"{i}. [{step['단계']}] {step['운동명']}  ({step['체력요인']})")
        print()
