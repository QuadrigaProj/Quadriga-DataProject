"""KSPO 연결과 연령 경계의 회귀 검사."""
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend import routines as rt

client = TestClient(app)

@pytest.mark.parametrize("age,group", [(11,"유소년"),(12,"유소년"),(13,"청소년"),(18,"청소년"),(19,"성인"),(64,"성인"),(65,"어르신")])
def test_boundaries(age, group):
    assert rt.age_group(age) == group
    response = client.get("/program/routine", params={"age_gbn":"성인","real_age":age,"purpose":"다이어트"})
    assert response.status_code == 200
    assert response.json()["연령대"] == group

@pytest.mark.parametrize("endpoint", ["/program/routine", "/recommend/routines"])
def test_underage_routines(endpoint):
    response = client.get(endpoint, params={"age_gbn":"성인","real_age":10,"purpose":"다이어트","ai":False})
    assert response.status_code == 422
    assert "만 11세 이상" in response.text

@pytest.mark.parametrize("endpoint", ["/fitness-age", "/bodycomp", "/hometest"])
def test_underage_measurement(endpoint):
    response = client.post(endpoint, json={"age_gbn":"성인","age":10,"sex":"M","height_cm":140,"weight_kg":40,"flexibility":10})
    assert response.status_code == 422
    assert "만 11세 이상" in response.text

def test_all_sources_and_cycle():
    root = Path(__file__).resolve().parents[1]
    original = json.loads((root / "data/sample/routines_250.json").read_text(encoding="utf-8"))
    assert "유아기" in original["routines"]
    source = json.loads((root / "data/generated/routines_200_kspo_official_video.json").read_text(encoding="utf-8"))
    for entry in source["routines"]:
        age, purpose, day = entry["aggrp_nm"], entry["purpose"].replace("기초체력", "기초 체력"), entry["day"]-1
        routine = rt.build_program_routine(age,purpose,day=day)
        assert [s["동작"] for s in routine["steps"]] == [s["official_video"]["title"] for s in entry["steps"]]
        assert len({s["동작"] for s in routine["steps"]}) == 5
        assert rt.routine_for(age,purpose,day) == rt.routine_for(age,purpose,day+10)

def test_growth_intensity_direction():
    assert rt.start_offset(11,18) == -1
    assert rt.start_offset(18,11) == 1
