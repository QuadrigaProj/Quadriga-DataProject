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


def test_사람_몸으로_나눈다():
    """졸라맨이 아니다. 몸통·팔다리·기구·배경선을 가른 뒤 사람 몸으로 그린다."""
    js = _js()
    본문 = js.split("function classify(pose)")[1].split("\n  }")[0]
    assert "touchesHead" in 본문                            # 머리에 닿은 선에서 시작해
    assert "'torso' : 'limb'" in 본문                       # 머리에 닿은 건 몸통, 이어진 건 팔다리
    assert "'line'" in 본문 and "'gear'" in 본문             # 떨어진 건 바닥·물결 아니면 기구
    뼈대 = js.split("function skeleton(pose, kinds)")[1].split("\n  }")[0]
    assert "along(pts[0]) < 0.55 ? arms : legs" in 뼈대     # 몸통 위쪽에 붙으면 팔, 아래쪽이면 다리
    몸통 = js.split("function torso(ctx, sk, build, s)")[1].split("\n  }")[0]
    for 자리 in ("build.shoulder", "build.chest", "build.waist", "build.hip"):
        assert 자리 in 몸통, 자리                            # 어깨·가슴·허리·골반 폭이 다르다
    assert "function limb(ctx, pts, w0, w1, s)" in js       # 위팔은 굵고 손목은 가늘게


def test_성별에_따라_실루엣이_다르다():
    """남성은 어깨가 넓고, 여성은 골반이 넓고 허리가 들어가며 묶은 머리가 있다."""
    js = _js()
    표 = js.split("const BUILD = {")[1].split("};")[0]
    남 = dict(re.findall(r"(\w+): ([\d.]+)", 표.split("M:")[1].split("F:")[0]))
    여 = dict(re.findall(r"(\w+): ([\d.]+)", 표.split("F:")[1]))
    assert float(남["shoulder"]) > float(여["shoulder"])
    assert float(여["hip"]) > float(남["hip"])
    assert float(여["hip"]) > float(여["waist"]) + 2      # 허리가 들어간다
    assert "hair: 'short'" in 표.split("F:")[0] and "hair: 'tied'" in 표.split("F:")[1]
    머리 = js.split("function headAndHair(ctx, sk, build, s)")[1].split("\n  }")[0]
    assert "build.hair === 'tied'" in 머리                  # 묶은 머리는 머리 뒤에 덩이
    assert "function start(canvas, poseId, { sex } = {})" in js
    assert "BUILD[sex === 'F' ? 'F' : 'M']" in js           # 모르면 남성 실루엣


def test_회색_하나에_낮은_대비():
    """색이 아니라 음영으로 알아본다. 대비는 낮게."""
    js = _js()
    for 이름 in ("SKIN", "HAIR", "GEAR"):
        줄 = js.split(f"const {이름} = ")[1].split("\n")[0]
        색 = dict(re.findall(r"(base|dark|light): '#([0-9A-F]{6})'", 줄))
        assert set(색) == {"base", "dark", "light"}, 이름
        r, g, b = (int(색["base"][i:i + 2], 16) for i in (0, 2, 4))
        assert max(r, g, b) - min(r, g, b) < 24, 이름       # 회색 — 색조가 거의 없다
        밝음 = int(색["light"][:2], 16); 어둠 = int(색["dark"][:2], 16)
        assert 0 < 밝음 - 어둠 <= 0x50, 이름                 # 음영은 있되 대비는 낮게


def test_입체로_그린다():
    js = _js()
    assert "createRadialGradient" in js                      # 머리는 구
    음영 = js.split("function shade(ctx, x0, y0, x1, y1, col)")[1].split("\n  }")[0]
    assert "col.light" in 음영 and "col.base" in 음영 and "col.dark" in 음영   # 축과 직각으로 밝음 → 바탕 → 어둠
    assert "function segment(ctx, a, b, w0, w1, col, s)" in js                 # 굵기가 변하는 마디
    assert "ctx.arc(a[0] * s, a[1] * s, w0 / 2 * s, 0, Math.PI * 2); ctx.fill();" in js   # 관절은 둥글게, 마디와 같은 음영
    assert "ellipse(" in js                                 # 발밑 그림자


def test_두_프레임_사이를_오간다_움직임_줄이기_존중():
    js = _js().split("function start(canvas, poseId, { sex } = {})")[1].split("\n  }")[0]
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
    assert "MOVE_3D.start($('exercise3dCanvas'), pose, { sex: state.sex })" in 보이기   # 성별대로
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
