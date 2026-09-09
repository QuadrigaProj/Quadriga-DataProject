"""200개 KSPO 루틴 — 불러오기 · 매일 순환 · 강도 · 컨디션 조정.

data/generated/routines_200_kspo_official_video.json을 기존 API 구조로 변환하여
연령대 × 목적 조합의 10개 루틴을 날짜에 따라 순환시켜 내보낸다.

    연령대 4 × 목적 5 = 20조합, 조합마다 루틴 10개(준비 1 · 본 3 · 마무리 1).
    Day 1→루틴1 … Day 10→루틴10 … Day 11→루틴1 (10일 주기).
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import re

try:
    from backend.paths import find_data
except ImportError:
    from paths import find_data

AGE_GROUPS = ( "유소년", "청소년", "성인", "어르신")
PURPOSES = ("다이어트", "기초 체력 증진", "재활 및 기능 회복", "수험생 체력 증진", "유연성 강화")
PARTS = ("무릎", "허리", "어깨")

_data: dict | None = None



def _official_info(raw: dict) -> dict | None:
    """공식 메타데이터를 API 응답 형식으로 변환하고 출처 원문도 보존한다."""
    values = raw.get("values", [])
    video_id = raw.get("youtube_id", "")
    if len(values) != 4 or not isinstance(video_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        return None
    factor, tool, part, age = values
    if age not in AGE_GROUPS or not raw.get("title"):
        return None
    # 호환 필드는 공식 목록에서 가져온 값이며 OpenAPI 운동명 매칭 결과가 아니다.
    metadata = {"aggrp_nm": age, "trng_nm": raw["title"], "ftns_fctr_nm": factor,
                "tool_nm": tool, "trng_part_nm": part, "vdo_ttl_nm": raw["title"]}
    code = "V" + hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
    return {"코드": code, "동작": raw["title"], "체력요인": [factor] if factor else [],
            "도구": tool or "미제공", "유형": "시간" if factor == "유연성" else "횟수",
            "부담부위": [], "부위검증됨": False, "kspo": metadata,
            "youtube_id": video_id, "official_video": raw}


def load() -> dict:
    """루틴 데이터를 한 번만 읽어 캐시한다."""
    global _data
    if _data is None:
        # 기존 파일은 수행량 설정만 사용하며 운동 후보는 가져오지 않는다.
        original = json.loads(find_data("routines_250.json").read_text(encoding="utf-8"))
        path = Path(__file__).resolve().parents[1] / "data/generated/routines_200_kspo_official_video.json"
        generated = json.loads(path.read_text(encoding="utf-8"))
        config = original["config"]
        for key in ("age_minutes", "reframe"):
            config[key] = {a: v for a, v in config[key].items() if a in AGE_GROUPS}
        for band in config["intensity"]["weeks"].values():
            band.pop("유아기", None)
        pools = {a: {p: {} for p in ("준비운동", "본운동", "정리운동")} for a in AGE_GROUPS}
        routines = {a: {p: [] for p in PURPOSES} for a in AGE_GROUPS}
        for entry in generated["routines"]:
            age = entry["aggrp_nm"]
            purpose = entry["purpose"].replace("기초체력", "기초 체력")
            routine = {"no": entry["day"], "name": f"{purpose} {entry['day']}일차", "prep": [], "main": [], "cool": [], "steps": []}
            for step in entry["steps"]:
                phase = step["role"]
                info = _official_info(step["official_video"])
                if info is None or step["official_video"]["values"][3] != age:
                    raise ValueError("공식 영상 루틴의 영상 ID 또는 연령 정보가 올바르지 않습니다.")
                code = info["코드"]
                pools[age][phase][code] = info
                routine[{"준비운동": "prep", "본운동": "main", "정리운동": "cool"}[phase]].append(code)
                routine["steps"].append(code)
            routines[age][purpose].append(routine)
        if any(len(items) != 10 for groups in routines.values() for items in groups.values()):
            raise ValueError("KSPO 루틴은 연령대·목적별 10개여야 합니다.")
        _data = {"_meta": {"샘플여부": False, "조합수": 20, "루틴수": 200},
                 "config": config, "pools": pools, "routines": routines}

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
        "youtube_id": info.get("youtube_id"),
        "official_video": info.get("official_video", {}),
        "부위검증됨": info.get("부위검증됨", True),
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
        if code in used or any(
            re.sub(r"\s+", "", info["동작"]) == re.sub(r"\s+", "", other["동작"])
            for phase_pool in load()["pools"][age_gbn].values()
            for other_code, other in phase_pool.items() if other_code in used
        ):
            continue
        if exclude and (not info.get("부위검증됨", True) or set(info.get("부담부위", [])) & exclude):
            continue
        if factors & set(info.get("체력요인", [])):
            return _step(age_gbn, "본운동", code)
    # 2순위: 체력요인 무시, 부담부위만 안전한 코드 (요인 조건을 먼저 완화)
    for code, info in pool.items():
        if code in used or any(
            re.sub(r"\s+", "", info["동작"]) == re.sub(r"\s+", "", other["동작"])
            for phase_pool in load()["pools"][age_gbn].values()
            for other_code, other in phase_pool.items() if other_code in used
        ):
            continue
        if (not exclude or info.get("부위검증됨", True)) and not (set(info.get("부담부위", [])) & exclude):
            return _step(age_gbn, "본운동", code)
    return None                     # 후보 없음 — 그래도 제외 조건은 풀지 않는다


def factor_units(value: str) -> set[str]:
    """복합 표기를 체력요소 단위로 나누고 협응력 동의어를 통일한다."""
    value = re.sub(r"\([^)]*\)", "", value).replace("협응력", "협응성")
    return {part.strip() for part in re.split(r"[·/,，&]+", value) if part.strip()}


def _has_factor(step: dict, factor: str) -> bool:
    """전체 문자열이 아닌 체력요소 단위의 교집합으로 매칭한다."""
    wanted = factor_units(factor)
    return any(wanted & factor_units(f) for f in step.get("체력요인", []))


def _sport_candidate(age_gbn: str, factors: list[str], used_names: set[str],
                     exclude: set[str], day: int, used_video_ids: set[str] | None = None) -> dict | None:
    """공식 목록에서 같은 연령·스포츠 체력요소·유효 영상 ID를 가진 후보를 고른다."""
    if exclude:
        return None
    path = Path(__file__).resolve().parents[1] / "data/processed/kspo_candidate_pool/official_video_catalog.json"
    try:
        records = json.loads(path.read_text(encoding="utf-8"))["items"]
    except (OSError, ValueError, KeyError):
        return None
    from backend.generate_kspo_routines import eligible
    wanted = set().union(*(factor_units(f) for f in factors))
    candidates = []
    for raw in records:
        info = _official_info(raw)
        if info is None or info["kspo"]["aggrp_nm"] != age_gbn or not eligible(info["kspo"]):
            continue
        name = re.sub(r"\s+", "", info["동작"]).casefold()
        if name in used_names or info["youtube_id"] in (used_video_ids or set()):
            continue
        if not wanted & factor_units(info["kspo"]["ftns_fctr_nm"] or ""):
            continue
        candidates.append(info)
    if not candidates:
        return None
    selected = min(candidates, key=lambda r: hashlib.sha256(
        (str(day) + json.dumps(r, ensure_ascii=False, sort_keys=True)).encode()).hexdigest())
    return dict(selected, 단계="본운동")


def _score(step: dict, prefer: list[str]) -> int:
    """선호 요인 몇 개를 건드리는 동작인가. 순서를 정하는 데만 쓴다."""
    return sum(1 for p in prefer if _has_factor(step, p))


def _prefer_substitute(age_gbn: str, factor: str, exclude: set[str],
                       used: set[str]) -> dict | None:
    """그 요인을 쓰는 본운동을 풀에서 하나 찾는다. 안전 조건은 그대로 지킨다."""
    pool = load()["pools"].get(age_gbn, {}).get("본운동", {})
    for code, info in pool.items():
        if code in used or any(
            re.sub(r"\s+", "", info["동작"]) == re.sub(r"\s+", "", other["동작"])
            for phase_pool in load()["pools"][age_gbn].values()
            for other_code, other in phase_pool.items() if other_code in used
        ):
            continue
        if exclude and (not info.get("부위검증됨", True) or set(info.get("부담부위", [])) & exclude):
            continue
        if _has_factor(info, factor):
            return _step(age_gbn, "본운동", code)
    return None


def build_program_routine(age_gbn: str, purpose: str, *, day: int = 0,
                          exclude_parts=None, heavy: bool = False,
                          prefer_factors=None) -> dict:
    """오늘의 루틴 한 벌 (준비 1 · 본 3 · 마무리 1).

    exclude_parts: 통증/제외 부위. heavy: 몸이 무거운 날.
    prefer_factors: 사용자가 고른 운동 종목이 많이 쓰는 체력요인.
        준비·정리와 본운동 첫 두 개를 유지하고 세 번째만 KSPO Pool에서 교체한다.
    """
    d = load()
    r = routine_for(age_gbn, purpose, day)
    exclude = {p for p in (exclude_parts or []) if p in PARTS}

    steps: list[dict] = [_step(age_gbn, "준비운동", c) for c in r["prep"]]

    used = set(r["steps"])
    dropped = []
    for c in r["main"]:
        s = _step(age_gbn, "본운동", c)
        if exclude and (not s.get("부위검증됨", True) or set(s["부담부위"]) & exclude):
            alt = _safe_substitute(age_gbn, s, exclude, used)
            if alt:
                used.add(alt["코드"])
                dropped.append({"원래": s["동작"], "대체": alt["동작"], "이유": "·".join(exclude & set(s["부담부위"])) + " 부담"})
                s = alt
            else:
                dropped.append({"원래": s["동작"], "대체": None, "이유": "안전한 대체 동작을 못 찾음 — 이 동작은 건너뛰세요"})
                continue
        steps.append(s)

    # 스포츠는 본운동 세 번째만 바꾼다. 나머지 위치와 순서는 유지한다.
    prefer = [f for f in (prefer_factors or []) if f]
    tuned: list[dict] = []
    mains = [i for i, step in enumerate(steps) if step["단계"] == "본운동"]
    if prefer and len(mains) == 3 and not heavy:
        names = {re.sub(r"\s+", "", step["동작"]).casefold() for step in steps}
        names.update(re.sub(r"\s+", "", _step(age_gbn, "정리운동", code)["동작"]).casefold()
                     for code in r["cool"])
        video_ids = {step.get("youtube_id") for step in steps}
        video_ids.update(_step(age_gbn, "정리운동", code).get("youtube_id") for code in r["cool"])
        replacement = _sport_candidate(age_gbn, prefer, names, exclude, day, video_ids)
        if replacement:
            index = mains[2]
            tuned.append({"바꾼것": {"원래": steps[index]["동작"], "대체": replacement["동작"]},
                          "이유": "선택 스포츠 관련 체력요소로 본운동 세 번째만 교체했습니다"})
            steps[index] = replacement

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
        "종목반영": tuned,
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
    gap = fitness_age - real_age
    if 11 <= real_age < 19:
        gap = -gap  # 성장기는 환산 나이가 높을수록 발달 수준이 높다.
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


AGE_NOTICE = "체력나이 분석은 만 11세 이상부터 이용할 수 있습니다.\n국민체력100 체력측정 데이터의 연령 범위에 따라 현재 서비스는 만 11세 이상을 지원합니다."


def age_group(age: float) -> str:
    """만 나이를 서비스 루틴 연령대로 변환한다."""
    import math
    if not math.isfinite(age) or age < 11:
        raise ValueError(AGE_NOTICE)
    return "어르신" if age >= 65 else "성인" if age >= 19 else "청소년" if age >= 13 else "유소년"
