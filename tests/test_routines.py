"""200 KSPO 루틴 — 로더·순환·강도·컨디션 조정 테스트.

루틴 데이터(data/sample/routines_250.json)는 저장소에 함께 커밋된 샘플이다.
정식 데이터는 data/processed/ 에 같은 스키마로 넣으면 우선 사용된다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import routines as rt          # noqa: E402
from backend.main import app                # noqa: E402

client = TestClient(app)


def test_데이터_20조합_200루틴():
    d = rt.load()
    assert d["_meta"]["조합수"] == 20
    assert d["_meta"]["루틴수"] == 200
    for a in rt.AGE_GROUPS:
        for p in rt.PURPOSES:
            rs = d["routines"][a][p]
            assert len(rs) == 10
            for r in rs:
                assert (len(r["prep"]), len(r["main"]), len(r["cool"])) == (1, 3, 1)


def test_모든_루틴_코드가_풀에_있다():
    d = rt.load()
    for a in rt.AGE_GROUPS:
        for p in rt.PURPOSES:
            for r in d["routines"][a][p]:
                for c in r["prep"]:
                    assert c in d["pools"][a]["준비운동"]
                for c in r["main"]:
                    assert c in d["pools"][a]["본운동"]
                for c in r["cool"]:
                    assert c in d["pools"][a]["정리운동"]


def test_10일_주기_순환():
    assert rt.cycle_index(0) == 1
    assert rt.cycle_index(9) == 10
    assert rt.cycle_index(10) == 1
    assert rt.cycle_index(89) == 10          # 3개월 마지막 날
    a, p = "성인", "다이어트"
    assert rt.routine_for(a, p, 0)["no"] == 1
    assert rt.routine_for(a, p, 10)["no"] == 1
    assert rt.routine_for(a, p, 13)["no"] == 4


def test_제외부위는_후보가_없어도_완화하지_않는다():
    """무릎·허리·어깨를 전부 제외해도 그 부위 부담 동작이 본운동에 남으면 안 된다."""
    for a in rt.AGE_GROUPS:
        r = rt.build_program_routine(a, "기초 체력 증진", day=0,
                                     exclude_parts=["무릎", "허리", "어깨"])
        for s in r["steps"]:
            if s["단계"] == "본운동":
                assert not (set(s["부담부위"]) & {"무릎", "허리", "어깨"}), (a, s)


def test_몸무거운날_본운동_2개():
    r = rt.build_program_routine("성인", "다이어트", day=0, heavy=True)
    mains = [s for s in r["steps"] if s["단계"] == "본운동"]
    assert len(mains) == 2
    assert r["예상시간분"][1] < rt.load()["config"]["age_minutes"]["성인"][1]


def test_강도_12주_3구간():
    assert rt.intensity_for("청소년", 3)["구간"] == "1-4"
    assert rt.intensity_for("청소년", 6)["구간"] == "5-8"
    assert rt.intensity_for("청소년", 11)["구간"] == "9-12"
    # 영상 기반 구조 — 세트 수만 쓴다. 1~4·5~8주 2세트, 9~12주 3세트.
    assert rt.intensity_for("성인", 2)["세트"] == 2
    assert rt.intensity_for("성인", 6)["세트"] == 2
    assert rt.intensity_for("성인", 10)["세트"] == 3
    # 반복·시간·라운드는 더 이상 돌려주지 않는다
    assert set(rt.intensity_for("성인", 2)) == {"주차", "구간", "세트"}


def test_체력_낮으면_시작_강도를_낮춘다():
    assert rt.start_offset(55, 45) == -1          # 체력나이가 실제보다 훨씬 높음
    assert rt.start_offset(45, 45) == 0
    assert rt.start_offset(38, 45) == 1
    assert rt.start_offset(None, None, focus_areas=["유연성", "근력"]) == -1
    # 낮은 체력이면 같은 주차라도 세트가 기본보다 적거나 같다
    낮음 = rt.intensity_for("성인", 10, offset=-1)
    기본 = rt.intensity_for("성인", 10, offset=0)
    assert 낮음["세트"] <= 기본["세트"]


def test_몸무거운날은_기본세트에서_한_세트_줄인다():
    # 9~12주 3세트 → 몸이 무거운 날 2세트
    assert rt.intensity_for("어르신", 10, heavy=True)["세트"] == 2
    assert rt.intensity_for("어르신", 10, heavy=False)["세트"] == 3
    # 1~4·5~8주 2세트 → 몸이 무거운 날 1세트 (최소 1세트)
    assert rt.intensity_for("어르신", 6, heavy=True)["세트"] == 1
    assert rt.intensity_for("어르신", 1, heavy=True)["세트"] == 1
    # 시간 감소 로직 제거 — 시간초 키 자체가 없다
    assert "시간초" not in rt.intensity_for("어르신", 6, heavy=True)


# ---------- API ----------

def test_program_routine_엔드포인트():
    b = client.get("/program/routine", params={
        "age_gbn": "성인", "purpose": "다이어트", "day": 0, "week": 1}).json()
    assert b["루틴번호"] == 1
    assert [s["단계"] for s in b["steps"]] == ["준비운동", "본운동", "본운동", "본운동", "정리운동"]
    assert b["안전문구"]
    assert "강도" in b


def test_program_routine_유아기_차단():
    response = client.get("/program/routine", params={
        "age_gbn": "유아기", "purpose": "유연성 강화", "day": 2, "week": 1})
    assert response.status_code == 422


def test_program_purposes_재프레이밍():
    b = client.get("/program/purposes", params={"age_gbn": "어르신"}).json()
    재활 = next(x for x in b if x["목적"] == "재활 및 기능 회복")
    assert 재활["표시명"] == "낙상 예방 중심"


def test_program_routine_제외부위_반영():
    b = client.get("/program/routine", params={
        "age_gbn": "성인", "purpose": "기초 체력 증진", "day": 1,
        "exclude_parts": "무릎,허리,어깨"}).json()
    for s in b["steps"]:
        if s["단계"] == "본운동":
            assert not (set(s["부담부위"]) & {"무릎", "허리", "어깨"})


def test_program_routine_exclude_parts_없이_heavy만_보내도_가볍게_돌려준다():
    """C9: 화면이 실제로 보내는 모양(heavy 만, exclude_parts 없음)으로도 가볍게 돌아온다."""
    b = client.get("/program/routine", params={
        "age_gbn": "성인", "purpose": "다이어트", "day": 0, "week": 1,
        "heavy": "true"}).json()
    assert b["몸무거운날"] is True
    assert sum(1 for s in b["steps"] if s["단계"] == "본운동") == 2
    assert b["강도"]["세트"] == 1


def test_없는_연령대는_422():
    r = client.get("/program/routine", params={"age_gbn": "노년기", "purpose": "다이어트"})
    assert r.status_code == 422
