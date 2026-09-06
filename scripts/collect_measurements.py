"""
국민체력100 측정결과 데이터 수집기  (담당 A·D 공통 선행 작업)

일일 트래픽 10,000회 / 요청당 최대 1,000행 (numOfRows를 더 크게 줘도 1,000으로 잘림)
전체 2,957,287건 → 약 2,958 요청. 하루 한도 안에 들어온다.

사용법:
    pip install requests pandas tqdm python-dotenv
    # .env 에 DATA_GO_KR_KEY=... 넣어둘 것
    python scripts/collect_measurements.py            # 전체
    python scripts/collect_measurements.py --pages 50 # 테스트용 5만 건

결과:
    data/raw/measurements.parquet   (없으면 csv)
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

BASE = "https://apis.data.go.kr/B551014/SRVC_NFA_TEST_RESULT/TODZ_NFA_TEST_RESULT_NEW"
KEY = os.environ.get("DATA_GO_KR_KEY")
ROWS = 1000                      # 서버 상한
OUT = Path("data/raw/measurements.parquet")
DAILY_LIMIT = 10_000             # 개발계정 일일 트래픽


def fetch_page(page: int, retries: int = 3) -> list[dict]:
    """한 페이지를 가져온다. 실패 시 지수 백오프로 재시도."""
    params = {
        "serviceKey": KEY,
        "resultType": "json",
        "numOfRows": ROWS,
        "pageNo": page,
    }
    for attempt in range(retries):
        try:
            r = requests.get(BASE, params=params, timeout=30)
            r.raise_for_status()
            body = r.json()["response"]["body"]
            items = body.get("items", {}).get("item", [])
            return items if isinstance(items, list) else [items]
        except Exception as e:
            if attempt == retries - 1:
                print(f"\n[실패] page={page}: {e}")
                return []
            time.sleep(2 ** attempt)
    return []


def total_count() -> int:
    params = {"serviceKey": KEY, "resultType": "json", "numOfRows": 1, "pageNo": 1}
    r = requests.get(BASE, params=params, timeout=30)
    return int(r.json()["response"]["body"]["totalCount"])


def main() -> None:
    if not KEY:
        raise SystemExit("DATA_GO_KR_KEY 가 없습니다. .env 를 확인하세요.")

    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=None, help="가져올 페이지 수 (기본: 전체)")
    ap.add_argument("--start", type=int, default=1, help="시작 페이지 (이어받기용)")
    args = ap.parse_args()

    total = total_count()
    last_page = (total + ROWS - 1) // ROWS
    end_page = min(args.start + args.pages - 1, last_page) if args.pages else last_page
    n_req = end_page - args.start + 1

    print(f"전체 {total:,}건 / 페이지 {last_page:,}개")
    print(f"수집 범위: {args.start} ~ {end_page} ({n_req:,} 요청)")
    if n_req > DAILY_LIMIT:
        print(f"⚠ 일일 한도({DAILY_LIMIT:,})를 넘습니다. --pages 로 나눠 받으세요.")

    records: list[dict] = []
    for page in tqdm(range(args.start, end_page + 1), desc="수집"):
        records.extend(fetch_page(page))

    df = pd.DataFrame(records)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(OUT, index=False)
        print(f"\n저장: {OUT}  ({len(df):,}행 × {len(df.columns)}열)")
    except Exception:
        csv = OUT.with_suffix(".csv")
        df.to_csv(csv, index=False, encoding="utf-8-sig")
        print(f"\n저장: {csv}  ({len(df):,}행)  ※ parquet 실패로 csv 저장")

    print("\n연령군 분포:")
    print(df["age_gbn"].value_counts().to_string())


if __name__ == "__main__":
    main()
