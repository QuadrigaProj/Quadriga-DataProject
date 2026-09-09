"""스포츠 선택 시 본운동 세 번째만 교체하는 최소 회귀 검사."""
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend import routines as rt, sports as sp
from backend.main import app

@pytest.mark.parametrize("ids", [["running"], ["yoga"], ["tennis"], ["running", "yoga", "tennis"]])
def test_only_third_main_changes(ids):
    base = rt.build_program_routine("유소년", "기초 체력 증진")
    factors = list(sp.factor_weights(ids))
    assert factors
    result = rt.build_program_routine("유소년", "기초 체력 증진", prefer_factors=factors)
    assert [i for i, (a, b) in enumerate(zip(base["steps"], result["steps"])) if a != b] == [3]
    raw = result["steps"][3]["official_video"]
    source = json.loads((Path(__file__).resolve().parents[1] / "data/processed/kspo_candidate_pool/official_video_catalog.json").read_text(encoding="utf-8"))
    assert raw in source["items"] and raw["values"][3] == "유소년"
    assert all(rt.re.fullmatch(r"[A-Za-z0-9_-]{11}", s["youtube_id"]) for s in result["steps"])
    assert len({s["youtube_id"] for s in result["steps"]}) == 5
    assert any(rt.factor_units(f) & rt.factor_units(raw["values"][0]) for f in factors)
    assert len({s["동작"].replace(" ", "") for s in result["steps"]}) == 5


def test_no_selection_and_no_candidate():
    base = rt.build_program_routine("성인", "다이어트")
    assert base == rt.build_program_routine("성인", "다이어트", prefer_factors=[])
    assert base == rt.build_program_routine("성인", "다이어트", prefer_factors=["존재하지않는요소"])
    assert not base["종목반영"]


def test_semantic_units():
    for a, b in [("민첩성·순발력", "민첩성/순발력"), ("협응력", "협응성"), ("근지구력", "근력/근지구력")]:
        assert rt.factor_units(a) & rt.factor_units(b)
    assert not rt.factor_units("근력") & rt.factor_units("심폐지구력")


def test_all_selected_factors_reach_candidates(monkeypatch):
    captured = []
    def capture(age, factors, names, exclude, day, video_ids=None):
        captured.extend(factors)
        return None
    monkeypatch.setattr(rt, "_sport_candidate", capture)
    ids = ["running", "yoga", "tennis"]
    response = TestClient(app).get("/program/routine", params={"age_gbn": "유소년", "purpose": "다이어트", "sports": ",".join(ids)})
    assert response.status_code == 200
    assert set(captured) == set(sp.factor_weights(ids))
    assert len(captured) > 2


def test_heavy_day_preserves_first_two():
    base = rt.build_program_routine("유소년", "다이어트", heavy=True)
    chosen = rt.build_program_routine("유소년", "다이어트", heavy=True, prefer_factors=["유연성"])
    assert base == chosen


def test_invalid_video_and_wrong_age_candidates_are_ignored(monkeypatch):
    """영상 누락·형식 오류·다른 연령·하루 중복 후보는 교체하지 않는다."""
    base = rt.build_program_routine("성인", "다이어트")
    original = base["steps"][0]["official_video"]
    records = [dict(original, youtube_id=""), dict(original, youtube_id="invalid"),
               dict(original, values=["심폐지구력", "맨몸", "전신", "청소년"]), original]
    monkeypatch.setattr(rt.json, "loads", lambda text: {"items": records})
    assert rt.build_program_routine("성인", "다이어트", prefer_factors=["심폐지구력", "유연성"]) == base


@pytest.mark.parametrize("age", ["유소년", "청소년", "성인", "어르신"])
def test_base_uses_verified_file_without_mutation(age):
    """기본 슬롯이 저장된 공식 영상 루틴과 일치하는지 확인한다."""
    path = Path(__file__).resolve().parents[1] / "data/generated/routines_200_kspo_official_video.json"
    before = path.read_bytes()
    entries = json.loads(before)["routines"]
    expected = next(r for r in entries if r["aggrp_nm"] == age and r["purpose"] == "다이어트" and r["day"] == 1)
    result = rt.build_program_routine(age, "다이어트")
    assert [s["official_video"] for s in result["steps"]] == [s["official_video"] for s in expected["steps"]]
    rt.build_program_routine(age, "다이어트", prefer_factors=list(sp.factor_weights(["running", "yoga"])))
    assert path.read_bytes() == before
