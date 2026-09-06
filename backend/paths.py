"""데이터 파일 경로 탐색.

어느 폴더에서 실행하든(저장소 루트, backend/, tests/) 같은 파일을 찾도록
저장소 루트 기준 절대경로를 돌려준다.

우선순위:
1. data/processed/  — 직접 수집·가공해 만든 최신 데이터 (git 에 올리지 않음)
2. data/sample/     — 저장소에 함께 커밋된 샘플 (clone 직후 바로 실행 가능)
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
SEARCH_DIRS = ("processed", "sample")


def find_data(name: str) -> Path:
    for sub in SEARCH_DIRS:
        p = ROOT / "data" / sub / name
        if p.exists():
            return p
    raise FileNotFoundError(
        f"{name} 을(를) 찾을 수 없습니다. data/processed/ 또는 data/sample/ 에 두세요.\n"
        "직접 만들려면:\n"
        "  python backend/collect_measurements.py --sample 450\n"
        "  python backend/build_distribution.py"
    )


def load_json(name: str) -> dict:
    """샘플 JSON 을 읽는다. 없으면 빈 목록을 돌려준다(서버는 계속 뜬다)."""
    try:
        return json.loads(find_data(name).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"items": []}
