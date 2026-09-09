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


def test_체력요인_복합표기와_없는_후보를_처리한다():
    from backend import routines as rt
    assert rt._has_factor({"체력요인": ["근력/근지구력"]}, "근지구력")
    성인심폐 = rt._prefer_substitute("성인", "심폐지구력", set(), set())
    assert 성인심폐 is not None
    assert rt._has_factor(성인심폐, "심폐지구력")
    assert 성인심폐["youtube_id"]
    assert rt._prefer_substitute("어르신", "심폐지구력", set(), set()) is not None


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


# ---------- 루틴 추천이 고른 종목을 참고한다 ----------

def _routine(**kw):
    q = {"age_gbn": "성인", "purpose": "기초 체력 증진", "day": 0, "week": 1}
    q.update(kw)
    return c.get("/program/routine", params=q).json()


def _mains(r):
    return [s["동작"] for s in r["steps"] if s["단계"] == "본운동"]


def test_종목을_안_고르면_원래_루틴_그대로():
    r = _routine()
    assert r["종목반영"] == []
    assert "고른종목" not in r


def test_러닝을_고르면_심폐_동작이_들어온다():
    """근력 위주 루틴에 심폐가 하나도 없으면 하나를 넣어준다."""
    기본 = _routine(age_gbn="어르신", purpose="유연성 강화")
    러너 = _routine(age_gbn="어르신", purpose="유연성 강화", sports="running,marathon")
    assert 러너["참고요인"][0] == "심폐지구력"
    요인 = [f for s in 러너["steps"] if s["단계"] == "본운동" for f in s["체력요인"]]
    assert any("심폐지구력" in f for f in 요인)
    assert _mains(기본) != _mains(러너)
    assert 러너["종목반영"]


def test_동작_개수는_그대로다():
    """루틴을 새로 만들지 않는다 — 개수가 늘거나 줄면 안 된다."""
    기본 = _routine()
    for ids in ("running,marathon", "yoga,pilates", "tennis,badminton"):
        assert len(_mains(_routine(sports=ids))) == len(_mains(기본)), ids


def test_종목을_골라도_첫_두_본운동은_유지한다():
    """종목 맞춤은 기본 200개 루틴을 다시 만들지 않고 세 번째 본운동만 다듬는다."""
    기본 = _routine()
    헬스 = _routine(sports="gym,crossfit")
    assert len(_mains(헬스)) == len(_mains(기본))
    assert _mains(헬스)[:2] == _mains(기본)[:2]


def test_제외한_부위는_종목보다_우선한다():
    """무릎이 아프면, 종목을 반영하느라 무릎 동작을 넣으면 안 된다."""
    r = _routine(sports="running,marathon", exclude_parts="무릎")
    for s in r["steps"]:
        assert "무릎" not in s["부담부위"], s["동작"]


def test_모르는_종목은_무시된다():
    assert _routine(sports="없는종목") ["종목반영"] == []


def test_조심할_부위를_같이_알려준다():
    r = _routine(sports="running,marathon")
    assert "무릎" in r["조심할부위"]
    assert r["고른종목"] == ["러닝", "마라톤"]


# --- 종목 데이터가 없을 때 ---
# 종목은 곁가지 기능이다. sports.json 이 없다고 해서 루틴이 안 나오면 안 된다.

@pytest.fixture
def 종목데이터_없음(monkeypatch):
    """sports.json 이 없는 상황을 만든다. 캐시도 비워야 실제로 읽으러 간다."""
    def 없다(name):
        raise FileNotFoundError(f"{name} 을(를) 찾을 수 없습니다.")

    monkeypatch.setattr(sp, "find_data", 없다)
    monkeypatch.setattr(sp, "_data", None)
    yield
    sp._data = None


def test_종목을_안_골랐으면_데이터가_없어도_루틴이_나온다(종목데이터_없음):
    """고르지 않은 사람에게까지 종목 데이터를 강요하지 않는다."""
    r = c.get("/program/routine", params={"age_gbn": "성인", "purpose": "다이어트"})
    assert r.status_code == 200
    assert r.json()["steps"]


def test_종목을_골랐는데_데이터가_없으면_404로_알려준다(종목데이터_없음):
    """500 으로 터지지 말고, 어디에 파일을 두라는 안내가 그대로 나가야 한다."""
    r = c.get("/program/routine",
              params={"age_gbn": "성인", "purpose": "다이어트", "sports": "running"})
    assert r.status_code == 404


def test_종목_목록도_데이터가_없으면_404다(종목데이터_없음):
    assert c.get("/sports").status_code == 404
    assert c.get("/sports/summary", params={"ids": "running"}).status_code == 404
