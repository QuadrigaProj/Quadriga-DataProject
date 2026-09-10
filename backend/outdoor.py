"""오늘 날씨에 맞춘 대안 — 밖에서 하는 동작이 있으면 실내·비슷한 것으로.

루틴을 고르면 매일 같은 루틴이 뜬다. 그런데 그날 비가 오거나 33℃ 면
러닝을 그대로 시킬 수 없다. 당일 아침 날씨(예보)를 보고, 루틴 안의
밖에서 하는 동작마다 실내 대안을 **안내**한다. 루틴을 바꿔치기하지는
않는다 — 어떻게 할지는 사용자가 정한다.

AI 를 부르지 않는다. 규칙이면 충분하고, 매일 아침 돌아가는 것이라
값이 들거나 느리면 안 된다. 날씨는 backend/season.py (Open-Meteo) 다.
"""
from __future__ import annotations

import datetime as _dt

try:                                        # 저장소 루트에서 실행할 때
    from backend import season as ssn
except ImportError:                         # backend/ 안에서 직접 실행할 때
    import season as ssn  # type: ignore

# 밖에서 하는 종목(sports.json id) → 실내·비슷한 대안. 여기 없으면 실내로 본다.
OUTDOOR_SPORTS = {
    "running":    ("러닝",     ["러닝머신 25분", "계단 오르기 15분 + 제자리 걷기 10분"]),
    "marathon":   ("마라톤",   ["러닝머신 40분", "실내 자전거 40분"]),
    "hiking":     ("등산",     ["계단 오르기 20분", "스텝 박스 오르내리기 15분"]),
    "cycling":    ("자전거",   ["실내 자전거 30분", "계단 오르기 15분"]),
    "tennis":     ("테니스",   ["스쿼시·실내 코트", "줄넘기 10분 + 맨몸 근력"]),
    "golf":       ("골프",     ["실내 연습장", "몸통 비틀기 스트레칭 + 맨몸 근력"]),
    "soccer":     ("축구",     ["줄넘기 10분 + 스쿼트·런지", "실내 풋살장"]),
    "basketball": ("농구",     ["줄넘기 10분 + 점프 스쿼트", "실내 체육관"]),
    "volleyball": ("배구",     ["실내 체육관", "점프 스쿼트 + 어깨 스트레칭"]),
    "baseball":   ("야구",     ["실내 연습장", "몸통 비틀기 + 맨몸 근력"]),
    "ski":        ("스키·보드", ["스쿼트·런지 + 균형 잡기", "실내 자전거 20분"]),
    "surfing":    ("서핑",     ["플랭크 + 푸시업 + 균형 잡기", "수영(실내)"]),
    "skating":    ("스케이팅", ["실내 링크", "런지 + 한 발 서기"]),
    "walking":    ("걷기",     ["제자리 걷기 20분", "계단 오르기 10분", "러닝머신 걷기 25분"]),
}

# 당일 기록 종목(workout_items id) 중 밖에서 하는 것
OUTDOOR_ITEMS = {
    "walk": ("걷기", ["제자리 걷기 20분", "러닝머신 걷기 25분"]),
    "run":  ("러닝", ["러닝머신 25분", "계단 오르기 15분"]),
}

HOT = 33          # 폭염주의보 기준 (일 최고)
COLD = -5         # 이보다 낮으면 준비운동을 길게, 실내 권장
MUGGY_H, MUGGY_T = 85, 28


def verdict(날씨: dict | None) -> dict:
    """밖에서 해도 되는지. 실외 = 괜찮음 | 조심 | 실내.

    날씨를 모르면 '괜찮음' 이 아니라 '모름' 이다 — 모르는 걸 괜찮다고
    하지 않는다.
    """
    if not 날씨:
        return {"실외": "모름", "이유": []}
    이유 = []
    실외 = "괜찮음"
    하늘 = 날씨.get("하늘")
    강수 = 날씨.get("강수확률")
    최고, 최저, 습도 = 날씨.get("최고"), 날씨.get("최저"), 날씨.get("습도")

    if 하늘 in ("비", "눈", "뇌우"):
        실외 = "실내"; 이유.append(f"{하늘} 예보")
    elif 강수 is not None and 강수 >= 60:
        실외 = "실내"; 이유.append(f"비 올 확률 {int(강수)}%")
    if 최고 is not None and 최고 >= HOT:
        실외 = "실내"; 이유.append(f"한낮 {round(최고)}℃ — 폭염")
    if 최저 is not None and 최저 <= COLD:
        if 실외 == "괜찮음":
            실외 = "조심"
        이유.append(f"아침 {round(최저)}℃ — 준비운동을 길게")
    if (습도 is not None and 최고 is not None and 습도 >= MUGGY_H and 최고 >= MUGGY_T):
        if 실외 == "괜찮음":
            실외 = "조심"
        이유.append(f"습도 {int(습도)}% — 물을 자주")
    if 실외 == "괜찮음" and 강수 is not None and 30 <= 강수 < 60:
        실외 = "조심"; 이유.append(f"비 올 확률 {int(강수)}% — 실내 대안을 준비")
    return {"실외": 실외, "이유": 이유}


def outdoor_of(step: dict) -> tuple[str, list[str]] | None:
    """이 동작이 밖에서 하는 것이면 (이름, 대안들). 아니면 None."""
    출처 = step.get("출처")
    key = str(step.get("id") or "")
    if 출처 == "종목" and key in OUTDOOR_SPORTS:
        return OUTDOOR_SPORTS[key]
    if 출처 == "기록" and key in OUTDOOR_ITEMS:
        return OUTDOOR_ITEMS[key]
    return None


def alternatives(steps: list[dict], 날씨: dict | None) -> dict:
    """루틴의 밖에서 하는 동작마다, 오늘 날씨에 맞는 안내.

    괜찮으면 대안 없이 '밖에서 해도 좋아요'. 조심이면 대안을 곁들이고,
    실내면 대안을 앞세운다. 밖에서 하는 동작이 없으면 아무 말도 하지 않는다.
    """
    판정 = verdict(날씨)
    밖 = []
    for s in steps or []:
        found = outdoor_of(s)
        if found:
            이름, 대안들 = found
            밖.append({"동작": s.get("동작") or 이름, "대안": list(대안들)})
    out = {"판정": 판정, "실외동작": 밖, "대안": []}
    if not 밖 or 판정["실외"] in ("괜찮음", "모름"):
        return out
    까닭 = " · ".join(판정["이유"]) or "오늘 날씨"
    for x in 밖:
        out["대안"].append({"동작": x["동작"], "대신": x["대안"][0],
                          "또는": x["대안"][1:], "왜": 까닭,
                          "권함": "실내로" if 판정["실외"] == "실내" else "실내 대안도 준비"})
    return out


# 같은 날·같은 자리의 예보는 한 번만 받는다. 홈에 들어올 때마다 부르면
# 바깥 서비스를 하루에 수십 번 두드린다.
_cache: dict[tuple, tuple[_dt.date, dict | None]] = {}


def today_weather(위도=None, 경도=None) -> dict | None:
    오늘 = _dt.date.today()
    key = (round(위도, 1) if 위도 is not None else None, round(경도, 1) if 경도 is not None else None)
    hit = _cache.get(key)
    if hit and hit[0] == 오늘:
        return hit[1]
    w = ssn.fetch_weather(오늘, 위도, 경도)
    _cache[key] = (오늘, w)
    return w


def check(steps: list[dict], 위도=None, 경도=None) -> dict:
    """오늘 날씨 + 루틴의 밖에서 하는 동작에 대한 안내. 화면이 그대로 그린다."""
    w = today_weather(위도, 경도)
    out = alternatives(steps, w)
    out["날짜"] = _dt.date.today().isoformat()
    out["날씨"] = w
    return out
