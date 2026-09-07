"""연령대 × 목적별 '오늘의 일상 처방' 문구 — 경과일 % 30 으로 순환.

data/processed/ (없으면 data/sample/) 의 daily_prescriptions_750.json 을 읽어
오늘 보여줄 문구 한 줄을 돌려준다.

이 문구는 운동 루틴(routines_250)과 별개다. 따로 시간 내지 않고
생활 속에서 몸을 쓰게 하는 제안(계단·이동·자세·집안일 등)이며,
25 카테고리(연령대 5 × 목적 5)마다 30개가 있고 날마다 하나씩 순환한다.
"""
from __future__ import annotations

import json

try:                                     # 저장소 루트에서 실행할 때
    from backend.paths import find_data
except ImportError:                      # backend/ 안에서 직접 실행할 때
    from paths import find_data

FILE = "daily_prescriptions_750.json"
DEFAULT_CYCLE = 30
FALLBACK_PURPOSE = "기초 체력 증진"

_data: dict | None = None


def load() -> dict:
    """문구 데이터를 한 번만 읽어 캐시한다."""
    global _data
    if _data is None:
        _data = json.loads(find_data(FILE).read_text(encoding="utf-8"))
    return _data


def _phrases(by_age: dict, purpose: str) -> list[str] | None:
    """해당 목적의 문구 목록. 없으면 기초 체력 증진으로 대체한다."""
    return by_age.get(purpose) or by_age.get(FALLBACK_PURPOSE)


def tip(age_gbn: str, purpose: str, day: int) -> dict | None:
    """오늘의 문구 한 줄.

    day 는 0-based 경과일(programDay). day % 30 으로 골라, 30일을 돌면 다시 1번으로.
    데이터에 해당 연령대가 없으면 None (화면은 계단·도보 문구만 보여준다).
    """
    data = load()
    by_age = data.get("prescriptions", {}).get(age_gbn)
    if not by_age:
        return None

    # 어르신 × 수험생 체력 증진은 대상이 아니다. 기초 체력 문구로 대체한다.
    # (JSON 의 해당 배열 첫 줄은 사용자용이 아니라 개발 안내라 그대로 쓰지 않는다.)
    if age_gbn == "어르신" and purpose == "수험생 체력 증진":
        purpose = FALLBACK_PURPOSE

    phrases = _phrases(by_age, purpose)
    if not phrases:
        return None

    cycle = int(data.get("config", {}).get("cycle_days", DEFAULT_CYCLE))
    index = max(0, int(day)) % cycle
    if index >= len(phrases):
        index %= len(phrases)

    return {
        "문구": phrases[index],
        "순번": index + 1,
        "총일수": len(phrases),
        "주기일수": cycle,
    }


if __name__ == "__main__":
    for d in (0, 1, 2, 30, 31):
        print(f"성인·다이어트 day {d:>2} → {tip('성인', '다이어트', d)}")
