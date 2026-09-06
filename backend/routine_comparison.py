"""동영상 표본의 품질, 중복, 조건별 루틴 구성 가능성을 비교한다."""

import json
import math
import re
from bisect import bisect_left, bisect_right
from collections import Counter
from dataclasses import asdict
from itertools import combinations
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .nfa_video_api import FIELDS, OPERATIONS, SOURCE_URL, SPEC_CHECKED_AT, Sample


def value_state(record: dict, name: str) -> str:
    """누락, null, 공백, 잘못된 타입, 유효 값을 구분한다."""
    if name not in record:
        return "missing"
    value = record[name]
    if value is None:
        return "null"
    if isinstance(value, str):
        return "blank" if not value.strip() else "valid"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "invalid"
    return "valid" if math.isfinite(value) else "invalid"


def duration_seconds(value, numeric_unit: str | None = None) -> float | None:
    """단위가 명시된 시간만 초로 바꾼다. 숫자의 단위는 추정하지 않는다."""
    if numeric_unit not in (None, "seconds", "minutes"):
        raise ValueError("숫자 단위는 seconds 또는 minutes만 지원합니다")
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    clock = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{2}(?:\.\d+)?)", text)
    if clock:
        hours, minutes, seconds = clock.groups()
        if float(seconds) >= 60 or (hours is not None and int(minutes) >= 60):
            return None
        result = int(hours or 0) * 3600 + int(minutes) * 60 + float(seconds)
    else:
        units = re.fullmatch(r"(?:(\d+(?:\.\d+)?)\s*분)?\s*(?:(\d+(?:\.\d+)?)\s*초)?", text)
        if units and any(units.groups()):
            result = float(units[1] or 0) * 60 + float(units[2] or 0)
        elif numeric_unit is not None:
            try:
                result = float(text) * (60 if numeric_unit == "minutes" else 1)
            except ValueError:
                return None
        else:
            return None
    return result if math.isfinite(result) and result > 0 else None


def video_identity(record: dict) -> str | None:
    """파일 URL을 보수적인 영상 식별자로 쓴다. 제목이나 행 순번은 쓰지 않는다."""
    value = record.get("file_url")
    if not isinstance(value, str):
        return None
    try:
        parts = urlsplit(value.strip())
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username:
            return None
        return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
    except ValueError:
        return None


def schema_comparison() -> list[dict]:
    """서버 필터 지원과 응답 제공 여부를 분리해 보여준다."""
    return [{"operation": operation.name, "title": operation.title,
             **{name: ("request+response" if name in operation.request_fields
                       else "response" if name in operation.response_fields else "absent")
                for name in FIELDS}}
            for operation in OPERATIONS]


def profile_sample(sample: Sample, numeric_unit: str | None = None) -> dict:
    """행 기준 품질과 URL 기준 고유 영상 수를 함께 집계한다."""
    records = sample.records
    count = len(records)
    profiles = {}
    for name in FIELDS:
        states = Counter(value_state(record, name) for record in records)
        values = Counter(str(record[name]).strip() for record in records
                         if value_state(record, name) == "valid")
        profiles[name] = {
            **{state: states[state] for state in ("missing", "null", "blank", "invalid", "valid")},
            "valid_rate": states["valid"] / count if count else None,
            "values": dict(values.most_common()),
        }
    identities = [identity for record in records if (identity := video_identity(record))]
    durations = [seconds for record in records
                 if (seconds := duration_seconds(record.get("vdo_len"), numeric_unit)) is not None]
    return {
        "operation": sample.operation, "collected_at": sample.collected_at,
        "total_count": sample.total_count, "row_count": count,
        "pages": sample.pages, "planned_pages": sample.planned_pages,
        "page_size": sample.page_size,
        "scope": "failed" if sample.error else "full" if sample.complete else "sample",
        "error": sample.error, "fields": profiles,
        "identified_rows": len(identities), "unique_videos": len(set(identities)),
        "unknown_identity_rows": count - len(identities),
        "duplicate_row_rate": 1 - len(set(identities)) / len(identities) if identities else None,
        "numeric_duration_unit": numeric_unit,
        "duration_parse_rate": len(durations) / count if count else None,
        "duration_min_seconds": min(durations) if durations else None,
        "duration_max_seconds": max(durations) if durations else None,
        "url_access": "not_checked", "browser_playback": "not_checked",
    }


def compare_overlap(samples: list[Sample]) -> list[dict]:
    """표본 내 교집합만 계산하며 수집 실패를 영상 부재로 해석하지 않는다."""
    output = []
    for left, right in combinations(samples, 2):
        left_ids = {identity for record in left.records if (identity := video_identity(record))}
        right_ids = {identity for record in right.records if (identity := video_identity(record))}
        union = left_ids | right_ids
        shared = left_ids & right_ids
        output.append({
            "left": left.operation, "right": right.operation,
            "scope": "partial_failure" if left.error or right.error
                     else "full" if left.complete and right.complete else "sample",
            "shared_videos": len(shared), "left_only": len(left_ids - right_ids),
            "right_only": len(right_ids - left_ids),
            "jaccard": len(shared) / len(union) if union else None,
        })
    return output


def evaluate_scenario(sample: Sample, allowed_values: dict[str, set[str]],
                      stage_values: dict[str, set[str]], target_seconds: tuple[int, int],
                      numeric_unit: str | None = None) -> dict:
    """명시한 값과 정확히 일치하는 영상을 골라 단계별 1개 조합을 탐색한다.

    여러 동작·세트 처방이나 저강도 판정을 하지 않는다. 부위의 부담 여부는
    메타데이터만으로 알 수 없으므로 검토한 허용 값만 호출자가 전달한다.
    """
    if set(allowed_values) - (set(FIELDS) - {"vdo_len", "trng_se_nm"}):
        raise ValueError("허용되지 않은 조건 필드입니다")
    if set(stage_values) != {"warmup", "main", "cooldown"}:
        raise ValueError("준비·본·정리 단계의 실제 분류값을 지정하세요")
    if any(not values for values in [*allowed_values.values(), *stage_values.values()]):
        raise ValueError("필터 값은 비어 있을 수 없습니다")
    if any(isinstance(values, str) for values in [*allowed_values.values(), *stage_values.values()]):
        raise ValueError("필터 값은 문자열 집합으로 전달하세요")
    low, high = target_seconds
    if not 0 < low <= high:
        raise ValueError("목표 시간 범위가 올바르지 않습니다")
    groups = {stage: {} for stage in stage_values}
    # 단계나 필터가 달라도 같은 URL의 길이는 일관되어야 한다.
    lengths_by_video = {}
    for record in sample.records:
        identity = video_identity(record)
        seconds = duration_seconds(record.get("vdo_len"), numeric_unit)
        if identity is not None and seconds is not None:
            lengths_by_video.setdefault(identity, set()).add(seconds)
    conflicting_videos = {identity for identity, lengths in lengths_by_video.items()
                          if len(lengths) > 1}
    matched = unknown = rejected = 0
    for record in sample.records:
        fields = [*allowed_values, "trng_se_nm"]
        if any(value_state(record, name) != "valid" for name in fields):
            unknown += 1
            continue
        if any(str(record[name]).strip() not in values for name, values in allowed_values.items()):
            rejected += 1
            continue
        stage_matches = [stage for stage, values in stage_values.items()
                         if str(record["trng_se_nm"]).strip() in values]
        identity = video_identity(record)
        seconds = duration_seconds(record.get("vdo_len"), numeric_unit)
        if len(stage_matches) != 1 or identity is None or seconds is None:
            unknown += 1
            continue
        matched += 1
        group = groups[stage_matches[0]]
        group.setdefault(identity, set()).add(seconds)
    # 같은 URL의 서로 다른 길이는 임의로 한 값을 선택하지 않는다.
    candidates = {stage: [(identity, next(iter(lengths))) for identity, lengths in videos.items()
                          if identity not in conflicting_videos]
                  for stage, videos in groups.items()}
    example = None
    cooldowns = sorted(candidates["cooldown"], key=lambda item: item[1])
    cooldown_lengths = [seconds for _, seconds in cooldowns]
    for warmup_id, warmup_length in candidates["warmup"]:
        for main_id, main_length in candidates["main"]:
            if main_id == warmup_id:
                continue
            subtotal = warmup_length + main_length
            start = bisect_left(cooldown_lengths, low - subtotal)
            end = bisect_right(cooldown_lengths, high - subtotal)
            for index in range(start, end):
                cooldown_id, cooldown_length = cooldowns[index]
                if cooldown_id in (warmup_id, main_id):
                    continue
                total = warmup_length + main_length + cooldown_length
                if low <= total <= high:
                    example = {"file_urls": [warmup_id, main_id, cooldown_id], "seconds": total}
                    break
            if example:
                break
        if example:
            break
    return {"matched_rows": matched, "unknown_rows": unknown, "rejected_rows": rejected,
            "stage_counts": {stage: len(videos) for stage, videos in candidates.items()},
            "duration_conflicts": len(conflicting_videos & {
                identity for videos in groups.values() for identity in videos
            }),
            "target_seconds": target_seconds, "example": example,
            "status": "partial_failure" if sample.error else "candidate_found" if example
                      else "not_found_in_observed_data",
            "scope": "full" if sample.complete else "sample",
            "limitation": "단계별 영상 1개 조합만 확인; 브라우저 재생·운동 적합성 미검증"}


def check_video_urls(sample: Sample, limit: int = 5, timeout: float = 10) -> list[dict]:
    """최대 limit개 URL을 HEAD로 확인한다. 접근 성공은 재생 성공이 아니다."""
    if limit < 1 or timeout <= 0:
        raise ValueError("검사 개수와 시간 제한은 양수여야 합니다")
    urls = list(dict.fromkeys(identity for record in sample.records
                             if (identity := video_identity(record))))[:limit]
    checks = []
    for url in urls:
        result = {"file_url": url, "browser_playback": "not_checked"}
        try:
            with urlopen(Request(url, method="HEAD"), timeout=timeout) as response:
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0]
                result.update(http_status=response.status, content_type=content_type,
                              status="video_header_accessible" if content_type.startswith("video/")
                              else "accessed_non_video_or_unknown_type")
        except HTTPError as error:
            result.update(http_status=error.code, status="head_not_supported" if error.code == 405
                          else "http_error")
        except (URLError, TimeoutError, OSError, ValueError):
            result["status"] = "connection_error"
        checks.append(result)
    return checks


def combine_samples(samples: list[Sample], numeric_units: dict[str, str] | None = None) -> Sample:
    """오퍼레이션 조합의 후보 행을 모으되 행 사이의 속성은 합치지 않는다."""
    if not samples or len({sample.operation for sample in samples}) != len(samples):
        raise ValueError("중복 없는 오퍼레이션 표본을 하나 이상 지정하세요")
    numeric_units = numeric_units or {}
    records = []
    for sample in samples:
        for record in sample.records:
            copied = dict(record)
            seconds = duration_seconds(record.get("vdo_len"), numeric_units.get(sample.operation))
            if seconds is not None:
                copied["vdo_len"] = f"{seconds}초"
            records.append(copied)
    errors = [sample.operation for sample in samples if sample.error]
    return Sample(
        operation=" + ".join(sample.operation for sample in samples),
        records=records,
        complete=all(sample.complete for sample in samples) and not errors,
        error="일부 오퍼레이션 수집 실패" if errors else None,
    )


def save_comparison(samples: list[Sample], data_dir: Path,
                    numeric_units: dict[str, str] | None = None) -> Path:
    """키와 원본 응답 없이 비교표와 허용 필드 표본을 DATA_DIR 아래 저장한다."""
    from .nfa_video_api import RETAINED_FIELDS

    numeric_units = numeric_units or {}
    report = {"source_url": SOURCE_URL, "spec_checked_at": SPEC_CHECKED_AT,
              "schema": schema_comparison(),
              "profiles": [profile_sample(sample, numeric_units.get(sample.operation)) for sample in samples],
              "overlap": compare_overlap(samples), "samples": [],
              "selection_status": "실데이터 품질·시나리오·재생 확인 후 담당자가 선별"}
    for sample in samples:
        saved = asdict(sample)
        saved["records"] = [{name: row[name] for name in RETAINED_FIELDS if name in row}
                            for row in sample.records]
        report["samples"].append(saved)
    destination = Path(data_dir) / "routine_player" / "comparison.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                           encoding="utf-8", newline="\n")
    return destination
