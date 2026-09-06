"""
국민체력100 측정결과 수집기 — 담당 A·D 공통 선행

전체 2,957,287건. 요청당 최대 1,000행(더 크게 줘도 1,000으로 잘림).
개발계정 일일 트래픽 10,000회 → 약 2,958회면 전체 수집 가능하다.

주의: 페이지는 측정연월 순이다. 앞 페이지만 받으면 오래된 데이터에 편향된다.
      표본만 필요하면 --sample 로 전 구간에 걸쳐 균등 추출한다.

사용법:
    pip install requests pandas tqdm python-dotenv pyarrow
    # .env 에 DATA_GO_KR_KEY=... 넣어둘 것

    python scripts/collect_measurements.py --sample 450   # 45만 건 표본 (약 20분)
    python scripts/collect_measurements.py                # 전체
"""
from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

BASE = "https://apis.data.go.kr/B551014/SRVC_NFA_TEST_RESULT/TODZ_NFA_TEST_RESULT_NEW"
KEY = os.environ.get("DATA_GO_KR_KEY")
ROWS = 1000            # 서버 상한
OUT = Path("data/raw/measurements.parquet")
DAILY_LIMIT = 10_000
WORKERS = 4            # 너무 올리면 게이트웨이가 연결을 끊는다


def fetch(page: int, retries: int = 3) -> list[dict]:
    params = {"serviceKey": KEY, "resultType": "json", "numOfRows": ROWS, "pageNo": page}
    for attempt in range(retries):
        try:
            r = requests.get(BASE, params=params, timeout=60)
            r.raise_for_status()
            items = r.json()["response"]["body"].get("items", {}).get("item", [])
            return items if isinstance(items, list) else [items]
        except Exception:
            if attempt == retries - 1:
                return []
            time.sleep(2 ** attempt)
    return []


def total_count() -> int:
    r = requests.get(BASE, params={"serviceKey": KEY, "resultType": "json",
                                   "numOfRows": 1, "pageNo": 1}, timeout=30)
    return int(r.json()["response"]["body"]["totalCount"])


def main() -> None:
    if not KEY:
        raise SystemExit("DATA_GO_KR_KEY 가 없습니다. .env 를 확인하세요.")

    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, help="전 구간 균등 표본 페이지 수")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--pages", type=int, help="연속 페이지 수 (--sample 과 배타)")
    args = ap.parse_args()

    total = total_count()
    last = (total + ROWS - 1) // ROWS
    print(f"전체 {total:,}건 / 페이지 {last:,}개")

    if args.sample:
        step = last / args.sample
        pages = sorted({max(1, min(last, int(1 + i * step))) for i in range(args.sample)})
        print(f"전 구간 균등 표본: {len(pages):,} 페이지")
    else:
        end = min(args.start + args.pages - 1, last) if args.pages else last
        pages = list(range(args.start, end + 1))
        print(f"연속 수집: {args.start} ~ {end}")

    if len(pages) > DAILY_LIMIT:
        print(f"⚠ 일일 한도({DAILY_LIMIT:,}) 초과. --pages 로 나눠 받으세요.")

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(fetch, p) for p in pages]
        for f in tqdm(as_completed(futs), total=len(futs), desc="수집"):
            rows.extend(f.result())

    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(OUT, index=False)
        print(f"\n저장: {OUT}  ({len(df):,}행 × {len(df.columns)}열)")
    except Exception:
        csv = OUT.with_suffix(".csv")
        df.to_csv(csv, index=False, encoding="utf-8-sig")
        print(f"\n저장: {csv}  ({len(df):,}행)  ※ parquet 실패로 csv 저장")

    if "age_gbn" in df:
        print("\n연령군 분포:")
        print(df["age_gbn"].value_counts().to_string())


if __name__ == "__main__":
    main()
