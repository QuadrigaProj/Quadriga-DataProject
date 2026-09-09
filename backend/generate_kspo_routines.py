"""저장된 KSPO 후보로 4개 연령대의 10일 루틴을 생성한다.

실행: python -m backend.generate_kspo_routines
준비·정리는 유연성 후보를 배치한 생성 역할이며 API 운동단계로 주장하지 않는다.
1순위가 부족하면 확정된 2순위 안에서만 고른다. 두 순위가 모두 없으면 실패한다.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

AGES = ("유소년", "청소년", "성인", "어르신")
STRENGTH = ("근력", "근지구력", "근력/근지구력")
MAPPINGS = {
    "다이어트": (("심폐지구력",), STRENGTH, ()),
    "기초체력 증진": (STRENGTH, ("심폐지구력",), ("PAPS 4-5등급 학생 체력증진",)),
    "재활 및 기능 회복": (("유연성",), ("평형성",), ("직장인 뭉친 어깨 예방", "직장인 다리 부종 예방")),
    "수험생 체력 증진": (STRENGTH, ("유연성",), ("PAPS 4-5등급 학생 체력증진",)),
    "유연성 강화": (("유연성",), ("평형성",), ("직장인 뭉친 어깨 예방",)),
}
# 측정 안내와 측정 장비는 이름·제목·설명·도구에서 검사한다.
EXCLUDED = re.compile(r"체력측정|체력인증|측정방법|측정 방법|측정기|측정장비|측정 장비|악력계|체성분측정|인바디|스텝검사|측정 설명|제도 안내|기구 사용법", re.I)
# 용도가 불명확한 기구와 고정식 기구도 보수적으로 제외한다.
EQUIPMENT = re.compile(r"헬스기구|머신|고정식|트레드밀|자전거|악력계|측정|인바디", re.I)
FIELDS = ("aggrp_nm", "trng_nm", "ftns_fctr_nm", "trng_se_nm", "trng_part_nm", "trng_aim_nm", "tool_nm", "vdo_desc", "vdo_ttl_nm", "file_nm")


def eligible(record: dict) -> bool:
    """실제 이름과 대상 연령이 있으며 측정·장비 제외 조건에 걸리지 않는지 검사한다."""
    if record.get("aggrp_nm") not in AGES or not str(record.get("trng_nm") or "").strip():
        return False
    text = " ".join(str(record.get(key) or "") for key in ("trng_nm", "vdo_ttl_nm", "vdo_desc", "tool_nm"))
    return not EXCLUDED.search(text) and not EQUIPMENT.search(text)


def identity(record: dict) -> str:
    """띄어쓰기만 다른 같은 운동도 하루 안에서는 중복으로 취급한다."""
    return re.sub(r"\s+", "", record["trng_nm"]).casefold()


def choose(records: list[dict], used: set[str], counts: Counter, salt: str,
           primary: tuple = (), aims: tuple = ()) -> dict:
    """10일간 덜 사용한 운동을 우선하고 동률이면 목적 우선순위를 적용한다."""
    options = [r for r in records if identity(r) not in used]
    if not options:
        raise ValueError("중복 없는 하루 운동을 구성할 후보가 부족합니다.")
    def rank(record):
        encoded = json.dumps(record, ensure_ascii=False, sort_keys=True)
        tie = hashlib.sha256((salt + encoded).encode("utf-8")).hexdigest()
        return (counts[identity(record)], record.get("ftns_fctr_nm") not in primary,
                record.get("trng_aim_nm") not in aims, tie)
    selected = min(options, key=rank)
    used.add(identity(selected))
    counts[identity(selected)] += 1
    return selected


def generate(records: list[dict]) -> dict:
    """원본 필드는 보존하고 생성 역할을 별도 키에 두어 200개를 만든다."""
    candidates = [r for r in records if eligible(r)]
    routines = []
    coverage = []
    for age in AGES:
        age_rows = [r for r in candidates if r["aggrp_nm"] == age]
        stretches = [r for r in age_rows if r.get("ftns_fctr_nm") == "유연성"]
        for purpose, (primary, secondary, aims) in MAPPINGS.items():
            mains = [r for r in age_rows if r.get("ftns_fctr_nm") in primary + secondary]
            coverage.append({"aggrp_nm": age, "purpose": purpose,
                             "primary_unique": len({identity(r) for r in mains if r.get("ftns_fctr_nm") in primary}),
                             "secondary_unique": len({identity(r) for r in mains if r.get("ftns_fctr_nm") in secondary})})
            main_counts, stretch_counts = Counter(), Counter()
            for day in range(1, 11):
                used = set()
                selected = [choose(mains, used, main_counts, f"{age}/{purpose}/{day}/{i}", primary, aims) for i in range(3)]
                prep = choose(stretches, used, stretch_counts, f"{age}/{purpose}/{day}/prep")
                cool = choose(stretches, used, stretch_counts, f"{age}/{purpose}/{day}/cool")
                steps = [{"role": role, "kspo": {k: r.get(k) for k in FIELDS}}
                         for role, r in zip(("준비운동", "본운동", "본운동", "본운동", "정리운동"), [prep, *selected, cool])]
                routines.append({"aggrp_nm": age, "purpose": purpose, "day": day, "steps": steps})
    result = {"metadata": {"routine_count": len(routines), "cycle_days": 10,
              "stage_policy": "준비·정리는 유연성 후보를 배치한 생성 역할. 원본 trng_se_nm은 변경하지 않음",
              "selection_policy": "사용 횟수 분산 후 1순위 체력요소와 운동목적 일치 우대. 부족 시 2순위만 활용",
              "clinical_validation": False, "coverage": coverage}, "routines": routines}
    validate(result, records)
    return result


def validate(result: dict, source: list[dict]) -> None:
    """개수·출처·목적·연령·하루 중복·제외 조건을 검증한다."""
    signatures = {json.dumps({k: r.get(k) for k in FIELDS}, sort_keys=True, ensure_ascii=False) for r in source}
    routines = result["routines"]
    assert len(routines) == 200
    assert {(r["aggrp_nm"], r["purpose"], r["day"]) for r in routines} == {(a, p, d) for a in AGES for p in MAPPINGS for d in range(1, 11)}
    for routine in routines:
        steps = routine["steps"]
        assert [s["role"] for s in steps] == ["준비운동", "본운동", "본운동", "본운동", "정리운동"]
        assert len({identity(s["kspo"]) for s in steps}) == 5
        first, second, _ = MAPPINGS[routine["purpose"]]
        for step in steps:
            r = step["kspo"]
            assert eligible(r) and r["aggrp_nm"] == routine["aggrp_nm"]
            assert json.dumps(r, sort_keys=True, ensure_ascii=False) in signatures
            assert r["ftns_fctr_nm"] in (first + second if step["role"] == "본운동" else ("유연성",))


def main() -> None:
    """저장된 후보만 읽고 검증이 모두 끝난 뒤 새 결과 파일을 저장한다."""
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=root / "data/processed/kspo_candidate_pool/candidates.json")
    parser.add_argument("--output", type=Path, default=root / "data/generated/routines_200_kspo.json")
    args = parser.parse_args()
    if args.output.resolve() == args.input.resolve() or args.output.name == "routines_250.json":
        parser.error("입력 또는 기존 250개 원본을 출력으로 사용할 수 없습니다.")
    records = json.loads(args.input.read_text(encoding="utf-8"))
    result = generate(records)
    result["metadata"]["source_sha256"] = hashlib.sha256(args.input.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(len(result["routines"]))


if __name__ == "__main__":
    main()
