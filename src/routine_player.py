"""체력요인·부위·도구·장소로 영상을 고르고 단계별 루틴을 구성한다."""

import math
import re
from collections import Counter, deque
from copy import deepcopy
from dataclasses import dataclass, field

from .nfa_video_api import RETAINED_FIELDS
from .routine_comparison import duration_seconds, video_identity


PHASES = ("준비운동", "본운동", "정리운동")
FILTER_FIELDS = ("ftns_fctr_nm", "trng_part_nm", "tool_nm", "trng_plc_nm")
DEFAULT_SEPARATORS = ("/", ",", ";", "|", "·", "+")


@dataclass(frozen=True)
class VideoFilter:
    """None은 조건 미지정이다. 도구는 모두, 나머지 허용 조건은 하나 이상 충족한다."""

    factors: frozenset[str] | None = None
    parts: frozenset[str] | None = None
    excluded_parts: frozenset[str] = frozenset()
    tools: frozenset[str] | None = None
    places: frozenset[str] | None = None


@dataclass
class FilterResult:
    """통과 영상과 행 기준 제외·미확인 사유를 담는다."""

    videos: list[dict] = field(default_factory=list)
    rejected_count: int = 0
    unknown_count: int = 0
    reasons: dict[str, int] = field(default_factory=dict)

    def summary(self) -> dict:
        """영상 목록을 제외한 집계 결과를 반환한다. 한 행에 사유가 여럿일 수 있다."""
        return {"accepted": len(self.videos), "rejected": self.rejected_count,
                "unknown": self.unknown_count, "reasons": dict(self.reasons)}


@dataclass
class RoutineResult:
    """완성 여부, 부족한 단계, 순서가 있는 영상 목록과 시간 정보를 담는다."""

    steps: list[dict]
    status: str
    missing: dict[str, int]
    total_seconds: float | None
    unknown_duration_urls: list[str]
    duration_conflicts: list[str]
    diagnostics: dict


def _clean(value: str) -> str:
    """양끝과 반복 공백을 정리한다."""
    return " ".join(value.split())


def _validate_options(criteria: VideoFilter, aliases: dict, separators: tuple[str, ...]) -> None:
    """잘못된 조건이 조용히 무시되지 않도록 검사한다."""
    if not isinstance(criteria, VideoFilter):
        raise ValueError("필터 조건은 VideoFilter로 전달하세요")
    for name in ("factors", "parts", "tools", "places", "excluded_parts"):
        values = getattr(criteria, name)
        if values is None and name != "excluded_parts":
            continue
        if not isinstance(values, (set, frozenset)):
            raise ValueError("필터 값은 문자열 집합이어야 합니다")
        if not values and name != "excluded_parts":
            raise ValueError("조건 미지정에는 빈 집합 대신 None을 사용하세요")
        if any(not isinstance(value, str) or not _clean(value) for value in values):
            raise ValueError("필터 값에 공백이나 문자열이 아닌 값이 있습니다")
    if not isinstance(separators, tuple) or any(not isinstance(s, str) or not s for s in separators):
        raise ValueError("구분자는 비어 있지 않은 문자열의 튜플이어야 합니다")
    if set(aliases) - set(FILTER_FIELDS):
        raise ValueError("동의어는 지정된 네 필드에만 설정할 수 있습니다")
    for mapping in aliases.values():
        if not isinstance(mapping, dict) or any(
            not isinstance(value, str) or not _clean(value)
            for pair in mapping.items() for value in pair
        ):
            raise ValueError("동의어는 비어 있지 않은 문자열끼리 연결하세요")


def _tokens(value, mapping: dict[str, str], separators: tuple[str, ...]) -> frozenset[str] | None:
    """명시적 구분자와 동의어만 적용한다. 부분 문자열로 일치시키지 않는다."""
    if not isinstance(value, str) or not _clean(value):
        return None
    aliases = {_clean(key): _clean(target) for key, target in mapping.items()}
    text = aliases.get(_clean(value), _clean(value))
    pieces = re.split("|".join(re.escape(s) for s in separators), text) if separators else [text]
    if any(not _clean(piece) for piece in pieces):
        return None
    return frozenset(aliases.get(_clean(piece), _clean(piece)) for piece in pieces)


def filter_videos(records: list[dict], criteria: VideoFilter, *,
                  aliases: dict[str, dict[str, str]] | None = None,
                  separators: tuple[str, ...] = DEFAULT_SEPARATORS) -> FilterResult:
    """조건을 모두 적용하고 통과한 영상의 복사본과 제외 사유를 반환한다.

    실내를 집으로, 빈 도구를 맨몸으로 추정하지 않는다. 제외 부위는 메타데이터
    일치만 의미하며 의학적 금기나 운동 부담을 자동으로 판정하지 않는다.
    """
    aliases = aliases if aliases is not None else {}
    _validate_options(criteria, aliases, separators)
    requested = dict(zip(FILTER_FIELDS, (criteria.factors, criteria.parts, criteria.tools, criteria.places)))
    allowed = {}
    for name, values in requested.items():
        if values is not None:
            token_sets = [_tokens(value, aliases.get(name, {}), separators) for value in sorted(values)]
            if any(tokens is None for tokens in token_sets):
                raise ValueError("필터 조건에 해석할 수 없는 복합값이 있습니다")
            allowed[name] = frozenset().union(*token_sets)
    excluded = frozenset()
    for value in sorted(criteria.excluded_parts):
        tokens = _tokens(value, aliases.get("trng_part_nm", {}), separators)
        if tokens is None:
            raise ValueError("제외 부위에 해석할 수 없는 값이 있습니다")
        excluded |= tokens
    result = FilterResult()
    reasons = Counter()
    for record in records:
        if not isinstance(record, dict):
            result.unknown_count += 1
            reasons["invalid_record"] += 1
            continue
        required = set(allowed) | ({"trng_part_nm"} if excluded else set())
        parsed = {name: _tokens(record.get(name), aliases.get(name, {}), separators)
                  for name in required}
        # 금지 부위가 있으면 다른 허용 조건보다 먼저 제외한다.
        if excluded and parsed["trng_part_nm"] and parsed["trng_part_nm"] & excluded:
            result.rejected_count += 1
            reasons["excluded:trng_part_nm"] += 1
            continue
        missing = [f"unknown:{name}" for name in sorted(required) if parsed[name] is None]
        mismatches = []
        for name, values in allowed.items():
            actual = parsed[name]
            if actual is None:
                continue
            matches = actual <= values if name == "tool_nm" else bool(actual & values)
            if not matches:
                mismatches.append(f"mismatch:{name}")
        reasons.update(missing + mismatches)
        if mismatches:
            result.rejected_count += 1
        elif missing:
            result.unknown_count += 1
        else:
            result.videos.append({name: deepcopy(record[name]) for name in RETAINED_FIELDS if name in record})
    result.reasons = dict(sorted(reasons.items()))
    return result


def normalize_phase(value) -> str | None:
    """준비·본·정리와 운동 접미어, 공백 차이를 표준 단계명으로 통일한다."""
    if not isinstance(value, str):
        return None
    compact = "".join(value.split())
    return {"준비": PHASES[0], "준비운동": PHASES[0],
            "본": PHASES[1], "본운동": PHASES[1],
            "정리": PHASES[2], "정리운동": PHASES[2]}.get(compact)


def _assign_unique(candidates: dict[str, dict[str, dict]], counts: dict[str, int]) -> dict[int, str]:
    """이전 선택을 재배치해 가능한 조합을 놓치지 않는 중복 없는 배정을 한다."""
    slots = [phase for phase in PHASES for _ in range(counts[phase])]
    assigned = {}
    owners = {}
    for start in range(len(slots)):
        queue = deque([start])
        parents = {start: None}
        found = False
        while queue and not found:
            slot = queue.popleft()
            for identity in candidates[slots[slot]]:
                owner = owners.get(identity)
                if owner is None:
                    available = identity
                    current = slot
                    while current is not None:
                        previous = assigned.get(current)
                        assigned[current] = available
                        owners[available] = current
                        available = previous
                        current = parents[current]
                    found = True
                    break
                if owner not in parents:
                    parents[owner] = slot
                    queue.append(owner)
    return assigned


def build_video_routine(records: list[dict], *, criteria: VideoFilter | None = None,
                        phase_filters: dict[str, VideoFilter] | None = None,
                        counts: dict[str, int] | None = None,
                        aliases: dict[str, dict[str, str]] | None = None,
                        separators: tuple[str, ...] = DEFAULT_SEPARATORS,
                        numeric_unit: str | None = None) -> RoutineResult:
    """공통·단계별 조건을 적용해 준비→본→정리 순서의 영상 목록을 반환한다.

    기본은 단계별 한 개다. 시간 최적화나 처방 추천 없이 입력 순서에 따라
    결정적으로 선택한다. 단계가 부족하거나 길이가 미확인이면 총시간은 None이다.
    """
    duration_seconds(None, numeric_unit)
    criteria = criteria if criteria is not None else VideoFilter()
    phase_filters = phase_filters if phase_filters is not None else {}
    counts = dict(counts) if counts is not None else dict.fromkeys(PHASES, 1)
    if set(counts) != set(PHASES) or any(type(count) is not int or count < 1 for count in counts.values()):
        raise ValueError("준비·본·정리 세 단계의 개수를 양의 정수로 지정하세요")
    if set(phase_filters) - set(PHASES):
        raise ValueError("단계별 조건의 키는 준비운동·본운동·정리운동이어야 합니다")
    filtered = filter_videos(records, criteria, aliases=aliases, separators=separators)
    lengths = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        identity = video_identity(record)
        seconds = duration_seconds(record.get("vdo_len"), numeric_unit)
        if identity and seconds is not None:
            lengths.setdefault(identity, set()).add(seconds)
    conflicts = {identity for identity, values in lengths.items() if len(values) > 1}
    grouped = {phase: [] for phase in PHASES}
    invalid_phase = 0
    for record in filtered.videos:
        phase = normalize_phase(record.get("trng_se_nm"))
        if phase is None:
            invalid_phase += 1
        else:
            grouped[phase].append(record)
    candidates = {phase: {} for phase in PHASES}
    diagnostics = {"common_filter": filtered.summary(), "unknown_phase_rows": invalid_phase,
                   "phase_filters": {}, "invalid_url_rows": 0, "duplicate_rows": 0}
    for phase in PHASES:
        phase_result = filter_videos(grouped[phase], phase_filters.get(phase, VideoFilter()),
                                     aliases=aliases, separators=separators)
        diagnostics["phase_filters"][phase] = phase_result.summary()
        for record in phase_result.videos:
            identity = video_identity(record)
            if identity is None:
                diagnostics["invalid_url_rows"] += 1
            elif identity in conflicts:
                continue
            elif identity in candidates[phase]:
                diagnostics["duplicate_rows"] += 1
            else:
                candidates[phase][identity] = record
    assignments = _assign_unique(candidates, counts)
    slots = [phase for phase in PHASES for _ in range(counts[phase])]
    steps = []
    selected_counts = Counter()
    unknown_duration = []
    for slot in sorted(assignments):
        phase = slots[slot]
        identity = assignments[slot]
        record = candidates[phase][identity]
        seconds = duration_seconds(record.get("vdo_len"), numeric_unit)
        if seconds is None:
            unknown_duration.append(identity)
        steps.append({"order": len(steps) + 1, "phase": phase, "file_url": identity,
                      "video": record, "duration_seconds": seconds})
        selected_counts[phase] += 1
    missing = {phase: counts[phase] - selected_counts[phase] for phase in PHASES
               if selected_counts[phase] < counts[phase]}
    total = math.fsum(step["duration_seconds"] for step in steps) if not missing and not unknown_duration else None
    diagnostics["candidate_counts"] = {phase: len(videos) for phase, videos in candidates.items()}
    return RoutineResult(steps, "incomplete" if missing else "complete", missing, total,
                         unknown_duration, sorted(conflicts), diagnostics)
