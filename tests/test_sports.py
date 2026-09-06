"""운동 종목 목록과 체력요인 매핑."""
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend import sports as sp

c = TestClient(app)


def test_종목_목록이_나온다():
    r = c.get("/sports")
    assert r.status_code == 200
    d = r.json()
    assert d["분류"] and d["종목"]
    assert len(d["종목"]) >= 20


def test_모든_종목이_분류에_속한다():
    d = c.get("/sports").json()
    분류 = set(d["분류"])
    for s in d["종목"]:
        assert s["분류"] in 분류, s["이름"]


def test_종목마다_필요한_것이_다_있다():
    for s in c.get("/sports").json()["종목"]:
        assert s["id"] and s["이름"] and s["아이콘"]
        assert s["체력요인"], f"{s['이름']} 에 체력요인이 없다"


def test_아이디는_겹치지_않는다():
    ids = [s["id"] for s in c.get("/sports").json()["종목"]]
    assert len(ids) == len(set(ids))


def test_체력요인은_루틴_데이터와_같은_말을_쓴다():
    """여기서 어긋나면 루틴 추천이 선택을 못 알아본다."""
    from backend import routines as rt
    쓰는말 = set()
    for _, phases in rt.load()["pools"].items():
        for _, items in phases.items():
            for v in items.values():
                쓰는말.update(v.get("체력요인", []))
    for s in sp.load()["sports"]:
        for f in s["체력요인"]:
            assert f in 쓰는말, f"'{f}' 는 루틴 데이터에 없는 표기다 ({s['이름']})"


def test_선택하면_요인을_세어준다():
    r = c.get("/sports/summary?ids=running,marathon,tennis")
    d = r.json()
    assert d["체력요인"]["심폐지구력"] == 3      # 셋 다 심폐를 요구한다
    assert len(d["선택"]) == 3


def test_모르는_종목은_조용히_버린다():
    """저장해 둔 선택이 낡아도 화면이 깨지면 안 된다."""
    d = c.get("/sports/summary?ids=running,없는종목,").json()
    assert [s["id"] for s in d["선택"]] == ["running"]


def test_아무것도_안_고르면_빈_결과():
    d = c.get("/sports/summary?ids=").json()
    assert d["선택"] == [] and d["체력요인"] == {} and d["조심할부위"] == []


def test_조심할_부위를_모아준다():
    d = c.get("/sports/summary?ids=running,marathon").json()
    assert "무릎" in d["조심할부위"]
