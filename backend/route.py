"""출발지→목적지 경로 분석 (F2).

가는 길의 특성(거리·시간·누적 오르막·계단 구간)을 읽고, 근력 별점에 맞춰 걷기/계단을 추천한다.
- 좌표: 카카오 로컬 키워드 검색 → 없으면 geo.geocode
- 경로: 카카오 도보 경로 API → 없으면 직선거리(분속 80m) 추정
- 오르막: Open-Meteo 고도 API (키 없음, 100점/요청)
provider 는 키 없음·타임아웃·status≠OK·응답 모양이 가정과 다름(파싱 실패) 이면 예외 대신 None 을 돌려주고,
advise() 가 폴백한다(500 금지).
Tmap 보행자 API 는 별도 키가 필요해 이번엔 안 쓴다 — 키가 생기면 kakao_walk 와 같은 반환 모양의 provider 를 추가한다.
"""
from __future__ import annotations

import os

import httpx

try:                                     # 저장소 루트에서 실행할 때
    from backend import daily, geo
except ImportError:                      # backend/ 안에서 직접 실행할 때
    import daily
    import geo

KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
KAKAO_WALK_URL = "https://dapi.kakao.com/v2/routing/walk"
OPEN_METEO_ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
ELEVATION_CREDIT = "고도 데이터: Open-Meteo (CC BY 4.0)"
HTTP_TIMEOUT = 10
WALK_SPEED_M_PER_MIN = 80        # 폴백 추정용 분속
PART_WALK_MAX_MIN = 45           # 이 분 이하면 '일부걷기', 넘으면 '대중교통'. 20분 이하는 daily.WALK_LIMIT_MIN
UPHILL_MIN_M = 15                # 누적 오르막이 이 이상이면 계단 문구를 붙인다
ELEVATION_MAX_POINTS = 100       # Open-Meteo 한 요청 상한
FALLBACK_LINE_POINTS = 20        # 직선 폴백일 때 고도를 볼 보간 점 수
SAME_POINT_M = 30                # 이보다 가까우면 같은 곳으로 본다
STAIR_WORDS = ("계단", "육교", "지하보도", "지하도")


# main.py 는 아래 두 예외만 404/400 으로 바꾼다. 부모 클래스(LookupError·ValueError)를 그대로 잡으면
# 파싱 중 난 KeyError·IndexError·float() 실패까지 사용자 오류로 둔갑해 내부 오류 문자열이 화면에 보인다.
class PlaceNotFoundError(LookupError):
    """출발지·목적지 문자열을 좌표로 바꾸지 못함 (→ 404)."""


class SamePointError(ValueError):
    """출발지와 목적지가 같은 지점 (→ 400)."""


def _kakao_key() -> str | None:
    """auth.client_config 와 같은 환경변수. REST 키 = 카카오 로그인 client id."""
    return os.getenv("KAKAO_CLIENT_ID") or None


def _kakao_headers(key: str) -> dict:
    return {"Authorization": f"KakaoAK {key}"}


async def _get_json(url: str, params: dict, headers: dict | None = None) -> dict | None:
    """GET 한 번. 타임아웃·비정상 상태·JSON 아님은 전부 None (예외를 밖으로 내지 않는다)."""
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as http:
            r = await http.get(url, params=params, headers=headers or {})
        if r.status_code != 200:
            return None
        j = r.json()
        return j if isinstance(j, dict) else None   # 세 API 모두 객체를 돌려준다 — 그 밖은 파싱 대상 아님
    except Exception:                    # 외부 API 실패는 전부 폴백 대상
        return None


# ---------- provider 1: 문자열 → 좌표 ----------

async def geocode_text(query: str) -> tuple[float, float] | None:
    """장소·지역 문자열 → (위도, 경도). 카카오 키워드 검색 1건. 키 없음·실패·결과 없음 → None."""
    key = _kakao_key()
    q = (query or "").strip()
    if not key or not q:
        return None
    j = await _get_json(KAKAO_KEYWORD_URL, {"query": q, "size": 1}, _kakao_headers(key))
    try:
        docs = (j or {}).get("documents") or []
        if not docs:
            return None
        return float(docs[0]["y"]), float(docs[0]["x"])      # y=위도, x=경도
    except Exception:                    # 응답 모양이 가정과 다르면(문서가 dict 가 아님 등) 폴백
        return None


# ---------- provider 2: 도보 경로 ----------

async def kakao_walk(start: tuple[float, float], end: tuple[float, float],
                     route_mode: str = "SHORTEST") -> dict | None:
    """카카오 도보 경로.

    반환 {"거리m": int, "시간초": int, "구간안내": [str], "좌표": [(위도, 경도), …]} / 실패 None.
    응답 필드명은 devtalk 공지(research.md) 기준: status, route.properties.totalDistance/totalTime,
    route.legs[].steps[].properties.guidance, steps[].path.points[[x, y], …]. routes[0] 형태도 허용.
    """
    key = _kakao_key()
    if not key:
        return None
    params = {"start_x": start[1], "start_y": start[0], "end_x": end[1], "end_y": end[0],
              "route_mode": route_mode}
    j = await _get_json(KAKAO_WALK_URL, params, _kakao_headers(key))
    # 필드명은 실제 응답으로 검증하지 못했다(risks). 모양이 다르면(points 가 객체·3원소, route 가
    # 리스트, legs 가 dict …) 어떤 예외든 None → advise() 가 직선거리로 추정한다. 400/500 금지.
    try:
        if not j or j.get("status") != "OK":
            return None
        r = j.get("route") or ((j.get("routes") or [None])[0]) or {}
        props = r.get("properties") or {}
        guidance: list[str] = []
        points: list[tuple[float, float]] = []
        for leg in r.get("legs") or []:
            for step in leg.get("steps") or []:
                g = (step.get("properties") or {}).get("guidance")
                if g:
                    guidance.append(str(g))
                for x, y in ((step.get("path") or {}).get("points") or []):
                    points.append((float(y), float(x)))
        return {"거리m": int(props["totalDistance"]), "시간초": int(props["totalTime"]),
                "구간안내": guidance, "좌표": points or [start, end]}
    except Exception:                    # 파싱 실패는 전부 폴백 대상
        return None


# ---------- provider 3: 고도 ----------

def _sample(points: list, n: int) -> list:
    """등간격 n개 이하로 줄인다. 처음·끝 점은 반드시 남긴다."""
    if len(points) <= n:
        return list(points)
    step = (len(points) - 1) / (n - 1)
    return [points[round(i * step)] for i in range(n)]


async def elevation_gain(points: list[tuple[float, float]]) -> float | None:
    """경로 좌표열 → 누적 오르막(m) = 인접 고도 차이의 양수 합. 실패·점 2개 미만 → None."""
    pts = _sample(points, ELEVATION_MAX_POINTS)
    if len(pts) < 2:
        return None
    j = await _get_json(OPEN_METEO_ELEVATION_URL, {
        "latitude": ",".join(f"{p[0]:.5f}" for p in pts),
        "longitude": ",".join(f"{p[1]:.5f}" for p in pts),
    })
    try:
        elev = (j or {}).get("elevation") or []
        if len(elev) != len(pts):
            return None
        gain = 0.0
        for a, b in zip(elev, elev[1:]):
            if b > a:
                gain += b - a
        return round(gain, 1)
    except Exception:                    # 응답이 dict 가 아니거나 고도가 숫자가 아니면 폴백
        return None


# ---------- 규칙 (네트워크 없음) ----------

def has_stairs(guidance: list[str]) -> bool:
    return any(w in g for g in guidance for w in STAIR_WORDS)


def recommend(minutes: int, gain_m: float | None, stairs: bool, strength_stars: int) -> dict:
    """거리·오르막·계단 + 근력 별점 → {"유형", "문구"}.

    - 도보 ≤ daily.WALK_LIMIT_MIN(20) → 전부걷기
    - ≤ PART_WALK_MAX_MIN(45)        → 일부걷기: N정거장 먼저 내려 걷기 (≤30분 1정거장, 그 밖 2정거장)
    - 그 밖                          → 대중교통
    - 계단 구간 또는 오르막 ≥ UPHILL_MIN_M → 근력 별점별 계단 문구(daily.stairs) 결합. 근력이 약하면
      계단을 권하지 않는 기존 안전선을 그대로 쓴다.
    """
    if minutes <= daily.WALK_LIMIT_MIN:
        kind = "전부걷기"
        text = f"도보 약 {minutes}분 거리예요. 오늘은 전부 걸어가 보세요."
    elif minutes <= PART_WALK_MAX_MIN:
        stops = 1 if minutes <= 30 else 2
        kind = "일부걷기"
        text = f"도보로는 약 {minutes}분이라 전부 걷기엔 조금 멀어요. {stops}정거장 먼저 내려서 걸어보세요."
    else:
        kind = "대중교통"
        text = f"도보 약 {minutes}분 · 걷기에는 먼 거리예요. 대중교통을 이용하세요."
    uphill = gain_m is not None and gain_m >= UPHILL_MIN_M
    if stairs or uphill:
        feature = "계단 구간이" if stairs else f"오르막(누적 {gain_m:g}m)이"
        text += f" 가는 길에 {feature} 있어요. " + daily.stairs(strength_stars)["문구"]
    return {"유형": kind, "문구": text}


# ---------- 조합 + 폴백 ----------

def _line(start, end, n: int = FALLBACK_LINE_POINTS) -> list[tuple[float, float]]:
    """직선 폴백용 보간 점."""
    return [(start[0] + (end[0] - start[0]) * i / (n - 1),
             start[1] + (end[1] - start[1]) * i / (n - 1)) for i in range(n)]


async def _locate(q: str) -> tuple[float, float]:
    q = (q or "").strip()
    hit = (await geocode_text(q)) or geo.geocode(q)
    if not hit:
        raise PlaceNotFoundError(f"'{q}' 을(를) 찾지 못했어요. 구 이름이나 역 이름으로 다시 입력해 주세요.")
    return hit


async def advise(from_: str, to: str, strength_stars: int = 3) -> dict:
    """출발지·목적지 문자열 + 근력 별점 → 경로 특성과 추천.

    반환 키: 출발지, 목적지, 거리m, 시간분, 오르막m(None 가능), 구간안내[], 계단있음,
            추천{유형: 전부걷기|일부걷기|대중교통, 문구}, 출처(kakao|추정), 안내
    예외: PlaceNotFoundError(지역 못 찾음 → 404), SamePointError(같은 지점 → 400)
    """
    start = await _locate(from_)
    end = await _locate(to)
    dist_line = round(daily._km(start[0], start[1], end[0], end[1]) * 1000)
    if dist_line < SAME_POINT_M:
        raise SamePointError("출발지와 목적지가 같은 곳이에요. 다른 곳을 입력해 주세요.")

    walk = await kakao_walk(start, end)
    if walk:
        distance, minutes = walk["거리m"], max(1, round(walk["시간초"] / 60))
        guidance, points, source = walk["구간안내"], walk["좌표"], "kakao"
        note = "카카오 도보 경로 기준이에요."
    else:                                  # 키 없음·실패 → 직선거리 추정
        distance, minutes = dist_line, max(1, round(dist_line / WALK_SPEED_M_PER_MIN))
        guidance, points, source = [], _line(start, end), "추정"
        note = "직선거리 기준 추정이에요. 실제 길은 이보다 길 수 있어요."

    gain = await elevation_gain(points)    # 키 없음 — 폴백 경로에서도 시도한다
    stairs = has_stairs(guidance)
    if gain is not None:
        note += " " + ELEVATION_CREDIT
    return {
        "출발지": from_.strip(), "목적지": to.strip(),
        "거리m": distance, "시간분": minutes, "오르막m": gain,
        "구간안내": guidance,
        "계단있음": stairs or (gain is not None and gain >= UPHILL_MIN_M),
        "추천": recommend(minutes, gain, stairs, strength_stars),
        "출처": source, "안내": note,
    }
