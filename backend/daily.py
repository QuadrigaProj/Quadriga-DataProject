"""일상 처방 · 강도 점증 · 영상 필터.

기획안 6-4, 15-2절. 운동 시간을 따로 내지 않아도 일상에서 몸을 쓰게 만드는
쪽이 이 서비스의 차별점이라, 체력나이 산출과 별개로 여기에 모아 둔다.

교통 데이터는 쓰지 않는다. 사용자가 알려준 도보 시간·층수만으로 판단한다.
"""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

try:
    from backend.paths import load_json
except ImportError:
    from paths import load_json

# 계단 처방: 근력이 약한 사람에게 계단을 권하면 무릎을 상하게 한다.
# 아래 세 갈래는 그 안전선을 지키기 위한 것이다.
STAIRS = {
    "상위": "3층 이내는 계단으로 올라가 보세요.",
    "중간": "올라갈 때만 계단을, 내려올 땐 엘리베이터를 이용하세요.",
    "하위": "계단 대신 한 정거장 먼저 내려서 걷는 걸 추천해요. "
            "무리한 계단 이용은 권하지 않습니다.",
}

WALK_LIMIT_MIN = 20


def stairs(strength_stars: int) -> dict:
    level = "상위" if strength_stars >= 4 else "중간" if strength_stars >= 2 else "하위"
    return {"수준": level, "문구": STAIRS[level]}


def walk(minutes: float | None) -> dict | None:
    if minutes is None:
        return None
    if minutes <= WALK_LIMIT_MIN:
        return {"권장": True, "문구": f"도보 약 {minutes:g}분 거리예요. 오늘은 걸어가 보는 건 어떨까요?"}
    return {"권장": False, "문구": "걷기에는 다소 먼 거리예요. 무리한 이동 제안은 드리지 않아요."}


def intensity(days_since_start: int) -> dict:
    """4주 단위로 세트·반복만 올린다. 종목은 바꾸지 않는다."""
    week = days_since_start // 7 + 1
    if week <= 4:
        return {"주차": week, "구간": "1~4주차", "반복": 10, "세트": 2}
    if week <= 8:
        return {"주차": week, "구간": "5~8주차", "반복": 12, "세트": 3}
    return {"주차": week, "구간": "9~12주차+", "반복": 15, "세트": 3}


def videos(*, factor=None, se=None, place=None, level=None,
           max_sec=None, exclude_parts=None) -> list[dict]:
    """동영상 목록을 조건으로 거른다.

    지금은 data/sample/videos.json 을 쓴다. 실제 동영상 API 응답을 받으면
    같은 필드명(ftns_fctr_nm 등)으로 채워 넣기만 하면 된다.
    """
    items = load_json("videos.json").get("items", [])
    exclude = set(exclude_parts or [])
    out = []
    for v in items:
        # 동영상 API 의 요인명은 "근력·근지구력", "민첩성·순발력" 처럼 묶여 있다.
        # 체력나이 쪽은 "근력" 만 쓰므로 부분일치로 잇는다.
        vf = v.get("ftns_fctr_nm") or ""
        if factor and factor not in vf and vf not in factor:
            continue
        if se and v.get("trng_se_nm") != se:
            continue
        if place and place not in (v.get("trng_plc_nm") or ""):
            continue
        if level and v.get("lvl_nm") != level:
            continue
        if max_sec and v.get("playSec", 0) > max_sec:
            continue
        if exclude & set(v.get("burdenParts") or []):
            continue
        out.append(v)
    return out


def _km(lat1, lon1, lat2, lon2) -> float:
    r = 6371
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def centers(lat: float | None = None, lon: float | None = None, limit: int = 5) -> list[dict]:
    items = load_json("centers.json").get("items", [])
    if lat is not None and lon is not None:
        items = sorted(
            ({**c, "거리km": round(_km(lat, lon, c["la"], c["lo"]), 1)} for c in items),
            key=lambda c: c["거리km"],
        )
    return items[:limit]
