"""고른 종목(테니스 · 발레 · 수영 …)은 3D 동작 대신 그림 한 장 — 남녀 따로.

예현(2026-09-21): "사용자가 선택한 본운동(수영, 발레, 요가 등)은 이미지로 대체하자.
보통 우리 앱에서의 도움만으로 되지 않고 학원에서 배워야 하거나 이미 기본적인 것들을 알고 있을 가능성이 커서."
그림체는 시안 다섯(픽토그램 · 라인 · 플랫 · SD 캐릭터 · 3D 클레이) 가운데 플랫 일러스트로 골랐고,
스타일 테스트 그림처럼 성별마다 다른 그림을 쓴다 ("이 이미지 작업들도 남녀 이미지로 나눠서 작업해줘").
"""
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONT = ROOT / "frontend"
ART = FRONT / "img" / "sport"


def _index() -> str:
    # 이 PC 는 줄 끝을 CRLF 로 적는다 — 서버는 그대로 내주지만, 여기서는 LF 로 맞춰 놓고 본다
    return (FRONT / "index.html").read_text(encoding="utf-8").replace("\r\n", "\n")


def _art() -> dict:
    """종목 id → 가지고 있는 그림 ('mf' · 'm' · 'f')."""
    있는 = defaultdict(str)
    for p in sorted(ART.glob("*-[mf].webp")):
        있는[p.stem[:-2]] += p.stem[-1]
    return {i: "".join(sorted(v, reverse=True)) for i, v in 있는.items()}        # 'mf' · 'm' · 'f' — 남자 먼저 (코드의 표와 같은 순서)


def _sport_ids() -> set:
    data = json.loads((ROOT / "data" / "sample" / "sports.json").read_text(encoding="utf-8"))
    return {s["id"] for s in data["sports"]}


def test_그림은_종목id_와_성별로_이름_짓는다():
    있는 = _art()
    assert 있는, "고른 종목 그림이 한 장도 없다"
    assert set(있는) <= _sport_ids(), sorted(set(있는) - _sport_ids())      # 파일 이름 앞부분이 곧 종목 id 다
    남은 = [p.name for p in ART.glob("*.webp") if not re.fullmatch(r"[a-z0-9-]+-[mf]\.webp", p.name)]
    assert not 남은, 남은                                                    # 성별이 안 붙은 파일이 남아 있지 않게
    for p in sorted(ART.glob("*.webp")):
        b = p.read_bytes()
        assert b[:4] == b"RIFF" and b[8:12] == b"WEBP", p.name               # 확장자만 webp 인 파일이 섞이지 않게
        assert len(b) < 60_000, (p.name, len(b))                             # 휴대폰에서 금방 받는다 (지금 장당 12KB 안팎)


def test_코드가_아는_그림과_파일이_같다():
    """SPORT_ART 에 적은 것과 frontend/img/sport 의 파일이 어긋나면 404 가 나거나 그림이 안 나온다."""
    표 = _index().split("const SPORT_ART = {")[1].split("};")[0]
    적힌 = dict(re.findall(r"([a-z0-9-]+): '(mf|m|f)'", 표))
    assert 적힌 == _art(), (sorted(적힌.items() - _art().items()), sorted(_art().items() - 적힌.items()))


def test_성별에_맞는_그림을_고른다():
    본문 = _index().split("function sportArtUrl(step)")[1].split("\n}")[0]
    assert "const 원하는 = state.sex === 'F' ? 'f' : 'm';" in 본문            # 앱의 성별 값으로 고른다
    assert "있는.includes(원하는) ? 원하는 : 있는[0]" in 본문                  # 아직 그 성별 그림이 없으면 있는 쪽으로
    assert "`/img/sport/${step.id}-${" in 본문


def test_고른_종목은_그림_영상이_있으면_영상():
    html = _index()
    본문 = html.split("function sportArtUrl(step)")[1].split("\n}")[0]
    assert "step.출처 !== '종목'" in 본문                                      # 기록 종목(스쿼트 …)은 그대로 3D
    assert "youtubeVideoId(step.youtube_id)" in 본문                          # 영상이 있으면 영상이 먼저
    보이기 = html.split("function show3dForStep(step)")[1].split("\n}")[0]
    assert "if (showSportArt(step)) { MOVE_3D.stop(); box.hidden = true; return; }" in 보이기   # 3D 보다 먼저, 띄웠으면 3D 는 접는다
    그림 = html.split("function showSportArt(step)")[1].split("\n}")[0]
    assert "if (!url) { art.hidden = true; return false; }" in 그림           # 그림이 없는 종목에서 앞 종목 그림이 남지 않게
    assert 'id="sportArt"' in html and 'id="sportArtImg"' in html
    assert "*배워서 하는 종목이라 동작 대신 그림으로 보여 드려요. (그림: AI 생성)" in html   # AI 로 그렸다고 화면에 적는다
    assert ".sport-art img{ width:min(100%, 320px); aspect-ratio:1;" in html  # 3D 와 같은 자리·같은 크기


def test_그림이_없는_종목은_예전처럼_3D():
    """32개를 다 그리기 전까지는 그림이 없는 종목이 있다 — 그때는 비슷한 3D 동작으로 간다."""
    html = _index()
    본문 = html.split("function poseForStep(step)")[1].split("\n}")[0]
    assert "POSE_FOR_SPORT[step.id] || null" in 본문
    없는 = _sport_ids() - set(_art())
    if 없는:
        표 = html.split("const POSE_FOR_SPORT = {")[1].split("};")[0]
        assert re.search(r"[a-z]+: '[a-z0-9-]+'", 표), "3D 로 잇는 표가 사라졌다"
