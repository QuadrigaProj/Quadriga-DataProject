"""시작일의 계절과 날씨.

사용자가 루틴을 받은 날이 곧 시작일이다. 봄에 받았다고 봄부터, 가을에 받았다고
가을부터 — 계절별 계획은 시작일의 계절에서 출발해야 한다. 그날 날씨(예보)가
있으면 AI 가 실내·실외, 물 마시기, 준비운동 길이를 그에 맞춘다.

계절은 기상청이 쓰는 달 구분을 따른다 (3~5월 봄, 6~8월 여름, 9~11월 가을,
12~2월 겨울). 날씨는 Open-Meteo 예보 — 키가 필요 없고 16일 앞까지만 준다.
그 밖의 날짜나 실패하면 None 이다. 날씨 없이도 루틴은 지어진다.
"""
from __future__ import annotations

import datetime as _dt

import httpx

SEASONS = ("봄", "여름", "가을", "겨울")
SEOUL = (37.5665, 126.9780)          # 위치를 모를 때 기준. 화면에도 '서울 기준' 이라 적는다
FORECAST_DAYS = 16
TIMEOUT_SEC = 5.0


def parse_date(값) -> _dt.date | None:
    """YYYY-MM-DD 만 받는다. 아니면 None."""
    if not isinstance(값, str):
        return None
    try:
        return _dt.date.fromisoformat(값.strip()[:10])
    except ValueError:
        return None


def season_of(날짜: _dt.date) -> str:
    m = 날짜.month
    if 3 <= m <= 5:
        return "봄"
    if 6 <= m <= 8:
        return "여름"
    if 9 <= m <= 11:
        return "가을"
    return "겨울"


def order_from(시작계절: str) -> tuple[str, ...]:
    """시작 계절부터 한 바퀴. 가을이면 가을·겨울·봄·여름."""
    if 시작계절 not in SEASONS:
        return SEASONS
    i = SEASONS.index(시작계절)
    return SEASONS[i:] + SEASONS[:i]


def fetch_weather(날짜: _dt.date, 위도: float | None = None, 경도: float | None = None) -> dict | None:
    """그날의 예보. 오늘부터 16일 안일 때만. 못 받으면 None — 부르는 쪽은 계절만 쓴다."""
    오늘 = _dt.date.today()
    if not (0 <= (날짜 - 오늘).days <= FORECAST_DAYS):
        return None
    lat, lon = (위도, 경도) if (위도 is not None and 경도 is not None) else SEOUL
    try:
        r = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": lat, "longitude": lon,
                    "daily": "temperature_2m_max,temperature_2m_min,"
                             "precipitation_probability_max,relative_humidity_2m_mean,"
                             "weather_code",
                    "timezone": "Asia/Seoul",
                    "start_date": 날짜.isoformat(), "end_date": 날짜.isoformat()},
            timeout=TIMEOUT_SEC)
        r.raise_for_status()
        d = r.json().get("daily") or {}
        첫 = lambda k: (d.get(k) or [None])[0]
        out = {"최고": 첫("temperature_2m_max"), "최저": 첫("temperature_2m_min"),
               "강수확률": 첫("precipitation_probability_max"),
               "습도": 첫("relative_humidity_2m_mean"),
               "하늘": _sky(첫("weather_code")),
               "기준": "내 위치" if (위도 is not None and 경도 is not None) else "서울"}
        if out["최고"] is None and out["최저"] is None:
            return None
        return out
    except Exception:
        return None


def _sky(code) -> str | None:
    """WMO 날씨 코드 → 한 낱말."""
    if code is None:
        return None
    try:
        c = int(code)
    except (TypeError, ValueError):
        return None
    if c == 0:
        return "맑음"
    if c in (1, 2):
        return "구름 조금"
    if c == 3:
        return "흐림"
    if c in (45, 48):
        return "안개"
    if 51 <= c <= 67 or 80 <= c <= 82:
        return "비"
    if 71 <= c <= 77 or 85 <= c <= 86:
        return "눈"
    if c >= 95:
        return "뇌우"
    return None


def start_info(시작일, 위도=None, 경도=None) -> dict | None:
    """시작일 → {시작일, 계절, 날씨}. 날짜가 아니면 None."""
    날짜 = parse_date(시작일)
    if not 날짜:
        return None
    return {"시작일": 날짜.isoformat(), "계절": season_of(날짜),
            "날씨": fetch_weather(날짜, 위도, 경도)}
