"""영상이 없는 동작을 3D 느낌 그림으로 (M5).

고른 종목·기록 종목은 공식 영상이 없다. 그 자리에 사람이 그 동작을 하는
모습을 띄우고, 아래에 대체했다고 적는다. 진짜 3D 모델이 아니라 형체만
살린 입체 그림이다 — 외부 파일·서버 없이 돈다.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _js() -> str:
    return (ROOT / "frontend" / "js" / "move-3d.js").read_text(encoding="utf-8")


def _index() -> str:
    return (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")


def test_자세_그림을_재료로_쓴다():
    """34개 동작이 이미 검증돼 있다. 새로 그리지 않는다."""
    js = _js()
    assert "readPose('pose-' + poseId)" in js and "readPose('poseb-' + poseId)" in js
    assert "getElementById(id)" in js                       # 문서에 심어 둔 <symbol> 을 읽는다


def test_path_문법을_읽는다():
    """자세 그림은 M · L · H · V · Q 만 쓴다. Q 는 몇 점으로 편다."""
    js = _js().split("function parsePath(d)")[1].split("\n  }")[0]
    for cmd in ("'M'", "'L'", "'H'", "'V'", "'Q'"):
        assert f"cmd === {cmd}" in js, cmd
    assert "k <= 6" in js                                   # 곡선을 여섯 점으로


def test_부위별로_색이_다르다():
    """2D 한 색 선 그림은 팔·다리·기구가 겹치면 헷갈린다."""
    js = _js()
    assert "head:" in js and "body:" in js and "gear:" in js
    본문 = js.split("function classify(pose)")[1].split("\n  }")[0]
    assert "touchesHead" in 본문                            # 머리에 닿은 선에서 시작해
    assert "'body' : 'gear'" in 본문                        # 이어진 건 몸, 떨어진 건 기구·바닥


def test_입체로_그린다():
    js = _js()
    assert "createRadialGradient" in js                      # 머리는 구
    캡슐 = js.split("function capsule(ctx, l, col, w, s)")[1].split("\n  }")[0]
    assert "col.dark" in 캡슐 and "col.base" in 캡슐 and "col.light" in 캡슐   # 그림자 → 바탕 → 하이라이트
    assert "ellipse(" in js                                 # 발밑 그림자


def test_두_프레임_사이를_오간다_움직임_줄이기_존중():
    js = _js().split("function start(canvas, poseId)")[1].split("\n  }")[0]
    assert "lerpPose(a, b, t)" in js
    assert "prefers-reduced-motion: reduce" in js
    assert "requestAnimationFrame(frame)" in js
    assert "function stop(){ if (raf) { cancelAnimationFrame(raf); raf = null; } }" in _js()


def test_플레이어에_붙어_있다():
    html = _index()
    assert html.index('src="js/move-art.js"') < html.index('src="js/move-3d.js"')   # 자세 뒤에
    assert 'id="exercise3d"' in html and 'id="exercise3dCanvas"' in html
    assert "*해당하는 영상이 없어 3D로 대체했습니다." in html


def test_영상이_있으면_영상_없으면_3D():
    html = _index()
    본문 = html.split("function poseForStep(step)")[1].split("\n}")[0]
    assert "if (!step || youtubeVideoId(step.youtube_id)) return null;" in 본문
    assert "if (step.출처 === '기록') return step.id || null;" in 본문     # 기록 종목 id = 자세 id
    assert "POSE_FOR_SPORT[step.id] || null" in 본문                      # 없는 종목은 아무것도
    멈춤 = html.split("function stopExerciseVideo()")[1].split("\n}")[0]
    assert "show3dForStep(step);" in 멈춤
    보이기 = html.split("function show3dForStep(step)")[1].split("\n}")[0]
    assert "MOVE_3D.start($('exercise3dCanvas'), pose)" in 보이기
    assert "MOVE_3D.stop(); box.hidden = true;" in 보이기


def test_종목은_비슷한_자세로_잇는다():
    html = _index()
    표 = html.split("const POSE_FOR_SPORT = {")[1].split("};")[0]
    for k, v in (("running", "run"), ("cycling", "cycle"), ("swimming", "swim"), ("hiking", "stair"), ("walking", "walk")):
        assert f"{k}: '{v}'" in 표, k
    assert "soccer" not in 표 and "tennis" not in 표         # 엉뚱한 동작을 보여 주느니 안 보여 준다


def test_화면을_떠나면_멈춘다():
    html = _index()
    assert "if(id !== 's4') MOVE_3D.stop();" in html
