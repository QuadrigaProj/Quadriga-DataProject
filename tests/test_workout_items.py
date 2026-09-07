"""당일 기록 작성 종목 (G3·G4).

화면은 /workout-items 를 받아 그대로 그린다. 여기서는 데이터의 앞뒤가 맞는지와
화면이 그 데이터를 쓰는 구조인지를 본다.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.main import app  # noqa: E402
from backend import workout_items as wi  # noqa: E402

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def test_종목_목록이_나온다():
    r = client.get("/workout-items")
    assert r.status_code == 200
    d = r.json()
    assert d["분류"] and d["종목"] and d["단위"]
    assert len(d["종목"]) >= 20


def test_모든_종목이_분류에_속한다():
    d = wi.catalog()
    분류 = set(d["분류"])
    for x in d["종목"]:
        assert x["분류"] in 분류, x["이름"]


def test_아이디는_겹치지_않는다():
    ids = [x["id"] for x in wi.catalog()["종목"]]
    assert len(ids) == len(set(ids))


def test_종목마다_입력칸이_있고_단위가_정의돼_있다():
    """G4: 명칭 우측에 횟수·무게·세트 같은 단위 칸이 붙는다."""
    d = wi.catalog()
    단위 = set(d["단위"])
    for x in d["종목"]:
        assert x["입력"], x["이름"]
        for k in x["입력"]:
            assert k in 단위, f"{x['이름']} 의 {k} 에 단위가 없다"


def test_운동에_따라_입력칸이_다르다():
    """무게를 쓰는 기구 운동과 안 쓰는 맨몸 운동이 함께 있어야 요구가 충족된다."""
    by = {x["id"]: x for x in wi.catalog()["종목"]}
    assert "무게" in by["bench-press"]["입력"]
    assert "무게" not in by["squat"]["입력"]
    assert "거리" in by["run"]["입력"]


def test_종목마다_자세_그림이_있다():
    """G4·H7: 명칭 앞 단색 그림. 기구가 아니라 사람이 그 동작을 하는 모습이다."""
    art = (ROOT / "frontend" / "js" / "move-art.js").read_text(encoding="utf-8")
    for x in wi.catalog()["종목"]:
        assert f'id="pose-{x["id"]}"' in art, f'{x["이름"]} 자세 그림 없음'


def test_종목마다_요인이_있다():
    """H7: 무엇을 늘리는 운동인지 아이콘으로 보여주려면 요인이 있어야 한다."""
    d = wi.catalog()
    요인 = set(d["요인"])
    assert 요인 == {"유연성", "근력", "심폐지구력", "근지구력"}
    art = (ROOT / "frontend" / "js" / "move-art.js").read_text(encoding="utf-8")
    for f in 요인:
        assert f'id="factor-{f}"' in art, f"{f} 아이콘 없음"
    for x in d["종목"]:
        assert x["요인"] in 요인, x["이름"]


def test_푸시업은_아령이_아니라_사람이다():
    """H7 원문: 푸시업은 사람이 직접 하는 것이므로 사람 자세여야 한다."""
    art = (ROOT / "frontend" / "js" / "move-art.js").read_text(encoding="utf-8")
    본문 = art.split('id="pose-pushup"')[1].split("</symbol>")[0]
    assert "<circle" in 본문        # 머리
    assert 본문.count("<path") >= 3  # 몸·팔·바닥


def test_화면에_당일_기록_작성이_붙어_있다():
    html = client.get("/").text
    assert "당일 기록 작성" in html
    assert 'id="s11"' in html
    assert "async function renderDailyLog()" in html
    assert "async function saveDailyLog()" in html
    assert "API.workoutItems()" in html


def test_직접_적은_운동도_운동한_날로_센다():
    """달력·변화추이가 읽는 allRoutineLog 에 들어가야 한다."""
    html = client.get("/").text
    body = html.split("function allRoutineLog()")[1].split("\n}")[0]
    assert "state.workoutLog" in body


# ---------- H6 달력 날짜별 버튼 ----------

def test_달력에_날짜별_버튼자리가_있다():
    html = client.get("/").text
    assert 'id="calDayActions"' in html
    assert "function editCalDayLog()" in html
    assert "async function deleteCalDayLog()" in html
    for label in ("기록 수정", "기록 삭제", "기록 작성"):
        assert label in html, label


def test_버튼은_직접_적은_기록에만_붙는다():
    """루틴 완료 기록은 사용자가 쓴 것이 아니라 수정·삭제 대상이 아니다."""
    html = client.get("/").text
    body = html.split("function renderCalDay()")[1].split("\n}")[0]
    assert "state.workoutLog" in body
    assert "todayIso()" in body          # 미래 날짜에는 버튼을 달지 않는다


def test_기록_작성은_다른_날짜도_받는다():
    html = client.get("/").text
    assert "let logTargetDate" in html
    save = html.split("async function saveDailyLog()")[1].split("\n}")[0]
    assert "logTargetDate || todayIso()" in save
    render = html.split("async function renderDailyLog()")[1].split("\n}")[0]
    assert "logTargetDate || todayIso()" in render


def test_요인_아이콘이_프로필_차트에도_붙는다():
    """H7: 사용자가 아이콘 뜻을 알 수 있게 차트 항목 글자 앞에 한 번씩 보여준다."""
    html = client.get("/").text
    assert 'src="js/move-art.js"' in html
    assert "MOVE_ART.install();" in html
    assert "MOVE_ART.factor(k, 'axis-icon')" in html      # 차트 항목 앞
    assert "MOVE_ART.factor(x.요인)" in html               # 기록 작성 화면
    assert "MOVE_ART.pose(x.id)" in html
