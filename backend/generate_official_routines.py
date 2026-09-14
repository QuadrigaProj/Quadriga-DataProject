"""공식 영상 목록으로 새 목적의 KSPO 루틴을 만들어 routines_200_kspo_official_video.json 에 덧붙인다.

실행: python -m backend.generate_official_routines --purposes 벌크업 "근육량 늘리기" "지구력 늘리기"

이미 있는 목적의 루틴은 건드리지 않는다 (재현성 — 사용자가 보던 루틴이 바뀌면 안 된다).
정책은 기존 파일과 같다: 준비·정리운동은 공식 유연성 영상, 본운동 3개는 목적의 1순위 체력요소를 우대하고
10일 동안 덜 쓴 영상을 먼저 쓰며, 하루 안에 같은 영상을 두 번 넣지 않는다. 동률은 해시로 갈라 언제 돌려도 같다.
새 목적은 기구도 우대한다 — 벌크업은 무거운 기구, 근육량 늘리기는 프리웨이트·밴드, 지구력 늘리기는 맨몸.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

AGES = ("유소년", "청소년", "성인", "어르신")
DAYS = 10
ID_RE = r"[A-Za-z0-9_-]{11}"          # 유튜브 영상 ID (목록에 10자짜리 잘못된 것이 하나 있다)
# 목적 → (1순위 체력요소, 2순위 체력요소, 우대 기구). 공식 목록의 체력항목 표기를 그대로 쓴다.
NEW_PURPOSES = {
    "벌크업": {"primary": ["근력/근지구력"], "secondary": ["민첩성/순발력"], "tools": ["웨이트기계", "프리웨이트"]},
    "근육량 늘리기": {"primary": ["근력/근지구력"], "secondary": ["심폐지구력"], "tools": ["프리웨이트", "밴드", "맨몸/밴드", "탄력밴드"]},
    "지구력 늘리기": {"primary": ["심폐지구력"], "secondary": ["근력/근지구력"], "tools": ["맨몸", "스텝박스", "줄넘기", "스텝퍼"]},
}
ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data/processed/kspo_candidate_pool/official_video_catalog.json"
OUTPUT = ROOT / "data/generated/routines_200_kspo_official_video.json"


def identity(item: dict) -> str:
    """띄어쓰기만 다른 같은 영상은 하루 안에서 중복으로 본다."""
    return re.sub(r"\s+", "", item["title"]).casefold()


def choose(items: list[dict], used: set[str], counts: Counter, salt: str,
           primary=(), tools=()) -> dict:
    """덜 쓴 영상 → 1순위 요소 → 우대 기구 → 해시 순으로 고른다."""
    options = [i for i in items if identity(i) not in used]
    if not options:
        raise ValueError("중복 없는 하루 운동을 구성할 영상이 부족합니다.")

    def rank(item):
        tie = hashlib.sha256((salt + json.dumps(item, ensure_ascii=False, sort_keys=True)).encode("utf-8")).hexdigest()
        return (counts[identity(item)], item["values"][0] not in primary, item["values"][1] not in tools, tie)

    picked = min(options, key=rank)
    used.add(identity(picked))
    counts[identity(picked)] += 1
    return picked


def step(role: str, item: dict) -> dict:
    return {"role": role, "name": item["title"], "youtube_id": item["youtube_id"], "official_video": item}


def generate(catalog: list[dict], purposes: dict, existing: set[tuple[str, str]]) -> list[dict]:
    """(연령대, 목적) 조합마다 10일 루틴. 이미 있는 조합은 건너뛴다."""
    out = []
    for age in AGES:
        rows = [i for i in catalog if i["values"][3] == age and re.fullmatch(ID_RE, i.get("youtube_id") or "")]   # 유튜브 ID 가 온전한 영상만
        stretches = [i for i in rows if i["values"][0] == "유연성"]
        for purpose, spec in purposes.items():
            if (age, purpose) in existing:
                continue
            primary, secondary, tools = tuple(spec["primary"]), tuple(spec["secondary"]), tuple(spec["tools"])
            mains = [i for i in rows if i["values"][0] in primary + secondary]
            if len(mains) < 3 or len(stretches) < 2:
                raise ValueError(f"{age} × {purpose}: 영상이 모자랍니다 (본운동 {len(mains)}, 유연성 {len(stretches)})")
            main_counts, stretch_counts = Counter(), Counter()
            for day in range(1, DAYS + 1):
                used: set[str] = set()
                picked = [choose(mains, used, main_counts, f"{age}/{purpose}/{day}/{i}", primary, tools) for i in range(3)]
                prep = choose(stretches, used, stretch_counts, f"{age}/{purpose}/{day}/prep")
                cool = choose(stretches, used, stretch_counts, f"{age}/{purpose}/{day}/cool")
                steps = [step("준비운동", prep), *(step("본운동", p) for p in picked), step("정리운동", cool)]
                out.append({"aggrp_nm": age, "purpose": purpose, "day": day, "steps": steps})
    return out


def validate(routines: list[dict], purposes: dict) -> None:
    """개수·역할·하루 중복·체력요소·영상 ID 를 검증한다."""
    for purpose in purposes:
        for age in AGES:
            days = [r for r in routines if r["aggrp_nm"] == age and r["purpose"] == purpose]
            assert len(days) == DAYS and sorted(r["day"] for r in days) == list(range(1, DAYS + 1)), (age, purpose)
    for r in routines:
        if r["purpose"] not in purposes:
            continue
        spec = purposes[r["purpose"]]
        assert [s["role"] for s in r["steps"]] == ["준비운동", "본운동", "본운동", "본운동", "정리운동"]
        assert len({identity(s["official_video"]) for s in r["steps"]}) == 5
        for s in r["steps"]:
            v = s["official_video"]
            assert v["values"][3] == r["aggrp_nm"] and re.fullmatch(ID_RE, v["youtube_id"] or "")
            allowed = ("유연성",) if s["role"] != "본운동" else tuple(spec["primary"]) + tuple(spec["secondary"])
            assert v["values"][0] in allowed, (r["aggrp_nm"], r["purpose"], s["name"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--purposes", nargs="+", default=list(NEW_PURPOSES), help="덧붙일 목적 (NEW_PURPOSES 에 있는 것)")
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    purposes = {p: NEW_PURPOSES[p] for p in args.purposes}
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))["items"]
    data = json.loads(args.output.read_text(encoding="utf-8"))
    existing = {(r["aggrp_nm"], r["purpose"]) for r in data["routines"]}
    added = generate(catalog, purposes, existing)
    data["routines"].extend(added)
    validate(data["routines"], purposes)
    meta = data["metadata"]
    meta["routine_count"] = len(data["routines"])
    for p, spec in purposes.items():
        meta.setdefault("purpose_factors", {})[p] = {"primary": spec["primary"], "secondary": spec["secondary"], "tools": spec["tools"]}
    meta["extended_purposes"] = {"목적": sorted({r["purpose"] for r in data["routines"] if r["purpose"] in NEW_PURPOSES}),
                                 "policy": "backend/generate_official_routines.py — 기존 목적과 같은 정책에 우대 기구를 더함. 기존 루틴은 그대로"}
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(added)}개 추가, 전체 {len(data['routines'])}개")


if __name__ == "__main__":
    main()
