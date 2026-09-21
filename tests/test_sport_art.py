"""고른 종목(테니스 · 발레 · 수영 …)은 3D 동작 대신 그림 한 장.

예현(2026-09-21): "사용자가 선택한 본운동(수영, 발레, 요가 등)은 이미지로 대체하자.
보통 우리 앱에서의 도움만으로 되지 않고 학원에서 배워야 하거나 이미 기본적인 것들을 알고 있을 가능성이 커서."
그림체는 시안 다섯(픽토그램 · 라인 · 플랫 · SD 캐릭터 · 3D 클레이) 가운데 플랫 일러스트로 골랐다.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONT = ROOT / "frontend"
ART = FRONT / "img" / "sport"


def _index() -> str:
    # 이 PC 는 줄 끝을 CRLF 로 적는다 — 서버는 그대로 내주지만, 여기서는 LF 로 맞춰 놓고 본다
    return (FRONT / "index.html").read_text(encoding="utf-8").replace("\r\n", "\n")


def _art_ids() -> set:
    return {p.stem for p in ART.glob("*.webp")}


def _sport_ids() -> set:
    data = json.loads((ROOT / "data" / "sample" / "sports.json").read_text(encoding="utf-8"))
    return {s["id"] for s in data["sports"]}


def test_그림은_고른_종목의_id_로_둔다():
    ids = _art_ids()
    assert ids, "고른 종목 그림이 한 장도 없다"
    assert ids <= _sport_ids(), sorted(ids - _sport_ids())          # 파일 이름이 곧 종목 id 다
    for p in sorted(ART.glob("*.webp")):
        b = p.read_bytes()
        assert b[:4] == b"RIFF" and b[8:12] == b"WEBP", p.name       # 확장자만 webp 인 파일이 섞이지 않게
        assert len(b) < 60_000, (p.name, len(b))                     # 휴대폰에서 금방 받는다 (지금 장당 12KB 안팎)


def test_코드가_아는_그림과_파일이_같다():
    """SPORT_ART 에 적은 것과 frontend/img/sport 의 파일이 어긋나면 404 가 나거나 그림이 안 나온다."""
    표 = _index().split("const SPORT_ART = new Set([")[1].split("]);")[0]
    적힌 = set(re.findall(r"'([a-z0-9-]+)'", 표))
    assert 적힌 == _art_ids(), (sorted(적힌 - _art_ids()), sorted(_art_ids() - 적힌))


def test_고른_종목은_그림_영상이_있으면_영상():
    html = _index()
    본문 = html.split("function sportArtUrl(step)")[1].split("\n}")[0]
    assert "step.출처 !== '종목'" in 본문                              # 기록 종목(스쿼트 …)은 그대로 3D
    assert "youtubeVideoId(step.youtube_id)" in 본문                  # 영상이 있으면 영상이 먼저
    assert "`/img/sport/${step.id}.webp`" in 본문
    보이기 = html.split("function show3dForStep(step)")[1].split("\n}")[0]
    assert "if (showSportArt(step)) { MOVE_3D.stop(); box.hidden = true; return; }" in 보이기   # 3D 보다 먼저, 띄웠으면 3D 는 접는다
    그림 = html.split("function showSportArt(step)")[1].split("\n}")[0]
    assert "if (!url) { art.hidden = true; return false; }" in 그림   # 그림이 없는 종목에서 앞 종목 그림이 남지 않게
    assert 'id="sportArt"' in html and 'id="sportArtImg"' in html
    assert "*배워서 하는 종목이라 동작 대신 그림으로 보여 드려요. (그림: AI 생성)" in html   # AI 로 그렸다고 화면에 적는다
    assert ".sport-art img{ width:min(100%, 320px); aspect-ratio:1;" in html         # 3D 와 같은 자리·같은 크기


def test_그림이_없는_종목은_예전처럼_3D():
    """32개를 다 그리기 전까지는 그림이 없는 종목이 있다 — 그때는 비슷한 3D 동작으로 간다."""
    html = _index()
    본문 = html.split("function poseForStep(step)")[1].split("\n}")[0]
    assert "POSE_FOR_SPORT[step.id] || null" in 본문
    표 = html.split("const POSE_FOR_SPORT = {")[1].split("};")[0]
    남은 = _sport_ids() - _art_ids()
    if 남은:                                                          # 아직 안 그린 종목이 있으면 그 자리는 3D 나 빈칸
        assert re.search(r"[a-z]+: '[a-z0-9-]+'", 표), "3D 로 잇는 표가 사라졌다"
