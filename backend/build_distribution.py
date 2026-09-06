"""
분포 테이블 · 처방 빈도 생성

수집한 측정결과에서
  1) 연령군 × 성별 × 연령구간 × 항목별 백분위 분포  → fitness_distribution.csv
  2) 연령군 × 성별 × 단계별 운동처방 빈도            → exercise_freq.csv
를 만든다.

사용법:
    python backend/collect_measurements.py   # 먼저 수집
    python backend/build_distribution.py
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

try:                                     # 저장소 루트에서 실행할 때
    from backend.paths import ROOT
except ImportError:                      # backend/ 안에서 직접 실행할 때
    from paths import ROOT

RAW = ROOT / "data/raw/measurements.parquet"
OUT = ROOT / "data/processed"

# 4-6절 판독 결과
ITEMS = {
    "item_f001": "신장", "item_f002": "체중", "item_f003": "체지방률",
    "item_f007": "악력(좌)", "item_f008": "악력(우)",
    "item_f012": "앉아윗몸앞으로굽히기", "item_f018": "BMI",
    "item_f019": "교차윗몸일으키기", "item_f020": "반복점프",
    "item_f021": "왕복오래달리기", "item_f022": "제자리멀리뛰기",
    "item_f023": "의자앉았다일어서기", "item_f024": "6분걷기",
    "item_f025": "2분제자리걷기", "item_f026": "3m표적돌아오기",
    "item_f027": "8자보행", "item_f028": "상대악력",
}

MIN_N = 30          # 셀당 최소 표본
WINSOR = 0.005      # 상하위 0.5% 절단

PHASES = ("준비운동", "본운동", "정리운동")
# 블록 구분자는 " / " (공백 포함). 운동명 안의 "/"(등/어깨 뒤쪽 스트레칭)를 자르면 안 된다.
BLOCK_SEP = re.compile(r"\s+/\s+")
PREFIX = re.compile(r"^\s*(준비운동|본운동|정리운동)\s*[:：]\s*")


def parse_note(note) -> dict[str, list[str]]:
    """pres_note 한 건을 단계별 운동명 리스트로 분해한다."""
    out = {p: [] for p in PHASES}
    if not isinstance(note, str) or not note.strip():
        return out
    for block in BLOCK_SEP.split(note):
        if not block.strip():
            continue
        m = PREFIX.match(block)
        phase, body = (m.group(1), block[m.end():]) if m else ("본운동", block)
        names = [re.sub(r"\s+", " ", x).strip() for x in body.split(",")]
        out[phase].extend([n for n in names if n])
    return out


def age_band(row) -> str | None:
    """연령구간을 나눈다.

    성인·어르신은 국민체력100 공식 구간(5세 단위)을 그대로 쓴다.

    성장기(11~18세)만 **1세 단위**로 나눈다. 5세 단위로 묶으면 청소년 구간이
    `10~14`·`15~19` 둘뿐이라 체력나이 역산이 양 끝값에 붙어버려 누구나 같은
    값이 나온다. 원본에 age_degree 가 1세 단위로 들어 있고 나이×성별당 표본이
    2,000건을 넘으므로 잘게 나눠도 안정적이다.

    유소년(11~12)과 청소년(13~18)은 성장 곡선이 이어지므로 `성장기` 하나로
    합친다. 이렇게 해야 8구간이 되어 보간이 의미를 갖는다.
    """
    a, g = row["age"], row.get("age_gbn")
    if pd.isna(a):
        return None
    a = int(a)
    if g == "성인":
        if a < 19 or a >= 65:
            return None
        for lo, hi in [(19,24),(25,29),(30,34),(35,39),(40,44),
                       (45,49),(50,54),(55,59),(60,64)]:
            if lo <= a <= hi:
                return f"{lo}~{hi}"
        return None
    if g == "어르신":
        for lo, hi in [(65,69),(70,74),(75,79),(80,120)]:
            if lo <= a <= hi:
                return f"{lo}~{hi}" if hi < 120 else "80+"
        return None
    if g in ("청소년", "유소년"):
        return str(a) if 11 <= a <= 18 else None
    return None                                  # 유아기는 age_degree 가 개월 수라 제외


def merge_gbn(g: str) -> str:
    """유소년(11~12)과 청소년(13~18)을 하나의 성장 곡선으로 합친다."""
    return "성장기" if g in ("청소년", "유소년") else g


def load_raw() -> pd.DataFrame:
    if RAW.exists():
        return pd.read_parquet(RAW)
    csv = RAW.with_suffix(".csv")
    if csv.exists():
        return pd.read_csv(csv)
    raise SystemExit(f"{RAW} 가 없습니다. backend/collect_measurements.py 를 먼저 실행하세요.")


def main() -> None:
    df = load_raw()
    print(f"표본 {len(df):,}행")

    df["age"] = pd.to_numeric(df.get("age_degree"), errors="coerce")
    for c in ITEMS:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
            lo, hi = df[c].quantile([WINSOR, 1 - WINSOR])
            df[c] = df[c].clip(lo, hi)          # 이상치 윈저화
    df["연령구간"] = df.apply(age_band, axis=1)
    df["age_gbn"] = df["age_gbn"].map(merge_gbn)

    OUT.mkdir(parents=True, exist_ok=True)

    # --- 1) 분포 ---
    recs = []
    for (g, sex, band), sub in df.groupby(["age_gbn", "test_sex", "연령구간"], dropna=True):
        if len(sub) < MIN_N:
            continue
        for code, name in ITEMS.items():
            if code not in sub:
                continue
            v = sub[code].dropna()
            if len(v) < MIN_N:
                continue
            recs.append({
                "연령군": g, "성별": sex, "연령구간": band,
                "항목코드": code, "항목": name, "n": len(v),
                **{f"p{p}": round(float(np.percentile(v, p)), 2)
                   for p in (5, 10, 25, 50, 75, 90, 95)},
                "평균": round(float(v.mean()), 2),
                "표준편차": round(float(v.std()), 2),
            })
    dist = pd.DataFrame(recs).sort_values(["연령군", "성별", "항목", "연령구간"])
    dist.to_csv(OUT / "fitness_distribution.csv", index=False, encoding="utf-8-sig")
    print(f"분포 {len(dist):,}행 → {OUT/'fitness_distribution.csv'}")

    # --- 2) 처방 빈도 ---
    if "pres_note" not in df:
        return
    parsed = df["pres_note"].apply(parse_note)
    rows = []
    for (g, sex), sub in df.groupby(["age_gbn", "test_sex"], dropna=True):
        for phase in PHASES:
            cnt = Counter()
            for d in parsed.loc[sub.index]:
                cnt.update(d[phase])
            total = sum(cnt.values()) or 1
            for name, n in cnt.most_common():
                rows.append({"연령군": g, "성별": sex, "단계": phase,
                             "운동명": name, "빈도": n,
                             "비율%": round(n / total * 100, 2)})
    freq = pd.DataFrame(rows)
    freq.to_csv(OUT / "exercise_freq.csv", index=False, encoding="utf-8-sig")
    print(f"처방 {len(freq):,}행, 고유 운동 {freq['운동명'].nunique():,}개 → {OUT/'exercise_freq.csv'}")


if __name__ == "__main__":
    main()
