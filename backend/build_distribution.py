"""
분포 테이블 · 처방 빈도 생성

수집한 측정결과에서
  1) 연령군 × 성별 × 연령구간 × 항목별 백분위 분포  → fitness_distribution.csv
  2) 연령군 × 성별 × 단계별 운동처방 빈도            → exercise_freq.csv
를 만든다.

  3) 또래 비교용 '좁은 창' 분포 — 나이마다 그 나이를 가운데 둔 창(21세 → 20~22세) → fitness_peer_windows.csv

사용법:
    python backend/collect_measurements.py   # 먼저 수집
    python backend/build_distribution.py

3) 을 앱에 반영하려면 만들어진 data/processed/fitness_peer_windows.csv 를 data/sample/ 에 복사해 커밋한다
(배포 서버에는 data/sample/ 만 올라간다). 백분위 표라 원자료가 아니고, 3천 줄 남짓이다.
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
# f020·f021 은 처음에 '반복점프'·'왕복오래달리기' 로 잘못 읽었다. 값으로 보면 f020 은 20~60회에 나이 들수록 줄고
# (남 19~24세 상위 25% = 62회 = 공식 1등급 기준), f021 은 9~17초에 나이 들수록 는다(상위 25% = 9.9초 = 공식 1등급) —
# f020 이 왕복오래달리기(회, 11~12세는 15m · 13세부터 20m), f021 이 10m 4회 왕복달리기(초)다.
ITEMS = {
    "item_f001": "신장", "item_f002": "체중", "item_f003": "체지방률",
    "item_f007": "악력(좌)", "item_f008": "악력(우)",
    "item_f012": "앉아윗몸앞으로굽히기", "item_f018": "BMI",
    "item_f019": "교차윗몸일으키기", "item_f020": "왕복오래달리기",
    "item_f021": "10m왕복달리기", "item_f022": "제자리멀리뛰기",
    "item_f023": "의자앉았다일어서기", "item_f024": "6분걷기",
    "item_f025": "2분제자리걷기", "item_f026": "3m표적돌아오기",
    "item_f027": "8자보행", "item_f028": "상대악력",
}

MIN_N = 30          # 셀당 최소 표본
WINSOR = 0.005      # 상하위 0.5% 절단

# 또래 비교용 좁은 창 — 환산나이 곡선(5세 구간)과 따로 둔다.
#   곡선은 구간이 좁으면 중앙값이 들쭉날쭉해져 환산나이가 튄다. 그래서 곡선은 공식 5세 구간 그대로 두고,
#   "또래 가운데 몇 등인가" 만 좁은 창으로 견준다 — 21세를 19~24세가 아니라 20~22세와.
# 창은 자기 나이 ±WINDOW_HALF 에서 시작해, 표본이 WINDOW_MIN_N 에 못 미치면 한 살씩 넓힌다(최대 ±WINDOW_MAX_HALF).
# 연령군의 경계는 넘지 않는다 — 18세(성장기)와 19세(성인)는 재는 항목이 다르다.
WINDOW_HALF = 1
WINDOW_MAX_HALF = 5
WINDOW_MIN_N = 300
GROUP_AGES = {"성장기": (11, 18), "성인": (19, 64), "어르신": (65, 95)}

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


def window_label(lo: int, hi: int) -> str:
    return str(lo) if lo == hi else f"{lo}~{hi}"


def peer_windows(df: pd.DataFrame, *, half: int = WINDOW_HALF, max_half: int = WINDOW_MAX_HALF,
                 min_n: int = WINDOW_MIN_N) -> pd.DataFrame:
    """나이마다 그 나이를 가운데 둔 창의 백분위 표.

    df 에는 age(정수 나이) · age_gbn(성장기/성인/어르신) · test_sex · 항목 열이 있어야 한다(윈저화가 끝난 값).
    항목마다 창을 따로 넓힌다 — 같은 나이라도 키는 다 재고 8자보행은 일부만 잰다.
    max_half 까지 넓혀도 min_n 이 안 되면 그 나이 · 항목은 내지 않는다(서버가 5세 구간으로 되돌아간다).
    """
    recs = []
    for g, (g_lo, g_hi) in GROUP_AGES.items():
        for sex in ("M", "F"):
            sub = df[(df["age_gbn"] == g) & (df["test_sex"] == sex) & (df["age"] >= g_lo)]
            if sub.empty:
                continue
            ages = sub["age"].to_numpy()
            for code, name in ITEMS.items():
                if code not in sub:
                    continue
                vals = sub[code].to_numpy(dtype=float)
                ok = ~np.isnan(vals)
                for a in range(g_lo, g_hi + 1):
                    for w in range(half, max_half + 1):
                        lo, hi = max(g_lo, a - w), a + w
                        # 어르신의 맨 위쪽은 위로 열어 둔다("93+") — 그 위로는 어차피 몇 명 없다
                        열림 = g == "어르신" and hi >= g_hi
                        if not 열림:
                            hi = min(hi, g_hi)
                        v = vals[ok & (ages >= lo) & ((ages <= hi) | 열림)]
                        if len(v) >= min_n:
                            recs.append({
                                "연령군": g, "성별": sex, "나이": a, "구간": f"{lo}+" if 열림 else window_label(lo, hi),
                                "항목코드": code, "항목": name, "n": int(len(v)),
                                **{f"p{p}": round(float(np.percentile(v, p)), 2) for p in (5, 10, 25, 50, 75, 90, 95)},
                                "평균": round(float(v.mean()), 2), "표준편차": round(float(v.std()), 2),
                            })
                            break
    cols = ["연령군", "성별", "나이", "구간", "항목코드", "항목", "n", "p5", "p10", "p25", "p50", "p75", "p90", "p95", "평균", "표준편차"]
    return pd.DataFrame(recs, columns=cols)


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

    # --- 3) 또래 비교용 좁은 창 ---
    win = peer_windows(df)
    win.to_csv(OUT / "fitness_peer_windows.csv", index=False, encoding="utf-8-sig")
    print(f"좁은 창 {len(win):,}행 → {OUT/'fitness_peer_windows.csv'}")
    print("  앱에 반영하려면 이 파일을 data/sample/ 에 복사해 커밋하세요.")

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
