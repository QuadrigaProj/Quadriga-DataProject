"""250개 고정 루틴 — 불러오기 · 매일 순환 · 강도 · 컨디션 조정.

이 모듈은 루틴을 **새로 만들지 않는다.** data/sample/routines_250.json
(정식 데이터가 있으면 data/processed/routines_250.json) 을 그대로 읽어
연령대 × 목적 조합의 10개 루틴을 날짜에 따라 순환시켜 내보낸다.

    연령대 5 × 목적 5 = 25조합, 조합마다 루틴 10개(준비 1 · 본 3 · 마무리 1).
    Day 1→루틴1 … Day 10→루틴10 … Day 11→루틴1 (10일 주기).
"""
from __future__ import annotations

import json

try:
    from backend.paths import find_data
except ImportError:
    from paths import find_data

AGE_GROUPS = ("유아기", "유소년", "청소년", "성인", "어르신")
PURPOSES = ("다이어트", "기초 체력 증진", "재활 및 기능 회복", "수험생 체력 증진", "유연성 강화")
PARTS = ("무릎", "허리", "어깨")

_data: dict | None = None


def load() -> dict:
    """루틴 데이터를 한 번만 읽어 캐시한다."""
    global _data
    if _data is None:
        _data = json.loads(find_data("routines_250.json").read_text(encoding="utf-8"))
    return _data


def is_sample() -> bool:
    return bool(load().get("_meta", {}).get("샘플여부"))


# ---------------------------------------------------------------------------
# 순환
# ---------------------------------------------------------------------------

def cycle_index(day: int, cycle: int = 10) -> int:
    """0-based 경과일 → 1..cycle 루틴 번호. Day 1 = day 0."""
    return (max(0, int(day)) % cycle) + 1


def routine_for(age_gbn: str, purpose: str, day: int) -> dict:
    d = load()
    combos = d["routines"].get(age_gbn)
    if not combos:
        raise KeyError(f"연령대 '{age_gbn}' 루틴이 없습니다.")
    rs = combos.get(purpose) or combos.get("기초 체력 증진")
    if not rs:
        raise KeyError(f"'{age_gbn} × {purpose}' 루틴이 없습니다.")
    cyc = d["config"].get("cycle_days", 10)
    no = cycle_index(day, cyc)
    return next((r for r in rs if r["no"] == no), rs[0])


# ---------------------------------------------------------------------------
# 코드 → 동작
# ---------------------------------------------------------------------------

_PHASE_KEY = {"prep": "준비운동", "main": "본운동", "cool": "정리운동"}


def _lookup(age_gbn: str, phase: str, code: str) -> dict | None:
    return load()["pools"].get(age_gbn, {}).get(phase, {}).get(code)


def _step(age_gbn: str, phase: str, code: str) -> dict:
    info = _lookup(age_gbn, phase, code) or {}
    return {
        "코드": code,
        "단계": phase,
        "동작": info.get("동작", code),
        "체력요인": info.get("체력요인", []),
        "도구": info.get("도구", "맨몸"),
        "유형": info.get("유형", "횟수"),
        "부담부위": info.get("부담부위", []),
        "kspo": info.get("kspo", {}),
    }


# ---------------------------------------------------------------------------
# 컨디션 · 부위 조정 (안전 조건은 절대 완화하지 않는다)
# ---------------------------------------------------------------------------

def _safe_substitute(age_gbn: str, step: dict, exclude: set[str], used: set[str]) -> dict | None:
    """본운동 step 의 부담부위가 제외 부위와 겹치면 같은 체력요인의 다른 본운동으로 교체."""
    factors = set(step["체력요인"])
    pool = load()["pools"].get(age_gbn, {}).get("본운동", {})
    # 1순위: 체력요인이 겹치고 부담부위가 제외와 안 겹치는 코드
    for code, info in pool.items():
        if code in used:
            continue
        if set(info.get("부담부위", [])) & exclude:
            continue
        if factors & set(info.get("체력요인", [])):
            return _step(age_gbn, "본운동", code)
    # 2순위: 체력요인 무시, 부담부위만 안전한 코드 (요인 조건을 먼저 완화)
    for code, info in pool.items():
        if code in used:
            continue
        if not (set(info.get("부담부위", [])) & exclude):
            return _step(age_gbn, "본운동", code)
    return None                     # 후보 없음 — 그래도 제외 조건은 풀지 않는다


def build_program_routine(age_gbn: str, purpose: str, *, day: int = 0,
                          exclude_parts=None, heavy: bool = False) -> dict:
    """오늘의 루틴 한 벌 (준비 1 · 본 3 · 마무리 1).

    exclude_parts: 통증/제외 부위. heavy: 몸이 무거운 날.
    """
    d = load()
    r = routine_for(age_gbn, purpose, day)
    exclude = {p for p in (exclude_parts or []) if p in PARTS}

    steps: list[dict] = [_step(age_gbn, "준비운동", c) for c in r["prep"]]

    used = set(r["main"])
    dropped = []
    for c in r["main"]:
        s = _step(age_gbn, "본운동", c)
        if exclude and (set(s["부담부위"]) & exclude):
            alt = _safe_substitute(age_gbn, s, exclude, used)
            if alt:
                used.add(alt["코드"])
                dropped.append({"원래": s["동작"], "대체": alt["동작"], "이유": "·".join(exclude & set(s["부담부위"])) + " 부담"})
                s = alt
            else:
                dropped.append({"원래": s["동작"], "대체": None, "이유": "안전한 대체 동작을 못 찾음 — 이 동작은 건너뛰세요"})
                continue
        steps.append(s)

    main_steps = [s for s in steps if s["단계"] == "본운동"]
    if heavy:
        hd = d["config"]["intensity"]["heavy_day"]
        keep = {id(s) for s in main_steps[: hd["main_count"]]}
        steps = [s for s in steps if s["단계"] != "본운동" or id(s) in keep]

    steps += [_step(age_gbn, "정리운동", c) for c in r["cool"]]

    lo, hi = d["config"]["age_minutes"].get(age_gbn, [10, 15])
    return {
        "연령대": age_gbn,
        "목적": purpose,
        "재프레이밍": d["config"]["reframe"].get(age_gbn, {}).get(purpose, purpose),
        "루틴번호": r["no"],
        "루틴명": r["name"],
        "주기일수": d["config"].get("cycle_days", 10),
        "예상시간분": [lo, hi] if not heavy else [max(3, lo - 3), hi - 3],
        "몸무거운날": heavy,
        "대체": dropped,
        "steps": [dict(s, 순서=i + 1) for i, s in enumerate(steps)],
        "안전문구": d["config"].get("safety_note", ""),
        "샘플": is_sample(),
    }


# ---------------------------------------------------------------------------
# 강도 (12주 = 3구간, 현재 체력이 낮으면 한 단계 낮춰 시작)
# ---------------------------------------------------------------------------

def _band(week: int) -> str:
    if week <= 4:
        return "1-4"
    if week <= 8:
        return "5-8"
    return "9-12"


def start_offset(fitness_age: float | None, real_age: float | None,
                 focus_areas: list[str] | None = None) -> int:
    """현재 체력 수준 → 시작 강도 보정.
    -1 = 한 단계 낮게, 0 = 기본, +1 = 한 단계 높게.
    체력이 안 좋은 사람에게 더 센 운동을 주지 않는다.
    """
    if fitness_age is None or real_age is None:
        return -1 if (focus_areas) else 0
    gap = fitness_age - real_age                 # 양수 = 또래보다 나이 들어 보임(체력 낮음)
    if gap >= 7 or (focus_areas and len(focus_areas) >= 2):
        return -1
    if gap <= -7:
        return 1
    return 0


def intensity_for(age_gbn: str, week: int, *, offset: int = 0, heavy: bool = False) -> dict:
    """주차 + 보정 → 이번 수행량."""
    d = load()
    bands = ["1-4", "5-8", "9-12"]
    idx = bands.index(_band(max(1, int(week))))
    idx = max(0, min(len(bands) - 1, idx + offset))     # 보정은 구간을 당기거나 미룬다
    conf = d["config"]["intensity"]["weeks"][bands[idx]]
    per_age = conf.get(age_gbn, {})
    time = conf.get("시간형", {})
    sets = per_age.get("sets", time.get("sets", 2))
    reps = per_age.get("reps")
    sec = time.get("sec", 30)
    rnd = per_age.get("round")
    if heavy:
        hd = d["config"]["intensity"]["heavy_day"]
        sets = hd["sets"]                       # 모든 세트 1세트
        sec = round(sec * hd["time_ratio"])     # 시간형 운동은 시간 절반
    out = {"주차": int(week), "구간": bands[idx], "세트": sets, "시간초": sec}
    if reps is not None:
        out["반복"] = reps
    if rnd is not None:
        out["라운드"] = rnd
    return out
