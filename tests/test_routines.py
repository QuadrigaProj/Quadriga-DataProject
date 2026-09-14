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


def test_데이터_32조합_320루틴():
    """연령대 4 × 목적 8 (원래 5 + 벌크업·근육량 늘리기·지구력 늘리기)."""
    d = rt.load()
    assert d["_meta"]["조합수"] == 32
    assert d["_meta"]["루틴수"] == 320
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
    # 영상 기반 구조 — 세트 수만 쓴다. 1~4주 2세트, 5~8·9~12주 3세트 (docs/effective_dose.md — 5주차부터 3세트여야 측정이 움직인다)
    assert rt.intensity_for("성인", 2)["세트"] == 2
    assert rt.intensity_for("성인", 6)["세트"] == 3
    assert rt.intensity_for("성인", 10)["세트"] == 3
    # 재활 및 기능 회복은 천천히 — 예전 진행(2·2·3)
    assert rt.intensity_for("성인", 6, purpose="재활 및 기능 회복")["세트"] == 2
    assert rt.intensity_for("성인", 10, purpose="재활 및 기능 회복")["세트"] == 3
    # 반복·시간·라운드는 더 이상 돌려주지 않는다. '노력' 한 줄은 모두에게 붙는다
    assert set(rt.intensity_for("성인", 2)) == {"주차", "구간", "세트", "노력"}
    assert "마지막 2~3회가 힘들 만큼" in rt.intensity_for("성인", 2)["노력"]
    assert "어지러우면" in rt.intensity_for("어르신", 2)["노력"]


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
    # 5~8주 3세트 → 2세트, 1~4주 2세트 → 몸이 무거운 날 1세트 (최소 1세트)
    assert rt.intensity_for("어르신", 6, heavy=True)["세트"] == 2
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


def test_벌크업_근육량_지구력_목적이_있다():
    """운동 단계에 셋을 더했다 — 루틴은 backend/generate_official_routines.py 가 공식 영상으로 만든 것."""
    assert rt.PURPOSES[-3:] == ("벌크업", "근육량 늘리기", "지구력 늘리기")
    d = rt.load()
    for a in rt.AGE_GROUPS:
        for p in ("벌크업", "근육량 늘리기", "지구력 늘리기"):
            assert len(d["routines"][a][p]) == 10, (a, p)
    # 본운동은 목적에 맞는 요소만: 지구력은 심폐지구력을 우대해 절반 이상이 심폐지구력이어야 한다
    본 = [d["pools"]["성인"]["본운동"][c] for r in d["routines"]["성인"]["지구력 늘리기"] for c in r["main"]]
    assert sum(1 for s in 본 if "심폐지구력" in (s.get("체력요인") or s.get("ftns_fctr_nm") or "")) >= len(본) // 2
    r = client.get("/program/routine", params={"age_gbn": "성인", "purpose": "벌크업", "day": 0, "week": 1}).json()
    assert len(r["steps"]) == 5 and r["강도"]["세트"] == 3          # 1-4주 기본 2세트 + 벌크업 1세트
    assert "무거운 기구" in r["강도"]["요령"]
    r2 = client.get("/program/routine", params={"age_gbn": "성인", "purpose": "지구력 늘리기", "day": 3, "week": 1}).json()
    assert r2["강도"]["세트"] == 2 and "15~20회" in r2["강도"]["요령"]
    assert "요령" not in client.get("/program/routine", params={"age_gbn": "성인", "purpose": "다이어트", "day": 0}).json()["강도"]
    assert client.get("/program/routine", params={"age_gbn": "성인", "purpose": "복근 만들기"}).status_code == 422


def test_새_목적은_다른_곳에서도_안다():
    from backend import ai_recommend as air, daily_prescription as dp, prescription as pr, style_test as st
    for p in ("벌크업", "근육량 늘리기", "지구력 늘리기"):
        assert p in air.PURPOSES and p in pr.PURPOSE_FACTORS and p in st.PURPOSE_KEY
        assert dp.tip("성인", p, 0)                                    # 문구가 없어도 가까운 목적의 문구로
    assert "벌크업" in air.COMPOSE_SYSTEM and "지구력 늘리기" in air.COMPOSE_SYSTEM
    html = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")
    for key, 이름 in (("bulk", "벌크업"), ("muscle", "근육량 늘리기"), ("endurance", "지구력 늘리기")):
        assert f'data-p="{key}" onclick="selectPurpose(\'{key}\')"' in html and 이름 in html
        assert f"{key}: '{이름}'" in html.split("const PURPOSE_TO_KO = {")[1].split("};")[0]


# ---------- 용량 (backend/dose.py) ----------

def test_권장_용량은_체력나이가_움직일_만큼이다():
    """8~12주 뒤 측정이 바뀌려면 근력 3세트·심폐 25~30분·주 3회는 되어야 한다 (docs/effective_dose.md)."""
    from backend import dose
    d = dose.dose_for("기초 체력 증진")
    assert d["한 번에"]["근력"] == "8~12회 × 3세트" and d["한 번에"]["심폐지구력"] == "25~30분 중강도"
    assert d["주 횟수"] == 3 and d["기간"] == "8~12주" and "체력나이가 움직입니다" in d["왜"]
    assert d["본운동 분"] == "30~40" and "시작" not in d
    assert dose.dose_for(None)["목적"] == "기초 체력 증진" and dose.dose_for("없는 목적")["목적"] == "기초 체력 증진"


def test_용량은_운동_단계에_따라_다르다():
    from backend import dose
    벌크 = dose.dose_for("벌크업")
    assert 벌크["한 번에"]["근력"].startswith("6~10회 × 4세트") and "무게" in 벌크["노력"] and 벌크["본운동 분"] == "40~50"
    재활 = dose.dose_for("재활 및 기능 회복")
    assert 재활["한 번에"]["근력"] == "10~15회 × 2세트" and "통증 없는 범위" in 재활["노력"] and 재활["본운동 분"] == "20~30"
    지구력 = dose.dose_for("지구력 늘리기")
    assert 지구력["한 번에"]["심폐지구력"] == "30~45분 중강도" and 지구력["한 번에"]["근지구력"] == "20~25회 × 3세트"
    assert dose.dose_for("유연성 강화")["한 번에"]["유연성"] == "45초 × 3, 매일"
    # 목적이 안 바꾼 요인은 기본 그대로
    assert 벌크["한 번에"]["유연성"] == "30초 × 3"


def test_용량은_어르신_빡빡함_낮은_체력에서_내려간다():
    from backend import dose
    어르신 = dose.dose_for("벌크업", age_gbn="어르신")
    assert 어르신["한 번에"]["근력"] == "10~15회 × 2~3세트" and "매일" in 어르신["한 번에"]["평형성"]   # 낙상이 먼저 — 목적보다 나중에 덮는다
    assert "어지러우면" in 어르신["노력"]
    빡빡 = dose.dose_for("다이어트", budget="빡빡함")
    assert "인터벌" in 빡빡["한 번에"]["심폐지구력"] and 빡빡["본운동 분"] == "20~30"
    assert dose.dose_for("다이어트", budget="넉넉함")["한 번에"]["심폐지구력"] == "30~40분 중강도"
    낮음 = dose.dose_for("기초 체력 증진", gap=8)
    assert "첫 2주" in 낮음["시작"] and "시작" not in dose.dose_for("기초 체력 증진", gap=3)
