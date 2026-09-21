"""운동 스타일 테스트(F1) — 문항 제공·채점·화면 진입."""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.main import app                   # noqa: E402
from backend import routines as rt             # noqa: E402
from backend import sports as sp               # noqa: E402
from backend import style_test as st           # noqa: E402

c = TestClient(app)

# 유형별로 그 유형다운 사람의 답 20개(설계 시 확인). 채점 데이터가 바뀌면 여기도 같이 고친다.
# 척도 문항(q4 · q7 · q9 · q13 · q14 · q15)은 0 = 전혀 아니에요 … 4 = 정말 그래요, q2(시간)는 0 = 10분 … 4 = 1시간 넘게.
KNOWN = {
    "runner":  [0, 4, 0, 4, 2, 3, 4, 0, 0, 0, 3, 0, 4, 0, 0, 1, 0, 3, 2, 0],
    "builder": [1, 4, 0, 0, 2, 2, 4, 3, 0, 1, 2, 0, 1, 0, 0, 0, 1, 0, 2, 1],
    "team":    [0, 2, 2, 4, 1, 0, 2, 2, 4, 2, 0, 1, 4, 0, 4, 1, 2, 2, 1, 3],
    "racket":  [1, 2, 1, 0, 1, 0, 4, 2, 4, 1, 0, 1, 1, 0, 1, 0, 2, 0, 0, 3],
    "rhythm":  [0, 2, 1, 0, 1, 1, 2, 2, 4, 1, 1, 2, 1, 4, 1, 2, 2, 0, 3, 3],
    "balance": [2, 2, 0, 0, 1, 1, 0, 1, 2, 1, 1, 3, 1, 3, 0, 2, 3, 1, 3, 2],
    "walker":  [2, 2, 1, 4, 0, 3, 0, 1, 2, 0, 3, 3, 2, 3, 0, 1, 3, 1, 3, 2],
    "quick":   [1, 0, 0, 0, 0, 0, 2, 0, 2, 3, 0, 0, 0, 4, 0, 3, 1, 0, 0, 3],
}


def _random_answers(n, seed=11):
    """가능한 답은 190억 가지라 다 돌릴 수 없다 — 씨앗을 고정한 무작위 답 n 벌."""
    import random
    rnd = random.Random(seed)
    qs = st.load()["문항"]
    return [[rnd.randrange(len(q["선택지"])) for q in qs] for _ in range(n)]


def test_문항이_나온다():
    r = c.get("/style-test")
    assert r.status_code == 200
    body = r.json()
    qs = body["문항"]
    assert len(qs) == 20                           # 9문항은 너무 짧다는 피드백 (예현)
    assert len({q["id"] for q in qs}) == 20
    for q in qs:
        assert q["질문"]
        assert 2 <= len(q["선택지"]) <= 5
        assert all(isinstance(x, str) and x for x in q["선택지"])
        assert "점수" not in q                      # 채점 기준은 서버만 안다
    assert body["유형"]
    assert all("가중치" not in t for t in body["유형"])


def test_단계로_답하는_문항은_척도로_나온다():
    """얼마나 그런지 단계로 답할 수 있는 문항은 고르기가 아니라 다섯 단계 척도다 (예현 요청).
    데이터에는 "척도": {축: [점수 5개]} 로 적고, 서버가 읽을 때 선택지 다섯 개로 편다 — 채점은 다른 문항과 똑같다."""
    raw = st.load()["문항"]
    척도 = [q for q in raw if q.get("모양") == "척도"]
    assert len(척도) >= 6
    for q in 척도:
        assert [x["글"] for x in q["선택지"]] == st.SCALE_STEPS == ["전혀 아니에요", "아닌 편이에요", "반반이에요", "그런 편이에요", "정말 그래요"]
        assert q["질문"].endswith("요.")                       # 물음이 아니라 '나는 이래요' 라는 말이어야 단계로 답할 수 있다
        for axis, vals in q["척도"].items():
            assert len(vals) == 5
            assert vals == sorted(vals) or vals == sorted(vals, reverse=True), (q["id"], axis)   # 단계가 오를수록 한쪽으로만 움직인다
    # 화면에는 모양만 간다 — 점수는 가지 않는다
    api = {q["id"]: q for q in c.get("/style-test").json()["문항"]}
    for q in 척도:
        assert api[q["id"]]["모양"] == "척도" and "척도" not in api[q["id"]] and "점수" not in api[q["id"]]
    assert "모양" not in api["q6"]                              # 장면을 고르는 문항은 그대로 고르기다
    # 같은 문항에서 단계가 오르면 그 축 점수도 오른다
    낮음, 높음 = list(KNOWN["balance"]), list(KNOWN["balance"])
    i = [q["id"] for q in raw].index("q7")
    낮음[i], 높음[i] = 0, 4
    assert st.axis_scores(높음)["강도"] > st.axis_scores(낮음)["강도"]
    html = c.get("/").text
    그림 = html.split("function renderStyleQuestion()")[1].split("\n}")[0]
    assert "if (q.모양 === '척도') {" in 그림 and 'role="radiogroup"' in 그림 and 'class="style-dot s${i}' in 그림
    assert "onclick=\"styleAnswer(${i})\"" in 그림


def test_유형은_6개에서_8개():
    types = st.result_types()
    assert 6 <= len(types) <= 8
    ids = [t["id"] for t in types]
    assert len(ids) == len(set(ids))
    for t in types:
        assert t["이름"] and t["설명"]
        assert t["갈래"].endswith("타입") and t["갈래"] != t["이름"]      # 이름은 은유, 무슨 유형인지는 갈래가 풀어 준다
    assert len({t["이름"] for t in types}) == len(types)


def test_추천목적과_종목이_실제_데이터와_맞는다():
    table = sp.by_id()
    for t in st.result_types():
        assert t["추천목적"] in rt.PURPOSES, t["id"]
        assert t["추천목적"] in st.PURPOSE_KEY, t["id"]
        assert len(t["추천종목"]) == 3, t["id"]
        assert all(i in table for i in t["추천종목"]), t["id"]
        assert isinstance(t["하루투자분"], int) and t["하루투자분"] > 0, t["id"]


def test_채점은_결정적이다():
    a = KNOWN["runner"]
    r1 = c.post("/style-test/result", json={"answers": a})
    r2 = c.post("/style-test/result", json={"answers": a})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()
    assert st.score(a) == st.score(list(a))


def test_정해진_답은_정해진_유형():
    for tid, a in KNOWN.items():
        assert st.score(a)["유형"]["id"] == tid, tid


def test_모든_유형이_고르게_나온다():
    """문항이 늘면 점수가 평균에 몰려, 그대로 가중합을 하면 두 유형이 절반을 가져가고 산책형은 2% 만 나온다.
    축마다 평균 · 표준편차로 맞춘 뒤 견주므로 여덟 유형이 고르게 나와야 한다."""
    n = 6000
    seen: dict[str, int] = {}
    for a in _random_answers(n):
        k = st.score(a)["유형"]["id"]
        seen[k] = seen.get(k, 0) + 1
    assert set(seen) == {t["id"] for t in st.result_types()}
    for k, v in seen.items():
        assert 0.05 < v / n < 0.25, (k, v / n)


def test_축_평균과_표준편차():
    """z 로 맞출 때 쓰는 값 — 모든 선택지를 같은 확률로 골랐을 때의 평균 · 표준편차(문항끼리 독립이라 더하면 된다)."""
    stats = st.axis_stats()
    assert set(stats) == set(st.axis_max())
    import statistics
    rows = [st.axis_scores(a) for a in _random_answers(4000, seed=3)]
    for axis, (m, sd) in stats.items():
        assert 0 < m < 1 and sd > 0
        assert abs(statistics.fmean(r[axis] for r in rows) - m) < 0.02, axis        # 식으로 낸 평균이 실제와 맞는다
        assert abs(statistics.pstdev(r[axis] for r in rows) - sd) < 0.02, axis


def test_결과_응답_모양():
    a = KNOWN["balance"]
    r = c.post("/style-test/result", json={"answers": a})
    assert r.status_code == 200
    body = r.json()
    t = body["유형"]
    assert {"id", "이름", "설명", "추천목적", "목적키", "추천종목", "하루투자분"} <= set(t)
    assert t["목적키"] == "flex"
    assert t["추천목적"] == "유연성 강화"
    assert body["답변"] == a
    assert body["점수"] and all(0.0 <= v <= 1.0 for v in body["점수"].values())
    assert [s["id"] for s in body["종목"]] == t["추천종목"]
    for s in body["종목"]:
        assert s["이름"] and s["아이콘"]


@pytest.mark.parametrize("bad", [
    [0] * 8,                 # 개수 부족
    [0] * 10,                # 개수 초과
    [0] * 8 + [9],           # 범위 밖
    [0] * 8 + [-1],          # 음수
    [0] * 8 + ["a"],         # 문자열
    [0] * 8 + [True],        # bool
    [0] * 8 + [1.5],         # 실수
])
def test_잘못된_답은_400(bad):
    r = c.post("/style-test/result", json={"answers": bad})
    assert r.status_code == 400
    assert r.json()["detail"]


def test_네_글자_성향_코드():
    """유형 이름과 함께 MBTI 처럼 읽는 네 글자가 나온다 (예현 요청). 어느 축을 어느 기준으로 자르는지는
    style_test.json 의 "코드" 에 있고 서버는 자르기만 한다."""
    spec = st.load()["코드"]
    assert [x["id"] for x in spec] == ["강도", "함께", "장소", "시간"]
    for x in spec:
        assert len(x["글자"]) == len(x["이름"]) == len(x["말"]) == 2
        assert "기준" not in x or 0 < x["기준"] < 1      # 적지 않으면 그 축의 평균에서 자른다
    글자 = [g for x in spec for g in x["글자"]]
    assert len(set(글자)) == 8                       # 글자가 겹치면 코드를 읽을 수 없다
    축이름 = {a for q in st.load()["문항"] for ch in q["선택지"] for a in ch.get("점수", {})}
    assert {x["축"] for x in spec} | {x["반대축"] for x in spec if x.get("반대축")} <= 축이름   # 없는 축을 가리키면 늘 0 이다

    r = st.score(KNOWN["runner"])                    # 숨차고 땀 · 45분 이상 · 혼자 · 무조건 바깥 · 거의 매일 · 달리는 여정 · 비옷을 입고라도 …
    assert r["코드"]["글자"] == "HSOL"
    assert [a["이름"] for a in r["코드"]["축"]] == ["고강도", "혼자", "야외", "길게"]
    assert st.score(KNOWN["balance"])["코드"]["글자"] == "MSIL"
    assert st.score(KNOWN["team"])["코드"]["글자"][1] == "T" and st.score(KNOWN["quick"])["코드"]["글자"][3] == "Q"
    for a in r["코드"]["축"]:
        assert {"id", "글자", "이름", "말", "양쪽", "비율"} <= set(a) and 0 <= a["비율"] <= 100
        assert a["글자"] == (a["양쪽"][0]["글자"] if a["비율"] >= 50 else a["양쪽"][1]["글자"])   # 글자와 막대가 어긋나지 않는다

    body = c.post("/style-test/result", json={"answers": KNOWN["runner"]}).json()
    assert body["코드"] == r["코드"]


def test_비율은_기준이_50퍼센트가_되게_편다():
    """기준은 그 축의 평균이다(0.5 가 아니다). 그래도 글자가 바뀌는 자리가 막대의 한가운데여야 글자와 막대가 어긋나 보이지 않는다."""
    m = st.axis_stats()["함께"][0]
    def 함께(v):
        return next(a for a in st.type_code({"함께": v})["축"] if a["id"] == "함께")
    assert (함께(m)["글자"], 함께(m)["비율"]) == ("T", 50)
    assert (함께(m / 2)["글자"], 함께(m / 2)["비율"]) == ("S", 25)
    assert 함께(1.0)["비율"] == 100 and 함께(0.0)["비율"] == 0
    # 길게 ↔ 짧게는 두 축의 차이로 본다 — 한쪽만 조금 골랐다고 100% 가 되지 않는다
    시간 = next(a for a in st.type_code({"시간": 1.0, "짧게": 0.0})["축"] if a["id"] == "시간")
    assert (시간["글자"], 시간["비율"]) == ("L", 100)
    시간 = next(a for a in st.type_code({"시간": 0.0, "짧게": 1.0})["축"] if a["id"] == "시간")
    assert (시간["글자"], 시간["비율"]) == ("Q", 0)
    중간 = next(a for a in st.type_code({"시간": 0.4, "짧게": 0.0})["축"] if a["id"] == "시간")
    assert 50 < 중간["비율"] < 100


def test_코드_열여섯_가지가_모두_나온다():
    """기준을 잘못 잡으면 어떤 글자는 아무도 받지 못한다. 무작위 답 6,000벌에서 열여섯 코드가 다 나오는지,
    어느 글자도 한쪽으로 쏠리지 않는지 본다(기준이 축의 평균이라 반반 언저리여야 한다)."""
    seen: dict[str, int] = {}
    for ans in _random_answers(6000, seed=5):
        k = st.type_code(st.axis_scores(ans))["글자"]
        seen[k] = seen.get(k, 0) + 1
    assert len(seen) == 16
    n = sum(seen.values())
    for i in range(4):
        앞 = sum(v for k, v in seen.items() if k[i] == st.load()["코드"][i]["글자"][0]) / n
        assert 0.4 < 앞 < 0.6, (i, 앞)


def test_유형마다_대표_그림이_있다():
    """결과 화면과 공유 카드의 얼굴. 유형을 더하고 그림을 빠뜨리면 그 유형만 그림 없이 나온다."""
    art = c.get("/js/style-art.js").text
    for t in st.load()["유형"]:
        assert f"    {t['id']}: () =>" in art and f"    {t['id']}:" in art.split("const TONE = {")[1].split("};")[0], t["id"]
    assert "function chibi(id, o)" in art                     # 여덟 명이 같은 얼굴 틀을 쓴다 — 한 식구로 보이게
    assert "function svg(id, size = 160, label = '')" in art and "function image(id, size = 400, sex)" in art
    assert "'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(s)" in art       # canvas 에 그릴 수 있게


def test_그림은_사용자의_성별에_따라_다르다():
    """같은 유형이어도 성별이 다르면 그림이 다르다 (예현 요청, 2026-09-20). SD 캐릭터, 유형 여덟 × 여 · 남 = 열여섯 장.
    파일을 못 받으면 예전 SVG 그림으로 돌아간다 — 그림 때문에 화면이 비면 안 된다."""
    from pathlib import Path
    폴더 = Path(__file__).resolve().parents[1] / "frontend" / "img" / "style"
    for t in st.load()["유형"]:
        for 성 in ("f", "m"):
            파일 = 폴더 / f"{t['id']}-{성}.webp"
            assert 파일.exists(), 파일.name
            머리 = 파일.read_bytes()[:12]
            assert 머리[:4] == b"RIFF" and 머리[8:12] == b"WEBP", 파일.name
            assert 파일.stat().st_size < 60_000, (파일.name, 파일.stat().st_size)      # 열여섯 장이 다 해서 0.5MB 아래 — 첫 화면에서는 받지 않는다
            assert c.get(f"/img/style/{t['id']}-{성}.webp").status_code == 200
    art = c.get("/js/style-art.js").text
    assert "const photo = (id, sex) => (has(id) ? `/img/style/${id}-${sex === 'M' ? 'm' : 'f'}.webp` : '');" in art
    assert "onerror=\"this.outerHTML = STYLE_ART.svg('${id}', ${size}, this.alt)\"" in art       # 못 받으면 그 자리를 SVG 로
    assert "img.onerror = () => svgImage(id, size).then(resolve, reject);" in art                 # 공유 카드도 마찬가지
    assert "return { svg, html, image, photo, has, tone:" in art


def test_결과_화면에_그림_코드_카드가_있다():
    html = c.get("/").text
    assert '<script src="js/style-art.js"></script>' in html
    assert 'id="styleArt"' in html and 'id="styleCode"' in html and 'id="styleAxes"' in html
    assert 'onclick="openStyleCard()">결과 카드 만들기</button>' in html
    그림 = html.split("function renderStyleCode(r)")[1].split("\n}")[0]
    assert "STYLE_ART.html(t.id, state.sex, 112," in 그림 and "$('styleCode').textContent = code?.글자 || '';" in 그림
    assert "if (!code) { refillStyleCode(); return; }" in 그림                       # 코드가 생기기 전의 저장본은 답으로 다시 채점해 채운다
    assert 'id="styleKind"' in html and "$('styleKind').textContent = t.갈래 || '';" in html   # 은유 이름 아래에 풀이
    채움 = html.split("async function refillStyleCode()")[1].split("\n}")[0]
    assert "await API.styleTestResult(saved.answers)" in 채움 and "saveProfile();" in 채움
    assert "테스트가 새로 바뀌었어요. 다시 해 보면 네 글자 유형이 나와요." in 채움      # 9문항 때의 답은 다시 채점할 수 없다
    카드 = html.split("async function openStyleCard()")[1].split("\n}")[0]
    assert "파일: 'fitage-style.png'" in 카드 and "await STYLE_ART.image(t.id, 560, state.sex)" in 카드
    assert "이름은 들어가지 않아요. 유형과 성향만 담깁니다." in 카드
    그리기 = html.split("function drawStyleCard(cv, r, img)")[1].split("\n}")[0]
    assert "const W = 1080, H = 1350" in 그리기 and "state.user" not in 그리기        # 체력나이 카드와 같은 크기, 이름은 넣지 않는다


def test_화면에_테스트_진입_링크와_s10_이_있다():
    html = c.get("/").text
    assert html.count("뭘 골라야 할지 모르겠어요 → 운동 스타일 테스트") == 2   # s2 · s8
    assert 'id="s10"' in html
    assert "이 목적으로 시작" in html
    assert "이 종목 담기" in html
    assert "styleTest: null" in html
    assert "openStyleTest(" in html
    js = c.get("/js/api.js").text
    assert "/style-test" in js and "/style-test/result" in js


def test_운동_고르기에서_결과_카드를_다시_볼_수_있다():
    """예현(2026-09-21): "운동고르기에서 카드 화면 나가도 추후에 확인 가능했으면 좋겠어".
    결과는 state.styleTest 에 남고 openStyleTest('s8') 도 결과부터 보여 주지만, 입구가 '… → 운동 스타일 테스트' 뿐이라
    결과가 남아 있는 줄 몰랐다. 결과가 있으면 '내 운동 스타일' 카드(그림 · 유형 이름 · 코드)를 보이고, 누르면 결과 카드를 연다."""
    html = c.get("/").text.replace("\r\n", "\n")
    s8 = html.split('<section class="screen" id="s8">')[1].split("</section>")[0]
    assert """<button type="button" class="style-mine" id="styleMine" hidden onclick="openStyleTest('s8')"></button>""" in s8
    assert 'id="styleTestLink"' in s8                                          # 결과가 없을 때는 예전 입구 그대로
    그림 = html.split("function renderStyleMine(){")[1].split("\n}")[0]
    assert "card.hidden = !t?.이름;" in 그림 and "link.hidden = !!t?.이름;" in 그림
    assert "STYLE_ART.html(t.id, state.sex, 56, '')" in 그림                  # 결과 화면과 같은 그림(성별대로)
    assert "결과 카드 보기 ›" in 그림 and "state.styleTest?.result?.코드?.글자" in 그림
    assert "renderStyleMine();" in html.split("async function renderSports(){")[1].split("\n}")[0]   # 운동 고르기를 열 때마다
    열기 = html.split("function openStyleTest(from){")[1].split("\n}")[0]
    assert "if (state.styleTest?.result) {" in 열기 and "styleView = 'result';" in 열기   # 누르면 테스트가 아니라 결과부터
    assert ".style-mine[hidden]{ display:none; }" in html
