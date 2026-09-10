"""영상이 없는 동작을 3D 마네킹으로 (M5).

고른 종목·기록 종목은 공식 영상이 없다. 그 자리에 관절이 있는 사람 몸
(머리·목·가슴·골반·팔·다리·손·발)이 그 동작을 하는 모습을 띄우고, 아래에
대체했다고 적는다. three.js 로 짓는 진짜 3D — 빛과 그림자가 있고, 성별로
실루엣이 다르다.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _js() -> str:
    return (ROOT / "frontend" / "js" / "move-3d.js").read_text(encoding="utf-8")


def _art() -> str:
    return (ROOT / "frontend" / "js" / "move-art.js").read_text(encoding="utf-8")


def _index() -> str:
    return (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")


def _poses() -> str:
    return _js().split("const POSES = {")[1].split("\n  };")[0]


def test_three_js_는_고정_버전으로_한_번만_받는다():
    js = _js()
    assert re.search(r"THREE_URL = 'https://cdnjs\.cloudflare\.com/ajax/libs/three\.js/0\.\d+\.\d+/three\.min\.js'", js)
    로드 = js.split("function loadThree()")[1].split("\n  }")[0]
    assert "if (window.THREE) return Promise.resolve(window.THREE);" in 로드   # 있으면 다시 안 받는다
    assert "if (threeLoading) return threeLoading;" in 로드                    # 받는 중이면 기다린다
    assert "s.onerror" in 로드                                                  # 못 받으면 알린다
    assert "3D 그림을 불러오지 못했어요" in js                                  # 오프라인이면 안내만


def test_사람_몸이다_관절로_이어진_부위들():
    """졸라맨이 아니다. 골반 → 허리 → 목 → 머리, 어깨 → 팔꿈치 → 손목 → 손, 고관절 → 무릎 → 발목 → 발."""
    js = _js().split("function buildBody(T, sex)")[1].split("\n  }")[0]
    for 부위 in ("LatheGeometry", "pelvis", "chest", "neck", "skull", "hand", "foot", "heel"):
        assert 부위 in js, 부위
    assert "const spine = joint(root, 0, 0.12, 0);" in js
    assert "const sh = joint(spine, side * D.shW, 0.35, 0, 'XZY');" in js       # 어깨는 가슴에
    assert "const el = joint(sh, 0, -D.uArm, 0);" in js and "const wr = joint(el, 0, -D.fArm, 0);" in js
    assert "const hip = joint(root, side * D.hipW, -0.02, 0, 'XZY');" in js     # 고관절은 골반에
    assert "const kn = joint(hip, 0, -D.thigh, 0);" in js and "const an = joint(kn, 0, -D.shin, 0);" in js
    assert "CylinderGeometry(r0, r1, len, 24)" in js                            # 관절 쪽이 굵고 끝이 가는 마디


def test_성별에_따라_실루엣이_다르다():
    js = _js()
    표 = js.split("const DIM = {")[1].split("\n  };")[0]
    남, 여 = 표.split("F:")[0], 표.split("F:")[1]
    def 값(블록, k): return float(re.search(rf"\b{k}: ([\d.]+)", 블록).group(1))
    assert 값(남, "shW") > 값(여, "shW")            # 남성은 어깨가 넓고
    assert 값(여, "hipW") > 값(남, "hipW")          # 여성은 골반이 넓다
    assert "hair: 'short'" in 남 and "hair: 'tied'" in 여 and "bust: true" in 여
    몸 = js.split("function buildBody(T, sex)")[1].split("\n  }")[0]
    assert "DIM[sex === 'F' ? 'F' : 'M']" in 몸      # 모르면 남성
    assert "D.hair === 'tied'" in 몸 and "bun" in 몸 and "tail" in 몸   # 묶은 머리
    assert "MOVE_3D.start($('exercise3dCanvas'), pose, { sex: state.sex })" in _index()   # 사용자 성별대로


def test_회색_하나에_빛과_그림자():
    js = _js()
    assert re.search(r"MeshStandardMaterial\(\{ color: 0x[A-F0-9]{6}, roughness", js)
    무대 = js.split("function setup(T, me, P)")[1].split("\n  }")[0]
    assert "renderer.shadowMap.enabled = true" in 무대
    assert "key.castShadow = true" in 무대 and "ShadowMaterial" in 무대     # 바닥엔 그림자만
    assert "HemisphereLight" in 무대 and "DirectionalLight" in 무대
    assert "alpha: true" in 무대                                          # 카드 배경이 비친다


def test_동작마다_두_자세_사이를_오간다_움직임_줄이기_존중():
    js = _js()
    무대 = js.split("function setup(T, me, P)")[1].split("\n  }")[0]
    assert "lerpPose(P.a, P.b, t)" in 무대
    assert "prefers-reduced-motion: reduce" in 무대
    assert "requestAnimationFrame(frame)" in 무대
    assert "8 * Math.sin(ms / 1400)" in 무대                               # 카메라가 천천히 돌며 입체를 보여 준다
    assert "B.pivot.position.y = -lo + (p.lift || 0);" in js               # 가장 낮은 곳이 바닥에 닿는다


def test_자세_그림이_있는_동작은_모두_3D_자세가_있다():
    """move-art.js 의 34개 동작 하나하나에 앞·뒤 자세가 있다. 종목 대응표도 있는 자세만 가리킨다."""
    ids = set(re.findall(r'id="pose-([a-z0-9-]+)"', _art()))
    poses = set(re.findall(r"^\s+'([a-z0-9-]+)':\s+P\(", _poses(), re.M))
    assert ids and ids <= poses, ids - poses
    표 = _index().split("const POSE_FOR_SPORT = {")[1].split("};")[0]
    for 자세 in re.findall(r": '([a-z0-9-]+)'", 표):
        assert 자세 in poses, 자세


def test_누운_동작은_눕고_기구가_있는_동작은_기구가_있다():
    p = _poses()
    for 동작 in ("pushup", "plank", "swim"):
        assert re.search(rf"'{동작}':\s+P\(\{{ \.\.\.PRONE", p), 동작
    for 동작 in ("crunch", "bridge", "bench-press", "dead-bug"):
        assert re.search(rf"'{동작}':\s+P\(\{{ \.\.\.SUPINE", p), 동작
    for 동작, 기구 in (("deadlift", "barbell"), ("dumbbell-curl", "dumbbells"), ("kettlebell-swing", "kettlebell"),
                      ("cycle", "bike"), ("jump-rope", "rope"), ("stair", "steps"), ("swim", "water")):
        assert f"gear: '{기구}'" in p.split(f"'{동작}':")[1].split("\n")[0] + p.split(f"'{동작}':")[1].split("\n")[1], 동작
    기구 = _js().split("function buildGear(T, name, B, scene)")[1].split("\n  }")[0]
    for 이름 in ("barbell", "backbar", "bench", "pulldown", "legpress", "dumbbells", "kettlebell", "treadmill", "bike", "rower", "rope", "steps", "wall", "water"):
        assert f"case '{이름}':" in 기구, 이름


def test_양쪽_값은_펼치고_발목은_서_있으면_바닥에_평평하게():
    js = _js().split("function expand(p)")[1].split("\n  }")[0]
    assert "BOTH[k].forEach(kk => { if (p[kk] === undefined) q[kk] = v; })" in js   # sh → shL·shR, 한쪽 값이 우선
    assert "Math.abs(q.rx) < 60 ? q.rx - q['hip' + s] + q['kn' + s] : 0" in js


def test_플레이어에_붙어_있다():
    html = _index()
    assert html.index('src="js/move-art.js"') < html.index('src="js/move-3d.js"')
    assert 'id="exercise3d"' in html and 'id="exercise3dCanvas"' in html
    assert "*해당하는 영상이 없어 3D로 대체했습니다." in html


def test_영상이_있으면_영상_없으면_3D():
    html = _index()
    본문 = html.split("function poseForStep(step)")[1].split("\n}")[0]
    assert "if (!step || youtubeVideoId(step.youtube_id)) return null;" in 본문
    assert "if (step.출처 === '기록') return step.id || null;" in 본문
    assert "POSE_FOR_SPORT[step.id] || null" in 본문
    멈춤 = html.split("function stopExerciseVideo()")[1].split("\n}")[0]
    assert "show3dForStep(step);" in 멈춤
    보이기 = html.split("function show3dForStep(step)")[1].split("\n}")[0]
    assert "MOVE_3D.stop(); box.hidden = true;" in 보이기


def test_화면을_떠나면_멈추고_자원을_돌려준다():
    assert "if(id !== 's4') MOVE_3D.stop();" in _index()
    멈춤 = _js().split("function stop(canvas)")[1].split("\n  }")[0]
    assert "cancelAnimationFrame(me.raf)" in 멈춤
    assert "me.renderer.dispose(); me.renderer.forceContextLoss();" in 멈춤   # WebGL 문맥을 놓아 준다
