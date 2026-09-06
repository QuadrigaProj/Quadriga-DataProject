"""표본에서 성별×연령×항목 분포와 처방 빈도를 만든다.

사용법:
    python scripts/build_dist.py [입력_sample.json 경로]

입력 기본값은 data/raw/sample.json, 출력은 data/sample/fitness_distribution.csv
와 data/sample/exercise_freq.csv 입니다(레포 루트에서 실행 기준, pathlib 사용).
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IN_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "raw" / "sample.json"
OUT_DIR = ROOT / "data" / "sample"

ITEMS = {
    "item_f001": "신장", "item_f002": "체중", "item_f003": "체지방률",
    "item_f007": "악력(좌)", "item_f008": "악력(우)", "item_f012": "앉아윗몸앞으로굽히기",
    "item_f018": "BMI", "item_f019": "교차윗몸일으키기", "item_f020": "반복점프",
    "item_f021": "왕복오래달리기", "item_f022": "제자리멀리뛰기",
    "item_f023": "의자앉았다일어서기", "item_f024": "6분걷기", "item_f025": "2분제자리걷기",
    "item_f026": "3m표적돌아오기", "item_f027": "8자보행", "item_f028": "상대악력",
}
CORE = ["item_f012", "item_f018", "item_f019", "item_f023"]


def band(r: pd.Series) -> str | None:
    """나이·연령군을 성인 5세 구간(19~24 …) / 어르신 5세 구간(65~69 …) / 그 외 5세 구간으로 나눈다."""
    a, g = r["age"], r.get("age_gbn")
    if pd.isna(a):
        return None
    a = int(a)
    if g == "성인":
        if a < 19:
            return None
        if a >= 65:
            return "65+"
        for lo, hi in [(19, 24), (25, 29), (30, 34), (35, 39), (40, 44), (45, 49), (50, 54), (55, 59), (60, 64)]:
            if lo <= a <= hi:
                return f"{lo}~{hi}"
        return None
    if g == "어르신":
        for lo, hi in [(65, 69), (70, 74), (75, 79), (80, 120)]:
            if lo <= a <= hi:
                return f"{lo}~{hi if hi < 120 else ''}".rstrip("~")
        return None
    return f"{a // 5 * 5}~{a // 5 * 5 + 4}"


PHASES = ("준비운동", "본운동", "정리운동")
_SEP = re.compile(r"\s*/\s*")
_PRE = re.compile(r"^\s*(준비운동|본운동|정리운동)\s*[:：]\s*")


def parse_prescription(note: object) -> dict[str, list[str]]:
    """pres_note 텍스트 한 줄을 준비/본/정리 운동 단계별 운동명 리스트로 나눈다."""
    out: dict[str, list[str]] = {p: [] for p in PHASES}
    if not isinstance(note, str) or not note.strip():
        return out
    for block in _SEP.split(note):
        if not block.strip():
            continue
        m = _PRE.match(block)
        phase, body = (m.group(1), block[m.end():]) if m else ("본운동", block)
        out[phase].extend([re.sub(r"\s+", " ", x).strip() for x in body.split(",") if x.strip()])
    return out


def main() -> None:
    if not IN_PATH.exists():
        raise SystemExit(f"입력 파일이 없습니다: {IN_PATH}")
    rows = json.loads(IN_PATH.read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    print(f"표본 {len(df):,}행")

    df["age"] = pd.to_numeric(df.get("age_degree"), errors="coerce")
    for c in ITEMS:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # 이상치 제거: 항목별 상하위 0.5% 윈저화
    for c in [c for c in ITEMS if c in df]:
        lo, hi = df[c].quantile([0.005, 0.995])
        df[c] = df[c].clip(lo, hi)

    df["연령구간"] = df.apply(band, axis=1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    recs = []
    for (g, sex, bd), sub in df.groupby(["age_gbn", "test_sex", "연령구간"], dropna=True):
        if len(sub) < 30:
            continue
        for code, name in ITEMS.items():
            if code not in sub:
                continue
            v = sub[code].dropna()
            if len(v) < 30:
                continue
            recs.append({
                "연령군": g, "성별": sex, "연령구간": bd, "항목코드": code, "항목": name, "n": len(v),
                **{f"p{p}": round(float(np.percentile(v, p)), 2) for p in (5, 10, 25, 50, 75, 90, 95)},
                "평균": round(float(v.mean()), 2), "표준편차": round(float(v.std()), 2),
            })
    dist = pd.DataFrame(recs).sort_values(["연령군", "성별", "항목", "연령구간"])
    dist_path = OUT_DIR / "fitness_distribution.csv"
    dist.to_csv(dist_path, index=False, encoding="utf-8-sig")
    print(f"분포 {len(dist):,}행 → {dist_path}")

    if "pres_note" in df:
        parsed = df["pres_note"].apply(parse_prescription)
        freq_rows = []
        for (g, sex), sub in df.groupby(["age_gbn", "test_sex"], dropna=True):
            for phase in PHASES:
                counter: Counter[str] = Counter()
                for d in parsed.loc[sub.index]:
                    counter.update(d[phase])
                total = sum(counter.values()) or 1
                for name, k in counter.most_common():
                    freq_rows.append({
                        "연령군": g, "성별": sex, "단계": phase, "운동명": name,
                        "빈도": k, "비율%": round(k / total * 100, 2),
                    })
        freq = pd.DataFrame(freq_rows)
        freq_path = OUT_DIR / "exercise_freq.csv"
        freq.to_csv(freq_path, index=False, encoding="utf-8-sig")
        print(f"처방 {len(freq):,}행, 고유 운동 {freq['운동명'].nunique():,}개 → {freq_path}")

    print("\n=== 필수 3항목 표본 수 (연령군×성별) ===")
    cov = df.groupby(["age_gbn", "test_sex"])[CORE].count()
    cov.columns = [ITEMS[c] for c in CORE]
    print(cov.to_string())


if __name__ == "__main__":
    main()
